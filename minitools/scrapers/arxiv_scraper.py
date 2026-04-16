"""
ArXiv paper scraper using PDF + marker-pdf.

Downloads ArXiv papers as PDF, converts to Markdown using marker-pdf,
and fetches metadata via ArXiv API.

Usage:
    async with ArxivScraper() as scraper:
        result = await scraper.fetch_and_parse("https://arxiv.org/abs/2401.12345")
        if result:
            print(result.markdown)
"""

import asyncio
import io
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

import feedparser
import httpx

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# リトライ設定
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]


@dataclass
class PaperImage:
    """抽出画像"""

    data: bytes
    filename: str
    caption: str = ""


@dataclass
class PaperMetadata:
    """論文メタデータ"""

    arxiv_id: str
    title: str
    authors: list[str]
    published: str  # YYYY-MM-DD形式
    abstract: str


@dataclass
class PaperContent:
    """PDF解析結果"""

    markdown: str
    images: list[PaperImage] = field(default_factory=list)
    metadata: PaperMetadata | None = None


class ArxivScraper:
    """ArXiv論文PDFを取得・解析するスクレイパー"""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._converter: Any = None

    async def __aenter__(self) -> "ArxivScraper":
        self._client = httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def validate_arxiv_url(self, url: str) -> bool:
        """ArXiv URLのバリデーション"""
        if not url:
            return False
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        return hostname in ("arxiv.org", "export.arxiv.org", "www.arxiv.org")

    @staticmethod
    def extract_arxiv_id(url: str) -> str | None:
        """URLからarXiv IDを抽出

        Examples:
            https://arxiv.org/abs/2401.12345 → 2401.12345
            https://arxiv.org/pdf/2401.12345v2 → 2401.12345v2
            https://arxiv.org/abs/cs.AI/0301001 → cs.AI/0301001
        """
        url = url.strip().rstrip("/")
        match = re.search(r"arxiv\.org/(?:abs|pdf|html)/(.+?)(?:\.pdf)?$", url)
        if match:
            return match.group(1)
        return None

    def _convert_to_pdf_url(self, arxiv_url: str) -> str:
        """ArXiv URLをPDF URLに変換

        Examples:
            https://arxiv.org/abs/2401.12345 → https://arxiv.org/pdf/2401.12345
            https://arxiv.org/html/2401.12345 → https://arxiv.org/pdf/2401.12345
        """
        url = arxiv_url.strip().rstrip("/")
        url = url.replace("http://", "https://")
        url = url.replace("export.arxiv.org", "arxiv.org")
        url = url.replace("www.arxiv.org", "arxiv.org")

        arxiv_id = self.extract_arxiv_id(url)
        if arxiv_id:
            return f"https://arxiv.org/pdf/{arxiv_id}"

        logger.warning(f"Could not extract ArXiv ID from URL: {arxiv_url}")
        return url

    async def fetch_pdf(self, url: str) -> bytes | None:
        """ArXiv PDFをダウンロード

        Args:
            url: ArXiv論文のURL

        Returns:
            PDFバイナリデータ（失敗時はNone）
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        pdf_url = self._convert_to_pdf_url(url)
        logger.info(f"Fetching PDF: {pdf_url}")

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.get(pdf_url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if "pdf" not in content_type and response.content[:5] != b"%PDF-":
                    logger.error(
                        f"Response is not PDF (content-type: {content_type}): {pdf_url}"
                    )
                    return None

                logger.info(f"PDF fetched: {len(response.content)} bytes")
                return response.content

            except httpx.HTTPStatusError as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"HTTP error {e.response.status_code} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Failed to fetch PDF after {MAX_RETRIES} attempts: {e}"
                    )
                    return None

            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Network error (attempt {attempt + 1}/{MAX_RETRIES}): "
                        f"{e}, retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Failed to fetch PDF after {MAX_RETRIES} attempts: {e}"
                    )
                    return None

        return None

    def parse_to_markdown(self, pdf_data: bytes) -> tuple[str, list[PaperImage]]:
        """PDFをMarkdown+画像に変換（marker-pdf使用）

        Args:
            pdf_data: PDFバイナリデータ

        Returns:
            (Markdown文字列, 抽出画像リスト)のタプル
        """
        if self._converter is None:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict

            logger.info("Loading marker-pdf models...")
            artifact_dict = create_model_dict()
            self._converter = PdfConverter(artifact_dict=artifact_dict)

        logger.info("Converting PDF to Markdown with marker-pdf...")
        result = self._converter(io.BytesIO(pdf_data))

        markdown = result.markdown
        logger.info(f"Markdown generated: {len(markdown)} chars")

        # 画像の抽出
        images: list[PaperImage] = []
        for filename, image_data in result.images.items():
            images.append(
                PaperImage(
                    data=image_data,
                    filename=filename,
                )
            )

        if images:
            logger.info(f"Extracted {len(images)} images from PDF")

        return markdown, images

    async def fetch_metadata(self, arxiv_id: str) -> PaperMetadata | None:
        """ArXiv APIからメタデータ取得

        Args:
            arxiv_id: arXiv ID（例: 2401.12345）

        Returns:
            PaperMetadata（失敗時はNone）
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1"
        logger.info(f"Fetching metadata from ArXiv API: {arxiv_id}")

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.get(api_url)
                response.raise_for_status()

                feed = feedparser.parse(response.text)
                if not feed.entries:
                    logger.warning(f"No metadata found for arXiv ID: {arxiv_id}")
                    return None

                entry = feed.entries[0]
                published = entry.published[:10] if entry.published else ""
                authors = (
                    [author.name for author in entry.authors] if entry.authors else []
                )

                metadata = PaperMetadata(
                    arxiv_id=arxiv_id,
                    title=(
                        entry.title.replace("\n", " ").strip()
                        if entry.title
                        else arxiv_id
                    ),
                    authors=authors,
                    published=published,
                    abstract=entry.summary.strip() if entry.summary else "",
                )
                logger.info(f"Metadata fetched: {metadata.title}")
                return metadata

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Metadata fetch error (attempt {attempt + 1}/{MAX_RETRIES}): "
                        f"{e}, retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Failed to fetch metadata for {arxiv_id} "
                        f"after {MAX_RETRIES} attempts: {e}"
                    )
                    return None

        return None

    async def fetch_and_parse(self, url: str) -> PaperContent | None:
        """PDF取得→解析→メタデータ取得の一連処理

        Args:
            url: ArXiv論文のURL

        Returns:
            PaperContent（失敗時はNone）
        """
        if not self.validate_arxiv_url(url):
            logger.error(f"ArXiv URLではありません: {url}")
            return None

        # PDF取得
        pdf_data = await self.fetch_pdf(url)
        if not pdf_data:
            logger.error(f"Failed to fetch PDF: {url}")
            return None

        # PDF解析（CPU-bound: run_in_executorで実行）
        loop = asyncio.get_event_loop()
        try:
            markdown, images = await loop.run_in_executor(
                None, self.parse_to_markdown, pdf_data
            )
        except Exception as e:
            logger.error(f"Failed to parse PDF: {e}")
            return None

        if not markdown:
            logger.error(f"Empty markdown from PDF: {url}")
            return None

        # メタデータ取得
        arxiv_id = self.extract_arxiv_id(url)
        metadata = None
        if arxiv_id:
            metadata = await self.fetch_metadata(arxiv_id)

        return PaperContent(
            markdown=markdown,
            images=images,
            metadata=metadata,
        )
