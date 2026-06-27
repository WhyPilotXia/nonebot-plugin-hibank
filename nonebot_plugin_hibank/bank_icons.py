from __future__ import annotations

import hashlib
import json
import re
import tempfile
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Iterable, Mapping

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from urllib3.exceptions import InsecureRequestWarning

from .names import bank_names_match, normalize


ASSET_DIR = Path(__file__).resolve().parent / "assets"
LOGO_DIR = ASSET_DIR / "bank_logos"
ICONGO_LOGO_DIR = LOGO_DIR / "icongo"
HIBANK_LOGO_DIR = LOGO_DIR / "hibank"
FALLBACK_LOGO_DIR = LOGO_DIR / "fallback"
MANUAL_LOGO_DIR = LOGO_DIR / "manual"
INDEX_FILE = ASSET_DIR / "bank_assets.json"
SOURCE_URL = "https://github.com/icongo/bank-logos/archive/refs/heads/main.zip"
SOURCE_NAME = "icongo/bank-logos"
SOURCE_REPO = "https://github.com/icongo/bank-logos"
HIBANK_BANKS_URL = "https://hi.zzz.moe/banks"
HIBANK_LOGO_PREFIX = "https://storage.my-api.cn/static/images/logo/"
HIBANK_SOURCE_NAME = "HiBank"
MANUAL_SOURCE_NAME = "manual"

README_IMG_RE = re.compile(
    r"<img\s+[^>]*src=\"\.\/logos\/([^\"]+)\"[^>]*"
    r"alt=\"([^\"]*)\"[^>]*title=\"([^\"]*)\"",
)
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
PAREN_RE = re.compile(r"[（(]([^（）()]+?)[）)]")

SLUG_ALIASES = {
    "AgriculturalBankofChina": "abchina",
    "AustraliaandNewZealandBank": "anz",
    "BankofChina": "boc",
    "BankofCommunications": "bankcomm",
    "BankofEastAsia": "hkbea",
    "BankofMontreal": "bmo",
    "BankSinoPac": "sinopac",
    "CathayUnitedBank": "cathaybk",
    "ChinaBohaiBank": "cbhb",
    "ChinaCITICBank": "citicbank",
    "ChinaConstructionBank": "ccb",
    "ChinaEverbrightBank": "cebbank",
    "ChinaGuangfaBank": "cgbchina",
    "ChinaMerchantsBank": "cmbchina",
    "ChinaMinshengBanking": "cmbc",
    "ChinaZheshangBank": "czbank",
    "Citibank": "citibank",
    "DahSingBank": "dahsing",
    "DBSBank": "dbs",
    "EastWestBank": "eastwestbank",
    "EvergrowingBank": "hfbank",
    "FirstCommercialBank": "firstbank",
    "FubonBank": "fubonchina",
    "HangSengBank": "hangseng",
    "HSBCBank": "hsbc",
    "HuaXiaBank": "hxb",
    "IndustrialandCommercialBankofChina": "icbc",
    "IndustrialBank": "cib",
    "IndustrialBankofKorea": "ibk",
    "JPMorganChaseBank": "jpmorganchina",
    "MalayanBankingBerhad": "maybank",
    "MegaInternationalCommercialBank": "megabank",
    "MUFGBank": "mufg",
    "NanyangCommercialBank": "ncbchina",
    "OCBCBank": "ocbc",
    "PingAnBank": "pingan",
    "PostalSavingsBankofChina": "psbc",
    "RoyalBankofCanada": "rbcroyalbank",
    "ShanghaiPudongDevelopmentBank": "spdb",
    "SocieteGenerale": "societegenerale",
    "StandardCharteredBank": "sc",
    "TheBankofEastAsia": "hkbea",
    "TheBankofNovaScotia": "scotiabank",
    "TheBankofYokohama": "boy",
    "UBS": "ubs",
    "UnitedOverseasBank": "uobchina",
}

