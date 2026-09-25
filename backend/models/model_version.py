"""Model registry: version, dataset, features, metrics, artifacts.

Populated in Phase 4 when real models are trained and evaluated. Metrics are
stored verbatim from the evaluation notebook - the API never computes them.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models.common import BaseDocument, utc_now
from models.enums import ModelRole


class EvaluationMetrics(BaseModel):
    true_positives: Optional[int] = None
    false_positives: Optional[int] = None
    true_negatives: Optional[int] = None
    false_negatives: Optional[int] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    roc_auc: Optional[float] = None
    pr_auc: Optional[float] = None
    confusion_matrix: Optional[list[list[int]]] = None
    calibration_method: Optional[str] = None
    calibration_error: Optional[float] = None


class ModelVersion(BaseDocument):
    model_version_id: str
    role: ModelRole
    algorithm: Optional[str] = None  # e.g. "xgboost"
    is_active: bool = False

    dataset_version: Optional[str] = None
    feature_set: list[str] = Field(default_factory=list)
    hyperparameters: dict = Field(default_factory=dict)
    class_labels: list[str] = Field(default_factory=list)

    metrics: EvaluationMetrics = Field(default_factory=EvaluationMetrics)

    artifact_uri: Optional[str] = None
    notes: Optional[str] = None

    trained_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
