"""Task 2 read-only verification: exact production-data counts from MongoDB.

Read-only: only find/count/aggregate operations. Nothing is modified.

Verifies:
  - detections: total, with state, with LULC, by satellite, by data_origin
  - enrichment nulls: sample coordinates of state-null detections to judge
    whether nulls are legitimate (outside India polygons: ocean / other
    countries inside the FIRMS bbox) vs missing reference data
  - events: total, by status, by classification fields, by data_origin
  - alerts: total, eligibility consistency, duplicate-free alert_ids
  - pipeline runs: recent triggered_by values and statuses
  - demo contamination: any demo docs outside the demo dataset
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from core.database import Collections, close_db, get_db  # noqa: E402


async def main() -> None:
    db = get_db()

    print("=" * 72)
    print("DETECTIONS")
    total = await db[Collections.THERMAL_DETECTIONS].count_documents({})
    prod = await db[Collections.THERMAL_DETECTIONS].count_documents(
        {"data_origin": "production"}
    )
    demo = await db[Collections.THERMAL_DETECTIONS].count_documents(
        {"data_origin": "demo"}
    )
    no_origin = await db[Collections.THERMAL_DETECTIONS].count_documents(
        {"data_origin": {"$exists": False}}
    )
    with_state = await db[Collections.THERMAL_DETECTIONS].count_documents(
        {"state": {"$ne": None}}
    )
    with_lulc = await db[Collections.THERMAL_DETECTIONS].count_documents(
        {"lulc_2021_code": {"$ne": None}}
    )
    print(f"  total={total}  production={prod}  demo={demo}  no_origin={no_origin}")
    print(f"  with state={with_state} ({100*with_state/max(total,1):.1f}%)  "
          f"with LULC={with_lulc} ({100*with_lulc/max(total,1):.1f}%)")

    sats = await db[Collections.THERMAL_DETECTIONS].aggregate([
        {"$group": {"_id": "$satellite", "n": {"$sum": 1}}}
    ]).to_list(20)
    print(f"  by satellite: {[(s['_id'], s['n']) for s in sats]}")

    newest = await db[Collections.THERMAL_DETECTIONS].find_one(
        {}, sort=[("acquired_at", -1)]
    )
    print(f"  newest detection acquired_at: {newest and newest.get('acquired_at')}")

    print("  -- state-null sample coordinates (are they outside India?) --")
    nulls = await db[Collections.THERMAL_DETECTIONS].find(
        {"state": None},
        {"location.coordinates": 1, "_id": 0},
    ).limit(12).to_list(12)
    coords = [
        (d["location"]["coordinates"][0], d["location"]["coordinates"][1])
        for d in nulls
        if d.get("location", {}).get("coordinates")
    ]
    for lon, lat in coords:
        in_india_bbox_core = (
            68.1 <= lon <= 97.4 and 6.1 <= lat <= 37.4
        )
        # Rough land/sea heuristic vs India core: report raw numbers so the
        # reader can judge; India polygons are the authority, not this print.
        print(f"    lon={lon:.3f} lat={lat:.3f}")

    print("=" * 72)
    print("EVENTS")
    ev_total = await db[Collections.EVENTS].count_documents({})
    by_origin = await db[Collections.EVENTS].aggregate([
        {"$group": {"_id": "$data_origin", "n": {"$sum": 1}}}
    ]).to_list(10)
    by_status = await db[Collections.EVENTS].aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1}}}
    ]).to_list(10)
    by_etype = await db[Collections.EVENTS].aggregate([
        {"$group": {"_id": "$classification.event_type", "n": {"$sum": 1}}}
    ]).to_list(10)
    by_stype = await db[Collections.EVENTS].aggregate([
        {"$group": {"_id": "$classification.source_type", "n": {"$sum": 1}}}
    ]).to_list(10)
    by_tlevel = await db[Collections.EVENTS].aggregate([
        {"$group": {"_id": "$threat.threat_level", "n": {"$sum": 1}}}
    ]).to_list(10)
    with_state_ev = await db[Collections.EVENTS].count_documents(
        {"state": {"$ne": None}}
    )
    with_model_ver = await db[Collections.EVENTS].count_documents(
        {"classification.model_version_id": {"$ne": None}}
    )
    no_class = await db[Collections.EVENTS].count_documents(
        {"classification": None}
    )
    no_threat = await db[Collections.EVENTS].count_documents({"threat": None})
    print(f"  total={ev_total}  by_origin={[(d['_id'], d['n']) for d in by_origin]}")
    print(f"  by_status={[(d['_id'], d['n']) for d in by_status]}")
    print(f"  with state={with_state_ev}/{ev_total}")
    print(f"  classification populated={ev_total - no_class}/{ev_total}  "
          f"model_version set={with_model_ver}")
    print(f"  event_type={[(d['_id'], d['n']) for d in by_etype]}")
    print(f"  source_type={[(d['_id'], d['n']) for d in by_stype]}")
    print(f"  threat populated={ev_total - no_threat}/{ev_total}  "
          f"levels={[(d['_id'], d['n']) for d in by_tlevel]}")

    # Expired events must never be re-ACTIVE-dup'd: unique event_id index.
    dup_ids = await db[Collections.EVENTS].aggregate([
        {"$group": {"_id": "$event_id", "n": {"$sum": 1}, "ids": {"$push": "$_id"}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$count": "dups"},
    ]).to_list(1)
    print(f"  duplicate event_id docs: {dup_ids}")

    print("=" * 72)
    print("ALERTS")
    al_total = await db[Collections.ALERTS].count_documents({})
    al_open = await db[Collections.ALERTS].count_documents({"status": "OPEN"})
    al_demo = await db[Collections.ALERTS].count_documents({"data_origin": "demo"})
    dup_alert = await db[Collections.ALERTS].aggregate([
        {"$group": {"_id": "$alert_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$count": "dups"},
    ]).to_list(1)
    print(f"  total={al_total}  open={al_open}  demo={al_demo}  dup_alert_ids={dup_alert}")
    if al_total:
        recent_alerts = await db[Collections.ALERTS].find(
            {}, {"alert_id": 1, "event_id": 1, "threat_level": 1, "_id": 0}
        ).limit(5).to_list(5)
        print(f"  sample: {recent_alerts}")

    print("=" * 72)
    print("INGESTION RUNS (last 5)")
    runs = await db[Collections.INGESTION_RUNS].find(
        {},
        {"run_id": 1, "status": 1, "triggered_by": 1,
         "detections_ingested": 1, "started_at": 1, "_id": 0},
    ).sort([("started_at", -1)]).limit(5).to_list(5)
    for r in runs:
        print(f"  {r.get('started_at')}  {r.get('run_id')}  {r.get('status')}  "
              f"by={r.get('triggered_by')}  det={r.get('detections_ingested')}")

    print("=" * 72)
    print("FACILITIES (context source)")
    fac_prod = await db[Collections.FACILITIES].count_documents(
        {"data_origin": "production"}
    )
    fac_legacy = await db[Collections.FACILITIES].count_documents(
        {"data_origin": {"$exists": False}, "is_demo": {"$ne": True}}
    )
    fac_demo = await db[Collections.FACILITIES].count_documents(
        {"data_origin": "demo"}
    )
    print(f"  production={fac_prod}  legacy(no data_origin)={fac_legacy}  demo={fac_demo}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
