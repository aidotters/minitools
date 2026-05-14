"""Tests for scripts/medium_translate.py helper functions."""

from __future__ import annotations

from typing import Any, Dict

from scripts.medium_translate import (
    NOTION_TEXT_LIMIT,
    _extract_clap_count_from_html,
    _extract_medium_metadata,
    _fallback_title_from_url,
    _normalize_iso_date,
    _normalize_medium_display_date,
    _parse_clap_count,
    build_new_page_properties,
)


class TestExtractMediumMetadata:
    def test_og_title_preferred(self):
        html = """
        <html><head>
          <meta property="og:title" content="OG Title">
          <title>HTML Title</title>
        </head></html>
        """
        result = _extract_medium_metadata(
            html, "https://medium.com/x/article-abc123def"
        )
        assert result["title"] == "OG Title"

    def test_title_tag_fallback(self):
        html = "<html><head><title>Only Title</title></head></html>"
        result = _extract_medium_metadata(html, "https://medium.com/x/foo")
        assert result["title"] == "Only Title"

    def test_url_fallback_when_no_title(self):
        html = "<html><head></head></html>"
        result = _extract_medium_metadata(
            html, "https://medium.com/abc/my-awesome-title-deadbeef12"
        )
        assert "my awesome title" in (result["title"] or "")

    def test_meta_author(self):
        html = '<html><head><meta name="author" content="Alice"></head></html>'
        result = _extract_medium_metadata(html, "https://medium.com/x/a")
        assert result["author"] == "Alice"

    def test_json_ld_author_fallback(self):
        html = """
        <html><head>
          <script type="application/ld+json">
          {"@type": "Article", "author": {"name": "Bob"}, "datePublished": "2024-03-15T10:00:00Z"}
          </script>
        </head></html>
        """
        result = _extract_medium_metadata(html, "https://medium.com/x/a")
        assert result["author"] == "Bob"
        assert result["published_at"] == "2024-03-15"

    def test_article_author_meta_fallback(self):
        html = (
            '<html><head><meta property="article:author" content="Carol"></head></html>'
        )
        result = _extract_medium_metadata(html, "https://medium.com/x/a")
        assert result["author"] == "Carol"

    def test_unknown_author_when_missing(self):
        html = "<html><head></head></html>"
        result = _extract_medium_metadata(html, "https://medium.com/x/a")
        assert result["author"] == "Unknown"

    def test_published_time_meta(self):
        html = (
            "<html><head>"
            '<meta property="article:published_time" content="2025-09-04T12:34:56+00:00">'
            "</head></html>"
        )
        result = _extract_medium_metadata(html, "https://medium.com/x/a")
        assert result["published_at"] == "2025-09-04"

    def test_published_at_none_when_missing(self):
        html = "<html><head></head></html>"
        result = _extract_medium_metadata(html, "https://medium.com/x/a")
        assert result["published_at"] is None

    def test_all_fields_missing_no_exception(self):
        result = _extract_medium_metadata("", "https://medium.com/x/post-1234abcd")
        assert result["title"]  # URL fallback
        assert result["author"] == "Unknown"
        assert result["published_at"] is None


class TestNormalizeIsoDate:
    def test_zulu(self):
        assert _normalize_iso_date("2024-03-15T10:00:00Z") == "2024-03-15"

    def test_offset(self):
        assert _normalize_iso_date("2025-09-04T12:34:56+09:00") == "2025-09-04"

    def test_date_only(self):
        assert _normalize_iso_date("2024-01-15") == "2024-01-15"

    def test_invalid(self):
        assert _normalize_iso_date("not-a-date") is None

    def test_none(self):
        assert _normalize_iso_date(None) is None


class TestFallbackTitleFromUrl:
    def test_removes_hash_suffix(self):
        result = _fallback_title_from_url(
            "https://medium.com/team/my-great-post-abc123def456"
        )
        assert result == "my great post"

    def test_underscore_and_dash(self):
        result = _fallback_title_from_url("https://example.com/a/b/foo_bar-baz")
        assert "foo bar baz" in result


