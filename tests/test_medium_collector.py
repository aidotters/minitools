"""Tests for MediumCollector claps extraction."""

import pytest
from unittest.mock import patch
from bs4 import BeautifulSoup

from minitools.collectors.medium import MediumCollector


@pytest.fixture
def collector():
    """Gmail認証をモックしたMediumCollectorインスタンス"""
    with patch.object(MediumCollector, "_authenticate_gmail"):
        return MediumCollector()


class TestParseCount:
    """_parse_count のテスト"""

    def test_integer(self):
        assert MediumCollector._parse_count("320") == 320

    def test_zero(self):
        assert MediumCollector._parse_count("0") == 0

    def test_k_suffix(self):
        assert MediumCollector._parse_count("1.2K") == 1200

    def test_k_suffix_lowercase(self):
        assert MediumCollector._parse_count("1.2k") == 1200

    def test_k_suffix_integer(self):
        assert MediumCollector._parse_count("5K") == 5000

    def test_m_suffix(self):
        assert MediumCollector._parse_count("1.5M") == 1500000

    def test_empty_string(self):
        assert MediumCollector._parse_count("") == 0

    def test_none(self):
        assert MediumCollector._parse_count(None) == 0

    def test_invalid(self):
        assert MediumCollector._parse_count("abc") == 0

    def test_whitespace(self):
        assert MediumCollector._parse_count("  320  ") == 320


class TestExtractClaps:
    """_extract_claps のテスト"""

    def test_claps_label_no_space(self, collector):
        """'Claps320' パターン"""
        html = "<div><span>5 min read</span><span>Claps320</span><span>Responses4</span></div>"
        container = BeautifulSoup(html, "html.parser").div
        assert collector._extract_claps(container) == 320

    def test_claps_label_with_space(self, collector):
        """'Claps 320' パターン"""
        html = "<div><span>Claps 1.2K</span></div>"
        container = BeautifulSoup(html, "html.parser").div
        assert collector._extract_claps(container) == 1200

    def test_claps_emoji(self, collector):
        """👏 アイコンの後の数値"""
        html = "<div><span>👏 500</span></div>"
        container = BeautifulSoup(html, "html.parser").div
        assert collector._extract_claps(container) == 500

    def test_min_read_pattern(self, collector):
        """'X min read' の後の数値"""
        html = "<div><span>5 min read 320 4</span></div>"
        container = BeautifulSoup(html, "html.parser").div
        assert collector._extract_claps(container) == 320

    def test_no_claps(self, collector):
        """拍手データがない場合は0"""
        html = "<div><span>Just some text</span></div>"
        container = BeautifulSoup(html, "html.parser").div
        assert collector._extract_claps(container) == 0

    def test_none_container(self, collector):
        """Noneが渡された場合は0"""
        assert collector._extract_claps(None) == 0

    def test_claps_in_nested_html(self, collector):
        """ネストされたHTML内のClapsパターン"""
        html = """
        <div>
            <a class="ag" href="https://medium.com/test">
                <h2>Article Title</h2>
                <h3>Preview text</h3>
            </a>
            <div>
                <span>3 min read</span>
                <span>Claps42</span>
                <span>Responses1</span>
            </div>
        </div>
        """
        container = BeautifulSoup(html, "html.parser").div
        assert collector._extract_claps(container) == 42


class TestParseArticlesWithClaps:
    """parse_articles がclapsを正しく抽出するかのテスト"""

    def _build_email_html(self, claps_text="Claps150"):
        """テスト用のMedium Daily Digest風HTMLを生成（新フォーマット）"""
        return f"""
        <html><body>
        <div>
            <div>
                <a href="https://medium.com/@author/test-article-12345?source=email-digest">
                    <h2>Test Article Title Here</h2>
                    <div>
                        <span>Author Name</span>
                    </div>
                    <div>This is a preview text that is long enough</div>
                </a>
                <div>
                    <span>5 min read</span>
                    <span>{claps_text}</span>
                    <span>Responses4</span>
                </div>
            </div>
        </div>
        </body></html>
        """

    def test_claps_extracted(self, collector):
        """parse_articlesが拍手数を抽出する"""
        html = self._build_email_html("Claps150")
        articles = collector.parse_articles(html)
        assert len(articles) == 1
        assert articles[0].claps == 150

    def test_claps_zero_when_absent(self, collector):
        """拍手データがない場合は0"""
        html = self._build_email_html("No data here")
        articles = collector.parse_articles(html)
        assert len(articles) == 1
        assert articles[0].claps == 0

    def test_claps_with_k_suffix(self, collector):
        """K表記の拍手数"""
        html = self._build_email_html("Claps2.5K")
        articles = collector.parse_articles(html)
        assert len(articles) == 1
        assert articles[0].claps == 2500
