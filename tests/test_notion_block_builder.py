"""Tests for NotionBlockBuilder."""

import pytest

from minitools.publishers.notion_block_builder import NotionBlockBuilder


@pytest.fixture
def builder():
    return NotionBlockBuilder()


class TestNotionBlockBuilderDivider:
    """区切り線ブロックのテスト"""

    def test_starts_with_divider(self, builder):
        """最初のブロックがdividerであること"""
        blocks = builder.build_blocks("Hello")
        assert blocks[0]["type"] == "divider"

    def test_divider_structure(self, builder):
        """dividerブロックの構造"""
        blocks = builder.build_blocks("Hello")
        divider = blocks[0]
        assert divider["object"] == "block"
        assert divider["type"] == "divider"
        assert "divider" in divider


class TestNotionBlockBuilderHeadings:
    """見出しブロックのテスト"""

    def test_heading_1(self, builder):
        """heading_1ブロックの生成"""
        blocks = builder.build_blocks("# Title")
        heading = blocks[1]  # blocks[0] is divider
        assert heading["type"] == "heading_1"
        assert heading["heading_1"]["rich_text"][0]["text"]["content"] == "Title"

    def test_heading_2(self, builder):
        """heading_2ブロックの生成"""
        blocks = builder.build_blocks("## Subtitle")
        heading = blocks[1]
        assert heading["type"] == "heading_2"
        assert heading["heading_2"]["rich_text"][0]["text"]["content"] == "Subtitle"

    def test_heading_3(self, builder):
        """heading_3ブロックの生成"""
        blocks = builder.build_blocks("### Section")
        heading = blocks[1]
        assert heading["type"] == "heading_3"
        assert heading["heading_3"]["rich_text"][0]["text"]["content"] == "Section"


class TestNotionBlockBuilderParagraphs:
    """段落ブロックのテスト"""

    def test_basic_paragraph(self, builder):
        """段落ブロックの生成"""
        blocks = builder.build_blocks("Hello World")
        para = blocks[1]
        assert para["type"] == "paragraph"
        assert para["paragraph"]["rich_text"][0]["text"]["content"] == "Hello World"

    def test_long_text_split(self, builder):
        """2000文字超のテキストが分割される"""
        long_text = "A" * 3000
        blocks = builder.build_blocks(long_text)
        para = blocks[1]
        rich_text = para["paragraph"]["rich_text"]
        assert len(rich_text) == 2
        assert len(rich_text[0]["text"]["content"]) == 2000
        assert len(rich_text[1]["text"]["content"]) == 1000


class TestNotionBlockBuilderCodeBlocks:
    """コードブロックのテスト"""

    def test_basic_code_block(self, builder):
        """コードブロックの生成"""
        md = "```python\nprint('hello')\n```"
        blocks = builder.build_blocks(md)
        code = blocks[1]
        assert code["type"] == "code"
        assert code["code"]["language"] == "python"
        assert code["code"]["rich_text"][0]["text"]["content"] == "print('hello')"

    def test_code_block_no_language(self, builder):
        """言語指定なしのコードブロック"""
        md = "```\nsome code\n```"
        blocks = builder.build_blocks(md)
        code = blocks[1]
        assert code["type"] == "code"
        assert code["code"]["language"] == "plain text"

    def test_code_block_language_mapping(self, builder):
        """言語名のマッピング"""
        md = "```js\nconst x = 1;\n```"
        blocks = builder.build_blocks(md)
        code = blocks[1]
        assert code["code"]["language"] == "javascript"


class TestNotionBlockBuilderImages:
    """画像ブロックのテスト"""

    def test_basic_image(self, builder):
        """画像ブロックの生成"""
        md = "![alt text](https://example.com/img.png)"
        blocks = builder.build_blocks(md)
        img = blocks[1]
        assert img["type"] == "image"
        assert img["image"]["type"] == "external"
        assert img["image"]["external"]["url"] == "https://example.com/img.png"


