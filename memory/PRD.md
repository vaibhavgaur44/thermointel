# ThermoIntel Product Brief

## Original problem statement

Build a complete, runnable AI + GIS platform for India that detects and classifies industrial fires and persistent thermal sources using NASA FIRMS, OSM industrial context, historical thermal observations, geospatial features, ML classification, persistence analysis, anomaly detection, transparent priority scoring, FastAPI APIs, and a GIS dashboard. The system must distinguish satellite detection from predicted classification and official confirmation, never fabricate data or metrics, and support clearly labeled demo mode.

## Architecture decisions

- FastAPI + MongoDB is the runnable MVP architecture, using stable string IDs and GeoJSON-shaped fields.
- PostGIS schema and migration intent are documented separately so a spatial database can be adopted without changing product concepts.
- React + Leaflet provides the GIS command center; the frontend calls only the configured backend URL.
- FIRMS is backend-only and uses `FIRMS_API_KEY`; missing credentials produce a configuration-required state.
- GPT-5.4 Analyst is backend-only and grounded in current structured API data.
- Satellite imagery and land-cover are modular but intentionally unavailable until configured.
- India scope is configuration-driven with All India, Gujarat, Maharashtra, and Odisha.

## User personas

- Disaster-management analyst triaging high-priority thermal signals.
- Geospatial investigator validating industrial context and historical behavior.
- Data/ML engineer replacing demo fixtures with validated FIRMS labels and trained models.

## Core requirements

- Regional India selector and server-side regional filtering.
- FIRMS ingestion endpoint with validation, secure credentials, and graceful failure.
- Industrial facilities, anomaly map, historical/persistence indicators, anomaly status, priority score, evidence, alerts, and investigation view.
- Honest model-status page and reproducible feature/training entry points.
- Optional Analyst assistant that does not invent data.
- DEMO DATA labeling and separation from real-source fields.

## Implemented

### 2026-08-29

- Replaced starter screen with the ThermoIntel tactical command dashboard.
- Added MongoDB demo seed data for industrial fires, persistent sources, flares, agricultural burning, and natural fires.
- Added FastAPI endpoints for summaries, anomalies, facilities, hotspots, alerts, model status, ingestion status, FIRMS ingestion, and Analyst.
- Added configurable India regions and GeoJSON-shaped anomaly responses without Mongo `_id` leakage.
- Added Leaflet map overlays, filters, facility markers, priority queue, investigation evidence, FRP/baseline chart, alerts, pipeline status, and responsive mobile layout.
- Added FIRMS service configuration, baseline feature builder, training scaffold, PostGIS migration notes, data-pipeline documentation, README, and secure backend-only LLM/FIRMS environment entries.
- Verified backend regression and frontend flows through two test iterations; final iteration reports no unresolved issues.

## Prioritized backlog

### P0

- Connect a validated FIRMS key and run real regional ingestion.
- Replace demo industrial facilities with cached OSM/Overpass ingestion and proximity calculations.
- Supply validated labels, train a time-split classifier, and store real evaluation metrics.

### P1

- Add real historical aggregation and persistent hotspot clustering.
- Add public satellite metadata retrieval and land-cover raster service adapters.
- Add PostGIS migration and spatial indexes for production-scale querying.

### P2

- Add alert lifecycle updates and analyst audit history.
- Add model registry UI, confusion matrix, per-class metrics, and SHAP evidence.
- Add scheduled ingestion and larger-scale server-side clustering.

## Next tasks

1. Configure FIRMS_API_KEY securely and validate live Gujarat/Maharashtra/Odisha ingestion.
2. Implement Overpass caching and real OSM facility enrichment.
3. Replace baseline rule inference with a validated time-aware ML model.
4. Enable satellite and land-cover adapters when public data paths are selected.