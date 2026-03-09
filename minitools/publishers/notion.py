"""
Notion publisher module for saving content to Notion databases.
"""

import os
import asyncio
from typing import Any, Dict, List, NamedTuple, Optional, cast
from notion_client import Client

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class PageInfo(NamedTuple):
    """find_page_by_urlの返り値"""

    page_id: str
    is_translated: bool


class NotionPublisher:
    """Notionデータベースにコンテンツを保存するクラス"""

    def __init__(
        self, api_key: Optional[str] = None, source_type: Optional[str] = None
    ):
        """
        Args:
            api_key: Notion APIキー（指定しない場合は環境変数から取得）
            source_type: ソースタイプ（'arxiv', 'medium', 'google_alerts'）
        """
        self.api_key = api_key or os.getenv("NOTION_API_KEY")
        if not self.api_key:
            raise ValueError("NOTION_API_KEY is required")

        self.source_type = source_type
        self.client = Client(auth=self.api_key)
        logger.info(f"Notion client initialized (source_type: {source_type})")

    async def _retry_api_call(
        self, func, max_retries: int = 3, description: str = "API call"
    ):
        """
        Notion APIコールをレートリミット対応のリトライ付きで実行

        Args:
            func: 実行する同期関数（lambda）
            max_retries: 最大リトライ回数
            description: ログ用の説明

        Returns:
            API呼び出しの結果
        """
        loop = asyncio.get_event_loop()
        for attempt in range(max_retries):
            try:
                return await loop.run_in_executor(None, func)
            except Exception as e:
                if "rate limited" in str(e).lower() and attempt < max_retries - 1:
                    delay = 2 ** (attempt + 1)  # 2, 4, 8秒
                    logger.warning(
                        f"  Rate limited ({description}), "
                        f"retrying in {delay}s... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

    def _normalize_url_by_source(self, url: str) -> str:
        """
        ソースタイプに応じたURL正規化

        Args:
            url: 正規化するURL

        Returns:
            正規化されたURL
        """
        if self.source_type == "arxiv":
            # ArXiv固有の正規化（バージョン番号は保持）
            url = url.replace("http://", "https://")
            url = url.replace("export.arxiv.org", "arxiv.org")
            logger.info(f"ArXiv URL normalized: {url}")
        elif self.source_type == "medium":
            # Medium固有の正規化（パラメータ除去、末尾スラッシュ除去）
            url = url.split("?")[0]
            url = url.rstrip("/")
            if "#" in url:
                url = url.split("#")[0]
            logger.debug(f"Medium URL normalized: {url}")
        elif self.source_type == "google_alerts":
            # Google Alerts固有の正規化（パラメータ除去、末尾スラッシュ除去）
            original_url = url
            url = url.split("?")[0]  # トラッキングパラメータ除去
            url = url.rstrip("/")  # 末尾スラッシュ除去
            if "#" in url:
                url = url.split("#")[0]  # フラグメント除去
            logger.info(f"Google Alerts URL normalized: {original_url} -> {url}")
        return url

    async def check_existing(self, database_id: str, url: str) -> bool:
        """
        URLが既にデータベースに存在するかチェック
        HTTPSとHTTP両方のバージョンをチェックして過去データとの互換性を保つ

        Args:
            database_id: NotionデータベースID
            url: チェックするURL

        Returns:
            存在する場合True
        """
        try:
            # ソースタイプに応じたURL正規化（HTTPS版）
            normalized_url = self._normalize_url_by_source(url)

            logger.info(
                f"Checking URL in DB {database_id[:8]}... (source: {self.source_type})"
            )
            logger.debug(f"  Original URL: {url}")
            logger.info(f"  Normalized URL: {normalized_url}")

            # まずHTTPS版で検索
            result = cast(
                Dict[str, Any],
                await self._retry_api_call(
                    lambda: self.client.databases.query(
                        database_id=database_id,
                        filter={"property": "URL", "url": {"equals": normalized_url}},
                    ),
                    description=f"check_existing({normalized_url[:50]})",
                ),
            )

            exists = len(result.get("results", [])) > 0
            logger.debug(f"  Query result count: {len(result.get('results', []))}")

            # HTTPS版で見つからない場合、HTTP版でも検索（過去データとの互換性）
            if (
                not exists
                and self.source_type == "arxiv"
                and normalized_url.startswith("https://")
            ):
                http_url = normalized_url.replace("https://", "http://")
                logger.info(f"  Checking HTTP version: {http_url}")

                result = cast(
                    Dict[str, Any],
                    await self._retry_api_call(
                        lambda: self.client.databases.query(
                            database_id=database_id,
                            filter={"property": "URL", "url": {"equals": http_url}},
                        ),
                        description=f"check_existing_http({http_url[:50]})",
                    ),
                )

                exists = len(result.get("results", [])) > 0
                logger.info(
                    f"  HTTP query result count: {len(result.get('results', []))}"
                )

                if exists:
                    logger.info("  Found with HTTP protocol (legacy data)")

            if exists:
                # 既存のエントリのURLも表示
                existing_urls = [
                    item.get("properties", {}).get("URL", {}).get("url", "N/A")
                    for item in result.get("results", [])
                ]
                logger.info(f"  既存のURL: {existing_urls}")
                logger.info(f"既に存在するためスキップ ({self.source_type}): {url}")
            else:
                logger.info(
                    f"新規記事として処理 ({self.source_type}): {normalized_url}"
                )
            return exists

        except Exception as e:
            logger.error(f"重複チェックエラー ({self.source_type}): {e}")
            logger.warning("安全のためスキップします（次回の実行で再処理されます）")
            return True

    async def create_page(
        self, database_id: str, properties: Dict[str, Any]
    ) -> Optional[str]:
        """
        Notionページを作成

        Args:
            database_id: NotionデータベースID
            properties: ページプロパティ

        Returns:
            作成されたページのID
        """
        try:
            page = cast(
                Dict[str, Any],
                await self._retry_api_call(
                    lambda: self.client.pages.create(
                        parent={"database_id": database_id}, properties=properties
                    ),
                    description="create_page",
                ),
            )

            page_id = page.get("id")
            logger.debug(f"Notionページ作成完了: {page_id}")
            return page_id

        except Exception as e:
            logger.error(f"Notionページ作成エラー: {e}")
            return None

    async def save_article(
        self, database_id: str, article_data: Dict[str, Any]
    ) -> bool:
        """
        記事をNotionデータベースに保存

        Args:
            database_id: NotionデータベースID
            article_data: 記事データ（title, url, author, summary等を含む辞書）

        Returns:
            保存成功の場合True
        """
        # URLの重複チェック
        url = article_data.get("url")
        title = article_data.get("title", "Unknown")
        author = article_data.get("author", "Unknown")

        logger.info(f"  -> 重複チェック開始: {url}")
        if url and await self.check_existing(database_id, url):
            logger.info(
                f"  -> 既に存在するためスキップ: {title[:50]}..."
                if len(title) > 50
                else f"  -> 既に存在するためスキップ: {title}"
            )
            return False

        logger.info(
            f"  -> Notionに保存中: {title[:50]}..."
            if len(title) > 50
            else f"  -> Notionに保存中: {title}"
        )

        # Notionプロパティの構築
        properties = self._build_article_properties(article_data)

        # ページ作成
        page_id = await self.create_page(database_id, properties)

        if page_id:
            logger.info(
                f"  -> 保存完了: {title[:50]}... by {author}"
                if len(title) > 50
                else f"  -> 保存完了: {title} by {author}"
            )
        else:
            logger.error(
                f"  -> 保存失敗: {title[:50]}..."
                if len(title) > 50
                else f"  -> 保存失敗: {title}"
            )

        return page_id is not None

    def _build_article_properties(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        記事データからNotionプロパティを構築

        Args:
            article_data: 記事データ

        Returns:
            Notionプロパティ辞書
        """
        # source_typeに応じて適切なプロパティ構築メソッドを使用
        if self.source_type == "arxiv":
            return self._build_arxiv_properties(article_data)
        elif self.source_type == "medium":
            return self._build_medium_properties(article_data)
        elif self.source_type == "google_alerts":
            return self._build_google_alerts_properties(article_data)
        else:
            # デフォルトはGoogle Alerts形式
            return self._build_google_alerts_properties(article_data)

    def _build_arxiv_properties(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ArXiv用の日本語プロパティを構築

        Args:
            article_data: 記事データ

        Returns:
            Notionプロパティ辞書（日本語プロパティ名）
        """
        properties: Dict[str, Any] = {}

        # タイトル（日本語プロパティ名）
        if "title" in article_data:
            properties["タイトル"] = {
                "title": [{"text": {"content": article_data["title"]}}]
            }

        # 公開日
        if "published" in article_data:
            properties["公開日"] = {
                "date": {"start": article_data["published"][:10]}  # YYYY-MM-DD形式
            }
        elif "date" in article_data:
            properties["公開日"] = {"date": {"start": article_data["date"]}}

        # 更新日
        if "updated" in article_data:
            properties["更新日"] = {"date": {"start": article_data["updated"][:10]}}
        elif "date" in article_data:
            properties["更新日"] = {"date": {"start": article_data["date"]}}

        # 概要（英語の要約）
        if "abstract" in article_data:
            properties["概要"] = {
                "rich_text": [{"text": {"content": article_data["abstract"][:2000]}}]
            }
        elif "summary" in article_data:
            properties["概要"] = {
                "rich_text": [{"text": {"content": article_data["summary"][:2000]}}]
            }

        # 日本語訳（翻訳された要約）
        if "japanese_summary" in article_data:
            properties["日本語訳"] = {
                "rich_text": [
                    {"text": {"content": article_data["japanese_summary"][:2000]}}
                ]
            }

        # URL（正規化して保存）
        if "url" in article_data:
            normalized_url = self._normalize_url_by_source(article_data["url"])
            properties["URL"] = {"url": normalized_url}
            logger.info(f"  Saving normalized URL: {normalized_url}")
        elif "pdf_url" in article_data:
            normalized_url = self._normalize_url_by_source(article_data["pdf_url"])
            properties["URL"] = {"url": normalized_url}
            logger.info(f"  Saving normalized PDF URL: {normalized_url}")

        return properties

    def _build_medium_properties(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Medium用のプロパティを構築

        Args:
            article_data: 記事データ

        Returns:
            Notionプロパティ辞書
        """
        properties: Dict[str, Any] = {}

        # Title（英語タイトル）
        if "title" in article_data:
            properties["Title"] = {
                "title": [{"text": {"content": article_data["title"]}}]
            }

        # Japanese Title（日本語タイトル）
        if "japanese_title" in article_data:
            properties["Japanese Title"] = {
                "rich_text": [{"text": {"content": article_data["japanese_title"]}}]
            }

        # URL
        if "url" in article_data:
            normalized_url = self._normalize_url_by_source(article_data["url"])
            properties["URL"] = {"url": normalized_url}
            logger.info(f"  Saving normalized URL: {normalized_url}")

        # Author（著者名）
        if "author" in article_data:
            properties["Author"] = {
                "rich_text": [{"text": {"content": article_data["author"]}}]
            }

        # Date（記事の日付）
        if "date" in article_data:
            properties["Date"] = {"date": {"start": article_data["date"]}}

        # Summary（日本語要約）
        if "japanese_summary" in article_data:
            properties["Summary"] = {
                "rich_text": [
                    {"text": {"content": article_data["japanese_summary"][:2000]}}
                ]
            }
        elif "summary" in article_data:
            properties["Summary"] = {
                "rich_text": [{"text": {"content": article_data["summary"][:2000]}}]
            }

        # Claps（拍手数）
        if "claps" in article_data and article_data["claps"]:
            properties["Claps"] = {"number": article_data["claps"]}

        return properties

    def _build_google_alerts_properties(
        self, article_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Google Alerts用のプロパティを構築

        Args:
            article_data: 記事データ

        Returns:
            Notionプロパティ辞書（英語プロパティ名）
        """
        properties: Dict[str, Any] = {}

        # タイトル (日本語タイトルをメインのTitleに)
        if "japanese_title" in article_data:
            properties["Title"] = {
                "title": [{"text": {"content": article_data["japanese_title"]}}]
            }
        elif "title" in article_data:
            # 日本語タイトルがない場合は英語タイトルを使用
            properties["Title"] = {
                "title": [{"text": {"content": article_data["title"]}}]
            }

        # 元の英語タイトルをOriginal Titleに
        if "title" in article_data:
            properties["Original Title"] = {
                "rich_text": [{"text": {"content": article_data["title"]}}]
            }

        # URL
        if "url" in article_data:
            normalized_url = self._normalize_url_by_source(article_data["url"])
            properties["URL"] = {"url": normalized_url}
            logger.info(f"  Saving normalized URL: {normalized_url}")

        # ソース情報をSourceプロパティに
        if "source" in article_data:
            properties["Source"] = {
                "rich_text": [{"text": {"content": article_data["source"]}}]
            }
        elif "author" in article_data:  # authorがある場合はそれを使用
            properties["Source"] = {
                "rich_text": [{"text": {"content": article_data["author"]}}]
            }

        # 要約
        if "japanese_summary" in article_data:
            properties["Summary"] = {
                "rich_text": [{"text": {"content": article_data["japanese_summary"]}}]
            }
        elif "summary" in article_data:
            properties["Summary"] = {
                "rich_text": [{"text": {"content": article_data["summary"]}}]
            }

        # スニペット
        if "snippet" in article_data:
            properties["Snippet"] = {
                "rich_text": [{"text": {"content": article_data["snippet"]}}]
            }

        # Date（メール受信日をdate型プロパティとして明示的に設定）
        if "date" in article_data:
            properties["Date"] = {"date": {"start": article_data["date"]}}

        # タグ
        if "tags" in article_data and isinstance(article_data["tags"], list):
            properties["Tags"] = {
                "multi_select": [{"name": tag} for tag in article_data["tags"]]
            }

        return properties

    async def batch_save_articles(
        self, database_id: str, articles: List[Dict[str, Any]], max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        複数の記事を並列でNotionに保存

        Args:
            database_id: NotionデータベースID
            articles: 記事データのリスト
            max_concurrent: 最大同時実行数

        Returns:
            処理結果の統計と詳細（成功数、スキップ数、失敗数、および各記事のリスト）
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        lock = asyncio.Lock()
        processed_urls: set[str] = set()
        stats = {"success": 0, "skipped": 0, "failed": 0}
        results: Dict[str, List[str]] = {"success": [], "skipped": [], "failed": []}

        # バッチ内URL重複排除（事前フィルタ）
        seen_urls: set[str] = set()
        unique_articles = []
        for article in articles:
            url = self._normalize_url_by_source(article.get("url", ""))
            if url and url in seen_urls:
                title = article.get("title", "Unknown")
                display_title = f"{title[:50]}..." if len(title) > 50 else title
                logger.info(f"  バッチ内重複のためスキップ: {display_title}")
                stats["skipped"] += 1
                results["skipped"].append(display_title)
            else:
                if url:
                    seen_urls.add(url)
                unique_articles.append(article)

        async def save_with_semaphore(article):
            async with semaphore:
                title = article.get("title", "Unknown")
                display_title = f"{title[:50]}..." if len(title) > 50 else title
                url = self._normalize_url_by_source(article.get("url", ""))

                # ロック付きで処理済みURLチェック（並列タスク間の重複防止）
                if url:
                    async with lock:
                        if url in processed_urls:
                            logger.info(
                                f"  並列処理内で重複のためスキップ: {display_title}"
                            )
                            stats["skipped"] += 1
                            results["skipped"].append(display_title)
                            return
                        processed_urls.add(url)

                try:
                    result = await self.save_article(database_id, article)
                    if result:
                        stats["success"] += 1
                        results["success"].append(display_title)
                    else:
                        stats["skipped"] += 1
                        results["skipped"].append(display_title)
                except Exception as e:
                    logger.error(f"記事の保存エラー '{display_title}': {e}")
                    stats["failed"] += 1
                    results["failed"].append(display_title)

        # 全記事を並列処理（重複排除済み）
        tasks = [save_with_semaphore(article) for article in unique_articles]
        await asyncio.gather(*tasks)

        # 詳細な結果ログ
        logger.info(
            f"バッチ保存完了: 成功={stats['success']}, スキップ={stats['skipped']}, 失敗={stats['failed']}"
        )

        if results["success"]:
            logger.info("【成功した論文】")
            for title in results["success"]:
                logger.info(f"  ✓ {title}")

        if results["skipped"]:
            logger.info("【スキップした論文（既存）】")
            for title in results["skipped"]:
                logger.info(f"  - {title}")

        if results["failed"]:
            logger.info("【失敗した論文】")
            for title in results["failed"]:
                logger.info(f"  ✗ {title}")

        return {"stats": stats, "results": results}

    async def update_page_properties(
        self, page_id: str, properties: Dict[str, Any]
    ) -> bool:
        """
        既存ページのプロパティを更新

        Args:
            page_id: NotionページID
            properties: 更新するプロパティ辞書

        Returns:
            更新成功の場合True
        """
        try:
            await self._retry_api_call(
                lambda: self.client.pages.update(
                    page_id=page_id, properties=properties
                ),
                description=f"update_page_properties({page_id[:8]})",
            )
            logger.debug(f"Page properties updated: {page_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update page properties ({page_id}): {e}")
            return False

    async def find_page_by_url(self, database_id: str, url: str) -> Optional[PageInfo]:
        """
        URLでNotionデータベースを検索し、既存ページの情報を返す

        完全一致で見つからない場合、Medium記事はスラッグ（パス末尾）で
        contains検索にフォールバックする（カスタムドメイン対応）

        Args:
            database_id: NotionデータベースID
            url: 検索するURL

        Returns:
            PageInfo(page_id, is_translated)（見つからない場合はNone）
        """
        try:
            normalized_url = self._normalize_url_by_source(url)

            logger.info(f"Finding page by URL: {normalized_url}")

            result = cast(
                Dict[str, Any],
                await self._retry_api_call(
                    lambda: self.client.databases.query(
                        database_id=database_id,
                        filter={"property": "URL", "url": {"equals": normalized_url}},
                    ),
                    description=f"find_page_by_url({normalized_url[:50]})",
                ),
            )

            query_results = result.get("results", [])
            if query_results:
                return self._extract_page_info(query_results[0])

            # Medium記事の場合、スラッグ（パス末尾）でcontains検索にフォールバック
            # カスタムドメイン（ehandbook.comなど）とmedium.comのURL不一致に対応
            if self.source_type == "medium":
                slug = normalized_url.rsplit("/", 1)[-1]
                if slug:
                    logger.info(f"Exact match not found, trying slug search: {slug}")
                    result = cast(
                        Dict[str, Any],
                        await self._retry_api_call(
                            lambda: self.client.databases.query(
                                database_id=database_id,
                                filter={
                                    "property": "URL",
                                    "url": {"contains": slug},
                                },
                            ),
                            description=f"find_page_by_url_slug({slug[:50]})",
                        ),
                    )
                    query_results = result.get("results", [])
                    if query_results:
                        logger.info(f"Page found via slug match: {slug}")
                        return self._extract_page_info(query_results[0])

            logger.info(f"Page not found for URL: {url}")
            return None

        except Exception as e:
            logger.error(f"Error finding page by URL: {e}")
            return None

    def _extract_page_info(self, page: Dict[str, Any]) -> PageInfo:
        """NotionページデータからPageInfoを抽出する"""
        page_id = page.get("id", "")
        is_translated = (
            page.get("properties", {}).get("Translated", {}).get("checkbox", False)
        )
        logger.info(f"Page found: {page_id} (translated: {is_translated})")
        return PageInfo(page_id=page_id, is_translated=is_translated)

    async def append_blocks(self, page_id: str, blocks: List[Dict[str, Any]]) -> bool:
        """
        既存ページにブロックを追記する

        Args:
            page_id: NotionページID
            blocks: 追記するNotionブロックのリスト

        Returns:
            追記成功の場合True
        """
        if not blocks:
            logger.warning("No blocks to append")
            return False

        try:
            return await self._batch_append_blocks(page_id, blocks)
        except Exception as e:
            logger.error(f"Error appending blocks to page {page_id}: {e}")
            return False

    async def _batch_append_blocks(
        self, page_id: str, blocks: List[Dict[str, Any]], batch_size: int = 100
    ) -> bool:
        """
        ブロックをバッチ単位で追記する（Notion APIの100ブロック制限対応）

        Args:
            page_id: NotionページID
            blocks: 追記するブロックのリスト
            batch_size: バッチサイズ（デフォルト: 100）

        Returns:
            全バッチの追記成功の場合True
        """
        total_batches = (len(blocks) + batch_size - 1) // batch_size
        logger.info(
            f"Appending {len(blocks)} blocks in {total_batches} batch(es) "
            f"to page {page_id[:8]}..."
        )

        for i in range(0, len(blocks), batch_size):
            batch = blocks[i : i + batch_size]
            batch_num = i // batch_size + 1

            logger.info(f"  Batch {batch_num}/{total_batches}: {len(batch)} blocks")

            try:
                await self._retry_api_call(
                    lambda b=batch: self.client.blocks.children.append(  # type: ignore[misc]
                        block_id=page_id, children=b
                    ),
                    description=f"append_blocks(batch {batch_num}/{total_batches})",
                )
            except Exception as e:
                logger.error(f"  Batch {batch_num} failed after retries: {e}")
                return False

        logger.info(f"All {len(blocks)} blocks appended successfully")
        return True
