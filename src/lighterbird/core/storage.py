"""Attachment storage — filesystem-backed, metadata in DB.

Storage layout::

    {data_dir}/attachments/
        {message_uuid}/
            {content_id}            # raw bytes, one file per attachment

DB stores only metadata: ``filename``, ``mime_type``, ``size``,
``content_id``, ``storage_path``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from lighterbird.core.paths import data_dir

logger = logging.getLogger(__name__)


class AttachmentStore:
    """Filesystem-backed storage for email attachment blobs.

    Thread-safe for *different* message UUIDs (each gets its own
    subdirectory). For concurrent writes to the *same* message, the
    caller must coordinate (in practice, IMAP sync processes one
    message at a time per account).
    """

    def __init__(self) -> None:
        self._base = data_dir() / "attachments"
        # Directory created lazily on first store() call.

    # ── Public API ─────────────────────────────────────────────────────────

    def store(
        self,
        message_uuid: str,
        content_id: str,
        data: bytes,
    ) -> Path:
        """Store attachment bytes and return the storage path.

        Args:
            message_uuid: UUID of the parent message.
            content_id: Unique identifier for this attachment within
                the message (may be the ``Content-ID`` header or a
                generated UUID).
            data: Raw attachment bytes.

        Returns:
            Absolute path to the stored file.
        """
        self._base.mkdir(parents=True, exist_ok=True)
        msg_dir = self._message_dir(message_uuid)
        dest = msg_dir / self._safe_filename(content_id)
        dest.write_bytes(data)
        logger.debug(
            "Stored attachment %s for message %s (%d bytes)",
            content_id[:12],
            message_uuid[:8],
            len(data),
        )
        return dest

    def retrieve(self, message_uuid: str, content_id: str) -> bytes:
        """Retrieve attachment bytes by message UUID + content ID.

        Args:
            message_uuid: UUID of the parent message.
            content_id: Attachment content ID.

        Returns:
            Raw attachment bytes.

        Raises:
            FileNotFoundError: If the attachment does not exist on disk.
        """
        path = self._message_dir(message_uuid) / self._safe_filename(content_id)
        return path.read_bytes()

    def list_for_message(self, message_uuid: str) -> list[Path]:
        """List all stored attachment paths for a given message.

        Args:
            message_uuid: UUID of the parent message.

        Returns:
            Sorted list of file paths, or empty list if none exist.
        """
        msg_dir = self._message_dir(message_uuid)
        if not msg_dir.is_dir():
            return []
        return sorted(msg_dir.iterdir())

    def delete_all(self, message_uuid: str) -> None:
        """Delete all attachments for a message (orphan cleanup).

        Args:
            message_uuid: UUID of the parent message.
        """
        msg_dir = self._message_dir(message_uuid)
        if msg_dir.is_dir():
            shutil.rmtree(msg_dir, ignore_errors=True)
            logger.debug("Deleted attachments for message %s", message_uuid[:8])

    def total_size(self, message_uuid: str) -> int:
        """Total size in bytes of all attachments for a message.

        Args:
            message_uuid: UUID of the parent message.
        """
        return sum(
            p.stat().st_size for p in self.list_for_message(message_uuid)
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    def _message_dir(self, message_uuid: str) -> Path:
        """Return (and create) the per-message attachment directory."""
        d = self._base / message_uuid
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _safe_filename(content_id: str) -> str:
        """Sanitize a content_id for use as a filename.

        Strips directory components (prevents ``../etc/passwd`` style
        path traversal from user-controlled IMAP headers) and removes
        null bytes.
        """
        # Strip directory components — ``Path.name`` on any platform
        # returns only the final path component.
        safe = Path(content_id).name
        # Remove null bytes which can cause issues on some filesystems
        safe = safe.replace("\0", "")
        # Replace backslash (path separator on Windows, regular char on
        # Linux — safe to normalize either way)
        safe = safe.replace("\\", "_")
        return safe


__all__ = ["AttachmentStore"]
