"""
ネットワーク到達性の待機ユーティリティ。

launchd のジョブはスリープ復帰直後に実行されることがあり、その時点では
DNS がまだ引けずに外部 API への接続が全て失敗する。処理開始前に名前解決が
通るまで待つことで、この取りこぼしを防ぐ。
"""

import socket
import time
from typing import Iterable

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


def wait_for_network(
    hosts: Iterable[str],
    timeout: float = 180.0,
    interval: float = 5.0,
) -> bool:
    """
    指定ホストのいずれかの名前解決が成功するまで待機する

    Args:
        hosts: 名前解決を試すホスト名
        timeout: 最大待機秒数
        interval: 再試行の間隔（秒）

    Returns:
        timeout 内に名前解決できれば True、できなければ False
    """
    hosts = list(hosts)
    deadline = time.monotonic() + timeout
    attempt = 0

    while True:
        attempt += 1
        for host in hosts:
            try:
                socket.getaddrinfo(host, 443)
                if attempt > 1:
                    logger.info(
                        f"ネットワーク復帰を確認しました（{host}, 試行 {attempt} 回目）"
                    )
                return True
            except OSError:
                continue

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.error(
                f"ネットワークに接続できません（{timeout:.0f}秒待機, 対象: {', '.join(hosts)}）"
            )
            return False

        logger.warning(
            f"名前解決に失敗しました。{interval:.0f}秒後に再試行します（試行 {attempt} 回目）"
        )
        time.sleep(min(interval, remaining))
