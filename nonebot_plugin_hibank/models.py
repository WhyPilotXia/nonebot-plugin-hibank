from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CityGroups = dict[str, list[str]]


@dataclass(frozen=True)
class CityRef:
    province: str
    province_code: str
    city: str
    city_slug: str

    @property
    def key(self) -> str:
        return f"{self.province}_{self.city}"


@dataclass(frozen=True)
class BankRef:
    name: str
    path: str


@dataclass(frozen=True)
class CityDetail:
    city: CityRef
    groups: CityGroups
    bank_paths: dict[str, str]
    from_cache: bool = False

    @property
    def total_count(self) -> int:
        return sum(len(items) for items in self.groups.values())


@dataclass(frozen=True)
class BranchDetail:
    city: CityRef
    bank: BankRef
    branches: list[dict[str, Any]]
    page: int
    page_size: int
    from_cache: bool = False

    @property
    def total_count(self) -> int:
        return len(self.branches)

    @property
    def total_pages(self) -> int:
        if not self.branches:
            return 1
        return (len(self.branches) + self.page_size - 1) // self.page_size

    @property
    def visible_branches(self) -> list[dict[str, Any]]:
        page = min(max(self.page, 1), self.total_pages)
        start = (page - 1) * self.page_size
        return self.branches[start : start + self.page_size]


@dataclass(frozen=True)
class CacheStats:
    indexes_cached: bool
    city_cache_count: int
    branch_cache_count: int
    cache_dir: str
