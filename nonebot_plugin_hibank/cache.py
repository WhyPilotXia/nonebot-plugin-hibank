from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from nonebot import require

require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as localstore  # noqa: E402


DATA_DIR: Path = localstore.get_plugin_data_dir()
INDEXES_FILE = DATA_DIR / "indexes.json"
CITY_DIR = DATA_DIR / "cities"
BRANCH_DIR = DATA_DIR / "branches"
USER_MARKS_FILE = DATA_DIR / "user_marks.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CITY_DIR.mkdir(parents=True, exist_ok=True)
    BRANCH_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(value: str) -> str:
    result = []
    for char in value:
        if char.isalnum() or char in {"-", "_"}:
            result.append(char)
        else:
            result.append("_")
    return "".join(result).strip("_") or "cache"


def read_json(path: Path) -> Any | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: Any) -> None:
    ensure_dirs()
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def city_cache_path(city_key: str) -> Path:
    return CITY_DIR / f"{safe_name(city_key)}.json"


def branch_cache_path(city_key: str, bank_name: str) -> Path:
    return BRANCH_DIR / f"{safe_name(city_key)}__{safe_name(bank_name)}.json"


def clear_cache() -> None:
    if INDEXES_FILE.exists():
        INDEXES_FILE.unlink()
    if CITY_DIR.exists():
        shutil.rmtree(CITY_DIR)
    if BRANCH_DIR.exists():
        shutil.rmtree(BRANCH_DIR)
    ensure_dirs()


def cache_counts() -> tuple[int, int]:
    ensure_dirs()
    city_count = len(list(CITY_DIR.glob("*.json")))
    branch_count = len(list(BRANCH_DIR.glob("*.json")))
    return city_count, branch_count
