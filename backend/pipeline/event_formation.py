"""Stage 2 - event formation (Phase 5).

A FIRMS detection is NOT a ThermoIntel event. Nearby detections are grouped
into one event using spatial proximity + temporal proximity + spatial-cluster
continuity.

The grouping radius and time window are DELIBERATELY UNFROZEN in Phase 1
(section 29). They are exposed here as configuration so they can be set from
real data rather than invented.
"""
from dataclasses import dataclass
from typing import Optional

from models.detection import ThermalDetection
from models.enums import EventStatus, PipelineStage
from models.event import Event
from pipeline.base import PipelineStageNotImplemented

STAGE = PipelineStage.EVENT_FORMATION


@dataclass
class EventFormationConfig:
    """Unfrozen, data-driven parameters. None => not yet determined."""

    grouping_radius_km: Optional[float] = None
    grouping_time_window_hours: Optional[float] = None
    min_detections_per_event: Optional[int] = None
    # How long an event may go unsupported by the live feed before it stops
    # being ACTIVE. Historical records are retained regardless.
    active_grace_period_hours: Optional[float] = None

    @property
    def is_calibrated(self) -> bool:
        return None not in (
            self.grouping_radius_km,
            self.grouping_time_window_hours,
            self.active_grace_period_hours,
        )


CONFIG = EventFormationConfig()


async def group_detections(
    detections: list[ThermalDetection], config: EventFormationConfig = CONFIG
) -> list[Event]:
    raise PipelineStageNotImplemented(STAGE, "Phase 5 (integration)")


async def expire_unsupported_events(config: EventFormationConfig = CONFIG) -> int:
    """Transition ACTIVE events no longer supported by the live FIRMS feed to
    INACTIVE/EXPIRED. This removes them from the LIVE map only - the documents
    stay in MongoDB and keep contributing to baselines and features."""
    raise PipelineStageNotImplemented(STAGE, "Phase 5 (integration)")


LIVE_STATUSES = (EventStatus.ACTIVE,)
HISTORICAL_STATUSES = (EventStatus.INACTIVE, EventStatus.EXPIRED)
