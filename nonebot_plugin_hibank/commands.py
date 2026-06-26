from __future__ import annotations

import re

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.exception import FinishedException, PausedException, RejectedException
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.typing import T_State

from .client import HibankError, client, normalize
from .marks import (
    MarkKind,
    add_user_banks,
    get_user_marks,
    remove_user_banks,
    set_user_banks,
)
from .render import (
    image_to_base64,
    render_bank_search,
    render_branch_detail,
    render_cache_stats,
    render_city_detail,
    render_city_search,
    render_help,
    render_mark_list,
)


PAGE_RE = re.compile(r"\s+(\d+)$")
HELP_ARGS = {"帮助", "-h", "--help", "help"}


bank_command = on_command("bank", priority=5, block=True)
city_command = on_command("银行", priority=5, block=True)
branch_command = on_command("网点", priority=5, block=True)
search_city_command = on_command("搜城市", priority=5, block=True)
search_bank_command = on_command("搜银行", priority=5, block=True)
mark_command = on_command("标记", aliases={"mark"}, priority=5, block=True)
unmark_command = on_command("取消标记", aliases={"unmark"}, priority=5, block=True)
mark_list_command = on_command("标记列表", priority=5, block=True)
follow_command = on_command("关注", aliases={"follow"}, priority=5, block=True)
unfollow_command = on_command("取消关注", aliases={"unfollow"}, priority=5, block=True)
follow_list_command = on_command("关注列表", priority=5, block=True)
batch_mark_command = on_command("批量标记", priority=5, block=True)
batch_follow_command = on_command("批量关注", priority=5, block=True)
batch_unmark_command = on_command("批量取消标记", priority=5, block=True)
batch_unfollow_command = on_command("批量取消关注", priority=5, block=True)
copy_mark_command = on_command("复制标记", priority=5, block=True)
copy_follow_command = on_command("复制关注", priority=5, block=True)

FLOW_EXCEPTIONS = (FinishedException, PausedException, RejectedException)


def image_segment(image_bytes: bytes) -> MessageSegment:
    return MessageSegment.image(image_to_base64(image_bytes))


def split_city_bank_page(argument: str) -> tuple[str, str, int]:
    text = " ".join(argument.strip().split())
    page = 1
    page_match = PAGE_RE.search(text)
    if page_match:
        page = int(page_match.group(1))
        text = text[: page_match.start()].strip()
    parts = text.split()
    if len(parts) < 2:
        raise HibankError("用法：/bank 网点 <城市名> <银行名> [页码]")
    if len(parts) == 2:
        return parts[0], parts[1], page
    # 支持 “四川 成都 成都银行”。
    return " ".join(parts[:2]), " ".join(parts[2:]), page


async def finish_image(matcher, image_bytes: bytes) -> None:
    await matcher.finish(image_segment(image_bytes))


async def send_city_detail(matcher, city_query: str, event: MessageEvent | None = None) -> None:
    if not city_query:
        await matcher.finish("请提供城市名，例如：/银行 成都")
    city = await client.resolve_city(city_query)
    detail = await client.get_city_detail(city)
    user_marks = get_user_marks(event.get_user_id()) if event is not None else None
    await finish_image(matcher, render_city_detail(detail, user_marks))


async def send_branch_detail(matcher, argument: str) -> None:
    city_query, bank_query, page = split_city_bank_page(argument)
    city = await client.resolve_city(city_query)
    detail = await client.get_branch_detail(city, bank_query, page)
    await finish_image(matcher, render_branch_detail(detail))


