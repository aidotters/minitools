"""
YouTube email collector module.

特定送信元(from)の Gmail を取得し、本文 HTML から YouTube 動画 URL を
抽出・正規化・重複除去するコレクター。Gmail 認証・本文抽出は
GoogleAlertsCollector と同じパターンを流用し、送信元をパラメータ化している。
"""

import os
import re
import base64
import pickle
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytz
from bs4 import BeautifulSoup

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# Gmail API スコープ（GoogleAlertsCollector と共有）
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# YouTube 動画 ID（11文字の英数・ハイフン・アンダースコア）
_VIDEO_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")

# 正規化時に除去するトラッキング系クエリパラメータ
_TRACKING_PARAMS = {
    "si",
    "feature",
    "t",
    "ab_channel",
    "pp",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
}


@dataclass
class VideoRef:
    """メールから抽出した YouTube 動画への参照"""

    url: str  # 正規化済み URL（https://www.youtube.com/watch?v=ID）
    video_id: str
    email_date: str = ""
    source_subject: str = ""


def extract_video_id(url: str) -> Optional[str]:
    """
    YouTube URL から動画 ID を抽出する。

    対応パターン:
    - https://www.youtube.com/watch?v=ID
    - https://youtu.be/ID
    - https://www.youtube.com/shorts/ID
    - https://www.youtube.com/embed/ID
    - https://www.youtube.com/live/ID

    Args:
        url: 任意の URL 文字列

    Returns:
        11文字の動画 ID。YouTube 動画 URL でなければ None。
    """
    if not url:
        return None

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None

    host = (parsed.netloc or "").lower()
    # ポート除去
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]

    candidate: Optional[str] = None

    if host == "youtu.be":
        # パスの先頭セグメントが動画 ID
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        path = parsed.path
        if path == "/watch":
            qs = urllib.parse.parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                candidate = qs["v"][0]
        else:
            for prefix in ("/shorts/", "/embed/", "/live/", "/v/"):
                if path.startswith(prefix):
                    candidate = path[len(prefix) :].split("/")[0]
                    break

    if candidate and _VIDEO_ID_RE.match(candidate):
        return candidate
    return None


def normalize_youtube_url(url: str) -> Optional[str]:
    """
    YouTube URL を正規化する（トラッキング除去・watch 形式へ統一）。

    Args:
        url: 任意の URL

    Returns:
        `https://www.youtube.com/watch?v=ID` 形式の正規化 URL。
        YouTube 動画 URL でなければ None。
    """
    video_id = extract_video_id(url)
    if not video_id:
        return None
    return f"https://www.youtube.com/watch?v={video_id}"


def _decode_redirect_urls(url: str) -> List[str]:
    """
    リダイレクト URL に base64 で内包された実 URL を取り出す。

    WordPress.com の購読 digest メールは、実リンクを
    `?action=user_content_redirect&...&encoded_url=<base64>` の
    `encoded_url` パラメータに base64 エンコードして埋め込む。
    その値をデコードして候補 URL として返す（WordPress 限定スコープ。
    汎用リダイレクト展開はしない）。

    Args:
        url: 任意の URL

    Returns:
        デコードで得られた URL のリスト。`encoded_url` が無い、または
        デコード不能な場合は空リスト。
    """
    if not url:
        return []

    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return []

    qs = urllib.parse.parse_qs(parsed.query)
    encoded_values = qs.get("encoded_url")
    if not encoded_values:
        return []

    decoded: List[str] = []
    for value in encoded_values:
        # padding 補正（base64 は 4 文字境界が必要）
        padded = value + "=" * (-len(value) % 4)
        for decoder in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                # binascii.Error は ValueError のサブクラス
                text = decoder(padded).decode("utf-8", errors="ignore")
            except ValueError:
                continue
            if text:
                decoded.append(text)
            break

    return decoded


def extract_youtube_urls(html: str) -> List[str]:
    """
    HTML 本文から YouTube 動画 URL を全て抽出し、正規化・重複除去して返す。

    `<a href>` のリンクに加え、本文テキスト中の生 URL、および
    WordPress リダイレクトの `encoded_url`（base64）に内包された URL も拾う。

    Args:
        html: メール本文の HTML

    Returns:
        正規化済み URL のリスト（動画 ID で重複除去、出現順を保持）
    """
    if not html:
        return []

    candidates: List[str] = []

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        candidates.append(str(a["href"]))

    # テキスト中の生 URL（href に現れないケースの保険）
    text = soup.get_text(separator=" ")
    candidates.extend(re.findall(r"https?://[^\s\"'<>]+", text))

    # リダイレクト URL に内包された実 URL を展開（WordPress encoded_url 等）
    for raw in list(candidates):
        candidates.extend(_decode_redirect_urls(raw))

    normalized: List[str] = []
    seen_ids = set()
    for raw in candidates:
        norm = normalize_youtube_url(raw)
        if not norm:
            continue
        vid = extract_video_id(norm)
        if vid in seen_ids:
            continue
        seen_ids.add(vid)
        normalized.append(norm)

    return normalized


