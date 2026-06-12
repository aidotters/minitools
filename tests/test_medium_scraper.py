"""Tests for MediumScraper with mocked Playwright."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from minitools.scrapers.medium_scraper import MediumScraper


@pytest.fixture
def scraper():
    """スタンドアロンモードのMediumScraperインスタンスを返す"""
    return MediumScraper()


@pytest.fixture
def cdp_scraper():
    """CDPモードのMediumScraperインスタンスを返す"""
    return MediumScraper(cdp_mode=True)


class TestMediumScraperInit:
    """初期化のテスト"""

    def test_init_defaults(self):
        """デフォルト値"""
        s = MediumScraper()
        assert s.headless is True
        assert s.cdp_mode is False
        assert s._playwright is None
        assert s._browser is None
        assert s._context is None
        assert s._chrome_process is None

    def test_init_standalone_mode(self):
        """スタンドアロンモードで初期化"""
        s = MediumScraper(headless=False)
        assert s.headless is False
        assert s.cdp_mode is False

    def test_init_cdp_mode(self):
        """CDPモードで初期化"""
        s = MediumScraper(cdp_mode=True)
        assert s.cdp_mode is True


class TestMediumScraperContextManager:
    """async context managerのテスト"""

    @pytest.mark.asyncio
    async def test_aexit_standalone_cleanup(self, scraper):
        """スタンドアロンモード: __aexit__でブラウザリソースが解放される"""
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()
        scraper._browser = mock_browser
        scraper._playwright = mock_playwright
        scraper._context = MagicMock()

        await scraper.__aexit__(None, None, None)

        mock_browser.close.assert_awaited_once()
        mock_playwright.stop.assert_awaited_once()
        assert scraper._browser is None
        assert scraper._context is None

    @pytest.mark.asyncio
    async def test_aexit_cdp_cleanup(self, cdp_scraper):
        """CDPモード: __aexit__でplaywright.stop()のみ実行（browser.close()は呼ばない）"""
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()
        cdp_scraper._browser = mock_browser
        cdp_scraper._playwright = mock_playwright
        cdp_scraper._context = MagicMock()

        await cdp_scraper.__aexit__(None, None, None)

        mock_browser.close.assert_not_awaited()
        mock_playwright.stop.assert_awaited_once()
        assert cdp_scraper._browser is None
        assert cdp_scraper._context is None

    @pytest.mark.asyncio
    async def test_aexit_without_browser(self, scraper):
        """ブラウザが未初期化でも__aexit__はエラーにならない"""
        scraper._browser = None
        scraper._playwright = None

        await scraper.__aexit__(None, None, None)
        assert scraper._browser is None


class TestMediumScraperScrapeArticle:
    """scrape_articleのテスト"""

    @pytest.mark.asyncio
    async def test_scrape_article_success(self, scraper):
        """記事HTMLが正常に取得される（outerHTML）"""
        mock_page = AsyncMock()
        mock_article = AsyncMock()
        mock_article.evaluate.return_value = (
            "<article><h1>Test</h1><p>Content</p></article>"
        )

        # query_selectorをセレクタごとに分岐
        async def query_selector(selector):
            if selector == "article":
                return mock_article
            # Cloudflare/エラーページ検出用セレクタにはNoneを返す
            return None

        mock_page.query_selector = AsyncMock(side_effect=query_selector)
        mock_page.title.return_value = "Test Article - Medium"
        mock_page.close = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        scraper._context = mock_context

        result = await scraper.scrape_article("https://medium.com/test-article")

        assert "<article>" in result
        assert "<h1>Test</h1>" in result
        mock_page.goto.assert_awaited_once()
        mock_article.evaluate.assert_awaited_once_with("el => el.outerHTML")
        mock_page.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scrape_article_no_article_tag(self, scraper):
        """articleタグがない場合は空文字列を返す（bodyフォールバックなし）"""
        mock_page = AsyncMock()
        mock_page.query_selector.return_value = None
        mock_page.title.return_value = "Some Page"
        mock_page.close = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        scraper._context = mock_context

        result = await scraper.scrape_article("https://medium.com/test")
        assert result == ""
        mock_page.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scrape_article_exception(self, scraper):
        """例外発生時は空文字列を返す"""
        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("Network error")
        mock_page.close = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        scraper._context = mock_context

        result = await scraper.scrape_article("https://medium.com/test")
        assert result == ""
        mock_page.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scrape_article_no_context(self, scraper):
        """ブラウザ未初期化時はRuntimeError"""
        scraper._context = None

        with pytest.raises(RuntimeError, match="Browser not initialized"):
            await scraper.scrape_article("https://medium.com/test")


class TestMediumScraperDateExtraction:
    """元日付メタ抽出（last_dates）のテスト"""

    @pytest.mark.asyncio
    async def test_last_dates_populated_on_success(self, scraper):
        """本文取得成功時に JSON-LD 由来の日付が last_dates に格納される"""
        mock_page = AsyncMock()
        mock_article = AsyncMock()
        mock_article.evaluate.return_value = "<article>" + "x" * 4000 + "</article>"

        async def query_selector(selector):
            if selector == "article":
                return mock_article
            return None

        mock_page.query_selector = AsyncMock(side_effect=query_selector)
        mock_page.title.return_value = "Test - Medium"
        mock_page.close = AsyncMock()
        # page.evaluate は日付シグナル JS の戻り値（_extract_dates 用）
        mock_page.evaluate = AsyncMock(
            return_value={
                "jsonld": [
                    {
                        "datePublished": "2026-03-09T15:05:43Z",
                        "dateModified": "2026-03-26T08:15:41Z",
                    }
                ],
                "ogPublished": "2026-03-26T08:15:41.297Z",
                "ogModified": None,
            }
        )

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        scraper._context = mock_context

        await scraper.scrape_article("https://medium.com/test")

        # JSON-LD datePublished(3/9) が og(3/26) に勝つ
        assert scraper.last_dates["published_at"] == "2026-03-09"
        assert scraper.last_dates["last_modified"] == "2026-03-26"
        assert scraper.last_dates["published_at_source"] == "html-meta"

    @pytest.mark.asyncio
    async def test_last_dates_reset_on_early_return(self, scraper):
        """前回の値が残らないよう、article 不在の早期 return で last_dates がリセットされる"""
        # 事前に値を汚しておく
        scraper.last_dates = {
            "published_at": "2020-01-01",
            "last_modified": "2020-01-01",
            "published_at_source": "html-meta",
            "last_modified_source": "html-meta",
        }

        mock_page = AsyncMock()
        mock_page.query_selector.return_value = None  # article 不在
        mock_page.title.return_value = "Some Page"
        mock_page.close = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        scraper._context = mock_context

        result = await scraper.scrape_article("https://medium.com/test")
        assert result == ""
        # 早期 return でもリセットされ、stale な 2020 が残らない
        assert scraper.last_dates["published_at"] is None
        assert scraper.last_dates["published_at_source"] == "unknown"

    @pytest.mark.asyncio
    async def test_date_extraction_failure_non_critical(self, scraper):
        """日付抽出が例外でも本文取得は成功し last_dates は unknown のまま"""
        mock_page = AsyncMock()
        mock_article = AsyncMock()
        mock_article.evaluate.return_value = "<article>" + "x" * 4000 + "</article>"

        async def query_selector(selector):
            if selector == "article":
                return mock_article
            return None

        mock_page.query_selector = AsyncMock(side_effect=query_selector)
        mock_page.title.return_value = "Test - Medium"
        mock_page.close = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("eval boom"))

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        scraper._context = mock_context

        result = await scraper.scrape_article("https://medium.com/test")
        assert "<article>" in result  # 本文は取得できる
        assert scraper.last_dates["published_at"] is None
        assert scraper.last_dates["published_at_source"] == "unknown"


class TestMediumScraperCloudflareDetection:
    """Cloudflareチャレンジ検出のテスト"""

    @pytest.mark.asyncio
    async def test_cloudflare_detected_by_title(self, scraper):
        """タイトルに'just a moment'がある場合にCloudflareと判定"""
        mock_page = AsyncMock()
        mock_page.title.return_value = "Just a moment..."
        mock_page.query_selector.return_value = None

        result = await scraper._is_cloudflare_challenge(mock_page)
        assert result is True

    @pytest.mark.asyncio
    async def test_cloudflare_detected_by_element(self, scraper):
        """#cf-challenge-running要素がある場合にCloudflareと判定"""
        mock_page = AsyncMock()
        mock_page.title.return_value = "Loading..."
        mock_page.query_selector.return_value = MagicMock()

        result = await scraper._is_cloudflare_challenge(mock_page)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_cloudflare(self, scraper):
        """通常ページではCloudflareと判定されない"""
        mock_page = AsyncMock()
        mock_page.title.return_value = "My Article - Medium"
        mock_page.query_selector.return_value = None

        result = await scraper._is_cloudflare_challenge(mock_page)
        assert result is False

    @pytest.mark.asyncio
    async def test_cloudflare_exception_returns_false(self, scraper):
        """例外発生時はFalse"""
        mock_page = AsyncMock()
        mock_page.title.side_effect = Exception("Page crashed")

        result = await scraper._is_cloudflare_challenge(mock_page)
        assert result is False