@bank_command.handle()
async def handle_bank(event: MessageEvent, args: Message = CommandArg()) -> None:
    raw = args.extract_plain_text().strip()
    if not raw or raw in HELP_ARGS:
        await finish_image(bank_command, render_help())

    action, _, rest = raw.partition(" ")
    action = action.strip()
    rest = rest.strip()

    try:
        if action == "城市":
            await send_city_detail(bank_command, rest, event)

        if action == "网点":
            await send_branch_detail(bank_command, rest)

        if action == "搜城市":
            if not rest:
                await bank_command.finish("请提供关键词，例如：/bank 搜城市 成都")
            results = await client.search_cities(rest)
            await finish_image(bank_command, render_city_search(rest, results))

        if action == "搜银行":
            if not rest:
                await bank_command.finish("请提供关键词，例如：/bank 搜银行 农商")
            results = await client.search_banks(rest)
            await finish_image(bank_command, render_bank_search(rest, results))

        if action == "缓存":
            await finish_image(bank_command, render_cache_stats(client.get_cache_stats()))

        if action == "清缓存":
            await client.clear_cache()
            await bank_command.finish("HiBank 缓存已清除。")

        await finish_image(bank_command, render_help())
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await bank_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 命令处理失败")
        await bank_command.finish(f"HiBank 查询失败：{exc}")


@city_command.handle()
async def handle_city(event: MessageEvent, args: Message = CommandArg()) -> None:
    city_query = args.extract_plain_text().strip()
    try:
        await send_city_detail(city_command, city_query, event)
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await city_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 城市查询失败")
        await city_command.finish(f"HiBank 城市查询失败：{exc}")


@branch_command.handle()
async def handle_branch(args: Message = CommandArg()) -> None:
    argument = args.extract_plain_text().strip()
    try:
        await send_branch_detail(branch_command, argument)
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await branch_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 网点查询失败")
        await branch_command.finish(f"HiBank 网点查询失败：{exc}")


@search_city_command.handle()
async def handle_search_city(args: Message = CommandArg()) -> None:
    keyword = args.extract_plain_text().strip()
    if not keyword:
        await search_city_command.finish("请提供关键词，例如：/搜城市 成都")
    try:
        results = await client.search_cities(keyword)
        await finish_image(search_city_command, render_city_search(keyword, results))
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await search_city_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 搜城市失败")
        await search_city_command.finish(f"HiBank 搜城市失败：{exc}")


@search_bank_command.handle()
async def handle_search_bank(args: Message = CommandArg()) -> None:
    keyword = args.extract_plain_text().strip()
    if not keyword:
        await search_bank_command.finish("请提供关键词，例如：/搜银行 农商")
    try:
        results = await client.search_banks(keyword)
        await finish_image(search_bank_command, render_bank_search(keyword, results))
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await search_bank_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 搜银行失败")
        await search_bank_command.finish(f"HiBank 搜银行失败：{exc}")


def parse_bank_names(argument: str) -> list[str]:
    return [part for part in " ".join(argument.strip().split()).split(" ") if part]


def mark_kind_name(kind: MarkKind) -> str:
    return "标记" if kind == "marked" else "关注"


def mark_kind_list_title(kind: MarkKind, user_id: str) -> str:
    return f"{user_id} 的{mark_kind_name(kind)}列表"


def parse_batch_argument(argument: str, kind: MarkKind) -> tuple[str, str]:
    parts = parse_bank_names(argument)
    if len(parts) < 2:
        raise HibankError(
            f"用法：/批量{mark_kind_name(kind)} <城市名> <分类>，例如：/批量{mark_kind_name(kind)} 成都 全国性"
        )
    return " ".join(parts[:-1]), parts[-1]


def find_category_banks(groups: dict[str, list[str]], category_query: str) -> tuple[str, list[str]]:
    target = normalize(category_query)
    for category, banks in groups.items():
        if normalize(category) == target:
            return category, banks
    for category, banks in groups.items():
        category_norm = normalize(category)
        if target in category_norm or category_norm in target:
            return category, banks
    available = "、".join(groups.keys()) or "暂无分类"
    raise HibankError(f"未找到分类：{category_query}。可用分类：{available}")


def extract_target_user_id(args: Message) -> str:
    for segment in args:
        if segment.type == "at":
            qq = str(segment.data.get("qq", "")).strip()
            if qq and qq != "all":
                return qq
    plain = args.extract_plain_text()
    match = re.search(r"\d{5,12}", plain)
    if match:
        return match.group(0)
    raise HibankError("请指定一个 QQ，例如：/复制标记 @某人 或 /复制标记 123456")


