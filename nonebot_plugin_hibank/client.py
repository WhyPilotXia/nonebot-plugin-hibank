from __future__ import annotations

import asyncio
import html
import json
import re
import warnings
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning
from nonebot import get_plugin_config

from . import cache
from .config import HibankConfig
from .models import BankRef, BranchDetail, CacheStats, CityDetail, CityRef
from .names import (
    bank_name_match_keys,
    bank_names_match,
    canonical_bank_name,
    has_protected_region_qualifier,
    normalize,
)


STATE_RE = re.compile(
    r"window\.__HIBANK_PINIA_STATE__\s*=\s*(\{.*?\})</script>",
    re.S,
)
BRANCH_HREF_RE = re.compile(r"^/branches/([^/]+)/([^/]+)/(.+)$")
STANDARD_BANK_CATEGORIES = ("全国性", "外资", "境外", "区域性", "民营", "村镇")
GLOBAL_FOREIGN_GROUPS = {"外资法人", "外资分行"}
GLOBAL_OVERSEAS_GROUPS = {"香港", "澳门", "台湾"}


class HibankError(RuntimeError):
    pass


class HibankClient:
    def __init__(self) -> None:
        self.config = get_plugin_config(HibankConfig)
        self._indexes: dict[str, Any] | None = None

    @property
    def base_url(self) -> str:
        return self.config.hibank_base_url.rstrip("/")

    async def ensure_indexes(self) -> dict[str, Any]:
        if self._indexes is not None:
            return self._indexes
        cached = cache.read_json(cache.INDEXES_FILE)
        if self._indexes_valid(cached):
            self._indexes = cached
            return cached
        html_text = await self._fetch_text("/cities")
        state = self._parse_state(html_text)
        indexes = state.get("data", {}).get("indexes", {})
        if not self._indexes_valid(indexes):
            raise HibankError("城市索引解析失败。")
        cache.write_json(cache.INDEXES_FILE, indexes)
        self._indexes = indexes
        return indexes

    async def search_cities(self, keyword: str, limit: int = 20) -> list[CityRef]:
        keyword_norm = normalize(keyword)
        if not keyword_norm:
            return []
        results: list[tuple[int, CityRef]] = []
        for city in await self.iter_cities():
            city_norm = normalize(city.city)
            province_norm = normalize(city.province)
            text = province_norm + city_norm
            if keyword_norm == city_norm:
                score = 100
            elif city_norm.startswith(keyword_norm):
                score = 80
            elif keyword_norm in city_norm:
                score = 60
            elif keyword_norm in text:
                score = 40
            else:
                continue
            results.append((score, city))
        results.sort(key=lambda item: (-item[0], item[1].province_code, item[1].city_slug))
        return [city for _, city in results[:limit]]

    async def search_banks(self, keyword: str, limit: int = 30) -> list[str]:
        keyword_norm = normalize(keyword)
        if not keyword_norm:
            return []
        bank_names = await self.all_bank_names()
        results = [
            name
            for name in bank_names
            if keyword_norm in normalize(name)
        ]
        results.sort(key=lambda name: (normalize(name).find(keyword_norm), len(name), name))
        return results[:limit]

    async def all_bank_names(self) -> set[str]:
        indexes = await self.ensure_indexes()
        bank_names: set[str] = set()
        banks = indexes.get("banks", [])
        if isinstance(banks, list):
            for group in banks:
                if not isinstance(group, dict):
                    continue
                value = group.get("value", [])
                if not isinstance(value, list):
                    continue
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if isinstance(name, str) and name.strip():
                        bank_names.add(canonical_bank_name(name))
        bank_names.update(await asyncio.to_thread(self._cached_city_bank_names))
        return bank_names

    async def all_bank_records(self) -> list[dict[str, str]]:
        indexes = await self.ensure_indexes()
        records: list[dict[str, str]] = []
        seen_keys: set[str] = set()
        banks = indexes.get("banks", [])
        if isinstance(banks, list):
            for group in banks:
                if not isinstance(group, dict):
                    continue
                value = group.get("value", [])
                if not isinstance(value, list):
                    continue
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    name = canonical_bank_name(str(item.get("name", "")))
                    if not name:
                        continue
                    keys = bank_name_match_keys(name)
                    if keys & seen_keys:
                        continue
                    seen_keys.update(keys)
                    records.append(
                        {
                            "name": name,
                            "slug": str(item.get("slug", "")).strip(),
                        }
                    )

        for name in sorted(await asyncio.to_thread(self._cached_city_bank_names)):
            keys = bank_name_match_keys(name)
            if keys & seen_keys:
                continue
            seen_keys.update(keys)
            records.append({"name": name, "slug": ""})
        return records

    async def bank_category_groups(self) -> dict[str, list[str]]:
        groups: dict[str, set[str]] = {category: set() for category in STANDARD_BANK_CATEGORIES}
        cached_groups = await asyncio.to_thread(self._cached_city_bank_category_groups)
        for category, banks in cached_groups.items():
            groups.setdefault(category, set()).update(banks)

        indexes = await self.ensure_indexes()
        index_banks = indexes.get("banks", [])
        if isinstance(index_banks, list):
            for group in index_banks:
                if not isinstance(group, dict):
                    continue
                category = self._global_group_to_category(str(group.get("label", "")))
                value = group.get("value", [])
                if not isinstance(value, list):
                    continue
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if isinstance(name, str) and name.strip():
                        bank_name = canonical_bank_name(name)
                        if not self._category_groups_contain(groups, bank_name):
                            groups.setdefault(category, set()).add(bank_name)

        return {
            category: sorted(groups.get(category, set()))
            for category in (*STANDARD_BANK_CATEGORIES, "其他")
            if groups.get(category)
        }

    def _cached_city_bank_names(self) -> set[str]:
        bank_names: set[str] = set()
        if not cache.CITY_DIR.exists():
            return bank_names
        for path in cache.CITY_DIR.glob("*.json"):
            payload = cache.read_json(path)
            if not isinstance(payload, dict):
                continue
            groups = payload.get("groups", {})
            if not isinstance(groups, dict):
                continue
            for banks in groups.values():
                if not isinstance(banks, list):
                    continue
                for bank in banks:
                    name = canonical_bank_name(str(bank))
                    if name:
                        bank_names.add(name)
        return bank_names

    def _cached_city_bank_category_groups(self) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        if not cache.CITY_DIR.exists():
            return result
        for path in cache.CITY_DIR.glob("*.json"):
            payload = cache.read_json(path)
            if not isinstance(payload, dict):
                continue
            groups = payload.get("groups", {})
            if not isinstance(groups, dict):
                continue
            for category, banks in groups.items():
                if not isinstance(banks, list):
                    continue
                bucket = result.setdefault(str(category), set())
                for bank in banks:
                    name = canonical_bank_name(str(bank))
                    if name:
                        bucket.add(name)
        return result

    def _global_group_to_category(self, label: str) -> str:
        if label == "全国性":
            return "全国性"
        if label in GLOBAL_OVERSEAS_GROUPS:
            return "境外"
        if label in GLOBAL_FOREIGN_GROUPS or "外资" in label:
            return "外资"
        return "区域性"

    def _category_groups_contain(self, groups: dict[str, set[str]], bank_name: str) -> bool:
        return any(
            bank_names_match(bank_name, existing)
            for banks in groups.values()
            for existing in banks
        )

    async def split_known_banks(self, banks: list[str]) -> tuple[list[str], list[str]]:
        known_names = await self.all_bank_names()
        known_by_norm: dict[str, str] = {}
        sorted_names = sorted(
            known_names,
            key=lambda name: (
                "(" not in name and "（" not in name,
                len(name),
                name,
            ),
        )
        for name in sorted_names:
            for key in bank_name_match_keys(name):
                known_by_norm.setdefault(key, name)
        known: list[str] = []
        unknown: list[str] = []
        for bank in banks:
            target = bank.strip()
            if not target:
                continue
            target_keys = bank_name_match_keys(target)
            target_norm = normalize(target)
            ordered_keys = [target_norm] + sorted(target_keys - {target_norm}, key=len)
            canonical_name = next(
                (
                    known_by_norm[key]
                    for key in ordered_keys
                    if key in known_by_norm
                ),
                None,
            )
            if canonical_name is None:
                canonical_name = next(
                    (
                        known_name
                        for known_name in sorted_names
                        if bank_names_match(target, known_name)
                    ),
                    None,
                )
            if canonical_name is not None:
                known.append(canonical_name)
            else:
                unknown.append(target)
        return list(dict.fromkeys(known)), list(dict.fromkeys(unknown))

    async def iter_cities(self) -> list[CityRef]:
        indexes = await self.ensure_indexes()
        cities = indexes.get("cities", {})
        refs: list[CityRef] = []
        for province, payload in cities.items():
            if not isinstance(payload, dict):
                continue
            code = payload.get("code")
            city_map = payload.get("cities", {})
            if not isinstance(code, str) or not isinstance(city_map, dict):
                continue
            for city, slug in city_map.items():
                if isinstance(city, str) and isinstance(slug, str):
                    refs.append(CityRef(province, code, city, slug))
        return refs

    async def resolve_city(self, query: str) -> CityRef:
        parts = [part for part in query.strip().split() if part]
        province_kw = ""
        city_kw = query
        if len(parts) >= 2:
            province_kw = parts[0]
            city_kw = "".join(parts[1:])
        city_norm = normalize(city_kw)
        province_norm = normalize(province_kw)
        if not city_norm:
            raise HibankError("请提供城市名。")

        matches: list[tuple[int, CityRef]] = []
        for city in await self.iter_cities():
            current_city = normalize(city.city)
            current_province = normalize(city.province)
            if province_norm and province_norm not in current_province:
                continue
            if city_norm == current_city:
                score = 100
            elif current_city.startswith(city_norm):
                score = 80
            elif city_norm in current_city:
                score = 60
            elif city_norm in current_province + current_city:
                score = 40
            else:
                continue
            matches.append((score, city))
        if not matches:
            raise HibankError(f"未找到城市：{query}")
        matches.sort(key=lambda item: (-item[0], item[1].province_code, item[1].city_slug))
        return matches[0][1]

    async def get_city_detail(self, city: CityRef) -> CityDetail:
        cached = cache.read_json(cache.city_cache_path(city.key))
        if isinstance(cached, dict) and cached.get("groups"):
            return CityDetail(
                city=city,
                groups=cached["groups"],
                bank_paths=cached.get("bank_paths", {}),
                from_cache=True,
            )
        html_text = await self._fetch_text(f"/cities/{city.province_code}/{city.city_slug}")
        state = self._parse_state(html_text)
        city_cache = state.get("data", {}).get("cache", {}).get("cities", {})
        groups = city_cache.get(city.key)
        if not isinstance(groups, dict):
            if len(city_cache) == 1:
                groups = next(iter(city_cache.values()))
        if not isinstance(groups, dict):
            raise HibankError(f"{city.city} 银行列表解析失败。")
        normalized_groups = {
            str(category): [str(item) for item in items]
            for category, items in groups.items()
            if isinstance(items, list)
        }
        bank_paths = self._extract_bank_paths(html_text, city)
        cache.write_json(
            cache.city_cache_path(city.key),
            {"city": city.__dict__, "groups": normalized_groups, "bank_paths": bank_paths},
        )
        return CityDetail(city=city, groups=normalized_groups, bank_paths=bank_paths)

    async def get_branch_detail(
        self,
        city: CityRef,
        bank_query: str,
        page: int = 1,
    ) -> BranchDetail:
        city_detail = await self.get_city_detail(city)
        bank = self.resolve_bank(city_detail, bank_query)
        cached = cache.read_json(cache.branch_cache_path(city.key, bank.name))
        if isinstance(cached, list):
            return BranchDetail(
                city=city,
                bank=bank,
                branches=cached,
                page=page,
                page_size=self.config.hibank_branch_page_size,
                from_cache=True,
            )
        bank_path = bank.path
        if not bank_path.startswith("%"):
            bank_path = quote(bank_path, safe="")
        html_text = await self._fetch_text(
            f"/branches/{city.province_code}/{city.city_slug}/{bank_path}"
        )
        state = self._parse_state(html_text)
        branch_cache = state.get("data", {}).get("cache", {}).get("branches", {})
        branches: Any = branch_cache.get(f"{city.key}_{bank.name}")
        if not isinstance(branches, list) and len(branch_cache) == 1:
            branches = next(iter(branch_cache.values()))
        if not isinstance(branches, list):
            raise HibankError(f"{city.city} {bank.name} 网点列表解析失败。")
        normalized = [
            item
            for item in branches
            if isinstance(item, dict)
        ]
        cache.write_json(cache.branch_cache_path(city.key, bank.name), normalized)
        return BranchDetail(
            city=city,
            bank=bank,
            branches=normalized,
            page=page,
            page_size=self.config.hibank_branch_page_size,
        )

    def resolve_bank(self, city_detail: CityDetail, query: str) -> BankRef:
        query_keys = bank_name_match_keys(query)
        if not query_keys:
            raise HibankError("请提供银行名。")
        candidates = city_detail.bank_paths
        if not candidates:
            candidates = {
                bank: bank
                for banks in city_detail.groups.values()
                for bank in banks
            }
        matches: list[tuple[int, str, str]] = []
        for name, path in candidates.items():
            name_keys = bank_name_match_keys(name)
            protected_pair = has_protected_region_qualifier(query) or has_protected_region_qualifier(name)
            if query_keys & name_keys or bank_names_match(query, name):
                score = 100
            elif not protected_pair and any(
                name_key.startswith(query_key)
                for name_key in name_keys
                for query_key in query_keys
            ):
                score = 80
            elif not protected_pair and any(
                query_key in name_key
                for name_key in name_keys
                for query_key in query_keys
            ):
                score = 60
            else:
                continue
            matches.append((score, name, path))
        if not matches:
            raise HibankError(f"{city_detail.city.city} 未找到银行：{query}")
        matches.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
        _, name, path = matches[0]
        return BankRef(name=name, path=path)

    def get_cache_stats(self) -> CacheStats:
        city_count, branch_count = cache.cache_counts()
        return CacheStats(
            indexes_cached=cache.INDEXES_FILE.exists(),
            city_cache_count=city_count,
            branch_cache_count=branch_count,
            cache_dir=str(cache.DATA_DIR),
        )

    def _indexes_valid(self, indexes: Any) -> bool:
        if not isinstance(indexes, dict):
            return False
        cities = indexes.get("cities")
        banks = indexes.get("banks")
        if not isinstance(cities, dict) or not isinstance(banks, list):
            return False
        sichuan = cities.get("四川省")
        if not isinstance(sichuan, dict):
            return False
        city_map = sichuan.get("cities")
        if not isinstance(city_map, dict):
            return False
        return city_map.get("成都市") == "chengdu"

    async def clear_cache(self) -> None:
        await asyncio.to_thread(cache.clear_cache)
        self._indexes = None

    async def _fetch_text(self, path: str) -> str:
        url = self.base_url + path
        return await asyncio.to_thread(self._fetch_text_sync, url)

    def _fetch_text_sync(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )
        }
        try:
            with warnings.catch_warnings():
                if not self.config.hibank_verify_ssl:
                    warnings.simplefilter("ignore", InsecureRequestWarning)
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=self.config.hibank_timeout,
                    verify=self.config.hibank_verify_ssl,
                )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise HibankError(f"请求 HiBank 失败：{exc}") from exc
        response.encoding = "utf-8"
        return response.text

    def _parse_state(self, html_text: str) -> dict[str, Any]:
        match = STATE_RE.search(html_text)
        if not match:
            raise HibankError("页面状态数据解析失败。")
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise HibankError("页面状态 JSON 解析失败。") from exc

    def _extract_bank_paths(self, html_text: str, city: CityRef) -> dict[str, str]:
        soup = BeautifulSoup(html_text, "html.parser")
        paths: dict[str, str] = {}
        prefix = f"/branches/{city.province_code}/{city.city_slug}/"
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href"))
            if not href.startswith(prefix):
                continue
            match = BRANCH_HREF_RE.match(href)
            if not match:
                continue
            name = " ".join(anchor.get_text(" ", strip=True).split())
            if not name:
                image = anchor.find("img", alt=True)
                if image is not None:
                    name = str(image.get("alt", "")).strip()
            if name:
                paths[html.unescape(name)] = match.group(3)
        return paths

client = HibankClient()
