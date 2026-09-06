from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional, List
from pathlib import Path
from datetime import datetime, timezone, timedelta
import os, uuid, logging, math, json, csv, io, asyncio

try:
    import requests
except ImportError:
    requests = None

from services import model_inference

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]
logger = logging.getLogger("thermointel")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="ThermoIntel API", version="0.1.0")
api = APIRouter(prefix="/api")

REGIONS = {
    "all-india": {"label": "All India", "bbox": [68.1, 6.5, 97.4, 35.7]},
    "gujarat": {"label": "Gujarat", "bbox": [68.1, 20.0, 74.5, 24.7]},
    "maharashtra": {"label": "Maharashtra", "bbox": [72.5, 15.6, 80.2, 22.1]},
    "odisha": {"label": "Odisha", "bbox": [81.3, 17.8, 87.6, 22.6]},
}
CLASSES = ["Industrial Fire", "Persistent Industrial Thermal Source", "Gas Flare / Industrial Flare", "Agricultural Burning", "Wildfire / Natural Fire", "Mining / Industrial Activity", "Other / Unknown"]

class AnalystRequest(BaseModel):
    question: str = Field(min_length=3, max_length=800)
    region: str = "all-india"

class MLClassifyRequest(BaseModel):
    features: dict = Field(description="Feature dict keyed by the names in /api/ml/schema")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def haversine(a_lat, a_lon, b_lat, b_lon):
    r = 6371
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat-a_lat), math.radians(b_lon-a_lon)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2*r*math.asin(math.sqrt(x)), 2)

def in_bbox(lat, lon, bbox):
    return bbox[1] <= lat <= bbox[3] and bbox[0] <= lon <= bbox[2]

def score_event(frp, confidence, distance_km, persistence, z_score, predicted_class):
    intensity = min(30, frp / 10)
    proximity = max(0, min(20, 20 - (distance_km or 20) * 1.5))
    deviation = min(20, max(0, z_score * 6))
    persist = min(15, persistence * 15)
    class_signal = 15 if predicted_class in ["Industrial Fire", "Gas Flare / Industrial Flare"] else 7
    return round(min(100, intensity + confidence * 0.15 + proximity + deviation + persist + class_signal))

def classify(frp, confidence, distance_km, detections_30d, z_score):
    if distance_km is not None and distance_km < 8 and z_score >= 2.2:
        label = "Industrial Fire"
    elif distance_km is not None and distance_km < 5 and detections_30d >= 8:
        label = "Persistent Industrial Thermal Source"
    elif distance_km is not None and distance_km < 3 and detections_30d >= 3:
        label = "Gas Flare / Industrial Flare"
    elif frp > 100 and confidence < 70:
        label = "Wildfire / Natural Fire"
    elif frp < 25:
        label = "Agricultural Burning"
    else:
        label = "Other / Unknown"
    base = {"Industrial Fire": .91, "Persistent Industrial Thermal Source": .87, "Gas Flare / Industrial Flare": .89, "Wildfire / Natural Fire": .76, "Agricultural Burning": .71, "Other / Unknown": .54}[label]
    return label, round(min(.98, base + max(0, min(.06, z_score*.01))), 2)

def demo_facilities():
    return [
        {"id":"fac-jamnagar-01","name":"Jamnagar Refining Complex","facility_type":"refinery","latitude":22.35,"longitude":69.89,"osm_id":"demo-osm-001","source":"DEMO DATA · OSM-shaped fixture","tags":{"industry":"oil"},"is_demo":True},
        {"id":"fac-dahej-01","name":"Dahej Petrochemical Estate","facility_type":"petrochemical","latitude":21.70,"longitude":72.63,"osm_id":"demo-osm-002","source":"DEMO DATA · OSM-shaped fixture","tags":{"industrial":"petrochemical"},"is_demo":True},
        {"id":"fac-trombay-01","name":"Trombay Power & Industrial Zone","facility_type":"power","latitude":19.00,"longitude":72.93,"osm_id":"demo-osm-003","source":"DEMO DATA · OSM-shaped fixture","tags":{"power":"plant"},"is_demo":True},
        {"id":"fac-talcher-01","name":"Talcher Energy Corridor","facility_type":"power","latitude":20.95,"longitude":85.22,"osm_id":"demo-osm-004","source":"DEMO DATA · OSM-shaped fixture","tags":{"industrial":"energy"},"is_demo":True},
    ]

