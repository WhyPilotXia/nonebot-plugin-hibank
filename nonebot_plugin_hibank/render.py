from __future__ import annotations

import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .bank_icons import resolve_bank_asset
from .models import BranchDetail, CacheStats, CityDetail, CityRef
from .marks import UserBankMarks
from .names import bank_name_match_keys, bank_names_match


FONT_PATH = Path(__file__).resolve().parent / "assets" / "原神字体.ttf"
SYSTEM_FONT_PATHS = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/opentype/source-han-sans/SourceHanSansCN-Regular.otf"),
)
IMAGE_WIDTH = 1400
MARGIN = 46
LINE_GAP = 12


@lru_cache(maxsize=16)
def _font_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (FONT_PATH, *SYSTEM_FONT_PATHS):
        try:
            if path == FONT_PATH:
                return ImageFont.truetype(BytesIO(_font_bytes(str(path))), size=size)
            if path.exists():
                return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    try:
        return ImageFont.truetype(str(FONT_PATH), size=size)
    except OSError:
        return ImageFont.load_default()


def get_symbol_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in SYSTEM_FONT_PATHS:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return get_font(size)


def text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    text = str(text)
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> str:
    text = str(text)
    if text_width(draw, text, font) <= max_width:
        return text
    suffix = "..."
    left, right = 0, len(text)
    while left < right:
        middle = (left + right + 1) // 2
        candidate = text[:middle] + suffix
        if text_width(draw, candidate, font) <= max_width:
            left = middle
        else:
            right = middle - 1
    return text[:left] + suffix


def new_canvas(height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (IMAGE_WIDTH, height), "#f4f7fb")
    return image, ImageDraw.Draw(image)


def save_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def image_to_base64(image_bytes: bytes) -> str:
    return "base64://" + base64.b64encode(image_bytes).decode("ascii")


def render_city_detail(detail: CityDetail, user_marks: UserBankMarks | None = None) -> bytes:
    title_font = get_font(40)
    info_font = get_font(24)
    section_font = get_font(28)
    item_font = get_font(24)
    small_font = get_font(20)

    probe, draw = new_canvas(10)
    content_width = IMAGE_WIDTH - MARGIN * 2
    category_blocks: list[tuple[str, list[tuple[str, list[str], str | None]]]] = []
    height = 190
    for category, banks in detail.groups.items():
        wrapped = [
            (bank, wrap_text(draw, bank, item_font, content_width - 44), bank_style(bank, user_marks))
            for bank in banks
        ]
        category_blocks.append((category, wrapped))
        height += 56
        height += sum(max(34, len(lines) * 30) + 8 for _, lines, _ in wrapped)
        height += 18
    height += 50

    image, draw = new_canvas(max(360, height))
    y = 34
    draw.text((MARGIN, y), f"{detail.city.city} 银行分布", font=title_font, fill="#172033")
    y += 58
    source = "缓存" if detail.from_cache else "实时"
    draw.text(
        (MARGIN, y),
        f"{detail.city.province} / 共 {detail.total_count} 家 / 数据来源：{source}",
        font=info_font,
        fill="#475467",
    )
    y += 62

    for category, wrapped_items in category_blocks:
        count = len(wrapped_items)
        draw.rounded_rectangle(
            (MARGIN, y, IMAGE_WIDTH - MARGIN, y + 42),
            radius=12,
            fill="#dbeafe",
        )
        draw.text((MARGIN + 18, y + 6), f"{category} ({count})", font=section_font, fill="#12335f")
        y += 56
        for index, (bank, lines, style) in enumerate(wrapped_items, start=1):
            block_height = max(34, len(lines) * 30)
            if index % 2 == 0:
                draw.rounded_rectangle(
                    (MARGIN, y - 2, IMAGE_WIDTH - MARGIN, y + block_height + 4),
                    radius=8,
                    fill="#ffffff",
                )
            draw.text((MARGIN + 14, y), f"{index}.", font=item_font, fill="#667085")
            line_y = y
            for line in lines:
                fill = "#98a2b3" if style == "marked" else "#F780BE" if style == "followed" else "#1f2937"
                draw.text((MARGIN + 58, line_y), line, font=item_font, fill=fill)
                if style == "marked":
                    baseline = line_y + 16
                    draw.line(
                        (MARGIN + 58, baseline, MARGIN + 58 + text_width(draw, line, item_font), baseline),
                        fill=fill,
                        width=2,
                    )
                line_y += 30
            y += block_height + 8
        y += 18

    draw.text(
        (MARGIN, image.height - 36),
        "命令：/bank 网点 <城市> <银行> 可查询网点列表",
        font=small_font,
        fill="#667085",
    )
    return save_png(image)


