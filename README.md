# ThermoIntel

ThermoIntel is an AI-powered geospatial intelligence platform for monitoring satellite-derived thermal anomalies across India.

It takes thermal observations from NASA FIRMS, enriches them with geographic and historical context, classifies their likely source using machine learning, and presents the resulting information through an interactive web dashboard.

The idea is simple: a satellite hotspot by itself does not tell you much. ThermoIntel tries to answer what the hotspot is likely to represent, whether the activity is recurring, whether it is close to an industrial facility, and whether it deserves further attention.

The overall workflow is:

NASA FIRMS
→ Thermal Detection
→ Contextual Enrichment
→ Feature Engineering
→ ML Classification
→ Anomaly Analysis
→ Priority Scoring
→ MongoDB
→ FastAPI
→ Web Dashboard


## What ThermoIntel Does

ThermoIntel works with satellite-derived thermal observations rather than satellite images.

For every observation, the system can use information such as:

- Location
- Acquisition time
- Fire Radiative Power (FRP)
- Brightness temperature
- Satellite and instrument
- Detection confidence
- Day/night information
- Land-use context
- State/UT information
- Historical thermal activity
- Nearby industrial facilities

The resulting information is used to classify and prioritize thermal events.

The system is designed primarily as a decision-support and monitoring platform. A FIRMS detection is a satellite-detected thermal anomaly; it is not automatically proof of a fire, and proximity to an industrial facility does not by itself prove causation.


## Classification

ThermoIntel uses a hierarchical machine-learning approach.

### M1 — Agricultural vs Industrial

The first classification separates thermal activity into:

- AGRICULTURAL
- INDUSTRIAL

The agricultural category is intentionally broad and includes agricultural and forest-fire activity.

The industrial category includes industrial fires and persistent industrial thermal sources.

### M2 — Agricultural Event Type

For observations classified as agricultural, the next stage distinguishes between:

- AGRICULTURAL_FIRE
- FOREST_FIRE

### M3 — Industrial Event Type

For observations classified as industrial, the next stage distinguishes between:

- INDUSTRIAL_FIRE
- PERSISTENT_SOURCE

### M4 — Persistent Source Type

Persistent industrial sources can then be classified into more specific source categories, including:

- Brick kiln
- Cement kiln
- Chemical facility
- Gas flare
- Mining/mineral processing
- Oil refinery/petrochemical
- Power plant
- Steel/metal
- Other persistent industrial source

The hierarchy prevents every thermal detection from being treated as the same type of event.


## Data Sources

### NASA FIRMS

NASA FIRMS (Fire Information for Resource Management System) is the primary source of thermal observations.

The data provides thermal and observation-level information including:

- Latitude and longitude
- Acquisition date and time
- FRP
- Brightness temperatures
- Confidence
- Satellite
- Instrument
- Day/night information

ThermoIntel processes these observations as satellite-derived thermal anomalies.


### OpenStreetMap

OpenStreetMap data is used to provide geographic context around industrial facilities.

Facility records can contain:

- OSM identifier
- Location
- Facility name
- Facility type
- Tags
- Source information
- Point geometry

Facility proximity is treated as contextual evidence rather than proof that a facility caused a particular thermal observation.


### Land-Use and Geographic Data

Land-use and geographic reference data are used during feature engineering to provide additional context around thermal observations.

State and Union Territory information is also incorporated into the data-processing pipeline.


### Historical Thermal Data

ThermoIntel does not treat every observation as an isolated point.

Historical observations around a location can be used to identify recurring or persistent thermal behaviour. Historical summaries are calculated across multiple time windows, including short-term and longer-term periods.


## Machine Learning

The machine-learning pipeline is built around XGBoost and scikit-learn.

The production inference pipeline uses the same feature definitions and preprocessing contract established during model development.

The core M1 pipeline uses 35 raw input features which are transformed into the encoded feature representation used by the trained model.

Features include information derived from:

- FIRMS thermal measurements
- Detection confidence
- Satellite/instrument information
- Temporal characteristics
- Day/night characteristics
- Geographic location
- State/UT
- Land-use information
- FRP transformations
- Brightness relationships
- Industrial-facility context
- Temporal/cyclic encodings

Model artifacts are serialized using Joblib and loaded by the backend during inference.


## Backend

The backend is written in Python using FastAPI.

Its responsibilities include:

