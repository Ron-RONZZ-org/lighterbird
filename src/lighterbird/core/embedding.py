"""Local embedding via fastembed — offline fallback for style RAG.

Resolution order:
1. If the configured LLM provider supports ``/embeddings`` → use it
   (no extra deps, any language the API supports).
2. Else if ``fastembed`` is installed → use the configured local model.
3. Else → embedding is unavailable (cowrite uses style guide only).

Usage::

    from lighterbird.core.embedding import embed, get_status, install

    status = get_status()
    if status["status"] == "ready":
        vectors = await embed(["text to embed"])
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from typing import Any

from lightercore.exceptions import AIError

logger = logging.getLogger(__name__)

# ── Supported models ──────────────────────────────────────────────────────

LOCAL_MODELS: dict[str, dict[str, Any]] = {
    "bge-small-en-v1.5": {
        "label": "English only",
        "hf_id": "BAAI/bge-small-en-v1.5",
        "dim": 384,
        "size_mb": 67,
        "languages": ["en"],
    },
    "paraphrase-multilingual-MiniLM-L12-v2": {
        "label": "Multilingual (50 languages)",
        "hf_id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "dim": 384,
        "size_mb": 220,
        "languages": [
            "ar", "bg", "ca", "cs", "da", "de", "el", "en", "es", "et",
            "fa", "fi", "fr", "ga", "gu", "he", "hi", "hr", "hu", "id",
            "it", "ja", "ko", "lt", "lv", "ms", "nl", "no", "pl", "pt",
            "pt_BR", "ro", "ru", "sk", "sl", "sr", "sv", "th", "tl",
            "tr", "uk", "ur", "vi", "zh_CN", "zh_TW",
        ],
    },
}

_FASTEMBED_AVAILABLE: bool | None = None
_MODEL_INSTANCE: Any = None


# ── Status ────────────────────────────────────────────────────────────────


def _check_fastembed() -> bool:
    """Check if ``fastembed`` is importable (cached)."""
    global _FASTEMBED_AVAILABLE
    if _FASTEMBED_AVAILABLE is None:
        try:
            import fastembed  # noqa: F401
            _FASTEMBED_AVAILABLE = True
        except ImportError:
            _FASTEMBED_AVAILABLE = False
    return _FASTEMBED_AVAILABLE


def get_status() -> dict[str, Any]:
    """Return the current embedding status.

    Returns:
        Dict with keys:
        - ``status``: ``"api-available"``, ``"local-ready"``, or
          ``"not-installed"``
        - ``model``: Current model name / HF ID (if ready).
        - ``dim``: Embedding dimension (if known).
        - ``models``: List of installable local models.
    """
    # 1. Check if the provider has a working embed()
    from lighterbird.core.ai import get_provider as get_core_provider
    from lighterbird.server.llm.provider import get_provider as get_wrapper

    try:
        wrapper = get_wrapper()
        if wrapper.is_available():
            core = get_core_provider(wrapper.config)
            return {
                "status": "api-available",
                "model": core._embedding_model(),
                "dim": None,
                "models": list(LOCAL_MODELS.values()),
            }
    except Exception:
        pass

    # 2. Check local fastembed
    if _check_fastembed():
        model_name = _current_local_model()
        info = LOCAL_MODELS.get(model_name) or LOCAL_MODELS.get(
            os.environ.get("LIGHTERBIRD_EMBED_MODEL", "bge-small-en-v1.5")
        )
        return {
            "status": "local-ready",
            "model": (info or {}).get("hf_id", model_name),
            "dim": (info or {}).get("dim"),
            "models": list(LOCAL_MODELS.values()),
        }

    return {
        "status": "not-installed",
        "model": None,
        "dim": None,
        "models": list(LOCAL_MODELS.values()),
    }


def _current_local_model() -> str | None:
    if _MODEL_INSTANCE is not None:
        return getattr(_MODEL_INSTANCE, "model_name", None)
    return None


# ── Embed ─────────────────────────────────────────────────────────────────


async def embed(texts: list[str]) -> list[list[float]] | None:
    """Embed texts using the best available method.

    1. LLM provider ``/embeddings`` endpoint.
    2. fastembed local model.
    3. ``None`` if neither is available.

    Args:
        texts: Text strings to embed.

    Returns:
        Float vectors, one per input, or ``None``.
    """
    # 1. Try API provider
    from lighterbird.core.ai import get_provider as get_core_provider
    from lighterbird.server.llm.provider import get_provider as get_wrapper

    try:
        wrapper = get_wrapper()
        if wrapper.is_available():
            core = get_core_provider(wrapper.config)
            try:
                return await core.embed(texts)
            except AIError:
                logger.debug("API embed failed, falling back to local")
            except Exception:
                logger.debug("API embed error, falling back to local")
    except Exception:
        pass

    # 2. Try local fastembed
    if _check_fastembed():
        try:
            return await _local_embed(texts)
        except Exception:
            logger.warning("Local embed failed", exc_info=True)

    return None


async def _local_embed(texts: list[str]) -> list[list[float]]:
    """Embed via fastembed (ONNX, runs sync in thread pool)."""
    global _MODEL_INSTANCE

    if _MODEL_INSTANCE is None:
        from fastembed import TextEmbedding

        model_name = _resolve_model_name()
        _MODEL_INSTANCE = TextEmbedding(
            model_name=model_name,
            max_length=512,
        )

    loop = asyncio.get_event_loop()
    docs = await loop.run_in_executor(
        None, lambda: list(_MODEL_INSTANCE.embed(texts))
    )
    return docs  # type: ignore[return-value]


# ── Install ───────────────────────────────────────────────────────────────


def install(model_name: str) -> dict[str, Any]:
    """Install fastembed and download the specified model.

    Args:
        model_name: Key in :data:`LOCAL_MODELS`.

    Returns:
        Dict with ``success`` and ``message``.

    Raises:
        ValueError: Unknown model.
    """
    if model_name not in LOCAL_MODELS:
        raise ValueError(
            f"Unknown model {model_name!r}. "
            f"Available: {list(LOCAL_MODELS)}"
        )

    info = LOCAL_MODELS[model_name]

    # Step 1: pip install fastembed
    logger.info("Installing fastembed package...")
    _run_pip_install("fastembed")
    logger.info("fastembed installed.")

    # Step 2: pre-download the model
    logger.info("Downloading model %s (%s)...", info["hf_id"], info["label"])
    _pre_download_model(info["hf_id"])
    logger.info("Model %s ready.", info["hf_id"])

    # Reset cached availability so subsequent calls detect the new install
    global _FASTEMBED_AVAILABLE, _MODEL_INSTANCE
    _FASTEMBED_AVAILABLE = None
    _MODEL_INSTANCE = None

    return {
        "success": True,
        "message": f"Installed {info['hf_id']} ({info['size_mb']} MB, {info['dim']} dim)",
    }


def _run_pip_install(package: str) -> None:
    """Run pip install, trying uv first then pip."""
    uv = shutil.which("uv")
    if uv:
        try:
            subprocess.run(
                [uv, "pip", "install", package],
                check=True, capture_output=True, timeout=120,
            )
            return
        except subprocess.CalledProcessError:
            logger.warning("uv pip install failed, falling back to pip")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        check=True, capture_output=True, timeout=120,
    )


def _pre_download_model(hf_id: str) -> None:
    """Pre-download model so first embed is instant."""
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=hf_id, max_length=512)
    list(model.embed(["warmup"]))


def _resolve_model_name() -> str:
    """Return configured model HF ID or default ``bge-small-en-v1.5``."""
    name = os.environ.get("LIGHTERBIRD_EMBED_MODEL", "bge-small-en-v1.5")
    if name in LOCAL_MODELS:
        return LOCAL_MODELS[name]["hf_id"]
    return name


def available_models() -> list[dict[str, Any]]:
    """Return installable local embedding models."""
    return list(LOCAL_MODELS.values())


__all__ = [
    "available_models",
    "embed",
    "get_status",
    "install",
]
