"""
OSM industrial/power/works facility ingestion — Milestone 2.

Source of truth: ThermoIntel_ML_ETL_Colab_IndiaWide.ipynb (cell 8A, Overpass query).
Replaces the 4-point demo fixture with a real, India-wide facility dataset
that backend/services/feature_engineering.py uses for facility proximity.
"""
import logging
from datetime import datetime, timezone

from pymongo import UpdateOne

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger("thermointel.osm_facilities")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_HEADERS = {"User-Agent": "ThermoIntel/1.0 (research project)", "Referer": "https://www.openstreetmap.org/"}

# (tag_key, tag_value) — tag_value None means "key present, any value" (matches notebook's ["industrial"])
FACILITY_TAGS = [("industrial", None), ("power", "plant"), ("man_made", "works")]


def build_overpass_query(bbox) -> str:
    """Exact port of the notebook's OVERPASS_QUERY (cell 16), parameterized by bbox."""
    west, south, east, north = bbox
    box = f"{south},{west},{north},{east}"
    clauses = []
    for key, value in FACILITY_TAGS:
        selector = f'"{key}"="{value}"' if value else f'"{key}"'
        for kind in ("node", "way", "relation"):
            clauses.append(f'  {kind}[{selector}]({box});')
    return "[out:json][timeout:120];\n(\n" + "\n".join(clauses) + "\n);\nout center tags;"


def parse_overpass_response(payload: dict) -> list:
    """Exact port of the notebook's facility_rows extraction (cell 16)."""
    facilities = []
    seen = set()
    for el in payload.get("elements", []):
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        osm_id = f"{el.get('type', 'unknown')}/{el.get('id')}"
        if osm_id in seen:
            continue
        seen.add(osm_id)
        tags = el.get("tags", {})
        facilities.append({
            "osm_id": osm_id,
            "latitude": float(lat),
            "longitude": float(lon),
            "name": tags.get("name"),
            "facility_type": tags.get("industrial") or tags.get("power") or tags.get("man_made") or "industrial",
            "tags": {k: v for k, v in tags.items() if k in ("industrial", "power", "man_made", "name")},
            "source": "OpenStreetMap",
        })
    return facilities


def fetch_facilities(bbox, timeout: int = 180) -> list:
    if requests is None:
        raise RuntimeError("requests dependency unavailable")
    query = build_overpass_query(bbox)
    response = requests.post(OVERPASS_URL, data={"data": query}, headers=OVERPASS_HEADERS, timeout=timeout)
    response.raise_for_status()
    return parse_overpass_response(response.json())


async def store_facilities(db, facilities: list) -> int:
    if not facilities:
        return 0
    operations = []
    for f in facilities:
        doc = {
            **f,
            "geometry": {"type": "Point", "coordinates": [f["longitude"], f["latitude"]]},
            "is_demo": False,
            "ingested_at": datetime.now(timezone.utc),
        }
        operations.append(UpdateOne({"osm_id": f["osm_id"]}, {"$set": doc}, upsert=True))
    result = await db.facilities.bulk_write(operations, ordered=False)
    return result.upserted_count + result.modified_count


async def run_osm_ingestion(db, bbox) -> dict:
    facilities = fetch_facilities(bbox)
    stored = await store_facilities(db, facilities)
    return {"status": "complete", "source": "OpenStreetMap · Overpass", "fetched": len(facilities), "stored_or_updated": stored}
