from fastapi import APIRouter, Query

from core.config import settings
from models.enums import ModelRole
from models.model_version import ModelVersion
from pipeline import ml_inference
from services import registry_service

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=dict)
async def get_models(limit: int = Query(50, ge=1, le=200)):
    """Registered model versions. Empty until Phase 4 training happens."""
    versions = await registry_service.list_model_versions(limit=limit)
    return {
        "items": versions,
        "total": len(versions),
        "inference_available": ml_inference.is_available(),
        "active_model_version": settings.ACTIVE_MODEL_VERSION,
        "expected_model_stack": [role.value for role in ModelRole],
    }
