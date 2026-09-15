"""DEVELOPMENT / DEMO DATASET - NOT OPERATIONAL INTELLIGENCE.

Every document produced here is tagged ``data_origin = "demo"``. The API never
returns demo documents unless a request explicitly passes ``include_demo=true``,
and the UI shows a permanent "DEMO DATA" banner while that mode is on.

Its only purpose is to exercise the marker system, the panels and the filter
UI. The values are invented and must never be read as FIRMS observations, model
predictions or threat assessments.
"""
import uuid
from datetime import datetime, timedelta, timezone

from core.database import Collections, get_db
from models.alert import Alert
from models.common import GeoPoint
from models.enums import (
    AlertStatus,
    DataOrigin,
    EVENT_TYPE_CATEGORY,
    EventStatus,
    EventType,
    EvidenceCode,
    SourceType,
    ThreatLevel,
)
from models.event import (
    ClassificationResult,
    Event,
    SupportingEvidence,
    ThermalMetrics,
    ThreatAssessment,
)
from models.facility import Facility

DEMO_TAG = "DEMO"
DEMO_MODEL_VERSION = "demo-placeholder-not-a-real-model"

_E = EvidenceCode

# state, lat, lon, event_type, source_type, threat_level, threat_score,
# confidence, peak_frp, detections, status, evidence codes
_ROWS = [
    ("Odisha", 21.4934, 84.0300, EventType.INDUSTRIAL_FIRE, SourceType.STEEL_METAL,
     ThreatLevel.CRITICAL, 92.4, 0.87, 742.0, 11, EventStatus.ACTIVE,
     [_E.HIGH_FRP, _E.BASELINE_DEVIATION, _E.RAPID_ESCALATION, _E.MULTIPLE_DETECTIONS]),
    ("Gujarat", 22.3095, 70.8022, EventType.INDUSTRIAL_FIRE,
     SourceType.OIL_REFINERY_PETROCHEMICAL, ThreatLevel.HIGH, 81.0, 0.79, 511.0, 8,
     EventStatus.ACTIVE,
     [_E.HIGH_FRP, _E.ABNORMAL_BEHAVIOUR_AT_PERSISTENT_SOURCE, _E.MULTIPLE_STRONG_INDICATORS]),
    ("Uttarakhand", 30.0668, 79.0193, EventType.FOREST_FIRE, None,
     ThreatLevel.HIGH, 76.2, 0.72, 288.0, 14, EventStatus.ACTIVE,
     [_E.ABNORMAL_SPATIAL_EXPANSION, _E.MULTIPLE_DETECTIONS]),
    ("Chhattisgarh", 21.2514, 81.6296, EventType.INDUSTRIAL_FIRE, SourceType.FOUNDRY_SMELTING,
     ThreatLevel.HIGH, 70.5, None, 402.0, 6, EventStatus.ACTIVE,
     [_E.RAPID_ESCALATION, _E.BASELINE_DEVIATION]),
    ("Madhya Pradesh", 23.2599, 77.4126, EventType.FOREST_FIRE, None,
     ThreatLevel.MODERATE, 58.9, 0.64, 174.0, 9, EventStatus.ACTIVE,
     [_E.MULTIPLE_DETECTIONS]),
    ("Punjab", 30.7333, 76.7794, EventType.AGRICULTURAL_FIRE, None,
     ThreatLevel.MODERATE, 47.3, 0.81, 96.0, 5, EventStatus.ACTIVE, [_E.MULTIPLE_DETECTIONS]),
    ("Haryana", 29.0588, 76.0856, EventType.AGRICULTURAL_FIRE, None,
     ThreatLevel.LOW, 22.8, 0.77, 41.0, 3, EventStatus.ACTIVE, []),
    ("Uttar Pradesh", 26.8467, 80.9462, EventType.UNKNOWN_AGRICULTURAL_FIRE, None,
     ThreatLevel.LOW, 18.4, None, 33.0, 2, EventStatus.ACTIVE, []),
    ("Rajasthan", 26.9124, 75.7873, EventType.PERSISTENT_HEAT_SOURCE, SourceType.CEMENT_KILN,
     ThreatLevel.LOW, 14.0, 0.91, 58.0, 22, EventStatus.ACTIVE,
     [_E.STABLE_HISTORICAL_BEHAVIOUR, _E.NIGHT_TIME_PERSISTENCE]),
    ("Assam", 27.2000, 95.3000, EventType.PERSISTENT_HEAT_SOURCE, SourceType.GAS_FLARE,
     ThreatLevel.LOW, 11.2, 0.94, 66.0, 31, EventStatus.ACTIVE,
     [_E.STABLE_HISTORICAL_BEHAVIOUR, _E.NIGHT_TIME_PERSISTENCE]),
    ("Maharashtra", 19.0760, 72.8777, EventType.PERSISTENT_HEAT_SOURCE,
     SourceType.POWER_PLANT, ThreatLevel.LOW, 9.8, 0.88, 120.0, 27, EventStatus.ACTIVE,
     [_E.STABLE_HISTORICAL_BEHAVIOUR]),
    ("West Bengal", 22.5726, 88.3639, EventType.PERSISTENT_HEAT_SOURCE,
     SourceType.BRICK_KILN, ThreatLevel.LOW, 8.1, 0.69, 44.0, 19, EventStatus.ACTIVE,
     [_E.STABLE_HISTORICAL_BEHAVIOUR]),
    ("Jharkhand", 23.6102, 85.2799, EventType.PERSISTENT_HEAT_SOURCE,
     SourceType.MINING_MINERAL_PROCESSING, ThreatLevel.LOW, 7.4, None, 38.0, 16,
     EventStatus.ACTIVE, [_E.STABLE_HISTORICAL_BEHAVIOUR]),
    ("Telangana", 17.3850, 78.4867, EventType.PERSISTENT_HEAT_SOURCE,
     SourceType.UNKNOWN_PERSISTENT_SOURCE, ThreatLevel.LOW, 6.0, None, 29.0, 12,
     EventStatus.ACTIVE, []),
    ("Karnataka", 12.9716, 77.5946, EventType.AGRICULTURAL_FIRE, None,
     ThreatLevel.LOW, 5.2, 0.58, 18.0, 2, EventStatus.ACTIVE, []),
    ("Tamil Nadu", 11.1271, 78.6569, EventType.FOREST_FIRE, None,
     ThreatLevel.MODERATE, 44.6, 0.66, 131.0, 7, EventStatus.ACTIVE, [_E.MULTIPLE_DETECTIONS]),
    # Historical / no longer supported by the live feed.
    ("Odisha", 20.9517, 85.0985, EventType.INDUSTRIAL_FIRE, SourceType.STEEL_METAL,
     ThreatLevel.HIGH, 74.0, 0.83, 480.0, 9, EventStatus.EXPIRED, [_E.HIGH_FRP]),
    ("Punjab", 31.1471, 75.3412, EventType.AGRICULTURAL_FIRE, None,
     ThreatLevel.LOW, 12.5, 0.74, 27.0, 4, EventStatus.INACTIVE, []),
]

