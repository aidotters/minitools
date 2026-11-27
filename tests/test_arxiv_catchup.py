"""arxiv の抜けた回の取り戻し（判定と記録）のテスト"""

import sys
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import arxiv

from minitools.utils.arxiv_catchup import (
    DeliveryState,
    load_state,
    missed_targets,
    save_state,
    scheduled_targets,
)

# 2026-11-26 は木曜日（定時の回あり・対象日は 11-25）


class TestScheduledTargets:
    def test_before_run_time_excludes_today(self):
        targets = scheduled_targets(datetime(2026, 11, 26, 14, 29), lookback_days=0)
        assert targets == []

    def test_after_run_time_includes_today(self):
        targets = scheduled_targets(datetime(2026, 11, 26, 14, 30), lookback_days=0)
        assert targets == [date(2026, 11, 25)]

    def test_skips_sunday_and_monday(self):
        # 月曜 2026-11-30 の 15:00 から 3 日さかのぼる: 金(27)・土(28) の回だけ
        targets = scheduled_targets(datetime(2026, 11, 30, 15, 0), lookback_days=3)
        assert targets == [date(2026, 11, 26), date(2026, 11, 27)]


class TestMissedTargets:
    def test_logged_out_at_run_time(self):
        # 11-26 14:30 の回が走らず、11-27 11:00 にログインした
        missed = missed_targets(
            datetime(2026, 11, 27, 11, 0), DeliveryState(date(2026, 11, 24))
        )
        assert missed == [date(2026, 11, 25)]

    def test_nothing_missed(self):
        missed = missed_targets(
            datetime(2026, 11, 27, 11, 0), DeliveryState(date(2026, 11, 25))
        )
        assert missed == []

    def test_several_missed_in_order(self):
        missed = missed_targets(
            datetime(2026, 11, 28, 16, 0), DeliveryState(date(2026, 11, 25))
        )
        assert missed == [date(2026, 11, 26), date(2026, 11, 27)]

    def test_lookback_limit(self):
        missed = missed_targets(
            datetime(2026, 11, 28, 16, 0),
            DeliveryState(date(2026, 11, 1)),
            lookback_days=1,
        )
        assert missed == [date(2026, 11, 26), date(2026, 11, 27)]


class TestState:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "state.json")
        assert load_state(path) is None
        state = DeliveryState(date(2026, 11, 25), {date(2026, 11, 27): {"slack"}})
        save_state(state, path)
        assert load_state(path) == state

    def test_legacy_migration_without_historical_replay(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text('{"last_done":"2026-11-25"}', encoding="utf-8")
        state = load_state(str(path))
        assert state == DeliveryState(date(2026, 11, 25))
        assert not state.pending(date(2026, 11, 25), {"notion", "slack"})
        assert state.pending(date(2026, 11, 26), {"notion", "slack"}) == {
            "notion",
            "slack",
        }

    @pytest.mark.parametrize("data", ["{broken", '{"version":3}', '{"last_done":null}'])
    def test_bad_state_fails_closed(self, tmp_path, data):
        path = tmp_path / "state.json"
        path.write_text(data, encoding="utf-8")
        with pytest.raises(ValueError, match="再送を避けるため中止"):
            load_state(str(path))


@pytest.fixture
def entry(monkeypatch, tmp_path):
    from minitools.utils import arxiv_catchup

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 28, 16, tzinfo=tz)

    path = tmp_path / "state.json"
    monkeypatch.setattr(arxiv_catchup, "DEFAULT_STATE_PATH", str(path))
    monkeypatch.setattr(
        arxiv_catchup, "DEFAULT_LOCK_PATH", str(tmp_path / "arxiv.lock")
    )
    monkeypatch.setattr(arxiv, "datetime", FixedDatetime)
    monkeypatch.setattr(arxiv, "get_config", dict)
    monkeypatch.setattr(arxiv, "setup_logger", lambda *a, **kw: arxiv.logger)
    monkeypatch.setattr(arxiv, "wait_for_network", lambda *a: True)
    monkeypatch.setenv("SLACK_ARXIV_WEBHOOK_URL", "https://example.invalid/mock")
    monkeypatch.setenv("NOTION_ARXIV_DATABASE_ID", "test-db")

    hf = AsyncMock()
    hf.__aenter__.return_value = hf
    hf.get_daily_papers.return_value = [{"title": "example"}]
    monkeypatch.setattr(arxiv, "HFPapersResearcher", lambda: hf)
    monkeypatch.setattr(arxiv, "build_daily_selection", lambda items, *a: items)
    monkeypatch.setattr(
        arxiv, "_translate", AsyncMock(side_effect=lambda papers: papers)
    )

    notion = MagicMock()
    notion.ensure_arxiv_properties = AsyncMock()
    notion.batch_save_articles = AsyncMock(
        return_value={"stats": {"success": 1, "failed": 0, "skipped": 0}}
    )
    monkeypatch.setattr(arxiv, "NotionPublisher", lambda **kw: notion)

    slack = AsyncMock()
    slack.__aenter__.return_value = slack
    slack.send_articles.return_value = True
    monkeypatch.setattr(arxiv, "SlackPublisher", lambda *a: slack)
    weekly = AsyncMock(return_value="page-id")
    monkeypatch.setattr(arxiv, "create_weekly_page", weekly)

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["arxiv", *args])
        arxiv.main()

    return run, notion, slack, weekly, hf, path


