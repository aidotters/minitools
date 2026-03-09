"""
Medium article scraper using Playwright.

Two modes:
    1. CDP mode (recommended): Connects to user's real Chrome browser.
       Bypasses Cloudflare bot detection and uses existing Medium login.
    2. Standalone mode: Uses Playwright's built-in Chromium.
       May be blocked by Cloudflare.

CDP mode usage:
    # First run: Chrome opens automatically, log in to Medium
    uv run medium-translate --url "..." --cdp --dry-run

    # Subsequent runs: Chrome opens with saved cookies, no login needed
    uv run medium-translate --url "..." --cdp --dry-run --provider gemini
"""

import asyncio
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# CDP用Chromeプロファイルのデフォルトパス
DEFAULT_CHROME_PROFILE = Path.home() / ".minitools" / "chrome-profile"
CDP_PORT = 9222


def _find_chrome_path() -> Optional[str]:
    """システムのChromeブラウザのパスを検出する"""
    if sys.platform == "darwin":
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path(chrome_path).exists():
            return chrome_path
    elif sys.platform == "linux":
        for name in ["google-chrome", "google-chrome-stable", "chromium-browser"]:
            path = shutil.which(name)
            if path:
                return path
    elif sys.platform == "win32":
        import winreg

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            )
            return winreg.QueryValue(key, None)
        except WindowsError:
            pass
    return None