def copy_prompt_message(kind: MarkKind, source_user_id: str, source_banks: list[str], self_empty: bool) -> Message:
    if self_empty:
        text = f"对方{mark_kind_name(kind)}列表如下。回复“复制”写入本账号，回复“取消”放弃。"
    else:
        text = (
            f"对方{mark_kind_name(kind)}列表如下。"
            "你已有本地数据，回复“合并”取并集，回复“复制”覆盖本账号，回复“取消”放弃。"
        )
    return (
        MessageSegment.text(text + "\n")
        + image_segment(render_mark_list(mark_kind_list_title(kind, source_user_id), source_banks))
    )


async def handle_add_marks(
    matcher,
    event: MessageEvent,
    state: T_State,
    argument: str,
    kind: MarkKind,
) -> None:
    banks = parse_bank_names(argument)
    if not banks:
        await matcher.finish(f"请提供银行名，例如：/{mark_kind_name(kind)} 成都银行 南京银行")
    known, unknown = await client.split_known_banks(banks)
    if unknown:
        state["hibank_mark_kind"] = kind
        state["hibank_mark_banks"] = known + unknown
        state["hibank_mark_known"] = known
        state["hibank_mark_unknown"] = unknown
        await matcher.pause(
            "以下银行未在全局索引和已缓存城市中找到，回复“确认”仍然写入，回复其他内容取消："
            + "、".join(unknown)
        )
    added = add_user_banks(event.get_user_id(), kind, known)
    await matcher.finish(f"已{mark_kind_name(kind)} {len(known)} 个银行，新增 {added} 个。")


async def handle_add_marks_confirm(
    matcher,
    event: MessageEvent,
    state: T_State,
    answer: str,
) -> None:
    kind = state.get("hibank_mark_kind")
    banks = state.get("hibank_mark_banks", [])
    unknown = state.get("hibank_mark_unknown", [])
    if kind not in {"marked", "followed"} or not isinstance(banks, list):
        await matcher.finish("没有待确认的银行。")
    if answer.strip() == "确认":
        added = add_user_banks(event.get_user_id(), kind, [str(item) for item in banks])
        await matcher.finish(
            f"已确认并{mark_kind_name(kind)} {len(banks)} 个银行，新增 {added} 个。"
        )
    await matcher.finish("已取消，未写入：" + "、".join(str(item) for item in unknown))


async def handle_remove_marks(
    matcher,
    event: MessageEvent,
    argument: str,
    kind: MarkKind,
) -> None:
    banks = parse_bank_names(argument)
    if not banks:
        await matcher.finish(f"请提供银行名，例如：/取消{mark_kind_name(kind)} 成都银行")
    removed = remove_user_banks(event.get_user_id(), kind, banks)
    await matcher.finish(f"已取消{mark_kind_name(kind)} {len(banks)} 个银行，实际移除 {removed} 个。")


async def handle_batch_marks(
    matcher,
    event: MessageEvent,
    argument: str,
    kind: MarkKind,
    remove: bool = False,
) -> None:
    city_query, category_query = parse_batch_argument(argument, kind)
    city = await client.resolve_city(city_query)
    detail = await client.get_city_detail(city)
    category, banks = find_category_banks(detail.groups, category_query)
    if not banks:
        await matcher.finish(f"{detail.city.city} {category} 分类下暂无银行。")
    if remove:
        changed = remove_user_banks(event.get_user_id(), kind, banks)
        await matcher.finish(
            f"已批量取消{mark_kind_name(kind)}：{detail.city.city} {category} {len(banks)} 个银行，实际移除 {changed} 个。"
        )
    changed = add_user_banks(event.get_user_id(), kind, banks)
    await matcher.finish(
        f"已批量{mark_kind_name(kind)}：{detail.city.city} {category} {len(banks)} 个银行，新增 {changed} 个。"
    )


