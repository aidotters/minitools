"""
arxiv の抜けた回を取り戻すための記録と判定。

launchd の定時実行（火〜土 14:30 JST・対象日は前日）は、その時刻に
Mac のユーザーがログアウトしていると走らず、後から追いかけても実行しない。
ログインのたびに `arxiv --catch-up` を走らせ、ここで「最後に処理した対象日」と
「本来走っているはずだった回」を突き合わせて、抜けた対象日だけを返す。

記録は `{"last_done": "YYYY-MM-DD"}` の JSON 1つ（outputs/ 配下・git 管理外）。
"""

import fcntl
import json
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterator, Optional

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


def missed_targets(
    now: datetime,
    last_done: Optional[date],
    lookback_days: int = MAX_LOOKBACK_DAYS,
) -> list[date]:
    """
    取り戻すべき対象日を古い順に返す。

    記録が無いとき（入れた直後）は空を返す。どの回が済んでいるか分からないので、
    取り戻して Slack へ二重に送るより、何もしないほうを選ぶ。
    """
    if last_done is None:
        return []
    targets = scheduled_targets(now, lookback_days)
    return [d for d in targets if d > last_done]


def load_last_done(path: str = DEFAULT_STATE_PATH) -> Optional[date]:
    """最後に処理した対象日を読む。無い・壊れているときは None"""
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return date.fromisoformat(raw["last_done"])
    except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as e:
        logger.warning(f"{path} の読み込みに失敗（記録なしとして扱う）: {e}")
        return None


def record_done(target: date, path: str = DEFAULT_STATE_PATH) -> None:
    """対象日を処理済みとして記録する。記録より古い日付では戻さない"""
    current = load_last_done(path)
    if current is not None and current >= target:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"last_done": target.isoformat()}, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(p)


@contextmanager
def run_lock(path: str = DEFAULT_LOCK_PATH) -> Iterator[None]:
    """定時の回と取り戻しの回が同時に走らないよう、終わるまで待って排他する"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