class MediumScraper:
    """Playwrightを使用してMedium記事の全文HTMLを取得するクラス"""

    def __init__(
        self,
        headless: bool = True,
        cdp_mode: bool = False,
    ):
        """
        Args:
            headless: ヘッドレスモードで実行するか（CDPモードでは無視）
            cdp_mode: Trueの場合、実際のChromeにCDP接続する
        """
        self.headless = headless
        self.cdp_mode = cdp_mode
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._chrome_process: Any = None

    async def __aenter__(self) -> "MediumScraper":
        """ブラウザを起動/接続する"""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            if self.cdp_mode:
                await self._connect_cdp()
            else:
                await self._launch_standalone()

            return self
        except ImportError:
            raise ImportError(
                "playwright is required. Install with: "
                "uv sync && playwright install chromium"
            )

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """ブラウザを切断/閉じる"""
        if self.cdp_mode:
            # CDP: browser.close()はChromeプロセスを終了させるため呼ばない
            # playwright.stop()のみでPlaywright側の接続をクリーンアップする
            pass
        else:
            if self._browser:
                await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._context = None

    async def _connect_cdp(self) -> None:
        """実際のChromeにCDP経由で接続する"""
        # Chromeが起動しているか確認、起動していなければ起動する
        if not await self._is_chrome_running():
            await self._launch_chrome()

        # CDP接続
        logger.info(f"Connecting to Chrome via CDP (port {CDP_PORT})...")
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{CDP_PORT}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to connect to Chrome via CDP: {e}\n"
                f"Ensure Chrome is running with --remote-debugging-port={CDP_PORT}"
            )

        # 既存のコンテキストを取得（Chromeの既存タブ/セッション）
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = await self._browser.new_context()

        logger.info("Connected to Chrome via CDP")

        # Mediumログイン状態を確認し、未ログインなら待機
        await self._ensure_medium_login()

    async def _ensure_medium_login(self) -> None:
        """
        Mediumにログイン済みか確認し、未ログインならCDP接続を切断してログインを促す

        CDP接続中はPlaywrightがChromeのウィンドウイベントを支配するため、
        Google OAuthポップアップ等が正常に動作しない。
        CDP接続を完全切断することで、ユーザーが通常通りブラウザを操作できる。
        ログイン完了後にCDP再接続する。
        """
        # ログイン状態チェック
        page = await self._context.new_page()
        needs_login = False
        try:
            logger.info("Checking Medium login status...")
            await page.goto(
                "https://medium.com/me",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(3)

            current_url = page.url
            needs_login = (
                "medium.com/m/signin" in current_url
                or "medium.com/m/callback" in current_url
            )
        except Exception as e:
            logger.warning(f"Medium login check failed (non-critical): {e}")
            return
        finally:
            await page.close()

        if not needs_login:
            logger.info("Medium login confirmed")
            return

        # Playwrightを完全停止してChromeへの干渉を排除する
        # browser.close()はChromeプロセスを終了させるため使わない
        # playwright.stop()でPlaywrightプロセスごと停止する
        logger.info("Stopping Playwright to release Chrome control...")
        self._browser = None
        self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        login_timeout = 300  # 最大5分待機
        poll_interval = 30  # 30秒ごとにチェック

        logger.warning(
            "\n" + "=" * 60 + "\n"
            "  Medium にログインされていません。\n"
            "  Chrome ブラウザで Medium にログインしてください。\n"
            "  （Playwright を停止済み — Google ログイン等が正常に動作します）\n"
            f"  {login_timeout}秒以内にログインしてください（{poll_interval}秒ごとに確認）。\n"
            + "="
            * 60
        )

        # ポーリングでログイン状態を定期チェック
        from playwright.async_api import async_playwright

        elapsed = 0
        logged_in = False

        while elapsed < login_timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            logger.info(f"Checking Medium login status... ({elapsed}/{login_timeout}s)")

            # CDP再接続してログイン状態を確認
            try:
                pw = await async_playwright().start()
                browser = await pw.chromium.connect_over_cdp(
                    f"http://localhost:{CDP_PORT}"
                )
                contexts = browser.contexts
                ctx = contexts[0] if contexts else await browser.new_context()
                check_page = await ctx.new_page()
                try:
                    await check_page.goto(
                        "https://medium.com/me",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    await asyncio.sleep(3)
                    check_url = check_page.url
                    if (
                        "medium.com/m/signin" not in check_url
                        and "medium.com/m/callback" not in check_url
                    ):
                        logged_in = True
                finally:
                    await check_page.close()
                    await pw.stop()
            except Exception as e:
                logger.warning(f"Login poll check failed: {e}")
                continue

            if logged_in:
                logger.info("Medium login confirmed!")
                break
            else:
                logger.info("Not yet logged in, waiting...")

        if not logged_in:
            logger.error(
                f"Login not detected after {login_timeout}s. Skipping Medium scraping."
            )
            raise RuntimeError(
                f"Medium login timeout ({login_timeout}s). "
                "Please log in to Medium in Chrome before running."
            )

        # Playwrightを再起動してCDP再接続
        logger.info("Restarting Playwright and reconnecting to Chrome via CDP...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(
            f"http://localhost:{CDP_PORT}"
        )
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = await self._browser.new_context()

    async def _is_chrome_running(self) -> bool:
        """CDP対応のChromeが起動しているか確認"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://localhost:{CDP_PORT}/json/version",
                    timeout=2,
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def _launch_chrome(self) -> None:
        """Chromeをデバッグポート付きで起動する"""
        chrome_path = _find_chrome_path()
        if not chrome_path:
            raise RuntimeError(
                "Chrome not found. Please install Google Chrome or "
                "start it manually with: "
                f"google-chrome --remote-debugging-port={CDP_PORT} "
                f"--user-data-dir={DEFAULT_CHROME_PROFILE}"
            )

        # プロファイルディレクトリ作成
        DEFAULT_CHROME_PROFILE.mkdir(parents=True, exist_ok=True)

        logger.info("Launching Chrome with debug port...")
        self._chrome_process = subprocess.Popen(
            [
                chrome_path,
                f"--remote-debugging-port={CDP_PORT}",
                f"--user-data-dir={DEFAULT_CHROME_PROFILE}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Chromeの起動を待機
        for _ in range(30):
            if await self._is_chrome_running():
                logger.info("Chrome started successfully")
                return
            await asyncio.sleep(0.5)

        raise RuntimeError("Chrome failed to start within 15 seconds")

    async def _launch_standalone(self) -> None:
        """Playwrightの内蔵Chromiumで起動する（Cloudflareにブロックされる可能性あり）"""
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        logger.warning(
            "Using standalone Chromium. "
            "May be blocked by Cloudflare. Use --cdp for reliable access."
        )

    async def _expand_lazy_content(self, page: Any) -> None:
        """
        遅延読み込みコンテンツを一括で展開する

        ページ最下部へ一度スクロールしてlazy loading要素をトリガーし、
        レンダリング完了を待って最上部に戻す。
        """
        try:
            await page.evaluate(
                "window.scrollTo(0, document.documentElement.scrollHeight)"
            )
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Lazy content expansion failed (non-critical): {e}")

    async def scrape_article(self, url: str) -> str:
        """
        記事URLから全文HTMLを取得する

        毎回新しいページ（タブ）を作成し、完了後に閉じる。
        これにより長時間の翻訳処理中にCDP接続がタイムアウトする問題を防ぐ。

        Args:
            url: Medium記事のURL

        Returns:
            記事のHTML文字列（取得失敗時は空文字列）
        """
        if not self._context:
            raise RuntimeError("Browser not initialized. Use 'async with' context.")

        page = await self._context.new_page()
        try:
            logger.info(f"Scraping article: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # <article>タグの出現を明示的に待機（クライアントサイドレンダリング対応）
            try:
                await page.wait_for_selector("article", timeout=30000)
            except Exception:
                logger.warning(
                    "Timed out waiting for <article> selector, continuing..."
                )
            await asyncio.sleep(random.uniform(1, 2))

            # Cloudflareチャレンジの検出
            if await self._is_cloudflare_challenge(page):
                logger.warning(
                    "Cloudflare challenge detected, waiting for resolution..."
                )
                for _ in range(24):
                    await asyncio.sleep(5)
                    if not await self._is_cloudflare_challenge(page):
                        logger.info("Cloudflare challenge resolved")
                        await asyncio.sleep(2)
                        break
                else:
                    logger.error("Cloudflare challenge not resolved within 2 minutes")
                    return ""

            # エラーページの検出（404等）
            if await self._is_error_page(page):
                logger.error(f"Error page detected for: {url}")
                return ""

            # 遅延読み込みコンテンツを展開する
            await self._expand_lazy_content(page)

            # ペイウォール/ログイン要求の検出
            paywall = await page.query_selector(
                "[data-testid='paywall-background-color'], "
                "[aria-label='upgrade'], "
                "div.meteredContent"
            )
            if paywall:
                logger.warning(
                    "Paywall detected — Medium session may have expired. "
                    "Open the CDP Chrome browser and log in to Medium."
                )

            # 記事本文のHTMLを取得
            article_element = await page.query_selector("article")

            if article_element:
                html = await article_element.evaluate("el => el.outerHTML")
                logger.info(f"Article HTML extracted: {len(html)} chars")

                # コンテンツが短すぎる場合は警告
                if len(html) < 3000:
                    logger.warning(
                        f"Article HTML is suspiciously short ({len(html)} chars). "
                        "Possible causes: paywall, login required, or "
                        "incomplete page load."
                    )

                return html

            logger.error(f"No <article> tag found for: {url}")
            return ""

        except Exception as e:
            logger.error(f"Article scraping failed for {url}: {e}")
            return ""
        finally:
            await page.close()

    async def _is_cloudflare_challenge(self, page: Any) -> bool:
        """現在のページがCloudflareチャレンジかどうかを判定"""
        try:
            title = await page.title()
            if "just a moment" in title.lower():
                return True
            cf_element = await page.query_selector("#cf-challenge-running")
            return cf_element is not None
        except Exception:
            return False

    async def _is_error_page(self, page: Any) -> bool:
        """現在のページがエラーページ（404等）かどうかを判定"""
        try:
            # Medium固有の404ページ検出
            title = await page.title()
            error_titles = [
                "page not found",
                "404",
                "error",
                "out of the loop",  # Mediumの404ページタイトル
            ]
            title_lower = title.lower()
            if any(t in title_lower for t in error_titles):
                return True

            # HTTP status codeベースの検出（h1に"404"等がある場合）
            h1 = await page.query_selector("h1")
            if h1:
                h1_text = await h1.inner_text()
                if "404" in h1_text or "not found" in h1_text.lower():
                    return True

            return False
        except Exception:
            return False
