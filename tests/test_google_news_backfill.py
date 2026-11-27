"""Google ニュース検索による Google Alerts の取り戻しのテスト（ネットワークなし）"""

import json
import urllib.parse
from datetime import date

import pytest

from minitools.collectors.google_news_backfill import (
    AlertKeyword,
    GoogleNewsBackfillCollector,
    build_batchexecute_body,
    build_search_url,
    extract_decoding_params,
    parse_batchexecute_response,
    parse_rss,
)

DAY = date(2026, 11, 22)


def _item(title, link, pub, source="Example News", url="https://www.example.com"):
    return (
        f"<item><title>{title}</title><link>{link}</link>"
        f"<pubDate>{pub}</pubDate>"
        f'<source url="{url}">{source}</source></item>'
    )


def _rss(*items):
    return f"<rss><channel>{''.join(items)}</channel></rss>"


def test_build_search_url_uses_one_day_window_and_locale():
    kw = AlertKeyword("生成AI", hl="ja", gl="JP", ceid="JP:ja")
    url = build_search_url(kw, DAY)
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert qs["q"] == ["生成AI after:2026-11-22 before:2026-11-23"]
    assert qs["hl"] == ["ja"] and qs["gl"] == ["JP"] and qs["ceid"] == ["JP:ja"]


def test_parse_rss_keeps_only_target_day_in_jst_newest_first():
    xml = _rss(
        # 11/22 01:00 UTC = 11/22 10:00 JST → 対象
        _item(
            "Older story - Example News",
            "https://news.google.com/rss/articles/A",
            "Sun, 22 Nov 2026 01:00:00 GMT",
        ),
        # 11/22 20:00 UTC = 11/23 05:00 JST → 対象外
        _item(
            "Next day story - Example News",
            "https://news.google.com/rss/articles/B",
            "Sun, 22 Nov 2026 20:00:00 GMT",
        ),
        # 11/22 12:00 UTC = 11/22 21:00 JST → 対象・こちらが新しい
        _item(
            "Newer story - Example News",
            "https://news.google.com/rss/articles/C",
            "Sun, 22 Nov 2026 12:00:00 GMT",
        ),
    )
    alerts = parse_rss(xml, DAY, limit=10)
    assert [a.title for a in alerts] == ["Newer story", "Older story"]
    assert all(a.email_date == "2026-11-22" for a in alerts)
    assert alerts[0].source == "www.example.com"
    assert alerts[0].url == "https://news.google.com/rss/articles/C"


def test_parse_rss_applies_limit():
    xml = _rss(
        *[
            _item(
                f"Story number {i}",
                f"https://news.google.com/rss/articles/{i}",
                f"Sun, 22 Nov 2026 0{i}:00:00 GMT",
            )
            for i in range(5)
        ]
    )
    assert len(parse_rss(xml, DAY, limit=3)) == 3


def test_parse_rss_tolerates_broken_xml():
    assert parse_rss("not xml", DAY, limit=10) == []
    assert parse_rss("", DAY, limit=10) == []


def test_extract_decoding_params():
    html = '<div jscontroller="x" data-n-a-sg="SIG123" data-n-a-ts="1764000000"></div>'
    assert extract_decoding_params(html) == {
        "signature": "SIG123",
        "timestamp": "1764000000",
    }
    assert extract_decoding_params("<html></html>") is None


def test_build_batchexecute_body_carries_id_signature_and_timestamp():
    body = build_batchexecute_body("CBMiABC", "SIG123", "1764000000")
    assert body.startswith("f.req=")
    payload = json.loads(urllib.parse.unquote(body[len("f.req=") :]))
    inner = json.loads(payload[0][0][1])
    assert payload[0][0][0] == "Fbv4je"
    assert inner[0] == "garturlreq"
    assert inner[-3:] == ["CBMiABC", 1764000000, "SIG123"]


def test_parse_batchexecute_response():
    inner = json.dumps(["garturlres", "https://www.example.com/a?b=1", 1])
    text = ")]}'\n\n" + json.dumps(
        [["wrb.fr", "Fbv4je", inner, None, None, None, "generic"]]
    )
    assert parse_batchexecute_response(text) == "https://www.example.com/a?b=1"
    assert parse_batchexecute_response(")]}'\n\n[]") is None


@pytest.mark.asyncio
async def test_collect_resolves_urls_drops_failures_and_dedups(monkeypatch):
    kw = [
        AlertKeyword("AI", hl="en-US", gl="US", ceid="US:en"),
        AlertKeyword("LLM", hl="en-US", gl="US", ceid="US:en"),
    ]
    collector = GoogleNewsBackfillCollector(keywords=kw, request_interval=0)

    feeds = {
        "AI": _rss(
            _item(
                "Shared story here",
                "https://news.google.com/rss/articles/S",
                "Sun, 22 Nov 2026 03:00:00 GMT",
            ),
            _item(
                "Cannot resolve this",
                "https://news.google.com/rss/articles/X",
                "Sun, 22 Nov 2026 02:00:00 GMT",
            ),
        ),
        "LLM": _rss(
            _item(
                "Shared story here",
                "https://news.google.com/rss/articles/S",
                "Sun, 22 Nov 2026 03:00:00 GMT",
            ),
        ),
    }

    async def fake_get(session, url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
        return feeds[q.split(" ")[0]]

    async def fake_resolve(session, link):
        return {"https://news.google.com/rss/articles/S": "https://site.example/s"}.get(
            link
        )

    monkeypatch.setattr(collector, "_get", fake_get)
    monkeypatch.setattr(collector, "resolve_url", fake_resolve)

    alerts = await collector.collect(DAY, DAY)
    assert [a.url for a in alerts] == ["https://site.example/s"]
    assert alerts[0].email_date == "2026-11-22"


def test_is_video_url():
    from minitools.collectors.google_news_backfill import is_video_url

    assert is_video_url("https://youtu.be/abc")
    assert is_video_url("https://www.youtube.com/watch?v=abc")
    assert not is_video_url("https://fortune.com/2026/11/22/ai/")


def test_drop_already_saved_keeps_only_new():
    import asyncio
    import logging
    from types import SimpleNamespace

    from scripts.google_alerts_backfill import drop_already_saved

    saved = {"https://a.example/1"}

    class FakePublisher:
        async def check_existing(self, database_id, url):
            return url in saved

    alerts = [
        SimpleNamespace(url="https://a.example/1"),
        SimpleNamespace(url="https://b.example/2"),
    ]
    remaining = asyncio.run(
        drop_already_saved(
            alerts, FakePublisher(), "db", logging.getLogger("t"), interval=0
        )
    )
    assert [a.url for a in remaining] == ["https://b.example/2"]
