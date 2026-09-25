"""Focused Phase 5 tests: Phase 3 facility import, Facility schema
compatibility, geospatial indexes, nearest-facility lookup and explicit
missing-context behavior.

These tests run against the project's MongoDB server but an ISOLATED test
database (thermointel_facility_test) which is dropped afterwards, so neither
the operational database nor the demo dataset is touched. Facility data is
produced either from a synthetic in-process "Phase 3 style" CSV set (no
external API is ever called) or from explicit Facility model instances.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from core.database import Collections, close_db, ensure_indexes, get_db  # noqa: E402
from models.common import GeoPoint  # noqa: E402
from models.enums import DataOrigin, SourceType  # noqa: E402
from models.facility import Facility  # noqa: E402
from pipeline import facility_import  # noqa: E402
from services import registry_service  # noqa: E402

TEST_DB_NAME = "thermointel_facility_test"

_LOOP = None


def run(coro):
    """Run a coroutine on one module-lifetime event loop.

    Motor clients bind to the loop they first run on, so all async work in
    this module shares a single loop instead of one asyncio.run() per call.
    """
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    return _LOOP.run_until_complete(coro)


_CSV_HEADER = (
    "facility_id,name,facility_type,subtype,is_thermal,latitude,longitude,"
    "state_ut,state_lgd,source,status,coord_flag"
)


def _csv_row(**kwargs) -> str:
    values = {key: "" for key in _CSV_HEADER.split(",")}
    values.update(kwargs)
    return ",".join(values[key] for key in _CSV_HEADER.split(","))


_MAIN_ROWS = [
    _csv_row(
        facility_id="PH3-0001", name="Audit Cement Works",
        facility_type="Cement / Kiln", subtype="cement", is_thermal="True",
        latitude="21.5000", longitude="84.0300", state_ut="Odisha",
        source="Climate TRACE v6 (via open composite)",
    ),
    _csv_row(
        facility_id="PH3-0002", name="Audit Brick Kiln",
        facility_type="Brick Kiln", subtype="FCBK (Fixed Chimney Bull's Trench)",
        is_thermal="True", latitude="28.6100", longitude="77.2100",
        state_ut="Delhi", source="APAD IGP Asset Data (AWS Open Data)",
    ),
    _csv_row(
        facility_id="PH3-0003", name="Audit Gas Flare",
        facility_type="Gas Flare", subtype="gas processing / distribution flare",
        is_thermal="True", latitude="27.432784", longitude="94.981748",
        state_ut="Assam", source="EOG Global Gas Flare Catalog (Colorado School of Mines)",
    ),
]


@pytest.fixture(scope="module", autouse=True)
def facility_test_db():
    """Point the database layer at an isolated test DB for this module."""
    original_db_name = settings.DB_NAME
    settings.DB_NAME = TEST_DB_NAME
    run(ensure_indexes())
    run(get_db()[Collections.FACILITIES].delete_many({}))
    yield
    run(get_db().client.drop_database(TEST_DB_NAME))
    run(close_db())
    if _LOOP is not None and not _LOOP.is_closed():
        _LOOP.close()
    settings.DB_NAME = original_db_name


@pytest.fixture(scope="module")
def phase3_dir(tmp_path_factory):
    """Synthetic Phase 3 standardized directory (all 8 files, 3 records)."""
    base = tmp_path_factory.mktemp("phase3_standardized")
    for filename in facility_import.PHASE3_FACILITY_FILES:
        rows = _MAIN_ROWS if filename == "facilities_industrial.csv" else []
        (base / filename).write_text(
            _CSV_HEADER + "\n" + "\n".join(rows) + ("\n" if rows else ""),
            encoding="utf-8",
        )
    return base


# ---------------------------------------------------------------- schema ---


def test_facility_row_maps_to_existing_schema(phase3_dir, monkeypatch):
    monkeypatch.setattr(facility_import, "STANDARDIZED_DIR", str(phase3_dir))
    facilities, skipped = facility_import.load_phase3_facilities()

    assert skipped == 0
    assert len(facilities) == 3

    facility = facilities[0]
    assert isinstance(facility, Facility)
    assert facility.facility_id == "PH3-0001"
    assert facility.name == "Audit Cement Works"
    # GeoJSON point: [longitude, latitude]
    assert facility.location.coordinates == [84.03, 21.5]
    assert facility.state == "Odisha"
    # Verbatim Phase 3 taxonomy preserved; no reinterpretation into a
    # different vocabulary and no parallel schema field.
    assert facility.attributes["facility_type"] == "Cement / Kiln"
    assert facility.source_type == SourceType.UNKNOWN_PERSISTENT_SOURCE
    assert facility.dataset_version == facility_import.DATASET_VERSION
    assert facility.verified is False
    assert facility.data_origin == DataOrigin.PRODUCTION


def test_invalid_rows_are_skipped_not_fabricated():
    load = facility_import._facility_from_row
    assert load({"facility_id": "X", "latitude": "abc", "longitude": "1"}) is None
    assert load({"facility_id": "X", "latitude": "999", "longitude": "1"}) is None
    assert load({"facility_id": "X", "latitude": "21.5", "longitude": "999"}) is None
    assert load({"facility_id": "", "latitude": "21.5", "longitude": "84.0"}) is None
    assert load({"latitude": "21.5", "longitude": "84.0"}) is None


# ---------------------------------------------------------------- import ---


def test_import_upserts_idempotent_and_production_only(phase3_dir, monkeypatch):
    monkeypatch.setattr(facility_import, "STANDARDIZED_DIR", str(phase3_dir))
    facilities, _ = facility_import.load_phase3_facilities()

    first = run(facility_import.import_facilities(facilities))
    assert first["upserted"] == 3

    collection = get_db()[Collections.FACILITIES]
    assert run(collection.count_documents({})) == 3
    assert run(
        collection.count_documents({"data_origin": DataOrigin.DEMO.value})
    ) == 0

    # Idempotent re-import: nothing inserted twice, nothing duplicated.
    second = run(facility_import.import_facilities(facilities))
    assert second["upserted"] == 0
    assert second["written"] == 3
    assert run(collection.count_documents({})) == 3

    docs = run(collection.find({}).to_list(length=10))
    assert all(doc["data_origin"] == DataOrigin.PRODUCTION.value for doc in docs)
    assert all("location" in doc and doc["location"]["type"] == "Point" for doc in docs)


# ---------------------------------------------------------------- indexes ---


def test_facilities_2dsphere_index_exists():
    info = run(get_db()[Collections.FACILITIES].index_information())
    keys = [tuple(spec["key"][0]) for spec in info.values()]
    assert ("location", "2dsphere") in keys


def test_facility_id_unique_index_is_partial():
    info = run(get_db()[Collections.FACILITIES].index_information())
    spec = next(
        spec for spec in info.values()
        if spec["key"] == [("facility_id", 1)]
    )
    assert spec.get("unique") is True
    assert spec.get("partialFilterExpression") == {"facility_id": {"$exists": True}}


def test_legacy_osm_documents_do_not_break_unique_index():
    """Legacy OSM docs (osm_id only, no facility_id) must coexist with the
    partial unique index instead of aborting its build."""
    collection = get_db()[Collections.FACILITIES]
    run(collection.delete_many({}))
    legacy = {
        "osm_id": "node/1",
        "facility_type": "works",
        "geometry": {"type": "Point", "coordinates": [76.74, 11.37]},
        "location": {"type": "Point", "coordinates": [76.74, 11.37]},
        "name": "Legacy Works",
        "is_demo": False,
    }
    run(collection.insert_one(legacy))
    production = Facility(
        facility_id="PH3-LEG-1",
        location=GeoPoint.from_lat_lon(11.38, 76.75),
    )
    run(collection.insert_one(production.to_mongo()))
    # Two documents, only one carrying facility_id: index must hold.
    assert run(collection.count_documents({})) == 2
    run(collection.delete_many({}))


# ----------------------------------------------------------------- lookup ---


def _insert_facilities(facilities: list[Facility]) -> None:
    run(get_db()[Collections.FACILITIES].insert_many(
        [f.to_mongo() for f in facilities]
    ))


def test_nearest_facility_found_with_distance_and_type():
    collection = get_db()[Collections.FACILITIES]
    run(collection.delete_many({}))
    _insert_facilities([
        Facility(
            facility_id="N-1", name="Nearest Plant",
            location=GeoPoint.from_lat_lon(28.61, 77.21),
            attributes={"facility_type": "Power Plant"},
        ),
        Facility(
            facility_id="N-2", name="Far Plant",
            location=GeoPoint.from_lat_lon(21.5, 84.03),
            attributes={"facility_type": "Cement / Kiln"},
        ),
    ])

    context = run(registry_service.nearest_facility(28.61, 77.22))

    assert context is not None
    assert context["facility_id"] == "N-1"
    # ~0.01 degrees of longitude at this latitude: well under 2 km.
    assert 0.3 < context["nearest_facility_km"] < 2.0
    assert context["nearest_facility_type"] == "Power Plant"


def test_nearest_facility_excludes_demo_documents():
    collection = get_db()[Collections.FACILITIES]
    run(collection.delete_many({}))
    _insert_facilities([
        # Demo facility sits exactly on the query point (distance ~0) but
        # must never be returned.
        Facility(
            facility_id="DEMO-1", name="Demo Kiln",
            location=GeoPoint.from_lat_lon(28.61, 77.22),
            attributes={"facility_type": "Brick Kiln"},
            data_origin=DataOrigin.DEMO,
        ),
        Facility(
            facility_id="N-1", name="Production Plant",
            location=GeoPoint.from_lat_lon(28.61, 77.21),
            attributes={"facility_type": "Power Plant"},
        ),
    ])

    context = run(registry_service.nearest_facility(28.61, 77.22))

    assert context is not None
    assert context["facility_id"] == "N-1"


def test_nearest_facility_includes_legacy_osm_documents():
    """Legacy OSM docs are production provenance (never demo) and must be
    used; the schema has no osm_id field, so facility_id comes back None."""
    collection = get_db()[Collections.FACILITIES]
    run(collection.delete_many({}))
    run(collection.insert_one({
        "osm_id": "node/42",
        "location": {"type": "Point", "coordinates": [77.21, 28.61]},
        "name": "Legacy Works",
        "is_demo": False,
    }))

    context = run(registry_service.nearest_facility(28.61, 77.22))

    assert context is not None
    assert context["facility_id"] is None
    assert context["nearest_facility_km"] < 2.0


def test_nearest_facility_missing_context_empty_collection():
    collection = get_db()[Collections.FACILITIES]
    run(collection.delete_many({}))

    # Explicit missing context: no facility, distance, or type fabricated.
    assert run(registry_service.nearest_facility(28.61, 77.22)) is None


def test_nearest_facility_missing_context_only_demo_data():
    collection = get_db()[Collections.FACILITIES]
    run(collection.delete_many({}))
    _insert_facilities([
        Facility(
            facility_id="DEMO-1", name="Demo Kiln",
            location=GeoPoint.from_lat_lon(28.61, 77.22),
            data_origin=DataOrigin.DEMO,
        ),
    ])

    assert run(registry_service.nearest_facility(28.61, 77.22)) is None


# ----------------------------------------------------------------- status ---


def test_facility_context_status_counts():
    collection = get_db()[Collections.FACILITIES]
    run(collection.delete_many({}))
    _insert_facilities([
        Facility(facility_id="S-1", location=GeoPoint.from_lat_lon(21.5, 84.03)),
        Facility(facility_id="S-2", location=GeoPoint.from_lat_lon(28.61, 77.21)),
        Facility(
            facility_id="S-3", location=GeoPoint.from_lat_lon(27.43, 94.98),
            data_origin=DataOrigin.DEMO,
        ),
    ])
    run(collection.insert_one({
        "osm_id": "node/7",
        "location": {"type": "Point", "coordinates": [76.74, 11.37]},
        "is_demo": False,
    }))

    status = run(registry_service.facility_context_status())

    assert status["imported"] == 2
    assert status["demo"] == 1
    assert status["legacy"] == 1
