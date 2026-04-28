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

        result = await scraper.fetch_and_parse("https://example.com/paper")
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
