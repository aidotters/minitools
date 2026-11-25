"""
Notion reader module for fetching content from Notion databases.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from notion_client import Client

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class NotionReadError(Exception):
    """Notion読み取りエラー"""

    pass


class NotionReader:
    """Notionデータベースから記事を読み取るクラス（読み取り専用）"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Notion APIキー（省略時は環境変数から取得）

        Raises:
            ValueError: APIキーが設定されていない場合
        """
        self.api_key = api_key or os.getenv("NOTION_API_KEY")
        if not self.api_key:
            raise ValueError("NOTION_API_KEY is required")

        self.client = Client(auth=self.api_key)
        logger.info("NotionReader initialized")

    async def get_articles_by_date_range(
        self,
        database_id: str,
        start_date: str,
        end_date: str,
        date_property: str = "Date",
    ) -> List[Dict[str, Any]]:
        """
        指定期間の記事を全件取得

        Args:
            database_id: NotionデータベースID
            start_date: 開始日（YYYY-MM-DD形式）
            end_date: 終了日（YYYY-MM-DD形式）
            date_property: 日付プロパティ名（デフォルト: "Date"）

        Returns:
            記事データの辞書リスト

        Raises:
            NotionReadError: 読み取りに失敗した場合
        """
        logger.info(
            f"Fetching articles from {start_date} to {end_date} "
            f"(property: {date_property})"
        )

        # 日付フィルタを構築
        filter_query = {
            "and": [
                {
                    "property": date_property,
                    "date": {"on_or_after": start_date},
                },
                {
                    "property": date_property,
                    "date": {"on_or_before": end_date},
                },
            ]
        }

        all_results = []
        has_more = True
        next_cursor = None

        try:
            while has_more:
                loop = asyncio.get_event_loop()

                query_params: Dict[str, Any] = {
                    "database_id": database_id,
                    "filter": filter_query,
                    "page_size": 100,
                }
                if next_cursor:
                    query_params["start_cursor"] = next_cursor

                def query_db(params: Dict[str, Any] = query_params) -> Dict[str, Any]:
                    result = self.client.databases.query(**params)
                    return dict(result) if result else {}  # type: ignore[arg-type]

                response = await loop.run_in_executor(None, query_db)

                results = response.get("results", [])
                all_results.extend(results)

                has_more = response.get("has_more", False)
                next_cursor = response.get("next_cursor")

                logger.debug(
                    f"Fetched {len(results)} articles (total: {len(all_results)})"
                )

            logger.info(f"Total articles fetched: {len(all_results)}")

            # Notionページを記事辞書に変換
            articles = [self._page_to_article(page) for page in all_results]
            return articles

        except Exception as e:
            logger.error(f"Failed to fetch articles from Notion: {e}")
            raise NotionReadError(f"Notion API error: {e}") from e

    async def get_latest_article_date(
        self,
        database_id: str,
        date_property: str = "Date",
    ) -> Optional[str]:
        """
        データベース内で最も新しい記事の日付を返す

        Args:
            database_id: NotionデータベースID
            date_property: 日付プロパティ名（デフォルト: "Date"）

        Returns:
            日付（YYYY-MM-DD形式）。記事が無ければ None

        Raises:
            NotionReadError: 読み取りに失敗した場合
        """
        query_params: Dict[str, Any] = {
            "database_id": database_id,
            "filter": {"property": date_property, "date": {"is_not_empty": True}},
            "sorts": [{"property": date_property, "direction": "descending"}],
            "page_size": 1,
        }

        def query_db() -> Dict[str, Any]:
            result = self.client.databases.query(**query_params)
            return dict(result) if result else {}  # type: ignore[arg-type]

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, query_db)
        except Exception as e:
            logger.error(f"Failed to fetch latest article date from Notion: {e}")
            raise NotionReadError(f"Notion API error: {e}") from e

        results = response.get("results", [])
        if not results:
            return None
        prop = results[0].get("properties", {}).get(date_property, {})
        start = (prop.get("date") or {}).get("start")
        return start[:10] if start else None

    def _page_to_article(self, page: Dict[str, Any]) -> Dict[str, Any]:
        """
        Notionページを記事辞書に変換

        Args:
            page: Notionページオブジェクト

        Returns:
            記事データの辞書
        """
        properties = page.get("properties", {})
        article = {
            "id": page.get("id"),
            "created_time": page.get("created_time"),
            "last_edited_time": page.get("last_edited_time"),
        }

        # 各プロパティを抽出
        for prop_name, prop_value in properties.items():
            extracted = self._extract_property_value(prop_value)
            if extracted is not None:
                # プロパティ名をスネークケースに変換
                key = prop_name.lower().replace(" ", "_")
                article[key] = extracted

        return article

    def _extract_property_value(self, prop: Dict[str, Any]) -> Any:
        """
        Notionプロパティから値を抽出

        Args:
            prop: Notionプロパティオブジェクト

        Returns:
            プロパティの値
        """
        prop_type = prop.get("type")

        if prop_type == "title":
            title_list = prop.get("title", [])
            if title_list:
                return "".join(t.get("plain_text", "") for t in title_list)
            return ""

        elif prop_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list:
                return "".join(t.get("plain_text", "") for t in text_list)
            return ""

        elif prop_type == "url":
            return prop.get("url")

        elif prop_type == "date":
            date_obj = prop.get("date")
            if date_obj:
                return date_obj.get("start")
            return None

        elif prop_type == "multi_select":
            items = prop.get("multi_select", [])
            return [item.get("name") for item in items]

        elif prop_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None

        elif prop_type == "number":
            return prop.get("number")

        elif prop_type == "checkbox":
            return prop.get("checkbox")

        elif prop_type == "created_time":
            return prop.get("created_time")

        elif prop_type == "last_edited_time":
            return prop.get("last_edited_time")

        else:
            logger.debug(f"Unsupported property type: {prop_type}")
            return None

    async def get_arxiv_papers_by_date_range(
        self,
        start_date: str,
        end_date: str,
        database_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        ArXiv論文DBから指定期間の論文を全件取得

        Args:
            start_date: 開始日（YYYY-MM-DD形式）
            end_date: 終了日（YYYY-MM-DD形式）
            database_id: NotionデータベースID（省略時は環境変数から取得）

        Returns:
            論文データの辞書リスト（空の場合は空リスト）

        Raises:
            NotionReadError: 読み取りに失敗した場合
        """
        # データベースIDを取得
        db_id = database_id or os.getenv("NOTION_ARXIV_DATABASE_ID")
        if not db_id:
            raise ValueError(
                "database_id is required or NOTION_ARXIV_DATABASE_ID must be set"
            )

        logger.info(f"Fetching ArXiv papers from {start_date} to {end_date}")

        # 既存のメソッドを「公開日」プロパティで呼び出し
        papers = await self.get_articles_by_date_range(
            database_id=db_id,
            start_date=start_date,
            end_date=end_date,
            date_property="公開日",
        )

        logger.info(f"Fetched {len(papers)} ArXiv papers")
        return papers

    async def get_database_info(self, database_id: str) -> Dict[str, Any]:
        """
        データベースの情報を取得

        Args:
            database_id: NotionデータベースID

        Returns:
            データベース情報の辞書
        """
        try:
            loop = asyncio.get_event_loop()

            def retrieve_db() -> Dict[str, Any]:
                result = self.client.databases.retrieve(database_id=database_id)
                return dict(result) if result else {}  # type: ignore[arg-type]

            response = await loop.run_in_executor(None, retrieve_db)
            return response
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            raise NotionReadError(f"Notion API error: {e}") from e
