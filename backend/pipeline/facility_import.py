"""Phase 3 standardized facility import.

The Phase 3 standardized facility dataset is the canonical production
facility source (FROZEN DECISION). This module loads it into the MongoDB
``facilities`` collection using the EXISTING v2 ``Facility`` schema.

Runtime architecture (frozen):

    Phase 3 standardized facility dataset
      -> MongoDB facilities
      -> services.registry_service.nearest_facility()
      -> nearest_facility_km / nearest_facility_type
      -> Phase 4 frozen ML feature vector

Rules enforced here:
  - Records conform to the existing v2 ``Facility`` schema. No parallel
    facility schema is created.
  - Demo facilities are never produced by this module.
  - No external (OSM or other) API is called; the standardized CSVs are the
    only source.
  - Dataset values are preserved verbatim. The Phase 3 ``facility_type``
    taxonomy is NOT one of the 13 frozen ``SourceType`` event-taxonomy values,
    so the schema's ``UNKNOWN_PERSISTENT_SOURCE`` member is used for the
    ``source_type`` field and the verbatim dataset value is preserved in
    ``attributes["facility_type"]`` (an existing schema field). No feature is
    renamed, added, removed, or reinterpreted.
  - Existing facility data is never deleted. Import is an idempotent upsert
    keyed on ``facility_id``.

Usage (manual operations step, not part of the request path):

    python -m pipeline.facility_import
"""

import asyncio
import csv
import time
from pathlib import Path
from typing import Optional

from pymongo import UpdateOne

from core.database import Collections, get_db
from models.common import GeoPoint
from models.enums import DataOrigin, SourceType
from models.facility import Facility
from pipeline.firms_ingestion import STANDARDIZED_DIR

# The eight Phase 3 standardized facility files (61,181 records, verified
# duplicate-free and coordinate-valid during the Phase 5 audit).
PHASE3_FACILITY_FILES = [
    "facilities_apad_other.csv",
    "facilities_brick_kilns_apad.csv",
    "facilities_brick_kilns_skdb.csv",
    "facilities_gas_flares.csv",
    "facilities_industrial.csv",
    "facilities_mining.csv",
    "facilities_osm.csv",
    "facilities_power_plants.csv",
]

# Dataset columns preserved verbatim in attributes (provenance / future
# context use). None of these alter the frozen ML feature schema.
_VERBATIM_ATTRIBUTE_FIELDS = (
    "facility_type",
    "subtype",
    "source",
    "status",
    "coord_flag",
    "is_thermal",
)

DATASET_VERSION = "phase3-standardized"


def _facility_from_row(row: dict[str, str]) -> Optional[Facility]:
    """Map one standardized CSV row onto the existing v2 Facility schema.

    Returns None for rows that cannot satisfy the schema (missing/invalid
    coordinates or facility_id). Nothing is fabricated for such rows; they
    are counted and skipped.
    """
    try:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None

    facility_id = (row.get("facility_id") or "").strip()
    if not facility_id:
        return None

    name = (row.get("name") or "").strip()
    state = (row.get("state_ut") or "").strip()
    dataset_source = (row.get("source") or "").strip()

    attributes = {
        key: value
        for key, value in row.items()
        if key in _VERBATIM_ATTRIBUTE_FIELDS and value != ""
    }

    return Facility(
        facility_id=facility_id,
        name=name or None,
        location=GeoPoint.from_lat_lon(latitude, longitude),
        state=state or None,
        # Frozen decision: no reinterpretation. The verbatim Phase 3
        # facility_type taxonomy is preserved in attributes["facility_type"].
        source_type=SourceType.UNKNOWN_PERSISTENT_SOURCE,
        dataset_source=dataset_source or None,
        dataset_version=DATASET_VERSION,
        verified=False,
        attributes=attributes,
        data_origin=DataOrigin.PRODUCTION,
    )


def load_phase3_facilities(limit: Optional[int] = None) -> tuple[list[Facility], int]:
    """Load Phase 3 standardized facility records.

    Returns (facilities, skipped_rows). ``limit`` exists solely for tests and
    operational dry-runs; production import loads every record.
    """
    facilities: list[Facility] = []
    skipped = 0
    remaining = limit

    for filename in PHASE3_FACILITY_FILES:
        path = Path(STANDARDIZED_DIR) / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Phase 3 standardized facility file missing: {path}"
            )

        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if remaining is not None and remaining <= 0:
                    return facilities, skipped
                facility = _facility_from_row(row)
                if facility is None:
                    skipped += 1
                    continue
                facilities.append(facility)
                if remaining is not None:
                    remaining -= 1

    return facilities, skipped


