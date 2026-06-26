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
        if base and base != text:
            keys.add(normalize(base))
    return {key for key in keys if key}
