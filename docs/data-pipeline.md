# Data Pipeline

NASA FIRMS is the real-data path when `FIRMS_API_KEY` is present. The `/api/ingestion/firms` endpoint validates coordinates, restricts the request to the configured India region, stores source metadata, and keeps demo fixtures separate. OSM and satellite/land-cover services are intentionally modular; the current UI reports their configuration state rather than fabricating values.