class TestMediumScraperErrorPageDetection:
    """エラーページ検出のテスト"""

    @pytest.mark.asyncio
    async def test_error_page_404_title(self, scraper):
        """タイトルに'404'がある場合にエラーページと判定"""
        mock_page = AsyncMock()
        mock_page.title.return_value = "404 - Page Not Found"

        result = await scraper._is_error_page(mock_page)
        assert result is True

    @pytest.mark.asyncio
    async def test_error_page_medium_specific(self, scraper):
        """Mediumの404ページタイトル'out of the loop'を検出"""
        mock_page = AsyncMock()
        mock_page.title.return_value = "Out of the loop"

        result = await scraper._is_error_page(mock_page)
        assert result is True

    @pytest.mark.asyncio
    async def test_error_page_h1_404(self, scraper):
        """h1に'404'がある場合にエラーページと判定"""
        mock_page = AsyncMock()
        mock_page.title.return_value = "Medium"
        mock_h1 = AsyncMock()
        mock_h1.inner_text.return_value = "404"
        mock_page.query_selector.return_value = mock_h1

        result = await scraper._is_error_page(mock_page)
        assert result is True

    @pytest.mark.asyncio
    async def test_normal_page_not_error(self, scraper):
        """通常ページではエラーと判定されない"""
        mock_page = AsyncMock()
        mock_page.title.return_value = "Great Article About AI - Medium"
        mock_page.query_selector.return_value = None

        result = await scraper._is_error_page(mock_page)
        assert result is False

    @pytest.mark.asyncio
    async def test_error_page_exception_returns_false(self, scraper):
        """例外発生時はFalse"""
        mock_page = AsyncMock()
        mock_page.title.side_effect = Exception("Page crashed")

        result = await scraper._is_error_page(mock_page)
        assert result is False


class TestMediumScraperCDP:
    """CDP接続関連のテスト"""

    @pytest.mark.asyncio
    async def test_connect_cdp_failure(self, cdp_scraper):
        """CDP接続失敗時にRuntimeError"""
        mock_playwright = MagicMock()
        mock_chromium = MagicMock()
        mock_chromium.connect_over_cdp = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        mock_playwright.chromium = mock_chromium
        cdp_scraper._playwright = mock_playwright

        with patch.object(cdp_scraper, "_is_chrome_running", return_value=True):
            with pytest.raises(
                RuntimeError, match="Failed to connect to Chrome via CDP"
            ):
                await cdp_scraper._connect_cdp()

    @pytest.mark.asyncio
    async def test_is_chrome_running_false_on_error(self, cdp_scraper):
        """httpx接続エラー時はFalseを返す"""
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_async_client.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_async_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await cdp_scraper._is_chrome_running()
            assert result is False
