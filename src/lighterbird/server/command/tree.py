"""Command tree — auto-generated from ``@command()`` and ``@group()`` decorator registrations.

Replaces the hardcoded 1369-line tree data with auto-generated output.
Helper functions are re-exported from ``registry`` for backward compatibility.

To add a new command to the tree, simply add metadata to its ``@command()``
decorator — the tree is auto-generated and never goes out of sync.
"""

from __future__ import annotations

# Re-export everything from registry for backward compatibility.
# tree.py used to be the single source of truth; now registry.py is.
# These imports ensure existing code that does
# ``from lighterbird.server.command.tree import ...`` continues to work.

from lighterbird.server.command.registry import (  # noqa: F401
    get_command_tree,
    find_tree_node,
    find_command_depth,
    get_param_names,
)
