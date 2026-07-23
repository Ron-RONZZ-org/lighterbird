"""Spam/fraud reporting REST API routes.

Provides endpoints for:
- ``POST /api/v1/email/spam/report`` — mark message as spam, fraudulent, or ham
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lighterbird.email.service import EmailService
from lighterbird.server.deps import get_email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/email/spam", tags=["email-spam"])


class SpamReportRequest(BaseModel):
    """Request body for spam/fraud/ham reporting.

    Attributes:
        uuid: Message UUID to report.
        type: ``"spam"``, ``"fraud"``, or ``"ham"``.
        delay_seconds: Seconds to delay IMAP backlog enqueue (for undo).
            Default 0 (immediate). Pass >= 5 to get an ``operation_id``
            back for undo.
    """
    uuid: str = Field(..., description="Message UUID")
    type: str = Field(..., description="Report type: spam, fraud, or ham")
    delay_seconds: float = Field(default=0.0, ge=0, description="Seconds to delay IMAP backlog enqueue (for undo)")

    model_config = {"extra": "forbid"}


@router.post("/report")
def report_spam(
    data: SpamReportRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Report a message as spam, fraudulent, or false positive (ham).

    **Spam**: Trains the Bayesian token model, sets ``is_spam=1`` on the
    message.  The message is flagged locally; IMAP MOVE to the Spam folder is
    handled by the sync backlog.

    **Fraudulent**: Does NOT train the Bayesian model (would pollute
    token frequencies with legitimate brand names).  Instead, records
    the sender domain in the phishing watchlist and hard-deletes the
    message.

    **Ham**: Trains the Bayesian token model as NOT spam, clears
    ``is_spam``.  Use for false-positive correction.

    When ``delay_seconds`` > 0, the IMAP backlog enqueue (or hard-delete
    for fraud) is deferred and an ``operation_id`` is returned.  Call
    ``POST /email/actions/undo/{id}`` within the window to revert.

    Returns:
        Dict with ``status``, ``type``, ``uuid``, and optionally
        ``operation_id``.
    """
    if data.type not in ("spam", "fraud", "ham"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report type: {data.type}. Use 'spam', 'fraud', or 'ham'.",
        )

    # Fetch the message
    msg = email_svc.messages.get(data.uuid)
    if not msg:
        raise HTTPException(status_code=404, detail=f"Message not found: {data.uuid}")

    account_email = msg.get("account_email", "")
    subject = msg.get("subject", "") or ""
    body = msg.get("body", "") or ""
    op_id = None

    if data.type == "spam":
        # Train Bayesian model immediately (harmless — just token stats)
        spam_detect = email_svc.spam_detect
        spam_detect.trainer.report(subject, body, account_email, is_spam=True)
        spam_detect.trainer.log_feedback(data.uuid, account_email, "spam")
        # Update message flags immediately
        email_svc.db.execute(
            "UPDATE messages SET is_spam = 1, spam_reported = 1 WHERE uuid = ?",
            (data.uuid,),
        )
        # Run classifier and store score
        result = spam_detect.classifier.classify(subject, body, account_email)
        if result["score"] is not None:
            email_svc.db.execute(
                "UPDATE messages SET spam_score = ? WHERE uuid = ?",
                (result["score"], data.uuid),
            )
        # Store similarity data for future near-duplicate detection
        try:
            email_svc.similarity.add_spam(
                data.uuid, subject, body, account_email,
            )
        except Exception:
            logger.warning(
                "Failed to store similarity data for %s", data.uuid,
                exc_info=True,
            )

        # Defer IMAP backlog if undo requested
        if data.delay_seconds > 0:
            from lighterbird.email.undo import get_undo_registry

            registry = get_undo_registry()
            op_id = registry.schedule(
                action="spam",
                msg_uuid=data.uuid,
                account_email=account_email,
                folder_name=msg.get("folder_name"),
                imap_uid=msg.get("imap_uid"),
                delay=data.delay_seconds,
            )

            def _revert_spam():
                now = datetime.now(UTC).isoformat()
                email_svc.db.execute(
                    "UPDATE messages SET is_spam = 0, spam_reported = 0, "
                    "updated_at = ? WHERE uuid = ?",
                    (now, data.uuid),
                )

            def _commit_spam():
                fresh = email_svc.get(data.uuid)
                if fresh and fresh.get("imap_uid"):
                    email_svc.msg_ops.backlog.enqueue_trash(
                        msg_uuid=data.uuid,
                        account_email=fresh["account_email"],
                        folder_name=fresh.get("folder_name"),
                        imap_uid=fresh["imap_uid"],
                    )

            registry.set_callbacks(op_id, _revert_spam, _commit_spam)

    elif data.type == "fraud":
        # Phishing watchlist update immediately
        phish = email_svc.phishing
        phish.report_fraudulent(
            from_addr=msg.get("from_addr", ""),
            subject=subject,
            body=body,
            account_email=account_email,
            message_uuid=data.uuid,
        )

        if data.delay_seconds > 0:
            # Defer local DB change + IMAP hard-delete
            from lighterbird.email.undo import get_undo_registry

            registry = get_undo_registry()
            op_id = registry.schedule(
                action="fraud",
                msg_uuid=data.uuid,
                account_email=account_email,
                folder_name=msg.get("folder_name"),
                imap_uid=msg.get("imap_uid"),
                delay=data.delay_seconds,
            )

            def _commit_fraud():
                email_svc.db.execute(
                    "UPDATE messages SET phishing_detected = 1, is_deleted = 1 "
                    "WHERE uuid = ?",
                    (data.uuid,),
                )

            def _revert_fraud():
                pass  # Nothing to revert — DB hasn't changed yet

            registry.set_callbacks(op_id, _revert_fraud, _commit_fraud)
        else:
            # Immediate: mark as phishing and hard-delete
            email_svc.db.execute(
                "UPDATE messages SET phishing_detected = 1, is_deleted = 1 WHERE uuid = ?",
                (data.uuid,),
            )

    elif data.type == "ham":
        # Train Bayesian as NOT spam (immediate — can't undo training)
        spam_detect = email_svc.spam_detect
        spam_detect.trainer.report(subject, body, account_email, is_spam=False)
        spam_detect.trainer.log_feedback(data.uuid, account_email, "ham")
        # Clear spam flags
        email_svc.db.execute(
            "UPDATE messages SET is_spam = 0, spam_reported = 0, ham_reported = 1 "
            "WHERE uuid = ?",
            (data.uuid,),
        )
        # Re-classify to update score
        result = spam_detect.classifier.classify(subject, body, account_email)
        if result["score"] is not None:
            email_svc.db.execute(
                "UPDATE messages SET spam_score = ? WHERE uuid = ?",
                (result["score"], data.uuid),
            )
        # Remove similarity data (false positive — don't match against this)
        try:
            email_svc.similarity.remove_message(data.uuid)
        except Exception:
            logger.warning(
                "Failed to remove similarity data for %s", data.uuid,
                exc_info=True,
            )

    response = {
        "status": "ok" if not op_id else "pending",
        "type": data.type,
        "uuid": data.uuid,
    }
    if op_id:
        response["operation_id"] = op_id
    return response
