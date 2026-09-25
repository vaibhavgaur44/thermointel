"""Canonical ThermoIntel v2 taxonomy.

These enumerations are frozen by the Phase 1 Master Specification.
Nothing here encodes classification logic - only vocabulary.
"""
from enum import Enum


class EventCategory(str, Enum):
    AGRICULTURAL = "AGRICULTURAL"
    INDUSTRIAL = "INDUSTRIAL"


class EventType(str, Enum):
    # AGRICULTURAL branch
    FOREST_FIRE = "FOREST_FIRE"
    AGRICULTURAL_FIRE = "AGRICULTURAL_FIRE"
    UNKNOWN_AGRICULTURAL_FIRE = "UNKNOWN_AGRICULTURAL_FIRE"
    # INDUSTRIAL branch
    INDUSTRIAL_FIRE = "INDUSTRIAL_FIRE"
    PERSISTENT_HEAT_SOURCE = "PERSISTENT_HEAT_SOURCE"


EVENT_TYPE_CATEGORY = {
    EventType.FOREST_FIRE: EventCategory.AGRICULTURAL,
    EventType.AGRICULTURAL_FIRE: EventCategory.AGRICULTURAL,
    EventType.UNKNOWN_AGRICULTURAL_FIRE: EventCategory.AGRICULTURAL,
    EventType.INDUSTRIAL_FIRE: EventCategory.INDUSTRIAL,
    EventType.PERSISTENT_HEAT_SOURCE: EventCategory.INDUSTRIAL,
}


class SourceType(str, Enum):
    """Industrial / persistent source taxonomy. Describes the FACILITY or
    SOURCE, never the event type."""

    GAS_FLARE = "GAS_FLARE"
    POWER_PLANT = "POWER_PLANT"
    OIL_REFINERY_PETROCHEMICAL = "OIL_REFINERY_PETROCHEMICAL"
    STEEL_METAL = "STEEL_METAL"
    CEMENT_KILN = "CEMENT_KILN"
    BRICK_KILN = "BRICK_KILN"
    CHEMICAL = "CHEMICAL"
    FOUNDRY_SMELTING = "FOUNDRY_SMELTING"
    INDUSTRIAL_FURNACE_BOILER = "INDUSTRIAL_FURNACE_BOILER"
    WASTE_INCINERATION = "WASTE_INCINERATION"
    MINING_MINERAL_PROCESSING = "MINING_MINERAL_PROCESSING"
    OTHER_PERSISTENT_INDUSTRIAL_SOURCE = "OTHER_PERSISTENT_INDUSTRIAL_SOURCE"
    UNKNOWN_PERSISTENT_SOURCE = "UNKNOWN_PERSISTENT_SOURCE"


class ThreatLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventStatus(str, Enum):
    """Live vs historical lifecycle. Historical records are never deleted."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"


class AlertStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLOSED = "CLOSED"


class DataOrigin(str, Enum):
    """Hard separation between production intelligence and development data."""

    PRODUCTION = "production"
    DEMO = "demo"


class TimeRange(str, Enum):
    H1 = "1h"
    H6 = "6h"
    H24 = "24h"
    W1 = "1w"


TIME_RANGE_SECONDS = {
    TimeRange.H1: 3600,
    TimeRange.H6: 6 * 3600,
    TimeRange.H24: 24 * 3600,
    TimeRange.W1: 7 * 24 * 3600,
}


class RegionKind(str, Enum):
    STATE = "STATE"
    UNION_TERRITORY = "UNION_TERRITORY"


class Satellite(str, Enum):
    VIIRS_NOAA20 = "VIIRS_NOAA20"
    VIIRS_NOAA21 = "VIIRS_NOAA21"
    VIIRS_SNPP = "VIIRS_SNPP"
    MODIS_TERRA = "MODIS_TERRA"
    MODIS_AQUA = "MODIS_AQUA"
    LANDSAT = "LANDSAT"
    OTHER = "OTHER"


class DayNight(str, Enum):
    DAY = "D"
    NIGHT = "N"


class IngestionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    # Completed, but some FIRMS sources failed and/or returned no data.
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class PipelineStage(str, Enum):
    FIRMS_INGESTION = "FIRMS_INGESTION"
    EVENT_FORMATION = "EVENT_FORMATION"
    FEATURE_ENGINEERING = "FEATURE_ENGINEERING"
    ML_INFERENCE = "ML_INFERENCE"
    THREAT_ANALYSIS = "THREAT_ANALYSIS"
    ALERT_GENERATION = "ALERT_GENERATION"


class ModelRole(str, Enum):
    """Hierarchical model roles defined in Phase 1 section 6."""

    M1_AGRICULTURAL_VS_INDUSTRIAL = "M1_AGRICULTURAL_VS_INDUSTRIAL"
    M2A_AGRICULTURAL_SUBTYPE = "M2A_AGRICULTURAL_SUBTYPE"
    M2B_INDUSTRIAL_EVENT_TYPE = "M2B_INDUSTRIAL_EVENT_TYPE"
    M3_PERSISTENT_SOURCE_SUBTYPE = "M3_PERSISTENT_SOURCE_SUBTYPE"


class EvidenceCode(str, Enum):
    """Vocabulary for 'why flagged'. Detection of these signals belongs to the
    Phase 4 threat/anomaly engine - Phase 2 only defines the vocabulary."""

    HIGH_FRP = "HIGH_FRP"
    BASELINE_DEVIATION = "BASELINE_DEVIATION"
    RAPID_ESCALATION = "RAPID_ESCALATION"
    ABNORMAL_SPATIAL_EXPANSION = "ABNORMAL_SPATIAL_EXPANSION"
    MULTIPLE_DETECTIONS = "MULTIPLE_DETECTIONS"
    MULTIPLE_STRONG_INDICATORS = "MULTIPLE_STRONG_INDICATORS"
    ABNORMAL_BEHAVIOUR_AT_PERSISTENT_SOURCE = "ABNORMAL_BEHAVIOUR_AT_PERSISTENT_SOURCE"
    STABLE_HISTORICAL_BEHAVIOUR = "STABLE_HISTORICAL_BEHAVIOUR"
    NIGHT_TIME_PERSISTENCE = "NIGHT_TIME_PERSISTENCE"
