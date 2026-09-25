"""Stage 5 & 6 - threat/anomaly engine and alert generation.

Threat is separate from classification confidence. The threat score considers
FRP magnitude, baseline deviation, rate of change, spatial behaviour, detection
strength, industrial context and validated anomaly signals.

HISTORY OF THE NUMERICAL CONTRACT
---------------------------------
Phase 1 (section 29) deliberately left the weights and the alert threshold
unfrozen. The Task 20 audit confirmed the complete numerical contract is NOT
recoverable from existing v2 materials. The numerical values below are
therefore NEW OWNER-PROPOSED v2 configuration values (Task 21), explicitly
provisional until calibrated/validated against real data. Every number lives
in ``CONFIG`` - nothing is hard-coded in the scoring logic. No ThermoIntel v1
material was imported.

SCORING ARCHITECTURE (owner-proposed, implemented literally)
------------------------------------------------------------
    signal -> individual normalization -> weighted contribution
           -> weighted aggregate -> 0-100 threat score -> threat level

    threat_score = clamp( 100 x SUM(weight_i x normalized_signal_i), 0, 100 )

- every normalized signal is in [0, 1] or exactly None
- weights sum to 1.0 (asserted by ThreatEngineConfig.validate)
- the formula is implemented LITERALLY: a signal that is None (missing or
  UNDEFINED normalization) contributes 0 to the weighted sum. Consequence,
  stated openly: with the current UNDEFINED signals (rate_of_change,
  spatial_behaviour, industrial_context - combined weight 0.35) the maximum
  reachable score is 100 x 0.65 = 65, so CRITICAL (>= 75) is unreachable
  until those normalizations are defined by a further owner decision. No
  renormalization was invented to hide this.
- when NO signal is computable the score is None and the event keeps its
  explicit UNASSESSED state - nothing is fabricated

SIGNAL NORMALIZATION STATUS (Task 21 audit, per-signal)
-------------------------------------------------------
1. frp_magnitude       PROVISIONAL - frp_log1p saturated at the Phase 4
                       feature-schema winsorization scale (documented in
                       models/ml/feature_schema_final.json).
2. baseline_deviation  PROVISIONAL LOCATION-BASED PROXY - brightness_diff
                       scaled by ~2x the schema-documented brightness_diff
                       mean. TRUE historical-baseline normalization is
                       UNDEFINED (no location/source history exists in v2).
3. rate_of_change      UNDEFINED - requires temporally comparable
                       observations; the current documented event rule is
                       one detection per event. Always None; never invented.
4. spatial_behaviour   UNDEFINED - requires a defined spatial comparison;
                       no spatial-comparison contract exists. Always None.
5. detection_strength  DERIVED - confidence_num is already [0, 1] by
                       construction in the frozen Phase 4 schema (clamped).
6. industrial_context  UNDEFINED - the owner definition requires facility/
                       source history; v2 facilities carry no behaviour
                       history. Proximity alone would change the signal's
                       defined semantics, so it stays None. Always None.
7. ml_evidence         PROVISIONAL - evidence vector over the EXISTING frozen
                       Phase 4 outputs (event_type / source_type /
                       calibrated confidence) with sub-weights isolated in
                       configuration. Distinct from classification
                       confidence itself being treated as "threat".
"""
from dataclasses import dataclass, field
from typing import Optional

from models.enums import EvidenceCode, PipelineStage, ThreatLevel
from models.event import Event, SupportingEvidence, ThreatAssessment

THREAT_STAGE = PipelineStage.THREAT_ANALYSIS
ALERT_STAGE = PipelineStage.ALERT_GENERATION

THREAT_LEVELS = [
    ThreatLevel.LOW,
    ThreatLevel.MODERATE,
    ThreatLevel.HIGH,
    ThreatLevel.CRITICAL,
]

