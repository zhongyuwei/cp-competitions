# cp-competitions

AtCoder / Codeforces 近期比赛的日历订阅源（`.ics`），由 GitHub Actions 每 3 天自动抓取更新。

## 订阅地址

| 用途 | 链接 |
| --- | --- |
| 主订阅（3 个提醒） | `https://zhongyuwei.github.io/cp-competitions/cp-competitions.ics` |
| 只提醒「提前 1 天」 | `https://zhongyuwei.github.io/cp-competitions/cp-competitions-1d.ics` |
| 只提醒「提前 3 小时」 | `https://zhongyuwei.github.io/cp-competitions/cp-competitions-3h.ics` |
| 只提醒「提前 15 分钟」 | `https://zhongyuwei.github.io/cp-competitions/cp-competitions-15m.ics` |

订阅页（含近期比赛列表）：<https://zhongyuwei.github.io/cp-competitions/>

## 提醒

主订阅给每场比赛挂了 3 个 `VALARM`：

- 比赛开始前 **1 天**
- 比赛开始前 **3 小时**
- 比赛开始前 **15 分钟**

不同客户端对订阅日历的提醒支持不一样：

- **Apple 日历（macOS / iOS）**：原生支持多个 `VALARM`，直接订阅即可。
- **Google 日历**：通过网址添加的日历**不读取** ICS 里的提醒，只能为每个日历设一个“默认通知”。
  如果要三个提醒都在，就分别订阅 `-1d` / `-3h` / `-15m` 三个变体，再把它们的默认通知分别设为 1 天、3 小时、15 分钟。
- **Outlook / Thunderbird**：支持 `VALARM`，按各自流程订阅即可。

想改提醒时间，编辑 `scripts/build.py` 里的 `REMINDERS`（主订阅）和 `VARIANT_FEEDS`（变体），提交后 Actions 会自动重建。

## 数据来源

| 源 | 抓取方式 |
| --- | --- |
| AtCoder | 解析 <https://atcoder.jp/contests/> 页面的 “Upcoming Contests” 表格 |
| Codeforces | 官方 API <https://codeforces.com/api/contest.list>（`phase` 为 `BEFORE` / `CODING`） |

两个源都用标准库 `urllib` + 正则实现，**没有第三方依赖**，Actions 里不需要 `pip install`。

单个源抓取失败时，会自动回退到 `data/state.json` 里上次成功的数据，另一个源照常更新；
只有全部源都失败时才会以非零状态退出，此时不会覆盖已有的订阅文件。

## 目录结构

```
scripts/
  build.py            # 入口：抓取 → 生成 ICS 和订阅页 → 写状态
  model.py            # Contest 数据模型
  ics.py              # 极简 RFC 5545 生成器（转义、75 字节折行、VALARM）
  template.html       # 订阅页模板
  sources/
    __init__.py       # 比赛源注册表
    atcoder.py        # AtCoder 源
    codeforces.py     # Codeforces 源
docs/
  cp-competitions.ics        # 主订阅文件（Actions 自动生成，不要手改）
  cp-competitions-*.ics      # 单提醒变体
  index.html                 # 订阅页（自动生成）
data/state.json              # 源数据缓存 + 事件时间戳（自动生成）
```

## 新增比赛源

1. 在 `scripts/sources/` 下新建模块，暴露三个名字：

```python
SOURCE = "luogu"          # 唯一标识，参与 UID
LABEL = "洛谷"             # 展示名
def fetch() -> list[Contest]:  # 返回 model.Contest 列表
    ...
```

2. 在 `scripts/sources/__init__.py` 的 `SOURCES` 元组里登记；
3. 本地跑一次 `python3 scripts/build.py` 验证，提交后 Actions 会自动带上。

UID 规则是 `{source}-{比赛ID}@cp-competitions`，**只要比赛 ID 稳定，日历里就不会出现重复事件**。

## 本地运行

```bash
python3 scripts/build.py     # 仅用标准库，Python 3.9+
```

## 实现细节

- 时间统一以 UTC 写入 `DTSTART` / `DTEND`，客户端会按本地时区展示；描述里同时给出 UTC 和北京时间。
- 事件内容没变化时沿用旧的 `DTSTAMP`，避免客户端把每次抓取都当成“比赛信息更新”。
- 已经结束超过 6 小时的比赛会从订阅文件里移除（长赛程的 AHC 不会在开赛时突然消失）。
- 文件按 RFC 5545 折行到 75 字节以内，中文不会被截断在字符中间。
