from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import cache


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
        marked=set(payload.get("marked", [])),
        followed=set(payload.get("followed", [])),
    )


def add_user_banks(user_id: str, kind: MarkKind, banks: list[str]) -> int:
    data = load_all_marks()
    user_key = str(user_id)
    payload = data.setdefault(user_key, {"marked": [], "followed": []})
    existing = {str(item) for item in payload.get(kind, [])}
    before = len(existing)
    existing.update(bank.strip() for bank in banks if bank.strip())
    payload[kind] = sorted(existing)
    data[user_key] = payload
    save_all_marks(data)
    return len(existing) - before


def remove_user_banks(user_id: str, kind: MarkKind, banks: list[str]) -> int:
    data = load_all_marks()
    user_key = str(user_id)
    payload = data.setdefault(user_key, {"marked": [], "followed": []})
    existing = {str(item) for item in payload.get(kind, [])}
    before = len(existing)
    for bank in banks:
        existing.discard(bank)
    payload[kind] = sorted(existing)
    data[user_key] = payload
    save_all_marks(data)
    return before - len(existing)


def set_user_banks(user_id: str, kind: MarkKind, banks: list[str]) -> int:
    data = load_all_marks()
    user_key = str(user_id)
    payload = data.setdefault(user_key, {"marked": [], "followed": []})
    normalized = sorted({bank.strip() for bank in banks if bank.strip()})
    payload[kind] = normalized
    data[user_key] = payload
    save_all_marks(data)
    return len(normalized)