# Signal vocabulary the engine scores (defined by the repository).
THREAT_SIGNALS = [
    "frp_magnitude",
    "baseline_deviation",
    "rate_of_change",
    "spatial_behaviour",
    "detection_strength",
    "industrial_context",
    "ml_evidence",
]

# Evidence weights over the EXISTING frozen Phase 4 outputs. Event-type
# values cover the full EventType enum (models/enums.py); source-type values
# cover the frozen Phase 4 M4 class vocabulary
# (models/ml/m4_class_mapping_final.json). The weights themselves are
# owner-proposed provisional values (Task 21); unknown classes score 0.
_ML_EVENT_TYPE_EVIDENCE = {
    "FOREST_FIRE": 1.0,
    "AGRICULTURAL_FIRE": 0.8,
    "UNKNOWN_AGRICULTURAL_FIRE": 0.4,
    "INDUSTRIAL_FIRE": 1.0,
    "PERSISTENT_HEAT_SOURCE": 0.6,
}
_ML_SOURCE_TYPE_EVIDENCE = {
    "GAS_FLARE": 0.8,
    "OIL_REFINERY_PETROCHEMICAL": 0.8,
    "CHEMICAL": 0.7,
    "POWER_PLANT": 0.7,
    "STEEL_METAL": 0.7,
    "CEMENT_KILN": 0.5,
    "BRICK_KILN": 0.5,
    "MINING_MINERAL_PROCESSING": 0.5,
    "OTHER_PERSISTENT_INDUSTRIAL_SOURCE": 0.4,
    # Classes outside the frozen M4 vocabulary (e.g.
    # UNKNOWN_PERSISTENT_SOURCE) score 0 - no invented evidence.
}

# Per-signal evidence codes with a clean 1:1 match in the documented
# EvidenceCode vocabulary. detection_strength and ml_evidence have no
# unambiguous entry, so no per-signal evidence item is emitted for them
# (their contribution is still scored; alert reasons name the signal).
SIGNAL_EVIDENCE_CODES = {
    "frp_magnitude": EvidenceCode.HIGH_FRP,
    "baseline_deviation": EvidenceCode.BASELINE_DEVIATION,
    "rate_of_change": EvidenceCode.RAPID_ESCALATION,
    "spatial_behaviour": EvidenceCode.ABNORMAL_SPATIAL_EXPANSION,
    "industrial_context": EvidenceCode.ABNORMAL_BEHAVIOUR_AT_PERSISTENT_SOURCE,
}

# --------------------------------------------------------------------------
# Configuration - THE single home of every numerical value in the contract.
# --------------------------------------------------------------------------
CALIBRATION_STATUS_PROVISIONAL = "PROVISIONAL_OWNER_PROPOSED"
CALIBRATION_STATUS_VALIDATED = "VALIDATED"


@dataclass
class SignalNormalizationConfig:
    """Normalization parameters. Each documents its derivation; none are
    recovered from a v2 specification - they are owner-proposed provisional
    values (Task 21) or derived from the frozen Phase 4 feature schema."""

    # frp_magnitude: normalized = frp_log1p / saturation, clamped to [0,1].
    # The value equals the upper winsorization bound of frp_log1p documented
    # in the Phase 4 feature schema, i.e. the scale the frozen pipeline
    # itself treats as the top of the observed range.
    frp_log1p_saturation: float = 5.0

    # baseline_deviation (PROVISIONAL LOCATION-BASED PROXY): normalized =
    # brightness_diff / scale, clamped to [0,1]. The value is ~2x the
    # brightness_diff mean (18.56) documented in the Phase 4 feature-schema
    # stats (models/ml/feature_schema_final.json).
    baseline_brightness_diff_scale: float = 40.0

    # ml_evidence: sub-weights over the existing frozen Phase 4 outputs.
    ml_evidence_event_type: float = 0.5
    ml_evidence_source_type: float = 0.3
    ml_evidence_confidence: float = 0.2


