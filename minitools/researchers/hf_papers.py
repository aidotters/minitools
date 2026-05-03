"""
HuggingFace Papers API client for fetching paper statistics.
"""

import asyncio
from dataclasses import dataclass

import aiohttp

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

HF_PAPERS_API_BASE = "https://huggingface.co/api/papers"


@dataclass
class HFPaperStats:
    """HuggingFace Papers APIから取得した論文統計"""

    arxiv_id: str
    upvotes: int = 0
    num_comments: int = 0
    found_on_hf: bool = False


class HFPapersResearcher:
    """HuggingFace Papers APIを使用して論文の統計情報を取得するクラス"""

    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "HFPapersResearcher":
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):  # type: ignore[no-untyped-def]
        if self.session:
            await self.session.close()

    async def get_paper_stats(self, arxiv_id: str) -> HFPaperStats:
        """単一論文のHF統計を取得

        Args:
            arxiv_id: arXiv ID (例: "2601.00001")

        Returns:
            HFPaperStats
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")

        url = f"{HF_PAPERS_API_BASE}/{arxiv_id}"
        max_retries = 3

        async with self.semaphore:
            for attempt in range(max_retries):
                try:
                    async with self.session.get(url) as response:
                        if response.status == 404:
                            logger.debug(f"Paper not found on HF: {arxiv_id}")
                            return HFPaperStats(arxiv_id=arxiv_id)

                        if response.status == 429 or response.status >= 500:
                            if attempt < max_retries - 1:
                                delay = 2 ** (attempt + 1)
                                logger.warning(
                                    f"HF API error {response.status} for {arxiv_id}, "
                                    f"retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                                )
                                await asyncio.sleep(delay)
                                continue
                            logger.warning(
                                f"HF API error {response.status} for {arxiv_id} after {max_retries} retries"
                            )
                            return HFPaperStats(arxiv_id=arxiv_id)

                        response.raise_for_status()
                        data = await response.json()

                        return HFPaperStats(
                            arxiv_id=arxiv_id,
                            upvotes=data.get("upvotes", 0),
                            num_comments=data.get("numComments", 0),
                            found_on_hf=True,
                        )

                except aiohttp.ClientError as e:
                    if attempt < max_retries - 1:
                        delay = 2 ** (attempt + 1)
                        logger.warning(
                            f"Network error for {arxiv_id}: {e}, "
                            f"retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(
                            f"Failed to fetch HF stats for {arxiv_id} after {max_retries} retries: {e}"
                        )
                        return HFPaperStats(arxiv_id=arxiv_id)

        return HFPaperStats(arxiv_id=arxiv_id)

    async def get_papers_stats(self, arxiv_ids: list[str]) -> dict[str, HFPaperStats]:
        """複数論文のHF統計を一括取得

        Args:
            arxiv_ids: arXiv IDのリスト

        Returns:
            arXiv ID -> HFPaperStats のマッピング
        """
        if not arxiv_ids:
            return {}

        logger.info(f"Fetching HF stats for {len(arxiv_ids)} papers...")

        tasks = [self.get_paper_stats(arxiv_id) for arxiv_id in arxiv_ids]
        results = await asyncio.gather(*tasks)

        stats_map = {stats.arxiv_id: stats for stats in results}

        found_count = sum(1 for s in results if s.found_on_hf)
        logger.info(
            f"HF stats fetched: {found_count}/{len(arxiv_ids)} papers found on HF"
        )

        return stats_map
