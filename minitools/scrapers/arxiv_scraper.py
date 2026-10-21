"""
ArXiv paper scraper using PDF + marker-pdf.

Downloads ArXiv papers as PDF, converts to Markdown using marker-pdf,
and fetches metadata via ArXiv API.

Non-arXiv URLs are also supported:
    - Generic PDF URLs: converted with marker-pdf, metadata from PDF info / Markdown
    - HTML pages: converted with ``WebDocumentConverter`` (math / code preserved)

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

from minitools.scrapers.web_document import (
    WebDocumentConverter,
    derive_document_id,
    extract_abstract_from_markdown,
    extract_title_from_markdown,
)
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
    """論文メタデータ

    ``arxiv_id`` は非 arXiv 文書では文書ID（``derive_document_id``）を保持する。
    既存の metadata.json との互換のためフィールド名は変更しない。
    """

    arxiv_id: str
    title: str
    authors: list[str]
    published: str  # YYYY-MM-DD形式
    abstract: str
    source_type: str = "arxiv"  # "arxiv" | "pdf" | "html"


@dataclass
class PaperContent:
    """PDF解析結果"""

    markdown: str
    images: list[PaperImage] = field(default_factory=list)
    metadata: PaperMetadata | None = None
    pdf_bytes: bytes | None = None


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
    def validate_url(url: str) -> bool:
        """http/https の URL かどうか（arXiv 以外の PDF / Webページ用）"""
        if not url:
            return False
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.hostname)

    @classmethod
    def document_id(cls, url: str) -> str:
        """URLから出力フォルダ名に使う文書IDを導出する

        arXiv URL は従来どおり arXiv ID（``/`` は ``_`` に置換）、それ以外は
        ``derive_document_id`` による ``{host}_{slug}_{hash8}`` 形式。
        """
        if cls._is_arxiv_host(url):
            arxiv_id = cls.extract_arxiv_id(url)
            if arxiv_id:
                return arxiv_id.replace("/", "_")
        return derive_document_id(url)

    @staticmethod
    def _is_arxiv_host(url: str) -> bool:
        hostname = urlparse(url.strip()).hostname or ""
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

        # 画像の抽出（marker-pdf は PIL.Image を返すため bytes に変換）
        images: list[PaperImage] = []
        for filename, image_obj in result.images.items():
            data = self._image_to_bytes(image_obj, filename)
            if data is None:
                continue
            images.append(
                PaperImage(
                    data=data,
                    filename=filename,
                )
            )

        if images:
            logger.info(f"Extracted {len(images)} images from PDF")

        return markdown, images

    @staticmethod
    def _image_to_bytes(image_obj: Any, filename: str) -> bytes | None:
        """marker-pdf が返す画像オブジェクトを bytes に変換する

        marker-pdf は PIL.Image.Image を返すため、ファイル拡張子に基づいた
        フォーマットでエンコードしてバイナリ列に変換する。すでに bytes の
        場合（互換用）はそのまま返す。
        """
        if isinstance(image_obj, (bytes, bytearray, memoryview)):
            return bytes(image_obj)

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
        format_map = {
            "jpg": "JPEG",
            "jpeg": "JPEG",
            "png": "PNG",
            "gif": "GIF",
            "webp": "WEBP",
            "bmp": "BMP",
            "tiff": "TIFF",
            "tif": "TIFF",
        }
        fmt = format_map.get(ext, "PNG")

        try:
            buf = io.BytesIO()
            image_obj.save(buf, format=fmt)
            return buf.getvalue()
        except Exception as e:
            logger.warning(f"Failed to encode image {filename} as {fmt}: {e}")
            return None

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

    async def fetch_document(self, url: str) -> httpx.Response | None:
        """任意 URL を GET する（リトライ付き）

        Returns:
            成功時の httpx.Response（失敗時はNone）
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        logger.info(f"Fetching document: {url}")
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.get(url)
                response.raise_for_status()
                logger.info(f"Document fetched: {len(response.content)} bytes")
                return response
            except (
                httpx.HTTPStatusError,
                httpx.RequestError,
                httpx.TimeoutException,
            ) as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Fetch error (attempt {attempt + 1}/{MAX_RETRIES}): "
                        f"{e}, retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Failed to fetch document after {MAX_RETRIES} attempts: {e}"
                    )
                    return None
        return None

    @staticmethod
    def _is_pdf_response(response: httpx.Response) -> bool:
        content_type = response.headers.get("content-type", "").lower()
        return "pdf" in content_type or response.content[:5] == b"%PDF-"

    @staticmethod
    def _is_html_response(response: httpx.Response) -> bool:
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type:
            return True
        head = response.content[:512].lstrip().lower()
        return head.startswith(b"<!doctype html") or head.startswith(b"<html")

    @staticmethod
    def extract_pdf_metadata(
        pdf_data: bytes, markdown: str, doc_id: str
    ) -> PaperMetadata:
        """一般 PDF のメタデータを PDF 情報辞書と Markdown から組み立てる

        PDF の Title は空や "Microsoft Word - xxx.docx" 等のことが多いため、
        その場合は Markdown の先頭見出しにフォールバックする。
        """
        info: dict[str, Any] = {}
        try:
            import fitz  # PyMuPDF

            with fitz.open(stream=pdf_data, filetype="pdf") as doc:
                info = dict(doc.metadata or {})
        except Exception as e:
            logger.debug(f"Failed to read PDF metadata: {e}")

        pdf_title = str(info.get("title") or "").strip()
        if re.match(r"^(microsoft word|untitled)\b", pdf_title, re.I) or re.search(
            r"\.(docx?|tex|dvi|pdf)$", pdf_title, re.I
        ):
            pdf_title = ""
        title = pdf_title or extract_title_from_markdown(markdown) or doc_id

        author = str(info.get("author") or "").strip()
        # 脚注記号（"Alec Radford*" / "Dario Amodei**" / "†"）は除去
        authors = [
            cleaned
            for a in re.split(r"[;,]| and ", author)
            if (cleaned := re.sub(r"[*†‡§¶\d]+$", "", a.strip()).strip())
        ]

        # PDF 日付は "D:20190214..." 形式
        published = ""
        date_match = re.match(
            r"^D:(\d{4})(\d{2})(\d{2})", str(info.get("creationDate") or "")
        )
        if date_match:
            published = "-".join(date_match.groups())

        return PaperMetadata(
            arxiv_id=doc_id,
            title=title,
            authors=authors,
            published=published,
            abstract=extract_abstract_from_markdown(markdown),
            source_type="pdf",
        )

    async def _fetch_and_parse_generic(self, url: str) -> PaperContent | None:
        """arXiv 以外の URL を取得し、PDF / HTML に応じて Markdown 化する"""
        response = await self.fetch_document(url)
        if response is None:
            return None

        doc_id = self.document_id(url)

        if self._is_pdf_response(response):
            pdf_data = response.content
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
            return PaperContent(
                markdown=markdown,
                images=images,
                metadata=self.extract_pdf_metadata(pdf_data, markdown, doc_id),
                pdf_bytes=pdf_data,
            )

        if self._is_html_response(response):
            logger.info("Converting HTML page to Markdown...")
            web_doc = WebDocumentConverter().convert(
                response.text, base_url=str(response.url)
            )
            if not web_doc.markdown.strip():
                logger.error(f"Empty markdown from HTML: {url}")
                return None
            logger.info(f"Markdown generated: {len(web_doc.markdown)} chars")
            return PaperContent(
                markdown=web_doc.markdown,
                metadata=PaperMetadata(
                    arxiv_id=doc_id,
                    title=web_doc.title or doc_id,
                    authors=web_doc.authors,
                    published=web_doc.published,
                    abstract=web_doc.abstract,
                    source_type="html",
                ),
            )

        content_type = response.headers.get("content-type", "")
        logger.error(f"Unsupported content-type ({content_type}): {url}")
        return None

    async def fetch_and_parse(self, url: str) -> PaperContent | None:
        """PDF取得→解析→メタデータ取得の一連処理

        arXiv URL は arXiv の PDF と API メタデータを使う。それ以外の URL は
        レスポンスの種類（PDF / HTML）に応じて変換する。

        Args:
            url: 論文・文書のURL（arXiv / 一般 PDF / Webページ）

        Returns:
            PaperContent（失敗時はNone）
        """
        if not self.validate_arxiv_url(url):
            if not self.validate_url(url):
                logger.error(f"URLが不正です: {url}")
                return None
            return await self._fetch_and_parse_generic(url)

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
            pdf_bytes=pdf_data,
        )
