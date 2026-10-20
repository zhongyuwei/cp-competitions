"""AtCoder 比赛源。

数据来自 https://atcoder.jp/contests/ 页面里的 “Upcoming Contests” 表格。
没有使用第三方 API，保证和官网展示完全一致。
"""

from __future__ import annotations

import html
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from model import Contest

SOURCE = "atcoder"
LABEL = "AtCoder"
INDEX_URL = "https://atcoder.jp/contests/"
BASE_URL = "https://atcoder.jp"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TAG_RE = re.compile(r"<[^>]+>")
TIME_RE = re.compile(r"<time class='fixtime fixtime-full'>([^<]+)</time>")
LINK_RE = re.compile(r"href=\"/contests/([^\"/?]+)\"[^>]*>(.*?)</a>", re.S)
NAME_CELL_RE = re.compile(r"<td\s*>(.*?)</td>\s*\n?\s*<td class=\"text-center\">(\d{1,3}):(\d{2})</td>", re.S)
RATED_RE = re.compile(r"<td class=\"text-center\">([^<]*\d[^<]*|[^<]*All[^<]*)</td>\s*</tr>")
KIND_RE = re.compile(r"data-toggle='tooltip' data-placement='top' title=\"([^\"]+)\"")


def _get(url: str, attempts: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", "replace")
        except Exception as error:  # noqa: BLE001 - 网络异常统一重试
            last_error = error
            if attempt < attempts:
                continue
    raise RuntimeError(f"抓取 {url} 失败：{last_error}")


def _plain(fragment: str) -> str:
    return html.unescape(TAG_RE.sub("", fragment)).strip()


def _duration(hours: str, minutes: str) -> timedelta:
    return timedelta(hours=int(hours), minutes=int(minutes))


def fetch() -> list[Contest]:
    page = _get(INDEX_URL)

    start = page.find('id="contest-table-upcoming"')
    if start < 0:
        raise RuntimeError("AtCoder 页面结构变化：找不到 Upcoming Contests 区块")
    # Upcoming 表格之后紧跟下一个表格（past / active），截断即可
    end = page.find('id="contest-table-', start + 10)
    block = page[start:end if end > start else len(page)]

    contests: list[Contest] = []
    for row in block.split("<tr>")[1:]:
        time_match = TIME_RE.search(row)
        link_match = LINK_RE.search(row)
        cell_match = NAME_CELL_RE.search(row)
        if not (time_match and link_match and cell_match):
            continue

        start_at = datetime.strptime(time_match.group(1).strip(), "%Y-%m-%d %H:%M:%S%z")
        contest_id = link_match.group(1)
        name = _plain(link_match.group(2))
        duration = _duration(cell_match.group(2), cell_match.group(3))

        kind_match = KIND_RE.search(row)
        kind = html.unescape(kind_match.group(1)) if kind_match else ""
        rated_match = RATED_RE.search(row)
        rated = rated_match.group(1).strip() if rated_match else ""

        detail_parts = []
        if kind:
            detail_parts.append(f"赛制：{kind}")
        if rated:
            detail_parts.append(f"Rated 范围：{rated}")

        contests.append(
            Contest(
                source=SOURCE,
                source_label=LABEL,
                uid=f"{SOURCE}-{contest_id}@cp-competitions",
                name=name,
                start=start_at.astimezone(timezone.utc),
                duration=duration,
                url=f"{BASE_URL}/contests/{contest_id}",
                detail="\n".join(detail_parts),
                categories=[LABEL] + ([kind] if kind else []),
            )
        )

    if not contests:
        raise RuntimeError("AtCoder 未解析到任何比赛，可能页面结构已变化")
    return contests
