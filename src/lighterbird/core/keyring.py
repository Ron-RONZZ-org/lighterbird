"""System keyring abstraction for lighterbird.

Delegates to ``lighterllm.llm.config`` for the canonical implementation.
Kept as a separate module for backward compatibility — importers continue
to work unchanged.
"""

from __future__ import annotations

from lighterllm.llm.config import keyring_delete as delete_password
from lighterllm.llm.config import keyring_get as get_password
from lighterllm.llm.config import keyring_set as set_password

__all__ = [
    "delete_password",
    "get_password",
    "set_password",
]
