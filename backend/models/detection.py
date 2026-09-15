"""Raw FIRMS observations.

Rule (Phase 1, section 22): raw observations are NEVER overwritten with ML or
frontend interpretation. Only ``event_id`` is written back, to record which
ThermoIntel event a detection was grouped into.
"""
from datetime import datetime
from typing import Optional

from pydantic import Field

from models.common import BaseDocument, GeoPoint, utc_now
from models.enums import DayNight, Satellite


class ThermalDetection(BaseDocument):
    # Stable de-duplication key derived from satellite + acquisition + position.
    observation_id: str

    location: GeoPoint
    acquired_at: datetime

    satellite: Satellite = Satellite.OTHER
    instrument: Optional[str] = None
    day_night: Optional[DayNight] = None

    # FIRMS measurements, kept verbatim.
    frp: Optional[float] = None
    brightness_ti4: Optional[float] = None
    brightness_ti5: Optional[float] = None
    firms_confidence: Optional[str] = None
    scan: Optional[float] = None
    track: Optional[float] = None

    # Geographic assignment (India administrative boundaries).
    state: Optional[str] = None

    # Event formation back-reference. None until event formation has run.
    event_id: Optional[str] = None

    ingestion_run_id: Optional[str] = None
    data_origin: str = "production"
    created_at: datetime = Field(default_factory=utc_now)
