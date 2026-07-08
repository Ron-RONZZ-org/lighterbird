"""Multi-round tool-calling loop with HITL support.

Re-exports from :mod:`lightercore.llm.tool_loop` for backward compatibility.

The canonical implementation lives in lightercore — this module is a thin
re-export so existing import paths continue to work.
"""

from lightercore.llm.tool_loop import (  # noqa: F401
    _pending_executions,
    resume_execution,
    run_tool_loop,
    sanitize_tool_result,
    tc_path,
)

__all__ = [
    "_pending_executions",
    "resume_execution",
    "run_tool_loop",
    "sanitize_tool_result",
    "tc_path",
]
