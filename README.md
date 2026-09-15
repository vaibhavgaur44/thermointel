# ThermoIntel v2 — Phase 2 Foundation

India-only thermal-event intelligence platform. NASA FIRMS reports a thermal
signal; ThermoIntel determines what likely produced it, whether it is
normal or abnormal, and whether it represents a threat.

**This repository is the Phase 2 application foundation.** The Cesium globe,
the floating intelligence panels, the API surface and the MongoDB schemas are
complete. Ingestion, event formation, feature engineering, ML inference, the
threat/anomaly engine and alert generation are declared as interfaces and
raise `PipelineStageNotImplemented` — nothing is simulated.

---

## Stack

| Layer    | Technology                                  |
| -------- | ------------------------------------------- |
| Frontend | React 19, CesiumJS (CDN), Tailwind, shadcn/ui |
| Backend  | Python, FastAPI, Motor                      |
| Database | MongoDB Atlas (any MongoDB 5+)              |
| Hosting  | Render (frontend + backend), GitHub         |

---

## Project structure

```
backend/
  server.py                  FastAPI entry point (/api/health + router)
  core/
    config.py                Environment-driven settings
    database.py              Motor client, collection names, index creation
  models/
    enums.py                 Frozen Phase 1 taxonomy (event types, source types,
                             threat levels, statuses, evidence codes)
    common.py                PyObjectId, BaseDocument, GeoPoint
    detection.py             thermal_detections   (raw FIRMS observations)
    event.py                 events               (primary operational dataset)
    facility.py              facilities           (India facility intelligence)
    ground_truth.py          ground_truth         (verified labels)
    alert.py                 alerts               (threat-threshold outcomes)
    ingestion_run.py         ingestion_runs       (pipeline execution history)
    model_version.py         model_versions       (versions, features, metrics)
  services/
    filters.py               Query-filter construction (all filtering is backend)
    event_service.py         Event reads, priority ranking, regional counts
    registry_service.py      Alerts, facilities, detections, runs, models
  pipeline/
    base.py                  PipelineStageNotImplemented
    firms_ingestion.py       Stage 1  (Phase 3/5)
    event_formation.py       Stage 2  (Phase 5) - unfrozen grouping config
    feature_engineering.py   Stage 3  (Phase 4) - feature GROUPS only
    ml_inference.py          Stage 4  (Phase 4/5) - hierarchical model stack
    threat_engine.py         Stage 5+6 (Phase 4/5) - unfrozen weights/threshold
  api/
    router.py                Aggregates every /api route group
    routes/                  events, alerts, data, ingestion, models,
                             reference, dev
  data/india_regions.py      States + Union Territories (no districts)
  dev/demo_dataset.py        Clearly labelled DEMO dataset (isolated)

frontend/src/
  api/                       client.js (axios) + thermointel.js (contracts)
  state/DashboardContext.jsx Filters, region, selection, demo mode
  hooks/useThermoIntel.js    React Query data hooks
  constants/taxonomy.js      Labels + marker colours (presentation only)
  lib/cesiumLoader.js        Waits for the CDN Cesium bundle
  map/
    viewer.js                Viewer creation, basemap stacks, camera helpers
    markerImages.js          Canvas marker artwork (pin + soft field markers)
    eventLayer.js            Event entities and picking
    boundaryLayer.js         India state/UT overlay + region picking
  components/
    map/GlobeCanvas.jsx      Globe orchestration
    layout/                  TopBar, FilterBar
    panels/                  RegionalOverview, PriorityEvents, AlertQueue,
                             SelectedEvent
    common/                  Panel, PanelStates, Indicators
  pages/Dashboard.jsx        Single continuous intelligence map
  public/geo/india_states.geojson  Simplified state/UT boundaries (78 KB)
```

The frontend contains **no** classification, threat or anomaly logic.

---

## Local development

```bash
# Backend
cd backend
cp .env.example .env          # set MONGO_URL + DB_NAME
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend
cp .env.example .env          # set REACT_APP_BACKEND_URL
yarn install
yarn start
```

### Environment variables

Backend (`backend/.env`):