async def handle_copy_marks(
    matcher,
    event: MessageEvent,
    state: T_State,
    args: Message,
    kind: MarkKind,
) -> None:
    source_user_id = extract_target_user_id(args)
    target_user_id = event.get_user_id()
    if source_user_id == target_user_id:
        await matcher.finish(f"不能复制自己的{mark_kind_name(kind)}列表。")
    source_marks = get_user_marks(source_user_id)
    source_banks = sorted(source_marks.marked if kind == "marked" else source_marks.followed)
    if not source_banks:
        await matcher.finish(f"对方{mark_kind_name(kind)}列表为空。")

    target_marks = get_user_marks(target_user_id)
    target_banks = sorted(target_marks.marked if kind == "marked" else target_marks.followed)
    self_empty = not target_banks
    state["hibank_copy_kind"] = kind
    state["hibank_copy_source_user_id"] = source_user_id
    state["hibank_copy_source_banks"] = source_banks
    state["hibank_copy_target_banks"] = target_banks
    state["hibank_copy_self_empty"] = self_empty
    await matcher.pause(copy_prompt_message(kind, source_user_id, source_banks, self_empty))


async def handle_copy_marks_confirm(
    matcher,
    event: MessageEvent,
    state: T_State,
    answer: str,
) -> None:
    kind = state.get("hibank_copy_kind")
    source_banks = state.get("hibank_copy_source_banks", [])
    target_banks = state.get("hibank_copy_target_banks", [])
    self_empty = bool(state.get("hibank_copy_self_empty"))
    action = answer.strip()
    if kind not in {"marked", "followed"} or not isinstance(source_banks, list):
        await matcher.finish("没有待复制的数据。")
    if action == "取消":
        await matcher.finish("已取消，未写入。")
    if self_empty:
        if action != "复制":
            await matcher.reject("请回复“复制”或“取消”。")
        count = set_user_banks(event.get_user_id(), kind, [str(item) for item in source_banks])
        await matcher.finish(f"已复制{mark_kind_name(kind)}列表，共 {count} 个银行。")
    if action == "合并":
        merged = sorted({str(item) for item in source_banks} | {str(item) for item in target_banks})
        count = set_user_banks(event.get_user_id(), kind, merged)
        await matcher.finish(f"已合并{mark_kind_name(kind)}列表，共 {count} 个银行。")
    if action == "复制":
        count = set_user_banks(event.get_user_id(), kind, [str(item) for item in source_banks])
        await matcher.finish(f"已复制{mark_kind_name(kind)}列表，共 {count} 个银行。")
    await matcher.reject("请回复“合并”“复制”或“取消”。")


@mark_command.handle()
async def handle_mark(
    event: MessageEvent,
    state: T_State,
    args: Message = CommandArg(),
) -> None:
    try:
        await handle_add_marks(mark_command, event, state, args.extract_plain_text(), "marked")
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await mark_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 标记失败")
        await mark_command.finish(f"HiBank 标记失败：{exc}")


@mark_command.handle()
async def handle_mark_confirm(event: MessageEvent, state: T_State) -> None:
    try:
        await handle_add_marks_confirm(mark_command, event, state, event.get_plaintext())
    except FLOW_EXCEPTIONS:
        raise
    except Exception as exc:
        logger.exception("HiBank 标记确认失败")
        await mark_command.finish(f"HiBank 标记确认失败：{exc}")


@follow_command.handle()
async def handle_follow(
    event: MessageEvent,
    state: T_State,
    args: Message = CommandArg(),
) -> None:
    try:
        await handle_add_marks(follow_command, event, state, args.extract_plain_text(), "followed")
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await follow_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 关注失败")
        await follow_command.finish(f"HiBank 关注失败：{exc}")


@follow_command.handle()
async def handle_follow_confirm(event: MessageEvent, state: T_State) -> None:
    try:
        await handle_add_marks_confirm(follow_command, event, state, event.get_plaintext())
    except FLOW_EXCEPTIONS:
        raise
    except Exception as exc:
        logger.exception("HiBank 关注确认失败")
        await follow_command.finish(f"HiBank 关注确认失败：{exc}")


@unmark_command.handle()
async def handle_unmark(event: MessageEvent, args: Message = CommandArg()) -> None:
    try:
        await handle_remove_marks(unmark_command, event, args.extract_plain_text(), "marked")
    except FLOW_EXCEPTIONS:
        raise
    except Exception as exc:
        logger.exception("HiBank 取消标记失败")
        await unmark_command.finish(f"HiBank 取消标记失败：{exc}")


