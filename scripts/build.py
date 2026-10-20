#!/usr/bin/env python3
"""cp-competitions 构建脚本：抓取比赛 → 生成日历订阅文件（.ics）→ 生成订阅页面。

用法：
    python3 scripts/build.py

输出：
    docs/cp-competitions.ics          主订阅文件（3 个提醒）
    docs/cp-competitions-1d.ics       仅“提前 1 天”提醒（给只支持单个提醒的客户端）
    docs/cp-competitions-3h.ics       仅“提前 3 小时”提醒
    docs/cp-competitions-15m.ics      仅“提前 15 分钟”提醒
    docs/index.html                   订阅页（自动列出近期比赛）
    data/state.json                   运行状态缓存（源数据 + 事件时间戳）
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ics import build_calendar  # noqa: E402
from model import Contest, human_duration  # noqa: E402
from sources import SOURCES  # noqa: E402

UTC = timezone.utc
BEIJING = timezone(timedelta(hours=8))

CALENDAR_NAME = "cp-competitions"
CALENDAR_DESCRIPTION = "AtCoder / Codeforces 近期比赛（自动更新）"

STATE_FILE = ROOT / "data" / "state.json"
DOCS_DIR = ROOT / "docs"
TEMPLATE_FILE = ROOT / "scripts" / "template.html"

# —— 提醒配置：改这里即可调整提醒时间 ——
REMINDERS: list[tuple[timedelta, str]] = [
    (timedelta(days=1), "明天有比赛：{name}（{label}）"),
    (timedelta(hours=3), "3 小时后开赛：{name}（{label}）"),
    (timedelta(minutes=15), "15 分钟后开赛：{name}（{label}）"),
]

# 给只支持“单个提醒”的客户端（例如 Google 日历）用的单提醒变体
VARIANT_FEEDS: dict[str, tuple[timedelta, str]] = {
    "1d": (timedelta(days=1), "明天有比赛：{name}（{label}）"),
    "3h": (timedelta(hours=3), "3 小时后开赛：{name}（{label}）"),
    "15m": (timedelta(minutes=15), "15 分钟后开赛：{name}（{label}）"),
}

# 已经结束超过这个时长的比赛不再输出（避免长赛程比赛刚开始就从日历里消失）
KEEP_AFTER_END = timedelta(hours=6)

FALLBACK_SITE_URL = "https://zhongyuwei.github.io/cp-competitions"


def log(message: str) -> None:
    print(message, flush=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log("⚠️  state.json 解析失败，按空状态处理")
    return {"version": 1, "sources": {}, "stamps": {}}


def site_url() -> str:
    explicit = os.environ.get("SITE_URL")
    if explicit:
        return explicit.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        try:
            remote = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote)
            if match:
                repo = f"{match.group(1)}/{match.group(2)}"
        except Exception:  # noqa: BLE001 - 没有 git 仓库时用兜底地址
            repo = ""
    if not repo:
        return FALLBACK_SITE_URL
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}"


def collect(state: dict) -> tuple[list[Contest], list[str], dict]:
    """抓取所有比赛源；单个源失败时退回上次成功的数据。"""
    contests: list[Contest] = []
    failures: list[str] = []
    source_state: dict = {}

    for module in SOURCES:
        key = module.SOURCE
        try:
            fetched = module.fetch()
            log(f"✅ {module.LABEL}: 抓到 {len(fetched)} 场比赛")
            source_state[key] = {
                "fetched_at": datetime.now(UTC).isoformat(),
                "contests": [contest.to_dict() for contest in fetched],
            }
            contests.extend(fetched)
        except Exception as error:  # noqa: BLE001 - 单源失败不影响整体
            failures.append(f"{module.LABEL}: {error}")
            log(f"❌ {module.LABEL} 抓取失败：{error}")
            cached = state.get("sources", {}).get(key, {}).get("contests", [])
            if cached:
                log(f"↩️  {module.LABEL}: 使用上次成功缓存的 {len(cached)} 场比赛")
                source_state[key] = state["sources"][key]
                contests.extend(Contest.from_dict(item) for item in cached)

    return contests, failures, source_state


def prune(contests: list[Contest], now: datetime) -> list[Contest]:
    """只保留尚未结束（或刚结束不久）的比赛，按开始时间排序。"""
    kept = [contest for contest in contests if contest.end >= now - KEEP_AFTER_END]
    kept.sort(key=lambda contest: (contest.start, contest.source_label))
    return kept


def apply_stamps(contests: list[Contest], state: dict, now: datetime) -> dict:
    """内容没变的事件沿用旧的 DTSTAMP，避免无意义的“更新”提示。"""
    stamps: dict[str, str] = {}
    previous = state.get("stamps", {})
    for contest in contests:
        signature = "|".join(
            [
                contest.start.isoformat(),
                str(int(contest.duration.total_seconds())),
                contest.name,
                contest.url,
            ]
        )
        old = previous.get(contest.uid, {})
        if old.get("signature") == signature and old.get("stamp"):
            contest.stamp = datetime.fromisoformat(old["stamp"])
        else:
            contest.stamp = now
        stamps[contest.uid] = {"signature": signature, "stamp": contest.stamp.isoformat()}

    # 为还没出现的比赛保留旧记录（万一某次抓取失败又恢复，时间戳仍然稳定）
    for uid, value in previous.items():
        stamps.setdefault(uid, value)
    return stamps


def write_calendars(contests: list[Contest], now: datetime, base_url: str) -> list[Path]:
    written: list[Path] = []
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    main_path = DOCS_DIR / f"{CALENDAR_NAME}.ics"
    main_path.write_text(
        build_calendar(
            contests,
            calendar_name=CALENDAR_NAME,
            calendar_description=CALENDAR_DESCRIPTION,
            reminders=REMINDERS,
            generated_at=now,
        ),
        encoding="utf-8",
        newline="",
    )
    written.append(main_path)

    for suffix, (ahead, template) in VARIANT_FEEDS.items():
        path = DOCS_DIR / f"{CALENDAR_NAME}-{suffix}.ics"
        path.write_text(
            build_calendar(
                contests,
                calendar_name=f"{CALENDAR_NAME} ({suffix})",
                calendar_description=f"{CALENDAR_DESCRIPTION} — 仅保留 {suffix} 提醒",
                reminders=[(ahead, template)],
                generated_at=now,
                product_id=f"-//cp-competitions//CP Contest Calendar {suffix}//ZH",
            ),
            encoding="utf-8",
            newline="",
        )
        written.append(path)

    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    return written


def write_index(contests: list[Contest], now: datetime, base_url: str) -> Path:
    rows = []
    for contest in contests:
        start = contest.start.astimezone(BEIJING)
        rows.append(
            "<tr>"
            f'<td><span class="badge badge-{contest.source}">{html.escape(contest.source_label)}</span></td>'
            f'<td class="name"><a href="{html.escape(contest.url)}" target="_blank" '
            f'rel="noopener">{html.escape(contest.name)}</a></td>'
            f'<td class="time">{start.strftime("%m-%d %H:%M")}'
            f'<span class="weekday">周{"一二三四五六日"[start.weekday()]}</span></td>'
            f'<td class="duration">{human_duration(contest.duration)}</td>'
            "</tr>"
        )

    counts = {}
    for contest in contests:
        counts[contest.source_label] = counts.get(contest.source_label, 0) + 1
    summary = " · ".join(f"{label} {count}" for label, count in counts.items()) or "暂无数据"

    page = TEMPLATE_FILE.read_text(encoding="utf-8")
    replacements = {
        "{{SITE_URL}}": base_url,
        "{{ICS_URL}}": f"{base_url}/{CALENDAR_NAME}.ics",
        "{{WEBCAL_URL}}": f"webcal://{base_url.split('://', 1)[-1]}/{CALENDAR_NAME}.ics",
        "{{UPDATED_AT}}": now.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M（北京时间）"),
        "{{TOTAL}}": str(len(contests)),
        "{{SUMMARY}}": summary,
        "{{ROWS}}": "\n".join(rows) if rows else '<tr><td colspan="4" class="empty">暂无已排期的比赛</td></tr>',
        "{{FIRST_START}}": (
            contests[0].start.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M")
            if contests
            else "—"
        ),
    }
    for placeholder, value in replacements.items():
        page = page.replace(placeholder, value)

    path = DOCS_DIR / "index.html"
    path.write_text(page, encoding="utf-8")
    return path


def main() -> int:
    now = datetime.now(UTC).replace(microsecond=0)
    state = load_state()

    log(f"== cp-competitions build @ {now.isoformat()} ==")
    contests, failures, source_state = collect(state)

    if not contests:
        log("❌ 所有比赛源都失败了，保留现有订阅文件不做覆盖")
        return 1

    contests = prune(contests, now)
    stamps = apply_stamps(contests, state, now)

    base_url = site_url()
    written = write_calendars(contests, now, base_url)
    write_index(contests, now, base_url)

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": now.isoformat(),
                "sources": source_state,
                "stamps": stamps,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    log(f"📅 写入 {len(contests)} 场比赛：")
    for contest in contests:
        log(
            f"   - [{contest.source_label}] {contest.start.astimezone(BEIJING):%Y-%m-%d %H:%M}"
            f" (北京时间) {contest.name}"
        )
    for path in written:
        log(f"   → {path.relative_to(ROOT)}")
    log(f"🔗 订阅地址：{base_url}/{CALENDAR_NAME}.ics")

    if failures:
        log("⚠️  以下源本次失败（已使用缓存）：" + "；".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
