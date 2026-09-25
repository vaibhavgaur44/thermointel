"""Phase 5 hierarchical ML inference using frozen Phase 4 artifacts."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd

import joblib
import numpy as np

from models.enums import EventCategory, EventType, PipelineStage, SourceType
from models.event import ClassificationResult, Event
from pipeline.base import PipelineStageNotImplemented
from pipeline.feature_engineering import RAW_FEATURES

STAGE = PipelineStage.ML_INFERENCE

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "ml"

PREPROCESSOR = joblib.load(MODEL_DIR / "preprocessing_final.joblib")

MODELS = {
    "m1": joblib.load(MODEL_DIR / "m1_model_final.joblib"),
    "m2": joblib.load(MODEL_DIR / "m2_model_final.joblib"),
    "m3": joblib.load(MODEL_DIR / "m3_model_final.joblib"),
    "m4": joblib.load(MODEL_DIR / "m4_model_final.joblib"),
}

MAPPINGS = {
    name: json.loads(
        (MODEL_DIR / f"{name}_class_mapping_final.json").read_text(
            encoding="utf-8"
        )
    )
    for name in MODELS
}

REVERSE_MAPPINGS = {
    name: {int(index): label for label, index in mapping.items()}
    for name, mapping in MAPPINGS.items()
}


def loaded_models() -> dict[str, Any]:
    return MODELS.copy()


def is_available() -> bool:
    return all(model is not None for model in MODELS.values())


def _transform(features: dict[str, Any]):
    row = {name: features.get(name) for name in RAW_FEATURES}
    X = pd.DataFrame([row], columns=RAW_FEATURES)
    return PREPROCESSOR.transform(X)


def _predict(model_name: str, features: dict[str, Any]):
    X = _transform(features)
    model = MODELS[model_name]

    probabilities = model.predict_proba(X)[0]
    index = int(np.argmax(probabilities))
    label = REVERSE_MAPPINGS[model_name][index]
    confidence = float(probabilities[index])

    return label, confidence


def classify_sync(
    event: Event,
    features: dict[str, Any],
) -> ClassificationResult:
    """Run the frozen M1→M2/M3→M4 hierarchy."""

    m1_label, m1_confidence = _predict("m1", features)

    # M1: AGRICULTURAL vs INDUSTRIAL
    if m1_label == "AGRICULTURAL":
        m2_label, m2_confidence = _predict("m2", features)

        event_type = (
            EventType.AGRICULTURAL_FIRE
            if m2_label == "AGRICULTURAL_FIRE"
            else EventType.FOREST_FIRE
        )

        return ClassificationResult(
            event_category=EventCategory.AGRICULTURAL,
            event_type=event_type,
            source_type=None,
            confidence=m2_confidence,
            model_version_id="thermointel-phase4-final",
            inferred_at=datetime.now(timezone.utc),
        )

    # M1: INDUSTRIAL → M3
    m3_label, m3_confidence = _predict("m3", features)

    if m3_label == "INDUSTRIAL_FIRE":
        return ClassificationResult(
            event_category=EventCategory.INDUSTRIAL,
            event_type=EventType.INDUSTRIAL_FIRE,
            source_type=None,
            confidence=m3_confidence,
            model_version_id="thermointel-phase4-final",
            inferred_at=datetime.now(timezone.utc),
        )

    # M3: PERSISTENT_SOURCE → M4
    m4_label, m4_confidence = _predict("m4", features)

    try:
        source_type = SourceType(m4_label)
    except ValueError:
        source_type = SourceType.UNKNOWN_PERSISTENT_SOURCE

    return ClassificationResult(
        event_category=EventCategory.INDUSTRIAL,
        event_type=EventType.PERSISTENT_HEAT_SOURCE,
        source_type=source_type,
        confidence=m4_confidence,
        model_version_id="thermointel-phase4-final",
        inferred_at=datetime.now(timezone.utc),
    )


async def classify(
    event: Event,
    features: dict[str, Any],
) -> ClassificationResult:
    return classify_sync(event, features)