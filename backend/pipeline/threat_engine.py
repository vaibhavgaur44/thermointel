"""Stage 5 & 6 - threat/anomaly engine and alert generation (Phase 4 / 5).

Threat is separate from classification confidence. The threat score considers
FRP magnitude, baseline deviation, rate of change, spatial behaviour, detection
strength, industrial context and validated anomaly signals.

The WEIGHTS and the ALERT THRESHOLD are deliberately unfrozen (Phase 1,
section 29). They are declared as configuration with no values so that nothing
arbitrary can be introduced in Phase 2.
"""
from dataclasses import dataclass, field
from typing import Optional

from models.enums import PipelineStage, ThreatLevel
from models.event import Event, ThreatAssessment
from pipeline.base import PipelineStageNotImplemented

THREAT_STAGE = PipelineStage.THREAT_ANALYSIS
ALERT_STAGE = PipelineStage.ALERT_GENERATION

THREAT_LEVELS = [
    ThreatLevel.LOW,
    ThreatLevel.MODERATE,
    ThreatLevel.HIGH,
    ThreatLevel.CRITICAL,
]

# Signal vocabulary the engine will score. No weight is assigned yet.
THREAT_SIGNALS = [
    "frp_magnitude",
    "baseline_deviation",
    "rate_of_change",
    "spatial_behaviour",
    "detection_strength",
    "industrial_context",
    "ml_evidence",
]


@dataclass
class ThreatEngineConfig:
    """All values None until validated against real data."""

    signal_weights: dict[str, Optional[float]] = field(
        default_factory=lambda: {signal: None for signal in THREAT_SIGNALS}
    )
    level_boundaries: dict[str, Optional[float]] = field(
        default_factory=lambda: {level.value: None for level in THREAT_LEVELS}
    )
    alert_threshold: Optional[float] = None
    threshold_profile: Optional[str] = None

    @property
    def is_calibrated(self) -> bool:
        return (
            self.alert_threshold is not None
            and all(v is not None for v in self.signal_weights.values())
        )


CONFIG = ThreatEngineConfig()


async def assess(event: Event, features: dict, config: ThreatEngineConfig = CONFIG) -> ThreatAssessment:
    raise PipelineStageNotImplemented(THREAT_STAGE, "Phase 4 (ML) / Phase 5")


async def generate_alerts(events: list[Event], config: ThreatEngineConfig = CONFIG) -> int:
    raise PipelineStageNotImplemented(ALERT_STAGE, "Phase 4 (ML) / Phase 5")
