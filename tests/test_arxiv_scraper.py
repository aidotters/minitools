"""Tests for ArxivScraper (PDF-based)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from minitools.scrapers.arxiv_scraper import (
    ArxivScraper,
    PaperContent,
    PaperImage,
    PaperMetadata,
)


class TestValidateArxivUrl:
    """ArXiv URLバリデーションのテスト"""

    def setup_method(self):
        self.scraper = ArxivScraper()

    def test_valid_url(self):
        assert self.scraper.validate_arxiv_url("https://arxiv.org/abs/2401.12345")

    def test_valid_export_url(self):
        assert self.scraper.validate_arxiv_url(
            "https://export.arxiv.org/abs/2401.12345"
        )

    def test_valid_www_url(self):
        assert self.scraper.validate_arxiv_url("https://www.arxiv.org/abs/2401.12345")

    def test_invalid_domain(self):
        assert not self.scraper.validate_arxiv_url("https://example.com/abs/2401.12345")

    def test_invalid_medium_url(self):
        assert not self.scraper.validate_arxiv_url("https://medium.com/some-article")

    def test_empty_url(self):
        assert not self.scraper.validate_arxiv_url("")


class TestExtractArxivId:
    """arXiv ID抽出のテスト"""

    def test_abs_url(self):
        result = ArxivScraper.extract_arxiv_id("https://arxiv.org/abs/2401.12345")
        assert result == "2401.12345"

    def test_abs_url_with_version(self):
        result = ArxivScraper.extract_arxiv_id("https://arxiv.org/abs/2401.12345v2")
        assert result == "2401.12345v2"

    def test_pdf_url(self):
        result = ArxivScraper.extract_arxiv_id("https://arxiv.org/pdf/2401.12345")
        assert result == "2401.12345"

    def test_html_url(self):
        result = ArxivScraper.extract_arxiv_id("https://arxiv.org/html/2401.12345")
        assert result == "2401.12345"

    def test_old_format_id(self):
        result = ArxivScraper.extract_arxiv_id("https://arxiv.org/abs/cs.AI/0301001")
        assert result == "cs.AI/0301001"

    def test_trailing_slash(self):
        result = ArxivScraper.extract_arxiv_id("https://arxiv.org/abs/2401.12345/")
        assert result == "2401.12345"

    def test_pdf_extension(self):
        result = ArxivScraper.extract_arxiv_id("https://arxiv.org/pdf/2401.12345.pdf")
        assert result == "2401.12345"

    def test_invalid_url(self):
        result = ArxivScraper.extract_arxiv_id("https://example.com/foo")
        assert result is None


class TestConvertToPdfUrl:
    """ArXiv URL → PDF URL変換のテスト"""

    def setup_method(self):
        self.scraper = ArxivScraper()

    def test_abs_url(self):
        result = self.scraper._convert_to_pdf_url("https://arxiv.org/abs/2401.12345")
        assert result == "https://arxiv.org/pdf/2401.12345"

    def test_abs_url_with_version(self):
        result = self.scraper._convert_to_pdf_url("https://arxiv.org/abs/2401.12345v2")
        assert result == "https://arxiv.org/pdf/2401.12345v2"

    def test_html_url(self):
        result = self.scraper._convert_to_pdf_url("https://arxiv.org/html/2401.12345")
        assert result == "https://arxiv.org/pdf/2401.12345"

    def test_http_url(self):
        result = self.scraper._convert_to_pdf_url("http://arxiv.org/abs/2401.12345")
        assert result == "https://arxiv.org/pdf/2401.12345"

    def test_export_domain(self):
        result = self.scraper._convert_to_pdf_url(
            "https://export.arxiv.org/abs/2401.12345"
        )
        assert result == "https://arxiv.org/pdf/2401.12345"

    def test_old_format_id(self):
        result = self.scraper._convert_to_pdf_url("https://arxiv.org/abs/cs.AI/0301001")
        assert result == "https://arxiv.org/pdf/cs.AI/0301001"

    def test_trailing_slash(self):
        result = self.scraper._convert_to_pdf_url("https://arxiv.org/abs/2401.12345/")
        assert result == "https://arxiv.org/pdf/2401.12345"


class TestParseToMarkdown:
    """PDF→Markdown変換のテスト（marker-pdfをモック）"""

    def setup_method(self):
        self.scraper = ArxivScraper()

    @patch("marker.models.create_model_dict")
    @patch("marker.converters.pdf.PdfConverter")
    def test_basic_conversion(self, mock_converter_cls, mock_create_models):
        """基本的な変換"""
        mock_create_models.return_value = {}
        mock_result = MagicMock()
        mock_result.markdown = "# Title\n\nSome content with $E=mc^2$"
        mock_result.images = {}
        mock_converter_cls.return_value.return_value = mock_result

        markdown, images = self.scraper.parse_to_markdown(b"fake pdf data")

        assert "# Title" in markdown
        assert "$E=mc^2$" in markdown
        assert len(images) == 0

    @patch("marker.models.create_model_dict")
    @patch("marker.converters.pdf.PdfConverter")
    def test_with_images(self, mock_converter_cls, mock_create_models):
        """画像付き変換"""
        mock_create_models.return_value = {}
        mock_result = MagicMock()
        mock_result.markdown = "# Paper\n\n![Figure 1](figure_1.png)"
        mock_result.images = {
            "figure_1.png": b"fake image data",
            "figure_2.png": b"fake image data 2",
        }
        mock_converter_cls.return_value.return_value = mock_result

        markdown, images = self.scraper.parse_to_markdown(b"fake pdf data")

        assert len(images) == 2
        assert images[0].filename == "figure_1.png"
        assert images[0].data == b"fake image data"


class TestFetchMetadata:
    """メタデータ取得のテスト"""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """正常なメタデータ取得"""
        mock_response_text = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Test Paper Title</title>
    <summary>This is the abstract.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Author One</name></author>
    <author><name>Author Two</name></author>
  </entry>
</feed>"""

        scraper = ArxivScraper()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = mock_response_text
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        scraper._client = mock_client

        result = await scraper.fetch_metadata("2401.12345")

        assert result is not None
        assert result.arxiv_id == "2401.12345"
        assert result.title == "Test Paper Title"
        assert result.authors == ["Author One", "Author Two"]
        assert result.published == "2024-01-15"
        assert result.abstract == "This is the abstract."

    @pytest.mark.asyncio
    async def test_not_found(self):
        """メタデータが見つからない場合"""
        mock_response_text = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""

        scraper = ArxivScraper()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = mock_response_text
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        scraper._client = mock_client

        result = await scraper.fetch_metadata("9999.99999")
        assert result is None

    @pytest.mark.asyncio
    async def test_api_error(self):
        """API呼び出しエラー"""
        scraper = ArxivScraper()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))
        scraper._client = mock_client

        result = await scraper.fetch_metadata("2401.12345")
        assert result is None


