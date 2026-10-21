"""
ArXiv paper collector module.
"""

import time

import aiohttp
from typing import List, Dict, Optional
from datetime import datetime
import feedparser
import requests

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class ArxivCollector:
    """ArXiv論文を収集するクラス"""

    def __init__(self):
        self.base_url = "http://export.arxiv.org/api/query"
        self.http_session = None

    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        connector = aiohttp.TCPConnector(limit=20)
        timeout = aiohttp.ClientTimeout(total=120)
        self.http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()

    def search(
        self, queries: List[str], start_date: str, end_date: str, max_results: int = 50
    ) -> List[Dict[str, str]]:
        """
        arXiv APIを使用して論文を検索

        Args:
            queries: 検索語のリスト
            start_date: 検索開始日（YYYYMMDD形式）
            end_date: 検索終了日（YYYYMMDD形式）
            max_results: 取得する最大結果数

        Returns:
            検索結果の論文情報のリスト
        """
        search_query = " AND ".join(queries)

        params: dict[str, str | int] = {
            "search_query": f"all:{search_query} AND submittedDate:[{start_date}000000 TO {end_date}235959]",
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            response = self._get_with_retry(params)
            response.raise_for_status()

            feed = feedparser.parse(response.text)
            papers = []

            for entry in feed.entries:
                # 投稿日の確認
                published_date = datetime.strptime(entry.published[:10], "%Y-%m-%d")
                start_dt = datetime.strptime(start_date, "%Y%m%d")
                end_dt = datetime.strptime(end_date, "%Y%m%d")

                if start_dt <= published_date <= end_dt:
                    paper = {
                        "title": entry.title,
                        "url": entry.link,
                        "abstract": entry.summary,
                        "authors": ", ".join([author.name for author in entry.authors]),
                        "published": entry.published,
                        "pdf_url": next(
                            (
                                link.href
                                for link in entry.links
                                if link.type == "application/pdf"
                            ),
                            None,
                        ),
                    }
                    papers.append(paper)

            logger.info(f"Found {len(papers)} papers matching criteria")
            return papers

        except Exception as e:
            logger.error(f"Error searching ArXiv: {e}")
            return []

    def _get_with_retry(
        self, params: dict, max_retries: int = 3, base_delay: float = 5.0
    ) -> requests.Response:
        """接続エラー時に指数バックオフ（5s/10s/20s）で再試行して GET する"""
        for attempt in range(max_retries + 1):
            try:
                return requests.get(self.base_url, params=params, timeout=60)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == max_retries:
                    raise
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"ArXiv API への接続に失敗しました。{delay:.0f}秒後に再試行します"
                    f"（{attempt + 1}/{max_retries}）: {e}"
                )
                time.sleep(delay)
        raise RuntimeError("unreachable")

    async def fetch_paper_details_async(self, paper_url: str) -> Optional[str]:
        """
        論文の詳細を非同期で取得

        Args:
            paper_url: 論文のURL

        Returns:
            論文の詳細テキスト
        """
        if not self.http_session:
            logger.error("HTTP session not initialized. Use async context manager.")
            return None

        try:
            async with self.http_session.get(paper_url) as response:
                response.raise_for_status()
                content = await response.text()
                return content
        except Exception as e:
            logger.error(f"Error fetching paper details from {paper_url}: {e}")
            return None
