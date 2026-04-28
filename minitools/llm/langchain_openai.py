"""
LangChain-based OpenAI LLM client implementation.
"""

import base64
import os
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from pydantic import SecretStr

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)


def _convert_messages(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """
    辞書形式のメッセージをLangChain形式に変換

    Args:
        messages: チャットメッセージのリスト
                  各メッセージは {"role": "user"|"assistant"|"system", "content": "..."}

    Returns:
        LangChain形式のメッセージリスト
    """
    langchain_messages: List[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            langchain_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            langchain_messages.append(AIMessage(content=content))
        else:
            langchain_messages.append(HumanMessage(content=content))

    return langchain_messages


class LangChainOpenAIClient(BaseLLMClient):
    """LangChainを使用したOpenAI LLMクライアント"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Args:
            api_key: OpenAI APIキー（省略時は環境変数から取得）
            model: 使用するOpenAIモデル名（省略時は設定ファイルから取得）

        Raises:
            ValueError: APIキーが設定されていない場合
        """
        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. Set it in .env file or pass as argument."
            )
        self.api_key: str = resolved_api_key

        config = get_config()
        self.default_model = model or config.get("llm.openai.default_model", "gpt-4o")
        self._chat_model: Optional[ChatOpenAI] = None
        logger.debug(
            f"LangChainOpenAIClient initialized with model: {self.default_model}"
        )

    def _get_chat_model(
        self, model: Optional[str] = None, json_mode: bool = False
    ) -> ChatOpenAI:
        """
        ChatOpenAIインスタンスを取得

        Args:
            model: 使用するモデル名
            json_mode: JSON出力モードを有効にするか

        Returns:
            ChatOpenAIインスタンス
        """
        use_model = model or self.default_model

        # APIキーをSecretStrに変換
        api_key_secret = SecretStr(self.api_key)

        # JSON modeの場合は毎回新規作成
        if json_mode:
            return ChatOpenAI(
                model=use_model,
                api_key=api_key_secret,
                model_kwargs={"response_format": {"type": "json_object"}},
            )

        # キャッシュされたモデルが同じなら再利用
        if self._chat_model is not None and self._chat_model.model_name == use_model:
            return self._chat_model

        self._chat_model = ChatOpenAI(model=use_model, api_key=api_key_secret)
        return self._chat_model

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
        try:
            chat_model = self._get_chat_model(model)
            langchain_messages = _convert_messages(messages)

            response = await chat_model.ainvoke(langchain_messages)
            content = response.content
            result = str(content).strip() if content else ""
            logger.debug(f"LangChain OpenAI response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LangChain OpenAI chat error: {e}")
            raise LLMError(f"LangChain OpenAI API call failed: {e}") from e

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
        try:
            chat_model = self._get_chat_model(model)
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
            message = HumanMessage(content=content)  # type: ignore[arg-type]

            response = await chat_model.ainvoke([message])
            result = str(response.content).strip() if response.content else ""
            logger.debug(f"LangChain OpenAI multimodal response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LangChain OpenAI multimodal error: {e}")
            raise LLMError(f"LangChain OpenAI multimodal call failed: {e}") from e

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
        try:
            chat_model = self._get_chat_model(model, json_mode=True)
            langchain_messages = _convert_messages(messages)

            response = await chat_model.ainvoke(langchain_messages)
            content = response.content
            result = str(content).strip() if content else ""
            logger.debug(f"LangChain OpenAI JSON response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LangChain OpenAI chat_json error: {e}")
            raise LLMError(f"LangChain OpenAI API call failed: {e}") from e
