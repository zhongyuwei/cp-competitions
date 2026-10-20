"""Codeforces 比赛源。

数据来自官方 API：https://codeforces.com/api/contest.list （无需鉴权）。
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone

from model import Contest

SOURCE = "codeforces"
LABEL = "Codeforces"
API_URL = "https://codeforces.com/api/contest.list?gym=false"
BASE_URL = "https://codeforces.com/contest"

UA = "Mozilla/5.0 (compatible; cp-competitions/1.0)"

# 只有还没开始（BEFORE）和正在进行的比赛（CODING）才进入日历
ACTIVE_PHASES = {"BEFORE", "CODING"}

TYPE_LABELS = {
    "CF": "Codeforces Round",
    "ICPC": "ICPC",
    "IOI": "IOI",
}


def _get(url: str, attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") != "OK":
                raise RuntimeError(f"Codeforces API 返回异常：{payload.get('comment')}")
            return payload
        except Exception as error:  # noqa: BLE001 - 网络异常统一重试
            last_error = error
            if attempt < attempts:
                continue
    raise RuntimeError(f"抓取 {url} 失败：{last_error}")


def fetch() -> list[Contest]:
    payload = _get(API_URL)

    contests: list[Contest] = []
    for item in payload["result"]:
        if item.get("phase") not in ACTIVE_PHASES:
            continue
        start_seconds = item.get("startTimeSeconds")
        if start_seconds is None:
            continue

        contest_type = item.get("type", "CF")
        type_label = TYPE_LABELS.get(contest_type, contest_type)
        contests.append(
            Contest(
                source=SOURCE,
                source_label=LABEL,
                uid=f"{SOURCE}-{item['id']}@cp-competitions",
                name=item["name"],
                start=datetime.fromtimestamp(start_seconds, tz=timezone.utc),
                duration=timedelta(seconds=item.get("durationSeconds", 0)),
                url=f"{BASE_URL}/{item['id']}",
                detail=f"赛制：{type_label}" if type_label else "",
                categories=[LABEL, type_label] if type_label else [LABEL],
            )
        )

    if not contests:
        raise RuntimeError("Codeforces 未解析到任何比赛")
    return contests