- FIRMS ingestion
- Data validation
- Thermal detection storage
- Event handling
- Contextual enrichment
- Feature engineering
- Machine-learning inference
- Dashboard APIs
- Ingestion monitoring
- Facility and regional queries
- Model status and classification endpoints

The backend communicates with MongoDB and exposes the data required by the frontend dashboard.


## Frontend

The frontend is built with React.

The dashboard provides an operational view of the thermal observations rather than simply displaying raw data.

The interface includes:

- Interactive map
- Thermal-event markers
- Agricultural/industrial classification filters
- Persistent-source and industrial-fire categories
- Region filtering
- Event details
- Historical information
- Priority information
- Facility context
- Dashboard summaries
- Investigation views

The mapping layer supports both 2D and 3D visualization, using Leaflet/React-Leaflet for the 2D map and Cesium for the 3D globe.


## Database

ThermoIntel uses MongoDB, with MongoDB Atlas used for cloud deployment.

The database stores the thermal observations and related contextual information required by the application.

Important data includes:

- Thermal detections
- Events
- Facilities
- Ingestion runs
- Model-related information

Geospatial indexes are used for location-based queries and facility searches.


## Pipeline

The main processing flow is:

1. NASA FIRMS provides thermal observations.
2. The backend validates and stores the observations.
3. Geographic and historical context is added.
4. Features are generated using the project's feature contract.
5. M1 determines whether the activity is agricultural or industrial.
6. The appropriate downstream classifier is applied.
7. Historical behaviour and contextual information are used for anomaly analysis.
8. A system priority value is generated.
9. The processed information is stored in MongoDB.
10. The React dashboard retrieves and visualizes the results through the FastAPI backend.


## Automated Ingestion

The project includes a Render cron-service configuration for automated FIRMS ingestion.

The cron entrypoint calls the same ingestion implementation used by the backend API rather than maintaining a separate ingestion pipeline.

The scheduled configuration is intended to periodically:

- Fetch recent FIRMS observations
- Insert new observations
- Skip observations that already exist
- Process the new detections
- Run the downstream pipeline

The production cron service requires the appropriate Render configuration and environment variables to be enabled.


## API

The backend exposes API endpoints for the dashboard and pipeline.

The API includes functionality for:

- Dashboard summaries
- Thermal anomalies
- Events
- Alerts
- Facilities
- Regions
- Hotspots
- Model information
- Classification
- Ingestion
- Ingestion status

The interactive API documentation is available through FastAPI's built-in Swagger interface when the backend is running.


## Project Structure

The repository is organized roughly as follows:

