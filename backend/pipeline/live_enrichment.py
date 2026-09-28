"""Live FIRMS NRT state/LULC enrichment - Phase 3 methodology.

The Phase 3 standardized state/LULC CSVs (``firms_india_with_states.csv``,
``firms_india_lulc.csv``) are a frozen HISTORICAL archive ending 2026-07-31
and cannot join live NRT detections. This module reuses the ESTABLISHED
Phase 3 enrichment methodology (not a new one) to compute the same fields for
live detections from their coordinates:

    State/LGD : point-in-polygon join against the Survey of India states
                shapefile (task_b2_states.py logic, verbatim)
    LULC 2021 : sampling of ESA WorldCover 10m 2021 v200 tiles
                (task_lulc_worldcover.py logic, verbatim)

Preserved invariants:
  - The ThermoIntel ``observation_id`` (sha256) is untouched; this module
    never assigns the Phase 3 sha1 ``detection_id``.
  - Results are deterministic: identical coordinates produce identical
    state/LULC values (nearest-resampling reads over a static 2021 snapshot,
    same as Phase 3).
  - No external runtime API beyond the same public ESA WorldCover COG bucket
    the Phase 3 tooling reads (no account, no OSM, no new database).
  - Unenrichable detections keep explicit None values. Nothing is guessed.
  - Reference data (state polygons, WorldCover tile overviews) is loaded at
    most once per process and reused across batches.

Source of record:
  - Boundaries: backend/data/reference/SOI_States.shp (Survey of India
    states/UTs, EPSG:4326, STATE + State_LGD columns). The shapefile is
    PACKAGED with the backend so local and deployed environments enrich
    identically; the Phase 3 working copy under SIH_DATASETS is only a
    local fallback.
  - LULC: ESA WorldCover 10m 2021 v200, CC BY 4.0 (static 2021 snapshot,
    public COG bucket - no local file dependency).
"""

import math
import unicodedata
from pathlib import Path
from typing import Optional

from models.enums import DayNight, Satellite  # noqa: F401  (schema parity)

STANDARDIZED_DIR = r"D:\SIH2026\SIH_DATASETS\data\standardized"

# Backend root (.../backend on any OS). The SOI boundary shapefile ships
# inside the repository so deployments without the D:\ SIH_DATASETS working
# copy (e.g. Render Linux) still enrich state/LGD identically to local runs.
BACKEND_DIR = Path(__file__).resolve().parent.parent
BOUNDARY_SHP = BACKEND_DIR / "data" / "reference" / "SOI_States.shp"
_LOCAL_PHASE3_SHP = Path(
    r"D:\SIH2026\SIH_DATASETS\data\raw\boundaries\soi_states\SOI_States.shp"
)


def resolve_boundary_shp() -> Path:
    """Packaged SOI shapefile when present, else the Phase 3 working copy."""
    if BOUNDARY_SHP.exists():
        return BOUNDARY_SHP
    return _LOCAL_PHASE3_SHP

# ESA WorldCover 10m 2021 v200 public COG bucket (same as Phase 3 tooling).
WORLDCOVER_S3_BASE = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/"
    "v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)
# 10 m pixels -> ~300 m cells (FIRMS is 375 m), per task_lulc_worldcover.py.
DECIMATION = 30

# WorldCover v200 class map (verbatim from task_lulc_worldcover.py).
WC_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare/sparse vegetation",
    70: "Snow/ice",
    80: "Water",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
    0: "NO_DATA",
}

# Historical CSV lookup (kept available for historical/replay data whose
# dates fall inside the archive coverage period).
HISTORICAL_STATES_CSV = str(Path(STANDARDIZED_DIR) / "firms_india_with_states.csv")
HISTORICAL_LULC_CSV = str(Path(STANDARDIZED_DIR) / "firms_india_lulc.csv")
HISTORICAL_COVERAGE_END = "2026-07-31"


def _clean_state_name(raw: str) -> str:
    """Verbatim normalization from task_b2_states.py."""
    s = str(raw).strip().upper()
    if s.startswith("DISPUTED"):
        return "DISPUTED_ZONE"
    s = "".join(
        ch
        for ch in unicodedata.normalize("NFD", s)
        if not unicodedata.combining(ch)
    )
    typo_fixes = {"RAJATHAN": "RAJASTHAN", "CHHATTISGARH": "CHHATTISGARH"}
    for wrong, right in typo_fixes.items():
        if wrong in s:
            s = s.replace(wrong, right)
    s = s.title()
    s = s.replace(" & ", " and ").replace(" And ", " and ")
    return s


