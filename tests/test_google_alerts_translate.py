"""Tests for the google-alerts-translate CLI components."""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from minitools.llm.base import BaseLLMClient
from minitools.scrapers.jina_reader import JinaReader

# scripts ディレクトリをインポート可能にする
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from scripts.google_alerts_translate import (  # noqa: E402
    _extract_domain,
    build_new_page_metadata,
    build_new_page_properties,
    process_url,
)


class _ScriptedLLM(BaseLLMClient):
    """chat 呼び出しを順番に決まったレスポンスで返すモック"""

    def __init__(self, responses: List[str]):
        self._responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        self.calls.append({"messages": messages, "model": model})
        if self._responses:
            return self._responses.pop(0)
        return ""

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        return ""


# ---------------------------------------------------------------------------
# JinaReader.extract_metadata
# ---------------------------------------------------------------------------


class TestJinaReaderMetadata:
    def test_extract_with_title_and_published(self):
        markdown = (
            "Title: Sample English Article\n"
            "URL Source: https://example.com/x\n"
            "Published Time: 2026-04-30T08:30:00Z\n\n"
            "Markdown Content:\nSome body text."
        )
        result = JinaReader.extract_metadata(markdown)
        assert result["title"] == "Sample English Article"
        assert result["published_at"] == "2026-04-30"

    def test_extract_title_only(self):
        markdown = "Title: Only Title\n\nMarkdown Content:\nbody"
        result = JinaReader.extract_metadata(markdown)
        assert result["title"] == "Only Title"
        assert result["published_at"] is None

    def test_extract_published_only_iso_format(self):
        markdown = "Published Time: 2025-01-15T12:00:00+00:00\n\nbody"
        result = JinaReader.extract_metadata(markdown)
        assert result["title"] is None
        assert result["published_at"] == "2025-01-15"

    def test_extract_no_metadata(self):
        markdown = "Just some random body without headers"
        result = JinaReader.extract_metadata(markdown)
        assert result == {"title": None, "published_at": None}


# ---------------------------------------------------------------------------
# _extract_domain
# ---------------------------------------------------------------------------


class TestExtractDomain:
    def test_with_www(self):
        assert (
            _extract_domain("https://www.techcrunch.com/2026/04/article")
            == "techcrunch.com"
        )

    def test_without_www(self):
        assert _extract_domain("https://example.com/foo/bar") == "example.com"

    def test_subdomain(self):
        assert _extract_domain("https://blog.openai.com/posts/x") == "blog.openai.com"


# ---------------------------------------------------------------------------
# build_new_page_metadata
# ---------------------------------------------------------------------------


class TestBuildMetadata:
    @pytest.mark.asyncio
    async def test_llm_success(self):
        llm = _ScriptedLLM(responses=["日本語タイトル", "これは記事の要約です。" * 3])
        metadata = await build_new_page_metadata(
            url="https://www.example.com/article",
            english_markdown="English body content",
            japanese_markdown="日本語の本文" * 50,
            jina_metadata={
                "title": "Original English Title",
                "published_at": "2026-04-01",
            },
            llm_client=llm,
        )
        assert metadata["title"] == "Original English Title"
        assert metadata["japanese_title"] == "日本語タイトル"
        assert metadata["source"] == "example.com"
        assert metadata["date"] == "2026-04-01"
        assert metadata["japanese_summary"].startswith("これは記事の要約")
        assert metadata["url"] == "https://www.example.com/article"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        # 両方の LLM 呼び出しが空文字列を返す → fallback パス
        llm = _ScriptedLLM(responses=["", ""])
        japanese_md = "日本語本文" * 100
        metadata = await build_new_page_metadata(
            url="https://example.com/path/my-cool-article",
            english_markdown="English",
            japanese_markdown=japanese_md,
            jina_metadata={"title": None, "published_at": None},
            llm_client=llm,
        )
        # タイトル: jina メタなし → URL パス末尾を fallback
        assert "my cool article" in metadata["title"]
        # 日本語タイトル LLM 失敗 → 英語タイトル fallback
        assert metadata["japanese_title"] == metadata["title"]
        # 要約 LLM 失敗 → 冒頭抜粋
        assert len(metadata["japanese_summary"]) <= 200
        assert metadata["japanese_summary"]
        # 公開日なし → 実行日（YYYY-MM-DD）
        assert len(metadata["date"]) == 10 and metadata["date"][4] == "-"


# ---------------------------------------------------------------------------
# build_new_page_properties
# ---------------------------------------------------------------------------


class TestBuildProperties:
    def _sample_metadata(self) -> Dict[str, Any]:
        return {
            "title": "English Title",
            "japanese_title": "日本語タイトル",
            "url": "https://www.example.com/x?utm_source=foo",
            "source": "example.com",
            "japanese_summary": "要約文",
            "date": "2026-04-30",
        }

    def test_translated_true_included(self):
        props = build_new_page_properties(
            self._sample_metadata(), normalized_url="https://www.example.com/x"
        )
        assert props["Translated"] == {"checkbox": True}

    def test_all_required_fields(self):
        props = build_new_page_properties(
            self._sample_metadata(), normalized_url="https://www.example.com/x"
        )
        expected_keys = {
            "Title",
            "Original Title",
            "URL",
            "Source",
            "Summary",
            "Snippet",
            "Date",
            "Tags",
            "Translated",
        }
        assert expected_keys.issubset(set(props.keys()))
        assert props["URL"] == {"url": "https://www.example.com/x"}
        assert props["Source"]["rich_text"][0]["text"]["content"] == "example.com"
        assert props["Date"] == {"date": {"start": "2026-04-30"}}
        assert props["Tags"] == {"multi_select": []}


# ---------------------------------------------------------------------------
# process_url (dry-run)
# ---------------------------------------------------------------------------


class TestProcessUrl:
    @pytest.mark.asyncio
    async def test_dry_run_success(self):
        jina = MagicMock(spec=JinaReader)
        jina.fetch_markdown = AsyncMock(
            return_value="Title: Hello\n\nMarkdown body content with enough length."
        )

        translator = MagicMock()
        translator.translate = AsyncMock(return_value="日本語の翻訳結果")

        block_builder = MagicMock()
        # dry-run 時は build_blocks が呼ばれないが、念のため戻り値を設定
        block_builder.build_blocks = MagicMock(return_value=[])

        publisher = MagicMock()  # dry_run では使われない

        llm = _ScriptedLLM(responses=[])

        result = await process_url(
            url="https://example.com/foo",
            jina=jina,
            translator=translator,
            block_builder=block_builder,
            publisher=publisher,
            database_id=None,
            llm_client=llm,
            dry_run=True,
        )
        assert result == "success"
        # Notion 系メソッドが一切呼ばれていないこと
        assert not publisher.find_page_by_url.called
        assert not publisher.create_page.called
        assert not publisher.append_blocks.called
        assert not publisher.update_page_properties.called
        # 翻訳が呼ばれていること
        translator.translate.assert_awaited_once()
