"""FastAPI dependency injection for service singletons."""

from __future__ import annotations

from lighterbird.core.storage import AttachmentStore
from lighterbird.email.service import EmailService
from lighterbird.calendar.service import CalendarService
from lighterbird.contacts.services import ContactService
from lighterbird.contacts.db import get_db as get_contacts_db
from lighterbird.todo.services import TodoService
from lighterbird.todo.db import get_db as get_todo_db
from lighterbird.journal.services import JournalService
from lighterbird.journal.db import get_db as get_journal_db
from lighterbird.user_commands.service import UserCommandsService

_email_service: EmailService | None = None
_calendar_service: CalendarService | None = None
_contact_service: ContactService | None = None
_todo_service: TodoService | None = None
_journal_service: JournalService | None = None
_attachment_store: AttachmentStore | None = None
_user_commands_service: UserCommandsService | None = None


def get_email_service() -> EmailService:
    """Get the singleton EmailService."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


def get_calendar_service() -> CalendarService:
    """Get the singleton CalendarService."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = CalendarService()
    return _calendar_service


def get_contact_service() -> ContactService:
    """Get the singleton ContactService."""
    global _contact_service
    if _contact_service is None:
        db = get_contacts_db()
        _contact_service = ContactService(db)
    return _contact_service


def get_todo_service() -> TodoService:
    """Get the singleton TodoService."""
    global _todo_service
    if _todo_service is None:
        db = get_todo_db()
        _todo_service = TodoService(db)
    return _todo_service


def get_journal_service() -> JournalService:
    """Get the singleton JournalService."""
    global _journal_service
    if _journal_service is None:
        db = get_journal_db()
        _journal_service = JournalService(db)
    return _journal_service


def get_user_commands_service() -> UserCommandsService:
    """Get the singleton UserCommandsService."""
    global _user_commands_service
    if _user_commands_service is None:
        _user_commands_service = UserCommandsService()
    return _user_commands_service


def get_attachment_store() -> AttachmentStore:
    """Get the singleton AttachmentStore."""
    global _attachment_store
    if _attachment_store is None:
        _attachment_store = AttachmentStore()
    return _attachment_store


def reset_services() -> None:
    """Reset all service singletons (useful for testing)."""
    global _email_service, _calendar_service
    global _contact_service, _todo_service, _journal_service
    global _attachment_store, _user_commands_service
    _email_service = None
    _calendar_service = None
    _contact_service = None
    _todo_service = None
    _journal_service = None
    _attachment_store = None
    _user_commands_service = None
