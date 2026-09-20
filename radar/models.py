from dataclasses import dataclass, field
from typing import Any

@dataclass
class KufarListing:
    ad_id: str
    url: str
    profile_id: str
    price_eur: float | None = None
    price_byn: float | None = None
    area: float | None = None
    rooms: int | None = None
    floor: int | None = None
    address: str | None = None
    title: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

@dataclass
class BirListing:
    object_key: str
    building_name: str | None = None
    official_address: str | None = None
    unit_no: str | None = None
    price_regular_eur: float | None = None
    price_fast_eur: float | None = None
    area: float | None = None
    rooms: int | None = None
    floor: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
