"""Email message composition and outbox storage.

Provides the ``MsgSendComposeMixin`` with methods for composing email messages,
saving them to the Outbox folder, and reconstructing attachments for retry.

Methods defined here expect to be mixed into a class that sets::

    self.db               # database connection
    self._account_service  # account lookup with password
"""

from __future__ import annotations

import asyncio
import base64
import json as json_mod
import logging
import threading
import uuid as uuid_mod
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class MsgSendComposeMixin:
    """Mixin for email message composition and outbox storage.

    Expects the host class to set ``self.db`` and ``self._account_service``.
    """

    # ── Send email ─────────────────────────────────────────────────────────

    def send_email(
        self,
        account_email: str,
        to: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        priority: int = 3,
        body_format: str = "markdown",
        attachments: list[dict[str, Any]] | None = None,
        signature: str | None = None,
        signature_format: str = "plain",
        in_reply_to: str | None = None,
        *,
        save_as_sample: bool = True,
    ) -> dict[str, Any]:
        """Send an email via SMTP with outbox fallback on connection failure.

        Always saves the composed message to the local database first
        (folder = ``"Outbox"``). Then attempts SMTP delivery:

        * **On success**: moves the message to the ``"Sent"`` folder.
        * **On connection failure**: leaves the message in ``"Outbox"``
          and enqueues a retry with exponential backoff via
          :meth:`process_send_queue`.

        Args:
            account_email: Sender account email.
            to: Primary recipients.
            subject: Email subject.
            body: Message body (markdown, html, or plain text per body_format).
            cc: Carbon-copy recipients.
            bcc: Blind carbon-copy recipients.
            priority: 1 (highest) to 5 (lowest), default 3.
            body_format: "markdown" (default), "html", or "plain".
            attachments: List of dicts with ``name`` and ``data`` (base64).
            signature: Optional override signature. If None, uses account's
                stored signature from the database.
            in_reply_to: Message-ID of the message being replied to, for
                conversation threading (In-Reply-To / References headers).
            save_as_sample: If True (default), save as a writing sample
                for LLM cowrite style learning (RAG).

        Returns:
            Dict with ``status`` ("sent" or "queued"), ``uuid`` (message UUID),
            and ``message_id`` (SMTP Message-ID).
        """
        from lighterbird.email.smtp import SMTPClient

        acct = self._account_service.get_account_with_password(account_email)
        if not acct:
            exists = self._account_service.get(account_email)
            if not exists:
                raise ValueError(
                    f"Account '{account_email}' not found. "
                    f"Use !email account list to see available accounts."
                )
            raise ValueError(
                f"No password configured for account {account_email}. "
                f"Set it with: !email account modify {account_email} --password <pw>"
            )
        sender_email = acct.get("email", "")
        cc = cc or []
        bcc = bcc or []
        att_list = attachments or []
        smtp_port = acct.get("smtp_port", 587)

        # Resolve signature — use stored default if no override provided
        if signature is None:
            from lighterbird.email.services.signatures import SignatureService
            sig_svc = SignatureService(self.db)
            resolved = sig_svc.resolve(account_email)
            signature = (resolved or {}).get("signature_text", "")
            signature_format = (resolved or {}).get("signature_format", "plain")

        msg_uuid = str(uuid_mod.uuid4())
        message_id = str(uuid_mod.uuid4())

        # Parse body per body_format using the same rendering utility
        # used by the preview endpoint for consistency.
        from lighterbird.server.render_utils import convert_to_html

        html_body = ""
        final_body = body
        if body_format == "markdown" and body:
            html_body = convert_to_html(body, "markdown")
            final_body = body
        elif body_format == "html":
            html_body = body
            final_body = ""
        elif body_format == "plain" and body:
            html_body = convert_to_html(body, "plain")
        # "plain" with no body — no html_body, final_body stays as-is

        # Step 1: Save to Outbox folder first (never lose the message)
        self._ensure_folder(account_email, "Outbox")
        self._save_outbox_message(
            msg_uuid=msg_uuid,
            account_email=account_email,
            sender_email=sender_email,
            to=to,
            cc=cc,
            subject=subject,
            body=body,
            body_format=body_format,
            message_id=message_id,
            in_reply_to=in_reply_to,
            attachments=att_list,
        )

        # Step 2: Attempt SMTP send
        send_error: str | None = None
        client = SMTPClient(
            host=acct.get("smtp_server", ""),
            port=smtp_port,
            use_tls=acct.get("smtp_use_tls", 1) == 1,
            use_ssl=smtp_port == 465,
        )
        try:
            client.connect(
                username=acct.get("smtp_username", "") or sender_email,
                password=acct["password"],
            )
            client.send_email(
                from_addr=sender_email, to=to, subject=subject,
                body=final_body, cc=cc, bcc=bcc,
                html_body=html_body,
                attachments=att_list,
                signature=signature,
                signature_format=signature_format,
                message_id=message_id,
                in_reply_to=in_reply_to,
            )
        except ConnectionError as e:
            send_error = str(e)
        except Exception as e:
            send_error = str(e)
        finally:
            client.disconnect()

        # Step 3: On success → Sent + save writing sample; on failure → queue
        now = datetime.now(UTC).isoformat()
        if send_error is None:
            self.db.execute(
                "UPDATE messages SET folder_name = 'Sent', is_read = 1, "
                "updated_at = ? WHERE uuid = ?",
                (now, msg_uuid),
            )
            logger.info("Email %s sent successfully to %s", msg_uuid[:8], to)
            if save_as_sample:
                self._save_writing_sample(
                    sample_uuid=str(uuid_mod.uuid4()),
                    source_uuid=msg_uuid,
                    title=subject,
                    body=body,
                    body_format=body_format,
                )
            return {"status": "sent", "uuid": msg_uuid, "message_id": message_id}
        else:
            self._enqueue_send(msg_uuid, account_email, body_format, signature,
                               priority, send_error, signature_format)
            logger.warning(
                "Email %s queued for retry (SMTP failed: %s)", msg_uuid[:8], send_error,
            )
            return {"status": "queued", "uuid": msg_uuid, "message_id": message_id,
                    "error": send_error}

    # ── Writing sample registration (RAG) ────────────────────────────────

    def _save_writing_sample(
        self,
        sample_uuid: str,
        source_uuid: str,
        title: str,
        body: str,
        body_format: str = "markdown",
    ) -> None:
        """Save a sent email as a writing sample for LLM style learning.

        The embedding is computed asynchronously in a background thread
        (best-effort — failures are logged but do not affect the send flow).

        Args:
            sample_uuid: Unique identifier for the sample.
            source_uuid: UUID of the original message.
            title: Email subject.
            body: Email body text.
            body_format: Body format (``"markdown"``, ``"html"``, ``"plain"``).
        """
        from lighterbird.email.db import ensure_vec_table

        now = datetime.now(UTC).isoformat()
        word_count = len(body.split())

        self.db.execute(
            """INSERT INTO writing_samples
               (uuid, source_uuid, source_domain, title, body,
                body_format, language, word_count, registered_at)
               VALUES (?, ?, 'email', ?, ?, ?, 'en', ?, ?)""",
            (sample_uuid, source_uuid, title, body, body_format, word_count, now),
        )

        # Ensure vec0 table exists so retrieval queries don't fail even if
        # the background embedding thread hasn't run yet (or fails).
        ensure_vec_table(self.db)

        # Fire background thread to compute and store the embedding
        thread = threading.Thread(
            target=self._store_writing_sample_embedding,
            args=(sample_uuid, body),
            daemon=True,
        )
        thread.start()

    @staticmethod
    def _store_writing_sample_embedding(sample_uuid: str, body: str) -> None:
        """Compute embedding and store in vec_samples (runs in background thread).

        This is a static method because it creates its own DB connection
        and event loop for the async LLM provider call.

        Args:
            sample_uuid: Writing sample UUID.
            body: Email body text to embed.
        """
        import json as _json

        from lighterbird.core.ai import get_provider as _get_core_provider
        from lighterbird.email.db import ensure_vec_table as _ensure_vec
        from lighterbird.email.db import get_db as _get_db
        from lighterbird.server.llm.provider import get_provider as _get_wrapper

        try:
            db = _get_db()

            # Get the LLM provider
            wrapper = _get_wrapper()
            if not wrapper.is_available():
                return  # No LLM configured — skip embedding
            core = _get_core_provider(wrapper.config)

            # Compute embedding (async → sync via new event loop)
            dim: int = 1536
            embedding: list[float] | None = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(core.embed([body]))
                loop.close()
                if result:
                    embedding = result[0]
                    dim = len(embedding)
            except Exception:
                logger.debug("Embedding not available for sample %s", sample_uuid[:8])
                return

            if embedding is None:
                return

            # Ensure vec0 table exists with the detected dimension
            _ensure_vec(db, dim)
            rowid = db.execute_one(
                "SELECT rowid FROM writing_samples WHERE uuid = ?",
                (sample_uuid,),
            )
            if rowid is None:
                return
            rowid_val = rowid["rowid"]

            # Store vector and update dimension
            db.execute(
                "INSERT INTO vec_samples(rowid, embedding) VALUES (?, ?)",
                (rowid_val, _json.dumps(embedding)),
            )
            db.execute(
                "UPDATE writing_samples SET embedding_dim = ? WHERE uuid = ?",
                (dim, sample_uuid),
            )
            logger.debug("Stored embedding for sample %s (dim=%d)", sample_uuid[:8], dim)
        except Exception:
            logger.debug("Failed to store writing sample embedding for %s", sample_uuid[:8])

    # ── Outbox / send-queue helpers ───────────────────────────────────────

    def _ensure_folder(self, account_email: str, folder_name: str) -> None:
        """Create a folder if it does not exist for the given account."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (account_email, folder_name, now, now),
        )

    def _save_outbox_message(
        self,
        msg_uuid: str,
        account_email: str,
        sender_email: str,
        to: list[str],
        cc: list[str],
        subject: str,
        body: str,
        body_format: str,
        message_id: str,
        in_reply_to: str | None,
        attachments: list[dict[str, Any]],
    ) -> None:
        """Insert a message record into the Outbox folder and persist attachments."""
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            """INSERT INTO messages
               (uuid, account_email, folder_name, message_id, in_reply_to, from_addr,
                to_recipients, cc_recipients, subject, body, is_read,
                received_at, created_at, updated_at)
               VALUES (?, ?, 'Outbox', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (
                msg_uuid,
                account_email,
                message_id,
                in_reply_to or "",
                sender_email,
                json_mod.dumps(to),
                json_mod.dumps(cc),
                subject,
                body,
                now,
                now,
                now,
            ),
        )

        # Store attachments via AttachmentStore so they survive process restart
        if not attachments:
            return
        from lighterbird.core.storage import AttachmentStore

        store = AttachmentStore()
        for att in attachments:
            if not isinstance(att, dict):
                continue
            name = att.get("name", "attachment")
            data_b64 = att.get("data", "")
            try:
                raw = base64.b64decode(data_b64) if data_b64 else b""
            except Exception:
                raw = data_b64.encode("utf-8") if isinstance(data_b64, str) else b""
            if not raw:
                continue
            content_id = str(uuid_mod.uuid4())
            store.store(msg_uuid, content_id, raw)
            self.db.execute(
                """INSERT INTO email_attachments
                   (uuid, message_uuid, filename, mime_type, size, content_id,
                    storage_path, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid_mod.uuid4()),
                    msg_uuid,
                    name,
                    "application/octet-stream",
                    len(raw),
                    content_id,
                    str(store._message_dir(msg_uuid) / content_id),
                    now,
                    now,
                ),
            )

    # ── Attachment reconstruction ─────────────────────────────────────────

    def _reconstruct_attachments(self, msg_uuid: str) -> list[dict[str, Any]]:
        """Reconstruct attachment dicts from stored data for SMTPClient.

        Args:
            msg_uuid: The message UUID whose attachments to reconstruct.

        Returns:
            List of ``{"name": ..., "data": base64}`` dicts suitable for
            :meth:`SMTPClient.send_email`.
        """
        from lighterbird.core.storage import AttachmentStore

        rows = list(self.db.execute(
            "SELECT filename, content_id FROM email_attachments WHERE message_uuid = ?",
            (msg_uuid,),
        ))
        if not rows:
            return []
        store = AttachmentStore()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                raw = store.retrieve(msg_uuid, row["content_id"])
                data_b64 = base64.b64encode(raw).decode("ascii")
                result.append({"name": row["filename"], "data": data_b64})
            except FileNotFoundError:
                logger.warning(
                    "Attachment %s missing for message %s",
                    row["content_id"][:12], msg_uuid[:8],
                )
                continue
        return result


__all__ = ["MsgSendComposeMixin"]
