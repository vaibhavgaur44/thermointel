"""Raw FIRMS observations."""
from datetime import datetime
from typing import Optional

from pydantic import Field

from models.common import BaseDocument, GeoPoint, utc_now
from models.enums import DayNight, Satellite


class ThermalDetection(BaseDocument):
    observation_id: str

    location: GeoPoint
    acquired_at: datetime

    satellite: Satellite = Satellite.OTHER
    satellite_std: Optional[str] = None
    instrument: Optional[str] = None
    version: Optional[str] = None
    day_night: Optional[DayNight] = None

    # FIRMS measurements, kept verbatim.
    frp: Optional[float] = None
    brightness_ti4: Optional[float] = None
    brightness_ti5: Optional[float] = None
    firms_confidence: Optional[str] = None
    scan: Optional[float] = None
    track: Optional[float] = None

    # Geographic/context enrichment used by the frozen ML pipeline.
    state: Optional[str] = None
    state_lgd: Optional[str] = None
    lulc_2021_code: Optional[str] = None
    lulc_2021_class: Optional[str] = None

    # Event formation back-reference.
    event_id: Optional[str] = None

    ingestion_run_id: Optional[str] = None
    data_origin: str = "production"
    created_at: datetime = Field(default_factory=utc_now)