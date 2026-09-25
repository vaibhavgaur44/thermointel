import asyncio

from core.database import get_db, Collections
from models.event import Event
from pipeline.feature_engineering import build_features
from pipeline.ml_inference import classify_sync


async def main():
    db = get_db()

    detection = await db[Collections.THERMAL_DETECTIONS].find_one(
        {"data_origin": "production"}
    )

    event_doc = await db[Collections.EVENTS].find_one(
        {"event_id": detection["event_id"]}
    )

    print("DETECTION FOUND:", detection["observation_id"])
    print("EVENT FOUND:", event_doc is not None)

    event = Event(**event_doc)

    features = build_features(
        event,
        detection,
        {},
    )

    print("RAW FEATURES:", len(features))
    print("CONFIDENCE:", features["confidence"])
    print("CONFIDENCE_NUM:", features["confidence_num"])

    result = classify_sync(event, features)

    print("CLASSIFICATION:", result)


asyncio.run(main())