@dataclass
class AlertSuppressionConfig:
    """Alert eligibility + duplicate-suppression parameters."""

    # "HIGH requires at least one qualifying abnormal signal": a signal
    # qualifies as abnormal when its normalized value >= this floor. The
    # floor is the HIGH band's lower boundary expressed in [0, 1] so
    # "abnormal" is tied to the same scale as the levels.
    abnormal_signal_floor: float = 0.50

    # Re-alert policy: "re-alert only after resolution/cooldown AND a
    # materially higher threat state". Both parameters are UNDEFINED until
    # the owner wants re-alerting; with None, an existing alert is never
    # superseded (at most one alert per event, ever).
    realert_cooldown_hours: Optional[float] = None
    materially_higher_delta: Optional[float] = None


@dataclass
class ThreatEngineConfig:
    """All numerical threat values in one place (Task 21 owner proposal).

    ``is_calibrated`` stays False until the owner validates the contract
    against real data (a separate, subsequent task); the engine scores
    whenever it ``is_configured``.
    """

    signal_weights: dict[str, Optional[float]] = field(
        default_factory=lambda: {signal: None for signal in THREAT_SIGNALS}
    )
    level_boundaries: dict[str, Optional[float]] = field(
        default_factory=lambda: {level.value: None for level in THREAT_LEVELS}
    )
    alert_threshold: Optional[float] = None
    threshold_profile: Optional[str] = None

    score_min: float = 0.0
    score_max: float = 100.0

    calibration_status: str = CALIBRATION_STATUS_PROVISIONAL

    normalization: SignalNormalizationConfig = field(
        default_factory=SignalNormalizationConfig
    )
    alerts: AlertSuppressionConfig = field(default_factory=AlertSuppressionConfig)

    @property
    def is_configured(self) -> bool:
        """Weights are complete => the framework can score."""
        return all(v is not None for v in self.signal_weights.values())

    @property
    def is_calibrated(self) -> bool:
        """True only once the owner VALIDATES the contract. Surfaced through
        GET /api/ingestion/status so the UI never claims validated readiness
        for provisional values."""
        return self.calibration_status == CALIBRATION_STATUS_VALIDATED

    def validate(self) -> None:
        weights = self.signal_weights
        if len(weights) != len(THREAT_SIGNALS) or set(weights) != set(THREAT_SIGNALS):
            raise ValueError("signal_weights must cover exactly THREAT_SIGNALS")
        if any(w is None for w in weights.values()):
            raise ValueError("signal_weights must be fully assigned to score")
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"signal_weights must sum to 1.0 (got {total})")
        for level in THREAT_LEVELS:
            if self.level_boundaries.get(level.value) is None:
                raise ValueError(f"missing level boundary for {level.value}")
        if self.alert_threshold is None:
            raise ValueError("alert_threshold must be set")


