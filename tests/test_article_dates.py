"""Tests for article_dates: JSON-LD/OpenGraph 日付抽出の純関数。"""

from minitools.scrapers.article_dates import (
    empty_dates,
    extract_dates_from_signals,
    normalize_iso_date,
)


class TestNormalizeIsoDate:
    def test_iso_with_z(self):
        assert normalize_iso_date("2026-03-09T15:05:43Z") == "2026-03-09"

    def test_iso_with_millis_and_z(self):
        assert normalize_iso_date("2026-03-26T08:15:41.297Z") == "2026-03-26"

    def test_iso_with_offset(self):
        assert normalize_iso_date("2026-03-09T15:05:43+09:00") == "2026-03-09"

    def test_date_only_prefix_fallback(self):
        assert normalize_iso_date("2026-03-09 something") == "2026-03-09"

    def test_none(self):
        assert normalize_iso_date(None) is None

    def test_empty(self):
        assert normalize_iso_date("   ") is None

    def test_garbage(self):
        assert normalize_iso_date("not a date") is None


class TestExtractDatesFromSignals:
    def test_jsonld_published_and_modified(self):
        """JSON-LD の datePublished/dateModified を採用し YYYY-MM-DD に整形する。"""
        result = extract_dates_from_signals(
            jsonld_pairs=[
                {
                    "datePublished": "2026-04-12T19:35:25Z",
                    "dateModified": "2026-04-12T19:35:25Z",
                }
            ],
        )
        assert result["published_at"] == "2026-04-12"
        assert result["last_modified"] == "2026-04-12"
        assert result["published_at_source"] == "html-meta"
        assert result["last_modified_source"] == "html-meta"

    def test_jsonld_beats_og_published(self):
        """[正本判定] JSON-LD datePublished(3/9) が og article:published_time(3/26) に勝つ。

        実機検証で og meta が更新時刻を指すケースを観測した契約の固定テスト。
        """
        result = extract_dates_from_signals(
            jsonld_pairs=[
                {
                    "datePublished": "2026-03-09T15:05:43Z",
                    "dateModified": "2026-03-26T08:15:41Z",
                }
            ],
            og_published="2026-03-26T08:15:41.297Z",
            og_modified=None,
        )
        assert result["published_at"] == "2026-03-09"
        assert result["last_modified"] == "2026-03-26"

    def test_og_fallback_when_no_jsonld(self):
        """JSON-LD 不在時は OpenGraph meta にフォールバックする。"""
        result = extract_dates_from_signals(
            jsonld_pairs=[],
            og_published="2026-01-15T00:00:00Z",
            og_modified="2026-02-20T00:00:00Z",
        )
        assert result["published_at"] == "2026-01-15"
        assert result["last_modified"] == "2026-02-20"
        assert result["published_at_source"] == "html-meta"
        assert result["last_modified_source"] == "html-meta"

    def test_no_signals_yields_unknown(self):
        """シグナルが何も無ければ None + unknown。"""
        result = extract_dates_from_signals(jsonld_pairs=[])
        assert result == empty_dates()
        assert result["published_at"] is None
        assert result["published_at_source"] == "unknown"
        assert result["last_modified_source"] == "unknown"

    def test_partial_published_only(self):
        """published のみ取れた場合、last_modified は unknown のまま。"""
        result = extract_dates_from_signals(
            jsonld_pairs=[{"datePublished": "2026-05-01T00:00:00Z"}],
        )
        assert result["published_at"] == "2026-05-01"
        assert result["published_at_source"] == "html-meta"
        assert result["last_modified"] is None
        assert result["last_modified_source"] == "unknown"

    def test_first_valid_jsonld_wins(self):
        """複数 JSON-LD のうち最初に見つかった日付を採用する。"""
        result = extract_dates_from_signals(
            jsonld_pairs=[
                {"datePublished": None, "dateModified": None},
                {
                    "datePublished": "2026-06-01T00:00:00Z",
                    "dateModified": "2026-06-02T00:00:00Z",
                },
            ],
        )
        assert result["published_at"] == "2026-06-01"
        assert result["last_modified"] == "2026-06-02"

    def test_non_dict_pairs_ignored(self):
        """dict でない要素は無視される（堅牢性）。"""
        result = extract_dates_from_signals(
            jsonld_pairs=["garbage", None, {"datePublished": "2026-07-04T00:00:00Z"}],  # type: ignore[list-item]
        )
        assert result["published_at"] == "2026-07-04"
