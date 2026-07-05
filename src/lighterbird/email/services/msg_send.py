"""Email send-queue service mixin.

Extracted from :mod:`msg_ops` to keep file sizes under 500 lines.
Provides SMTP send, outbox persistence, and deferred retry with
exponential backoff.

Separated into a mixin class so ``MessageOpsService`` in :mod:`msg_ops`
can inherit and expose all methods through a single public interface.

Message composition is provided by :class:`MsgSendComposeMixin`
(``msg_compose``). Queue management is provided by :class:`MsgQueueMixin`
(``msg_queue``).
"""

from __future__ import annotations

from lighterbird.email.services.msg_compose import MsgSendComposeMixin
from lighterbird.email.services.msg_queue import MsgQueueMixin


class MsgSendQueueMixin(MsgSendComposeMixin, MsgQueueMixin):
    """Combined mixin providing email send + send-queue retry methods.

    Expects the host class to set::

        self.db          # database connection
        self._account_service  # account lookup with password
    """
    pass


__all__ = ["MsgSendQueueMixin"]
