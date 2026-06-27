from __future__ import annotations


SUFFIXES = (
    "省",
    "市",
    "自治区",
    "特别行政区",
    "壮族自治区",
    "回族自治区",
    "维吾尔自治区",
    "自治州",
    "地区",
    "盟",
)

PROTECTED_REGION_QUALIFIERS = ("香港", "澳门", "亚洲", "国际")
SYSTEM_NAME_QUALIFIERS = {"企"}


def _protected_qualifier_norms() -> tuple[str, ...]:
    return tuple(normalize(item) for item in PROTECTED_REGION_QUALIFIERS)


def _protected_extension(long_key: str, prefix: str) -> bool:
    if not long_key.startswith(prefix):
        return False
    suffix = long_key[len(prefix) :]
    return any(suffix.startswith(item) for item in _protected_qualifier_norms())


def normalize(value: str) -> str:
    text = str(value).strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    for char in (" ", "\t", "\n", "\r", "　", "-", "_"):
        text = text.replace(char, "")
    for suffix in SUFFIXES:
        text = text.replace(suffix, "")
    return text


def bank_name_match_keys(value: str) -> set[str]:
    text = str(value).strip()
    if not text:
        return set()

    keys = {normalize(text)}
    for separator in ("(", "（"):
        base = text.split(separator, 1)[0].strip()
        if not base or base == text:
            continue
        qualifier = text.split(separator, 1)[1].split(")" if separator == "(" else "）", 1)[0].strip()
        if has_protected_region_qualifier(text):
            keys.add(normalize(base + qualifier))
        else:
            keys.add(normalize(base))
    return {key for key in keys if key}


def canonical_bank_name(value: str) -> str:
    text = str(value).strip()
    for left, right in (("(", ")"), ("（", "）")):
        if not text.endswith(right) or left not in text:
            continue
        base, qualifier = text.rsplit(left, 1)
        qualifier = qualifier[:-1].strip()
        if qualifier in SYSTEM_NAME_QUALIFIERS:
            return base.strip()
    return text


def has_protected_region_qualifier(value: str) -> bool:
    text = str(value)
    for left, right in (("(", ")"), ("（", "）")):
        if left not in text:
            continue
        qualifier = text.split(left, 1)[1].split(right, 1)[0]
        if any(region in qualifier for region in PROTECTED_REGION_QUALIFIERS):
            return True
    return False


def bank_names_match(left: str, right: str) -> bool:
    left_keys = bank_name_match_keys(left)
    right_keys = bank_name_match_keys(right)
    if left_keys & right_keys:
        return True
    if has_protected_region_qualifier(left) or has_protected_region_qualifier(right):
        return False
    for left_key in left_keys:
        for right_key in right_keys:
            short_key, long_key = sorted((left_key, right_key), key=len)
            if len(short_key) < 3:
                continue
            if long_key.startswith(short_key) and not _protected_extension(long_key, short_key):
                return True
            china_prefixed_key = "中国" + short_key
            if long_key.startswith(china_prefixed_key) and not _protected_extension(long_key, china_prefixed_key):
                return True
    return False
