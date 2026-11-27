"""
Google Alerts が届かなかった期間を、Google ニュースの検索で取り戻すためのコレクター。

Google Alerts は配信できなかったメールを後から送り直さない。そこで、アラートと同じ
キーワードで Google ニュースの RSS 検索を1日ずつ引き、結果を Google Alerts と同じ
Alert 形式にして、いつもの流れ（本文取得 → 翻訳・要約 → Notion 保存）に流す。

- 日付は記事の公開日（JST）を使う。週次ダイジェストは Notion の Date で記事を選ぶため、
  記事の日付で入れれば取り戻した記事がその週の集計に入る。
- RSS の link は news.google.com/rss/articles/... の形なので、元記事の URL に戻してから
  使う（Notion の重複判定と本文取得が元記事の URL を前提にしているため）。戻せなかった
  ものは捨てる（Google ニュースの URL のまま入れると、同じ記事が別物として二重に入る）。
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import aiohttp
import pytz

from minitools.collectors.google_alerts import Alert
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

JST = pytz.timezone("Asia/Tokyo")

RSS_SEARCH_URL = "https://news.google.com/rss/search"
ARTICLE_PAGE_URL = "https://news.google.com/rss/articles/{id}"
BATCHEXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class AlertKeyword:
    """Google Alerts に登録しているキーワードと、その言語・地域"""

    query: str
    hl: str
    gl: str
    ceid: str


EN_US = {"hl": "en-US", "gl": "US", "ceid": "US:en"}
JA_JP = {"hl": "ja", "gl": "JP", "ceid": "JP:ja"}

# Google Alerts に登録しているアラート（2026-11 時点・メールの見出しから確認）。
# 英語のアラートは hl=en gl=US、日本語のアラートは ja/JP で届いている。
DEFAULT_KEYWORDS: List[AlertKeyword] = [
    AlertKeyword("AI", **EN_US),
    AlertKeyword("LLM", **EN_US),
    AlertKeyword('"Generative AI"', **EN_US),
    AlertKeyword('"Deep Learning"', **EN_US),
    AlertKeyword('"AI startup"', **EN_US),
    AlertKeyword("生成AI", **JA_JP),
    AlertKeyword("ディープラーニング", **JA_JP),
    AlertKeyword('"AI スタートアップ"', **JA_JP),
]


def build_search_url(keyword: AlertKeyword, day: date) -> str:
    """1日分の Google ニュース RSS 検索 URL を作る（after は当日、before は翌日）"""
    nxt = day + timedelta(days=1)
    q = f"{keyword.query} after:{day.isoformat()} before:{nxt.isoformat()}"
    params = {"q": q, "hl": keyword.hl, "gl": keyword.gl, "ceid": keyword.ceid}
    return f"{RSS_SEARCH_URL}?{urllib.parse.urlencode(params)}"


def _strip_source_suffix(title: str, source: str) -> str:
    """Google ニュースの title は「見出し - 媒体名」なので媒体名を落とす"""
    if source and title.endswith(f" - {source}"):
        return title[: -len(f" - {source}")].strip()
    return title.strip()


def parse_rss(xml_text: str, day: date, limit: int) -> List[Alert]:
    """
    RSS を Alert のリストにする。公開日（JST）が day の記事だけを、新しい順に limit 件まで。

    url には Google ニュースの link をそのまま入れる（元記事の URL へは後で戻す）。
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"RSS を読めませんでした: {e}")
        return []

    items = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        title = item.findtext("title") or ""
        pub = item.findtext("pubDate") or ""
        source_el = item.find("source")
        source_name = (source_el.text or "").strip() if source_el is not None else ""
        source_url = source_el.get("url", "") if source_el is not None else ""
        if not link or not pub:
            continue
        try:
            published = parsedate_to_datetime(pub).astimezone(JST)
        except (TypeError, ValueError):
            continue
        if published.date() != day:
            continue
        # 通常のアラートと同じく、媒体はドメインで持つ
        source = urllib.parse.urlparse(source_url).netloc if source_url else ""
        title = _strip_source_suffix(title, source_name)
        items.append((published, link, title, source or source_name))

    items.sort(key=lambda x: x[0], reverse=True)
    alerts = []
    for published, link, title, source in items[:limit]:
        if len(title) < 5:
            continue
        alerts.append(
            Alert(
                title=title,
                url=link,
                source=source or "Unknown",
                date_processed=datetime.now().isoformat(),
                email_date=published.strftime("%Y-%m-%d"),
            )
        )
    return alerts


def _article_id(link: str) -> Optional[str]:
    m = re.search(r"news\.google\.com/(?:rss/)?articles/([^?/#]+)", link)
    return m.group(1) if m else None


