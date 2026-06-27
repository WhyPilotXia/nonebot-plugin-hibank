from __future__ import annotations

from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_localstore")

from .config import HibankConfig  # noqa: E402

__plugin_meta__ = PluginMetadata(
    name="HiBank 城市银行查询",
    description="查询 HiBank 城市银行分布与银行网点信息的 NoneBot2 插件。",
    usage=(
        "/bank 城市 <城市名>\n"
        "/bank 网点 <城市名> <银行名> [页码]\n"
        "/银行 <城市名>\n"
        "/网点 <城市名> <银行名> [页码]\n"
        "/bank 搜城市 <关键词>\n"
        "/bank 搜银行 <关键词>\n"
        "/bank 缓存\n"
        "/bank 清缓存\n"
        "/标记 <银行名...> [次数] / /mark <银行名...> [次数]\n"
        "/取消标记 <银行名...> / /unmark <银行名...>\n"
        "/批量标记 <城市名> <分类> [次数]\n"
        "/批量取消标记 <城市名> <分类>\n"
        "/复制标记 <@用户/QQ号>\n"
        "/标记列表\n"
        "/卡号 <银行名> <卡号...>\n"
        "/关注 <银行名...> [次数] / /follow <银行名...> [次数]\n"
        "/取消关注 <银行名...> / /unfollow <银行名...>\n"
        "/批量关注 <城市名> <分类> [次数]\n"
        "/批量取消关注 <城市名> <分类>\n"
        "/复制关注 <@用户/QQ号>\n"
        "/关注列表\n"
        "/更新银行图标（仅超级用户）\n"
        "/搜城市 <关键词>\n"
        "/搜银行 <关键词>"
    ),
    type="application",
    homepage="https://github.com/WhyPilotXia/nonebot-plugin-hibank",
    config=HibankConfig,
    supported_adapters={"~onebot.v11"},
)

from . import commands as commands  # noqa: E402
