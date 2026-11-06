"""Tests for FullTextTranslator."""

import asyncio

import pytest

from minitools.llm.base import LLMError
from minitools.processors.full_text_translator import (
    FullTextTranslator,
    TranslationError,
    is_fatal_llm_error,
)
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
    async def test_all_retries_exhausted_raises(self, monkeypatch):
        """全リトライ失敗時は原文を返さず TranslationError を送出する

        原文を返すと、呼び出し側が英語のまま「翻訳済み」として Notion に
        保存してしまう（2026-11-06 の Gemini クレジット枯渇で実際に発生）。
        """
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        call_count = 0

        class AlwaysFailLLM(MockLLMClient):
            async def chat(self, messages, model=None):
                nonlocal call_count
                call_count += 1
                raise Exception("Persistent error")

        translator = FullTextTranslator(llm_client=AlwaysFailLLM(), max_retries=2)

        with pytest.raises(TranslationError) as exc_info:
            await translator.translate("Original text")
        assert exc_info.value.fatal is False
        assert "Persistent error" in str(exc_info.value)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_empty_results_exhausted_raises(self, monkeypatch):
        """全リトライで空の結果しか返らない場合も TranslationError"""
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        translator = FullTextTranslator(
            llm_client=MockLLMClient(chat_response="   "), max_retries=2
        )

        with pytest.raises(TranslationError):
            await translator.translate("Original text")

    @pytest.mark.asyncio
    async def test_payment_required_fails_fast_without_retry(self, monkeypatch):
        """402（Prepay クレジット枯渇）はリトライせず即座に fatal で失敗する"""
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        call_count = 0

        class PaymentRequiredLLM(MockLLMClient):
            async def chat(self, messages, model=None):
                nonlocal call_count
                call_count += 1
                raise LLMError(
                    "LangChain Gemini API call failed: Error calling model "
                    "'gemini-3.1-flash-lite' (RESOURCE_EXHAUSTED): 402 "
                    "RESOURCE_EXHAUSTED. {'error': {'code': 402, 'message': "
                    "'Your prepayment credits are depleted.'}}"
                )

        translator = FullTextTranslator(llm_client=PaymentRequiredLLM(), max_retries=3)

        with pytest.raises(TranslationError) as exc_info:
            await translator.translate("Original text")
        assert exc_info.value.fatal is True
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_partial_chunk_failure_raises(self, monkeypatch):
        """一部のチャンクだけ失敗しても、英語混じりの結果を返さず失敗にする"""
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        call_count = 0

        class SecondChunkFailsLLM(MockLLMClient):
            async def chat(self, messages, model=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return "最初のチャンクの翻訳"
                raise Exception("Persistent error")

        translator = FullTextTranslator(
            llm_client=SecondChunkFailsLLM(), chunk_size=100, max_retries=2
        )
        md = "# Section 1\n\n" + "A" * 80 + "\n\n# Section 2\n\n" + "B" * 80

        with pytest.raises(TranslationError):
            await translator.translate(md)

    @pytest.mark.asyncio
    async def test_rate_limit_429_is_retried(self, monkeypatch):
        """429 RESOURCE_EXHAUSTED（レート制限）は一時的なのでリトライする"""
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        call_count = 0

        class RateLimitedOnceLLM(MockLLMClient):
            async def chat(self, messages, model=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise LLMError("429 RESOURCE_EXHAUSTED. Quota exceeded")
                return "翻訳成功"

        translator = FullTextTranslator(llm_client=RateLimitedOnceLLM(), max_retries=3)

        assert await translator.translate("Original text") == "翻訳成功"
        assert call_count == 2


async def _no_sleep(_delay):
    """リトライ待機をスキップする（テスト高速化）"""
    return None


class TestIsFatalLlmError:
    """課金・認証系エラー判定のテスト"""

    @pytest.mark.parametrize(
        "message",
        [
            "402 RESOURCE_EXHAUSTED. Your prepayment credits are depleted.",
            "PAYMENT_REQUIRED",
            "400 API key not valid. Please pass a valid API key.",
            "API_KEY_INVALID",
            "403 PERMISSION_DENIED",
        ],
    )
    def test_fatal(self, message):
        assert is_fatal_llm_error(Exception(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "429 RESOURCE_EXHAUSTED. Quota exceeded",
            "503 UNAVAILABLE",
            "Read timed out",
            "chunk 4021 failed",  # 402 を部分一致で誤検出しない
        ],
    )
    def test_not_fatal(self, message):
        assert is_fatal_llm_error(Exception(message)) is False

    def test_fatal_in_cause_chain(self):
        """LLMError でラップされた元例外の 402 も検出する"""
        try:
            try:
                raise RuntimeError("402 Payment Required")
            except RuntimeError as inner:
                raise LLMError("LangChain Gemini API call failed") from inner
        except LLMError as outer:
            assert is_fatal_llm_error(outer) is True


class TestFullTextTranslatorTablePreservation:
    """テーブル構造保持のテスト"""

    def test_split_preserves_table(self):
        """テーブル行がチャンク境界で分割されない"""
        mock_llm = MockLLMClient()
        translator = FullTextTranslator(llm_client=mock_llm, chunk_size=60)

        # chunk_size 超のテキストで、テーブルが中央に含まれるケース
        md = (
            "Intro paragraph that is not short at all to force splitting.\n\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n"
            "| 3 | 4 |\n\n"
            "Trailing paragraph text here."
        )
        chunks = translator._split_into_chunks(md)

        # テーブル行は同一チャンク内にまとまっている
        for chunk in chunks:
            if "| A | B |" in chunk:
                assert "|---|---|" in chunk
                assert "| 1 | 2 |" in chunk
                assert "| 3 | 4 |" in chunk
                break
        else:
            raise AssertionError("Table header not found in any chunk")

    def test_translation_prompt_has_table_rule(self):
        """翻訳プロンプトにテーブル構造維持ルールが含まれる"""
        from minitools.processors.full_text_translator import TRANSLATION_PROMPT

        assert "テーブル構造維持" in TRANSLATION_PROMPT

    def test_translation_prompt_forbids_outer_fence(self):
        """プロンプトに「コードフェンスで包まない」ルールが含まれる"""
        from minitools.processors.full_text_translator import TRANSLATION_PROMPT

        assert "コードフェンスで包まない" in TRANSLATION_PROMPT


class TestFullTextTranslatorOuterFenceUnwrap:
    """LLM が出力全体を ```markdown ... ``` で包んだ場合の剥離テスト"""

    def test_unwrap_markdown_fence(self):
        """```markdown ... ``` で包まれた出力が剥離される"""
        wrapped = "```markdown\n# 見出し\n\n本文\n```"
        result = FullTextTranslator._unwrap_outer_code_fence(wrapped)
        assert result == "# 見出し\n\n本文"

    def test_unwrap_plain_fence(self):
        """言語指定なし ``` ... ``` でも剥離される"""
        wrapped = "```\n# 見出し\n\n本文\n```"
        result = FullTextTranslator._unwrap_outer_code_fence(wrapped)
        assert result == "# 見出し\n\n本文"

    def test_no_unwrap_when_inner_fence(self):
        """内側に独立 ``` がある場合は剥離しない（誤剥離防止）"""
        wrapped = "```markdown\n# 見出し\n\n```python\ncode\n```\n\n本文\n```"
        result = FullTextTranslator._unwrap_outer_code_fence(wrapped)
        assert result == wrapped

    def test_no_unwrap_for_normal_text(self):
        """通常の翻訳結果はそのまま返す"""
        text = "# 見出し\n\n本文の段落"
        result = FullTextTranslator._unwrap_outer_code_fence(text)
        assert result == text


class TestFullTextTranslatorThinkingLevel:
    """thinking_level の伝搬テスト"""

    def test_thinking_level_propagated_to_client(self):
        """FullTextTranslator が thinking_level を get_llm_client に渡す"""
        from unittest.mock import patch, MagicMock

        with patch(
            "minitools.processors.full_text_translator.get_llm_client"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            FullTextTranslator(provider="gemini", thinking_level="medium")
            kwargs = mock_factory.call_args.kwargs
            assert kwargs["provider"] == "gemini"
            assert kwargs["thinking_level"] == "medium"

    def test_thinking_level_default_none(self):
        """thinking_level 未指定時は None が渡される（クライアント側でデフォルト解決）"""
        from unittest.mock import patch, MagicMock

        with patch(
            "minitools.processors.full_text_translator.get_llm_client"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            FullTextTranslator(provider="gemini")
            kwargs = mock_factory.call_args.kwargs
            assert kwargs["thinking_level"] is None
