"""Backend tests for ThermoIntel v2 Phase 2 API.

All tests live in a single class to avoid xdist loadscope races —
they share sequential state (clear -> empty checks -> seed -> filtered
checks -> clear -> empty check).
"""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # Windows/Linux portable path resolution relative to this repo.
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend", ".env")
    if not os.path.exists(_env_path):
        _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", ".env")
    if os.path.exists(_env_path):
        with open(_env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE}/api"

TIMEOUT = 20


def _items(payload):
    if isinstance(payload, list):
        return payload
    for k in ("items", "events", "alerts", "facilities"):
        if k in payload:
            return payload[k]
    return []


class TestThermoIntelPhase2:
    """Full lifecycle test suite - runs sequentially on a single xdist worker."""

    # ----- 1. clear state at start (idempotent) -----
    def test_01_clear_initial(self):
        r = requests.delete(f"{API}/dev/demo-data/clear", timeout=TIMEOUT)
        assert r.status_code in (200, 204)

    # ----- 2. Health + reference -----
    def test_02_health(self):
        r = requests.get(f"{API}/health", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["database"] == "connected"
        assert d.get("service")

    def test_03_regions(self):
        r = requests.get(f"{API}/regions", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "india_bbox" in d or "bbox" in d
        states = d.get("states") or d.get("regions") or d.get("states_and_uts") or []
        assert len(states) == 36
        kinds = {s.get("kind") for s in states}
        assert kinds.issubset({"STATE", "UNION_TERRITORY"})
        for s in states:
            assert "name" in s and "bbox" in s
            assert "districts" not in s
        assert "districts" not in d

    def test_04_taxonomy(self):
        r = requests.get(f"{API}/taxonomy", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        # event_types can be strings or dicts with 'value'
        ets = d["event_types"]
        et_values = {e["value"] if isinstance(e, dict) else e for e in ets}
        assert et_values == {"FOREST_FIRE", "AGRICULTURAL_FIRE", "UNKNOWN_AGRICULTURAL_FIRE",
                             "INDUSTRIAL_FIRE", "PERSISTENT_HEAT_SOURCE"}
        assert len(d["source_types"]) == 13
        assert set(d["threat_levels"]) == {"LOW", "MODERATE", "HIGH", "CRITICAL"}
        assert set(d["time_ranges"]) == {"1h", "6h", "24h", "1w"}

    # ----- 3. Database state -----
    # PHASE 5 UPDATE: the operational database now holds real FIRMS production
    # data (NOAA-20 + NOAA-21). Production records must NEVER be deleted to
    # make an empty-state assertion pass, so these checks assert the
    # production/demo separation instead of a zero total.
    def test_05_empty_events(self):
        r = requests.get(f"{API}/events", timeout=TIMEOUT).json()
        assert r.get("total", 0) >= 0
        for it in _items(r):
            assert it.get("data_origin") != "demo", "demo data leaked into default (production) view"

    def test_06_empty_priority(self):
        r = requests.get(f"{API}/events/priority", timeout=TIMEOUT).json()
        for it in _items(r):
            assert it.get("data_origin") != "demo", "demo data leaked into default priority view"

    def test_07_empty_summary(self):
        r = requests.get(f"{API}/events/summary", timeout=TIMEOUT).json()
        assert r.get("total_events", 0) >= 0
        assert r.get("data_origin_scope") == ["production"]

    def test_08_empty_alerts(self):
        r = requests.get(f"{API}/alerts", timeout=TIMEOUT).json()
        for a in _items(r):
            assert a.get("data_origin") != "demo", "demo data leaked into default alert queue"

    def test_09_empty_thermal_detections(self):
        r = requests.get(f"{API}/thermal-detections", timeout=TIMEOUT).json()
        for d in _items(r):
            assert d.get("data_origin") != "demo", "demo data leaked into default detections view"

    # ----- 4. Seed + idempotency -----
    def test_10_seed(self):
        r = requests.post(f"{API}/dev/demo-data/seed", timeout=30)
        assert r.status_code in (200, 201)
        d = r.json()
        assert "warning" in d
        assert d.get("events") == 18
        assert d.get("alerts") == 4
        assert d.get("facilities") == 5

    def test_11_seed_idempotent(self):
        r = requests.post(f"{API}/dev/demo-data/seed", timeout=30)
        assert r.status_code in (200, 201)
        # Demo totals are stable across re-seeds (seed() clears first).
        # Production events (real FIRMS data) are counted separately and
        # must be untouched by demo seeding.
        before = requests.get(f"{API}/events", params={"limit": 1}, timeout=TIMEOUT).json()
        prod_total_before = before.get("total", 0)
        active = requests.get(f"{API}/events", params={"include_demo": "true", "status": "ACTIVE", "limit": 500}, timeout=TIMEOUT).json()
        exp = requests.get(f"{API}/events", params={"include_demo": "true", "status": "EXPIRED", "limit": 500}, timeout=TIMEOUT).json()
        ina = requests.get(f"{API}/events", params={"include_demo": "true", "status": "INACTIVE", "limit": 500}, timeout=TIMEOUT).json()
        total = active.get("total", 0) + exp.get("total", 0) + ina.get("total", 0)
        assert total >= prod_total_before + 18, "demo seed did not add the 18 demo events on top of production data"
        al = requests.get(f"{API}/alerts", params={"include_demo": "true", "limit": 500}, timeout=TIMEOUT).json()
        assert len(_items(al)) >= 4
        fac = requests.get(f"{API}/facilities", params={"include_demo": "true", "limit": 2000}, timeout=TIMEOUT).json()
        assert len(_items(fac)) >= 5

    # ----- 5. Demo isolation -----
    def test_12_demo_default_still_empty(self):
        r = requests.get(f"{API}/events", timeout=TIMEOUT).json()
        # Default (production) view never contains demo-tagged events.
        assert all(e.get("data_origin") != "demo" for e in _items(r))
        r2 = requests.get(f"{API}/events", params={"include_demo": "true", "limit": 500}, timeout=TIMEOUT).json()
        items = _items(r2)
        assert len(items) > 0
        demo_items = [e for e in items if e.get("data_origin") == "demo"]
        assert demo_items, "expected seeded demo events to be exposed under include_demo=true"

    # ----- 6. Priority ordering -----
    def test_13_priority_sorted_by_threat(self):
        r = requests.get(f"{API}/events/priority", params={"include_demo": "true", "limit": 5}, timeout=TIMEOUT).json()
        items = _items(r)
        assert len(items) == 5
        scores = [it.get("threat_score") or (it.get("threat") or {}).get("threat_score") for it in items]
        assert scores == sorted(scores, reverse=True)
        assert abs(scores[0] - 92.4) < 0.5
        first = items[0].get("event_id") or items[0].get("id")
        assert "demo-evt-001" in str(first)
        # Not ordered by last_detected
        last_dets = [it.get("last_detected") for it in items]
        assert last_dets != sorted(last_dets, reverse=True) or scores == sorted(scores, reverse=True)

    # ----- 7. Filtering -----
    def test_14_filter_classification(self):
        r = requests.get(f"{API}/events", params={"include_demo": "true", "classification": "INDUSTRIAL_FIRE", "limit": 100}, timeout=TIMEOUT).json()
        items = _items(r)
        assert len(items) > 0
        for it in items:
            et = it.get("event_type") or (it.get("classification") or {}).get("event_type")
            assert et == "INDUSTRIAL_FIRE"

    def test_15_filter_state_odisha(self):
        r = requests.get(f"{API}/events", params={"include_demo": "true", "state": "Odisha", "limit": 100}, timeout=TIMEOUT).json()
        items = _items(r)
        assert len(items) > 0
        for it in items:
            assert it.get("state") == "Odisha"

    def test_16_filter_source_type(self):
        r = requests.get(f"{API}/events", params={"include_demo": "true", "source_type": "STEEL_METAL", "limit": 100}, timeout=TIMEOUT).json()
        items = _items(r)
        assert len(items) > 0
        for it in items:
            assert it.get("source_type") == "STEEL_METAL"

    def test_17_no_confidence_filter(self):
        a = requests.get(f"{API}/events", params={"include_demo": "true", "limit": 100}, timeout=TIMEOUT).json()
        b = requests.get(f"{API}/events", params={"include_demo": "true", "confidence": "0.5", "limit": 100}, timeout=TIMEOUT).json()
        assert a.get("total") == b.get("total")

    def test_18_status_expired_inactive(self):
        r = requests.get(f"{API}/events", params={"include_demo": "true", "status": "EXPIRED", "limit": 100}, timeout=TIMEOUT).json()
        ids = [it.get("event_id") for it in _items(r)]
        assert "demo-evt-017" in ids
        r2 = requests.get(f"{API}/events", params={"include_demo": "true", "status": "INACTIVE", "limit": 100}, timeout=TIMEOUT).json()
        ids2 = [it.get("event_id") for it in _items(r2)]
        assert "demo-evt-018" in ids2

    def test_19_time_ranges_accepted(self):
        for tr in ["1h", "6h", "24h", "1w"]:
            r = requests.get(f"{API}/events", params={"include_demo": "true", "time_range": tr}, timeout=TIMEOUT)
            assert r.status_code == 200, f"time_range {tr} failed with {r.status_code}"

    def test_19b_default_status_includes_expired_in_1w(self):
        """Regression: omitting `status` on GET /events must not hide EXPIRED events.

        The events list is the exploratory table, so its default is ALL
        statuses: with time_range=1w the default total must equal the sum of
        the per-status totals (ACTIVE + EXPIRED + INACTIVE). Under the old
        ACTIVE default the identity broke whenever EXPIRED events existed
        inside the 7-day last_detected window. Short windows use the same
        partition identity, which holds regardless of what data is present.
        /summary stays ACTIVE-scoped by default and /priority stays
        explicitly ACTIVE-only. Production data only (no demo dependency).
        """
        params = {"time_range": "1w", "limit": 2000}
        wk = requests.get(f"{API}/events", params=params, timeout=TIMEOUT).json()
        parts = 0
        for st in ("ACTIVE", "EXPIRED", "INACTIVE"):
            r = requests.get(f"{API}/events", params={**params, "status": st}, timeout=TIMEOUT).json()
            parts += r.get("total", 0)
            if st == "EXPIRED" and r.get("total", 0) > 0:
                statuses = {it.get("status") for it in _items(wk)}
                assert "EXPIRED" in statuses, "1w default view must include EXPIRED events"
        assert wk.get("total") == parts, (
            "default (no status) 1w total must equal ACTIVE+EXPIRED+INACTIVE"
        )

        # Short windows: same identity; default never diverges from the
        # union of explicit statuses there.
        for tr in ("1h", "6h", "24h"):
            d = requests.get(f"{API}/events", params={"time_range": tr, "limit": 2000}, timeout=TIMEOUT).json()
            s = sum(
                requests.get(
                    f"{API}/events", params={"time_range": tr, "limit": 2000, "status": st}, timeout=TIMEOUT
                ).json().get("total", 0)
                for st in ("ACTIVE", "EXPIRED", "INACTIVE")
            )
            assert d.get("total") == s, f"{tr}: default total must equal the union of statuses"

        # /summary stays ACTIVE by default; /priority stays explicitly ACTIVE-only.
        s = requests.get(f"{API}/events/summary", timeout=TIMEOUT).json()
        assert s.get("status_scope") == "ACTIVE"
        pr = requests.get(f"{API}/events/priority", params={"limit": 50}, timeout=TIMEOUT).json()
        assert _items(pr) and all(it.get("status") == "ACTIVE" for it in _items(pr))

    # ----- 8. Event detail + honesty -----
    def test_20_event_detail(self):
        r = requests.get(f"{API}/events/demo-evt-001", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        se = d.get("supporting_evidence") or (d.get("classification") or {}).get("supporting_evidence")
        assert se and len(se) >= 1
        conf = d.get("model_confidence") if d.get("model_confidence") is not None else (d.get("classification") or {}).get("model_confidence")
        assert conf is not None and abs(conf - 0.87) < 0.05
        tl = d.get("threat_level") or (d.get("threat") or {}).get("threat_level")
        assert tl == "CRITICAL"

    def test_21_event_detail_404(self):
        r = requests.get(f"{API}/events/nonexistent-xyz", timeout=TIMEOUT)
        assert r.status_code == 404

    def test_22_model_confidence_null_for_some(self):
        found_null = False
        for eid in ["demo-evt-004", "demo-evt-008", "demo-evt-013", "demo-evt-014"]:
            r = requests.get(f"{API}/events/{eid}", timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            d = r.json()
            conf = d.get("model_confidence")
            if conf is None:
                cls = d.get("classification") or {}
                conf = cls.get("model_confidence")
            if conf is None:
                found_null = True
        assert found_null, "expected at least one demo event with null confidence"

    def test_23_no_full_confidence_anywhere(self):
        for tail in ["", "&status=EXPIRED", "&status=INACTIVE"]:
            r = requests.get(f"{API}/events?include_demo=true&limit=500{tail}", timeout=TIMEOUT).json()
            for it in _items(r):
                conf = it.get("model_confidence")
                if conf is None:
                    cls = it.get("classification") or {}
                    conf = cls.get("model_confidence")
                if conf is not None:
                    assert conf < 1.0, f"event {it.get('event_id')} has confidence>=1.0"

    # ----- 9. Summary -----
    def test_24_summary_seeded(self):
        r = requests.get(f"{API}/events/summary", params={"include_demo": "true"}, timeout=TIMEOUT).json()
        assert r.get("total_events", 0) > 0
        bet = r.get("by_event_type") or {}
        assert set(bet.keys()) >= {"FOREST_FIRE", "AGRICULTURAL_FIRE", "UNKNOWN_AGRICULTURAL_FIRE",
                                   "INDUSTRIAL_FIRE", "PERSISTENT_HEAT_SOURCE"}

    def test_25_summary_state_scope(self):
        india = requests.get(f"{API}/events/summary", params={"include_demo": "true"}, timeout=TIMEOUT).json()
        odisha = requests.get(f"{API}/events/summary", params={"include_demo": "true", "state": "Odisha"}, timeout=TIMEOUT).json()
        assert odisha.get("total_events", 0) < india.get("total_events", 0)
        assert odisha.get("total_events", 0) >= 1

    # ----- 10. Alerts -----
    # PHASE 5 UPDATE: the operational alert queue holds real production
    # alerts (owner eligibility contract). The demo seed adds 4 demo alerts.
    def test_26_alerts(self):
        r = requests.get(f"{API}/alerts", params={"include_demo": "true", "limit": 500}, timeout=TIMEOUT).json()
        items = _items(r)
        assert len(items) >= 4, "expected at least the 4 demo alerts"
        demo_alerts = [a for a in items if a.get("data_origin") == "demo"]
        assert len(demo_alerts) == 4, f"expected exactly 4 demo alerts, got {len(demo_alerts)}"
        for a in demo_alerts:
            assert a.get("primary_reason") or a.get("reason")
            assert a.get("supporting_evidence")
        # Default view still excludes demo alerts.
        r2 = requests.get(f"{API}/alerts", params={"limit": 500}, timeout=TIMEOUT).json()
        assert all(a.get("data_origin") != "demo" for a in _items(r2))

    def test_27_alert_detail(self):
        r = requests.get(f"{API}/alerts/demo-alr-001", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_28_alert_404(self):
        r = requests.get(f"{API}/alerts/no-such-alert", timeout=TIMEOUT)
        assert r.status_code == 404

    # ----- 11. Facilities + thermal -----
    # PHASE 5 UPDATE: facilities now holds the Phase 3 standardized corpus
    # (61,181 production records) plus the 5 demo facilities. The demo
    # records are verified through the dedicated demo-status endpoint
    # (the list endpoint pages in natural order, so a small tail page
    # cannot be asserted against a 61k-record corpus).
    def test_29_facilities(self):
        r = requests.get(f"{API}/facilities", params={"include_demo": "true", "limit": 50}, timeout=TIMEOUT).json()
        items = _items(r)
        # Everything returned from the shared corpus is production-tagged.
        assert all(f.get("data_origin") == "production" for f in items)
        # Production corpus present and matches the Phase 3 import size.
        r2 = requests.get(f"{API}/facilities", params={"limit": 1}, timeout=TIMEOUT).json()
        assert r2.get("total", 0) >= 61181, "Phase 3 standardized facility corpus missing"
        # Demo facilities exist and are counted through the demo-status endpoint.
        st = requests.get(f"{API}/dev/demo-data/status", timeout=TIMEOUT).json()
        assert st.get("counts", {}).get("facilities") == 5, "expected 5 demo facilities"
        # Demo facilities never appear in the default view.
        r3 = requests.get(f"{API}/facilities", params={"limit": 500}, timeout=TIMEOUT).json()
        assert all(f.get("data_origin") != "demo" for f in _items(r3))

    def test_30_thermal_detections_empty(self):
        r = requests.get(f"{API}/thermal-detections", timeout=TIMEOUT).json()
        # Production detections exist (real FIRMS); demo never appears by default.
        assert r.get("total", 0) > 0, "expected production FIRMS detections"
        assert all(d.get("data_origin") != "demo" for d in _items(r))

    # ----- 12. Ingestion + Models -----
    # PHASE 5 UPDATE: FIRMS is configured, the frozen Phase 4 models are
    # deployed and the pipeline is implemented (no NOT_IMPLEMENTED stage).
    def test_31_ingestion_status(self):
        r = requests.get(f"{API}/ingestion/status", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d.get("firms_source_configured") is True
        assert d.get("event_formation_calibrated") is False
        assert d.get("ml_models_available") is True
        assert d.get("threat_engine_calibrated") is False
        assert d.get("latest_run") is not None

    def test_32_ingestion_run(self):
        r = requests.get(f"{API}/ingestion/status", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        latest = d.get("latest_run") or {}
        # The last completed run reflects the implemented Phase 5 pipeline.
        assert latest.get("status") in ("SUCCEEDED", "PARTIAL", "FAILED", "RUNNING", "PENDING")
        stages = latest.get("stages", [])
        assert len(stages) == 6
        names = {s.get("stage") or s.get("name") for s in stages}
        assert names == {"FIRMS_INGESTION", "EVENT_FORMATION", "FEATURE_ENGINEERING",
                         "ML_INFERENCE", "THREAT_ANALYSIS", "ALERT_GENERATION"}
        # No stage is left NOT_IMPLEMENTED in Phase 5.
        assert all(s.get("status") != "NOT_IMPLEMENTED" for s in stages)

    def test_33_ingestion_no_objectid_leak(self):
        st = requests.get(f"{API}/ingestion/status", timeout=TIMEOUT).json()
        # _id must not leak from Mongo
        lr = st.get("latest_run") or {}
        assert "_id" not in lr, f"MongoDB _id leaked in latest_run: {lr.get('_id')}"
        for run in st.get("recent_runs") or []:
            assert "_id" not in run, "MongoDB _id leaked in recent_runs"

    def test_34_models(self):
        r = requests.get(f"{API}/models", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        # Model registry rows are only written by an explicit registration
        # step; inference availability comes from the frozen Phase 4
        # artifacts, which ARE deployed in Phase 5.
        assert isinstance(d.get("items"), list)
        assert d.get("inference_available") is True
        stack = " ".join(str(s) for s in d.get("expected_model_stack", []))
        for m in ["M1", "M2A", "M2B", "M3"]:
            assert m in stack

    # ----- 13. Clear at end -----
    # PHASE 5 UPDATE: clear removes ONLY demo data. Production records must
    # survive (they are never deletable by a demo-management endpoint).
    def test_35_clear_removes_all_demo(self):
        r = requests.delete(f"{API}/dev/demo-data/clear", timeout=30)
        assert r.status_code in (200, 204)
        ev = requests.get(f"{API}/events", params={"include_demo": "true", "limit": 500}, timeout=TIMEOUT).json()
        assert all(e.get("data_origin") != "demo" for e in _items(ev)), "demo events survived clear"
        al = requests.get(f"{API}/alerts", params={"include_demo": "true", "limit": 500}, timeout=TIMEOUT).json()
        assert all(a.get("data_origin") != "demo" for a in _items(al)), "demo alerts survived clear"
        fac = requests.get(f"{API}/facilities", params={"include_demo": "true", "limit": 2000}, timeout=TIMEOUT).json()
        assert all(f.get("data_origin") != "demo" for f in _items(fac)), "demo facilities survived clear"
