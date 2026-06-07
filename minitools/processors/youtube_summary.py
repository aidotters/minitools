"""
YouTube 文字起こしから日本語の要約文＋ポイント箇条書きを生成する processor。

LLM プロバイダは get_llm_client 経由で切替可能（デフォルトは settings の
`defaults.youtube_mail_digest`、未設定時は Gemini）。
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import List, Optional

from minitools.llm import BaseLLMClient, get_llm_client
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# 1回の要約に渡す文字起こしの最大文字数（超過分は末尾を切り詰め）
DEFAULT_MAX_INPUT_CHARS = 24000

_SUMMARY_HEADER = "【要約】"
_POINTS_HEADER = "【ポイント】"


@dataclass
class Summary:
    """要約結果"""

    text: str
    points: List[str] = field(default_factory=list)


def _parse_summary_response(response: str) -> Summary:
    """
    LLM 応答から要約文とポイント箇条書きを抽出する。

    期待フォーマット:
        【要約】
        （数文の要約）

        【ポイント】
        - ポイント1
        - ポイント2

    フォーマットが崩れている場合も可能な範囲で救済する。
    """
    if not response:
        return Summary(text="", points=[])

    text = response.strip()
    summary_part = text
    points_part = ""

    if _POINTS_HEADER in text:
        before, after = text.split(_POINTS_HEADER, 1)
        summary_part = before
        points_part = after

    # 要約見出しを除去
    summary_part = summary_part.replace(_SUMMARY_HEADER, "").strip()

    points: List[str] = []
    for line in points_part.splitlines():
        line = line.strip()
        if not line:
            continue
        # 箇条書き記号や番号を除去
        cleaned = re.sub(r"^[\-\*・•]\s*", "", line)
        cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            points.append(cleaned)

    return Summary(text=summary_part, points=points)


class YouTubeSummarizer:
    """文字起こしから要約文＋ポイントを生成するクラス"""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        thinking_level: Optional[str] = None,
        llm_client: Optional[BaseLLMClient] = None,
        max_retries: int = 3,
        max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
    ):
        config = get_config()
        self.max_retries = max_retries
        self.max_input_chars = max_input_chars

        if llm_client is not None:
            self.client = llm_client
        else:
            use_provider = provider or config.get(
                "defaults.youtube_mail_digest.provider", "gemini"
            )
            use_model = model or config.get("defaults.youtube_mail_digest.model", None)
            use_thinking = thinking_level or config.get(
                "defaults.youtube_mail_digest.thinking_level", "minimal"
            )
            self.client = get_llm_client(
                provider=use_provider,
                model=use_model,
                thinking_level=use_thinking,
            )

    def _build_prompt(self, transcript: str, title: str) -> str:
        trimmed = transcript[: self.max_input_chars]
        title_line = f"動画タイトル: {title}\n\n" if title else ""
        return (
            "以下は YouTube 動画の文字起こしです。日本語で要約してください。\n"
            "次のフォーマットを厳密に守って出力してください:\n\n"
            "【要約】\n"
            "（動画全体の内容を3〜5文で要約）\n\n"
            "【ポイント】\n"
            "- （重要ポイント1）\n"
            "- （重要ポイント2）\n"
            "（重要ポイントは3〜7個、各1行の箇条書き）\n\n"
            f"{title_line}"
            "--- 文字起こし ---\n"
            f"{trimmed}\n"
            "--- ここまで ---"
        )

    async def summarize(self, transcript: str, title: str = "") -> Summary:
        """
        文字起こしから要約文＋ポイントを生成する。

        Args:
            transcript: 文字起こしテキスト
            title: 動画タイトル（プロンプト補助）

        Returns:
            Summary(text, points)。生成失敗時は空の Summary。
        """
        if not transcript or not transcript.strip():
            logger.warning("空の文字起こしのため要約をスキップ")
            return Summary(text="", points=[])

        prompt = self._build_prompt(transcript, title)

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = await self.client.generate(prompt)
                summary = _parse_summary_response(response)
                if summary.text or summary.points:
                    return summary
                logger.warning(
                    f"要約応答が空（attempt {attempt + 1}/{self.max_retries}）"
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"要約生成エラー（attempt {attempt + 1}/{self.max_retries}）: {e}"
                )
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2**attempt)  # 1, 2, 4秒

        if last_error:
            logger.error(f"要約生成に失敗しました: {last_error}")
        return Summary(text="", points=[])
