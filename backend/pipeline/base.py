"""ThermoIntel processing pipeline - Phase 2 interface definitions.

    FIRMS -> ingestion -> thermal_detections -> event formation ->
    feature engineering -> ML classification -> threat/anomaly engine ->
    alert generation -> MongoDB -> FastAPI -> React/Cesium

Every stage below is an explicit, documented contract with NO implementation.
Phases 3-5 fill these in. Raising ``PipelineStageNotImplemented`` is the only
honest behaviour in Phase 2: it guarantees no fabricated data can ever reach
the database or the UI.
"""
from models.enums import PipelineStage


class PipelineStageNotImplemented(NotImplementedError):
    def __init__(self, stage: PipelineStage, phase: str):
        self.stage = stage
        self.phase = phase
        super().__init__(
            f"{stage.value} is not implemented in Phase 2. "
            f"It is delivered in {phase}."
        )