def bank_style(bank: str, user_marks: UserBankMarks | None) -> str | None:
    if user_marks is None:
        return None
    marked = {
        key
        for item in user_marks.marked
        for key in bank_name_match_keys(item)
    }
    followed = {
        key
        for item in user_marks.followed
        for key in bank_name_match_keys(item)
    }
    current = bank_name_match_keys(bank)
    if current & marked or any(bank_names_match(bank, item) for item in user_marks.marked):
        return "marked"
    if current & followed or any(bank_names_match(bank, item) for item in user_marks.followed):
        return "followed"
    return None


def render_branch_detail(detail: BranchDetail) -> bytes:
    title_font = get_font(38)
    info_font = get_font(23)
    header_font = get_font(23)
    body_font = get_font(21)
    small_font = get_font(19)

    visible = detail.visible_branches
    probe, draw = new_canvas(10)
    content_width = IMAGE_WIDTH - MARGIN * 2
    row_blocks = []
    for item in visible:
        name = str(item.get("org_name", ""))
        county = str(item.get("county", ""))
        address = str(item.get("address", ""))
        address_lines = wrap_text(draw, address, body_font, content_width - 74)
        row_blocks.append((name, county, address_lines))

    height = 220
    for _, _, address_lines in row_blocks:
        height += 82 + len(address_lines) * 28
    height += 56

    image, draw = new_canvas(max(380, height))
    y = 34
    draw.text(
        (MARGIN, y),
        f"{detail.city.city} {detail.bank.name} 网点",
        font=title_font,
        fill="#172033",
    )
    y += 56
    source = "缓存" if detail.from_cache else "实时"
    current_page = min(max(detail.page, 1), detail.total_pages)
    draw.text(
        (MARGIN, y),
        f"共 {detail.total_count} 条 / 第 {current_page}/{detail.total_pages} 页 / 数据来源：{source}",
        font=info_font,
        fill="#475467",
    )
    y += 58

    draw.rounded_rectangle(
        (MARGIN, y, IMAGE_WIDTH - MARGIN, y + 44),
        radius=12,
        fill="#dbeafe",
    )
    draw.text((MARGIN + 18, y + 8), "机构 / 区县 / 地址", font=header_font, fill="#12335f")
    y += 62

    if not row_blocks:
        draw.text((MARGIN + 12, y), "暂无网点数据", font=body_font, fill="#667085")
    for index, (name, county, address_lines) in enumerate(row_blocks, start=(current_page - 1) * detail.page_size + 1):
        block_height = 72 + len(address_lines) * 28
        draw.rounded_rectangle(
            (MARGIN, y, IMAGE_WIDTH - MARGIN, y + block_height),
            radius=12,
            fill="#ffffff" if index % 2 else "#f8fafc",
            outline="#e4e7ec",
            width=1,
        )
        draw.text((MARGIN + 18, y + 14), f"{index}.", font=body_font, fill="#667085")
        shown_name = fit_text(draw, name, header_font, content_width - 220)
        draw.text((MARGIN + 72, y + 12), shown_name, font=header_font, fill="#1f2937")
        draw.text((IMAGE_WIDTH - MARGIN - 150, y + 12), county, font=body_font, fill="#175cd3")
        line_y = y + 48
        for line in address_lines:
            draw.text((MARGIN + 72, line_y), line, font=body_font, fill="#475467")
            line_y += 28
        y += block_height + 12

    draw.text(
        (MARGIN, image.height - 36),
        "翻页：/bank 网点 <城市> <银行> <页码>",
        font=small_font,
        fill="#667085",
    )
    return save_png(image)


def render_city_search(keyword: str, results: list[CityRef]) -> bytes:
    rows = [f"{item.province} {item.city}  /cities/{item.province_code}/{item.city_slug}" for item in results]
    return render_simple_list(f"城市搜索：{keyword}", rows or ["未找到匹配城市"])


