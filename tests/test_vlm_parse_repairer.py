"""Tests for VLM parse repairer components."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from unittest.mock import patch

import pytest

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.processors.vlm_parse_repairer import (
    MarkdownPatcher,
    ParseDefect,
    ParseErrorDetector,
    PdfPageRenderer,
    RepairResult,
    VlmParseRepairer,
    VlmRepairer,
    repaired_output_path,
)


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------


class MockMultimodalLLMClient(BaseLLMClient):
    """Multimodal LLM 動作をモックするクライアント"""

    def __init__(
        self,
        response: str = "```markdown\n| A | B |\n|---|---|\n| 1 | 2 |\n```",
        raise_n_times: int = 0,
        response_fn: Optional[Callable[[str], str]] = None,
    ):
        self.response = response
        self.response_fn = response_fn
        self.calls: List[Dict[str, Any]] = []
        self.raise_n_times = raise_n_times
        self._raised = 0

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        return self.response

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        return self.response

    async def generate_from_images(
        self,
        prompt: str,
        images: List[bytes],
        mime_type: str = "image/png",
        model: Optional[str] = None,
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "image_count": len(images),
                "mime_type": mime_type,
                "model": model,
            }
        )
        if self._raised < self.raise_n_times:
            self._raised += 1
            raise RuntimeError(f"mock failure {self._raised}")
        if self.response_fn is not None:
            return self.response_fn(prompt)
        return self.response


# ---------------------------------------------------------------------------
# ParseErrorDetector
# ---------------------------------------------------------------------------


class TestRepairedOutputPath:
    def test_raw_md_suffix_replaced(self):
        from pathlib import Path

        result = repaired_output_path(Path("/p/2602.12670_raw.md"))
        assert result == Path("/p/2602.12670_repaired.md")

    def test_md_only_suffix(self):
        from pathlib import Path

        result = repaired_output_path(Path("/p/foo.md"))
        assert result == Path("/p/foo.repaired.md")

    def test_no_md_suffix(self):
        from pathlib import Path

        result = repaired_output_path(Path("/p/foo"))
        assert result == Path("/p/foo.repaired.md")


class TestParseErrorDetector:
    def test_short_line_run_detected(self):
        """1-3語の短行が連続するブロックがtableとして検出される"""
        markdown = "\n".join(
            [
                "## Some heading",
                "",
                "Easy",
                "",
                "Easy",
                "",
                "Hard",
                "",
                "Med",
                "",
                "Hard",
                "",
                "Software Eng.",
                "",
                "Software Eng.",
            ]
        )
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        table_defects = [d for d in defects if d.kind == "table"]
        assert len(table_defects) >= 1

    def test_short_line_run_below_threshold_not_detected(self):
        """5行未満は検出されない"""
        markdown = "\n".join(
            [
                "Easy",
                "",
                "Hard",
                "",
                "Med",
            ]
        )
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        # MIN_RUN_LENGTH=5 なので3つでは検出されない
        table_defects = [d for d in defects if d.kind == "table"]
        assert len(table_defects) == 0

    def test_orphan_figure_detected(self):
        """画像参照が figure として検出される"""
        markdown = "Some intro\n\n![](_page_3_Figure_5.jpeg)\n\nNext paragraph"
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        figure_defects = [d for d in defects if d.kind == "figure"]
        assert len(figure_defects) == 1
        assert figure_defects[0].image_ref == "_page_3_Figure_5.jpeg"
        assert figure_defects[0].page_hint == 3

    def test_continued_marker_detected(self):
        """Continued on next page 周辺がtableとして検出される"""
        markdown = "\n".join(
            [
                "row1",
                "row2",
                "Continued on next page",
                "row3",
                "row4",
            ]
        )
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        # continued近辺は table として検出
        assert any(d.kind == "table" for d in defects)

    def test_broken_table_high_empty_rate(self):
        """空セル率30%超のテーブルが検出される"""
        markdown = "\n".join(
            [
                "| A | B | C |",
                "|---|---|---|",
                "| 1 |   |   |",
                "| 2 |   |   |",
                "|   |   |   |",
            ]
        )
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        assert any(d.kind == "table" for d in defects)

    def test_page_hint_inferred_from_nearby_image(self):
        """前後30行内の画像参照からpage_hintが推定される"""
        lines = [
            "![](_page_5_Figure_1.jpeg)",
            "",
        ]
        # 短行ラン
        for _ in range(7):
            lines.extend(["Easy", ""])
        markdown = "\n".join(lines)

        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        table_defects = [d for d in defects if d.kind == "table"]
        assert table_defects, "短行ランが検出されること"
        # figureの参照から推定されるはず
        assert any(d.page_hint == 5 for d in table_defects)

    def test_page_hint_fallback_via_continued_marker(self):
        """画像参照が ±radius を超える距離でも continued マーカーで page を補正"""
        lines = [
            "![](_page_22_Figure_1.jpeg)",  # line 0: page 22 ref
            "*Figure 13.* caption",
            "",
        ]
        # radius=30 を超える filler
        for _ in range(40):
            lines.append("filler line content " * 3)
        # 1ページ目の終了マーカー
        lines.append("Continued on next page")
        lines.append("")
        # 短行ラン (Table 9 continuation 相当)
        for _ in range(7):
            lines.extend(["Easy", ""])

        markdown = "\n".join(lines)
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        table_defects = [d for d in defects if d.kind == "table"]
        # 短行ラン検出は continued マーカー検出と重複しマージされる
        assert table_defects
        # ref_page=22 + continued=1 = 23 が最低1件あるはず
        assert any(d.page_hint == 23 for d in table_defects), (
            f"page_hint 期待値 23、実際: {[d.page_hint for d in table_defects]}"
        )

    def test_page_hint_fallback_no_ref_returns_none(self):
        """画像参照が一切ない場合は None を返す"""
        lines = []
        for _ in range(7):
            lines.extend(["Easy", ""])
        markdown = "\n".join(lines)
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        table_defects = [d for d in defects if d.kind == "table"]
        assert table_defects
        assert all(d.page_hint is None for d in table_defects)

    def test_excerpt_includes_surrounding_lines(self):
        """excerptには前後の行が含まれる"""
        lines = ["context_before"] * 3 + ["Easy"] * 7 + ["context_after"] * 3
        markdown = "\n".join(lines)
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        assert defects
        assert "context_before" in defects[0].excerpt
        assert "context_after" in defects[0].excerpt

    def test_no_false_positive_on_normal_paragraphs(self):
        """通常の段落で誤検出が発生しない"""
        markdown = (
            "This is a normal paragraph that contains many words and is "
            "definitely longer than fifty characters in total length.\n\n"
            "Another paragraph with substantial content and standard prose.\n\n"
            "A third paragraph also containing reasonable content for evaluation.\n"
        )
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        table_defects = [d for d in defects if d.kind == "table"]
        assert len(table_defects) == 0

    def test_bullet_list_not_detected_as_short_run(self):
        """箇条書きは短行ランとして検出されない"""
        markdown = "\n".join(
            [
                "- item one",
                "- item two",
                "- item three",
                "- item four",
                "- item five",
                "- item six",
            ]
        )
        detector = ParseErrorDetector()
        defects = detector.detect(markdown)
        table_defects = [d for d in defects if d.kind == "table"]
        assert len(table_defects) == 0


# ---------------------------------------------------------------------------
# MarkdownPatcher
# ---------------------------------------------------------------------------


class TestMarkdownPatcher:
    def test_table_replacement_basic(self):
        markdown = "before\nbroken1\nbroken2\nafter\n"
        defect = ParseDefect(kind="table", line_start=1, line_end=3)
        repaired = "```markdown\n| A | B |\n|---|---|\n| 1 | 2 |\n```\n"
        patcher = MarkdownPatcher()
        new_md, applied, skipped = patcher.apply(markdown, [(defect, repaired)])
        assert applied == 1
        assert skipped == 0
        assert "| A | B |" in new_md
        assert "before" in new_md
        assert "after" in new_md
        assert "broken1" not in new_md

    def test_invalid_table_kept_original(self):
        markdown = "before\nbroken1\nbroken2\nafter\n"
        defect = ParseDefect(kind="table", line_start=1, line_end=3)
        # 区切り行がない無効なテーブル
        repaired = "| A | B |\n| 1 | 2 |\n"
        patcher = MarkdownPatcher()
        new_md, applied, skipped = patcher.apply(markdown, [(defect, repaired)])
        assert applied == 0
        assert skipped == 1
        assert "broken1" in new_md
        assert "broken2" in new_md

    def test_figure_note_inserted(self):
        markdown = "intro\n![](_page_0_Figure_1.jpeg)\nother\n"
        defect = ParseDefect(
            kind="figure",
            line_start=1,
            line_end=2,
            image_ref="_page_0_Figure_1.jpeg",
        )
        patcher = MarkdownPatcher()
        new_md, applied, _ = patcher.apply(markdown, [(defect, "図の要約テキスト")])
        assert applied == 1
        assert "> [図解説] 図の要約テキスト" in new_md

    def test_figure_note_idempotent(self):
        """既に図解説がある場合は重複挿入しない"""
        markdown = "intro\n![](_page_0_Figure_1.jpeg)\n> [図解説] 既存の要約\nother\n"
        defect = ParseDefect(
            kind="figure",
            line_start=1,
            line_end=2,
            image_ref="_page_0_Figure_1.jpeg",
        )
        patcher = MarkdownPatcher()
        new_md, applied, skipped = patcher.apply(markdown, [(defect, "新しい要約")])
        assert applied == 0
        assert skipped == 1
        # 既存の要約が残り、新しい要約は追加されない
        assert new_md.count("[図解説]") == 1

    def test_crlf_input_handled(self):
        markdown = "before\r\nbroken1\r\nbroken2\r\nafter\r\n"
        defect = ParseDefect(kind="table", line_start=1, line_end=3)
        repaired = "```markdown\n| A | B |\n|---|---|\n| 1 | 2 |\n```\n"
        patcher = MarkdownPatcher()
        new_md, applied, _ = patcher.apply(markdown, [(defect, repaired)])
        assert applied == 1
        # CRLF 区切りが保持される（少なくとも他の行は）
        assert "before" in new_md
        assert "after" in new_md

    def test_no_trailing_newline_input(self):
        markdown = "before\nbroken\nafter"
        defect = ParseDefect(kind="table", line_start=1, line_end=2)
        repaired = "```markdown\n| A | B |\n|---|---|\n| 1 | 2 |\n```\n"
        patcher = MarkdownPatcher()
        new_md, applied, _ = patcher.apply(markdown, [(defect, repaired)])
        assert applied == 1

    def test_first_line_replacement(self):
        markdown = "broken\nafter\n"
        defect = ParseDefect(kind="table", line_start=0, line_end=1)
        repaired = "```markdown\n| A | B |\n|---|---|\n| 1 | 2 |\n```\n"
        patcher = MarkdownPatcher()
        new_md, applied, _ = patcher.apply(markdown, [(defect, repaired)])
        assert applied == 1
        assert "| A | B |" in new_md
        assert "broken" not in new_md

    def test_validate_markdown_table(self):
        valid = "| A | B |\n|---|---|\n| 1 | 2 |"
        invalid_no_sep = "| A | B |\n| 1 | 2 |"
        too_few_rows = "| A | B |"
        assert MarkdownPatcher._validate_markdown_table(valid) is True
        assert MarkdownPatcher._validate_markdown_table(invalid_no_sep) is False
        assert MarkdownPatcher._validate_markdown_table(too_few_rows) is False


# ---------------------------------------------------------------------------
# VlmRepairer
# ---------------------------------------------------------------------------


class TestVlmRepairer:
    @pytest.mark.asyncio
    async def test_repair_table_calls_client_with_excerpt(self):
        client = MockMultimodalLLMClient()
        repairer = VlmRepairer(provider="custom", client=client)
        defect = ParseDefect(
            kind="table",
            line_start=10,
            line_end=15,
            excerpt="excerpt content here",
        )
        result = await repairer.repair_table(defect, [b"fake_png"])
        assert "| A | B |" in result
        assert client.calls
        assert "excerpt content here" in client.calls[0]["prompt"]

    @pytest.mark.asyncio
    async def test_repair_figure_calls_client_with_caption(self):
        client = MockMultimodalLLMClient(response="図の日本語要約です。")
        repairer = VlmRepairer(provider="custom", client=client)
        defect = ParseDefect(kind="figure", line_start=10, line_end=11)
        result = await repairer.repair_figure(
            defect, [b"fake_png"], "Figure 1: caption"
        )
        assert result == "図の日本語要約です。"
        assert "Figure 1: caption" in client.calls[0]["prompt"]

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        # 2回失敗、3回目で成功
        client = MockMultimodalLLMClient(
            response="```markdown\n| A |\n|---|\n| 1 |\n```", raise_n_times=2
        )
        repairer = VlmRepairer(provider="custom", client=client)
        # リトライ遅延をテスト用に短縮
        with patch.object(VlmRepairer, "RETRY_DELAYS", [0, 0, 0]):
            defect = ParseDefect(kind="table", line_start=0, line_end=1, excerpt="x")
            result = await repairer.repair_table(defect, [b"fake_png"])
        assert "| A |" in result

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        client = MockMultimodalLLMClient(raise_n_times=10)
        repairer = VlmRepairer(provider="custom", client=client)
        with patch.object(VlmRepairer, "RETRY_DELAYS", [0, 0, 0]):
            defect = ParseDefect(kind="table", line_start=0, line_end=1, excerpt="x")
            with pytest.raises(LLMError):
                await repairer.repair_table(defect, [b"fake_png"])

    @pytest.mark.asyncio
    async def test_ollama_provider_returns_empty(self):
        client = MockMultimodalLLMClient()
        repairer = VlmRepairer(provider="ollama", client=client)
        defect = ParseDefect(kind="table", line_start=0, line_end=1, excerpt="x")
        result = await repairer.repair_table(defect, [b"fake_png"])
        assert result == ""
        # client は呼ばれない
        assert not client.calls


# ---------------------------------------------------------------------------
# PdfPageRenderer
# ---------------------------------------------------------------------------


class TestPdfPageRenderer:
    @pytest.mark.asyncio
    async def test_pdf_not_found_returns_empty(self, tmp_path):
        cache_dir = tmp_path / "cache"
        renderer = PdfPageRenderer(cache_dir=cache_dir, max_pages_per_defect=3)
        result = await renderer.render_pages(
            pdf_path=tmp_path / "nonexistent.pdf",
            page_numbers=[0],
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_truncates_when_over_limit(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        # キャッシュにダミーファイルを置く
        for i in range(10):
            (cache_dir / f"page_{i:03d}.png").write_bytes(b"fake_png")

        # 存在するダミーPDFパス（中身は空）
        pdf_path = tmp_path / "fake.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        renderer = PdfPageRenderer(cache_dir=cache_dir, max_pages_per_defect=3)
        # キャッシュヒットするので fitz が呼ばれず、3 件返る
        result = await renderer.render_pages(
            pdf_path=pdf_path,
            page_numbers=[0, 1, 2, 3, 4],  # 5 ページ要求
        )
        # 3 ページに切り詰められ、すべてキャッシュからロード
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_cache_hit_loads_from_disk(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "page_005.png").write_bytes(b"cached_data")
        pdf_path = tmp_path / "fake.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        renderer = PdfPageRenderer(cache_dir=cache_dir, max_pages_per_defect=3)
        result = await renderer.render_pages(
            pdf_path=pdf_path,
            page_numbers=[5],
        )
        assert result == [b"cached_data"]


# ---------------------------------------------------------------------------
# VlmParseRepairer (オーケストレータ統合テスト)
# ---------------------------------------------------------------------------


class TestVlmParseRepairer:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_modify_file(self, tmp_path):
        raw_md = tmp_path / "test_raw.md"
        original = "intro\n\n![](_page_0_Figure_1.jpeg)\n\n" + "Easy\n\n" * 7 + "tail\n"
        raw_md.write_text(original, encoding="utf-8")
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        client = MockMultimodalLLMClient()
        repairer = VlmParseRepairer(provider="custom", client=client)
        result = await repairer.repair(raw_md, pdf_path, dry_run=True)

        assert isinstance(result, RepairResult)
        # dry-run では client が呼ばれない
        assert not client.calls
        # ファイルは変更されない
        assert raw_md.read_text(encoding="utf-8") == original

    @pytest.mark.asyncio
    async def test_pdf_missing_returns_detected_only(self, tmp_path):
        raw_md = tmp_path / "test_raw.md"
        raw_md.write_text(
            "![](_page_0_Figure_1.jpeg)\n\n" + "Easy\n\n" * 7,
            encoding="utf-8",
        )
        pdf_path = tmp_path / "missing.pdf"

        client = MockMultimodalLLMClient()
        repairer = VlmParseRepairer(provider="custom", client=client)
        result = await repairer.repair(raw_md, pdf_path, dry_run=False)

        # PDF が無いので applied=0 errors=0、検出だけは行う
        assert result.applied == 0
        assert result.detected

    @pytest.mark.asyncio
    async def test_repair_happy_path_rewrites_file(self, tmp_path):
        """正常系 e2e: VLM 応答が table/figure 双方で _raw.md に反映される"""
        raw_md = tmp_path / "test_raw.md"
        # figure (page 2) と短行ラン table が両方検出される構成
        original_lines = [
            "# Title",
            "",
            "intro",
            "",
            "![](_page_2_Figure_1.jpeg)",
            "",
            "Caption text here",
            "",
            "Easy",
            "Easy",
            "Hard",
            "Med",
            "Hard",
            "Software Eng.",
            "",
            "tail",
            "",
        ]
        original = "\n".join(original_lines)
        raw_md.write_text(original, encoding="utf-8")

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        # ページ画像キャッシュを事前配置（PyMuPDF を呼ばないため）
        # cache_dir は pdf_path.parent / "page_images" 固定
        cache_dir = tmp_path / "page_images"
        cache_dir.mkdir()
        for page_num in (2, 3):
            (cache_dir / f"page_{page_num:03d}.png").write_bytes(b"cached_png")

        # プロンプト内容で table / figure を判別して応答を返す
        table_response = "```markdown\n| Col1 | Col2 |\n|---|---|\n| a | b |\n```"
        figure_response = (
            "図2は学習曲線を示しており、横軸はエポック、縦軸は精度。"
            "10エポック付近で精度が頭打ちになる傾向。"
        )

        def respond(prompt: str) -> str:
            if "キャプション" in prompt:
                return figure_response
            return table_response

        client = MockMultimodalLLMClient(response_fn=respond)
        repairer = VlmParseRepairer(provider="custom", client=client)
        result = await repairer.repair(raw_md, pdf_path, dry_run=False)

        # 元の _raw.md は変更されない
        assert raw_md.read_text(encoding="utf-8") == original
        # 新ファイル _repaired.md が作成される
        from minitools.processors.vlm_parse_repairer import repaired_output_path

        repaired_path = repaired_output_path(raw_md)
        assert repaired_path.exists(), f"Expected {repaired_path} to be created"
        new_md = repaired_path.read_text(encoding="utf-8")
        # 修復内容が反映されている
        assert new_md != original
        # table が反映されている
        assert "| Col1 | Col2 |" in new_md
        # figure note が挿入されている
        assert "> [図解説]" in new_md
        assert "図2は学習曲線" in new_md
        # 元の短行ラン (Easy/Hard) は table 置換で消えている
        # （ただしプリアンブルの段落などは残るので "Easy" 単独行が消えていることを軽くチェック）
        assert "\nEasy\nEasy\nHard\n" not in new_md
        # RepairResult: 少なくとも 1件 applied、output_path がセットされる
        assert isinstance(result, RepairResult)
        assert result.applied >= 1
        assert result.output_path == repaired_path
        # client が呼ばれている
        assert client.calls

    def test_apply_budget_truncates_with_table_priority(self):
        """16件以上の defect で tables 優先・figures 後ろ削減を検証"""
        client = MockMultimodalLLMClient()
        repairer = VlmParseRepairer(
            provider="custom", client=client, max_total_calls=15
        )
        defects: list[ParseDefect] = []
        for i in range(10):
            defects.append(
                ParseDefect(kind="table", line_start=i * 10, line_end=i * 10 + 1)
            )
        for i in range(10):
            defects.append(
                ParseDefect(
                    kind="figure",
                    line_start=200 + i * 10,
                    line_end=201 + i * 10,
                    image_ref=f"_page_{i}_Figure_1.jpeg",
                )
            )

        budgeted = repairer._apply_budget(defects)

        assert len(budgeted) == 15
        table_count = sum(1 for d in budgeted if d.kind == "table")
        figure_count = sum(1 for d in budgeted if d.kind == "figure")
        assert table_count == 10  # 全 table が残る（優先）
        assert figure_count == 5  # figure は前から 5件、残り 5件は削減

    def test_apply_budget_within_limit_returns_all(self):
        """budget 内に収まる場合は全件返る"""
        client = MockMultimodalLLMClient()
        repairer = VlmParseRepairer(
            provider="custom", client=client, max_total_calls=15
        )
        defects = [
            ParseDefect(kind="table", line_start=0, line_end=1),
            ParseDefect(kind="figure", line_start=10, line_end=11),
        ]
        budgeted = repairer._apply_budget(defects)
        assert len(budgeted) == 2

    def test_apply_budget_respects_repair_tables_flag(self):
        """repair_tables=False で table が除外される"""
        client = MockMultimodalLLMClient()
        repairer = VlmParseRepairer(
            provider="custom",
            client=client,
            max_total_calls=15,
            repair_tables=False,
        )
        defects = [
            ParseDefect(kind="table", line_start=0, line_end=1),
            ParseDefect(kind="figure", line_start=10, line_end=11),
        ]
        budgeted = repairer._apply_budget(defects)
        assert all(d.kind == "figure" for d in budgeted)

    def test_apply_budget_respects_repair_figures_flag(self):
        """repair_figures=False で figure が除外される"""
        client = MockMultimodalLLMClient()
        repairer = VlmParseRepairer(
            provider="custom",
            client=client,
            max_total_calls=15,
            repair_figures=False,
        )
        defects = [
            ParseDefect(kind="table", line_start=0, line_end=1),
            ParseDefect(kind="figure", line_start=10, line_end=11),
        ]
        budgeted = repairer._apply_budget(defects)
        assert all(d.kind == "table" for d in budgeted)

    def test_apply_budget_warning_includes_kind_breakdown(self, caplog):
        """budget 超過時の warning に table/figure の skip 件数が含まれる"""
        import logging

        client = MockMultimodalLLMClient()
        repairer = VlmParseRepairer(provider="custom", client=client, max_total_calls=2)
        defects = [
            ParseDefect(kind="table", line_start=0, line_end=1),
            ParseDefect(kind="table", line_start=10, line_end=11),
            ParseDefect(kind="figure", line_start=20, line_end=21),
            ParseDefect(kind="figure", line_start=30, line_end=31),
        ]
        with caplog.at_level(logging.WARNING):
            repairer._apply_budget(defects)
        # warning に table と figure の内訳が含まれること
        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("table" in m and "figure" in m for m in warnings)

    @pytest.mark.asyncio
    async def test_repair_one_no_page_hint_returns_empty(self, tmp_path):
        """page_hint=None の defect は warning + 空文字列でスキップ"""
        client = MockMultimodalLLMClient()
        repairer = VlmParseRepairer(provider="custom", client=client)
        renderer = PdfPageRenderer(cache_dir=tmp_path / "cache", max_pages_per_defect=3)
        defect = ParseDefect(
            kind="table",
            line_start=0,
            line_end=1,
            page_hint=None,
            excerpt="x",
        )
        pdf_path = tmp_path / "fake.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        result = await repairer._repair_one(defect, renderer, pdf_path, "markdown")

        assert result == ""
        # VLM は呼ばれない
        assert not client.calls


class TestVlmRepairerThinkingLevel:
    """VlmRepairer / VlmParseRepairer の thinking_level 伝搬テスト"""

    def test_vlm_repairer_uses_configured_thinking_level(self):
        """VlmRepairer 構築時に thinking_level が get_llm_client に渡される"""
        from unittest.mock import MagicMock, patch

        with patch(
            "minitools.processors.vlm_parse_repairer.get_llm_client"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            VlmRepairer(
                provider="gemini",
                model="gemini-3-flash-preview",
                thinking_level="medium",
            )
            kwargs = mock_factory.call_args.kwargs
            assert kwargs["provider"] == "gemini"
            assert kwargs["model"] == "gemini-3-flash-preview"
            assert kwargs["thinking_level"] == "medium"

    def test_vlm_parse_repairer_propagates_thinking_level(self):
        """VlmParseRepairer から VlmRepairer まで thinking_level が伝搬する"""
        from unittest.mock import MagicMock, patch

        with patch(
            "minitools.processors.vlm_parse_repairer.get_llm_client"
        ) as mock_factory:
            mock_factory.return_value = MagicMock()
            parent = VlmParseRepairer(
                provider="gemini",
                model="gemini-3-flash-preview",
                thinking_level="medium",
            )
            assert parent.thinking_level == "medium"
            assert parent.repairer.thinking_level == "medium"
            kwargs = mock_factory.call_args.kwargs
            assert kwargs["thinking_level"] == "medium"