class TestBuildNewPageProperties:
    def _metadata(self, **overrides: Any) -> Dict[str, Any]:
        base = {
            "title": "Original English Title",
            "japanese_title": "日本語タイトル",
            "url": "https://medium.com/x/foo-abc123",
            "author": "Alice",
            "japanese_summary": "短い要約です。",
            "date": "2025-09-04",
        }
        base.update(overrides)
        return base

    def test_full_snapshot(self):
        props = build_new_page_properties(
            self._metadata(), normalized_url="https://medium.com/x/foo"
        )
        assert props["Title"]["title"][0]["text"]["content"] == "Original English Title"
        assert (
            props["Japanese Title"]["rich_text"][0]["text"]["content"]
            == "日本語タイトル"
        )
        assert props["URL"]["url"] == "https://medium.com/x/foo"
        assert props["Author"]["rich_text"][0]["text"]["content"] == "Alice"
        assert props["Date"]["date"]["start"] == "2025-09-04"
        assert props["Summary"]["rich_text"][0]["text"]["content"] == "短い要約です。"
        assert props["Translated"]["checkbox"] is True
        assert "Claps" not in props

    def test_japanese_title_falls_back_to_english(self):
        meta = self._metadata(japanese_title="")
        props = build_new_page_properties(meta, normalized_url="https://x/y")
        assert (
            props["Japanese Title"]["rich_text"][0]["text"]["content"]
            == "Original English Title"
        )

    def test_author_defaults_to_unknown(self):
        meta = self._metadata(author=None)
        props = build_new_page_properties(meta, normalized_url="https://x/y")
        assert props["Author"]["rich_text"][0]["text"]["content"] == "Unknown"

    def test_summary_truncated_to_2000_chars(self):
        long_summary = "あ" * 3000
        meta = self._metadata(japanese_summary=long_summary)
        props = build_new_page_properties(meta, normalized_url="https://x/y")
        content = props["Summary"]["rich_text"][0]["text"]["content"]
        assert len(content) == NOTION_TEXT_LIMIT
        assert content == "あ" * NOTION_TEXT_LIMIT

    def test_date_falls_back_to_today_when_missing(self):
        meta = self._metadata(date=None)
        props = build_new_page_properties(meta, normalized_url="https://x/y")
        start = props["Date"]["date"]["start"]
        # YYYY-MM-DD 形式
        assert len(start) == 10 and start[4] == "-" and start[7] == "-"

    def test_claps_included_when_positive(self):
        meta = self._metadata(claps=55)
        props = build_new_page_properties(meta, normalized_url="https://x/y")
        assert props["Claps"] == {"number": 55}

    def test_claps_zero_included(self):
        meta = self._metadata(claps=0)
        props = build_new_page_properties(meta, normalized_url="https://x/y")
        assert props["Claps"] == {"number": 0}

    def test_claps_absent_when_none(self):
        meta = self._metadata(claps=None)
        props = build_new_page_properties(meta, normalized_url="https://x/y")
        assert "Claps" not in props


class TestParseClapCount:
    def test_plain_int(self):
        assert _parse_clap_count("55") == 55

    def test_k_suffix(self):
        assert _parse_clap_count("1.2K") == 1200

    def test_m_suffix(self):
        assert _parse_clap_count("3M") == 3_000_000

    def test_comma_thousands(self):
        assert _parse_clap_count("1,234") == 1234

    def test_invalid(self):
        assert _parse_clap_count("abc") is None

    def test_empty(self):
        assert _parse_clap_count("") is None


class TestExtractClapCountFromHtml:
    def test_extracts_number_after_clap_button(self):
        html = (
            '<button data-testid="headerClapButton">'
            '<svg viewBox="0 0 24 24"><path d="M0 0"/></svg></button>'
            '<p><button class="z">55</button></p>'
        )
        assert _extract_clap_count_from_html(html) == 55

    def test_skips_svg_only_buttons(self):
        html = (
            '<button data-testid="headerClapButton">'
            "<svg><path/></svg></button>"
            '<button class="a"><svg><path/></svg></button>'
            '<button class="b">1.2K</button>'
        )
        assert _extract_clap_count_from_html(html) == 1200

    def test_no_clap_button(self):
        assert _extract_clap_count_from_html("<p>hello</p>") is None

    def test_no_count(self):
        html = (
            '<button data-testid="headerClapButton">'
            "<svg><path/></svg></button>"
            "<p>no numeric buttons here</p>"
        )
        assert _extract_clap_count_from_html(html) is None


class TestNormalizeMediumDisplayDate:
    def test_abbrev_month(self):
        assert _normalize_medium_display_date("Feb 11, 2026") == "2026-02-11"

    def test_full_month(self):
        assert _normalize_medium_display_date("February 11, 2026") == "2026-02-11"

    def test_invalid(self):
        assert _normalize_medium_display_date("not-a-date") is None


class TestMediumTestidExtraction:
    def test_authorname_testid(self):
        html = (
            '<article><span data-testid="authorName">Mario Khoury</span>'
            '<span data-testid="storyPublishDate">Feb 11, 2026</span></article>'
        )
        result = _extract_medium_metadata(html, "https://medium.com/x/a-abc123")
        assert result["author"] == "Mario Khoury"
        assert result["published_at"] == "2026-02-11"

    def test_authorphoto_alt_fallback(self):
        html = '<article><img data-testid="authorPhoto" alt="Carol"></article>'
        result = _extract_medium_metadata(html, "https://medium.com/x/a-abc123")
        assert result["author"] == "Carol"

    def test_claps_extracted_into_metadata(self):
        html = (
            "<article>"
            '<button data-testid="headerClapButton"><svg><path/></svg></button>'
            '<p><button class="z">55</button></p>'
            "</article>"
        )
        result = _extract_medium_metadata(html, "https://medium.com/x/a-abc123")
        assert result["claps"] == 55
