"""Shared Pydantic building blocks for MongoDB documents."""
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_object_id(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    return value


PyObjectId = Annotated[str, BeforeValidator(_coerce_object_id)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GeoPoint(BaseModel):
    """GeoJSON point, stored so a 2dsphere index can be used."""

    model_config = ConfigDict(extra="ignore")

    type: str = "Point"
    coordinates: list[float]  # [longitude, latitude]

    @classmethod
    def from_lat_lon(cls, latitude: float, longitude: float) -> "GeoPoint":
        return cls(coordinates=[longitude, latitude])

    @property
    def longitude(self) -> float:
        return self.coordinates[0]

    @property
    def latitude(self) -> float:
        return self.coordinates[1]


class BaseDocument(BaseModel):
    """Base for every MongoDB document model.

    Maps Mongo's ``_id`` to a JSON-serialisable ``id`` string and provides
    explicit conversion helpers so raw Mongo documents never leak out of the
    service layer.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        use_enum_values=True,
        protected_namespaces=(),
    )

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    def to_mongo(self) -> dict:
        doc = self.model_dump(by_alias=True)
        doc.pop("_id", None)
        return doc

    @classmethod
    def from_mongo(cls, doc: Optional[dict]):
        if doc is None:
            return None
        return cls.model_validate(doc)


class Paginated(BaseModel):
    """Envelope for list endpoints."""

    model_config = ConfigDict(protected_namespaces=())

    items: list[Any]
    total: int
    limit: int
    offset: int