def render_bank_search(keyword: str, results: list[str]) -> bytes:
    return render_simple_list(f"银行搜索：{keyword}", results or ["未找到匹配银行"])


def render_mark_list(title: str, banks: list[str]) -> bytes:
    rows = banks or ["暂无"]
    return render_simple_list(title, rows)


def render_grouped_mark_list(
    title: str,
    grouped_banks: dict[str, list[str]],
    unmatched_banks: list[str],
    kind: str,
) -> bytes:
    title_font = get_font(40)
    info_font = get_font(24)
    section_font = get_font(28)
    item_font = get_font(24)
    small_font = get_font(20)

    probe, draw = new_canvas(10)
    content_width = IMAGE_WIDTH - MARGIN * 2
    sections = [
        (category, banks)
        for category, banks in grouped_banks.items()
        if banks
    ]
    if unmatched_banks:
        sections.append(("其他", unmatched_banks))

    section_blocks: list[tuple[str, list[tuple[str, list[str]]]]] = []
    height = 190
    if not sections:
        height += 64
    for category, banks in sections:
        wrapped = [
            (bank, wrap_text(draw, bank, item_font, content_width - 44))
            for bank in banks
        ]
        section_blocks.append((category, wrapped))
        height += 56
        height += sum(max(34, len(lines) * 30) + 8 for _, lines in wrapped)
        height += 18
    height += 50

    image, draw = new_canvas(max(360, height))
    y = 34
    draw.text((MARGIN, y), title, font=title_font, fill="#172033")
    y += 58
    hit_count = sum(len(banks) for banks in grouped_banks.values())
    total_count = hit_count + len(unmatched_banks)
    draw.text(
        (MARGIN, y),
        f"已分类 {hit_count} 个 / 列表 {total_count} 个",
        font=info_font,
        fill="#475467",
    )
    y += 62

    if not section_blocks:
        draw.rounded_rectangle(
            (MARGIN, y, IMAGE_WIDTH - MARGIN, y + 50),
            radius=10,
            fill="#ffffff",
        )
        draw.text((MARGIN + 20, y + 10), "暂无", font=item_font, fill="#667085")
    for category, wrapped_items in section_blocks:
        count = len(wrapped_items)
        draw.rounded_rectangle(
            (MARGIN, y, IMAGE_WIDTH - MARGIN, y + 42),
            radius=12,
            fill="#dbeafe",
        )
        draw.text((MARGIN + 18, y + 6), f"{category} ({count})", font=section_font, fill="#12335f")
        y += 56
        for index, (bank, lines) in enumerate(wrapped_items, start=1):
            block_height = max(34, len(lines) * 30)
            if index % 2 == 0:
                draw.rounded_rectangle(
                    (MARGIN, y - 2, IMAGE_WIDTH - MARGIN, y + block_height + 4),
                    radius=8,
                    fill="#ffffff",
                )
            draw.text((MARGIN + 14, y), f"{index}.", font=item_font, fill="#667085")
            line_y = y
            fill = "#98a2b3" if kind == "marked" else "#F780BE"
            for line in lines:
                draw.text((MARGIN + 58, line_y), line, font=item_font, fill=fill)
                if kind == "marked":
                    baseline = line_y + 16
                    draw.line(
                        (MARGIN + 58, baseline, MARGIN + 58 + text_width(draw, line, item_font), baseline),
                        fill=fill,
                        width=2,
                    )
                line_y += 30
            y += block_height + 8
        y += 18

    draw.text((MARGIN, image.height - 36), "HiBank", font=small_font, fill="#98a2b3")
    return save_png(image)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        return (63, 86, 130)
    try:
        return tuple(int(value[index : index + 2], 16) for index in range(0, 6, 2))
    except ValueError:
        return (63, 86, 130)