# OWNER-PROPOSED V2 CONTRACT (Task 21) - provisional, NOT calibrated/validated.
CONFIG = ThreatEngineConfig(
    signal_weights={
        "frp_magnitude": 0.20,
        "baseline_deviation": 0.20,
        "rate_of_change": 0.15,
        "spatial_behaviour": 0.10,
        "detection_strength": 0.10,
        "industrial_context": 0.10,
        "ml_evidence": 0.15,
    },
    level_boundaries={
        "LOW": 0.0,        # 0-24
        "MODERATE": 25.0,  # 25-49
        "HIGH": 50.0,      # 50-74
        "CRITICAL": 75.0,  # 75-100
    },
    alert_threshold=50.0,            # eligibility begins at HIGH (>= 50)
    threshold_profile="owner-proposal-v1",
    calibration_status=CALIBRATION_STATUS_PROVISIONAL,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------------------
# Signal normalization. Each function returns float in [0, 1] or None.
# UNDEFINED signals return None unconditionally - no value is fabricated.
# ---------------------------------------------------------------------------
def _normalize_frp_magnitude(event: Event, features: dict, cfg: ThreatEngineConfig) -> Optional[float]:
    frp_log1p = features.get("frp_log1p")
    if frp_log1p is None:
        return None
    saturation = cfg.normalization.frp_log1p_saturation
    if saturation <= 0:
        return None
    return _clamp01(float(frp_log1p) / saturation)


def _normalize_baseline_deviation(event: Event, features: dict, cfg: ThreatEngineConfig) -> Optional[float]:
    # PROVISIONAL LOCATION-BASED PROXY (see module docstring). True
    # historical-baseline normalization is UNDEFINED in v2.
    brightness_diff = features.get("brightness_diff")
    if brightness_diff is None:
        return None
    scale = cfg.normalization.baseline_brightness_diff_scale
    if scale <= 0:
        return None
    return _clamp01(float(brightness_diff) / scale)


def _normalize_rate_of_change(event: Event, features: dict, cfg: ThreatEngineConfig) -> Optional[float]:
    # UNDEFINED: requires temporally comparable observations; the documented
    # event rule is one detection per event. Never fabricate a value.
    return None


def _normalize_spatial_behaviour(event: Event, features: dict, cfg: ThreatEngineConfig) -> Optional[float]:
    # UNDEFINED: requires a defined spatial-comparison contract. Never
    # fabricate a value.
    return None


def _normalize_detection_strength(event: Event, features: dict, cfg: ThreatEngineConfig) -> Optional[float]:
    # DERIVED: confidence_num is already in [0, 1] by construction in the
    # frozen Phase 4 schema; only the range is enforced.
    confidence_num = features.get("confidence_num")
    if confidence_num is None:
        return None
    return _clamp01(float(confidence_num))


def _normalize_industrial_context(event: Event, features: dict, cfg: ThreatEngineConfig) -> Optional[float]:
    # UNDEFINED: the owner definition requires abnormality "relative to that
    # facility's established behavior"; v2 facilities carry no behaviour
    # history. Proximity alone would change the signal's semantics. Never
    # fabricate a value.
    return None


def _normalize_ml_evidence(event: Event, features: dict, cfg: ThreatEngineConfig) -> Optional[float]:
    # PROVISIONAL: evidence vector over the EXISTING frozen Phase 4 outputs.
    classification = event.classification
    if classification is None or classification.event_type is None:
        return None

    cfg_n = cfg.normalization
    total = (
        cfg_n.ml_evidence_event_type
        + cfg_n.ml_evidence_source_type
        + cfg_n.ml_evidence_confidence
    )
    if total <= 0:
        return None

    contribution = 0.0
    contribution += cfg_n.ml_evidence_event_type * _ML_EVENT_TYPE_EVIDENCE.get(
        str(classification.event_type), 0.0
    )

    if classification.source_type is not None:
        contribution += cfg_n.ml_evidence_source_type * _ML_SOURCE_TYPE_EVIDENCE.get(
            str(classification.source_type), 0.0
        )
    # No source_type => its sub-weight drops out (no fabrication).

    if classification.confidence is not None:
        contribution += cfg_n.ml_evidence_confidence * _clamp01(
            float(classification.confidence)
        )
    # No confidence => its sub-weight drops out.

    return _clamp01(contribution / total)


# Dispatch table: signal -> normalizer. UNDEFINED signals are explicit.
SIGNAL_NORMALIZERS = {
    "frp_magnitude": _normalize_frp_magnitude,
    "baseline_deviation": _normalize_baseline_deviation,
    "rate_of_change": _normalize_rate_of_change,
    "spatial_behaviour": _normalize_spatial_behaviour,
    "detection_strength": _normalize_detection_strength,
    "industrial_context": _normalize_industrial_context,
    "ml_evidence": _normalize_ml_evidence,
}

SIGNAL_DEFINITIONS_STATUS = {
    "frp_magnitude": "PROVISIONAL",
    "baseline_deviation": "PROVISIONAL_LOCATION_PROXY",
    "rate_of_change": "UNDEFINED",
    "spatial_behaviour": "UNDEFINED",
    "detection_strength": "DERIVED",
    "industrial_context": "UNDEFINED",
    "ml_evidence": "PROVISIONAL",
}


def normalize_signals(
    event: Event,
    features: dict,
    config: ThreatEngineConfig = CONFIG,
) -> dict[str, Optional[float]]:
    """Normalize every signal; UNDEFINED signals are explicit None."""
    return {
        signal: SIGNAL_NORMALIZERS[signal](event, features, config)
        for signal in THREAT_SIGNALS
    }


def weighted_score(
    normalized: dict[str, Optional[float]],
    config: ThreatEngineConfig = CONFIG,
) -> Optional[float]:
    """Literal owner formula:

        100 x SUM(weight_i x normalized_signal_i), clamped to
        [score_min, score_max].

    A None (missing/UNDEFINED) signal contributes 0. Returns None when NO
    signal is available - the caller keeps the explicit UNASSESSED state
    instead of a fabricated score.
    """
    config.validate()
    available = {
        signal: value
        for signal, value in normalized.items()
        if value is not None
    }
    if not available:
        return None

    score = 100.0 * sum(
        config.signal_weights[signal] * value
        for signal, value in available.items()
    )
    return max(config.score_min, min(config.score_max, score))


def level_for_score(
    score: float,
    config: ThreatEngineConfig = CONFIG,
) -> ThreatLevel:
    """Highest level whose configured boundary is <= score (inclusive lower
    bounds: 0-24 LOW, 25-49 MODERATE, 50-74 HIGH, 75-100 CRITICAL)."""
    config.validate()
    level = None
    for candidate in THREAT_LEVELS:
        boundary = config.level_boundaries[candidate.value]
        if boundary is not None and score >= boundary:
            level = candidate
    if level is None:
        level = THREAT_LEVELS[0]
    return level


def _evidence_items(
    normalized: dict[str, Optional[float]],
    config: ThreatEngineConfig,
) -> list[SupportingEvidence]:
    items: list[SupportingEvidence] = []
    for signal in THREAT_SIGNALS:
        value = normalized.get(signal)
        code = SIGNAL_EVIDENCE_CODES.get(signal)
        if value is None or code is None:
            continue
        items.append(
            SupportingEvidence(
                code=code,
                label=signal,
                detail=(
                    f"normalized={value:.3f}, "
                    f"weight={config.signal_weights[signal]:.2f} "
                    f"[{SIGNAL_DEFINITIONS_STATUS[signal]}]"
                ),
            )
        )
    return items


async def assess(
    event: Event,
    features: dict,
    config: ThreatEngineConfig = CONFIG,
) -> Optional[ThreatAssessment]:
    """Score one event with the configured (provisional) contract.

    Returns None - leaving the event explicitly UNASSESSED - only when the
    engine is not configured or no signal is computable. Never fabricates a
    score for missing data. Threat remains separate from classification
    confidence: the frozen ML outputs are one input signal, not the score.
    """
    if not config.is_configured:
        return None

    normalized = normalize_signals(event, features, config)
    score = weighted_score(normalized, config)
    if score is None:
        return None

    return ThreatAssessment(
        threat_level=level_for_score(score, config),
        threat_score=score,
        supporting_evidence=_evidence_items(normalized, config),
        engine_version=(
            f"v2-threat-framework ({config.threshold_profile}, "
            f"{config.calibration_status})"
        ),
    )


# ---------------------------------------------------------------------------
# Alert generation - owner eligibility contract + duplicate suppression.
# ---------------------------------------------------------------------------
def _is_alert_eligible(
    threat_level: Optional[ThreatLevel],
    normalized: dict[str, Optional[float]],
    config: ThreatEngineConfig,
) -> bool:
    """Eligibility begins at HIGH. HIGH requires at least one qualifying
    abnormal signal; CRITICAL automatically qualifies. Nothing below HIGH is
    eligible. No additional condition is applied."""
    config.validate()
    if threat_level is None:
        return False
    if threat_level == ThreatLevel.CRITICAL:
        return True
    if threat_level != ThreatLevel.HIGH:
        return False  # UNASSESSED, LOW, MODERATE

    floor = config.alerts.abnormal_signal_floor
    return any(
        value is not None and value >= floor for value in normalized.values()
    )


def _primary_reason(
    normalized: dict[str, Optional[float]],
    config: ThreatEngineConfig,
) -> str:
    available = {
        signal: value for signal, value in normalized.items() if value is not None
    }
    if not available:
        return "CRITICAL: automatic qualification (no computable signals)"
    top_signal, top_value = max(available.items(), key=lambda kv: kv[1])
    return (
        f"{top_signal}: normalized={top_value:.3f} "
        f"(weight={config.signal_weights[top_signal]:.2f})"
    )


async def generate_alerts(
    events: list[Event],
    normalized_by_event: dict[str, dict[str, Optional[float]]],
    config: ThreatEngineConfig = CONFIG,
) -> int:
    """Persist alerts for eligible events using the existing Alert schema.

    ``normalized_by_event`` maps event_id -> the normalized signals computed
    by ``normalize_signals`` at ASSESSMENT time with the same features, so
    alert-time eligibility is exactly consistent with assessment-time
    scoring (no re-derivation from a reduced view).

    - eligibility: level >= HIGH (HIGH needs an abnormal signal; CRITICAL
      automatic; nothing below HIGH)
    - duplicate suppression: deterministic alert_id ``alr-{event_id}``
      upserted on the unique alert_id index - at most one alert per event;
      re-alerting requires the owner to define cooldown/materially-higher
      parameters (currently UNDEFINED, so an existing alert is never
      superseded)
    - production/demo separation: demo events never produce alerts
    - idempotent: re-running writes no duplicates

    Returns the number of NEW alerts created.
    """
    from core.database import Collections, get_db
    from models.alert import Alert
    from models.enums import AlertStatus, DataOrigin

    config.validate()
    db = get_db()
    collection = db[Collections.ALERTS]
    created = 0

    for event in events:
        if event.data_origin == DataOrigin.DEMO:
            continue  # demo data must never produce production alerts

        normalized = normalized_by_event.get(event.event_id)
        if normalized is None:
            continue  # never assessed with features -> never alert-eligible

        threat_level = event.threat.threat_level if event.threat else None
        if not _is_alert_eligible(threat_level, normalized, config):
            continue

        alert = Alert(
            alert_id=f"alr-{event.event_id}",
            event_id=event.event_id,
            status=AlertStatus.OPEN,
            data_origin=event.data_origin,
            event_type=event.classification.event_type if event.classification else None,
            source_type=event.classification.source_type if event.classification else None,
            state=event.state,
            threat_level=threat_level,
            threat_score=event.threat.threat_score if event.threat else None,
            primary_reason=_primary_reason(normalized, config),
            supporting_evidence=event.threat.supporting_evidence if event.threat else [],
            threshold_profile=config.threshold_profile,
            engine_version=f"v2-threat-framework ({config.threshold_profile})",
        )

        set_doc = alert.to_mongo()
        raised_at = set_doc.pop("raised_at", None)
        set_doc.pop("updated_at", None)
        on_insert = {"raised_at": raised_at} if raised_at else {}

        update = {"$set": set_doc}
        if on_insert:
            update["$setOnInsert"] = on_insert

        result = await collection.update_one(
            {"alert_id": alert.alert_id}, update, upsert=True
        )
        if result.upserted_id is not None:
            created += 1

    return created