class LiveEnricher:
    """Once-per-process enrichment context (Phase 3 methodology).

    Loads the SOI states shapefile once, builds a STRtree spatial index once,
    and caches WorldCover tile overviews per 3x3-degree tile. All public
    methods are synchronous and deterministic; call sites batch detections
    per ingestion run.
    """

    def __init__(self, boundary_shp: Optional[Path] = None, lulc_enabled: bool = True):
        # Default resolves at CONSTRUCTION time (deploy-safe: packaged
        # reference data first, Phase 3 working copy as local fallback).
        self._boundary_shp = Path(boundary_shp) if boundary_shp else Path(resolve_boundary_shp())
        self._lulc_enabled = lulc_enabled
        self._states_loaded = False
        self._geoms = None
        self._tree = None
        self._state_names: list[Optional[str]] = []
        self._state_lgd: list[Optional[str]] = []
        self._tiles: dict[str, Optional[object]] = {}

    # ------------------------------------------------------------- states --

    def _load_states(self) -> None:
        if self._states_loaded:
            return
        self._states_loaded = True

        import geopandas as gpd
        from shapely.strtree import STRtree

        if not self._boundary_shp.exists():
            raise FileNotFoundError(
                f"SOI states boundary file missing: {self._boundary_shp}"
            )

        gdf = gpd.read_file(self._boundary_shp)

        name_col = next(
            (c for c in ("STATE", "STATE_NAME", "STATE", "STNAME", "state_name", "state")
             if c in gdf.columns),
            None,
        )
        if name_col is None:
            raise ValueError(
                "SOI states shapefile has no recognized state-name column"
            )

        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)

        keep = [name_col] + (["State_LGD"] if "State_LGD" in gdf.columns else [])
        gdf = gdf[keep + ["geometry"]].copy()
        gdf[name_col] = gdf[name_col].map(_clean_state_name)
        gdf = gdf.rename(columns={name_col: "state_ut"})
        # task_b2_states.py dissolves duplicates by cleaned name.
        gdf = gdf.dissolve(by="state_ut", as_index=False, aggfunc="first")

        self._geoms = list(gdf.geometry.values)
        self._tree = STRtree(self._geoms)
        self._state_names = list(gdf["state_ut"])
        lgd = gdf["State_LGD"] if "State_LGD" in gdf.columns else None
        self._state_lgd = (
            [None if (lgd is None or v is None or v == "") else str(v) for v in lgd]
            if lgd is not None
            else [None] * len(self._geoms)
        )

    def enrich_states(
        self, lats: list[float], lons: list[float]
    ) -> list[tuple[Optional[str], Optional[str]]]:
        """Point-in-polygon state/LGD join for a batch of coordinates."""
        self._load_states()
        results: list[tuple[Optional[str], Optional[str]]] = []

        for lat, lon in zip(lats, lons):
            point = _make_point(lat, lon)
            hit_idx = _nearest_within(self._tree, self._geoms, point)
            if hit_idx is None:
                # task_b2_states.py keeps unmatched points as OUTSIDE_STATES
                # in the archive; the v2 ThermalDetection schema has no such
                # marker, so unmatched stays explicitly missing.
                results.append((None, None))
            else:
                lgd = self._state_lgd[hit_idx]
                results.append((self._state_names[hit_idx], lgd))
        return results

    # --------------------------------------------------------------- lulc --

    @staticmethod
    def _tile_name(lat: float, lon: float) -> str:
        """Verbatim tile naming from task_lulc_worldcover.py."""
        lat0 = math.floor((lat - 1e-9) / 3.0) * 3.0
        lon0 = math.floor((lon - 1e-9) / 3.0) * 3.0
        ns = "N" if lat0 >= 0 else "S"
        ew = "E" if lon0 >= 0 else "W"
        return f"{ns}{abs(int(lat0)):02d}{ew}{abs(int(lon0)):03d}"

    def _tile_array(self, tile: str):
        """Decimated overview of one WorldCover tile, cached per process."""
        if tile in self._tiles:
            return self._tiles[tile]

        arr = None
        if self._lulc_enabled:
            try:
                import rasterio
                from rasterio.enums import Resampling

                url = WORLDCOVER_S3_BASE.format(tile=tile)
                with rasterio.open(url) as src:
                    transform = src.transform
                    oh = max(1, src.height // DECIMATION)
                    ow = max(1, src.width // DECIMATION)
                    overview = src.read(
                        1, out_shape=(oh, ow), resampling=Resampling.nearest
                    )
                arr = (overview, transform, oh, ow)
            except Exception:
                # Phase 3 behaviour: a tile that cannot be read is reported
                # and yields NO_DATA (code 0), never a fabricated class.
                arr = None
        else:
            arr = None

        self._tiles[tile] = arr
        return arr

    def enrich_lulc(
        self, lats: list[float], lons: list[float]
    ) -> list[tuple[Optional[str], Optional[str]]]:
        """Sample WorldCover 2021 for a batch of coordinates.

        Returns (code_str, class_name) or (None, None) when the tile cannot
        be read, when LULC sampling is disabled, or when the pixel is
        NO_DATA (code 0). Phase 3 methodology, verbatim resampling.
        """
        if not self._lulc_enabled:
            return [(None, None)] * len(lats)

        try:
            import numpy as np
        except ImportError:  # pragma: no cover
            return [(None, None)] * len(lats)

        results: list[tuple[Optional[str], Optional[str]]] = []
        tile_groups: dict[str, list[int]] = {}
        for i, (lat, lon) in enumerate(zip(lats, lons)):
            tile_groups.setdefault(self._tile_name(lat, lon), []).append(i)

        codes = np.full(len(lats), -1, dtype=np.int64)

        for tile, indices in tile_groups.items():
            packed = self._tile_array(tile)
            if packed is None:
                continue
            overview, transform, oh, ow = packed
            dec = transform * _affine_scale(DECIMATION)
            a, b, c = dec.a, dec.b, dec.c
            d, e, f = dec.d, dec.e, dec.f
            det = a * e - b * d
            if det == 0:
                continue
            g_lons = np.array([lons[i] for i in indices], dtype=float)
            g_lats = np.array([lats[i] for i in indices], dtype=float)
            col = ((g_lons - c) * e - (g_lats - f) * b) / det
            row = ((g_lats - f) * a - (g_lons - c) * d) / det
            col = np.floor(col).astype(int)
            row = np.floor(row).astype(int)
            valid = (row >= 0) & (row < oh) & (col >= 0) & (col < ow)
            for j, i in enumerate(indices):
                if valid[j]:
                    codes[i] = int(overview[row[j], col[j]])

        for code in codes:
            if code <= 0:  # unreadable tile (-1) or NO_DATA (0)
                results.append((None, None))
            else:
                results.append((str(int(code)), WC_CLASSES.get(int(code))))
        return results

    # ------------------------------------------------------------ overall --

    def enrich_batch(
        self, lats: list[float], lons: list[float]
    ) -> list[dict]:
        """Enrich a batch of detections: state, state_lgd, lulc_2021_code,
        lulc_2021_class. Unenrichable fields stay None."""
        states = self.enrich_states(lats, lons)
        lulc = self.enrich_lulc(lats, lons)

        enriched = []
        for (state, lgd), (lcode, lclass) in zip(states, lulc):
            enriched.append(
                {
                    "state": state,
                    "state_lgd": lgd,
                    "lulc_2021_code": lcode,
                    "lulc_2021_class": lclass,
                }
            )
        return enriched


_LIVE_ENRICHER: Optional["LiveEnricher"] = None


def get_live_enricher() -> "LiveEnricher":
    """Process-wide LiveEnricher singleton (reference data cached once)."""
    global _LIVE_ENRICHER
    if _LIVE_ENRICHER is None:
        _LIVE_ENRICHER = LiveEnricher()
    return _LIVE_ENRICHER


def _make_point(lat: float, lon: float):
    from shapely.geometry import Point

    return Point(float(lon), float(lat))


def _nearest_within(tree, geoms, point):
    """Index of the polygon containing ``point`` via STRtree query, else None."""
    for idx in tree.query(point):
        if geoms[idx].contains(point):
            return idx
    return None


def _affine_scale(factor: int):
    from rasterio.transform import Affine

    return Affine.scale(factor)


# --------------------------------------------------------------- historical -


def _historical_lookup_cache() -> tuple[dict, dict]:
    """One-pass load of the historical archive CSVs (per-process cache).

    Returns (states_by_id, lulc_by_id) keyed by the Phase 3 sha1
    ``detection_id``. Only useful for historical/replay detections whose
    dates fall within the archive coverage period.
    """
    global _HIST_CACHE
    if _HIST_CACHE is not None:
        return _HIST_CACHE

    states: dict[str, dict] = {}
    lulc: dict[str, dict] = {}

    try:
        with open(HISTORICAL_STATES_CSV, "r", encoding="utf-8", newline="") as f:
            for row in _csv_reader(f):
                did = row.get("detection_id")
                if did:
                    states[did] = {
                        "state": row.get("state_ut") or None,
                        "state_lgd": row.get("State_LGD") or None,
                    }
    except FileNotFoundError:
        states = {}

    try:
        with open(HISTORICAL_LULC_CSV, "r", encoding="utf-8", newline="") as f:
            for row in _csv_reader(f):
                did = row.get("detection_id")
                if did:
                    lulc[did] = {
                        "lulc_2021_code": row.get("lulc_2021_code") or None,
                        "lulc_2021_class": row.get("lulc_2021_class") or None,
                    }
    except FileNotFoundError:
        lulc = {}

    _HIST_CACHE = (states, lulc)
    return _HIST_CACHE


_HIST_CACHE: Optional[tuple[dict, dict]] = None


def _csv_reader(handle):
    import csv

    return csv.DictReader(handle)


def historical_enrich_batch(
    detection_ids: list[str],
) -> list[Optional[dict]]:
    """Historical-archive enrichment for replay data (Phase 3 CSVs).

    Returns None for IDs absent from the archive. Callers must confirm the
    detection date is within HISTORICAL_COVERAGE_END before trusting a hit.
    """
    states, lulc = _historical_lookup_cache()
    out = []
    for did in detection_ids:
        s = states.get(did)
        l = lulc.get(did)
        if s is None and l is None:
            out.append(None)
        else:
            merged = {
                "state": (s or {}).get("state"),
                "state_lgd": (s or {}).get("state_lgd"),
                "lulc_2021_code": (l or {}).get("lulc_2021_code"),
                "lulc_2021_class": (l or {}).get("lulc_2021_class"),
            }
            out.append(merged)
    return out
