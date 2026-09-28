"""Backfill State/LGD + LULC onto already-persisted production data.

Purpose: production runs executed before the packaged reference data existed
left `state: null` on every detection/event (0/618). This script repairs the
persisted documents in place with the SAME Phase 3 methodology the live
pipeline uses (live_enrichment.get_live_enricher) - no new logic, no
fabrication: fields that cannot be enriched stay None.

Idempotent: only documents with a null `state` (detections) / null `state`
(events) are processed; re-running is a no-op. Detection->event grouping is
respected by recomputing events from their own detection_ids afterwards.

Run from the backend directory:
    python scripts/backfill_enrichment.py [--limit N] [--dry-run]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import Collections, close_db, ensure_indexes, get_db  # noqa: E402
from pipeline import live_enrichment  # noqa: E402

BATCH = 500


def _detection_coords(doc: dict) -> tuple[float, float] | None:
    coords = ((doc.get("location") or {}).get("coordinates")) or []
    if len(coords) < 2:
        return None
    return float(coords[1]), float(coords[0])  # (lat, lon)


async def _backfill_detections(limit: int | None, dry: bool) -> int:
    db = get_db()
    query = {"data_origin": "production", "state": None}
    cursor = db[Collections.THERMAL_DETECTIONS].find(query)
    if limit:
        cursor = cursor.limit(limit)

    enricher = live_enrichment.get_live_enricher()
    repaired = 0
    batch: list[dict] = []

    async def _flush(batch: list[dict]) -> int:
        if not batch:
            return 0
        lats = [b["lat"] for b in batch]
        lons = [b["lon"] for b in batch]
        results = await asyncio.to_thread(enricher.enrich_batch, lats, lons)
        n = 0
        for doc, rec in zip(batch, results):
            if not rec.get("state"):
                continue  # outside India states polygon: stays None, truthful
            updates = {
                "state": rec["state"],
                "state_lgd": rec.get("state_lgd"),
            }
            if rec.get("lulc_2021_code") and not doc.get("lulc_2021_code"):
                updates["lulc_2021_code"] = rec["lulc_2021_code"]
                updates["lulc_2021_class"] = rec.get("lulc_2021_class")
            if not dry:
                await db[Collections.THERMAL_DETECTIONS].update_one(
                    {"_id": doc["_id"]}, {"$set": updates}
                )
            n += 1
        return n

    async for doc in cursor:
        coords = _detection_coords(doc)
        if coords is None:
            continue
        batch.append({"_id": doc["_id"], "lat": coords[0], "lon": coords[1], "doc": doc})
        if len(batch) >= BATCH:
            repaired += await _flush(batch)
            batch = []
            print(f"  detections processed so far: {repaired} repaired", flush=True)
    repaired += await _flush(batch)
    return repaired


async def _recompute_events_from_detections(limit: int | None, dry: bool) -> int:
    """Propagate detection state onto events whose state is still null."""
    db = get_db()
    query = {"data_origin": "production", "state": None}
    cursor = db[Collections.EVENTS].find(query)
    if limit:
        cursor = cursor.limit(limit)

    fixed = 0
    async for event in cursor:
        detection_ids = event.get("detection_ids") or []
        if not detection_ids:
            continue
        detection = await db[Collections.THERMAL_DETECTIONS].find_one(
            {"observation_id": detection_ids[0], "state": {"$ne": None}},
            {"state": 1, "state_lgd": 1},
        )
        if detection is None:
            continue
        if not dry:
            await db[Collections.EVENTS].update_one(
                {"_id": event["_id"]},
                {"$set": {
                    "state": detection["state"],
                    "state_lgd": detection.get("state_lgd"),
                }},
            )
        fixed += 1
    return fixed


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="process at most N null-state documents per collection")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args()

    await ensure_indexes()

    print("Backfilling production detections (state/LGD/LULC) ...", flush=True)
    det = await _backfill_detections(args.limit, args.dry_run)
    print(f"detections repaired: {det}")

    print("Propagating state onto production events ...", flush=True)
    ev = await _recompute_events_from_detections(args.limit, args.dry_run)
    print(f"events repaired: {ev}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