def demo_anomalies():
    base = datetime.now(timezone.utc)
    raw = [
        ("an-001",22.36,69.90,186,96,"Industrial Fire",.93,2.9,0.18,14,"High",88,"Jamnagar Refining Complex","refinery"),
        ("an-002",21.70,72.65,78,91,"Persistent Industrial Thermal Source",.88,1.8,0.91,23,"Watch",63,"Dahej Petrochemical Estate","petrochemical"),
        ("an-003",19.01,72.92,128,82,"Gas Flare / Industrial Flare",.89,1.4,0.56,11,"Watch",67,"Trombay Power & Industrial Zone","power"),
        ("an-004",20.46,73.92,42,74,"Agricultural Burning",.71,42.0,0.08,2,"Normal",28,None,None),
        ("an-005",20.95,85.20,231,88,"Industrial Fire",.92,2.3,0.31,8,"High",91,"Talcher Energy Corridor","power"),
        ("an-006",21.05,85.41,109,68,"Wildfire / Natural Fire",.76,25.0,0.12,4,"Watch",51,None,None),
    ]
    docs=[]
    for i,(ident,lat,lon,frp,conf,label,prob,dist,persist,count,status,priority,facility,ftype) in enumerate(raw):
        docs.append({"id":ident,"latitude":lat,"longitude":lon,"acquisition_datetime":(base-timedelta(hours=i*7)).isoformat(),"satellite":"VIIRS SNPP","instrument":"VIIRS","confidence":conf,"frp":frp,"daynight":"D" if i%2 else "N","source":"DEMO DATA · synthetic fixture","is_demo":True,"region":"India","state":"Gujarat" if i<4 else "Odisha","predicted_class":label,"prediction_confidence":prob,"nearest_facility":facility,"nearest_facility_type":ftype,"distance_km":dist,"persistence_score":persist,"detections_30d":count,"z_score":3.2 if status=="High" else 1.1,"anomaly_status":status,"priority_score":priority,"evidence":["high thermal intensity" if frp>100 else "moderate thermal intensity", "industrial context detected" if facility else "no nearby industrial facility", "historical baseline comparison available"],"land_cover_status":"Unavailable · configure land-cover service","imagery_status":"Unavailable · configure satellite imagery service"})
    return docs

async def seed_demo():
    if await db.anomalies.count_documents({}) == 0:
        await db.anomalies.insert_many(demo_anomalies())
    if await db.facilities.count_documents({}) == 0:
        await db.facilities.insert_many(demo_facilities())

@app.on_event("startup")
async def startup():
    try:
        await seed_demo()
    except Exception as exc:
        logger.warning("Demo seed unavailable: %s", exc)

@api.get("/")
async def root():
    return {"name":"ThermoIntel API","status":"online","scope":"India","demo_data":True}

@api.get("/regions")
async def regions():
    return [{"id":k,"label":v["label"],"bbox":v["bbox"]} for k,v in REGIONS.items()]

@api.get("/dashboard/summary")
async def summary(region: str = "all-india"):
    bbox = REGIONS.get(region, REGIONS["all-india"])["bbox"]
    docs = await db.anomalies.find({}, {"_id":0}).to_list(5000)
    docs = [d for d in docs if in_bbox(d.get("latitude",0), d.get("longitude",0), bbox)]
    facs = await db.facilities.count_documents({})
    return {"total_anomalies":len(docs),"industrial_classified":sum(d.get("predicted_class","") in CLASSES[:3] for d in docs),"persistent_sources":sum(d.get("persistence_score",0)>=.5 for d in docs),"abnormal_events":sum(d.get("anomaly_status") in ["High","Anomalous"] for d in docs),"high_priority":sum(d.get("priority_score",0)>=80 for d in docs),"facilities_monitored":facs,"last_update":max([d.get("acquisition_datetime","") for d in docs],default=None),"data_mode":"DEMO DATA","scope":REGIONS.get(region,REGIONS["all-india"])["label"]}

