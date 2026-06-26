"""Side-effect imports to register all command handlers.

Each module is imported for its ``@command`` / ``@alias`` side effects.
"""

from lighterbird.server.command.handlers import email  # noqa: F401
from lighterbird.server.command.handlers import calendar  # noqa: F401
from lighterbird.server.command.handlers import sync  # noqa: F401
from lighterbird.server.command.handlers import help  # noqa: F401
from lighterbird.server.command.handlers import contacts  # noqa: F401
from lighterbird.server.command.handlers import todo  # noqa: F401
from lighterbird.server.command.handlers import journal  # noqa: F401
from lighterbird.server.command.handlers import llm  # noqa: F401
from lighterbird.server.command.handlers import backup  # noqa: F401
from lighterbird.server.command.handlers import user_commands  # noqa: F401
