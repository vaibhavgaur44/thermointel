"""India states and Union Territories - the operational geography.

Districts are intentionally NOT part of the product navigation/filter system
(Phase 1, section 19). Bounding boxes are used purely for camera framing.
"""
from models.enums import RegionKind

INDIA_BBOX = [68.1, 6.5, 97.4, 35.7]  # [west, south, east, north]

# name, kind, [west, south, east, north]
INDIA_REGIONS = [
    ("Andaman and Nicobar Islands", RegionKind.UNION_TERRITORY, [92.2, 6.7, 94.3, 13.7]),
    ("Andhra Pradesh", RegionKind.STATE, [76.7, 12.6, 84.8, 19.9]),
    ("Arunachal Pradesh", RegionKind.STATE, [91.6, 26.7, 97.4, 29.5]),
    ("Assam", RegionKind.STATE, [89.7, 24.1, 96.0, 28.2]),
    ("Bihar", RegionKind.STATE, [83.3, 24.3, 88.3, 27.5]),
    ("Chandigarh", RegionKind.UNION_TERRITORY, [76.7, 30.6, 76.9, 30.8]),
    ("Chhattisgarh", RegionKind.STATE, [80.2, 17.8, 84.4, 24.1]),
    ("Dadra and Nagar Haveli and Daman and Diu", RegionKind.UNION_TERRITORY, [72.6, 20.1, 73.2, 20.8]),
    ("Delhi", RegionKind.UNION_TERRITORY, [76.8, 28.4, 77.4, 28.9]),
    ("Goa", RegionKind.STATE, [73.6, 14.8, 74.4, 15.8]),
    ("Gujarat", RegionKind.STATE, [68.1, 20.1, 74.5, 24.7]),
    ("Haryana", RegionKind.STATE, [74.4, 27.6, 77.6, 30.9]),
    ("Himachal Pradesh", RegionKind.STATE, [75.5, 30.3, 79.0, 33.3]),
    ("Jammu and Kashmir", RegionKind.UNION_TERRITORY, [73.8, 32.2, 80.3, 35.7]),
    ("Jharkhand", RegionKind.STATE, [83.3, 21.9, 87.9, 25.4]),
    ("Karnataka", RegionKind.STATE, [74.0, 11.5, 78.6, 18.5]),
    ("Kerala", RegionKind.STATE, [74.8, 8.2, 77.4, 12.8]),
    ("Ladakh", RegionKind.UNION_TERRITORY, [75.8, 32.2, 80.3, 35.7]),
    ("Lakshadweep", RegionKind.UNION_TERRITORY, [71.7, 8.2, 74.0, 12.3]),
    ("Madhya Pradesh", RegionKind.STATE, [74.0, 21.1, 82.8, 26.9]),
    ("Maharashtra", RegionKind.STATE, [72.6, 15.6, 80.9, 22.0]),
    ("Manipur", RegionKind.STATE, [92.9, 23.8, 94.8, 25.7]),
    ("Meghalaya", RegionKind.STATE, [89.8, 25.0, 92.8, 26.1]),
    ("Mizoram", RegionKind.STATE, [92.2, 21.9, 93.5, 24.5]),
    ("Nagaland", RegionKind.STATE, [93.3, 25.2, 95.3, 27.0]),
    ("Odisha", RegionKind.STATE, [81.3, 17.8, 87.5, 22.6]),
    ("Puducherry", RegionKind.UNION_TERRITORY, [74.8, 10.9, 79.9, 12.0]),
    ("Punjab", RegionKind.STATE, [73.8, 29.5, 76.9, 32.5]),
    ("Rajasthan", RegionKind.STATE, [69.4, 23.0, 78.3, 30.2]),
    ("Sikkim", RegionKind.STATE, [88.0, 27.0, 88.9, 28.1]),
    ("Tamil Nadu", RegionKind.STATE, [76.2, 8.0, 80.3, 13.6]),
    ("Telangana", RegionKind.STATE, [77.2, 15.8, 81.3, 19.9]),
    ("Tripura", RegionKind.STATE, [91.0, 22.9, 92.4, 24.5]),
    ("Uttar Pradesh", RegionKind.STATE, [77.0, 23.8, 84.7, 30.4]),
    ("Uttarakhand", RegionKind.STATE, [77.5, 28.7, 81.1, 31.5]),
    ("West Bengal", RegionKind.STATE, [85.8, 21.4, 89.9, 27.3]),
]

REGION_NAMES = {name for name, _, _ in INDIA_REGIONS}


def list_regions() -> list[dict]:
    return [
        {"name": name, "kind": kind.value, "bbox": bbox}
        for name, kind, bbox in INDIA_REGIONS
    ]


def is_valid_region(name: str) -> bool:
    return name in REGION_NAMES
