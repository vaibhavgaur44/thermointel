"""Stage 4 - hierarchical ML inference (Phase 4 / 5).

Model stack (Phase 1, section 6):
    M1  Agricultural vs Industrial
    M2A Agricultural subtype  -> Forest / Agricultural / Unknown Agricultural
    M2B Industrial event type -> Industrial Fire vs Persistent Heat Source
    M3  Persistent source subtype -> Gas Flare / Power Plant / ... / Unknown

No model is trained, bundled or simulated in Phase 2. ``classify`` raises, and
``ClassificationResult`` stays empty, so the UI shows an explicit
"model unavailable" state instead of a fabricated confidence.
"""
from models.enums import ModelRole, PipelineStage
from models.event import ClassificationResult, Event
from pipeline.base import PipelineStageNotImplemented

STAGE = PipelineStage.ML_INFERENCE

MODEL_STACK = [
    ModelRole.M1_AGRICULTURAL_VS_INDUSTRIAL,
    ModelRole.M2A_AGRICULTURAL_SUBTYPE,
    ModelRole.M2B_INDUSTRIAL_EVENT_TYPE,
    ModelRole.M3_PERSISTENT_SOURCE_SUBTYPE,
]


def loaded_models() -> dict[ModelRole, None]:
    """No artifacts are loaded in Phase 2."""
    return {role: None for role in MODEL_STACK}


def is_available() -> bool:
    return any(model is not None for model in loaded_models().values())


async def classify(event: Event, features: dict) -> ClassificationResult:
    raise PipelineStageNotImplemented(STAGE, "Phase 4 (ML) / Phase 5 (integration)")
