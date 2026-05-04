"""
Content summarization processor using Ollama.
"""

import asyncio
from typing import Optional
import ollama

from minitools.utils.logger import get_logger
from minitools.utils.config import get_config

logger = get_logger(__name__)


class Summarizer:
    """コンテンツを要約するクラス"""

    def __init__(self, model: Optional[str] = None):
        """
        Args:
            model: 使用するOllamaモデル名（指定しない場合は設定ファイルから取得）
        """
        config = get_config()
        self.model = model or config.get("models.summarization", "gemma3:27b")
        self.client = ollama.Client()
        logger.info(f"Summarizer initialized (provider=ollama, model={self.model})")

    async def summarize(
        self, text: str, max_length: int = 200, language: str = "japanese"
    ) -> str:
        """
        テキストを要約

        Args:
            text: 要約するテキスト
            max_length: 要約の最大文字数
            language: 要約の言語（japanese/english）

        Returns:
            要約されたテキスト
        """
        if not text:
            return ""

        lang_instruction = "日本語で" if language == "japanese" else "in English"

        prompt = f"""以下の文章を{lang_instruction}要約してください。
要約は{max_length}文字程度にまとめてください。
重要なポイントを含めて、簡潔にまとめてください。

文章:
{text}

要約:"""

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=self.model, messages=[{"role": "user", "content": prompt}]
                ),
            )

            content = response.message.content or ""
            summary = content.strip()
            logger.debug(f"Generated summary: {summary[:100]}...")
            return summary

        except Exception as e:
            logger.error(f"Summarization error: {e}")
            return "要約の生成に失敗しました"

    async def extract_key_points(self, text: str, num_points: int = 5) -> list[str]:
        """
        テキストから重要ポイントを抽出

        Args:
            text: 分析するテキスト
            num_points: 抽出するポイント数

        Returns:
            重要ポイントのリスト
        """
        if not text:
            return []

        prompt = f"""以下の文章から最も重要な{num_points}つのポイントを箇条書きで抽出してください。
各ポイントは簡潔に1行でまとめてください。

文章:
{text}

重要ポイント:"""

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=self.model, messages=[{"role": "user", "content": prompt}]
                ),
            )

            # レスポンスを行ごとに分割してリスト化
            points = []
            content = response.message.content or ""
            for line in content.strip().split("\n"):
                line = line.strip()
                if line and (
                    line.startswith("・")
                    or line.startswith("-")
                    or line.startswith("*")
                    or line[0].isdigit()
                ):
                    # 箇条書き記号を削除
                    clean_line = line.lstrip("・-*0123456789. ")
                    if clean_line:
                        points.append(clean_line)

            logger.info(f"Extracted {len(points)} key points")
            return points[:num_points]  # 指定数までに制限

        except Exception as e:
            logger.error(f"Key point extraction error: {e}")
            return []