@api.get("/anomalies")
async def anomalies(region: str="all-india", classification: Optional[str]=None, status: Optional[str]=None, min_priority: int=0, limit: int=100):
    bbox=REGIONS.get(region,REGIONS["all-india"])["bbox"]
    docs=await db.anomalies.find({}, {"_id":0}).sort("priority_score",-1).to_list(5000)
    docs=[d for d in docs if in_bbox(d.get("latitude",0),d.get("longitude",0),bbox)]
    if classification: docs=[d for d in docs if d.get("predicted_class")==classification]
    if status: docs=[d for d in docs if d.get("anomaly_status")==status]
    return {"items":[{**d,"type":"Feature","geometry":{"type":"Point","coordinates":[d["longitude"],d["latitude"]]},"properties":d} for d in docs if d.get("priority_score",0)>=min_priority][:limit],"count":len(docs),"data_mode":"DEMO DATA"}

@api.get("/anomalies/{anomaly_id}")
async def anomaly(anomaly_id: str):
    doc=await db.anomalies.find_one({"id":anomaly_id},{"_id":0})
    if not doc: raise HTTPException(404,"Anomaly not found")
    history=[{"date":(datetime.now(timezone.utc)-timedelta(days=i)).strftime("%b %d"),"frp":round(max(12,doc["frp"]*(.56+((i*17)%40)/100)),1),"baseline":round(doc["frp"]*.56,1)} for i in range(13,-1,-1)]
    return {"anomaly":doc,"history":history,"model_explanation":doc.get("evidence",[]),"classification_probabilities":[{"label":c,"value":(doc["prediction_confidence"] if c==doc["predicted_class"] else round(max(.03,(1-doc["prediction_confidence"])/6),2))} for c in CLASSES],"scientific_note":"Detection, predicted classification, and anomaly status are separate signals. This is a system priority score, not an official risk rating."}

@api.get("/facilities")
async def facilities(region: str="all-india"):
    bbox=REGIONS.get(region,REGIONS["all-india"])["bbox"]
    docs=await db.facilities.find({}, {"_id":0}).to_list(5000)
    return {"items":[d for d in docs if in_bbox(d.get("latitude",0),d.get("longitude",0),bbox)],"data_mode":"DEMO DATA"}

@api.get("/hotspots")
async def hotspots(region: str="all-india"):
    docs=await anomalies(region,limit=100)
    return {"items":[d for d in docs["items"] if d.get("persistence_score",0)>=.5],"data_mode":docs["data_mode"]}

@api.get("/alerts")
async def alerts(region: str="all-india"):
    docs=await anomalies(region,limit=100)
    return {"items":[{"id":"alert-"+d["id"],"time":d["acquisition_datetime"],"location":f"{d['latitude']:.2f}°N, {d['longitude']:.2f}°E","reason":"Potential abnormal industrial thermal activity" if d["anomaly_status"]=="High" else "Persistent thermal source detected","priority":d["priority_score"],"status":"Open","anomaly_id":d["id"]} for d in docs["items"] if d.get("priority_score",0)>=60],"data_mode":"DEMO DATA"}

@api.get("/model/status")
async def model_status():
    availability = model_inference.models_available()
    return {"available":False,"version":"baseline-rules-v0.1","metrics_available":False,"message":"Model evaluation unavailable — training dataset requires validation.","classes":CLASSES,"training_pipeline":"/app/ml/training/train_classifier.py","trained_models":{"model1_agricultural_vs_industrial":availability["model1_loaded"],"model2_persistent_vs_industrial_fire":availability["model2_loaded"],"metrics_validated":False,"disclaimer":model_inference.DISCLAIMER}}

@api.get("/ml/schema")
async def ml_schema():
    return model_inference.get_feature_schema()

@api.post("/ml/classify")
async def ml_classify(req: MLClassifyRequest):
    availability = model_inference.models_available()
    if not availability["model1_loaded"]:
        raise HTTPException(503, "Trained model artifacts are not available on this deployment.")
    try:
        result = model_inference.run_inference(req.features)
    except Exception as exc:
        logger.exception("ML inference failed")
        raise HTTPException(500, f"Inference failed: {exc}")
    return result

