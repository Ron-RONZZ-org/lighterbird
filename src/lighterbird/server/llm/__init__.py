"""LLM provider abstraction and multi-round tool-calling loop for lighterbird.

Supports OpenAI-compatible APIs and Ollama.

The :mod:`~lighterbird.server.llm.tool_loop` module provides the shared
multi-round tool-calling loop used by both ``/api/v1/chat`` and
``/api/v1/prompt-commands/execute``.
"""