async def import_facilities(
    facilities: Optional[list[Facility]] = None,
    batch_size: int = 1000,
) -> dict:
    """Upsert Phase 3 facilities into MongoDB.

    Idempotent: re-running updates existing records by ``facility_id`` and
    inserts only new ones. Existing documents are never deleted (import must
    not destroy valid facility data to make an index pass).
    """
    skipped = 0
    if facilities is None:
        facilities, skipped = load_phase3_facilities()

    db = get_db()
    collection = db[Collections.FACILITIES]

    upserted = 0
    matched = 0
    modified = 0

    for start in range(0, len(facilities), batch_size):
        batch = facilities[start:start + batch_size]
        operations = []
        for facility in batch:
            document = facility.to_mongo()
            created_at = document.pop("created_at", None)
            operations.append(
                UpdateOne(
                    {"facility_id": facility.facility_id},
                    {
                        "$set": document,
                        "$setOnInsert": {"created_at": created_at},
                    },
                    upsert=True,
                )
            )

        result = await collection.bulk_write(operations, ordered=False)
        upserted += result.upserted_count
        matched += result.matched_count
        modified += result.modified_count

    return {
        "dataset_records": len(facilities),
        "skipped_invalid_rows": skipped,
        "upserted": upserted,
        "matched_updated": modified,
        "written": upserted + matched,
    }


async def import_facilities_resumable(batch_size: int = 5000) -> dict:
    """Resumable bulk import of Phase 3 facilities (operational fast path).

    Identical end state to ``import_facilities`` (same schema mapping, same
    ``dataset_version``, production origin, no demo data, no deletions), but
    safe to run while the ``facility_id`` unique index has not been built yet:

    - Records already imported (matching ``facility_id`` AND
      ``dataset_version="phase3-standardized"``) are skipped without a write.
      The mapping from the canonical frozen CSVs is deterministic, so a
      re-write would be a no-op; skipping is semantically identical and never
      duplicates or corrupts the existing records.
    - Everything else is written with ``insert_many`` (one bulk command per
      batch) instead of per-document upserts. Without an index on
      ``facility_id`` each upsert would trigger a collection scan, which is
      what made the original import too slow.

    Re-running this function after a complete import performs one read scan
    and zero writes.
    """
    started = time.monotonic()

    facilities, skipped = load_phase3_facilities()

    db = get_db()
    collection = db[Collections.FACILITIES]

    existing_ids = {
        doc["facility_id"]
        async for doc in collection.find(
            {"dataset_version": DATASET_VERSION},
            {"facility_id": 1},
        )
    }

    to_insert = [
        facility
        for facility in facilities
        if facility.facility_id not in existing_ids
    ]
    already_imported = len(facilities) - len(to_insert)

    inserted = 0
    for start in range(0, len(to_insert), batch_size):
        batch = to_insert[start:start + batch_size]
        await collection.insert_many(
            [facility.to_mongo() for facility in batch],
            ordered=False,
        )
        inserted += len(batch)

    duration_s = time.monotonic() - started
    return {
        "dataset_records": len(facilities),
        "skipped_invalid_rows": skipped,
        "already_imported": already_imported,
        "inserted": inserted,
        "duration_s": round(duration_s, 1),
        "records_per_second": (
            round(inserted / duration_s, 1) if duration_s > 0 else None
        ),
    }


async def facility_import_status() -> dict:
    """Composition of the facilities collection (for run/status reporting)."""
    db = get_db()
    collection = db[Collections.FACILITIES]
    return {
        "phase3_production": await collection.count_documents(
            {"data_origin": DataOrigin.PRODUCTION.value}
        ),
        "demo": await collection.count_documents(
            {"data_origin": DataOrigin.DEMO.value}
        ),
        "legacy_production": await collection.count_documents(
            {"data_origin": {"$exists": False}, "is_demo": {"$ne": True}}
        ),
    }


if __name__ == "__main__":

    async def _main() -> None:
        result = await import_facilities_resumable()
        status = await facility_import_status()
        print("IMPORT RESULT:", result)
        print("FACILITIES COLLECTION:", status)

    asyncio.run(_main())
