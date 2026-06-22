"""Command dispatch package for lighterbird.

Routes ``POST /api/v1/command`` to registered handler functions.
See :mod:`registry` for the decorator-based dispatch system.
"""

from lighterbird.server.command import handlers  # noqa: F401 — side-effect: registers handlers