@api.get("/ingestion/status")
async def ingestion_status():
    return {"firms":{"status":"ready" if os.environ.get("FIRMS_API_KEY") else "configuration_required","last_run":None,"records":await db.anomalies.count_documents({})},"osm":{"status":"demo_context","last_run":None,"records":await db.facilities.count_documents({})},"satellite":{"status":"unavailable","message":"Configure a public imagery provider to enable retrieval"},"land_cover":{"status":"unavailable","message":"Configure a public raster/data path to enable land-cover evidence"},"data_mode":"DEMO DATA"}

@api.post("/ingestion/firms")
async def ingest_firms(region: str="all-india", days: int=1):
    key=os.environ.get("FIRMS_API_KEY")
    if not key: raise HTTPException(503,"FIRMS_API_KEY is not configured; demo data remains available.")
    if requests is None: raise HTTPException(503,"Requests dependency unavailable")
    bbox=REGIONS.get(region,REGIONS["all-india"])["bbox"]
    url=f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{','.join(map(str,bbox))}/{max(1,min(days,10))}"
    try:
        response=requests.get(url,timeout=30); response.raise_for_status()
        rows=list(csv.DictReader(io.StringIO(response.text))); valid=[]
        for row in rows:
            try:
                lat,lon=float(row["latitude"]),float(row["longitude"])
                if not in_bbox(lat,lon,bbox): continue
                valid.append({"id":"firms-"+str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(row,sort_keys=True))),"latitude":lat,"longitude":lon,"acquisition_datetime":row.get("acq_date","")+"T"+row.get("acq_time","0000").zfill(4)+"00+00:00","satellite":row.get("satellite"),"instrument":row.get("instrument"),"confidence":float(row.get("confidence",0) or 0),"frp":float(row.get("frp",0) or 0),"daynight":row.get("daynight"),"source":"NASA FIRMS","is_demo":False})
            except (ValueError,KeyError): continue
        if valid: await db.anomalies.insert_many(valid,ordered=False)
        return {"status":"complete","inserted":len(valid),"source":"NASA FIRMS","region":REGIONS.get(region,REGIONS["all-india"])["label"]}
    except Exception as exc:
        logger.exception("FIRMS ingestion failed")
        raise HTTPException(502,f"FIRMS ingestion unavailable: {exc}")

@api.post("/analyst")
async def analyst(req: AnalystRequest):
    key=os.environ.get("EMERGENT_LLM_KEY")
    if not key: raise HTTPException(503,"Analyst unavailable: EMERGENT_LLM_KEY is not configured.")
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, ToolCallReady, StreamDone
    docs=(await anomalies(req.region,limit=100))["items"]
    context=json.dumps([{k:d.get(k) for k in ["id","predicted_class","prediction_confidence","priority_score","anomaly_status","frp","latitude","longitude","nearest_facility","persistence_score","detections_30d"]} for d in docs])
    chat=LlmChat(api_key=key,session_id="thermointel-"+str(uuid.uuid4()),system_message="You are ThermoIntel Analyst. Answer only from the supplied structured data. Never invent observations. Clearly distinguish detection, predicted classification, anomaly status, and system priority score. Mention DEMO DATA when present. Be concise and operational.").with_model("openai","gpt-5.4")
    answer=[]
    async for ev in chat.stream_message(UserMessage(text=f"User question: {req.question}\nRegion: {REGIONS.get(req.region,REGIONS['all-india'])['label']}\nStructured ThermoIntel data: {context}")):
        if isinstance(ev,TextDelta): answer.append(ev.content)
        if isinstance(ev,StreamDone): break
    return {"answer":"".join(answer),"data_mode":"DEMO DATA","scope":REGIONS.get(req.region,REGIONS["all-india"])["label"]}

app.include_router(api)
app.add_middleware(CORSMiddleware,allow_credentials=True,allow_origins=os.environ.get("CORS_ORIGINS","*").split(","),allow_methods=["*"],allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown():
    client.close()