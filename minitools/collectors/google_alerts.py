"""
Google Alerts collector module.
"""

import os
import pickle
import base64
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import pytz
from bs4 import BeautifulSoup

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# Gmail API スコープ
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass
class Alert:
    """アラート情報を格納するデータクラス"""

    title: str
    url: str
    source: str
    snippet: str = ""
    japanese_title: str = ""
    japanese_summary: str = ""
    date_processed: str = ""
    article_content: str = ""
    email_date: str = ""
    tags: Optional[List[str]] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class GoogleAlertsCollector:
    """Google Alertsメールを収集するクラス"""

    def __init__(self, credentials_path: Optional[str] = None):
        self.gmail_service = None
        self.credentials_path = credentials_path or os.getenv(
            "GMAIL_CREDENTIALS_PATH", "credentials.json"
        )
        self._authenticate_gmail()

    def _authenticate_gmail(self):
        """Gmail APIの認証"""
        try:
            creds = None
            token_path = "token.pickle"

            if os.path.exists(token_path):
                with open(token_path, "rb") as token:
                    creds = pickle.load(token)

            if not creds or not creds.valid:
                refreshed = False
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        refreshed = True
                    except RefreshError as e:
                        logger.warning(
                            f"リフレッシュトークンが失効しました ({e})。再認証を行います。"
                        )
                        try:
                            os.remove(token_path)
                        except FileNotFoundError:
                            pass
                        creds = None

                if not refreshed:
                    if not os.path.exists(self.credentials_path):
                        raise FileNotFoundError(
                            f"認証ファイル {self.credentials_path} が見つかりません"
                        )

                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                with open(token_path, "wb") as token:
                    pickle.dump(creds, token)

            self.gmail_service = build("gmail", "v1", credentials=creds)
            logger.info("Gmail API authenticated successfully")

        except Exception as e:
            logger.error(f"Gmail認証エラー: {e}")
            raise

    def get_alerts_emails(
        self, hours_back: int = 6, date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Google Alertsメールを取得

        Args:
            hours_back: 何時間前までのメールを取得するか（dateが指定されていない場合）
            date: 特定の日付のメールを取得（指定された場合）

        Returns:
            メールメッセージのリスト
        """
        jst = pytz.timezone("Asia/Tokyo")

        if date:
            # 特定の日付の全メールを取得
            if date.tzinfo is None:
                date = jst.localize(date)
            start_time = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(days=1)
            logger.info(f"検索期間 (JST): {start_time} から {end_time} (指定日全日)")
        else:
            # 過去数時間のメールを取得
            end_time = datetime.now(jst)
            start_time = end_time - timedelta(hours=hours_back)
            logger.info(
                f"検索期間 (JST): {start_time} から {end_time} (過去{hours_back}時間)"
            )

        # タイムスタンプに変換
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp())
        logger.info(f"タイムスタンプ: {start_timestamp} から {end_timestamp}")

        query = f"from:googlealerts-noreply@google.com after:{start_timestamp} before:{end_timestamp}"
        logger.info(f"Gmail検索クエリ: {query}")

        try:
            if self.gmail_service is None:
                logger.error("Gmail service is not initialized")
                return []

            service = self.gmail_service
            response = service.users().messages().list(userId="me", q=query).execute()

            messages = response.get("messages", [])

            logger.info(f"Gmail検索結果: {len(messages)}件のメッセージが見つかりました")

            if not messages:
                logger.warning("Google Alertsメールが見つかりません")
                return []

            # メッセージの詳細を取得
            detailed_messages = []
            logger.info(f"{len(messages)}件のメッセージの詳細を取得中...")
            for i, msg in enumerate(messages, 1):
                try:
                    logger.info(
                        f"  -> メッセージ取得中 ({i}/{len(messages)}): {msg['id']}"
                    )
                    detail = (
                        service.users()
                        .messages()
                        .get(userId="me", id=msg["id"])
                        .execute()
                    )

                    # メール件名を取得してログ出力
                    headers = detail["payload"].get("headers", [])
                    subject = next(
                        (h["value"] for h in headers if h["name"] == "Subject"),
                        "No Subject",
                    )
                    logger.info(f"    -> 件名: {subject}")

                    # メール配信日時を取得してログ出力
                    if "internalDate" in detail:
                        jst = pytz.timezone("Asia/Tokyo")
                        email_timestamp = int(detail["internalDate"]) / 1000
                        email_date = datetime.fromtimestamp(email_timestamp, tz=jst)
                        logger.info(f"    -> メール配信日時: {email_date}")

                    detailed_messages.append(detail)
                except HttpError as e:
                    logger.error(f"メッセージ取得エラー ({msg['id']}): {e}")

            logger.info(
                f"{len(detailed_messages)}件のGoogle Alertsメールを取得しました"
            )
            return detailed_messages

        except HttpError as error:
            logger.error(f"Gmail APIエラー: {error}")
            return []

    def parse_alerts(self, message: Dict) -> List[Alert]:
        """
        メールからアラート情報を抽出

        Args:
            message: Gmail APIのメッセージオブジェクト

        Returns:
            アラート情報のリスト
        """
        # メール配信日時を取得
        email_date_str = ""
        if "internalDate" in message:
            jst = pytz.timezone("Asia/Tokyo")
            email_timestamp = int(message["internalDate"]) / 1000
            email_date = datetime.fromtimestamp(email_timestamp, tz=jst)
            email_date_str = email_date.strftime("%Y-%m-%d")
            logger.debug(f"メール配信日時: {email_date} -> {email_date_str}")

        # メール本文を取得
        body = self._extract_body(message)
        if not body:
            return []

        soup = BeautifulSoup(body, "html.parser")
        alerts = []

        # Google Alertsのリンクパターンを探す
        alert_links = soup.find_all(
            "a", href=re.compile(r"https://www\.google\.com/url\?")
        )
        logger.info(f"Google Alertsリンクを {len(alert_links)}個発見")

        if not alert_links:
            logger.warning("Google Alertsリンクが見つかりません")
            return []

        seen_urls = set()

        for link in alert_links:
            href = link.get("href", "")
            if not href:
                continue

            # Google URLから実際のURLを抽出
            try:
                import urllib.parse

                href_str = str(href)  # 型を明示的にstrに変換
                parsed_url = urllib.parse.urlparse(href_str)
                query_params = urllib.parse.parse_qs(parsed_url.query)

                actual_url = None
                # 複数のパラメータパターンを試す
                for param in ["url", "q"]:
                    if param in query_params:
                        actual_url = query_params[param][0]
                        break

                if actual_url:
                    # 重複チェック
                    if actual_url in seen_urls:
                        continue
                    seen_urls.add(actual_url)

                    # タイトルを取得
                    title = link.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue

                    # ソースを抽出（URLから）
                    source = "Unknown"
                    try:
                        source = urllib.parse.urlparse(actual_url).netloc
                    except Exception:
                        pass

                    # スニペットを抽出（リンクの後にある説明文）
                    snippet = ""
                    parent = link.parent
                    if parent:
                        # 親要素のテキストからスニペットを抽出
                        parent_text = parent.get_text(strip=True)
                        # タイトルより後の部分をスニペットとして使用
                        if title in parent_text:
                            snippet_parts = parent_text.split(title, 1)
                            if len(snippet_parts) > 1:
                                snippet = snippet_parts[1].strip()[:200]

                    alert = Alert(
                        title=title,
                        url=actual_url,
                        source=source,
                        snippet=snippet,
                        date_processed=datetime.now().isoformat(),
                        email_date=email_date_str,
                    )
                    alerts.append(alert)

            except Exception as e:
                logger.error(f"URL解析エラー: {e}")
                continue

        logger.info(f"メールから{len(alerts)}件のアラートを抽出")
        return alerts

    def _extract_body(self, message: Dict) -> str:
        """メールメッセージから本文を抽出"""
        payload = message.get("payload", {})
        return self._extract_body_from_payload(payload)

    def _extract_body_from_payload(self, payload: Dict) -> str:
        """ペイロードからメール本文を抽出（再帰的）"""
        body = ""

        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/html":
                    data = part["body"].get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="ignore"
                        )
                        break
                elif "parts" in part:
                    body = self._extract_body_from_payload(part)
                    if body:
                        break
        elif payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8", errors="ignore"
            )

        return body

    async def fetch_article_content(self, url: str, retry_count: int = 3) -> str:
        """
        URLから記事の本文を取得

        Args:
            url: 記事のURL
            retry_count: リトライ回数

        Returns:
            記事の本文（最大3000文字）
        """
        import asyncio
        import aiohttp
        import random

        # 複数のUser-Agentを用意
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ]

        for attempt in range(retry_count):
            try:
                # ランダムなUser-Agentを選択
                user_agent = random.choice(user_agents)

                # ヘッダーを設定（Brotliエラーの場合はAccept-Encodingを調整）
                headers = {
                    "User-Agent": user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Cache-Control": "max-age=0",
                }

                # SSL検証の設定（リトライ時は検証を無効化する場合がある）
                ssl_verify = True
                if attempt > 0:
                    # 2回目以降のリトライではSSL検証を緩和
                    ssl_verify = False
                    logger.warning(f"SSL検証を無効化してリトライ: {url}")

                # コネクタの設定
                connector = aiohttp.TCPConnector(ssl=ssl_verify)

                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(
                        url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                        allow_redirects=True,
                    ) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, "html.parser")

                            # 記事本文を抽出する複数のパターンを試す
                            content_selectors = [
                                "article",
                                ".post-content",
                                ".entry-content",
                                ".content",
                                ".article-body",
                                ".story-body",
                                ".article-content",
                                "main",
                                ".main-content",
                                '[role="main"]',
                                ".article-text",
                                ".post-body",
                                ".entry-content-wrap",
                                ".article-wrapper",
                            ]

                            article_text = ""
                            for selector in content_selectors:
                                content_element = soup.select_one(selector)
                                if content_element:
                                    # スクリプトとスタイルタグを除去
                                    for script in content_element(
                                        [
                                            "script",
                                            "style",
                                            "nav",
                                            "header",
                                            "footer",
                                            "aside",
                                        ]
                                    ):
                                        script.decompose()

                                    article_text = content_element.get_text(
                                        separator=" ", strip=True
                                    )
                                    if (
                                        len(article_text) > 100
                                    ):  # 有意なコンテンツがある場合
                                        break

                            # 記事が見つからない場合は全体のテキストを取得
                            if not article_text or len(article_text) < 100:
                                # スクリプトとスタイルタグを除去
                                for script in soup(
                                    [
                                        "script",
                                        "style",
                                        "nav",
                                        "header",
                                        "footer",
                                        "aside",
                                    ]
                                ):
                                    script.decompose()
                                article_text = soup.get_text(separator=" ", strip=True)

                            # 長すぎる場合は最初の3000文字に制限
                            return article_text[:3000] if article_text else ""

                        elif response.status in [403, 422, 429]:
                            # アクセス制限系のエラーの場合
                            if attempt < retry_count - 1:
                                wait_time = (attempt + 1) * random.uniform(2, 5)
                                logger.warning(
                                    f"記事取得エラー ({url}): {response.status}. {wait_time:.1f}秒後にリトライ..."
                                )
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                logger.error(
                                    f"記事取得エラー ({url}): {response.status}. リトライ回数を超えました"
                                )
                                return ""
                        else:
                            logger.error(
                                f"記事取得エラー ({url}): HTTPステータス {response.status}"
                            )
                            return ""

            except aiohttp.ContentTypeError as e:
                # Brotliデコードエラーの場合
                if "brotli" in str(e).lower() and attempt < retry_count - 1:
                    # Accept-Encodingからbrを除外してリトライ
                    headers["Accept-Encoding"] = "gzip, deflate"
                    wait_time = 2
                    logger.warning(
                        f"Brotliデコードエラー ({url}). Accept-Encodingを変更して{wait_time}秒後にリトライ..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"コンテンツデコードエラー ({url}): {e}")
                    return ""

            except asyncio.TimeoutError:
                if attempt < retry_count - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(
                        f"記事取得タイムアウト ({url}). {wait_time}秒後にリトライ..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"記事取得タイムアウト ({url}). リトライ回数を超えました"
                    )
                    return ""

            except Exception as e:
                if attempt < retry_count - 1:
                    wait_time = (attempt + 1) * 1.5
                    logger.warning(
                        f"記事取得エラー ({url}): {e}. {wait_time}秒後にリトライ..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"記事取得エラー ({url}): {e}. リトライ回数を超えました"
                    )
                    return ""

        return ""

    async def fetch_articles_for_alerts(self, alerts: List[Alert]) -> None:
        """
        複数のアラートの記事本文を並列で取得

        Args:
            alerts: アラートのリスト
        """
        import asyncio

        logger.info(f"記事コンテンツ並列取得開始: {len(alerts)}件のアラートを処理中...")

        # 各アラートの記事取得タスクを作成
        tasks = []
        for i, alert in enumerate(alerts, 1):
            logger.info(f"  -> 記事取得中 ({i}/{len(alerts)}): {alert.url[:50]}...")
            task = self.fetch_article_content(alert.url)
            tasks.append(task)

        # 並列で実行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 結果をアラートに設定
        success_count = 0
        for i, (alert, result) in enumerate(zip(alerts, results), 1):
            if isinstance(result, BaseException):
                logger.error(
                    f"  -> 記事取得エラー ({i}/{len(alerts)}): {alert.url}: {result}"
                )
                alert.article_content = ""
            else:
                alert.article_content = result or ""
                if alert.article_content:
                    logger.info(
                        f"  -> 記事取得完了 ({i}/{len(alerts)}): {alert.url[:50]}..."
                    )
                    success_count += 1
                else:
                    logger.warning(
                        f"  -> 記事取得失敗（空のコンテンツ） ({i}/{len(alerts)}): {alert.url[:50]}..."
                    )

        logger.info(f"記事コンテンツ取得完了: {success_count}/{len(alerts)}件成功")
