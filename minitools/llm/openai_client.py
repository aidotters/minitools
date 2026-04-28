"""
OpenAI LLM client implementation.
"""

import base64
import os
from typing import Any, Dict, List, Optional, cast

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class OpenAIClient(BaseLLMClient):
    """OpenAI APIを使用するLLMクライアント"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Args:
            api_key: OpenAI APIキー（省略時は環境変数から取得）
            model: 使用するOpenAIモデル名（省略時は設定ファイルから取得）

        Raises:
            LLMError: openaiパッケージがインストールされていない場合
            ValueError: APIキーが設定されていない場合
        """
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise LLMError(
                "openai package is not installed. Install it with: uv add openai"
            ) from e

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. Set it in .env file or pass as argument."
            )

        config = get_config()
        self.default_model = model or config.get("llm.openai.default_model", "gpt-4o")

        self.client = AsyncOpenAI(api_key=self.api_key)
        logger.debug(f"OpenAIClient initialized with model: {self.default_model}")

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
            response = await self.client.chat.completions.create(
                model=use_model,
                messages=cast(List[Any], messages),
            )
            content = response.choices[0].message.content
            result = content.strip() if content else ""
            logger.debug(f"OpenAI response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            raise LLMError(f"OpenAI API call failed: {e}") from e

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
        """画像とプロンプトからテキスト生成（multimodal）"""
        use_model = model or self.default_model
        try:
            content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
            for img in images:
                b64 = base64.b64encode(img).decode("ascii")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64}",
                        },
                    }
                )
            messages = [{"role": "user", "content": content}]
            response = await self.client.chat.completions.create(
                model=use_model,
                messages=cast(List[Any], messages),
            )
            result = response.choices[0].message.content
            text = result.strip() if result else ""
            logger.debug(f"OpenAI multimodal response: {text[:100]}...")
            return text

        except Exception as e:
            logger.error(f"OpenAI multimodal error: {e}")
            raise LLMError(f"OpenAI multimodal call failed: {e}") from e

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
            response = await self.client.chat.completions.create(
                model=use_model,
                messages=cast(List[Any], messages),
                response_format={"type": "json_object"},  # type: ignore[arg-type]
            )
            content = response.choices[0].message.content
            result = content.strip() if content else ""
            logger.debug(f"OpenAI JSON response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"OpenAI chat_json error: {e}")
            raise LLMError(f"OpenAI API call failed: {e}") from e