class YouTubeEmailCollector:
    """特定送信元のメールから YouTube 動画 URL を収集するクラス"""

    def __init__(self, sender: str, credentials_path: Optional[str] = None):
        """
        Args:
            sender: 対象とするメールの送信元（Gmail の from: クエリに使用）
            credentials_path: 認証情報ファイル。未指定時は settings/環境変数から取得。
        """
        if not sender:
            raise ValueError("sender (メール送信元) は必須です")
        self.sender = sender

        config = get_config()
        self.credentials_path = (
            credentials_path
            or os.getenv("GMAIL_CREDENTIALS_PATH")
            or config.get("gmail.credentials_file", "credentials.json")
        )
        self.token_path = config.get("gmail.token_file", "token.pickle")
        self.gmail_service = None
        self._authenticate_gmail()

    def _authenticate_gmail(self) -> None:
        """Gmail API の認証（token.pickle を GoogleAlertsCollector と共有）"""
        try:
            creds = None
            if os.path.exists(self.token_path):
                with open(self.token_path, "rb") as token:
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
                            os.remove(self.token_path)
                        except FileNotFoundError:
                            pass
                        creds = None

                if not refreshed:
                    if not os.path.exists(self.credentials_path):
                        raise FileNotFoundError(
                            f"認証ファイル {self.credentials_path} が見つかりません"
                        )
                    # 注意: run_local_server はブラウザ認証フローを起動する。
                    # launchd など headless 環境では永久ハングするため、
                    # 初回認証は必ず対話的に実行して token.pickle を生成しておくこと。
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                with open(self.token_path, "wb") as token:
                    pickle.dump(creds, token)

            self.gmail_service = build("gmail", "v1", credentials=creds)
            logger.info("Gmail API authenticated successfully (youtube_email)")

        except Exception as e:
            logger.error(f"Gmail認証エラー: {e}")
            raise

    def _build_query(self, hours_back: int, date: Optional[datetime]) -> str:
        """Gmail 検索クエリを構築（JST 基準、from: 指定）"""
        jst = pytz.timezone("Asia/Tokyo")
        if date:
            if date.tzinfo is None:
                date = jst.localize(date)
            start_time = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(days=1)
            logger.info(f"検索期間 (JST): {start_time} から {end_time} (指定日全日)")
        else:
            end_time = datetime.now(jst)
            start_time = end_time - timedelta(hours=hours_back)
            logger.info(
                f"検索期間 (JST): {start_time} から {end_time} (過去{hours_back}時間)"
            )
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())
        return f"from:{self.sender} after:{start_ts} before:{end_ts}"

    def collect(
        self, hours_back: int = 24, date: Optional[datetime] = None
    ) -> List[VideoRef]:
        """
        対象送信元のメールを取得し、YouTube 動画参照のリストを返す。

        Args:
            hours_back: 過去何時間分のメールを取得するか（date 未指定時）
            date: 特定日の全メールを取得（指定時）

        Returns:
            VideoRef のリスト（メール横断で動画 ID 重複除去済み）
        """
        if self.gmail_service is None:
            logger.error("Gmail service is not initialized")
            return []

        query = self._build_query(hours_back, date)
        logger.info(f"Gmail検索クエリ: {query}")

        try:
            service = self.gmail_service
            response = service.users().messages().list(userId="me", q=query).execute()
            messages = response.get("messages", [])
            logger.info(f"Gmail検索結果: {len(messages)}件のメッセージ")
        except HttpError as error:
            logger.error(f"Gmail APIエラー: {error}")
            return []

        refs: List[VideoRef] = []
        seen_ids = set()

        for i, msg in enumerate(messages, 1):
            try:
                detail = (
                    service.users().messages().get(userId="me", id=msg["id"]).execute()
                )
            except HttpError as e:
                logger.error(f"メッセージ取得エラー ({msg['id']}): {e}")
                continue

            headers = detail.get("payload", {}).get("headers", [])
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"),
                "No Subject",
            )
            email_date = self._email_date(detail)
            logger.info(f"  -> ({i}/{len(messages)}) 件名: {subject}")

            body = self._extract_body(detail)
            urls = extract_youtube_urls(body)
            logger.info(f"     YouTube URL: {len(urls)}件抽出")

            for url in urls:
                vid = extract_video_id(url)
                if not vid or vid in seen_ids:
                    continue
                seen_ids.add(vid)
                refs.append(
                    VideoRef(
                        url=url,
                        video_id=vid,
                        email_date=email_date,
                        source_subject=subject,
                    )
                )

        logger.info(f"抽出した動画: {len(refs)}件（重複除去後）")
        return refs

    def _email_date(self, message: Dict) -> str:
        """メール配信日時を YYYY-MM-DD (JST) で返す"""
        if "internalDate" in message:
            jst = pytz.timezone("Asia/Tokyo")
            ts = int(message["internalDate"]) / 1000
            return datetime.fromtimestamp(ts, tz=jst).strftime("%Y-%m-%d")
        return ""

    def _extract_body(self, message: Dict) -> str:
        """メールメッセージから本文 HTML を抽出"""
        payload = message.get("payload", {})
        return self._extract_body_from_payload(payload)

    def _extract_body_from_payload(self, payload: Dict) -> str:
        """ペイロードからメール本文を抽出（再帰的、text/html 優先）"""
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html":
                    data = part.get("body", {}).get("data", "")
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
