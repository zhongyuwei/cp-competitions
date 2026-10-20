"""极简 iCalendar (RFC 5545) 生成器：只实现日历订阅需要的部分。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from model import Contest, human_duration

UTC = timezone.utc


def escape(text: str) -> str:
    """转义 TEXT 类型字段里的特殊字符。"""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold(line: str, limit: int = 75) -> str:
    """按 RFC 5545 折行：每行不超过 75 个八位字节，续行以空格开头。"""
    if len(line.encode("utf-8")) <= limit:
        return line

    chunks: list[str] = []
    current = ""
    current_bytes = 0
    for char in line:
        char_bytes = len(char.encode("utf-8"))
        # 续行开头的空格也计入 75 字节
        if current_bytes + char_bytes > limit:
            chunks.append(current)
            current = " "
            current_bytes = 1
        current += char
        current_bytes += char_bytes
    chunks.append(current)
    return "\r\n".join(chunks)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def iso_trigger(ahead: timedelta) -> str:
    """把“提前量”转换成 VALARM 需要的负时长，如 -P1D / -PT3H / -PT15M。"""
    total = int(ahead.total_seconds())
    if total % 86400 == 0:
        return f"-P{total // 86400}D"
    if total % 3600 == 0:
        return f"-PT{total // 3600}H"
    return f"-PT{total // 60}M"


def _reminder_label(ahead: timedelta) -> str:
    total = int(ahead.total_seconds())
    if total % 86400 == 0:
        return f"{total // 86400} 天后"
    if total % 3600 == 0:
        return f"{total // 3600} 小时后"
    return f"{total // 60} 分钟后"


def _description(contest: Contest) -> str:
    lines = [
        contest.name,
        "",
        f"开始：{contest.start.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
        f"（北京时间 {contest.start.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')}）",
        f"时长：{human_duration(contest.duration)}",
        f"链接：{contest.url}",
    ]
    if contest.detail:
        lines.append("")
        lines.append(contest.detail)
    lines.append("")
    lines.append("由 cp-competitions 自动生成")
    return "\n".join(lines)


def build_calendar(
    contests: list[Contest],
    *,
    calendar_name: str,
    calendar_description: str,
    reminders: list[tuple[timedelta, str]],
    generated_at: datetime,
    product_id: str = "-//cp-competitions//CP Contest Calendar//ZH",
) -> str:
    """生成完整的 .ics 文本。

    reminders: [(提前量, VALARM 的 DESCRIPTION 模板)]，模板里可用 {name} 占位。
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{product_id}",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{escape(calendar_name)}",
        f"X-WR-CALDESC:{escape(calendar_description)}",
        "X-WR-TIMEZONE:UTC",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]

    for contest in contests:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{contest.uid}",
                f"DTSTAMP:{_stamp(contest.stamp or generated_at)}",
                f"DTSTART:{_stamp(contest.start)}",
                f"DTEND:{_stamp(contest.end)}",
                f"SUMMARY:{escape(f'[{contest.source_label}] {contest.name}')}",
                f"DESCRIPTION:{escape(_description(contest))}",
                f"URL:{contest.url}",
                "LOCATION:Online",
                f"CATEGORIES:{','.join(escape(item) for item in contest.categories)}",
                "STATUS:CONFIRMED",
                "TRANSP:TRANSPARENT",
            ]
        )
        for ahead, template in reminders:
            message = template.format(
                name=contest.name,
                label=contest.source_label,
                when=_reminder_label(ahead),
            )
            lines.extend(
                [
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{escape(message)}",
                    f"TRIGGER:{iso_trigger(ahead)}",
                    "X-WR-ALARMUID:" + f"{contest.uid}-{iso_trigger(ahead).replace('-', '')}",
                    "END:VALARM",
                ]
            )
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "".join(f"{fold(line)}\r\n" for line in lines)
