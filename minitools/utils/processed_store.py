"""
処理済み動画の永続化ストア。

youtube-mail-digest で一度処理した動画を記録し、再実行時の重複処理・
重複配信を防ぐ。dedup スコープは **per-profile**（キー = プロファイル名）。
JSON は `{ "<profile>": ["<video_id>", ...], ... }` の形。
"""

import json
from pathlib import Path
from typing import Dict, Iterable, List, Set, TypeVar

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_STORE_PATH = "outputs/youtube_mail_digest/processed.json"

T = TypeVar("T")


class ProcessedStore:
    """処理済み動画 ID を per-profile で記録する JSON ストア"""

    def __init__(self, path: str = DEFAULT_STORE_PATH):
        self.path = Path(path)
        self._data: Dict[str, Set[str]] = self._load()

    def _load(self) -> Dict[str, Set[str]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"processed.json の読み込みに失敗（空で開始）: {e}")
            return {}
        data: Dict[str, Set[str]] = {}
        if isinstance(raw, dict):
            for profile, ids in raw.items():
                if isinstance(ids, list):
                    data[profile] = set(str(i) for i in ids)
        return data

    def is_processed(self, profile: str, video_id: str) -> bool:
        """指定プロファイルで動画が処理済みか"""
        return video_id in self._data.get(profile, set())

    def filter_new(self, profile: str, refs: Iterable[T]) -> List[T]:
        """
        未処理の参照のみを返す（VideoRef を想定、`video_id` 属性を持つもの）。

        Args:
            profile: プロファイル名（dedup の名前空間）
            refs: `.video_id` を持つオブジェクトの列

        Returns:
            未処理のものだけを残したリスト
        """
        processed = self._data.get(profile, set())
        result: List[T] = []
        for ref in refs:
            vid = getattr(ref, "video_id")
            if vid not in processed:
                result.append(ref)
        return result

    def mark(self, profile: str, video_id: str) -> None:
        """動画を処理済みとしてメモリ上に記録する（永続化は save() で）"""
        self._data.setdefault(profile, set()).add(video_id)

    def mark_many(self, profile: str, video_ids: Iterable[str]) -> None:
        """複数動画をまとめて処理済み記録する（並列処理後の一括反映向け）"""
        bucket = self._data.setdefault(profile, set())
        for vid in video_ids:
            bucket.add(vid)

    def save(self) -> None:
        """現在の状態を JSON に永続化する"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {profile: sorted(ids) for profile, ids in self._data.items()}
        self.path.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug(f"processed.json を保存: {self.path}")
