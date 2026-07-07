"""Embedding management API routes.

``GET  /api/v1/embed/status`` — check embedding availability.
``POST /api/v1/embed/install`` — download model weights from HuggingFace Hub.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from lighterbird.core.embedding import available_models, get_status, install

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/embed", tags=["embed"])


@router.get("/status")
def embed_status() -> dict:
    """Return the current embedding status.

    Used by the frontend to decide whether to show the download dialog.
    """
    return get_status()


@router.post("/install")
def embed_install(data: dict) -> dict:
    """Download model weights from HuggingFace Hub.

    Request body: ``{"model": "bge-small-en-v1.5"}``.
    Runs synchronously (blocks until download completes).
    No pip install is needed — fastembed is always bundled.
    """
    model_name = (data or {}).get("model", "").strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="model is required")

    try:
        result = install(model_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Model download failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return result
