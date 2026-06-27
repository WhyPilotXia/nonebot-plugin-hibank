from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

from . import cache
from .names import bank_name_match_keys, bank_names_match, canonical_bank_name


MarkKind = Literal["marked", "followed"]


@dataclass(frozen=True)
class BankMarkEntry:
    name: str
    count: int = 1
    card_numbers: tuple[str, ...] = ()

    @property
    def card_number(self) -> str:
        return self.card_numbers[0] if self.card_numbers else ""


@dataclass(frozen=True)
class UserBankMarks:
    marked: dict[str, BankMarkEntry]
    followed: dict[str, BankMarkEntry]

    @property
    def marked_names(self) -> set[str]:
        return set(self.marked)

    @property
    def followed_names(self) -> set[str]:
        return set(self.followed)


def _dedupe_card_numbers(card_numbers: Iterable[object]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in card_numbers:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _entry_count(count: object, card_numbers: Sequence[str] = ()) -> int:
    try:
        value = int(count or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, value, len(card_numbers))


def _entry_to_payload(entry: BankMarkEntry) -> dict[str, object]:
    card_numbers = _dedupe_card_numbers(entry.card_numbers)
    payload: dict[str, object] = {
        "name": entry.name,
        "count": _entry_count(entry.count, card_numbers),
    }
    if card_numbers:
        payload["card_numbers"] = list(card_numbers)
    return payload


def _entry_from_item(item: object) -> BankMarkEntry | None:
    if isinstance(item, dict):
        name = canonical_bank_name(str(item.get("name") or ""))
        if not name:
            return None
        raw_card_numbers = item.get("card_numbers")
        if isinstance(raw_card_numbers, list):
            card_numbers = _dedupe_card_numbers(raw_card_numbers)
        else:
            card_numbers = _dedupe_card_numbers([item.get("card_number", "")])
        return BankMarkEntry(
            name=name,
            count=_entry_count(item.get("count", 1), card_numbers),
            card_numbers=card_numbers,
        )
    name = canonical_bank_name(str(item))
    if not name:
        return None
    return BankMarkEntry(name=name)


def _dedupe_entries(items: object) -> dict[str, BankMarkEntry]:
    if not isinstance(items, list):
        return {}
    result: list[BankMarkEntry] = []
    for item in items:
        entry = _entry_from_item(item)
        if entry is None:
            continue
        keys = bank_name_match_keys(entry.name)
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(result)
                if keys & bank_name_match_keys(existing.name)
                or bank_names_match(entry.name, existing.name)
            ),
            None,
        )
        if duplicate_index is None:
            result.append(entry)
            continue
        existing = result[duplicate_index]
        name = entry.name if len(entry.name) > len(existing.name) else existing.name
        card_numbers = _dedupe_card_numbers((*existing.card_numbers, *entry.card_numbers))
        count = max(existing.count, entry.count, len(card_numbers))
        result[duplicate_index] = BankMarkEntry(name=name, count=count, card_numbers=card_numbers)
    return {entry.name: entry for entry in sorted(result, key=lambda item: item.name)}


def load_all_marks() -> dict[str, dict[str, list[dict[str, object]]]]:
    data = cache.read_json(cache.USER_MARKS_FILE)
    if not isinstance(data, dict):
        return {}
    result: dict[str, dict[str, list[dict[str, object]]]] = {}
    for user_id, payload in data.items():
        if not isinstance(payload, dict):
            continue
        marked = _dedupe_entries(payload.get("marked", []))
        followed = _dedupe_entries(payload.get("followed", []))
        result[str(user_id)] = {
            "marked": [_entry_to_payload(entry) for entry in marked.values()],
            "followed": [_entry_to_payload(entry) for entry in followed.values()],
        }
    return result


def save_all_marks(data: dict[str, dict[str, list[dict[str, object]]]]) -> None:
    cache.write_json(cache.USER_MARKS_FILE, data)


def _ensure_payload(data: dict[str, dict[str, list[dict[str, object]]]], user_id: str) -> dict[str, list[dict[str, object]]]:
    return data.setdefault(str(user_id), {"marked": [], "followed": []})


def get_user_marks(user_id: str) -> UserBankMarks:
    data = load_all_marks()
    payload = data.get(str(user_id), {})
    return UserBankMarks(
        marked=_dedupe_entries(payload.get("marked", [])),
        followed=_dedupe_entries(payload.get("followed", [])),
    )


def get_user_entries(user_id: str, kind: MarkKind) -> dict[str, BankMarkEntry]:
    marks = get_user_marks(user_id)
    return marks.marked if kind == "marked" else marks.followed


