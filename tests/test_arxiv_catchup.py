"""arxiv の抜けた回の取り戻し（判定と記録）のテスト"""

from datetime import date, datetime

from minitools.utils.arxiv_catchup import (
    load_last_done,
    missed_targets,
    record_done,
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
        missed = missed_targets(datetime(2026, 11, 27, 11, 0), date(2026, 11, 24))
        assert missed == [date(2026, 11, 25)]

    def test_nothing_missed(self):
        missed = missed_targets(datetime(2026, 11, 27, 11, 0), date(2026, 11, 25))
        assert missed == []

    def test_several_missed_in_order(self):
        missed = missed_targets(datetime(2026, 11, 28, 16, 0), date(2026, 11, 25))
        assert missed == [date(2026, 11, 26), date(2026, 11, 27)]

    def test_no_record_does_nothing(self):
        # 入れた直後は、どの回が済んでいるか分からないので取り戻さない
        assert missed_targets(datetime(2026, 11, 28, 16, 0), None) == []

    def test_lookback_limit(self):
        missed = missed_targets(
            datetime(2026, 11, 28, 16, 0), date(2026, 11, 1), lookback_days=1
        )
        assert missed == [date(2026, 11, 26), date(2026, 11, 27)]


class TestState:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "state.json")
        assert load_last_done(path) is None
        record_done(date(2026, 11, 25), path)
        assert load_last_done(path) == date(2026, 11, 25)

    def test_does_not_go_back(self, tmp_path):
        path = str(tmp_path / "state.json")
        record_done(date(2026, 11, 25), path)
        record_done(date(2026, 11, 20), path)
        assert load_last_done(path) == date(2026, 11, 25)

    def test_broken_file_is_treated_as_missing(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("{broken", encoding="utf-8")
        assert load_last_done(str(path)) is None