@unfollow_command.handle()
async def handle_unfollow(event: MessageEvent, args: Message = CommandArg()) -> None:
    try:
        await handle_remove_marks(unfollow_command, event, args.extract_plain_text(), "followed")
    except FLOW_EXCEPTIONS:
        raise
    except Exception as exc:
        logger.exception("HiBank 取消关注失败")
        await unfollow_command.finish(f"HiBank 取消关注失败：{exc}")


@batch_mark_command.handle()
async def handle_batch_mark(event: MessageEvent, args: Message = CommandArg()) -> None:
    try:
        await handle_batch_marks(batch_mark_command, event, args.extract_plain_text(), "marked")
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await batch_mark_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 批量标记失败")
        await batch_mark_command.finish(f"HiBank 批量标记失败：{exc}")


@batch_follow_command.handle()
async def handle_batch_follow(event: MessageEvent, args: Message = CommandArg()) -> None:
    try:
        await handle_batch_marks(batch_follow_command, event, args.extract_plain_text(), "followed")
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await batch_follow_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 批量关注失败")
        await batch_follow_command.finish(f"HiBank 批量关注失败：{exc}")


@batch_unmark_command.handle()
async def handle_batch_unmark(event: MessageEvent, args: Message = CommandArg()) -> None:
    try:
        await handle_batch_marks(
            batch_unmark_command,
            event,
            args.extract_plain_text(),
            "marked",
            remove=True,
        )
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await batch_unmark_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 批量取消标记失败")
        await batch_unmark_command.finish(f"HiBank 批量取消标记失败：{exc}")


@batch_unfollow_command.handle()
async def handle_batch_unfollow(event: MessageEvent, args: Message = CommandArg()) -> None:
    try:
        await handle_batch_marks(
            batch_unfollow_command,
            event,
            args.extract_plain_text(),
            "followed",
            remove=True,
        )
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await batch_unfollow_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 批量取消关注失败")
        await batch_unfollow_command.finish(f"HiBank 批量取消关注失败：{exc}")


@copy_mark_command.handle()
async def handle_copy_mark(
    event: MessageEvent,
    state: T_State,
    args: Message = CommandArg(),
) -> None:
    try:
        await handle_copy_marks(copy_mark_command, event, state, args, "marked")
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await copy_mark_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 复制标记失败")
        await copy_mark_command.finish(f"HiBank 复制标记失败：{exc}")


@copy_mark_command.handle()
async def handle_copy_mark_confirm(event: MessageEvent, state: T_State) -> None:
    try:
        await handle_copy_marks_confirm(copy_mark_command, event, state, event.get_plaintext())
    except FLOW_EXCEPTIONS:
        raise
    except Exception as exc:
        logger.exception("HiBank 复制标记确认失败")
        await copy_mark_command.finish(f"HiBank 复制标记确认失败：{exc}")


@copy_follow_command.handle()
async def handle_copy_follow(
    event: MessageEvent,
    state: T_State,
    args: Message = CommandArg(),
) -> None:
    try:
        await handle_copy_marks(copy_follow_command, event, state, args, "followed")
    except FLOW_EXCEPTIONS:
        raise
    except HibankError as exc:
        await copy_follow_command.finish(str(exc))
    except Exception as exc:
        logger.exception("HiBank 复制关注失败")
        await copy_follow_command.finish(f"HiBank 复制关注失败：{exc}")


@copy_follow_command.handle()
async def handle_copy_follow_confirm(event: MessageEvent, state: T_State) -> None:
    try:
        await handle_copy_marks_confirm(copy_follow_command, event, state, event.get_plaintext())
    except FLOW_EXCEPTIONS:
        raise
    except Exception as exc:
        logger.exception("HiBank 复制关注确认失败")
        await copy_follow_command.finish(f"HiBank 复制关注确认失败：{exc}")


@mark_list_command.handle()
async def handle_mark_list(event: MessageEvent) -> None:
    marks = get_user_marks(event.get_user_id())
    await finish_image(mark_list_command, render_mark_list("已标记银行", sorted(marks.marked)))


@follow_list_command.handle()
async def handle_follow_list(event: MessageEvent) -> None:
    marks = get_user_marks(event.get_user_id())
    await finish_image(follow_list_command, render_mark_list("已关注银行", sorted(marks.followed)))