def find_entry(entries: dict[str, BankMarkEntry], name: str) -> BankMarkEntry | None:
    keys = bank_name_match_keys(name)
    return next(
        (
            entry
            for entry in entries.values()
            if keys & bank_name_match_keys(entry.name) or bank_names_match(name, entry.name)
        ),
        None,
    )


def _replace_entry(
    entries: dict[str, BankMarkEntry],
    name: str,
    *,
    count: int | None = None,
    card_numbers: Sequence[str] | None = None,
) -> None:
    normalized = canonical_bank_name(name)
    if not normalized:
        return
    keys = bank_name_match_keys(normalized)
    kept_entries: dict[str, BankMarkEntry] = {}
    matched_entries = [
        item
        for item in entries.values()
        if item.name == normalized
        or (keys and keys & bank_name_match_keys(item.name))
        or bank_names_match(normalized, item.name)
    ]
    for item in entries.values():
        if item not in matched_entries:
            kept_entries[item.name] = item
    existing = matched_entries[0] if matched_entries else None
    for item in matched_entries:
        if existing is None:
            existing = item
            continue
        existing = BankMarkEntry(
            name=item.name if len(item.name) > len(existing.name) else existing.name,
            count=max(existing.count, item.count),
            card_numbers=_dedupe_card_numbers((*existing.card_numbers, *item.card_numbers)),
        )
    preserved_card_numbers = existing.card_numbers if existing is not None else ()
    next_card_numbers = (
        preserved_card_numbers
        if card_numbers is None
        else _dedupe_card_numbers(card_numbers)
    )
    entry = BankMarkEntry(
        name=normalized if existing is None or len(normalized) >= len(existing.name) else existing.name,
        count=_entry_count(existing.count if count is None and existing is not None else count or 1, next_card_numbers),
        card_numbers=next_card_numbers,
    )
    entries.clear()
    entries.update(kept_entries)
    entries[entry.name] = entry


def add_user_banks(user_id: str, kind: MarkKind, banks: list[str], count: int | None = None) -> int:
    data = load_all_marks()
    payload = _ensure_payload(data, str(user_id))
    entries = _dedupe_entries(payload.get(kind, []))
    before = len(entries)
    for bank in banks:
        _replace_entry(entries, bank, count=count)
    payload[kind] = [_entry_to_payload(entry) for entry in sorted(entries.values(), key=lambda item: item.name)]
    data[str(user_id)] = payload
    save_all_marks(data)
    return max(0, len(entries) - before)


def remove_user_banks(user_id: str, kind: MarkKind, banks: list[str]) -> int:
    data = load_all_marks()
    payload = _ensure_payload(data, str(user_id))
    entries = _dedupe_entries(payload.get(kind, []))
    before = len(entries)
    for bank in banks:
        name = canonical_bank_name(bank)
        keys = bank_name_match_keys(name)
        entries = {
            item.name: item
            for item in entries.values()
            if item.name != name
            and (not keys or not (keys & bank_name_match_keys(item.name)))
            and not bank_names_match(name, item.name)
        }
    payload[kind] = [_entry_to_payload(entry) for entry in sorted(entries.values(), key=lambda item: item.name)]
    data[str(user_id)] = payload
    save_all_marks(data)
    return before - len(entries)


def set_user_entries(user_id: str, kind: MarkKind, entries: list[BankMarkEntry]) -> int:
    data = load_all_marks()
    payload = _ensure_payload(data, str(user_id))
    normalized = _dedupe_entries([_entry_to_payload(entry) for entry in entries])
    payload[kind] = [_entry_to_payload(entry) for entry in normalized.values()]
    data[str(user_id)] = payload
    save_all_marks(data)
    return len(normalized)


def set_user_banks(user_id: str, kind: MarkKind, banks: list[str]) -> int:
    return set_user_entries(user_id, kind, [BankMarkEntry(canonical_bank_name(item)) for item in banks])


def set_entry_card_numbers(
    user_id: str,
    kind: MarkKind,
    bank_name: str,
    card_numbers: Sequence[str],
) -> bool:
    data = load_all_marks()
    payload = _ensure_payload(data, str(user_id))
    entries = _dedupe_entries(payload.get(kind, []))
    entry = find_entry(entries, bank_name)
    if entry is None:
        return False
    _replace_entry(entries, entry.name, count=entry.count, card_numbers=card_numbers)
    payload[kind] = [_entry_to_payload(item) for item in sorted(entries.values(), key=lambda item: item.name)]
    data[str(user_id)] = payload
    save_all_marks(data)
    return True


def update_card_number(user_id: str, kind: MarkKind, bank_name: str, card_number: str) -> bool:
    return set_entry_card_numbers(user_id, kind, bank_name, [card_number])