_EVIDENCE_LABELS = {
    _E.HIGH_FRP: "Unusually high FRP",
    _E.BASELINE_DEVIATION: "Extreme deviation from baseline",
    _E.RAPID_ESCALATION: "Rapid escalation",
    _E.ABNORMAL_SPATIAL_EXPANSION: "Abnormal spatial expansion",
    _E.MULTIPLE_DETECTIONS: "Multiple detections",
    _E.MULTIPLE_STRONG_INDICATORS: "Multiple strong indicators",
    _E.ABNORMAL_BEHAVIOUR_AT_PERSISTENT_SOURCE: "Abnormal behaviour at persistent source",
    _E.STABLE_HISTORICAL_BEHAVIOUR: "Stable historical behaviour",
    _E.NIGHT_TIME_PERSISTENCE: "Night-time persistence",
}

_FACILITY_SEED = [
    ("Demo Steel Works", "Odisha", 21.4934, 84.0300, SourceType.STEEL_METAL),
    ("Demo Refinery Complex", "Gujarat", 22.3095, 70.8022, SourceType.OIL_REFINERY_PETROCHEMICAL),
    ("Demo Thermal Station", "Maharashtra", 19.0760, 72.8777, SourceType.POWER_PLANT),
    ("Demo Flare Site", "Assam", 27.2000, 95.3000, SourceType.GAS_FLARE),
    ("Demo Cement Kiln", "Rajasthan", 26.9124, 75.7873, SourceType.CEMENT_KILN),
]


