"""Side-effect imports to register all command handlers.

Each module is imported for its ``@command`` side effects.
"""

import lighterbird.server.command.registry as _reg

# Suppress per-registration cache invalidations during bulk load.
# Use try/finally so an import failure doesn't leave _bulk_loading stuck True,
# which would permanently disable cache invalidation.
_reg._bulk_loading = True
try:
    from lighterbird.server.command.handlers import (
        backup,  # noqa: F401
        calendar,  # noqa: F401
        contacts,  # noqa: F401
        debug,  # noqa: F401
        drafts,  # noqa: F401
        email,  # noqa: F401
        email_account,  # noqa: F401
        email_sieve,  # noqa: F401
        email_signature,  # noqa: F401
        email_spam,  # noqa: F401
        help,  # noqa: F401
        journal,  # noqa: F401
        letter,  # noqa: F401
        llm,  # noqa: F401
        sync,  # noqa: F401
        tags,  # noqa: F401
        todo,  # noqa: F401
        user_commands,  # noqa: F401
        user_profiles,  # noqa: F401
    )
finally:
    _reg._bulk_loading = False

# ── Group metadata ────────────────────────────────────────────────────────

from lighterbird.server.command.registry import alias, group

group("email", description="Email operations", default_action="list")
group("email.folder", description="IMAP folder management")
alias(["email", "folders"], ["email", "folder", "list"])
group("calendar", description="Calendar operations", default_action="list")
group("contact", description="Contact management", default_action="list")
group("todo", description="Task management", default_action="list")
group("journal", description="Journal entries", default_action="list")
group("email.spam", description="Spam block management")
group("tag", description="Cross-domain tag management")
group("contact.category", description="Contact category management")

# Interactive forms are now declared inline on each @command() decorator
# via ``interactive=True`` and (where needed) ``form_type="..."``.
# No separate registration dict needed.
