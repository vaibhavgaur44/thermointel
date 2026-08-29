# ThermoIntel

India-first AI and GIS prototype for detecting and classifying industrial thermal sources. The runnable MVP includes MongoDB persistence, clearly labeled demo data, NASA FIRMS ingestion when configured, India region filtering, industrial context, baseline feature engineering, persistence/anomaly/priority signals, FastAPI APIs, a GIS dashboard, investigation detail, alerts, model status, and the GPT-5.4 Analyst integration.

## Run

Backend uses existing `backend/.env` keys `MONGO_URL`, `DB_NAME`, and `CORS_ORIGINS`. Add `FIRMS_API_KEY` and `EMERGENT_LLM_KEY` only to backend environment configuration; neither is exposed to the frontend. Start services with the workspace supervisor. Frontend API calls use the existing `REACT_APP_BACKEND_URL`.

## Scientific limits

Demo fixtures are synthetic and always labeled `DEMO DATA`. A FIRMS detection is not a confirmed fire; proximity is evidence, not causation; model evaluation remains unavailable until validated human labels are supplied. Satellite imagery and land-cover are shown as unavailable until configured.

## Training

`python ml/training/train_classifier.py --dataset path/to/validated_labels.csv` is the explicit training entry point. The baseline feature builder is in `ml/features/build_features.py`. Do not publish metrics until a time-based evaluation is performed on validated labels.
# Here are your Instructions