class TestNotionBlockBuilderLists:
    """リストブロックのテスト"""

    def test_bulleted_list(self, builder):
        """箇条書きリストの生成"""
        md = "- Item 1\n- Item 2"
        blocks = builder.build_blocks(md)
        assert blocks[1]["type"] == "bulleted_list_item"
        assert (
            blocks[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"]
            == "Item 1"
        )
        assert blocks[2]["type"] == "bulleted_list_item"

    def test_numbered_list(self, builder):
        """番号付きリストの生成"""
        md = "1. First\n2. Second"
        blocks = builder.build_blocks(md)
        assert blocks[1]["type"] == "numbered_list_item"
        assert (
            blocks[1]["numbered_list_item"]["rich_text"][0]["text"]["content"]
            == "First"
        )
        assert blocks[2]["type"] == "numbered_list_item"


class TestNotionBlockBuilderQuotes:
    """引用ブロックのテスト"""

    def test_basic_quote(self, builder):
        """引用ブロックの生成"""
        md = "> This is a quote"
        blocks = builder.build_blocks(md)
        quote = blocks[1]
        assert quote["type"] == "quote"
        assert quote["quote"]["rich_text"][0]["text"]["content"] == "This is a quote"

    def test_multiline_quote(self, builder):
        """複数行引用の結合"""
        md = "> Line 1\n> Line 2"
        blocks = builder.build_blocks(md)
        quote = blocks[1]
        assert quote["type"] == "quote"
        assert "Line 1\nLine 2" in quote["quote"]["rich_text"][0]["text"]["content"]


class TestNotionBlockBuilderHorizontalRules:
    """水平線ブロックのテスト"""

    def test_horizontal_rule_dashes(self, builder):
        """---が水平線（divider）に変換される"""
        blocks = builder.build_blocks("text\n\n---\n\nmore text")
        types = [b["type"] for b in blocks]
        # divider(先頭) + paragraph + divider(---) + paragraph
        assert types.count("divider") == 2

    def test_horizontal_rule_asterisks(self, builder):
        """***が水平線（divider）に変換される"""
        blocks = builder.build_blocks("text\n\n***\n\nmore text")
        types = [b["type"] for b in blocks]
        assert types.count("divider") == 2

    def test_horizontal_rule_underscores(self, builder):
        """___が水平線（divider）に変換される"""
        blocks = builder.build_blocks("text\n\n___\n\nmore text")
        types = [b["type"] for b in blocks]
        assert types.count("divider") == 2


class TestNotionBlockBuilderItalicLines:
    """イタリック行（キャプション等）のテスト"""

    def test_italic_line(self, builder):
        """*text*がイタリックannotation付き段落に変換される"""
        blocks = builder.build_blocks("*Caption text*")
        para = blocks[1]
        assert para["type"] == "paragraph"
        rich_text = para["paragraph"]["rich_text"][0]
        assert rich_text["text"]["content"] == "Caption text"
        assert rich_text["annotations"]["italic"] is True

    def test_italic_line_with_spaces(self, builder):
        """前後にスペースのあるイタリック行"""
        blocks = builder.build_blocks("  *Figure 1: Diagram*  ")
        para = blocks[1]
        assert para["type"] == "paragraph"
        rich_text = para["paragraph"]["rich_text"][0]
        assert rich_text["text"]["content"] == "Figure 1: Diagram"
        assert rich_text["annotations"]["italic"] is True


class TestNotionBlockBuilderRichText:
    """_build_rich_textのテスト"""

    def test_empty_text_returns_empty_content(self, builder):
        """空テキストでも空contentのrich_textを返す"""
        rich_text = builder._build_rich_text("")
        assert len(rich_text) == 1
        assert rich_text[0]["type"] == "text"
        assert rich_text[0]["text"]["content"] == ""

    def test_none_text_returns_empty_content(self, builder):
        """Noneテキストでも空contentのrich_textを返す"""
        rich_text = builder._build_rich_text(None)
        assert len(rich_text) == 1
        assert rich_text[0]["text"]["content"] == ""

    def test_bold_text(self, builder):
        """**text**がbold annotationに変換される"""
        rich_text = builder._build_rich_text("This is **bold** text")
        assert len(rich_text) == 3
        assert rich_text[0]["text"]["content"] == "This is "
        assert rich_text[1]["text"]["content"] == "bold"
        assert rich_text[1]["annotations"]["bold"] is True
        assert rich_text[2]["text"]["content"] == " text"

    def test_italic_text(self, builder):
        """*text*がitalic annotationに変換される"""
        rich_text = builder._build_rich_text("This is *italic* text")
        assert len(rich_text) == 3
        assert rich_text[0]["text"]["content"] == "This is "
        assert rich_text[1]["text"]["content"] == "italic"
        assert rich_text[1]["annotations"]["italic"] is True
        assert rich_text[2]["text"]["content"] == " text"

    def test_inline_code(self, builder):
        """`code`がcode annotationに変換される"""
        rich_text = builder._build_rich_text("Use `pip install` to install")
        assert len(rich_text) == 3
        assert rich_text[0]["text"]["content"] == "Use "
        assert rich_text[1]["text"]["content"] == "pip install"
        assert rich_text[1]["annotations"]["code"] is True
        assert rich_text[2]["text"]["content"] == " to install"

    def test_link(self, builder):
        """[text](url)がNotion linkに変換される"""
        rich_text = builder._build_rich_text(
            "Visit [here](https://example.com) for more"
        )
        assert len(rich_text) == 3
        assert rich_text[0]["text"]["content"] == "Visit "
        assert rich_text[1]["text"]["content"] == "here"
        assert rich_text[1]["text"]["link"]["url"] == "https://example.com"
        assert rich_text[2]["text"]["content"] == " for more"

    def test_mixed_formatting(self, builder):
        """複数の書式が混在するテキスト"""
        rich_text = builder._build_rich_text("**Bold** and *italic* and `code`")
        assert rich_text[0]["text"]["content"] == "Bold"
        assert rich_text[0]["annotations"]["bold"] is True
        assert rich_text[1]["text"]["content"] == " and "
        assert rich_text[2]["text"]["content"] == "italic"
        assert rich_text[2]["annotations"]["italic"] is True
        assert rich_text[3]["text"]["content"] == " and "
        assert rich_text[4]["text"]["content"] == "code"
        assert rich_text[4]["annotations"]["code"] is True

    def test_plain_text_no_formatting(self, builder):
        """書式なしテキストはプレーンテキストとして返される"""
        rich_text = builder._build_rich_text("Just plain text")
        assert len(rich_text) == 1
        assert rich_text[0]["text"]["content"] == "Just plain text"
        assert "annotations" not in rich_text[0]


class TestNotionBlockBuilderComplex:
    """複合的なMarkdownのテスト"""

    def test_complex_markdown(self, builder):
        """複合的なMarkdownからのブロック列生成"""
        md = """# Title

This is a paragraph.

## Section 1

- Item A
- Item B

```python
print("hello")
```

> A quote here

1. First
2. Second

![img](https://example.com/img.png)"""

        blocks = builder.build_blocks(md)
        # divider + heading_1 + paragraph + heading_2 + 2 bullets + code + quote + 2 numbered + image = 11
        types = [b["type"] for b in blocks]
        assert types[0] == "divider"
        assert "heading_1" in types
        assert "heading_2" in types
        assert "paragraph" in types
        assert "bulleted_list_item" in types
        assert "code" in types
        assert "quote" in types
        assert "numbered_list_item" in types
        assert "image" in types

    def test_empty_markdown(self, builder):
        """空Markdownの処理"""
        assert builder.build_blocks("") == []
        assert builder.build_blocks("   ") == []


class TestNotionBlockBuilderBlockEquation:
    """ブロック数式のテスト"""

    def test_build_block_equation_single_line(self, builder):
        """1行内の $$...$$ が equation block として生成される"""
        md = "$$g = \\frac{x}{y} \\tag{1}$$"
        blocks = builder.build_blocks(md)
        eq = blocks[1]
        assert eq["type"] == "equation"
        assert eq["equation"]["expression"] == "g = \\frac{x}{y} \\tag{1}"

    def test_build_block_equation_multi_line(self, builder):
        """複数行に跨る $$...$$ が 1 つの equation block として生成される"""
        md = "$$\ng = \\frac{x}{y}\n+ z\n$$"
        blocks = builder.build_blocks(md)
        eq = blocks[1]
        assert eq["type"] == "equation"
        assert "g = \\frac{x}{y}" in eq["equation"]["expression"]
        assert "+ z" in eq["equation"]["expression"]

    def test_block_equation_before_paragraph(self, builder):
        """ブロック数式の後に段落が続く場合"""
        md = "$$x = 1$$\n\nHello"
        blocks = builder.build_blocks(md)
        types = [b["type"] for b in blocks]
        assert "equation" in types
        assert "paragraph" in types

    def test_build_block_equation_empty_expression(self, builder):
        """空 expression（$$$$ や $$ $$）は equation ではなく paragraph として扱う"""
        for md in ["$$$$", "$$ $$"]:
            blocks = builder.build_blocks(md)
            types = [b["type"] for b in blocks]
            assert "equation" not in types, f"空 expression で equation 生成: {md!r}"
            assert "paragraph" in types

    def test_build_block_equation_empty_multiline(self, builder):
        """複数行で空 expression（$$\\n$$）も paragraph フォールバック"""
        md = "$$\n$$"
        blocks = builder.build_blocks(md)
        types = [b["type"] for b in blocks]
        assert "equation" not in types
        assert "paragraph" in types


class TestNotionBlockBuilderInlineEquation:
    """インライン数式のテスト"""

    def test_build_inline_equation(self, builder):
        """$...$ が rich_text の equation として変換される"""
        rich_text = builder._build_rich_text("Check $\\checkmark$ symbol")
        types = [rt.get("type") for rt in rich_text]
        assert "equation" in types
        eq = next(rt for rt in rich_text if rt.get("type") == "equation")
        assert eq["equation"]["expression"] == "\\checkmark"

    def test_build_inline_equation_in_bold(self, builder):
        """**$x$** のように bold の内側にある数式が equation として処理される"""
        rich_text = builder._build_rich_text("Value **$x$** appears")
        # equation 型の rich_text が含まれる
        types = [rt.get("type") for rt in rich_text]
        assert "equation" in types

    def test_build_inline_equation_escaped_dollar(self, builder):
        """\\$100 のようにエスケープされた $ は通常文字として扱われる"""
        rich_text = builder._build_rich_text("Price is \\$100 USD")
        # equation にはならない
        types = [rt.get("type") for rt in rich_text]
        assert "equation" not in types


class TestNotionBlockBuilderTable:
    """テーブルのテスト"""

    def test_build_table_basic(self, builder):
        """基本的なヘッダー+データ行のテーブル"""
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        blocks = builder.build_blocks(md)
        table = blocks[1]
        assert table["type"] == "table"
        assert table["table"]["table_width"] == 2
        assert table["table"]["has_column_header"] is True
        children = table["table"]["children"]
        # 1 header + 2 data = 3 rows
        assert len(children) == 3
        assert children[0]["type"] == "table_row"
        assert children[0]["table_row"]["cells"][0][0]["text"]["content"] == "A"
        assert children[1]["table_row"]["cells"][0][0]["text"]["content"] == "1"

    def test_build_table_inline_equation_in_cell(self, builder):
        """セル内の $\\checkmark$ が equation として表示される"""
        md = "| Feature | Supported |\n|---|---|\n| foo | $\\checkmark$ |"
        blocks = builder.build_blocks(md)
        table = blocks[1]
        data_row = table["table"]["children"][1]
        cell = data_row["table_row"]["cells"][1]
        types = [rt.get("type") for rt in cell]
        assert "equation" in types

    def test_build_table_padding_missing_cells(self, builder):
        """行によってセル数が不足する場合、ヘッダー幅に合わせて padding される"""
        md = "| A | B | C |\n|---|---|---|\n| 1 | 2 |"
        blocks = builder.build_blocks(md)
        table = blocks[1]
        assert table["table"]["table_width"] == 3
        data_row = table["table"]["children"][1]
        cells = data_row["table_row"]["cells"]
        assert len(cells) == 3


class TestNotionBlockBuilderImageUploads:
    """画像アップロードマッピングのテスト"""

    def test_build_image_with_upload_mapping(self, builder):
        """image_uploads マッピングで file_upload 型 image block が生成される"""
        md = "![Figure 1](_page_0_Figure_5.jpeg)"
        blocks = builder.build_blocks(
            md, image_uploads={"_page_0_Figure_5.jpeg": "abc-123-uuid"}
        )
        img = blocks[1]
        assert img["type"] == "image"
        assert img["image"]["type"] == "file_upload"
        assert img["image"]["file_upload"]["id"] == "abc-123-uuid"
        assert img["image"]["caption"][0]["text"]["content"] == "Figure 1"

    def test_build_image_fallback_no_mapping(self, builder):
        """マッピングに無いローカル画像はキャプション段落にフォールバック"""
        md = "![Figure 1](_page_0_Figure_5.jpeg)"
        blocks = builder.build_blocks(md, image_uploads={})
        # image block ではなく paragraph にフォールバック
        para = blocks[1]
        assert para["type"] == "paragraph"
        assert "Figure 1" in para["paragraph"]["rich_text"][0]["text"]["content"]

    def test_build_blocks_backward_compat(self, builder):
        """image_uploads=None（デフォルト）で既存動作と一致する"""
        md = "# Title\n\nHello"
        blocks_default = builder.build_blocks(md)
        blocks_none = builder.build_blocks(md, image_uploads=None)
        assert blocks_default == blocks_none


class TestNotionBlockBuilderBulletVariants:
    """`•` (U+2022) bullet と `- 1.` 番号付き再分類のテスト"""

    def test_bullet_unicode(self, builder):
        """`• item` が bulleted_list_item として認識される"""
        blocks = builder.build_blocks("• Codex CLI: lightweight agent")
        item = blocks[1]
        assert item["type"] == "bulleted_list_item"
        assert (
            item["bulleted_list_item"]["rich_text"][0]["text"]["content"]
            == "Codex CLI: lightweight agent"
        )

    def test_bullet_with_numbered_inside_becomes_numbered(self, builder):
        """`- 1. xxx` は numbered_list_item として再分類される"""
        blocks = builder.build_blocks("- 1. タスク要件を分析する")
        item = blocks[1]
        assert item["type"] == "numbered_list_item"
        assert (
            item["numbered_list_item"]["rich_text"][0]["text"]["content"]
            == "タスク要件を分析する"
        )

    def test_indented_bullet(self, builder):
        """先頭に空白がある bullet も検出される"""
        blocks = builder.build_blocks("    - インデントされた項目")
        item = blocks[1]
        assert item["type"] == "bulleted_list_item"


class TestNotionBlockBuilderHtmlStrip:
    """HTML タグ除去のテスト"""

    def test_strip_span_anchor(self, builder):
        """`<span id="...">...</span>` が除去される"""
        blocks = builder.build_blocks('<span id="page-1"></span>本文の段落です。')
        para = blocks[1]
        assert para["type"] == "paragraph"
        assert (
            para["paragraph"]["rich_text"][0]["text"]["content"] == "本文の段落です。"
        )

    def test_strip_sup(self, builder):
        """`<sup>...</sup>` が除去される"""
        blocks = builder.build_blocks("脚注付きテキスト<sup>1</sup>。")
        para = blocks[1]
        text = "".join(rt["text"]["content"] for rt in para["paragraph"]["rich_text"])
        assert "<sup>" not in text
        assert "1" not in text or text == "脚注付きテキスト。"


class TestNotionBlockBuilderTableBr:
    """テーブルセル内 `<br>` 改行処理のテスト"""

    def test_cell_with_br(self, builder):
        """セル内の `<br>` が rich_text の改行として扱われる"""
        md = (
            "| Harness | Models |\n|---|---|\n| Claude Code | Opus<br>Sonnet<br>Haiku |"
        )
        blocks = builder.build_blocks(md)
        table = blocks[1]
        cells = table["table"]["children"][1]["table_row"]["cells"]
        # 2 列目のセル rich_text を結合すると改行が含まれる
        joined = "".join(rt["text"]["content"] for rt in cells[1])
        assert "Opus\nSonnet\nHaiku" in joined


class TestNotionBlockBuilderEmptyTable:
    """空・caption-only テーブルのフォールバックテスト"""

    def test_caption_only_table_falls_back_to_paragraph(self, builder):
        """データ行が無くヘッダーが実質1セルなら paragraph にフォールバック"""
        md = "| 表18. スキルによる影響が最大のタスク |  |  |\n|---|---|---|\n|  |  |  |"
        blocks = builder.build_blocks(md)
        # divider + paragraph
        assert blocks[1]["type"] == "paragraph"
        assert "表18" in blocks[1]["paragraph"]["rich_text"][0]["text"]["content"]

    def test_normal_table_still_built(self, builder):
        """データ行があれば通常通りテーブル化される（リグレッション防止）"""
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        blocks = builder.build_blocks(md)
        assert blocks[1]["type"] == "table"


class TestNotionBlockBuilderTranslationFenceStrip:
    """LLM 誤包装 ```markdown ... ``` の除去テスト"""

    def test_unwrap_markdown_fence(self, builder):
        """`\\`\\`\\`markdown` で包まれた翻訳セクションが展開される"""
        md = "前段の段落\n\n```markdown\n### 見出し\n\n本文の段落\n```\n\n後段の段落"
        blocks = builder.build_blocks(md)
        types = [b["type"] for b in blocks]
        # 見出しと段落が独立したブロックになり、code ブロックは生成されない
        assert "heading_3" in types
        assert "code" not in types

    def test_preserve_legitimate_code_block(self, builder):
        """内部に独立 ``` を持つ場合はコードブロックとして残す"""
        md = "```python\nprint('hello')\n```\n"
        blocks = builder.build_blocks(md)
        types = [b["type"] for b in blocks]
        assert "code" in types

    def test_real_world_table_inside_fence(self, builder):
        """テーブルが ```markdown 内にある場合も table として処理される"""
        md = "```markdown\n| A | B |\n|---|---|\n| 1 | 2 |\n```\n"
        blocks = builder.build_blocks(md)
        types = [b["type"] for b in blocks]
        assert "table" in types
        assert "code" not in types
