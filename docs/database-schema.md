# ThermoIntel Data Schema

The runnable MVP uses MongoDB with stable string IDs and GeoJSON-shaped `geometry` values. Collections are `anomalies`, `facilities`, `ingestion_runs`, `alerts`, and `model_versions`. All returned documents explicitly exclude MongoDB `_id`.

The planned PostGIS migration maps `anomalies.geometry` to `geography(Point,4326)`, `facilities.geometry` to `geography(Point,4326)`, adds GiST indexes, and preserves `source`, `is_demo`, and raw-source metadata. This keeps the MVP portable without claiming MongoDB provides PostGIS functionality.