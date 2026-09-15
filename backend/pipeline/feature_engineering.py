"""Stage 3 - feature engineering (Phase 4).

Phase 1 section 7 defines the FEATURE GROUPS but explicitly leaves the final
feature subset to be determined after the dataset exists. Only the group
vocabulary is declared here - no feature is computed.

Facility proximity is a feature. It is never a hidden decision rule.
"""
from models.enums import PipelineStage
from models.event import Event
from pipeline.base import PipelineStageNotImplemented

STAGE = PipelineStage.FEATURE_ENGINEERING

FEATURE_GROUPS = {
    "current_thermal": [
        "frp",
        "brightness_ti4",
        "brightness_ti5",
        "firms_confidence",
        "day_night",
        "satellite",
    ],
    "historical": [
        "frp_mean",
        "frp_median",
        "frp_max",
        "frp_variance",
        "frp_percentiles",
        "detection_frequency",
        "active_days",
        "historical_baseline",
    ],
    "change_anomaly": [
        "frp_vs_baseline",
        "change_rate",
        "recent_trend",
        "sudden_spike",
        "deviation_from_normal",
        "change_point_indicator",
    ],
    "spatial": [
        "detection_count",
        "detection_density",
        "spatial_spread",
        "cluster_characteristics",
        "cluster_stability",
    ],
    "context": [
        "facility_source_type",
        "facility_proximity_km",
        "nearby_facility_count",
    ],
}


async def build_feature_vector(event: Event) -> dict:
    raise PipelineStageNotImplemented(STAGE, "Phase 4 (ML)")
