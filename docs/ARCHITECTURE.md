# ThermoIntel v2 — Architecture Notes (Phase 2)

## Pipeline contract

```
NASA FIRMS
   │  pipeline/firms_ingestion.py        (Phase 3 / 5)
   ▼
thermal_detections        raw, verbatim, never overwritten by interpretation
   │  pipeline/event_formation.py        (Phase 5, unfrozen thresholds)
   ▼
events                    grouped ThermoIntel event objects
   │  pipeline/feature_engineering.py    (Phase 4, feature GROUPS only)
   ▼
feature vectors
   │  pipeline/ml_inference.py           (Phase 4 / 5, M1 → M2A/M2B → M3)
   ▼
ClassificationResult      event_category / event_type / source_type / confidence
   │  pipeline/threat_engine.py          (Phase 4 / 5, unfrozen weights)
   ▼
ThreatAssessment + alerts
   │  MongoDB
   ▼
FastAPI  →  React / CesiumJS
```

FastAPI is the only orchestrator. React renders and interacts; it never
computes classification, threat or anomaly values.

## Why every interpretation field is Optional

`Event.classification`, `Event.threat` and `Event.metrics` are nested models
whose fields default to `None`. Phase 2 has no model and no threat engine, so
the honest representation of "we do not know" is absence. The UI renders an
explicit `Unavailable` state for `model_confidence` and `UNASSESSED` for
threat level, which is what the specification demands instead of
`System Confidence: 100%`.

## Facility type vs event type

`facilities.source_type` describes a physical installation.
`events.classification.event_type` describes thermal behaviour. A steel plant
can present as `PERSISTENT_HEAT_SOURCE` on one day and `INDUSTRIAL_FIRE` on
another. Nothing in this codebase maps one onto the other; `facility_reference`
is a link for future feature engineering only.

## Deliberately unfrozen configuration

| Object                                   | Fields left `None`                                      |
| ---------------------------------------- | ------------------------------------------------------- |
| `event_formation.EventFormationConfig`   | grouping radius, time window, min detections, grace period |
| `threat_engine.ThreatEngineConfig`       | signal weights, level boundaries, alert threshold        |
| `Settings.ACTIVE_MODEL_VERSION`          | active model artifact                                    |

Each config exposes `is_calibrated`, surfaced through
`GET /api/ingestion/status` and the Pipeline readiness popover in the UI.

## Collections and indexes

| Collection           | Key indexes                                                     |
| -------------------- | --------------------------------------------------------------- |
| `thermal_detections` | unique `observation_id`, 2dsphere `location`, `acquired_at`, `event_id` |
| `events`             | unique `event_id`, 2dsphere `centroid`, `status`+`threat.threat_score`, `state`+`status`+`threat.threat_score`, `event_type`, `source_type`, `last_detected`, `data_origin` |
| `facilities`         | unique `facility_id`, 2dsphere `location`, `state`, `source_type` |
| `ground_truth`       | unique `label_id`, `split`, 2dsphere `location`                  |
| `alerts`             | unique `alert_id`, `event_id`, `raised_at`, `status`+`threat_score` |
| `ingestion_runs`     | unique `run_id`, `started_at`                                    |
| `model_versions`     | unique `model_version_id`, `created_at`                          |

Indexes are created idempotently on backend startup (`core.database.ensure_indexes`).

## Priority ranking

`GET /api/events/priority` sorts by `threat.threat_score` descending, then
`last_detected` descending. In BSON ordering `null` sorts below numbers, so
events without a threat assessment always fall to the bottom rather than
displacing assessed events. It is never a "most recent" list.

## Map layers

1. Imagery — a basemap stack selected in the UI:
   * **Dark** — Esri World Street Map, colour-graded down (roads, places and
     labels appear as the camera descends).
   * **Satellite** — Cesium Ion world imagery when `REACT_APP_CESIUM_ION_TOKEN`
     is set, otherwise Esri World Imagery, with a dark reference label overlay.
   * **Streets** — Esri World Street Map, ungraded.
2. `india_states.geojson` — state/UT polygons. Very low fill alpha keeps the
   imagery readable; the polygons are also the pick target for region selection.
3. Event markers — a `CustomDataSource` of billboards:
   * `INDUSTRIAL_FIRE` → red pin with a ball top, anchored at its base.
   * everything else → translucent radial field markers with a thin definition
     ring, `scaleByDistance` + `translucencyByDistance` so overlapping events
     stay readable.

Click behaviour: marker → select event + fly to it; state polygon → select the
region; anywhere else → close the selected-event panel.

3D is used for globe navigation only. No terrain, buildings or digital twins.
