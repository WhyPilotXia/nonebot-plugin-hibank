<div>
    <a href="https://v2.nonebot.dev/store">
    <img src="https://raw.githubusercontent.com/fllesser/nonebot-plugin-template/refs/heads/resource/.docs/NoneBotPlugin.svg" width="310" alt="logo"></a>

## ✨ HiBank 城市银行查询 ✨

[![LICENSE](https://img.shields.io/github/license/WhyPilotXia/nonebot-plugin-hibank.svg)](./LICENSE)[![pypi](https://img.shields.io/pypi/v/nonebot-plugin-hibank.svg)](https://pypi.python.org/pypi/nonebot-plugin-hibank)[![python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)[![NoneBot](https://img.shields.io/badge/NoneBot-2.x-green.svg)](https://github.com/nonebot/nonebot2)

## 📖 介绍

查询城市银行分布与网点信息并提供标记关注等功能的 NoneBot2 插件。集卡人的福音！

功能特色：

- **城市银行分布**：查询指定城市的全国性、外资、区域性、民营、村镇银行列表。
- **银行网点列表**：查询指定城市指定银行的网点名称、区县与地址。
- **本地缓存**：使用 `nonebot-plugin-localstore` 缓存城市索引、城市银行列表与网点列表。
- **图片返回**：查询结果渲染为图片，并通过 `base64://...` 发送。
- **快捷搜索**：支持 `/搜城市`、`/搜银行` 快速查找名称。
- **个人标注**：按 QQ 号保存已开户标记与关注银行，城市查询图中自动高亮。

## 💿 安装

### 使用 nb-cli 安装

在 nonebot2 项目的根目录下打开命令行，输入以下指令：

```bash
nb plugin install nonebot-plugin-hibank
```

### 使用包管理器安装

在 nonebot2 项目的插件目录下，打开命令行，根据你使用的包管理器输入相应命令。

#### pdm

```bash
pdm add nonebot-plugin-hibank
```

#### poetry

```bash
poetry add nonebot-plugin-hibank
```

然后打开 nonebot2 项目根目录下的 `pyproject.toml` 文件，在 `[tool.nonebot]` 部分追加写入：

```toml
plugins = ["nonebot_plugin_hibank"]
```

## ⚙️ 配置

本插件默认无需配置，以下配置仅用于覆盖默认行为。

| 配置项 | 必填 | 默认值 | 说明 |
|:--:|:--:|:--:|:--|
| `HIBANK_BASE_URL` | 否 | `https://hi.zzz.moe` | HiBank 站点地址。 |
| `HIBANK_TIMEOUT` | 否 | `30` | 请求超时时间，单位秒。 |
| `HIBANK_VERIFY_SSL` | 否 | `false` | 是否校验 HTTPS 证书。当前站点在部分环境会出现 TLS EOF，默认关闭以保证可用。 |
| `HIBANK_BRANCH_PAGE_SIZE` | 否 | `30` | 网点查询每页显示数量。 |

## 🎉 使用

### 指令表

| 指令 | 说明 |
|:--:|:--|
| `/bank 城市 <城市名>` | 查询某城市有哪些银行，支持 `成都`、`成都市`、`四川 成都`。 |
| `/bank 网点 <城市名> <银行名> [页码]` | 查询某城市某银行网点列表。 |
| `/银行 <城市名>` | 等价于 `/bank 城市 <城市名>`。 |
| `/网点 <城市名> <银行名> [页码]` | 等价于 `/bank 网点 <城市名> <银行名> [页码]`。 |
| `/bank 搜城市 <关键词>` | 搜索城市索引。 |
| `/bank 搜银行 <关键词>` | 搜索银行索引。 |
| `/bank 缓存` | 查看缓存统计。 |
| `/bank 清缓存` | 清除本插件所有缓存。 |
| `/bank 帮助` | 显示命令帮助。 |
| `/标记 <银行名...>` | 标记已开户银行；支持一次写入多个银行。 |
| `/mark <银行名...>` | 等价于 `/标记 <银行名...>`。 |
| `/取消标记 <银行名...>` | 取消已开户标记。 |
| `/unmark <银行名...>` | 等价于 `/取消标记 <银行名...>`。 |
| `/批量标记 <城市名> <分类>` | 将某城市分类下的全部银行加入标记列表，例如 `/批量标记 成都 全国性`。 |
| `/批量取消标记 <城市名> <分类>` | 从标记列表移除某城市分类下的全部银行。 |
| `/复制标记 <@用户/QQ号>` | 复制或合并对方的标记列表到当前 QQ。 |
| `/标记列表` | 查看当前 QQ 号的已标记银行。 |
| `/关注 <银行名...>` | 关注银行；支持一次写入多个银行。 |
| `/follow <银行名...>` | 等价于 `/关注 <银行名...>`。 |
| `/取消关注 <银行名...>` | 取消关注。 |
| `/unfollow <银行名...>` | 等价于 `/取消关注 <银行名...>`。 |
| `/批量关注 <城市名> <分类>` | 将某城市分类下的全部银行加入关注列表。 |
| `/批量取消关注 <城市名> <分类>` | 从关注列表移除某城市分类下的全部银行。 |
| `/复制关注 <@用户/QQ号>` | 复制或合并对方的关注列表到当前 QQ。 |
| `/关注列表` | 查看当前 QQ 号的关注银行。 |
| `/搜城市 <关键词>` | 等价于 `/bank 搜城市 <关键词>`。 |
| `/搜银行 <关键词>` | 等价于 `/bank 搜银行 <关键词>`。 |

### 使用示例

```text
/bank 城市 成都
/bank 网点 成都 成都银行
/bank 网点 成都 成都银行 2
/银行 成都
/网点 成都 成都银行
/bank 搜城市 绵阳
/bank 搜银行 农商
/bank 缓存
/bank 清缓存
/标记 成都银行 南京银行 上海银行
/取消标记 成都银行
/批量标记 成都 全国性
/复制标记 123456
/标记列表
/关注 成都银行 南京银行
/取消关注 成都银行
/批量关注 成都 区域性
/复制关注 123456
/关注列表
```

## 🗂️ 缓存说明

插件使用 `nonebot-plugin-localstore` 分配的数据目录保存缓存：

- `indexes.json`：城市索引与银行索引。
- `cities/*.json`：城市银行分布缓存。
- `branches/*.json`：网点列表缓存。
- `user_marks.json`：按 QQ 号保存的标记与关注银行。

除非使用 `/bank 清缓存`，否则已抓取过的数据会优先使用本地缓存。

## 🏷️ 标记说明

- `/标记` 表示已开户成功，城市银行图中会显示为灰色删除线。
- `/关注` 表示关注中的银行，城市银行图中会显示为 `#F780BE` 粉色文字。
- 标记或关注不存在于当前索引的银行时，会提示回复“确认”；回复其他内容不会写入。
- `/复制标记`、`/复制关注` 会先展示对方列表图片；本方为空时回复“复制/取消”，本方已有数据时回复“合并/复制/取消”。


## 🏷️ 指令示例


<img width="761" height="521" alt="image" src="https://github.com/user-attachments/assets/15376dc2-e44f-4f37-b49b-dc0697824ba2" />


<img width="815" height="744" alt="image" src="https://github.com/user-attachments/assets/a92ef43b-ed2c-49b4-92de-1138337c615e" />

<img width="1280" height="3284" alt="3ae49cdf5f5063a56c5d6834247969a2_720" src="https://github.com/user-attachments/assets/b5d1be0a-9426-4ce6-8d33-a45ce47ccf2d" />

<img width="806" height="530" alt="image" src="https://github.com/user-attachments/assets/a4fba9a8-c18d-477e-8805-d2d1e0f28143" />

<img width="1280" height="3015" alt="1ef70bebb61163158a989e1936501fd5_720" src="https://github.com/user-attachments/assets/f2161437-c0f4-49f4-a4bd-8daf1540b0e7" />

<img width="816" height="753" alt="image" src="https://github.com/user-attachments/assets/adb58da8-67a9-43cf-a272-3e3df918c1c7" />


<img width="811" height="790" alt="image" src="https://github.com/user-attachments/assets/a553d6f8-e02e-4b3a-a532-83b886652cec" />


## 📄 License

GPL-3.0-or-later
