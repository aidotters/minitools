"""
LangChain-based Ollama LLM client implementation.
"""

from typing import Dict, List, Optional

from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

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


class LangChainOllamaClient(BaseLLMClient):
    """LangChainを使用したOllama LLMクライアント"""

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
        self._chat_model: Optional[ChatOllama] = None
        logger.debug(
            f"LangChainOllamaClient initialized with model: {self.default_model}"
        )

    def _get_chat_model(self, model: Optional[str] = None) -> ChatOllama:
        """
        ChatOllamaインスタンスを取得

        Args:
            model: 使用するモデル名

        Returns:
            ChatOllamaインスタンス
        """
        use_model = model or self.default_model

        # キャッシュされたモデルが同じなら再利用
        if self._chat_model is not None and self._chat_model.model == use_model:
            return self._chat_model

        self._chat_model = ChatOllama(model=use_model)
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

            # LangChainのainvokeを使用
            response = await chat_model.ainvoke(langchain_messages)
            content = response.content
            result = str(content).strip() if content else ""
            logger.debug(f"LangChain Ollama response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LangChain Ollama chat error: {e}")
            raise LLMError(f"LangChain Ollama API call failed: {e}") from e

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
            "LangChainOllamaClient does not support multimodal generation in this build. "
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
        try:
            use_model = model or self.default_model

            # JSON出力用にformat指定したChatOllamaを作成
            chat_model = ChatOllama(model=use_model, format="json")
            langchain_messages = _convert_messages(messages)

            response = await chat_model.ainvoke(langchain_messages)
            content = response.content
            result = str(content).strip() if content else ""
            logger.debug(f"LangChain Ollama JSON response: {result[:100]}...")
            return result

        except Exception as e:
            logger.error(f"LangChain Ollama chat_json error: {e}")
            raise LLMError(f"LangChain Ollama API call failed: {e}") from e
