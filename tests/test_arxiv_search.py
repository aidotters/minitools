"""arxiv-search（手動のキーワード検索）の期間とフラグの解決."""

from datetime import datetime

import pytest

from scripts.arxiv_search import resolve_date_range, resolve_outputs


class TestResolveDateRange:
    def test_one_day(self):
        start, end = resolve_date_range("2026-11-20", 1)
        assert start == end == datetime(2026, 11, 20)

    def test_several_days(self):
        start, end = resolve_date_range("2026-11-20", 3)
        assert start == datetime(2026, 11, 18)
        assert end == datetime(2026, 11, 20)

    def test_monday_is_not_extended(self):
        # 旧 arxiv にあった「月曜は3日」は持ち込まない
        start, end = resolve_date_range("2026-11-23", 1)
        assert start == end == datetime(2026, 11, 23)

    def test_days_must_be_positive(self):
        with pytest.raises(ValueError):
            resolve_date_range("2026-11-20", 0)


class TestResolveOutputs:
    def test_no_flags_means_both(self):
        assert resolve_outputs(False, False) == (True, True)

    def test_notion_only(self):
        assert resolve_outputs(True, False) == (True, False)

    def test_slack_only(self):
        assert resolve_outputs(False, True) == (False, True)

    def test_dry_run_disables_both(self):
        assert resolve_outputs(True, True, dry_run=True) == (False, False)
