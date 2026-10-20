"""赛事数据模型：所有比赛源都产出 Contest 对象。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class Contest:
    """一场比赛。时间统一使用带时区的 UTC datetime。"""

    source: str  # 来源标识，如 "atcoder"
    source_label: str  # 展示名，如 "AtCoder"
    uid: str  # 稳定唯一 ID（跨次构建不变），用于日历去重
    name: str
    start: datetime
    duration: timedelta
    url: str
    detail: str = ""  # 附加说明（赛制、时长等），会写进 DESCRIPTION
    categories: list[str] = field(default_factory=list)
    # 该事件最近一次内容变化的时间，用于 DTSTAMP；未变化时保持不变，避免日历客户端误判为更新
    stamp: datetime | None = None

    @property
    def end(self) -> datetime:
        return self.start + self.duration

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "source_label": self.source_label,
            "uid": self.uid,
            "name": self.name,
            "start": self.start.astimezone(timezone.utc).isoformat(),
            "duration": int(self.duration.total_seconds()),
            "url": self.url,
            "detail": self.detail,
            "categories": list(self.categories),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Contest":
        return cls(
            source=data["source"],
            source_label=data["source_label"],
            uid=data["uid"],
            name=data["name"],
            start=datetime.fromisoformat(data["start"]).astimezone(timezone.utc),
            duration=timedelta(seconds=data["duration"]),
            url=data["url"],
            detail=data.get("detail", ""),
            categories=list(data.get("categories", [])),
        )


def human_duration(delta: timedelta) -> str:
    """把时长格式化成 '2 小时 30 分' 这样的可读文本。"""
    total = int(delta.total_seconds())
    hours, minutes = divmod(total // 60, 60)
    if hours and minutes:
        return f"{hours} 小时 {minutes} 分"
    if hours:
        return f"{hours} 小时"
    return f"{minutes} 分钟"