| Variable               | Required | Notes                                        |
| ---------------------- | -------- | -------------------------------------------- |
| `MONGO_URL`            | yes      | MongoDB Atlas connection string              |
| `DB_NAME`              | yes      | Fresh v2 database, e.g. `thermointel_v2`     |
| `CORS_ORIGINS`         | no       | Comma-separated origins, defaults to `*`     |
| `FIRMS_API_KEY`        | no       | Phase 3/5. Empty in Phase 2                  |
| `FIRMS_BASE_URL`       | no       | Phase 3/5. Empty in Phase 2                  |
| `ACTIVE_MODEL_VERSION` | no       | Phase 4/5. Empty in Phase 2                  |
| `ALLOW_DEMO_DATA`      | no       | `false` disables the DEMO endpoints entirely |

Frontend (`frontend/.env`):

| Variable                      | Required | Notes                                              |
| ----------------------------- | -------- | -------------------------------------------------- |
| `REACT_APP_BACKEND_URL`       | yes      | Backend base URL, no trailing slash                |
| `REACT_APP_CESIUM_ION_TOKEN`  | no       | Enables Cesium Ion world imagery for "Satellite"   |

No secret is ever hard-coded. `.env` files are not committed.

---

## API

All routes are prefixed with `/api`.

| Method | Route                     | Purpose                                            |
| ------ | ------------------------- | -------------------------------------------------- |
| GET    | `/health`                 | Service + database status                          |
| GET    | `/events`                 | Filtered events (`status`, `classification`, `source_type`, `state`, `time_range`, `sort_by`, paging) |
| GET    | `/events/summary`         | Regional Overview counts                           |
| GET    | `/events/priority`        | Top-N highest-threat ACTIVE events                 |
| GET    | `/events/{event_id}`      | Selected Event Intelligence payload                |
| GET    | `/alerts`                 | Alert queue                                        |
| GET    | `/alerts/{alert_id}`      | Single alert                                       |
| GET    | `/facilities`             | Facility intelligence                              |
| GET    | `/thermal-detections`     | Raw FIRMS observations                             |
| GET    | `/ingestion/status`       | Pipeline readiness + recent runs                   |
| POST   | `/ingestion/run`          | Trigger the pipeline (records a run per stage)      |
| GET    | `/models`                 | Model registry + expected model stack              |
| GET    | `/regions`                | States and Union Territories with bounding boxes   |
| GET    | `/taxonomy`               | Frozen Phase 1 vocabulary                          |
| GET    | `/dev/demo-data/status`   | DEMO dataset counts                                |
| POST   | `/dev/demo-data/seed`     | Insert the DEMO dataset                            |
| DELETE | `/dev/demo-data/clear`    | Remove the DEMO dataset                            |

There is deliberately **no confidence filter** (Phase 1, section 19).

---

## Live vs historical

```
RAW FIRMS DETECTIONS -> EVENT FORMATION -> THERMOINTEL EVENTS
```

* An event is `ACTIVE` while current FIRMS observations support it.
* Only `ACTIVE` events are on the LIVE map (`viewMode = LIVE`).
* When the live feed no longer supports an event it becomes `INACTIVE` /
  `EXPIRED`; the document is **never deleted** and keeps feeding baselines.
* `viewMode = HISTORICAL` widens the query to every status.

---

## DEMO data

Demo documents carry `data_origin = "demo"`. The API returns them **only** when
a request passes `include_demo=true`, the UI toggle is **off by default**, and
a full-width amber banner is shown whenever it is on. Set
`ALLOW_DEMO_DATA=false` to remove the endpoints completely.

Demo values are invented for interface testing. They are not FIRMS
observations, model predictions or threat assessments.

---

## Deployment (Render + MongoDB Atlas)

`render.yaml` describes both services.

1. Create a free MongoDB Atlas cluster, a fresh v2 database, and a database
   user. Allow Render's egress IPs (or `0.0.0.0/0` for a student project).
2. Push this repository to GitHub.
3. In Render, create a **Blueprint** from the repo, then set the secrets:
   `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS` (backend) and
   `REACT_APP_BACKEND_URL` (frontend).
4. Deploy. Indexes are created automatically on backend startup.

Nothing here requires paid infrastructure.

---

## What Phase 2 intentionally does NOT do

No model training, no model artifacts, no feature engineering, no anomaly
algorithm, no threat-score formula, no alert threshold, no FIRMS dataset, no
ground-truth dataset, no classification heuristics, no invented facilities, no
weather/AQI/imagery layers, no authentication, no push notifications, no 3D
buildings or simulated fires.

Values left unfrozen by Phase 1 (grouping radius, grouping time window,
threat weights, level boundaries, alert threshold, calibration method) are
exposed as configuration objects whose fields are `None` until real data sets
them.
