"""FastAPI dependency injection for thread-safe service singletons.

Uses a registry dict with a threading lock to ensure each service is
initialised exactly once, even under concurrent requests.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from lighterbird.calendar.service import CalendarService
from lighterbird.contacts.db import get_db as get_contacts_db
from lighterbird.contacts.services import ContactService
from lighterbird.core.storage import AttachmentStore
from lighterbird.email.service import EmailService
from lighterbird.journal.db import get_db as get_journal_db
from lighterbird.journal.services import JournalService
from lighterbird.letter.db import get_db as get_letter_db
from lighterbird.letter.services.letters import LetterService
from lighterbird.profiles.services.profiles import ProfileService
from lighterbird.tags.service import TagService
from lighterbird.todo.db import get_db as get_todo_db
from lighterbird.todo.services import TodoService
from lighterbird.user_commands.service import UserCommandsService

_lock = threading.Lock()
_services: dict[str, Any] = {}


def _get_or_create(name: str, factory: Callable[[], Any]) -> Any:
    """Return a named singleton, creating it once under a lock."""
    if name in _services:
        return _services[name]
    with _lock:
        if name not in _services:
            _services[name] = factory()
        return _services[name]


def get_email_service() -> EmailService:
    """Get the singleton EmailService."""
    return _get_or_create("email", EmailService)


def get_calendar_service() -> CalendarService:
    """Get the singleton CalendarService."""
    return _get_or_create("calendar", CalendarService)


def get_contact_service() -> ContactService:
    """Get the singleton ContactService."""
    def _factory() -> ContactService:
        db = get_contacts_db()
        return ContactService(db)
    return _get_or_create("contact", _factory)


def get_todo_service() -> TodoService:
    """Get the singleton TodoService."""
    def _factory() -> TodoService:
        db = get_todo_db()
        return TodoService(db)
    return _get_or_create("todo", _factory)


def get_journal_service() -> JournalService:
    """Get the singleton JournalService."""
    def _factory() -> JournalService:
        db = get_journal_db()
        return JournalService(db)
    return _get_or_create("journal", _factory)


def get_profiles_service() -> ProfileService:
    """Get the singleton ProfileService."""
    return _get_or_create("profiles", ProfileService)


def get_user_commands_service() -> UserCommandsService:
    """Get the singleton UserCommandsService."""
    return _get_or_create("user_commands", UserCommandsService)


def get_letter_service() -> LetterService:
    """Get the singleton LetterService."""
    def _factory() -> LetterService:
        db = get_letter_db()
        return LetterService(db)
    return _get_or_create("letter", _factory)


def get_tag_service() -> TagService:
    """Get the singleton TagService."""
    return _get_or_create("tag", TagService)


def get_attachment_store() -> AttachmentStore:
    """Get the singleton AttachmentStore."""
    return _get_or_create("attachment", AttachmentStore)


def reset_services() -> None:
    """Reset all service singletons (useful for testing)."""
    global _services
    with _lock:
        _services = {}
