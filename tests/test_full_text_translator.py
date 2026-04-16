"""Tests for FullTextTranslator."""

import pytest

from minitools.processors.full_text_translator import FullTextTranslator
from tests.conftest import MockLLMClient


class TestFullTextTranslatorChunking:
    """チャンク分割ロジックのテスト"""

    def test_short_text_no_split(self):
        """短いテキストは分割されない"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm, chunk_size=1000)
        chunks = translator._split_into_chunks("Short text")
        assert len(chunks) == 1
        assert chunks[0] == "Short text"

    def test_long_text_split_by_headings(self):
        """長いテキストが見出しで分割される"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm, chunk_size=80)

        # chunk_sizeを超える長さのテキストを用意
        md = "# Section 1\n\n" + "A" * 50 + "\n\n# Section 2\n\n" + "B" * 50
        chunks = translator._split_into_chunks(md)
        assert len(chunks) >= 2
        assert "Section 1" in chunks[0]
        assert "Section 2" in chunks[-1]

    def test_single_large_section(self):
        """見出しのない大きなテキストは1チャンクになる"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm, chunk_size=100)

        md = "A" * 200
        chunks = translator._split_into_chunks(md)
        assert len(chunks) == 1

    def test_empty_text(self):
        """空テキストは空リストを返す"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm)
        chunks = translator._split_into_chunks("")
        assert chunks == [""]

    def test_h2_h3_also_split(self):
        """h2, h3でも分割される"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm, chunk_size=80)

        # chunk_sizeを超える長さのテキストを用意
        md = "## Section A\n\n" + "X" * 50 + "\n\n### Section B\n\n" + "Y" * 50
        chunks = translator._split_into_chunks(md)
        assert len(chunks) >= 2


class TestDoNotTranslateMarker:
    """DO NOT TRANSLATE マーカーのテスト"""

    def test_split_with_marker(self):
        """マーカーで正しく分割される"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm)

        md = "Body text\n\n<!-- DO NOT TRANSLATE -->\nReferences"
        translatable, untranslatable = translator._split_by_do_not_translate(md)

        assert translatable == "Body text"
        assert "<!-- DO NOT TRANSLATE -->" in untranslatable
        assert "References" in untranslatable

    def test_split_without_marker(self):
        """マーカーがない場合は全文がtranslatable"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm)

        md = "Full body text"
        translatable, untranslatable = translator._split_by_do_not_translate(md)

        assert translatable == "Full body text"
        assert untranslatable == ""

    def test_marker_at_beginning(self):
        """マーカーが先頭にある場合"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm)

        md = "<!-- DO NOT TRANSLATE -->\nAll references"
        translatable, untranslatable = translator._split_by_do_not_translate(md)

        assert translatable == ""
        assert "All references" in untranslatable


class TestFullTextTranslatorTranslation:
    """翻訳実行のテスト"""

    @pytest.mark.asyncio
    async def test_basic_translation(self):
        """基本的な翻訳が実行される"""
        mock_llm = MockLLMClient(chat_response="翻訳されたテキスト")
        translator = FullTextTranslator(llm_client=mock_llm)

        result = await translator.translate("Hello world")

        assert result == "翻訳されたテキスト"
        assert len(mock_llm.chat_calls) == 1

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self):
        """空テキストは空文字列を返す"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm)

        result = await translator.translate("")
        assert result == ""
        assert len(mock_llm.chat_calls) == 0

    @pytest.mark.asyncio
    async def test_translation_prompt_contains_text(self):
        """翻訳プロンプトに原文が含まれる"""
        mock_llm = MockLLMClient(chat_response="translated")
        translator = FullTextTranslator(llm_client=mock_llm)

        await translator.translate("Original text here")

        prompt_content = mock_llm.chat_calls[0]["messages"][0]["content"]
        assert "Original text here" in prompt_content

    @pytest.mark.asyncio
    async def test_translation_prompt_contains_code_rule(self):
        """翻訳プロンプトにコード非翻訳ルールが含まれる"""
        mock_llm = MockLLMClient(chat_response="translated")
        translator = FullTextTranslator(llm_client=mock_llm)

        await translator.translate("Some text")

        prompt_content = mock_llm.chat_calls[0]["messages"][0]["content"]
        assert "コードブロック" in prompt_content or "コード" in prompt_content

    @pytest.mark.asyncio
    async def test_multi_chunk_translation(self):
        """複数チャンクの翻訳が結合される"""
        mock_llm = MockLLMClient(chat_response="翻訳チャンク")
        translator = FullTextTranslator(llm_client=mock_llm, chunk_size=50)

        md = "# Section 1\n\nLong text here.\n\n# Section 2\n\nMore text here."
        result = await translator.translate(md)

        assert "翻訳チャンク" in result
        # 複数チャンクに分割されたことを確認
        assert len(mock_llm.chat_calls) >= 2

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """翻訳失敗時にリトライされる"""
        call_count = 0

        class FailThenSuccessLLM(MockLLMClient):
            async def chat(self, messages, model=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Temporary error")
                return "成功した翻訳"

        mock_llm = FailThenSuccessLLM()
        translator = FullTextTranslator(llm_client=mock_llm, max_retries=3)

        result = await translator.translate("Test text")
        assert result == "成功した翻訳"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_do_not_translate_marker_skips_rest(self):
        """<!-- DO NOT TRANSLATE --> マーカー以降は翻訳されない"""
        mock_llm = MockLLMClient(chat_response="翻訳済み本文")
        translator = FullTextTranslator(llm_client=mock_llm)

        md = (
            "# Introduction\n\nSome text.\n\n"
            "<!-- DO NOT TRANSLATE -->\n"
            "# References\n\n[1] Author et al. Paper title."
        )
        result = await translator.translate(md)

        assert "翻訳済み本文" in result
        assert "<!-- DO NOT TRANSLATE -->" in result
        assert "[1] Author et al. Paper title." in result
        # LLMに渡されたプロンプトにReferencesが含まれていないことを確認
        prompt_content = mock_llm.chat_calls[0]["messages"][0]["content"]
        assert "References" not in prompt_content

    @pytest.mark.asyncio
    async def test_no_do_not_translate_marker(self):
        """マーカーがない場合は全文が翻訳される"""
        mock_llm = MockLLMClient(chat_response="全文翻訳")
        translator = FullTextTranslator(llm_client=mock_llm)

        result = await translator.translate("Full text to translate")
        assert result == "全文翻訳"

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_returns_original(self):
        """全リトライ失敗時に原文を返す"""

        class AlwaysFailLLM(MockLLMClient):
            async def chat(self, messages, model=None):
                raise Exception("Persistent error")

        mock_llm = AlwaysFailLLM()
        translator = FullTextTranslator(llm_client=mock_llm, max_retries=2)

        result = await translator.translate("Original text")
        assert result == "Original text"
