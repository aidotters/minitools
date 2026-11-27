"""
arxiv の抜けた回を取り戻すための記録と判定。

launchd の定時実行（火〜土 14:30 JST・対象日は前日）は、その時刻に
Mac のユーザーがログアウトしていると走らず、後から追いかけても実行しない。
ログインのたびに `arxiv --catch-up` を走らせ、ここで配信先ごとの記録と
「本来走っているはずだった回」を突き合わせて、未完了の回だけを返す。

記録は outputs/ 配下の JSON（git 管理外）。旧 last_done は再送を避ける移行境界にする。
"""

import fcntl
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterator

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_STATE_PATH = "outputs/arxiv/state.json"
DEFAULT_LOCK_PATH = "outputs/arxiv/run.lock"

# launchd の StartCalendarInterval と合わせる（Python の weekday: 月=0 … 日=6）
SCHEDULE_WEEKDAYS = frozenset({1, 2, 3, 4, 5})  # 火〜土
SCHEDULE_TIME = time(14, 30)

# これより古い抜けは取り戻さない（長期の不在後に何日分も Slack へ流さない）
MAX_LOOKBACK_DAYS = 7


def scheduled_targets(
    now: datetime, lookback_days: int = MAX_LOOKBACK_DAYS
) -> list[date]:
    """
    now までに走っているはずだった回の対象日（実行日の前日）を古い順に返す。

    Args:
        now: 現在時刻（JST の naive / aware どちらでも、時刻の比較は壁時計で行う）
        lookback_days: さかのぼる日数
    """
    targets: list[date] = []
    for back in range(lookback_days, -1, -1):
        run_day = now.date() - timedelta(days=back)
        if run_day.weekday() not in SCHEDULE_WEEKDAYS:
            continue
        if back == 0 and now.time().replace(tzinfo=None) < SCHEDULE_TIME:
            continue
        targets.append(run_day - timedelta(days=1))
    return targets


DESTINATIONS = frozenset({"notion", "slack", "weekly"})


def required_destinations(target: date) -> set[str]:
    daily = {"notion", "slack"}
    if target.weekday() == 4:  # 金曜分を処理する土曜に週次ページを作る
        daily.add("weekly")
    return daily


@dataclass
class DeliveryState:
    # 旧版または初回起動以前の不明な日付は、一括で再送しない。
    baseline: date
    completed: dict[date, set[str]] = field(default_factory=dict)

    def pending(self, target: date, requested: set[str]) -> set[str]:
        if target <= self.baseline:
            return set()
        return requested - self.completed.get(target, set())


def missed_targets(
    now: datetime, state: DeliveryState, lookback_days: int = MAX_LOOKBACK_DAYS
) -> list[date]:
    return [
        day
        for day in scheduled_targets(now, lookback_days)
        if state.pending(day, required_destinations(day))
    ]


def load_state(path: str | None = None) -> DeliveryState | None:
    p = Path(path or DEFAULT_STATE_PATH)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(f"配信記録を読めません。再送を避けるため中止: {p}") from exc

    try:
        if not isinstance(raw, dict):
            raise ValueError("not an object")
        if set(raw) == {"last_done"}:
            return DeliveryState(date.fromisoformat(raw["last_done"]))
        if raw["version"] != 2 or not isinstance(raw["completed"], dict):
            raise ValueError("unknown format")
        complete = {}
        for day, destinations in raw["completed"].items():
            if not isinstance(destinations, list) or any(
                destination not in DESTINATIONS for destination in destinations
            ):
                raise ValueError("unknown destination")
            complete[date.fromisoformat(day)] = set(destinations)
        return DeliveryState(date.fromisoformat(raw["baseline"]), complete)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"配信記録の形式が不正です。再送を避けるため中止: {p}"
        ) from exc


def save_state(state: DeliveryState, path: str | None = None) -> None:
    p = Path(path or DEFAULT_STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "version": 2,
                "baseline": state.baseline.isoformat(),
                "completed": {
                    day.isoformat(): sorted(destinations)
                    for day, destinations in sorted(state.completed.items())
                },
            }
        ),
        encoding="utf-8",
    )
    tmp.replace(p)


@contextmanager
def run_lock(path: str | None = None) -> Iterator[None]:
    """定時の回と取り戻しの回が同時に走らないよう、終わるまで待って排他する"""
    p = Path(path or DEFAULT_LOCK_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
