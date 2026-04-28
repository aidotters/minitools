"""
LangChain-based Google Gemini LLM client implementation.
Uses Google AI Studio (free tier) via langchain-google-genai.
"""

import base64
import os
from typing import Any, Dict, List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)


def _convert_messages(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """辞書形式のメッセージをLangChain形式に変換"""
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


class LangChainGeminiClient(BaseLLMClient):
    """LangChainを使用したGoogle Gemini LLMクライアント"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Args:
            api_key: Google AI Studio APIキー（省略時は環境変数から取得）
            model: 使用するGeminiモデル名（省略時は設定ファイルから取得）

        Raises:
            ValueError: APIキーが設定されていない場合
        """
        resolved_api_key = (
            api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
        if not resolved_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required. Set it in .env file or pass as argument."
            )
        self.api_key: str = resolved_api_key

        config = get_config()
        self.default_model = model or config.get(
            "llm.gemini.default_model", "gemini-2.5-flash"
        )
        self._chat_model: Optional[ChatGoogleGenerativeAI] = None
        logger.debug(
            f"LangChainGeminiClient initialized with model: {self.default_model}"
        )

    def _get_chat_model(
        self, model: Optional[str] = None, json_mode: bool = False
    ) -> ChatGoogleGenerativeAI:
        """ChatGoogleGenerativeAIインスタンスを取得"""
        use_model = model or self.default_model

        if json_mode:
            return ChatGoogleGenerativeAI(
                model=use_model,
                google_api_key=self.api_key,
                convert_system_message_to_human=True,
                max_output_tokens=65536,
                model_kwargs={
                    "response_mime_type": "application/json",
                    "thinking_config": {"thinking_budget": 0},
                },
            )

        if self._chat_model is not None and self._chat_model.model == use_model:
            return self._chat_model

        self._chat_model = ChatGoogleGenerativeAI(
            model=use_model,
            google_api_key=self.api_key,
            convert_system_message_to_human=True,
            max_output_tokens=65536,
            model_kwargs={"thinking_config": {"thinking_budget": 0}},
        )
        return self._chat_model

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """メッセージを送信してレスポンスを取得"""
        try:
            chat_model = self._get_chat_model(model)
            langchain_messages = _convert_messages(messages)

            response = await chat_model.ainvoke(langchain_messages)
            content = response.content
            result = str(content).strip() if content else ""
            logger.debug(f"LangChain Gemini response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LangChain Gemini chat error: {e}")
            raise LLMError(f"LangChain Gemini API call failed: {e}") from e

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """プロンプトからテキスト生成"""
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
                        "image_url": f"data:{mime_type};base64,{b64}",
                    }
                )
            message = HumanMessage(content=content)  # type: ignore[arg-type]

            response = await chat_model.ainvoke([message])
            result = str(response.content).strip() if response.content else ""
            logger.debug(f"LangChain Gemini multimodal response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LangChain Gemini multimodal error: {e}")
            raise LLMError(f"LangChain Gemini multimodal call failed: {e}") from e

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """JSON形式のレスポンスを取得"""
        try:
            chat_model = self._get_chat_model(model, json_mode=True)
            langchain_messages = _convert_messages(messages)

            response = await chat_model.ainvoke(langchain_messages)
            content = response.content
            result = str(content).strip() if content else ""
            logger.debug(f"LangChain Gemini JSON response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LangChain Gemini chat_json error: {e}")
            raise LLMError(f"LangChain Gemini API call failed: {e}") from e
