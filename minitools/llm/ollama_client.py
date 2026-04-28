"""
Ollama LLM client implementation.
"""

import asyncio
from typing import Dict, List, Optional

import ollama

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class OllamaClient(BaseLLMClient):
    """Ollama APIを使用するLLMクライアント"""

    def __init__(self, model: Optional[str] = None):
        """
        Args:
            model: 使用するOllamaモデル名（省略時は設定ファイルから取得）
        """
        config = get_config()
        self.default_model = model or config.get(
            "llm.ollama.default_model",
            config.get("models.translation", "gemma3:27b"),
        )
        self.client = ollama.Client()
        logger.debug(f"OllamaClient initialized with model: {self.default_model}")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """
        メッセージを送信してレスポンスを取得

        Args:
            messages: チャットメッセージのリスト
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            LLMからのレスポンステキスト

        Raises:
            LLMError: API呼び出しに失敗した場合
        """
        use_model = model or self.default_model

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=use_model,
                    messages=messages,
                ),
            )
            content = response.message.content
            result = content.strip() if content else ""
            logger.debug(f"Ollama response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            raise LLMError(f"Ollama API call failed: {e}") from e

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """
        プロンプトからテキスト生成

        Args:
            prompt: 生成のためのプロンプト
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            生成されたテキスト

        Raises:
            LLMError: API呼び出しに失敗した場合
        """
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, model)

    async def generate_from_images(
        self,
        prompt: str,
        images: List[bytes],
        mime_type: str = "image/png",
        model: Optional[str] = None,
    ) -> str:
        """画像からテキスト生成（multimodal は未対応）

        Ollama の multimodal モデル (llava 等) には未対応。
        warning ログを出して空文字列を返す（graceful degradation）。
        """
        logger.warning(
            "OllamaClient does not support multimodal generation in this build. "
            "Falling back to empty response."
        )
        return ""

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """
        JSON形式のレスポンスを取得

        Args:
            messages: チャットメッセージのリスト
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            LLMからのJSONレスポンステキスト

        Raises:
            LLMError: API呼び出しに失敗した場合
        """
        use_model = model or self.default_model

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=use_model,
                    messages=messages,
                    format="json",
                ),
            )
            content = response.message.content
            result = content.strip() if content else ""
            logger.debug(f"Ollama JSON response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"Ollama chat_json error: {e}")
            raise LLMError(f"Ollama API call failed: {e}") from e
