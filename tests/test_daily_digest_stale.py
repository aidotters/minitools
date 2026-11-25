"""google-alert-daily-digest の「記事が長く入っていない」警告のテスト"""

from datetime import datetime

import pytest

from minitools.publishers.slack import SlackPublisher
from scripts.google_alert_daily_digest import is_feed_stale


class _FakeReader:
    def __init__(self, articles=None, error=None):
        self.articles = articles or []
        self.error = error
        self.calls = []

    async def get_articles_by_date_range(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.articles


NOW = datetime(2026, 11, 25, 19, 0)


@pytest.mark.asyncio
async def test_stale_when_no_articles_in_window():
    reader = _FakeReader(articles=[])
    assert await is_feed_stale(reader, "db", 24, 48, NOW) is True
    assert reader.calls[0]["start_date"] == "2026-11-23"
    assert reader.calls[0]["end_date"] == "2026-11-25"


@pytest.mark.asyncio
async def test_not_stale_when_articles_exist():
    reader = _FakeReader(articles=[{"title": "x"}])
    assert await is_feed_stale(reader, "db", 24, 48, NOW) is False


@pytest.mark.asyncio
async def test_not_stale_when_window_not_longer():
    reader = _FakeReader(articles=[])
    assert await is_feed_stale(reader, "db", 48, 48, NOW) is False
    assert reader.calls == []


@pytest.mark.asyncio
async def test_not_stale_when_notion_fails():
    reader = _FakeReader(error=RuntimeError("boom"))
    assert await is_feed_stale(reader, "db", 24, 48, NOW) is False


def test_stale_warning_message():
    msg = SlackPublisher.format_stale_alerts_warning(48)
    assert "過去48時間" in msg
    assert "googlealerts-noreply@google.com" in msg