def _mix_rgb(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    return tuple(int(start[index] * (1 - ratio) + end[index] * ratio) for index in range(3))


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    size: int,
    max_width: int,
    min_size: int = 24,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    current = size
    while current > min_size:
        font = get_font(current)
        if text_width(draw, text, font) <= max_width:
            return font
        current -= 2
    return get_font(min_size)


def _load_logo(path: Path | None, size: int) -> Image.Image | None:
    if path is None:
        return None
    try:
        logo = Image.open(path).convert("RGBA")
    except OSError:
        return None
    logo.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(logo, ((size - logo.width) // 2, (size - logo.height) // 2))
    return canvas


def _white_watermark(logo: Image.Image, size: int, alpha: int) -> Image.Image:
    source = logo.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
    mask = source.getchannel("A")
    white = Image.new("RGBA", (size, size), (255, 255, 255, alpha))
    white.putalpha(mask.point(lambda value: int(value * alpha / 255)))
    return white


def _draw_card_background(
    card: Image.Image,
    base_color: str,
    radius: int,
) -> Image.Image:
    base_rgb = _hex_to_rgb(base_color)
    darker = _mix_rgb(base_rgb, (0, 0, 0), 0.20)
    lighter = _mix_rgb(base_rgb, (255, 255, 255), 0.08)
    width, height = card.size
    gradient = Image.new("RGBA", card.size, (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for x in range(width):
        ratio = x / max(1, width - 1)
        color = _mix_rgb(lighter, darker, ratio)
        gradient_draw.line((x, 0, x, height), fill=(*color, 255))
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
    card.alpha_composite(gradient)
    card.putalpha(mask)
    return mask


def _draw_fallback_symbol(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    bank: str,
) -> None:
    x1, y1, x2, y2 = box
    label = bank[:1] or "银"
    font = get_font(56)
    bbox = draw.textbbox((0, 0), label, font=font)
    draw.text(
        (x1 + (x2 - x1 - (bbox[2] - bbox[0])) / 2, y1 + (y2 - y1 - (bbox[3] - bbox[1])) / 2 - 3),
        label,
        font=font,
        fill=(255, 255, 255, 230),
    )


def _render_bank_card(bank: str, kind: str, width: int, height: int) -> Image.Image:
    asset = resolve_bank_asset(bank)
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    _draw_card_background(card, asset.color, radius=20)
    draw = ImageDraw.Draw(card)

    logo_size = min(82, max(66, width // 8))
    logo = _load_logo(asset.logo, logo_size)
    if logo is not None:
        watermark_size = min(300, max(210, width // 2))
        watermark = _white_watermark(logo, watermark_size, 34)
        card.alpha_composite(watermark, (width - watermark_size - 34, -20))

    icon_x = 36
    icon_y = 36
    icon_box = (icon_x, icon_y, icon_x + logo_size, icon_y + logo_size)
    if logo is not None:
        card.alpha_composite(logo, (icon_x, icon_y))
    else:
        _draw_fallback_symbol(draw, icon_box, bank)

    text_x = icon_x + logo_size + 22
    text_width_limit = max(220, width - text_x - 34)
    name_font = _fit_font(draw, bank, 34, text_width_limit, 22)
    desc_font = get_font(22)
    number_font = get_symbol_font(30)
    draw.text((text_x, 36), bank, font=name_font, fill=(255, 255, 255, 248))
    draw.text((text_x, 82), "储蓄卡", font=desc_font, fill=(255, 255, 255, 205))

    number = "••••  ••••  ••••  ••••"
    draw.text((text_x, height - 64), number, font=number_font, fill=(255, 255, 255, 235))
    return card


def render_card_pack_mark_list(
    title: str,
    grouped_banks: dict[str, list[str]],
    unmatched_banks: list[str],
    kind: str,
) -> bytes:
    title_font = get_font(40)
    info_font = get_font(24)
    section_font = get_font(25)
    empty_font = get_font(26)
    small_font = get_font(20)

    sections = [(category, banks) for category, banks in grouped_banks.items() if banks]
    if unmatched_banks:
        sections.append(("其他", unmatched_banks))
    total_count = sum(len(banks) for _, banks in sections)
    classified_count = sum(len(banks) for banks in grouped_banks.values())

    column_gap = 24
    card_width = (IMAGE_WIDTH - MARGIN * 2 - column_gap) // 2
    card_height = 172
    card_gap = 24
    section_gap = 24
    height = 174
    if not sections:
        height += 96
    for _, banks in sections:
        row_count = (len(banks) + 1) // 2
        height += 46 + row_count * (card_height + card_gap) + section_gap
    height += 52

    image = Image.new("RGBA", (IMAGE_WIDTH, max(360, height)), "#f2f3f5")
    draw = ImageDraw.Draw(image)
    y = 34
    draw.text((MARGIN, y), title, font=title_font, fill="#111827")
    y += 58
    draw.text(
        (MARGIN, y),
        f"共 {total_count} 张 / 已分类 {classified_count} 张",
        font=info_font,
        fill="#667085",
    )
    y += 66

    if not sections:
        draw.rounded_rectangle(
            (MARGIN, y, IMAGE_WIDTH - MARGIN, y + 76),
            radius=18,
            fill="#ffffff",
        )
        draw.text((MARGIN + 28, y + 21), "暂无", font=empty_font, fill="#667085")
    for category, banks in sections:
        draw.text(
            (MARGIN + 4, y),
            f"{category} · {len(banks)} 张",
            font=section_font,
            fill="#475467",
        )
        y += 46
        for index, bank in enumerate(banks):
            column = index % 2
            if column == 0 and index:
                y += card_height + card_gap
            x = MARGIN + column * (card_width + column_gap)
            card = _render_bank_card(bank, kind, card_width, card_height)
            image.alpha_composite(card, (x, y))
        if banks:
            y += card_height + card_gap
        y += section_gap

    draw.text((MARGIN, image.height - 34), "HiBank", font=small_font, fill="#98a2b3")
    return save_png(image)


def render_cache_stats(stats: CacheStats) -> bytes:
    rows = [
        f"城市索引缓存：{'已缓存' if stats.indexes_cached else '未缓存'}",
        f"城市银行列表缓存：{stats.city_cache_count} 个",
        f"网点列表缓存：{stats.branch_cache_count} 个",
        f"缓存目录：{stats.cache_dir}",
    ]
    return render_simple_list("HiBank 缓存状态", rows)


def render_help() -> bytes:
    rows = [
        "/bank 帮助 | /bank -h | /bank --help",
        "/bank 城市 <城市名> | /银行 <城市名>",
        "/bank 网点 <城市名> <银行名> [页码] | /网点 <城市名> <银行名> [页码]",
        "/bank 搜城市 <关键词> | /搜城市 <关键词>",
        "/bank 搜银行 <关键词> | /搜银行 <关键词>",
        "/<标记/关注> <银行名...> 或 /<mark/follow> <银行名...>",
        "/<取消标记/取消关注> <银行名...> 或 /<unmark/unfollow> <银行名...>",
        "/<批量标记/批量关注> <城市名> <分类>",
        "/<批量取消标记/批量取消关注> <城市名> <分类>",
        "/<复制标记/复制关注> <@用户/QQ号>",
        "/<标记列表/关注列表>",
        "/更新银行图标（仅超级用户）",
        "/bank 缓存",
        "/bank 清缓存",
    ]
    return render_simple_list("HiBank 命令帮助", rows)


def render_simple_list(title: str, rows: Iterable[str]) -> bytes:
    title_font = get_font(38)
    row_font = get_font(24)
    small_font = get_font(19)
    row_list = list(rows)
    probe, draw = new_canvas(10)
    content_width = IMAGE_WIDTH - MARGIN * 2 - 40
    wrapped_rows = [wrap_text(draw, row, row_font, content_width) for row in row_list]
    height = 150 + sum(max(42, len(lines) * 31) + 12 for lines in wrapped_rows) + 42
    image, draw = new_canvas(max(280, height))
    y = 34
    draw.text((MARGIN, y), title, font=title_font, fill="#172033")
    y += 66
    for index, lines in enumerate(wrapped_rows, start=1):
        block_height = max(42, len(lines) * 31)
        draw.rounded_rectangle(
            (MARGIN, y - 4, IMAGE_WIDTH - MARGIN, y + block_height + 6),
            radius=10,
            fill="#ffffff" if index % 2 else "#f8fafc",
        )
        line_y = y
        for line in lines:
            draw.text((MARGIN + 20, line_y), line, font=row_font, fill="#1f2937")
            line_y += 31
        y += block_height + 12
    draw.text((MARGIN, image.height - 34), "HiBank", font=small_font, fill="#98a2b3")
    return save_png(image)
