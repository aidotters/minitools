"""Tests for LangChainGeminiClient (thinking_level support)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    """Provide a dummy API key so the constructor does not raise."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def _import_client():
    """`langchain_google_genai` 依存を遅延 import するため都度ロードする"""
    from minitools.llm.langchain_gemini import LangChainGeminiClient

    return LangChainGeminiClient


class TestThinkingLevelInit:
    """`thinking_level` 引数の解決と検証"""

    def test_default_minimal_when_not_specified(self, monkeypatch):
        """thinking_level 未指定時は minimal がデフォルト"""
        # 設定値もデフォルト想定
        Client = _import_client()
        client = Client(api_key="test")
        assert client.thinking_level == "minimal"

    def test_explicit_value_used(self):
        """明示指定された thinking_level が採用される"""
        Client = _import_client()
        client = Client(api_key="test", thinking_level="medium")
        assert client.thinking_level == "medium"

    def test_invalid_thinking_level_raises(self):
        """不正値は ValueError"""
        Client = _import_client()
        with pytest.raises(ValueError, match="Invalid thinking_level"):
            Client(api_key="test", thinking_level="ultra")

    def test_default_model_from_config(self):
        """設定の default_model が読み込まれる（モデル ID 形式の確認）"""
        Client = _import_client()
        client = Client(api_key="test")
        # gemini-3.1-flash-lite-preview がデフォルト想定。
        # 旧テスト互換のため startswith("gemini") で確認に留める。
        assert isinstance(client.default_model, str)
        assert client.default_model.startswith("gemini")


class TestThinkingLevelInChatModel:
    """`_get_chat_model()` への thinking_config 反映"""

    def test_thinking_level_passed_to_chat_model(self):
        """thinking_level が model_kwargs.thinking_config に反映される"""
        Client = _import_client()
        client = Client(api_key="test", thinking_level="medium")

        with patch(
            "minitools.llm.langchain_gemini.ChatGoogleGenerativeAI"
        ) as mock_chat:
            mock_chat.return_value = MagicMock()
            client._get_chat_model()
            kwargs = mock_chat.call_args.kwargs
            assert kwargs["model_kwargs"]["thinking_config"] == {
                "thinking_level": "medium"
            }
            # 旧 thinking_budget は使われていない
            assert "thinking_budget" not in kwargs["model_kwargs"]["thinking_config"]

    def test_thinking_level_inherited_in_json_mode(self):
        """JSON モードでも同じ thinking_config が渡される"""
        Client = _import_client()
        client = Client(api_key="test", thinking_level="low")

        with patch(
            "minitools.llm.langchain_gemini.ChatGoogleGenerativeAI"
        ) as mock_chat:
            mock_chat.return_value = MagicMock()
            client._get_chat_model(json_mode=True)
            kwargs = mock_chat.call_args.kwargs
            assert kwargs["model_kwargs"]["thinking_config"] == {
                "thinking_level": "low"
            }
            assert kwargs["model_kwargs"]["response_mime_type"] == "application/json"

    def test_extract_text_str_passthrough(self):
        """旧来の str content は trim されてそのまま返る"""
        from minitools.llm.langchain_gemini import _extract_text

        assert _extract_text("  hello  ") == "hello"

    def test_extract_text_parts_list_dict_form(self):
        """Gemini 3 系の parts list (dict 形式) からテキストを抽出"""
        from minitools.llm.langchain_gemini import _extract_text

        content = [
            {"type": "text", "text": "ok", "extras": {"signature": "x"}},
        ]
        assert _extract_text(content) == "ok"

    def test_extract_text_parts_list_concat(self):
        """複数 parts は連結される"""
        from minitools.llm.langchain_gemini import _extract_text

        content = [
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
        ]
        assert _extract_text(content) == "ab"

    def test_extract_text_empty_returns_empty(self):
        from minitools.llm.langchain_gemini import _extract_text

        assert _extract_text("") == ""
        assert _extract_text([]) == ""
        assert _extract_text(None) == ""

    def test_thinking_level_default_minimal_in_chat_model(self):
        """未指定時は minimal が thinking_config に渡される"""
        Client = _import_client()
        client = Client(api_key="test")

        with patch(
            "minitools.llm.langchain_gemini.ChatGoogleGenerativeAI"
        ) as mock_chat:
            mock_chat.return_value = MagicMock()
            client._get_chat_model()
            kwargs = mock_chat.call_args.kwargs
            assert kwargs["model_kwargs"]["thinking_config"] == {
                "thinking_level": "minimal"
            }
