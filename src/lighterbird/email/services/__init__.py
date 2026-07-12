"""Email service classes."""

from lighterbird.email.services.accounts import AccountService
from lighterbird.email.services.backlog import (
    BacklogLockError,
    BacklogOperation,
    BacklogService,
)
from lighterbird.email.services.dead_letter import DeadLetterService
from lighterbird.email.services.flag_sync import FlagSyncService
from lighterbird.email.services.messages import MessageService
from lighterbird.email.services.msg_ops import MessageOpsService
from lighterbird.email.services.sieve import SieveService
from lighterbird.email.services.signatures import SignatureService

__all__ = [
    "AccountService",
    "BacklogLockError",
    "BacklogService",
    "DeadLetterService",
    "FlagSyncService",
    "MessageOpsService",
    "MessageService",
    "SieveService",
    "SignatureService",
]
