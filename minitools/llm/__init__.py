"""
LLM abstraction layer for minitools.
Provides a unified interface for different LLM providers.

LangChainベースの実装を優先使用し、ImportError時はネイティブクライアントにフォールバックします。
"""

from typing import Optional

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.llm.embeddings import (
    BaseEmbeddingClient,
    EmbeddingError,
    get_embedding_client,
)
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "BaseLLMClient",
    "LLMError",
    "get_llm_client",
    "BaseEmbeddingClient",
    "EmbeddingError",
    "get_embedding_client",
]


def _get_ollama_client(model: Optional[str] = None) -> BaseLLMClient:
    """
    Ollamaクライアントを取得（LangChain優先、フォールバックはネイティブ）

    Args:
        model: 使用するモデル名

    Returns:
        LLMクライアントインスタンス
    """
    try:
        from minitools.llm.langchain_ollama import LangChainOllamaClient

        logger.debug("Using LangChain Ollama client")
        return LangChainOllamaClient(model=model)
    except ImportError as e:
        logger.warning(
            f"LangChain not available ({e}), falling back to native Ollama client. "
            "Install LangChain with: uv sync"
        )
        from minitools.llm.ollama_client import OllamaClient

        return OllamaClient(model=model)


def _get_openai_client(model: Optional[str] = None) -> BaseLLMClient:
    """
    OpenAIクライアントを取得（LangChain優先、フォールバックはネイティブ）

    Args:
        model: 使用するモデル名

    Returns:
        LLMクライアントインスタンス
    """
    try:
        from minitools.llm.langchain_openai import LangChainOpenAIClient

        logger.debug("Using LangChain OpenAI client")
        return LangChainOpenAIClient(model=model)
    except ImportError as e:
        logger.warning(
            f"LangChain not available ({e}), falling back to native OpenAI client. "
            "Install LangChain with: uv sync"
        )
        try:
            from minitools.llm.openai_client import OpenAIClient

            return OpenAIClient(model=model)
        except ImportError:
            raise LLMError(
                "Neither LangChain nor native OpenAI client available. "
                "Install with: uv sync (LangChain) or uv add openai (native)"
            )


def _get_gemini_client(
    model: Optional[str] = None,
    thinking_level: Optional[str] = None,
) -> BaseLLMClient:
    """
    Geminiクライアントを取得（LangChain経由）

    Args:
        model: 使用するモデル名
        thinking_level: Gemini 3系の思考深度（"minimal" / "low" / "medium" / "high"）

    Returns:
        LLMクライアントインスタンス
    """
    try:
        from minitools.llm.langchain_gemini import LangChainGeminiClient

        logger.debug("Using LangChain Gemini client")
        return LangChainGeminiClient(model=model, thinking_level=thinking_level)
    except ImportError as e:
        raise LLMError(
            f"langchain-google-genai not available ({e}). "
            "Install with: uv add langchain-google-genai"
        )


def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    thinking_level: Optional[str] = None,
) -> BaseLLMClient:
    """
    LLMクライアントを取得するファクトリ関数

    LangChainベースの実装を優先使用し、ImportError時はネイティブクライアントにフォールバックします。

    Args:
        provider: LLMプロバイダー名（"ollama", "openai", "gemini"）
                  省略時は設定ファイルから取得
        model: 使用するモデル名（省略時は各プロバイダーのデフォルトを使用）
        thinking_level: Gemini 3系の思考深度。Gemini 利用時のみ有効
                        （OpenAI / Ollama では無視）

    Returns:
        LLMクライアントインスタンス

    Raises:
        ValueError: 未対応のプロバイダーが指定された場合
        LLMError: クライアントの初期化に失敗した場合
    """
    config = get_config()
    use_provider = provider or config.get("llm.provider", "ollama")

    logger.info(
        f"Creating LLM client: provider={use_provider}, model={model}, "
        f"thinking_level={thinking_level}"
    )

    if use_provider == "ollama":
        return _get_ollama_client(model=model)

    elif use_provider == "openai":
        try:
            return _get_openai_client(model=model)
        except ValueError as e:
            logger.warning(
                f"OpenAI initialization failed: {e}. Falling back to Ollama."
            )
            return _get_ollama_client(model=model)

    elif use_provider == "gemini":
        return _get_gemini_client(model=model, thinking_level=thinking_level)

    else:
        raise ValueError(
            f"Unsupported LLM provider: {use_provider}. "
            f"Supported providers: ollama, openai, gemini"
        )
