"""
Translation processor using Ollama.
"""

import json
import asyncio
from typing import Optional, Dict
import ollama

from minitools.utils.logger import get_logger
from minitools.utils.config import get_config

logger = get_logger(__name__)


class Translator:
    """テキストを翻訳するクラス"""

    def __init__(self, model: Optional[str] = None):
        """
        Args:
            model: 使用するOllamaモデル名（指定しない場合は設定ファイルから取得）
        """
        config = get_config()
        self.model = model or config.get("models.translation", "gemma3:27b")
        self.client = ollama.Client()
        logger.info(f"Translator initialized (provider=ollama, model={self.model})")

    async def translate_to_japanese(self, text: str, context: str = "") -> str:
        """
        テキストを日本語に翻訳

        Args:
            text: 翻訳するテキスト
            context: 追加のコンテキスト情報

        Returns:
            翻訳されたテキスト
        """
        if not text:
            return ""

        prompt = f"""以下のテキストを日本語に翻訳してください。
自然で読みやすい日本語にしてください。

{f"コンテキスト: {context}" if context else ""}

テキスト:
{text}

日本語訳:"""

        try:
            # Ollamaは同期APIなので、executorで実行
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=self.model, messages=[{"role": "user", "content": prompt}]
                ),
            )

            content = response.message.content or ""
            translation = content.strip()
            logger.debug(f"Translated text: {translation[:100]}...")
            return translation

        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text  # エラー時は元のテキストを返す

    async def translate_with_summary(
        self, title: str, content: str, author: str = ""
    ) -> Dict[str, str]:
        """
        タイトルと内容を翻訳し、要約も生成

        Args:
            title: 記事のタイトル
            content: 記事の内容
            author: 著者名（オプション）

        Returns:
            翻訳されたタイトルと要約を含む辞書
        """
        prompt = f"""You are a professional translator and summarizer. Respond in JSON format.

Translate the following article title to Japanese and summarize the article text in Japanese (around 200 characters).

Original Title: {title}
{f"Author: {author}" if author else ""}

Article Text:
{content[:3000]}

---

Respond with a JSON object with two keys: 'japanese_title' and 'japanese_summary'.
Example:
{{
  "japanese_title": "ここに日本語のタイトル",
  "japanese_summary": "ここに日本語の要約"
}}
"""

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    format="json",
                ),
            )

            content = response.message.content or "{}"
            result = json.loads(content)
            logger.info(f"Translated and summarized: {title[:50]}...")
            return {
                "japanese_title": result.get("japanese_title", "翻訳失敗"),
                "japanese_summary": result.get("japanese_summary", "要約失敗"),
            }

        except Exception as e:
            logger.error(f"Translation/summary error for '{title}': {e}")
            return {
                "japanese_title": "翻訳失敗",
                "japanese_summary": "要約の生成に失敗しました",
            }