def _build() -> tuple[list[Event], list[Alert], list[Facility]]:
    now = datetime.now(timezone.utc)
    events: list[Event] = []
    alerts: list[Alert] = []

    for idx, row in enumerate(_ROWS):
        (state, lat, lon, event_type, source_type, threat_level, threat_score,
         confidence, peak_frp, detections, status, evidence) = row

        age_hours = 1 + idx * 3
        last_seen = now - timedelta(hours=1 if status == EventStatus.ACTIVE else 60)
        event = Event(
            event_id=f"demo-evt-{idx + 1:03d}",
            status=status,
            data_origin=DataOrigin.DEMO,
            centroid=GeoPoint.from_lat_lon(lat, lon),
            state=state,
            first_detected=now - timedelta(hours=age_hours + 6),
            last_detected=last_seen,
            detection_count=detections,
            classification=ClassificationResult(
                event_category=EVENT_TYPE_CATEGORY[event_type],
                event_type=event_type,
                source_type=source_type,
                confidence=confidence,
                model_version_id=DEMO_MODEL_VERSION if confidence is not None else None,
                inferred_at=last_seen if confidence is not None else None,
            ),
            threat=ThreatAssessment(
                threat_level=threat_level,
                threat_score=threat_score,
                supporting_evidence=[
                    SupportingEvidence(code=c, label=_EVIDENCE_LABELS[c]) for c in evidence
                ],
                assessed_at=last_seen,
                engine_version="demo-placeholder",
            ),
            metrics=ThermalMetrics(
                peak_frp=peak_frp,
                latest_frp=round(peak_frp * 0.72, 1),
                mean_frp=round(peak_frp * 0.55, 1),
                spatial_extent_km2=round(0.4 * detections, 2),
            ),
            created_at=now - timedelta(hours=age_hours + 6),
            updated_at=last_seen,
        )
        events.append(event)

        if threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL) and status == EventStatus.ACTIVE:
            alerts.append(
                Alert(
                    alert_id=f"demo-alr-{idx + 1:03d}",
                    event_id=event.event_id,
                    status=AlertStatus.OPEN,
                    data_origin=DataOrigin.DEMO,
                    event_type=event_type,
                    source_type=source_type,
                    state=state,
                    threat_level=threat_level,
                    threat_score=threat_score,
                    primary_reason=_EVIDENCE_LABELS[evidence[0]] if evidence else None,
                    supporting_evidence=event.threat.supporting_evidence,
                    threshold_profile="demo-placeholder",
                    engine_version="demo-placeholder",
                    raised_at=last_seen,
                )
            )

    facilities = [
        Facility(
            facility_id=f"demo-fac-{i + 1:03d}",
            name=name,
            location=GeoPoint.from_lat_lon(lat, lon),
            state=state,
            source_type=source_type,
            dataset_source="DEVELOPMENT_DEMO",
            dataset_version="demo",
            verified=False,
            data_origin=DataOrigin.DEMO,
        )
        for i, (name, state, lat, lon, source_type) in enumerate(_FACILITY_SEED)
    ]
    return events, alerts, facilities


async def seed() -> dict:
    db = get_db()
    await clear()
    events, alerts, facilities = _build()
    await db[Collections.EVENTS].insert_many([e.to_mongo() for e in events])
    if alerts:
        await db[Collections.ALERTS].insert_many([a.to_mongo() for a in alerts])
    await db[Collections.FACILITIES].insert_many([f.to_mongo() for f in facilities])
    return {
        "seeded": True,
        "events": len(events),
        "alerts": len(alerts),
        "facilities": len(facilities),
    }


async def clear() -> dict:
    db = get_db()
    origin = {"data_origin": DataOrigin.DEMO.value}
    removed = {}
    for name in (
        Collections.EVENTS,
        Collections.ALERTS,
        Collections.FACILITIES,
        Collections.THERMAL_DETECTIONS,
    ):
        result = await db[name].delete_many(origin)
        removed[name] = result.deleted_count
    return {"cleared": True, "removed": removed}


async def status() -> dict:
    db = get_db()
    origin = {"data_origin": DataOrigin.DEMO.value}
    return {
        "events": await db[Collections.EVENTS].count_documents(origin),
        "alerts": await db[Collections.ALERTS].count_documents(origin),
        "facilities": await db[Collections.FACILITIES].count_documents(origin),
    }
