"""Phase 5 event formation.

Until grouping parameters are calibrated from production data, each
detection is represented as one event. No arbitrary spatial/time thresholds
are introduced.

The grouping parameters below are the fields declared in
``docs/ARCHITECTURE.md`` ("Deliberately unfrozen configuration"): they stay
``None`` and ``is_calibrated`` stays ``False`` until the owner calibrates
them. When calibration happens, only the values change - the schema and the
persisted Event shape do not.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.database import Collections, get_db
from models.detection import ThermalDetection
from models.enums import DataOrigin, EventStatus, PipelineStage
from models.event import Event, ThermalMetrics

STAGE = PipelineStage.EVENT_FORMATION


@dataclass
class EventFormationConfig:
    """Deliberately unfrozen grouping configuration (ARCHITECTURE.md).

    Grouping values are ``None`` until calibrated from production data by
    the project owner. No code path may substitute defaults for them.
    """

    # Spatial grouping radius in km. None => grouping disabled (1:1).
    grouping_radius_km: Optional[float] = None
    # Temporal grouping window in hours. None => grouping disabled (1:1).
    time_window_hours: Optional[float] = None
    # Minimum detections to constitute a grouped event.
    min_detections: Optional[int] = None
    # Grace period in hours before an event expires (UNFROZEN grouping
    # parameter - NOT used by the basic lifecycle mechanism below).
    grace_period_hours: Optional[float] = None

    # Basic lifecycle expiry window (Task 24B). Must be one of the existing
    # intended configurable lifecycle periods (1 hour, 6 hours, 24 hours,
    # 1 week); None disables expiry. ASSUMPTION (reported): the demo runs
    # with the 24-hour window - a supported owner value, chosen as the
    # simplest safe default matching the frontend's default 24h view. This
    # is a lifecycle display-window choice, NOT threat calibration.
    expiry_window_hours: Optional[float] = 24.0

    is_calibrated = False


# The lifecycle periods the configuration supports (existing intended set).
SUPPORTED_EXPIRY_WINDOW_HOURS = (1.0, 6.0, 24.0, 168.0)


CONFIG = EventFormationConfig()


async def group_detections(
    detections: list[ThermalDetection],
) -> list[Event]:
    events = []

    for detection in detections:
        event_id = f"evt-{detection.observation_id}"

        event = Event(
            event_id=event_id,
            status=EventStatus.ACTIVE,
            # Production/demo separation: an event carries the data origin of
            # the detection that formed it. Demo detections can never
            # produce production events and vice versa.
            data_origin=detection.data_origin,
            centroid=detection.location,
            state=detection.state,
            first_detected=detection.acquired_at,
            last_detected=detection.acquired_at,
            detection_count=1,
            detection_ids=[detection.observation_id],
            metrics=ThermalMetrics(
                peak_frp=detection.frp,
                latest_frp=detection.frp,
                mean_frp=detection.frp,
                spatial_extent_km2=0.0,
            ),
        )

        events.append(event)

    return events


async def persist_events(events: list[Event]) -> int:
    if not events:
        return 0

    db = get_db()
    collection = db[Collections.EVENTS]

    inserted = 0

    for event in events:
        # Idempotent upsert keyed on the unique event_id. ``created_at`` is
        # set only on first insert ($setOnInsert) so re-processing the same
        # detections never rewrites the original creation timestamp.
        set_doc = event.to_mongo()
        created_at = set_doc.pop("created_at", None)
        on_insert = {"created_at": created_at} if created_at else {}

        result = await collection.update_one(
            {"event_id": event.event_id},
            (
                {"$set": set_doc, "$setOnInsert": on_insert}
                if on_insert
                else {"$set": set_doc}
            ),
            upsert=True,
        )

        if result.upserted_id is not None:
            inserted += 1

    # Write event_id back to the raw detection only.
    for event in events:
        if event.detection_ids:
            await db[Collections.THERMAL_DETECTIONS].update_many(
                {"observation_id": {"$in": event.detection_ids}},
                {"$set": {"event_id": event.event_id}},
            )

    return inserted


async def expire_stale_events(
    now: Optional[datetime] = None,
    config: EventFormationConfig = CONFIG,
) -> int:
    """Basic safe lifecycle mechanism (Task 24B).

    An event stays ACTIVE while it is recently receiving detections and
    becomes EXPIRED once ``now - last_detected`` exceeds the configured
    expiry window. Deliberately simple and configurable:

    - only the ``status`` field transitions (ACTIVE -> EXPIRED); lifecycle
      fields (first_detected, last_detected, detection_count,
      detection_ids) are never altered
    - idempotent: only ACTIVE documents can transition, so re-running is a
      no-op
    - origin-agnostic by design: production and demo events follow the same
      lifecycle rule and are never cross-contaminated
    - no threat-dependent or spatial/temporal-grouping logic is involved
    """
    if config.expiry_window_hours is None:
        return 0
    if config.expiry_window_hours not in SUPPORTED_EXPIRY_WINDOW_HOURS:
        raise ValueError(
            "expiry_window_hours must be one of "
            f"{SUPPORTED_EXPIRY_WINDOW_HOURS} (got {config.expiry_window_hours})"
        )

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=config.expiry_window_hours)

    db = get_db()
    result = await db[Collections.EVENTS].update_many(
        {
            "status": EventStatus.ACTIVE.value,
            "last_detected": {"$lt": cutoff},
        },
        {"$set": {"status": EventStatus.EXPIRED.value, "updated_at": now}},
    )
    return result.modified_count