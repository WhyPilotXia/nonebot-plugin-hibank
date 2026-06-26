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

PROTECTED_REGION_QUALIFIERS = ("香港", "澳门")


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
        if base and base != text and not has_protected_region_qualifier(text):
            keys.add(normalize(base))
    return {key for key in keys if key}


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
            if long_key.startswith(short_key) or long_key.startswith("中国" + short_key):
                return True
    return False
