"""
Base class for LLM clients.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseLLMClient(ABC):
    """LLMクライアントの抽象基底クラス"""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """
        メッセージを送信してレスポンスを取得

        Args:
            messages: チャットメッセージのリスト
                      各メッセージは {"role": "user"|"assistant"|"system", "content": "..."}
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            LLMからのレスポンステキスト
        """
        pass

    @abstractmethod
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
        """
        pass

    async def generate_from_images(
        self,
        prompt: str,
        images: List[bytes],
        mime_type: str = "image/png",
        model: Optional[str] = None,
    ) -> str:
        """
        画像とプロンプトからテキスト生成（multimodal）

        デフォルト実装は warning を出して空文字列を返す（multimodal 未対応プロバイダ向け）。
        対応プロバイダではこのメソッドをオーバーライドする。

        Args:
            prompt: 生成のためのプロンプト
            images: 画像バイト列のリスト
            mime_type: 画像のMIMEタイプ（"image/png" or "image/jpeg"）
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            生成されたテキスト（未対応時は空文字列）
        """
        from minitools.utils.logger import get_logger

        logger = get_logger(__name__)
        logger.warning(
            f"{self.__class__.__name__} does not support multimodal generation. "
            "Returning empty string."
        )
        return ""


class LLMError(Exception):
    """LLM API呼び出しエラー"""

    pass
