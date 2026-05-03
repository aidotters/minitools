"""
Jina AI Reader scraper module.

Fetches full-text Markdown of arbitrary web articles via the
``https://r.jina.ai/{url}`` endpoint. Used by ``google-alerts-translate``
for English news / blog articles.

Note:
    This module is **not** intended for Medium articles. Medium has
    explicit Cloudflare blocking against Jina AI Reader and the existing
    ``MediumCollector`` implements site-specific workarounds. Do not
    consolidate the two paths.
"""

import asyncio
import random
import re
from datetime import datetime
from typing import Optional

import aiohttp

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


# User-Agent ローテーション用リスト（MediumCollector と同等の組み合わせ）
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
]

# Jina AI Reader が返す Markdown のヘッダ形式（最初の数行）
_TITLE_PATTERN = re.compile(r"^Title:\s*(.+?)\s*$", re.MULTILINE)
_PUBLISHED_PATTERN = re.compile(r"^Published Time:\s*(.+?)\s*$", re.MULTILINE)


class JinaReader:
    """Jina AI Reader 経由で URL の Markdown 全文を取得する非同期クライアント"""

    BASE_URL = "https://r.jina.ai/"

    async def fetch_markdown(
        self,
        url: str,
        max_chars: Optional[int] = None,
        max_retries: int = 3,
    ) -> str:
        """指定 URL の Markdown 全文を取得する

        Args:
            url: 取得対象の記事 URL
            max_chars: 最大文字数。None の場合トリミングしない
            max_retries: リトライ回数（指数バックオフ 1s/2s/4s）

        Returns:
            Markdown 文字列。失敗時は空文字列
        """
        jina_url = f"{self.BASE_URL}{url}"

        for attempt in range(max_retries):
            try:
                user_agent = random.choice(USER_AGENTS)
                headers = {
                    "User-Agent": user_agent,
                    "Accept": "text/plain",
                }

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        jina_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(f"HTTP {response.status}")

                        text_content = await response.text()
                        lower_content = text_content.lower()

                        if (
                            "error 403" in lower_content
                            or "just a moment" in lower_content
                        ):
                            logger.warning(f"Jina Reader blocked for {url}")
                            return ""

                        text_content = text_content.strip()
                        if len(text_content) < 100:
                            raise RuntimeError("Content too short")

                        if max_chars is not None:
                            text_content = text_content[:max_chars]

                        logger.debug(
                            f"Jina Reader fetched {len(text_content)} chars from {url}"
                        )
                        return text_content

            except Exception as e:
                wait_time = 2**attempt  # 1, 2, 4
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Error fetching {url} via Jina, retrying in {wait_time}s... "
                        f"(attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Jina Reader failed for {url}: {e}")
                    return ""

        return ""

    @staticmethod
    def extract_metadata(markdown: str) -> dict[str, Optional[str]]:
        """Jina 出力の Markdown ヘッダからメタデータを抽出する

        ``Title:`` 行と ``Published Time:`` 行を抽出する。前者は文字列、
        後者は ISO 8601 から ``YYYY-MM-DD`` への整形を試みる。失敗時は
        対応キーが ``None`` になる。
        """
        result: dict[str, Optional[str]] = {"title": None, "published_at": None}

        if not markdown:
            return result

        title_match = _TITLE_PATTERN.search(markdown)
        if title_match:
            title = title_match.group(1).strip()
            if title:
                result["title"] = title

        published_match = _PUBLISHED_PATTERN.search(markdown)
        if published_match:
            raw = published_match.group(1).strip()
            if raw:
                result["published_at"] = _normalize_iso_date(raw)

        return result


def _normalize_iso_date(value: str) -> Optional[str]:
    """ISO 8601 文字列を YYYY-MM-DD に整形する。失敗時は None"""
    candidates = [value]
    if value.endswith("Z"):
        candidates.append(value[:-1] + "+00:00")

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # 単純な YYYY-MM-DD プレフィックスにフォールバック
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    if match:
        return match.group(1)

    return None