FRIDAY = date(2026, 11, 27)
THURSDAY = date(2026, 11, 26)
WEDNESDAY = date(2026, 11, 25)


@pytest.mark.parametrize("first", ["scheduled", "catch-up"])
def test_scheduled_and_catch_up_overlap_without_duplicate(entry, first):
    run, notion, slack, weekly, _, path = entry
    save_state(DeliveryState(THURSDAY), str(path))
    if first == "scheduled":
        run()
        run("--catch-up")
    else:
        run("--catch-up")
        run()
    assert (
        notion.batch_save_articles.await_count == slack.send_articles.await_count == 1
    )
    assert weekly.await_count == 1


def test_slack_false_retries_only_slack(entry):
    run, notion, slack, weekly, _, path = entry
    save_state(DeliveryState(THURSDAY), str(path))
    slack.send_articles.side_effect = [False, True]
    with pytest.raises(SystemExit, match="1"):
        run()
    assert load_state(str(path)).completed[FRIDAY] == {"notion", "weekly"}
    run("--catch-up")
    assert slack.send_articles.await_count == 2
    assert notion.batch_save_articles.await_count == weekly.await_count == 1


def test_notion_batch_failure_does_not_send_slack_twice_or_make_incomplete_weekly(
    entry,
):
    run, notion, slack, weekly, _, path = entry
    save_state(DeliveryState(THURSDAY), str(path))
    notion.batch_save_articles.side_effect = [
        {"stats": {"success": 0, "failed": 1, "skipped": 0}},
        {"stats": {"success": 0, "failed": 0, "skipped": 1}},
    ]
    with pytest.raises(SystemExit, match="1"):
        run()
    assert load_state(str(path)).completed[FRIDAY] == {"slack"}
    weekly.assert_not_awaited()
    run("--catch-up")
    assert notion.batch_save_articles.await_count == 2
    assert slack.send_articles.await_count == weekly.await_count == 1


def test_weekly_failure_retried_independently(entry):
    run, notion, slack, weekly, _, path = entry
    save_state(DeliveryState(THURSDAY), str(path))
    weekly.side_effect = [None, "page-id"]
    with pytest.raises(SystemExit, match="1"):
        run()
    run("--catch-up")
    assert weekly.await_count == 2
    assert (
        notion.batch_save_articles.await_count == slack.send_articles.await_count == 1
    )


def test_a_later_scheduled_success_does_not_hide_older_gap(entry):
    run, notion, slack, weekly, hf, path = entry
    save_state(DeliveryState(WEDNESDAY), str(path))
    run()
    run("--catch-up")
    assert [c.args[0] for c in hf.get_daily_papers.await_args_list] == [
        FRIDAY.isoformat(),
        THURSDAY.isoformat(),
    ]
    assert (
        notion.batch_save_articles.await_count == slack.send_articles.await_count == 2
    )
    assert weekly.await_count == 1


def test_first_catch_up_does_not_replay_history(entry):
    run, notion, slack, weekly, hf, path = entry
    run("--catch-up")
    assert load_state(str(path)) == DeliveryState(FRIDAY)
    hf.get_daily_papers.assert_not_awaited()
    notion.batch_save_articles.assert_not_awaited()
    slack.send_articles.assert_not_awaited()
    weekly.assert_not_awaited()


def test_failed_source_fetch_is_not_an_empty_digest(entry):
    run, notion, slack, weekly, hf, path = entry
    save_state(DeliveryState(THURSDAY), str(path))
    hf.get_daily_papers.side_effect = RuntimeError("offline")
    with pytest.raises(SystemExit, match="1"):
        run()
    hf.get_daily_papers.assert_awaited_once_with(FRIDAY.isoformat(), strict=True)
    assert not load_state(str(path)).completed
    notion.batch_save_articles.assert_not_awaited()
    slack.send_articles.assert_not_awaited()
    weekly.assert_not_awaited()


def test_notion_creation_without_id_is_failure_not_duplicate(monkeypatch):
    import asyncio

    from minitools.publishers.notion import NotionPublisher

    notion = NotionPublisher.__new__(NotionPublisher)
    monkeypatch.setattr(notion, "_normalize_url_by_source", lambda url: url)
    monkeypatch.setattr(notion, "check_existing", AsyncMock(side_effect=[False, True]))
    monkeypatch.setattr(notion, "_build_article_properties", lambda article: {})
    monkeypatch.setattr(notion, "create_page", AsyncMock(return_value=None))
    result = asyncio.run(
        notion.batch_save_articles(
            "db",
            [
                {"url": "https://example.invalid/a"},
                {"url": "https://example.invalid/b"},
            ],
            max_concurrent=1,
            strict=True,
        )
    )
    assert result["stats"] == {"success": 0, "skipped": 1, "failed": 1}


def test_empty_source_is_not_a_failure(entry):
    run, notion, slack, _, hf, path = entry
    save_state(DeliveryState(THURSDAY), str(path))
    hf.get_daily_papers.return_value = []
    run("--no-weekly")
    assert load_state(str(path)).completed[FRIDAY] == {"notion", "slack"}
    notion.batch_save_articles.assert_not_awaited()
    assert slack.send_articles.await_args.args[0] == []