def extract_decoding_params(html: str) -> Optional[Dict[str, str]]:
    """記事ページの HTML から、URL を戻すのに要る署名と時刻を取り出す"""
    sig = re.search(r'data-n-a-sg="([^"]+)"', html)
    ts = re.search(r'data-n-a-ts="([^"]+)"', html)
    if not sig or not ts:
        return None
    return {"signature": sig.group(1), "timestamp": ts.group(1)}


def build_batchexecute_body(article_id: str, signature: str, timestamp: str) -> str:
    inner = [
        "garturlreq",
        [
            [
                "X",
                "X",
                ["X", "X"],
                None,
                None,
                1,
                1,
                "US:en",
                None,
                1,
                None,
                None,
                None,
                None,
                None,
                0,
                1,
            ],
            "X",
            "X",
            1,
            [1, 1, 1],
            1,
            1,
            None,
            0,
            0,
            None,
            0,
        ],
        article_id,
        int(timestamp),
        signature,
    ]
    payload = [[["Fbv4je", json.dumps(inner, separators=(",", ":")), None, "generic"]]]
    return "f.req=" + urllib.parse.quote(json.dumps(payload, separators=(",", ":")))


def parse_batchexecute_response(text: str) -> Optional[str]:
    """batchexecute の応答から元記事の URL を取り出す"""
    m = re.search(r'\\"garturlres\\",\\"(https?://[^\\"]+)\\"', text)
    if m:
        return m.group(1).encode().decode("unicode_escape")
    # 応答が JSON として読める形のときの経路
    try:
        body = text.split("\n\n", 1)[1]
        data = json.loads(body)
        inner = json.loads(data[0][2])
        url = inner[1]
        if isinstance(url, str) and url.startswith("http"):
            return url
    except (IndexError, ValueError, TypeError, KeyError):
        pass
    return None


class GoogleNewsBackfillCollector:
    """Google ニュースの検索で、届かなかった日の Google Alerts を作り直す"""

    def __init__(
        self,
        keywords: Optional[List[AlertKeyword]] = None,
        per_keyword_per_day: int = 10,
        concurrency: int = 3,
        request_interval: float = 1.0,
    ):
        self.keywords = keywords or DEFAULT_KEYWORDS
        self.per_keyword_per_day = per_keyword_per_day
        self._sem = asyncio.Semaphore(concurrency)
        self.request_interval = request_interval

    async def _get(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        async with self._sem:
            for attempt in range(3):
                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=30)
                    ) as r:
                        if r.status == 200:
                            text = await r.text()
                            await asyncio.sleep(self.request_interval)
                            return text
                        logger.warning(f"HTTP {r.status}: {url[:100]}")
                        if r.status not in (429, 500, 502, 503):
                            return None
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(f"取得エラー ({attempt + 1}/3): {e}")
                await asyncio.sleep(2 ** (attempt + 1))
        return None

    async def resolve_url(
        self, session: aiohttp.ClientSession, link: str
    ) -> Optional[str]:
        """Google ニュースの link を元記事の URL に戻す。戻せなければ None"""
        article_id = _article_id(link)
        if not article_id:
            return link if "news.google.com" not in link else None
        html = await self._get(session, ARTICLE_PAGE_URL.format(id=article_id))
        if not html:
            return None
        params = extract_decoding_params(html)
        if not params:
            return None
        body = build_batchexecute_body(
            article_id, params["signature"], params["timestamp"]
        )
        async with self._sem:
            try:
                async with session.post(
                    BATCHEXECUTE_URL,
                    data=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as r:
                    text = await r.text()
                    await asyncio.sleep(self.request_interval)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"URL の復元に失敗: {e}")
                return None
        return parse_batchexecute_response(text)

    async def collect(self, start: date, end: date) -> List[Alert]:
        """start〜end（両端を含む）の各日について、キーワードごとに記事を集める"""
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        alerts: List[Alert] = []
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            for day in days:
                for kw in self.keywords:
                    xml_text = await self._get(session, build_search_url(kw, day))
                    found = parse_rss(xml_text or "", day, self.per_keyword_per_day)
                    logger.info(f"{day} {kw.query}: {len(found)}件")
                    alerts.extend(found)

            resolved = await asyncio.gather(
                *(self.resolve_url(session, a.url) for a in alerts)
            )

        seen = set()
        result: List[Alert] = []
        dropped = 0
        for alert, url in zip(alerts, resolved):
            if not url:
                dropped += 1
                continue
            if url in seen:
                continue
            seen.add(url)
            alert.url = url
            result.append(alert)
        logger.info(
            f"取り戻し候補 {len(alerts)}件 → 元記事の URL に戻せた重複なし {len(result)}件"
            f"（戻せず捨てた {dropped}件）"
        )
        return result