```text
thermointel/
│
├── backend/
│   ├── api/
│   │   └── routes/
│   ├── core/
│   ├── data/
│   ├── models/
│   ├── pipeline/
│   ├── scripts/
│   ├── services/
│   ├── tests/
│   └── server.py
│
├── frontend/
│   ├── public/
│   └── src/
│
├── docs/
│
├── render.yaml
├── README.md
└── .gitignore


Running Locally
Requirements

Install the following before starting the project:

Python 3.x
Node.js
npm
MongoDB or a MongoDB Atlas connection
NASA FIRMS API key

The Python environment should use versions compatible with the project's machine-learning dependencies.

Backend Setup

Open a terminal in the backend directory:

cd backend

Create and activate a Python virtual environment if required.

Install dependencies:

pip install -r requirements.txt

Create a .env file in the backend directory.

The main configuration values are:

MONGO_URL=your_mongodb_connection_string
DB_NAME=thermointel
FIRMS_API_KEY=your_firms_api_key

Additional deployment-specific variables may be required depending on the configured environment.

Start the Backend

From the backend directory:

python -m uvicorn server:app --host 127.0.0.1 --port 8000

The API will then be available at:

http://127.0.0.1:8000

FastAPI Swagger documentation:

http://127.0.0.1:8000/docs
Frontend Setup

Open another terminal:

cd frontend

Install dependencies:

npm install

If the project requires the legacy peer-dependency resolution used by the existing dependency set:

npm install --legacy-peer-deps

Create the frontend environment file if it does not already exist:

REACT_APP_BACKEND_URL=http://127.0.0.1:8000

Start the frontend:

npm start

The dashboard will normally be available at:

http://localhost:3000
Production Architecture

The deployed system uses:

Render for application hosting
MongoDB Atlas for the database
GitHub for source control
NASA FIRMS for satellite-derived thermal observations

The production flow is:

NASA FIRMS
→ Backend ingestion
→ MongoDB Atlas
→ Feature engineering
→ ML inference
→ FastAPI
→ React dashboard

Deployment

The repository contains a render.yaml configuration for deployment.

The application can be deployed using Render with the required environment variables configured in the Render dashboard.

The backend requires access to:

MongoDB
NASA FIRMS
The trained model artifacts
Required reference data

The frontend communicates with the deployed backend through the configured backend URL.

Testing

Backend tests use Pytest.

Run the backend test suite from the backend directory:

pytest

For targeted testing, individual test files can be executed directly:

pytest tests/<test_file>.py

The most important tests cover areas such as:

API behaviour
Data ingestion
Feature engineering
Model inference
Facility context
Pipeline behaviour
Model Artifacts

The trained models and their supporting preprocessing/configuration artifacts are stored as serialized files.

The M1 inference contract includes:

Model artifact
Preprocessing artifact
Feature schema
Class mapping
Model metadata
Calibration information where applicable

The backend must use the same feature order and preprocessing assumptions used when the model was trained.

Changing the feature contract without retraining and regenerating compatible artifacts can break inference.

Important Interpretation Notes

ThermoIntel works with satellite-derived thermal observations.

A thermal observation should not automatically be described as a confirmed fire.

Similarly:

An industrial classification is a model prediction.
A nearby industrial facility is contextual evidence.
A persistent thermal source is a classification, not proof of a specific industrial process.
A system priority value is an internal prioritization signal, not an official risk rating.
A potential industrial fire should not be described as a confirmed industrial fire without independent confirmation.

These distinctions are important when interpreting results from the system.

Intended Use

ThermoIntel is intended to help users investigate large numbers of thermal observations more efficiently.

Potential users include:

Government and disaster-management authorities
Industrial safety teams
Emergency response teams
Environmental authorities
Researchers working with satellite thermal data

The platform is intended to support investigation and prioritization rather than replace field verification or official emergency-response systems.

Why It Matters

Satellite thermal products can produce large numbers of observations across a large geographic area.

Looking at those observations individually makes it difficult to identify which ones deserve attention.

ThermoIntel combines:

Satellite thermal measurements
Temporal behaviour
Geographic context
Industrial-facility proximity
Land-use information
Machine learning

to turn individual thermal observations into more useful, contextualized intelligence.

Limitations

ThermoIntel has several important limitations.

NASA FIRMS observations are remote-sensing detections and do not independently establish the cause of a thermal anomaly.

Industrial-facility proximity does not establish causation.

Machine-learning predictions depend on the quality and coverage of their training and validation data.

Some geographic locations may have incomplete contextual coverage.

Independent ground-truth validation is still important before making strong real-world accuracy or safety claims.

The system should therefore be treated as a monitoring and decision-support platform rather than a certified fire-detection or emergency-response authority.

Future Scope

Potential future improvements include:

More extensive independently verified ground truth
Additional environmental and meteorological context
Improved event grouping and temporal continuity
More detailed industrial-source classification
Additional satellite sources
Improved uncertainty estimation
Larger-scale historical analysis
More advanced geospatial visualization
Improved alerting and notification workflows
Continued validation across different geographic and seasonal conditions
Technology Stack

ThermoIntel is built using:

Python
FastAPI
Uvicorn
MongoDB
MongoDB Atlas
PyMongo / Motor
Pydantic
XGBoost
scikit-learn
Pandas
NumPy
Joblib
React
React Leaflet
Leaflet
Cesium
Tailwind CSS
Axios
Lucide React
Recharts
NASA FIRMS
OpenStreetMap
Overpass API
Pytest
Git
GitHub
Render
Jupyter
Project Status

ThermoIntel currently provides an end-to-end pipeline for processing real satellite-derived thermal observations, enriching them with contextual information, running machine-learning classification, storing the results, and presenting them through a web dashboard.

The system is intended to continue evolving as additional ground-truth data, validation and operational requirements become available.

License

This project was developed as part of the Smart India Hackathon and is currently maintained as a project/research prototype.

See the repository for the applicable project licensing and usage terms.



I intentionally kept the README **human-readable and practical** rather than turning it into a giant technical specification. I also removed claims that the project documentation explicitly says should **not** be made, such as satellite-image analysis, TensorFlow/PyTorch, weather APIs, IoT sensors, etc. :contentReference[oaicite:2]{index=2}

One correction from the older README/context: **Cesium is included here because the current project audit explicitly confirms the 3D Cesium globe alongside the 2D Leaflet map.** :contentReference[oaicite:3]{index=3}