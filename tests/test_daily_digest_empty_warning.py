"""google-alert-daily-digest の0件時の警告（供給元の停止に気づくため）"""

import asyncio
from datetime import date
from unittest.mock import MagicMock

from minitools.publishers.slack import SlackPublisher
from minitools.readers.notion import NotionReader
from scripts.google_alert_daily_digest import build_empty_warning


def test_warning_shows_latest_date_and_days():
    msg = build_empty_warning("2026-11-20", date(2026, 11, 24))
    assert "2026-11-20" in msg
    assert "4日前" in msg
    assert "from:googlealerts-noreply@google.com" in msg


def test_warning_accepts_datetime_string():
    msg = build_empty_warning("2026-11-20T17:14:00.000+09:00", date(2026, 11, 22))
    assert "2026-11-20（2日前）" in msg


def test_warning_when_no_article_at_all():
    msg = build_empty_warning(None, date(2026, 11, 24))
    assert "見当たりません" in msg


def test_warning_when_lookup_failed():
    msg = build_empty_warning(None, date(2026, 11, 24), lookup_failed=True)
    assert "取得に失敗" in msg
    assert "見当たりません" not in msg


def test_warning_when_date_unreadable():
    msg = build_empty_warning("not-a-date", date(2026, 11, 24))
    assert "読めませんでした" in msg


def test_format_daily_digest_puts_warning_after_header():
    slack = SlackPublisher()
    msg = slack.format_daily_digest(
        date="2026-11-24", articles=[], warning="記事が入っていません。"
    )
    lines = msg.splitlines()
    assert lines[0] == "*📰 Google Alerts Daily Digest (2026-11-24)*"
    assert lines[1] == "⚠️ 記事が入っていません。"
    assert "本日該当記事なし" in msg


def test_format_daily_digest_without_warning_is_unchanged():
    slack = SlackPublisher()
    msg = slack.format_daily_digest(date="2026-11-24", articles=[])
    assert msg == "*📰 Google Alerts Daily Digest (2026-11-24)*\n本日該当記事なし"


def _reader_with_response(response):
    reader = NotionReader.__new__(NotionReader)
    reader.client = MagicMock()
    reader.client.databases.query.return_value = response
    return reader


def test_get_latest_article_date_queries_newest_one():
    reader = _reader_with_response(
        {"results": [{"properties": {"Date": {"date": {"start": "2026-11-20"}}}}]}
    )
    got = asyncio.run(reader.get_latest_article_date("db"))
    assert got == "2026-11-20"
    kwargs = reader.client.databases.query.call_args.kwargs
    assert kwargs["page_size"] == 1
    assert kwargs["sorts"] == [{"property": "Date", "direction": "descending"}]


def test_get_latest_article_date_returns_none_when_empty():
    reader = _reader_with_response({"results": []})
    assert asyncio.run(reader.get_latest_article_date("db")) is None