class TestFetchPdf:
    """PDF取得のテスト"""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """正常なPDF取得"""
        scraper = ArxivScraper()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4 fake content"
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        scraper._client = mock_client

        result = await scraper.fetch_pdf("https://arxiv.org/abs/2401.12345")

        assert result == b"%PDF-1.4 fake content"

    @pytest.mark.asyncio
    async def test_not_pdf_response(self):
        """PDF以外のレスポンス"""
        scraper = ArxivScraper()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = b"<html>Not a PDF</html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        scraper._client = mock_client

        result = await scraper.fetch_pdf("https://arxiv.org/abs/2401.12345")
        assert result is None


class TestFetchAndParse:
    """統合テスト（fetch_and_parse）"""

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        """無効なURLの場合"""
        scraper = ArxivScraper()
        scraper._client = AsyncMock()

        result = await scraper.fetch_and_parse("not-a-url")
        assert result is None

    @pytest.mark.asyncio
    async def test_pdf_fetch_failure(self):
        """PDF取��失敗の場合"""
        scraper = ArxivScraper()
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = b"<html>Error</html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        scraper._client = mock_client

        result = await scraper.fetch_and_parse("https://arxiv.org/abs/2401.12345")
        assert result is None

    @pytest.mark.asyncio
    async def test_success(self):
        """正常系: PDF取得→解析→メタデータ取得の一連処理"""
        scraper = ArxivScraper()

        # PDF取得用モック
        pdf_response = MagicMock()
        pdf_response.content = b"%PDF-1.4 fake content"
        pdf_response.headers = {"content-type": "application/pdf"}
        pdf_response.raise_for_status = MagicMock()

        # メタデータ取得用モック
        metadata_response = MagicMock()
        metadata_response.text = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Test Paper</title>
    <summary>Abstract.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Author</name></author>
  </entry>
