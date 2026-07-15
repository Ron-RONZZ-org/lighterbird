"""Local embedding via fastembed.

Resolution order (in ``embed()``):
1. LLM provider ``/embeddings`` endpoint (if available).
2. fastembed local model (always bundled in desktop builds; model
   weights downloaded on demand from HuggingFace Hub).
3. ``None`` if the model weights haven't been downloaded yet.

Status states:
- ``api-available`` — LLM provider supports embeddings.
- ``local-ready`` — fastembed model weights cached and ready.
- ``model-needed`` — fastembed is installed but no weights downloaded.
"""

from __future__ import annotations

import asyncio
import logging
import os
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

_MODEL_INSTANCE: Any = None


# ── Status ────────────────────────────────────────────────────────────────


def _model_is_downloaded() -> bool:
    """Check if the configured model's weights are cached locally."""
    try:
        from fastembed import TextEmbedding

        model = TextEmbedding(model_name=_resolve_model_name(), max_length=512)
        # fastembed raises if model not cached; if it succeeds, weights exist
        list(model.embed(["ping"]))
        return True
    except Exception:
        return False


def get_status() -> dict[str, Any]:
    """Return the current embedding status.

    Returns:
        Dict with keys ``status``, ``model``, ``dim``, ``models``.
    """
    from lighterbird.core.ai import get_provider as get_core_provider
    from lighterbird.server.llm.provider import get_provider as get_wrapper

    # 1. Check if the LLM provider supports embeddings
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

    # 2. Check if local model weights are cached
    if _model_is_downloaded():
        info = _current_model_info()
        return {
            "status": "local-ready",
            "model": (info or {}).get("hf_id", "unknown"),
            "dim": (info or {}).get("dim"),
            "models": list(LOCAL_MODELS.values()),
        }

    # 3. Model not downloaded yet
    return {
        "status": "model-needed",
        "model": None,
        "dim": None,
        "models": list(LOCAL_MODELS.values()),
    }


def _current_model_info() -> dict[str, Any] | None:
    """Return info dict for the currently configured model."""
    name = os.environ.get("LIGHTERBIRD_EMBED_MODEL", "bge-small-en-v1.5")
    return LOCAL_MODELS.get(name)


# ── Embed ─────────────────────────────────────────────────────────────────


async def embed(texts: list[str]) -> list[list[float]] | None:
    """Embed texts using the best available method.

    1. LLM provider ``/embeddings`` endpoint.
    2. fastembed local model (weights must be cached).
    3. ``None`` if neither is available.

    Args:
        texts: Text strings to embed.

    Returns:
        Float vectors or ``None``.
    """
    from lighterbird.core.ai import get_provider as get_core_provider
    from lighterbird.server.llm.provider import get_provider as get_wrapper

    # 1. Try API provider
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
    try:
        return await _local_embed(texts)
    except Exception:
        logger.debug("Local embed failed (model not downloaded?)")

    return None


async def _local_embed(texts: list[str]) -> list[list[float]]:
    """Embed via fastembed (ONNX, runs sync in thread pool)."""
    from fastembed import TextEmbedding

    global _MODEL_INSTANCE

    if _MODEL_INSTANCE is None:
        _MODEL_INSTANCE = TextEmbedding(
            model_name=_resolve_model_name(),
            max_length=512,
        )

    loop = asyncio.get_event_loop()
    docs = await loop.run_in_executor(
        None, lambda: list(_MODEL_INSTANCE.embed(texts))
    )
    return docs  # type: ignore[return-value]


# ── Install (download model weights; no pip needed) ─────────────────────


def install(model_name: str) -> dict[str, Any]:
    """Download the specified model weights from HuggingFace Hub.

    In desktop builds, fastembed is already bundled; only the model
    weights need to be fetched on first use.

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
    logger.info("Downloading model %s (%s)...", info["hf_id"], info["label"])
    _download_model(info["hf_id"])
    logger.info("Model %s ready.", info["hf_id"])

    # Reset cached instance so next embed uses the new model
    global _MODEL_INSTANCE
    _MODEL_INSTANCE = None

    return {
        "success": True,
        "message": f"Downloaded {info['hf_id']} ({info['size_mb']} MB, {info['dim']} dim)",
    }


def _download_model(hf_id: str) -> None:
    """Pre-download model weights so first embed call is instant."""
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
