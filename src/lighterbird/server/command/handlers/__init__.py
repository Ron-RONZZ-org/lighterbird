"""Side-effect imports to register all command handlers.

Each module is imported for its ``@command`` / ``@alias`` side effects.
"""

from lighterbird.server.command.handlers import email  # noqa: F401
from lighterbird.server.command.handlers import email_sieve  # noqa: F401
from lighterbird.server.command.handlers import email_signature  # noqa: F401
from lighterbird.server.command.handlers import email_account  # noqa: F401
from lighterbird.server.command.handlers import calendar  # noqa: F401
from lighterbird.server.command.handlers import sync  # noqa: F401
from lighterbird.server.command.handlers import help  # noqa: F401
from lighterbird.server.command.handlers import contacts  # noqa: F401
from lighterbird.server.command.handlers import todo  # noqa: F401
from lighterbird.server.command.handlers import journal  # noqa: F401
from lighterbird.server.command.handlers import llm  # noqa: F401
from lighterbird.server.command.handlers import backup  # noqa: F401
from lighterbird.server.command.handlers import user_commands  # noqa: F401
from lighterbird.server.command.handlers import user_profiles  # noqa: F401
from lighterbird.server.command.handlers import drafts  # noqa: F401
from lighterbird.server.command.handlers import letter  # noqa: F401

# ── Group metadata ────────────────────────────────────────────────────────

from lighterbird.server.command.registry import group, register_interactive_form

group("email", description="Email operations", default_action="list")
group("calendar", description="Calendar operations", default_action="list")
group("contact", description="Contact management", default_action="list")
group("todo", description="Task management", default_action="list")
group("journal", description="Journal entries", default_action="list")

# ── Interactive forms ─────────────────────────────────────────────────────
# Commands that have an interactive form popup in the frontend.
# Over time, add ``interactive=True`` to the @command() decorator instead.

_INTERACTIVE_FORMS = {
    "email.send": "email-send",
    "email.reply": "email-send",
    "email.forward": "email-send",
    "email.sieve.add": "email-sieve-add",
    "email.sieve.modify": "email-sieve-modify",
    "calendar.event.add": "calendar-event-add",
    "contact.add": "contacts-add",
    "contact.modify": "contacts-modify",
    "email.account.add": "email-account-add",
    "email.account.modify": "email-account-modify",
    "calendar.account.add": "calendar-account-add",
    "calendar.account.modify": "calendar-account-modify",
    "todo.add": "todo-add",
    "todo.modify": "todo-modify",
    "todo.template.add": "todo-template-add",
    "todo.template.modify": "todo-template-modify",
    "journal.write": "journal-write",
    "user.saved-commands.add": "user-saved-commands-add",
    "user.saved-commands.modify": "user-saved-commands-modify",
    "user.info.add": "user-info-add",
    "user.info.modify": "user-info-modify",
    "llm.profile.new": "llm-profile-new",
    "llm.profile.set": "llm-profile-set",
    "backup.config.add": "backup-config-add",
    "backup.config.modify": "backup-config-modify",
    "backup.prune": "backup-prune",
    "sync": "sync",
    "letter.add": "letter-add",
    "letter.send": "letter-send",
    "todo.delete": "todo-delete",
    "todo.template.delete": "todo-template-delete",
    "email.account.delete": "email-account-delete",
    "calendar.event.delete": "calendar-event-delete",
    "calendar.account.delete": "calendar-account-delete",
    "backup.config.delete": "backup-config-delete",
    "user.saved-commands.delete": "user-saved-commands-delete",
    "journal.delete": "journal-delete",
    "reset": "reset-no-backup",
}

for path, form_type in _INTERACTIVE_FORMS.items():
    register_interactive_form(path, form_type)