FALLBACK_COLORS = (
    "#B81C22",
    "#0F4C81",
    "#0E8F7E",
    "#7A3E98",
    "#B65C18",
    "#2457A6",
    "#1F7A4D",
    "#A52834",
    "#5F4B8B",
    "#C0392B",
    "#2A6F97",
    "#6A994E",
)


@dataclass(frozen=True)
class BankAsset:
    name: str
    color: str
    logo: Path | None
    source: str


def _asset_id(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    safe = "".join(char.lower() if char.isalnum() else "_" for char in value)
    safe = "_".join(part for part in safe.split("_") if part)
    return f"{safe[:42] or 'bank'}_{digest}"


def _slug_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def color_from_text(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    return FALLBACK_COLORS[digest[0] % len(FALLBACK_COLORS)]


def _adjust_color(hex_color: str, factor: float) -> str:
    value = hex_color.lstrip("#")
    rgb = [int(value[index : index + 2], 16) for index in range(0, 6, 2)]
    adjusted = [max(0, min(255, int(channel * factor))) for channel in rgb]
    return "#" + "".join(f"{channel:02X}" for channel in adjusted)


def _extract_theme_color(image: Image.Image, fallback: str) -> str:
    rgba = image.convert("RGBA").resize((80, 80))
    counts: dict[tuple[int, int, int], int] = {}
    for red, green, blue, alpha in rgba.getdata():
        if alpha < 32:
            continue
        if max(red, green, blue) > 238 or max(red, green, blue) < 38:
            continue
        if max(red, green, blue) - min(red, green, blue) < 24:
            continue
        key = (red // 16 * 16, green // 16 * 16, blue // 16 * 16)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return fallback
    red, green, blue = max(counts.items(), key=lambda item: item[1])[0]
    return f"#{red:02X}{green:02X}{blue:02X}"


def _parse_readme_entries(readme_text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for match in README_IMG_RE.finditer(readme_text):
        base = match.group(1).removesuffix(".svg").removesuffix("-rect")
        title = (match.group(2).strip() or match.group(3).strip()).strip()
        if title:
            entries.append((base, title))
    return entries


def _choose_logo_base(
    bank_name: str,
    slug: str,
    readme_entries: list[tuple[str, str]],
    available_bases: set[str],
) -> str | None:
    for base, title in readme_entries:
        if base in available_bases and (
            normalize(bank_name) == normalize(title) or bank_names_match(bank_name, title)
        ):
            return base

    alias = SLUG_ALIASES.get(slug)
    if alias in available_bases:
        return alias

    slug_key = _slug_key(slug)
    by_key = {_slug_key(base): base for base in available_bases}
    if slug_key in by_key:
        return by_key[slug_key]

    candidates = [
        (len(key), base)
        for key, base in by_key.items()
        if len(key) >= 4 and slug_key and (key in slug_key or slug_key in key)
    ]
    if candidates:
        return max(candidates)[1]
    return None


def _render_fallback_logo(path: Path, bank_name: str, color: str) -> None:
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((18, 18, 238, 238), fill=color)
    draw.ellipse((36, 36, 220, 220), outline=(255, 255, 255, 90), width=8)
    label = bank_name[:1] or "银"
    try:
        font = ImageFont.truetype(BytesIO((ASSET_DIR / "原神字体.ttf").read_bytes()), 112)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    draw.text(
        ((256 - (bbox[2] - bbox[0])) / 2, (256 - (bbox[3] - bbox[1])) / 2 - 6),
        label,
        font=font,
        fill=(255, 255, 255, 245),
    )
    image.save(path, format="PNG", optimize=True)


def _convert_svg_to_png(svg_path: Path, output_path: Path) -> Image.Image:
    import cairosvg

    png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=256, output_height=256)
    output_path.write_bytes(png_bytes)
    return Image.open(output_path).convert("RGBA")


def _convert_svg_bytes_to_png(svg_bytes: bytes, output_path: Path) -> Image.Image:
    import cairosvg

    png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=256, output_height=256)
    output_path.write_bytes(png_bytes)
    return Image.open(output_path).convert("RGBA")


def _download_source(timeout: int = 60) -> Path:
    temp_path = Path(tempfile.gettempdir()) / "hibank-bank-logos-main.zip"
    try:
        response = requests.get(SOURCE_URL, timeout=timeout)
        response.raise_for_status()
        temp_path.write_bytes(response.content)
    except requests.RequestException:
        if not temp_path.exists():
            raise
    return temp_path


def _fetch_hibank_logo_mapping(timeout: int = 60) -> dict[str, str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        response = requests.get(HIBANK_BANKS_URL, timeout=timeout, verify=False)
    response.raise_for_status()
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    mapping: dict[str, str] = {}
    for image in soup.find_all("img"):
        alt = str(image.get("alt", "")).strip()
        src = str(image.get("src", "")).strip()
        if alt and src.startswith(HIBANK_LOGO_PREFIX):
            mapping[alt] = src
    return mapping


def _hibank_parent_names(bank_name: str) -> list[str]:
    names: list[str] = []
    for parent_name in PAREN_RE.findall(bank_name):
        parent_name = parent_name.strip()
        if not parent_name:
            continue
        names.append(parent_name)
        if not parent_name.endswith("银行"):
            names.append(parent_name + "银行")
    stripped = PAREN_RE.sub("", bank_name).strip()
    if stripped and stripped != bank_name:
        names.append(stripped)
    return list(dict.fromkeys(names))


def _hibank_name_matches(query: str, known_name: str, loose: bool = False) -> bool:
    if normalize(query) == normalize(known_name) or bank_names_match(query, known_name):
        return True
    if not loose:
        return False
    query_key = normalize(query).removesuffix("银行")
    known_key = normalize(known_name).removesuffix("银行")
    if len(query_key) < 4 or len(known_key) < 4:
        return False
    return query_key.endswith(known_key) or known_key.endswith(query_key)


def _find_hibank_mapping(
    query: str,
    hibank_mapping: Mapping[str, str],
    loose: bool = False,
) -> tuple[str | None, str]:
    direct = hibank_mapping.get(query)
    if direct:
        return direct, query
    for known_name, url in hibank_mapping.items():
        if _hibank_name_matches(query, known_name, loose=loose):
            return url, known_name
    return None, ""


def _choose_hibank_logo_url(
    bank_name: str,
    hibank_mapping: Mapping[str, str],
) -> tuple[str | None, str]:
    direct_url, direct_name = _find_hibank_mapping(bank_name, hibank_mapping)
    if direct_url:
        return direct_url, direct_name

    for parent_name in _hibank_parent_names(bank_name):
        parent_url, mapped_name = _find_hibank_mapping(parent_name, hibank_mapping, loose=True)
        if parent_url:
            return parent_url, mapped_name

    return None, ""


def _download_hibank_logo(url: str, output_path: Path, timeout: int = 30) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        response = requests.get(url, timeout=timeout, verify=False)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "svg" not in content_type and not response.content.lstrip().startswith(b"<svg"):
        raise ValueError("HiBank logo response is not SVG")
    return _convert_svg_bytes_to_png(response.content, output_path)


def _download_hibank_logo_task(
    bank_name: str,
    url: str,
    output_path: Path,
    fallback_color: str,
) -> tuple[str, str]:
    image = _download_hibank_logo(url, output_path)
    return bank_name, _extract_theme_color(image, fallback_color)


def _load_manual_assets() -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    banks = payload.get("banks", {})
    if not isinstance(banks, dict):
        return {}

    manual_assets: dict[str, dict[str, str]] = {}
    for name, value in banks.items():
        if not isinstance(value, dict):
            continue
        if str(value.get("source") or "") != MANUAL_SOURCE_NAME:
            continue
        manual_assets[str(name)] = {
            "logo": str(value.get("logo") or ""),
            "color": str(value.get("color") or color_from_text(str(name))),
            "source": MANUAL_SOURCE_NAME,
            "slug": str(value.get("slug") or ""),
            "logo_base": str(value.get("logo_base") or ""),
            "hibank_name": str(value.get("hibank_name") or ""),
        }
    return manual_assets


def update_bank_icon_assets(bank_records: Iterable[Mapping[str, str]]) -> dict[str, int | str]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    ICONGO_LOGO_DIR.mkdir(parents=True, exist_ok=True)
    HIBANK_LOGO_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACK_LOGO_DIR.mkdir(parents=True, exist_ok=True)
    MANUAL_LOGO_DIR.mkdir(parents=True, exist_ok=True)
    manual_assets = _load_manual_assets()
    for logo_dir in (ICONGO_LOGO_DIR, HIBANK_LOGO_DIR, FALLBACK_LOGO_DIR):
        for old_png in logo_dir.glob("*.png"):
            old_png.unlink()
    zip_path = _download_source()
    hibank_mapping = _fetch_hibank_logo_mapping()

    with tempfile.TemporaryDirectory(prefix="hibank-bank-logos-") as temp_dir:
        extract_dir = Path(temp_dir)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
        source_root = next(extract_dir.glob("bank-logos-*"))
        source_logo_dir = source_root / "logos"
        readme_text = (source_root / "README.md").read_text(encoding="utf-8")
        readme_entries = _parse_readme_entries(readme_text)
        available_bases = {
            path.stem.removesuffix("-rect")
            for path in source_logo_dir.glob("*.svg")
            if not path.stem.endswith("-rect")
        }

        banks: dict[str, dict[str, str]] = dict(manual_assets)
        hibank_tasks: list[dict[str, str]] = []
        icongo_matched = 0
        hibank_matched = 0
        fallback = 0
        failed = 0
        for record in bank_records:
            bank_name = str(record.get("name", "")).strip()
            if not bank_name or bank_name in banks:
                continue
            slug = str(record.get("slug", "")).strip()
            asset_id = _asset_id(bank_name)
            fallback_color = color_from_text(bank_name)
            logo_base = _choose_logo_base(bank_name, slug, readme_entries, available_bases)
            source = "fallback"
            color = fallback_color
            output_name = f"{asset_id}.png"
            logo_value = f"bank_logos/fallback/{output_name}"
            hibank_name = ""
            if logo_base:
                svg_path = source_logo_dir / f"{logo_base}.svg"
                output_path = ICONGO_LOGO_DIR / output_name
                try:
                    image = _convert_svg_to_png(svg_path, output_path)
                    color = _extract_theme_color(image, fallback_color)
                    icongo_matched += 1
                    source = SOURCE_NAME
                    logo_value = f"bank_logos/icongo/{output_name}"
                except Exception:
                    failed += 1
                    logo_base = None

            if source == "fallback":
                hibank_url, hibank_name = _choose_hibank_logo_url(bank_name, hibank_mapping)
                if hibank_url:
                    hibank_tasks.append(
                        {
                            "name": bank_name,
                            "slug": slug,
                            "url": hibank_url,
                            "hibank_name": hibank_name,
                            "output_name": output_name,
                            "fallback_color": fallback_color,
                        }
                    )
                    continue

            if source == "fallback":
                output_path = FALLBACK_LOGO_DIR / output_name
                _render_fallback_logo(output_path, bank_name, fallback_color)
                fallback += 1
                hibank_name = ""

            banks[bank_name] = {
                "logo": logo_value,
                "color": _adjust_color(color, 0.86),
                "source": source,
                "slug": slug,
                "logo_base": logo_base or "",
                "hibank_name": hibank_name or "",
            }

        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {
                executor.submit(
                    _download_hibank_logo_task,
                    task["name"],
                    task["url"],
                    HIBANK_LOGO_DIR / task["output_name"],
                    task["fallback_color"],
                ): task
                for task in hibank_tasks
            }
            for future in as_completed(futures):
                task = futures[future]
                bank_name = task["name"]
                try:
                    _, color = future.result()
                    hibank_matched += 1
                    banks[bank_name] = {
                        "logo": f"bank_logos/hibank/{task['output_name']}",
                        "color": _adjust_color(color, 0.86),
                        "source": HIBANK_SOURCE_NAME,
                        "slug": task["slug"],
                        "logo_base": "",
                        "hibank_name": task["hibank_name"],
                    }
                except Exception:
                    failed += 1
                    fallback += 1
                    output_path = FALLBACK_LOGO_DIR / task["output_name"]
                    _render_fallback_logo(output_path, bank_name, task["fallback_color"])
                    banks[bank_name] = {
                        "logo": f"bank_logos/fallback/{task['output_name']}",
                        "color": _adjust_color(task["fallback_color"], 0.86),
                        "source": "fallback",
                        "slug": task["slug"],
                        "logo_base": "",
                        "hibank_name": task["hibank_name"],
                    }

    payload = {
        "sources": [
            {"name": SOURCE_NAME, "url": SOURCE_REPO, "license": "MIT"},
            {"name": HIBANK_SOURCE_NAME, "url": HIBANK_BANKS_URL, "license": "site-provided logo assets"},
            {"name": MANUAL_SOURCE_NAME, "url": "", "license": "user-provided local assets"},
        ],
        "banks": dict(sorted(banks.items())),
    }
    INDEX_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    load_bank_assets.cache_clear()
    return {
        "total": len(banks),
        "matched": icongo_matched + hibank_matched,
        "icongo": icongo_matched,
        "hibank": hibank_matched,
        "fallback": fallback,
        "manual": len(manual_assets),
        "failed": failed,
        "source": f"{SOURCE_REPO}; {HIBANK_BANKS_URL}",
    }


@lru_cache(maxsize=1)
def load_bank_assets() -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    banks = payload.get("banks", {})
    if not isinstance(banks, dict):
        return {}
    return {
        str(name): value
        for name, value in banks.items()
        if isinstance(value, dict)
    }


def clear_bank_asset_cache() -> None:
    load_bank_assets.cache_clear()


def _asset_logo_path(payload: Mapping[str, str]) -> Path | None:
    logo_value = str(payload.get("logo", "")).strip()
    logo_path = ASSET_DIR / logo_value if logo_value else None
    if logo_path is not None and not logo_path.exists():
        return None
    return logo_path


def _is_real_logo_payload(payload: Mapping[str, str] | None) -> bool:
    return bool(
        payload
        and str(payload.get("source") or "fallback") != "fallback"
        and _asset_logo_path(payload) is not None
    )


def _find_asset_payload(bank_name: str, assets: Mapping[str, dict[str, str]]) -> dict[str, str] | None:
    payload = assets.get(bank_name)
    if payload is not None:
        return payload
    return next(
        (
            value
            for known_name, value in assets.items()
            if bank_names_match(bank_name, known_name)
        ),
        None,
    )


def _find_parent_asset_payload(
    bank_name: str,
    assets: Mapping[str, dict[str, str]],
) -> dict[str, str] | None:
    if "村镇银行" not in bank_name:
        return None
    for parent_name in _hibank_parent_names(bank_name):
        payload = _find_asset_payload(parent_name, assets)
        if _is_real_logo_payload(payload):
            return payload
    return None


def _asset_from_payload(bank_name: str, payload: Mapping[str, str]) -> BankAsset:
    return BankAsset(
        name=bank_name,
        color=str(payload.get("color") or color_from_text(bank_name)),
        logo=_asset_logo_path(payload),
        source=str(payload.get("source") or "fallback"),
    )


def resolve_bank_asset(bank_name: str) -> BankAsset:
    assets = load_bank_assets()
    payload = _find_asset_payload(bank_name, assets)
    if not _is_real_logo_payload(payload):
        parent_payload = _find_parent_asset_payload(bank_name, assets)
        if parent_payload is not None:
            payload = parent_payload
    if payload is None:
        return BankAsset(
            name=bank_name,
            color=color_from_text(bank_name),
            logo=None,
            source="fallback",
        )
    return _asset_from_payload(bank_name, payload)