</feed>"""
        metadata_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[pdf_response, metadata_response])
        scraper._client = mock_client

        # parse_to_markdownをモック
        with patch.object(
            scraper,
            "parse_to_markdown",
            return_value=("# Title\nContent", []),
        ):
            result = await scraper.fetch_and_parse("https://arxiv.org/abs/2401.12345")

        assert result is not None
        assert result.markdown == "# Title\nContent"
        assert result.images == []
        assert result.metadata is not None
        assert result.metadata.title == "Test Paper"


class TestDataClasses:
    """データクラスの���スト"""

    def test_paper_image(self):
        img = PaperImage(data=b"data", filename="fig1.png", caption="Figure 1")
        assert img.data == b"data"
        assert img.filename == "fig1.png"
        assert img.caption == "Figure 1"

    def test_paper_image_default_caption(self):
        img = PaperImage(data=b"data", filename="fig1.png")
        assert img.caption == ""

    def test_paper_metadata(self):
        meta = PaperMetadata(
            arxiv_id="2401.12345",
            title="Test Paper",
            authors=["Author A", "Author B"],
            published="2024-01-15",
            abstract="Abstract text",
        )
        assert meta.arxiv_id == "2401.12345"
        assert len(meta.authors) == 2

    def test_paper_content(self):
        content = PaperContent(markdown="# Title\nContent")
        assert content.markdown == "# Title\nContent"
        assert content.images == []
        assert content.metadata is None

    def test_paper_content_with_metadata(self):
        meta = PaperMetadata(
            arxiv_id="2401.12345",
            title="Test",
            authors=[],
            published="2024-01-15",
            abstract="",
        )
        content = PaperContent(
            markdown="# Title",
            images=[PaperImage(data=b"x", filename="f.png")],
            metadata=meta,
        )
        assert content.metadata is not None
        assert len(content.images) == 1


class TestDocumentId:
    """出力フォルダ名に使う文書IDの導出"""

    def test_arxiv_url_keeps_existing_id(self):
        assert ArxivScraper.document_id("https://arxiv.org/abs/2401.12345") == (
            "2401.12345"
        )

    def test_arxiv_old_format_id(self):
        assert ArxivScraper.document_id("https://arxiv.org/abs/cs.AI/0301001") == (
            "cs.AI_0301001"
        )

    def test_generic_pdf_url(self):
        doc_id = ArxivScraper.document_id(
            "https://cdn.openai.com/better-language-models/"
            "language_models_are_unsupervised_multitask_learners.pdf"
        )
        assert doc_id.startswith(
            "cdn.openai.com_language_models_are_unsupervised_multitask_learners_"
        )
        assert len(doc_id.rsplit("_", 1)[1]) == 8

    def test_different_urls_with_same_slug_differ(self):
        a = ArxivScraper.document_id("https://example.com/a/index.html")
        b = ArxivScraper.document_id("https://example.com/b/index.html")
        assert a != b
        assert a.startswith("example.com_index_")

    def test_strips_www(self):
        doc_id = ArxivScraper.document_id("https://www.example.com/post")
        assert doc_id.startswith("example.com_post_")


class TestValidateUrl:
    """一般 URL バリデーション"""

    def test_https(self):
        assert ArxivScraper.validate_url("https://d2l.ai/chapter/page.html")

    def test_http(self):
        assert ArxivScraper.validate_url("http://example.com/paper.pdf")

    def test_invalid(self):
        assert not ArxivScraper.validate_url("not-a-url")
        assert not ArxivScraper.validate_url("ftp://example.com/file.pdf")
        assert not ArxivScraper.validate_url("")


class TestFetchAndParseGeneric:
    """arXiv 以外の URL（一般 PDF / HTML）の取得と振り分け"""

    @staticmethod
    def _response(content: bytes, content_type: str, url: str) -> MagicMock:
        response = MagicMock()
        response.content = content
        response.text = content.decode("utf-8", errors="ignore")
        response.headers = {"content-type": content_type}
        response.url = url
        response.raise_for_status = MagicMock()
        return response

    @pytest.mark.asyncio
    async def test_pdf_by_magic_bytes(self):
        """content-type が不正確でも %PDF- で PDF と判定する"""
        scraper = ArxivScraper()
        url = "https://example.com/files/paper.pdf"
        scraper._client = AsyncMock()
        scraper._client.get = AsyncMock(
            return_value=self._response(
                b"%PDF-1.5 dummy", "application/octet-stream", url
            )
        )
        with patch.object(
            scraper,
            "parse_to_markdown",
            return_value=("# Great Paper\n\n## Abstract\n\nWe study X.\n", []),
        ):
            result = await scraper.fetch_and_parse(url)

        assert result is not None
        assert result.pdf_bytes == b"%PDF-1.5 dummy"
        assert result.metadata is not None
        assert result.metadata.source_type == "pdf"
        assert result.metadata.title == "Great Paper"
        assert result.metadata.abstract == "We study X."
        assert result.metadata.arxiv_id.startswith("example.com_paper_")
        # arXiv API は呼ばない（GET は本体の1回のみ）
        assert scraper._client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_html_page(self):
        scraper = ArxivScraper()
        url = "https://docs.example.com/guide/attention.html"
        html = (
            b"<html><head><title>Attention | Example Docs</title>"
            b'<meta name="description" content="About attention."></head>'
            b'<body><nav>menu</nav><div role="main"><h1>Attention</h1>'
            b'<p>See <img src="../img/fig.png" alt="fig"></p></div></body></html>'
        )
        scraper._client = AsyncMock()
        scraper._client.get = AsyncMock(
            return_value=self._response(html, "text/html; charset=utf-8", url)
        )

        result = await scraper.fetch_and_parse(url)

        assert result is not None
        assert result.pdf_bytes is None
        assert result.metadata is not None
        assert result.metadata.source_type == "html"
        assert result.metadata.title == "Attention"
        assert result.metadata.abstract == "About attention."
        assert "menu" not in result.markdown
        assert "https://docs.example.com/img/fig.png" in result.markdown

    @pytest.mark.asyncio
    async def test_unsupported_content_type(self):
        scraper = ArxivScraper()
        url = "https://example.com/data.json"
        scraper._client = AsyncMock()
        scraper._client.get = AsyncMock(
            return_value=self._response(b'{"a": 1}', "application/json", url)
        )
        assert await scraper.fetch_and_parse(url) is None


class TestExtractPdfMetadata:
    def test_falls_back_to_markdown_heading(self):
        metadata = ArxivScraper.extract_pdf_metadata(
            b"not a real pdf", "# Language Models\n\nBody", "doc_id"
        )
        assert metadata.title == "Language Models"
        assert metadata.source_type == "pdf"

    def test_falls_back_to_doc_id(self):
        metadata = ArxivScraper.extract_pdf_metadata(b"x", "no heading", "doc_id")
        assert metadata.title == "doc_id"


class TestExtractPdfMetadataAuthors:
    def test_authors_footnote_marks_removed(self):
        with patch("fitz.open") as mock_open:
            doc = MagicMock()
            doc.metadata = {
                "title": "Microsoft Word - paper.docx",
                "author": "Alec Radford*, Jeffrey Wu*; Dario Amodei**",
                "creationDate": "D:20190214120000Z",
            }
            mock_open.return_value.__enter__.return_value = doc
            metadata = ArxivScraper.extract_pdf_metadata(
                b"%PDF-", "# Real Title\n", "doc_id"
            )
        assert metadata.title == "Real Title"
        assert metadata.authors == ["Alec Radford", "Jeffrey Wu", "Dario Amodei"]
        assert metadata.published == "2019-02-14"


class TestPaperMetadataCompat:
    def test_legacy_metadata_json_without_source_type(self):
        """source_type が無い既存の metadata.json も読み込める"""
        metadata = PaperMetadata(
            arxiv_id="2401.12345",
            title="T",
            authors=[],
            published="2024-01-01",
            abstract="",
        )
        assert metadata.source_type == "arxiv"
