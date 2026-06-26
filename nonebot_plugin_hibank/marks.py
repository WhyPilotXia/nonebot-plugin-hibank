from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import cache
from .names import bank_name_match_keys


MarkKind = Literal["marked", "followed"]


@dataclass(frozen=True)
class UserBankMarks:
    marked: set[str]
    followed: set[str]


def load_all_marks() -> dict[str, dict[str, list[str]]]:
    data = cache.read_json(cache.USER_MARKS_FILE)
    if not isinstance(data, dict):
        return {}
    result: dict[str, dict[str, list[str]]] = {}
    for user_id, payload in data.items():
        if not isinstance(payload, dict):
            continue
        marked = payload.get("marked", [])
        followed = payload.get("followed", [])
        result[str(user_id)] = {
            "marked": [str(item) for item in marked if str(item).strip()],
            "followed": [str(item) for item in followed if str(item).strip()],
        }
    return result


def save_all_marks(data: dict[str, dict[str, list[str]]]) -> None:
    cache.write_json(cache.USER_MARKS_FILE, data)


def get_user_marks(user_id: str) -> UserBankMarks:
    data = load_all_marks()
    payload = data.get(str(user_id), {})
    return UserBankMarks(
        marked=set(_dedupe_bank_names(payload.get("marked", []))),
        followed=set(_dedupe_bank_names(payload.get("followed", []))),
    )


def _dedupe_bank_names(banks: list[str]) -> list[str]:
    result: list[str] = []
    for bank in banks:
        name = bank.strip()
        if not name:
            continue
        keys = bank_name_match_keys(name)
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(result)
                if keys & bank_name_match_keys(existing)
            ),
            None,
        )
        if duplicate_index is None:
            result.append(name)
        elif len(name) > len(result[duplicate_index]):
            result[duplicate_index] = name
    return sorted(result)


def add_user_banks(user_id: str, kind: MarkKind, banks: list[str]) -> int:
    data = load_all_marks()
    user_key = str(user_id)
    payload = data.setdefault(user_key, {"marked": [], "followed": []})
    existing = {str(item).strip() for item in payload.get(kind, []) if str(item).strip()}
    before = len(existing)
    for bank in banks:
        name = bank.strip()
        if not name:
            continue
        keys = bank_name_match_keys(name)
        existing = {
            item
            for item in existing
            if not keys or not (keys & bank_name_match_keys(item))
        }
        existing.add(name)
    payload[kind] = sorted(existing)
    data[user_key] = payload
    save_all_marks(data)
    return max(0, len(existing) - before)


def remove_user_banks(user_id: str, kind: MarkKind, banks: list[str]) -> int:
    data = load_all_marks()
    user_key = str(user_id)
    payload = data.setdefault(user_key, {"marked": [], "followed": []})
    existing = {str(item).strip() for item in payload.get(kind, []) if str(item).strip()}
    before = len(existing)
    for bank in banks:
        name = bank.strip()
        keys = bank_name_match_keys(name)
        existing = {
            item
            for item in existing
            if item != name and (not keys or not (keys & bank_name_match_keys(item)))
        }
    payload[kind] = sorted(existing)
    data[user_key] = payload
    save_all_marks(data)
    return before - len(existing)


def set_user_banks(user_id: str, kind: MarkKind, banks: list[str]) -> int:
    data = load_all_marks()
    user_key = str(user_id)
    payload = data.setdefault(user_key, {"marked": [], "followed": []})
    normalized = _dedupe_bank_names(banks)
    payload[kind] = normalized
    data[user_key] = payload
    save_all_marks(data)
    return len(normalized)
