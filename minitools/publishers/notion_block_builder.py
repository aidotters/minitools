"""
Markdown to Notion block converter.
Converts translated Markdown into Notion API block format.
"""

import re
from typing import Any, Dict, List

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# Notion APIのrich_textの最大文字数
NOTION_TEXT_LIMIT = 2000


class NotionBlockBuilder:
    """翻訳済みMarkdownをNotionブロック形式に変換するクラス"""

    def build_blocks(self, markdown: str) -> List[Dict[str, Any]]:
        """
        Markdown文字列をNotionブロックのリストに変換する

        Args:
            markdown: 翻訳済みのMarkdown文字列

        Returns:
            Notionブロック形式の辞書のリスト
        """
        if not markdown or not markdown.strip():
            return []

        blocks: List[Dict[str, Any]] = []

        # 先頭にdividerを追加
        blocks.append(self._build_divider_block())

        lines = markdown.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # 空行はスキップ
            if not line.strip():
                i += 1
                continue

            # コードブロック
            if line.strip().startswith("```"):
                code_blocks, i = self._parse_code_block(lines, i)
                blocks.extend(code_blocks)
                continue

            # 見出し
            heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                blocks.append(self._build_heading_block(text, level))
                i += 1
                continue

            # 画像
            image_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", line.strip())
            if image_match:
                caption = image_match.group(1)
                url = image_match.group(2)
                if url.startswith(("http://", "https://")):
                    blocks.append(self._build_image_block(url))
                else:
                    # 相対パスやローカルパスの画像はキャプション段落に変換
                    if caption:
                        blocks.append(
                            self._build_paragraph_block(f"*[Image: {caption}]*")
                        )
                    else:
                        logger.debug(f"Skipping non-URL image: {url}")
                i += 1
                continue

            # 箇条書きリスト
            bullet_match = re.match(r"^[-*]\s+(.+)$", line)
            if bullet_match:
                text = bullet_match.group(1)
                blocks.append(self._build_list_block(text, ordered=False))
                i += 1
                continue

            # 番号付きリスト
            numbered_match = re.match(r"^\d+\.\s+(.+)$", line)
            if numbered_match:
                text = numbered_match.group(1)
                blocks.append(self._build_list_block(text, ordered=True))
                i += 1
                continue

            # 引用
            if line.startswith("> "):
                quote_lines: List[str] = []
                while i < len(lines) and lines[i].startswith("> "):
                    quote_lines.append(lines[i][2:])
                    i += 1
                text = "\n".join(quote_lines)
                blocks.append(self._build_quote_block(text))
                continue

            # 水平線
            if line.strip() in ("---", "***", "___"):
                blocks.append(self._build_divider_block())
                i += 1
                continue

            # イタリック行（キャプション等）
            italic_match = re.match(r"^\*([^*]+)\*$", line.strip())
            if italic_match:
                text = italic_match.group(1)
                blocks.append(self._build_paragraph_block(f"*{text}*"))
                i += 1
                continue

            # 通常の段落
            blocks.append(self._build_paragraph_block(line))
            i += 1

        return blocks

    def _parse_code_block(
        self, lines: List[str], start: int
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        コードブロックを解析する

        コードが2000文字を超える場合は複数のコードブロックに分割する。

        Args:
            lines: 全行のリスト
            start: コードブロック開始行のインデックス

        Returns:
            (Notionブロックのリスト, 次の行のインデックス)のタプル
        """
        first_line = lines[start].strip()
        # 言語を抽出
        language = first_line[3:].strip() if len(first_line) > 3 else "plain text"

        code_lines: List[str] = []
        i = start + 1

        while i < len(lines):
            if lines[i].strip() == "```":
                i += 1
                break
            code_lines.append(lines[i])
            i += 1

        code = "\n".join(code_lines)

        # 2000文字以下ならそのまま1ブロック
        if len(code) <= NOTION_TEXT_LIMIT:
            return [self._build_code_block(code, language)], i

        # 2000文字超の場合、行単位で分割して複数ブロックに
        blocks: List[Dict[str, Any]] = []
        current_lines: List[str] = []
        current_len = 0

        for code_line in code_lines:
            # +1 は改行文字分
            line_len = len(code_line) + (1 if current_lines else 0)
            if current_len + line_len > NOTION_TEXT_LIMIT and current_lines:
                blocks.append(
                    self._build_code_block("\n".join(current_lines), language)
                )
                current_lines = []
                current_len = 0
            current_lines.append(code_line)
            current_len += line_len

        if current_lines:
            blocks.append(self._build_code_block("\n".join(current_lines), language))

        return blocks, i

    # Markdownインライン書式のパターン
    _INLINE_PATTERN = re.compile(
        r"`([^`]+)`"  # inline code: `text`
        r"|\[([^\]]+)\]\(([^)]+)\)"  # link: [text](url)
        r"|\*\*(.+?)\*\*"  # bold: **text**
        r"|(?<!\*)\*([^*]+?)\*(?!\*)"  # italic: *text* (not inside bold)
    )

    def _build_rich_text(self, text: str) -> List[Dict[str, Any]]:
        """
        テキストからNotionのrich_textオブジェクトを構築する

        Markdownのインライン書式（太字、斜体、インラインコード、リンク）を
        Notionのrich_text annotations/link形式に変換する。
        テキストが2000文字を超える場合は複数のrich_textに分割する。

        Args:
            text: テキスト文字列

        Returns:
            rich_textオブジェクトのリスト
        """
        if not text:
            return [{"type": "text", "text": {"content": ""}}]

        parts: List[Dict[str, Any]] = []
        pos = 0

        for match in self._INLINE_PATTERN.finditer(text):
            # マッチ前のプレーンテキストを追加
            if match.start() > pos:
                plain = text[pos : match.start()]
                parts.extend(self._build_plain_rich_text(plain))

            if match.group(1) is not None:
                # inline code: `text`
                parts.append(
                    {
                        "type": "text",
                        "text": {"content": match.group(1)},
                        "annotations": {"code": True},
                    }
                )
            elif match.group(2) is not None:
                # link: [text](url)
                link_url = match.group(3)
                if link_url.startswith(("http://", "https://")):
                    parts.append(
                        {
                            "type": "text",
                            "text": {
                                "content": match.group(2),
                                "link": {"url": link_url},
                            },
                        }
                    )
                else:
                    # 不正なURL（相対パス、アンカー等）はプレーンテキストにフォールバック
                    parts.extend(self._build_plain_rich_text(match.group(2)))
            elif match.group(4) is not None:
                # bold: **text**
                parts.append(
                    {
                        "type": "text",
                        "text": {"content": match.group(4)},
                        "annotations": {"bold": True},
                    }
                )
            elif match.group(5) is not None:
                # italic: *text*
                parts.append(
                    {
                        "type": "text",
                        "text": {"content": match.group(5)},
                        "annotations": {"italic": True},
                    }
                )

            pos = match.end()

        # 残りのプレーンテキストを追加
        if pos < len(text):
            parts.extend(self._build_plain_rich_text(text[pos:]))

        # マッチがなかった場合はプレーンテキスト全体
        if not parts:
            parts.extend(self._build_plain_rich_text(text))

        return parts

    def _build_plain_rich_text(self, text: str) -> List[Dict[str, Any]]:
        """
        プレーンテキストからNotionのrich_textオブジェクトを構築する

        Markdown書式の解析を行わず、2000文字制限のみ対応する。
        コードブロック内のテキストに使用する。

        Args:
            text: テキスト文字列

        Returns:
            rich_textオブジェクトのリスト
        """
        if not text:
            return [{"type": "text", "text": {"content": ""}}]

        # 2000文字制限対応
        chunks: List[str] = []
        while text:
            chunks.append(text[:NOTION_TEXT_LIMIT])
            text = text[NOTION_TEXT_LIMIT:]

        return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]

    def _build_heading_block(self, text: str, level: int) -> Dict[str, Any]:
        """見出しブロックを生成"""
        # Notionはheading_1, heading_2, heading_3のみサポート
        level = min(max(level, 1), 3)
        block_type = f"heading_{level}"
        return {
            "object": "block",
            "type": block_type,
            block_type: {"rich_text": self._build_rich_text(text)},
        }

    def _build_paragraph_block(self, text: str) -> Dict[str, Any]:
        """段落ブロックを生成"""
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": self._build_rich_text(text)},
        }

    def _build_code_block(
        self, code: str, language: str = "plain text"
    ) -> Dict[str, Any]:
        """コードブロックを生成"""
        # Notion APIの言語名にマッピング
        language_map = {
            "python": "python",
            "py": "python",
            "javascript": "javascript",
            "js": "javascript",
            "typescript": "typescript",
            "ts": "typescript",
            "java": "java",
            "go": "go",
            "rust": "rust",
            "c": "c",
            "cpp": "c++",
            "c++": "c++",
            "csharp": "c#",
            "c#": "c#",
            "ruby": "ruby",
            "rb": "ruby",
            "php": "php",
            "swift": "swift",
            "kotlin": "kotlin",
            "shell": "shell",
            "bash": "shell",
            "sh": "shell",
            "sql": "sql",
            "html": "html",
            "css": "css",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "xml": "xml",
            "markdown": "markdown",
            "md": "markdown",
            "r": "r",
            "scala": "scala",
            "": "plain text",
        }

        notion_language = language_map.get(language.lower(), "plain text")

        return {
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": self._build_plain_rich_text(code),
                "language": notion_language,
            },
        }

    def _build_image_block(self, url: str) -> Dict[str, Any]:
        """画像ブロックを生成"""
        return {
            "object": "block",
            "type": "image",
            "image": {
                "type": "external",
                "external": {"url": url},
            },
        }

    def _build_list_block(self, text: str, ordered: bool = False) -> Dict[str, Any]:
        """リストブロックを生成"""
        block_type = "numbered_list_item" if ordered else "bulleted_list_item"
        return {
            "object": "block",
            "type": block_type,
            block_type: {"rich_text": self._build_rich_text(text)},
        }

    def _build_quote_block(self, text: str) -> Dict[str, Any]:
        """引用ブロックを生成"""
        return {
            "object": "block",
            "type": "quote",
            "quote": {"rich_text": self._build_rich_text(text)},
        }

    def _build_divider_block(self) -> Dict[str, Any]:
        """区切り線ブロックを生成"""
        return {
            "object": "block",
            "type": "divider",
            "divider": {},
        }
