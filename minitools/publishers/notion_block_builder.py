"""
Markdown to Notion block converter.
Converts translated Markdown into Notion API block format.
"""

import re
from typing import Any, Dict, List, Optional

from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# Notion APIのrich_textの最大文字数
NOTION_TEXT_LIMIT = 2000


class NotionBlockBuilder:
    """翻訳済みMarkdownをNotionブロック形式に変換するクラス"""

    def build_blocks(
        self,
        markdown: str,
        image_uploads: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Markdown文字列をNotionブロックのリストに変換する

        Args:
            markdown: 翻訳済みのMarkdown文字列
            image_uploads: ローカル画像ファイル名→file_upload_id のマッピング。
                Noneまたは空辞書の場合、ローカル画像はキャプション段落にフォールバック。

        Returns:
            Notionブロック形式の辞書のリスト
        """
        if not markdown or not markdown.strip():
            return []

        # 前処理: 不要な HTML タグ（pseudo-anchor 等）を除去
        markdown = self._strip_inline_html(markdown)
        # LLM が誤って ```markdown ... ``` で囲んだ翻訳結果を除去
        markdown = self._unwrap_translation_code_fences(markdown)

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

            # ブロック数式 $$...$$
            stripped = line.strip()
            if stripped.startswith("$$"):
                eq_blocks, i = self._parse_block_equation(lines, i)
                blocks.extend(eq_blocks)
                continue

            # コードブロック
            if stripped.startswith("```"):
                code_blocks, i = self._parse_code_block(lines, i)
                blocks.extend(code_blocks)
                continue

            # テーブル（次行が |---|---| 形式）
            if (
                line.lstrip().startswith("|")
                and i + 1 < len(lines)
                and self._is_table_separator(lines[i + 1])
            ):
                table_block, i = self._parse_table(lines, i)
                blocks.append(table_block)
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
                    blocks.append(self._build_image_block(url=url, caption=caption))
                elif image_uploads and url in image_uploads:
                    # ローカル画像でfile_upload_idが用意されている
                    blocks.append(
                        self._build_image_block(
                            file_upload_id=image_uploads[url], caption=caption
                        )
                    )
                else:
                    # マッピング無しの場合はキャプション段落にフォールバック
                    if caption:
                        blocks.append(
                            self._build_paragraph_block(f"*[Image: {caption}]*")
                        )
                    else:
                        logger.debug(f"Skipping non-URL image: {url}")
                i += 1
                continue

            # 箇条書きリスト（- * • のいずれか、インデント許容）
            bullet_match = re.match(r"^\s*[-*•]\s+(.+)$", line)
            if bullet_match:
                text = bullet_match.group(1)
                # `- 1. xxx` のような bullet+番号の混在は番号付きリストへ再分類
                renumbered = re.match(r"^(\d+)\.\s+(.+)$", text)
                if renumbered:
                    blocks.append(
                        self._build_list_block(renumbered.group(2), ordered=True)
                    )
                else:
                    blocks.append(self._build_list_block(text, ordered=False))
                i += 1
                continue

            # 番号付きリスト
            numbered_match = re.match(r"^\s*\d+\.\s+(.+)$", line)
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

    def _parse_block_equation(
        self, lines: List[str], start: int
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        ブロック数式 $$...$$ を解析する

        1 行内で閉じた `$$...$$` と複数行にまたがる `$$...$$` の両方に対応する。

        Args:
            lines: 全行のリスト
            start: ブロック数式開始行のインデックス

        Returns:
            (Notion equation blockを含むリスト, 次の行のインデックス)
        """
        first_line = lines[start].strip()

        # 1行内で閉じているパターン: $$...$$
        if first_line.count("$$") >= 2:
            # 最初の $$ と最後の $$ で切り出す
            inner = first_line[2:]
            end_idx = inner.rfind("$$")
            if end_idx >= 0:
                expression = inner[:end_idx].strip()
                if not expression:
                    # 空 expression（$$$$ や $$ $$ 等）は paragraph フォールバック
                    return [self._build_paragraph_block(first_line)], start + 1
                return [self._build_equation_block(expression)], start + 1

        # 複数行パターン: $$ から始まり、後続の $$ で閉じる
        # 最初の行に $$ 以降の内容があればそれも含める
        expr_lines: List[str] = []
        first_content = first_line[2:].strip()
        if first_content:
            expr_lines.append(first_content)

        i = start + 1
        closed = False
        while i < len(lines):
            current = lines[i]
            if "$$" in current:
                # 終端 $$ が見つかった
                end_idx = current.find("$$")
                before = current[:end_idx].rstrip()
                if before:
                    expr_lines.append(before)
                i += 1
                closed = True
                break
            expr_lines.append(current)
            i += 1

        if not closed:
            # 閉じタグが見つからない場合は段落フォールバック
            logger.warning("Unclosed block equation, treating as paragraph")
            return [self._build_paragraph_block(lines[start])], start + 1

        expression = "\n".join(expr_lines).strip()
        if not expression:
            # 空 expression は paragraph フォールバック
            return [self._build_paragraph_block(lines[start])], start + 1
        return [self._build_equation_block(expression)], i

    def _is_table_separator(self, line: str) -> bool:
        """|---|---| 形式の区切り行かチェックする"""
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            return False
        # 内側のセル群が - や : のみで構成されているか
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells:
            return False
        return all(re.fullmatch(r":?-+:?", c) for c in cells if c)

    def _parse_table_row(self, line: str) -> List[str]:
        """`| a | b | c |` 形式の行からセル文字列のリストを抽出する"""
        stripped = line.strip()
        # 先頭・末尾の | を除去
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        return [c.strip() for c in stripped.split("|")]

    def _parse_table(self, lines: List[str], start: int) -> tuple[Dict[str, Any], int]:
        """
        Markdownテーブルを解析する

        start 行目がヘッダー行、start+1 行目が区切り行、start+2 以降がデータ行。
        データ行が全て空セルしか持たない（caption-only テーブル等）の場合は
        段落フォールバックを返す。

        Args:
            lines: 全行のリスト
            start: テーブル開始行（ヘッダー行）のインデックス

        Returns:
            (Notion block, 次の行のインデックス)
        """
        header_cells = self._parse_table_row(lines[start])
        # 区切り行をスキップ
        i = start + 2

        data_rows: List[List[str]] = []
        while i < len(lines):
            line = lines[i]
            if not line.lstrip().startswith("|"):
                break
            # 区切り行はスキップ（誤検出防止）
            if self._is_table_separator(line):
                i += 1
                continue
            row = self._parse_table_row(line)
            # 全セルが空の行はスキップ（PDF 抽出時のダミー行）
            if any(cell.strip() for cell in row):
                data_rows.append(row)
            i += 1

        # データ行が無く、ヘッダーも実質1セルしか中身がない場合は
        # caption とみなして段落へフォールバック
        non_empty_header = [c for c in header_cells if c.strip()]
        if not data_rows and len(non_empty_header) <= 1:
            text = " ".join(non_empty_header).strip()
            if text:
                return self._build_paragraph_block(text), i
            # 完全に空のテーブルは divider にフォールバック
            return self._build_divider_block(), i

        return self._build_table_block(header_cells, data_rows), i

    # テーブルセル内の <br> 系タグ（Notion rich_text は改行を \n で表す）
    _CELL_BR_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)

    @classmethod
    def _normalize_cell(cls, cell: str) -> str:
        """セル文字列内の <br> を改行に置換する"""
        return cls._CELL_BR_PATTERN.sub("\n", cell)

    def _build_cell_rich_text(self, cell: str) -> List[Dict[str, Any]]:
        """セル文字列を rich_text に変換する（<br> を改行として扱う）"""
        normalized = self._normalize_cell(cell)
        if "\n" not in normalized:
            return self._build_rich_text(normalized)

        parts: List[Dict[str, Any]] = []
        segments = normalized.split("\n")
        for idx, seg in enumerate(segments):
            if seg:
                parts.extend(self._build_rich_text(seg))
            if idx < len(segments) - 1:
                parts.append({"type": "text", "text": {"content": "\n"}})
        if not parts:
            parts.append({"type": "text", "text": {"content": ""}})
        return parts

    def _build_table_block(
        self, header_cells: List[str], data_rows: List[List[str]]
    ) -> Dict[str, Any]:
        """Notion table block を生成する"""
        width = len(header_cells)

        def _cells_to_rich_text(cells: List[str]) -> List[List[Dict[str, Any]]]:
            # セル数が不足している場合はヘッダー幅に合わせて padding
            padded = list(cells) + [""] * (width - len(cells))
            padded = padded[:width]
            return [self._build_cell_rich_text(c) for c in padded]

        children: List[Dict[str, Any]] = []
        children.append(
            {
                "object": "block",
                "type": "table_row",
                "table_row": {"cells": _cells_to_rich_text(header_cells)},
            }
        )
        for row in data_rows:
            children.append(
                {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {"cells": _cells_to_rich_text(row)},
                }
            )

        return {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": width,
                "has_column_header": True,
                "has_row_header": False,
                "children": children,
            },
        }

    def _build_equation_block(self, expression: str) -> Dict[str, Any]:
        """ブロック数式を生成"""
        return {
            "object": "block",
            "type": "equation",
            "equation": {"expression": expression},
        }

    # Markdownインライン書式のパターン
    # 順序重要: inline code → link → equation → bold → italic
    _INLINE_PATTERN = re.compile(
        r"`([^`]+)`"  # group 1: inline code
        r"|\[([^\]]+)\]\(([^)]+)\)"  # groups 2,3: link
        r"|(?<!\\)\$([^$\n]+?)(?<!\\)\$"  # group 4: inline equation
        r"|\*\*(.+?)\*\*"  # group 5: bold
        r"|(?<!\*)\*([^*]+?)\*(?!\*)"  # group 6: italic
    )

    def _build_rich_text(self, text: str) -> List[Dict[str, Any]]:
        """
        テキストからNotionのrich_textオブジェクトを構築する

        Markdownのインライン書式（太字、斜体、インラインコード、リンク、数式）を
        Notionのrich_text annotations/link/equation形式に変換する。
        テキストが2000文字を超える場合は複数のrich_textに分割する。

        Args:
            text: テキスト文字列

        Returns:
            rich_textオブジェクトのリスト
        """
        if not text:
            return [{"type": "text", "text": {"content": ""}}]

        # インライン処理の前に、bold 内の数式を先に展開する
        # **$x$** のようなケースで bold と equation の両立は Notion rich_text の
        # 単一 annotation モデル上困難。本実装では数式優先で扱う
        # （bold 記号を外した上で equation に変換）
        text = self._unwrap_bold_around_equation(text)

        parts: List[Dict[str, Any]] = []
        pos = 0

        for match in self._INLINE_PATTERN.finditer(text):
            # マッチ前のプレーンテキストを追加
            if match.start() > pos:
                plain = text[pos : match.start()]
                parts.extend(self._build_plain_rich_text(self._unescape_dollar(plain)))

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
                # inline equation: $expr$
                parts.append(
                    {
                        "type": "equation",
                        "equation": {"expression": match.group(4)},
                    }
                )
            elif match.group(5) is not None:
                # bold: **text**
                parts.append(
                    {
                        "type": "text",
                        "text": {"content": match.group(5)},
                        "annotations": {"bold": True},
                    }
                )
            elif match.group(6) is not None:
                # italic: *text*
                parts.append(
                    {
                        "type": "text",
                        "text": {"content": match.group(6)},
                        "annotations": {"italic": True},
                    }
                )

            pos = match.end()

        # 残りのプレーンテキストを追加
        if pos < len(text):
            parts.extend(self._build_plain_rich_text(self._unescape_dollar(text[pos:])))

        # マッチがなかった場合はプレーンテキスト全体
        if not parts:
            parts.extend(self._build_plain_rich_text(self._unescape_dollar(text)))

        return parts

    @staticmethod
    def _unescape_dollar(text: str) -> str:
        """エスケープされた \\$ を通常の $ に戻す"""
        return text.replace("\\$", "$")

    # 行内に出現するノイズ HTML タグ（marker-pdf が PDF アンカー等で残すもの）
    _STRIP_HTML_PATTERN = re.compile(
        r"<span\b[^>]*>.*?</span>"
        r"|<sup\b[^>]*>.*?</sup>"
        r"|<sub\b[^>]*>.*?</sub>"
        r"|<a\b[^>]*>.*?</a>",
        re.DOTALL,
    )

    @classmethod
    def _strip_inline_html(cls, text: str) -> str:
        """Notion で意味を持たない HTML タグ（pseudo-anchor 等）を除去する"""
        return cls._STRIP_HTML_PATTERN.sub("", text)

    # LLM が翻訳結果を ```markdown ... ``` で誤って包むケースの検出
    # 言語識別子付きで開き、内側に Markdown 構造（見出し / テーブル / リスト）があり、
    # 単独の ``` で閉じる場合のみマッチする
    _TRANSLATION_FENCE_PATTERN = re.compile(
        r"(?m)^```(?:markdown|md|MARKDOWN|MD)\s*\n"
        r"(?P<body>(?:.*\n)*?)"
        r"^```\s*$"
    )

    @classmethod
    def _unwrap_translation_code_fences(cls, text: str) -> str:
        """LLM が ```markdown ... ``` で包んだ翻訳結果ブロックを段落化する

        ただし内側に独立した ``` が含まれる場合は誤剥離を避けてそのまま残す。
        """

        def _replace(match: re.Match) -> str:
            body = match.group("body")
            # 内側に独立 ``` が含まれていればコードブロックとして残す（誤剥離回避）
            if re.search(r"(?m)^```", body):
                return match.group(0)
            return body

        return cls._TRANSLATION_FENCE_PATTERN.sub(_replace, text)

    @staticmethod
    def _unwrap_bold_around_equation(text: str) -> str:
        """**$...$** パターンを $...$ に展開する（数式優先）"""
        return re.sub(r"\*\*(\$[^$\n]+?\$)\*\*", r"\1", text)

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

    def _build_image_block(
        self,
        url: Optional[str] = None,
        file_upload_id: Optional[str] = None,
        caption: str = "",
    ) -> Dict[str, Any]:
        """画像ブロックを生成

        Args:
            url: 外部URL（http(s)://）
            file_upload_id: Notion File Upload API のID
            caption: 画像キャプション
        """
        caption_rich_text: List[Dict[str, Any]] = []
        if caption:
            caption_rich_text = [{"type": "text", "text": {"content": caption}}]

        if file_upload_id:
            return {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "file_upload",
                    "file_upload": {"id": file_upload_id},
                    "caption": caption_rich_text,
                },
            }
        # external URL
        block: Dict[str, Any] = {
            "object": "block",
            "type": "image",
            "image": {
                "type": "external",
                "external": {"url": url},
            },
        }
        if caption_rich_text:
            block["image"]["caption"] = caption_rich_text
        return block

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
