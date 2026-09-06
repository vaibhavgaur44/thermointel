"""
ThermoIntel ML inference layer — Milestone 1.

Loads the two pre-trained XGBoost artifacts (model1: agricultural vs industrial,
model2: persistent_source vs industrial_fire) and exposes a single clean
`run_inference(observation)` function that the later FIRMS ingestion pipeline
can call once real feature values are computed.

IMPORTANT:
- Models are NOT retrained here. Artifacts are loaded exactly as provided.
- These models were trained against heuristic pseudo-labels. Their metrics
  (including any 100% scores) reflect reproduction of those labeling rules,
  not independently validated real-world accuracy.
"""
import logging
import math
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

logger = logging.getLogger("thermointel.ml_inference")

MODELS_DIR = Path(__file__).parent.parent / "models"
MODEL1_PATH = MODELS_DIR / "model1_agricultural_vs_industrial.joblib"
MODEL2_PATH = MODELS_DIR / "model2_persistent_vs_industrial_fire.joblib"

# Fallback negative-class names, used only if an artifact does not carry
# enough information to resolve the non-positive label on its own.
MODEL1_NEGATIVE_CLASS = "agricultural"
MODEL2_NEGATIVE_CLASS = "persistent_source"

DISCLAIMER = (
    "Trained on heuristic pseudo-labels. Reported metrics reflect reproduction "
    "of those labeling rules, not independently validated real-world accuracy."
)


def _safe_load(path: Path) -> Optional[dict]:
    if not path.exists():
        logger.warning("Model artifact not found: %s", path)
        return None
    try:
        artifact = joblib.load(path)
    except Exception:
        logger.exception("Failed to load model artifact: %s", path)
        return None
    if not isinstance(artifact, dict) or "model" not in artifact or "features" not in artifact:
        logger.error("Model artifact %s is missing required keys (model/features)", path)
        return None
    return artifact


_MODEL1 = _safe_load(MODEL1_PATH)
_MODEL2 = _safe_load(MODEL2_PATH)


def models_available() -> dict:
    return {"model1_loaded": _MODEL1 is not None, "model2_loaded": _MODEL2 is not None}


def get_feature_schema() -> dict:
    """Feature names/order read directly from the loaded artifacts, so the
    later FIRMS ingestion pipeline knows exactly what to compute per observation."""
    return {
        "model1_features": _MODEL1["features"] if _MODEL1 else None,
        "model2_features": _MODEL2["features"] if _MODEL2 else None,
    }


def _to_safe_float(value) -> float:
    """Convert any input to a finite float, or NaN for missing/invalid values.
    XGBoost natively handles NaN as a missing value during split evaluation."""
    if value is None:
        return float("nan")
    try:
        f = float(value)
    except (TypeError, ValueError):
        return float("nan")
    if math.isnan(f) or math.isinf(f):
        return float("nan")
    return f


def _build_feature_vector(observation: dict, feature_names: list) -> np.ndarray:
    values = [_to_safe_float(observation.get(name)) for name in feature_names]
    return np.array(values, dtype=float).reshape(1, -1)


def _resolve_class_names(artifact: dict, fallback_negative: str) -> list:
    """Resolve the [negative_label, positive_label] order matching classes_ == [0, 1]."""
    positive_class = artifact.get("positive_class")
    return [fallback_negative, positive_class]


def _predict(artifact: dict, observation: dict, fallback_negative: str):
    feature_names = artifact["features"]
    model = artifact["model"]
    class_names = _resolve_class_names(artifact, fallback_negative)
    X = _build_feature_vector(observation, feature_names)
    proba = model.predict_proba(X)[0]
    pred_idx = int(np.argmax(proba))
    label = class_names[pred_idx] if pred_idx < len(class_names) else str(pred_idx)
    probability = float(proba[pred_idx])
    return label, probability


def predict_model1(observation: dict):
    """Run model 1 (agricultural vs industrial). Raises if artifact failed to load."""
    if _MODEL1 is None:
        raise RuntimeError("Model 1 artifact is not available")
    return _predict(_MODEL1, observation, MODEL1_NEGATIVE_CLASS)


def predict_model2(observation: dict):
    """Run model 2 (persistent_source vs industrial_fire). Raises if artifact failed to load."""
    if _MODEL2 is None:
        raise RuntimeError("Model 2 artifact is not available")
    return _predict(_MODEL2, observation, MODEL2_NEGATIVE_CLASS)


def run_inference(observation: dict) -> dict:
    """
    Two-stage inference pipeline for a single thermal observation's feature dict.

    Model 1 always runs. Model 2 runs ONLY when Model 1 predicts "industrial".
    For "agricultural" observations, model2_class is "not_applicable" and
    model2_probability is None. final_class mirrors model1's negative outcome
    (agricultural) or model2's outcome (persistent_source / industrial_fire).
    """
    availability = models_available()
    if not availability["model1_loaded"]:
        raise RuntimeError("Model 1 artifact is not available; inference cannot run")

    model1_class, model1_probability = predict_model1(observation)

    if model1_class != "industrial":
        return {
            "model1_class": model1_class,
            "model1_probability": model1_probability,
            "model2_class": "not_applicable",
            "model2_probability": None,
            "final_class": model1_class,
            "disclaimer": DISCLAIMER,
        }

    if not availability["model2_loaded"]:
        return {
            "model1_class": model1_class,
            "model1_probability": model1_probability,
            "model2_class": "unavailable",
            "model2_probability": None,
            "final_class": "industrial",
            "disclaimer": DISCLAIMER,
        }

    model2_class, model2_probability = predict_model2(observation)
    return {
        "model1_class": model1_class,
        "model1_probability": model1_probability,
        "model2_class": model2_class,
        "model2_probability": model2_probability,
        "final_class": model2_class,
        "disclaimer": DISCLAIMER,
    }
