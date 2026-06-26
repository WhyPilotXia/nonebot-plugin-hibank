from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .models import BranchDetail, CacheStats, CityDetail, CityRef
from .marks import UserBankMarks


FONT_PATH = Path(__file__).resolve().parent / "assets" / "原神字体.ttf"
IMAGE_WIDTH = 1400
MARGIN = 46
LINE_GAP = 12


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size=size)
    except OSError:
        return ImageFont.load_default()


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
    marked = {normalize_mark_name(item) for item in user_marks.marked}
    followed = {normalize_mark_name(item) for item in user_marks.followed}
    current = normalize_mark_name(bank)
    if current in marked:
        return "marked"
    if current in followed:
        return "followed"
    return None


def normalize_mark_name(value: str) -> str:
    return str(value).strip().lower().replace(" ", "").replace("　", "")


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
        "/bank 城市 <城市名>",
        "/bank 网点 <城市名> <银行名> [页码]",
        "/银行 <城市名>",
        "/网点 <城市名> <银行名> [页码]",
        "/标记 <银行名...> 或 /mark <银行名...>",
        "/取消标记 <银行名...> 或 /unmark <银行名...>",
        "/批量标记 <城市名> <分类>",
        "/批量取消标记 <城市名> <分类>",
        "/复制标记 <@用户/QQ号>",
        "/标记列表",
        "/关注 <银行名...> 或 /follow <银行名...>",
        "/取消关注 <银行名...> 或 /unfollow <银行名...>",
        "/批量关注 <城市名> <分类>",
        "/批量取消关注 <城市名> <分类>",
        "/复制关注 <@用户/QQ号>",
        "/关注列表",
        "/bank 搜城市 <关键词>",
        "/bank 搜银行 <关键词>",
        "/bank 缓存",
        "/bank 清缓存",
        "/搜城市 <关键词>",
        "/搜银行 <关键词>",
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
