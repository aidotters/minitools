"""
VLM Parse Repairer for arxiv-translate.

marker-pdf が崩した Markdown の table/figure 領域を VLM (multimodal LLM) で
再抽出して構造を復元する。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from minitools.llm import get_llm_client
from minitools.llm.base import BaseLLMClient, LLMError
from minitools.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# パス変換ヘルパー
# ---------------------------------------------------------------------------


def repaired_output_path(raw_md_path: Path) -> Path:
    """raw markdown のパスから repaired markdown のパスを導出。

    例 (新構造): `outputs/arxiv_translate/2602.12670/raw.md`
        → `outputs/arxiv_translate/2602.12670/repaired.md`
    例 (旧フラット構造): `outputs/arxiv_translate/2602.12670_raw.md`
        → `outputs/arxiv_translate/2602.12670_repaired.md`
    """
    name = raw_md_path.name
    if name == "raw.md":
        return raw_md_path.with_name("repaired.md")
    if name.endswith("_raw.md"):
        new_name = name[: -len("_raw.md")] + "_repaired.md"
    elif name.endswith(".md"):
        new_name = name[: -len(".md")] + ".repaired.md"
    else:
        new_name = name + ".repaired.md"
    return raw_md_path.with_name(new_name)


# ---------------------------------------------------------------------------
# データ型
# ---------------------------------------------------------------------------


@dataclass
class ParseDefect:
    """検出された欠陥1件分のメタ情報"""

    kind: Literal["table", "figure", "unknown"]
    line_start: int  # 0-indexed inclusive
    line_end: int  # exclusive
    page_hint: int | None = None
    excerpt: str = ""
    image_ref: str | None = None  # figure 種別時の画像ファイル名


@dataclass
class RepairResult:
    """修復処理の結果サマリ"""

    detected: list[ParseDefect] = field(default_factory=list)
    applied: int = 0
    skipped: int = 0
    errors: int = 0
    output_path: Path | None = (
        None  # 修復済 Markdown の保存先（applied=0 / dry-run 時は None）
    )


# ---------------------------------------------------------------------------
# 定数（プロンプト）
# ---------------------------------------------------------------------------


TABLE_REPAIR_PROMPT = """以下は論文PDFから抽出されたMarkdownの一部で、テーブルの構造が崩れています。
添付のPDFページ画像を参照し、正しいMarkdownテーブル形式で再構成してください。

# 制約
- 列見出しを1行目、`|---|---|` 区切りを2行目、データ行を続けて出力
- セル内容は原文（英語）のまま、翻訳しない
- 数式は `$...$` / `$$...$$` で維持
- テーブル以外の段落や見出しは出力しない
- 出力はMarkdownコードブロック ```markdown ... ``` で囲む

# 崩れた抽出結果の抜粋
{excerpt}

# 出力
"""


FIGURE_SUMMARY_PROMPT = """以下の図をキャプションと合わせて理解し、図の主要な情報を日本語Markdownで要約してください。
- 数値・比較関係・軸ラベル・凡例の主要項目を含める
- グラフ形状/傾向を1〜2文で説明
- 出力は 50〜200字の段落1つのみ（見出しや箇条書き禁止）
- 不明確な部分は「(読み取り不能)」と明記

# キャプション
{caption}
"""


# ---------------------------------------------------------------------------
# ParseErrorDetector
# ---------------------------------------------------------------------------


_IMAGE_REF_PATTERN = re.compile(
    r"!\[[^\]]*\]\((_page_(\d+)_(?:Figure|Picture|Image)_\d+\.\w+)\)"
)
_PAGE_HINT_PATTERN = re.compile(r"_page_(\d+)_(?:Figure|Picture|Image)_\d+\.\w+")
_TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_PATTERN = re.compile(r"^\s*\|?\s*[:\-\s|]+\s*\|?\s*$")
_CONTINUED_PATTERN = re.compile(
    r"continued (?:on next page|from previous page)", re.IGNORECASE
)
_CONTINUED_NEXT_PATTERN = re.compile(r"continued on next page", re.IGNORECASE)
# 記号のみの短行（✓ / × / $\checkmark$ など）も短行ラン検出で吸収される
# （`_is_short_line` は 1〜3語かつ 50 文字未満の行を全て候補に含めるため）。


class ParseErrorDetector:
    """構文ヒューリスティックで破損候補を列挙する検出器（LLM 不使用）"""

    SHORT_LINE_MAX_WORDS = 3
    SHORT_LINE_MAX_CHARS = 50
    MIN_RUN_LENGTH = 5
    EXCERPT_PADDING = 10
    PAGE_HINT_RADIUS = 30

    def detect(self, markdown: str) -> list[ParseDefect]:
        """Markdown を走査し、破損候補のリストを返す"""
        lines = markdown.splitlines()
        defects: list[ParseDefect] = []

        defects.extend(self._detect_short_line_runs(lines))
        defects.extend(self._detect_broken_tables(lines))
        defects.extend(self._detect_continued_markers(lines))
        defects.extend(self._detect_orphan_figures(lines))

        merged = self._merge_overlapping(defects)
        for d in merged:
            d.excerpt = self._extract_excerpt(lines, d.line_start, d.line_end)
            if d.page_hint is None:
                d.page_hint = self._infer_page_hint(lines, d.line_start, d.line_end)

        return merged

    # --- 短行ラン検出 ---

    def _detect_short_line_runs(self, lines: list[str]) -> list[ParseDefect]:
        """1-3語 / 短い行が連続するブロックを検出"""
        defects: list[ParseDefect] = []
        i = 0
        n = len(lines)
        while i < n:
            if not self._is_short_line(lines[i]):
                i += 1
                continue
            run_start = i
            count = 0
            j = i
            while j < n:
                line = lines[j]
                if self._is_short_line(line):
                    count += 1
                    j += 1
                elif line.strip() == "":
                    j += 1
                else:
                    break
            if count >= self.MIN_RUN_LENGTH:
                # ラン末尾の空行を含めない
                run_end = j
                while run_end > run_start and lines[run_end - 1].strip() == "":
                    run_end -= 1
                defects.append(
                    ParseDefect(
                        kind="table",
                        line_start=run_start,
                        line_end=run_end,
                    )
                )
                i = j
            else:
                i = j if j > i else i + 1
        return defects

    def _is_short_line(self, line: str) -> bool:
        s = line.strip()
        if not s:
            return False
        if len(s) > self.SHORT_LINE_MAX_CHARS:
            return False
        # 通常の箇条書きは除外
        if s.startswith(("- ", "* ", "+ ", "> ")):
            return False
        if re.match(r"^\d+\.\s", s):
            return False
        # 見出しは除外
        if s.startswith("#"):
            return False
        # 画像参照は除外（別ロジックで処理）
        if s.startswith("!["):
            return False
        # テーブル行は除外
        if _TABLE_ROW_PATTERN.match(s):
            return False
        words = s.split()
        if len(words) > self.SHORT_LINE_MAX_WORDS:
            return False
        return True

    # --- 壊れたテーブル検出 ---

    def _detect_broken_tables(self, lines: list[str]) -> list[ParseDefect]:
        """空セル過多または列数不一致のMarkdownテーブル"""
        defects: list[ParseDefect] = []
        i = 0
        n = len(lines)
        while i < n:
            if not _TABLE_ROW_PATTERN.match(lines[i]):
                i += 1
                continue
            block_start = i
            j = i
            while j < n and (
                _TABLE_ROW_PATTERN.match(lines[j]) or _TABLE_SEP_PATTERN.match(lines[j])
            ):
                j += 1
            block_lines = lines[block_start:j]
            if len(block_lines) >= 2 and self._is_broken_table(block_lines):
                defects.append(
                    ParseDefect(
                        kind="table",
                        line_start=block_start,
                        line_end=j,
                    )
                )
            i = max(j, i + 1)
        return defects

    def _is_broken_table(self, block_lines: list[str]) -> bool:
        rows = [
            self._split_cells(line)
            for line in block_lines
            if _TABLE_ROW_PATTERN.match(line)
        ]
        if len(rows) < 2:
            return False
        widths = [len(r) for r in rows]
        # 列数不一致
        if len(set(widths)) > 1:
            return True
        # 空セル率
        total = sum(widths)
        empty = sum(1 for r in rows for c in r if not c.strip())
        if total > 0 and empty / total > 0.3:
            return True
        return False

    @staticmethod
    def _split_cells(row: str) -> list[str]:
        cells = row.strip().strip("|").split("|")
        return [c.strip() for c in cells]

    # --- continued マーカー周辺 ---

    def _detect_continued_markers(self, lines: list[str]) -> list[ParseDefect]:
        defects: list[ParseDefect] = []
        for i, line in enumerate(lines):
            if not _CONTINUED_PATTERN.search(line):
                continue
            # 前後 ±10 行を欠陥候補としてマーク
            start = max(0, i - 10)
            end = min(len(lines), i + 11)
            defects.append(
                ParseDefect(
                    kind="table",
                    line_start=start,
                    line_end=end,
                )
            )
        return defects

    # --- 孤立画像 ---

    def _detect_orphan_figures(self, lines: list[str]) -> list[ParseDefect]:
        defects: list[ParseDefect] = []
        for i, line in enumerate(lines):
            m = _IMAGE_REF_PATTERN.search(line)
            if not m:
                continue
            image_ref = m.group(1)
            page_num = int(m.group(2))
            defects.append(
                ParseDefect(
                    kind="figure",
                    line_start=i,
                    line_end=i + 1,
                    page_hint=page_num,
                    image_ref=image_ref,
                )
            )
        return defects

    # --- 共通ユーティリティ ---

    def _merge_overlapping(self, defects: list[ParseDefect]) -> list[ParseDefect]:
        """行範囲が重複する table/unknown の欠陥をマージ。figure は独立保持。"""
        if not defects:
            return []
        # figure はマージ対象外
        figures = [d for d in defects if d.kind == "figure"]
        non_figures = [d for d in defects if d.kind != "figure"]
        non_figures.sort(key=lambda d: (d.line_start, d.line_end))
        merged: list[ParseDefect] = []
        for d in non_figures:
            if merged and d.line_start <= merged[-1].line_end:
                merged[-1] = ParseDefect(
                    kind="table",
                    line_start=merged[-1].line_start,
                    line_end=max(merged[-1].line_end, d.line_end),
                    page_hint=merged[-1].page_hint or d.page_hint,
                )
            else:
                merged.append(d)
        result = merged + figures
        result.sort(key=lambda d: d.line_start)
        return result

    def _extract_excerpt(self, lines: list[str], line_start: int, line_end: int) -> str:
        start = max(0, line_start - self.EXCERPT_PADDING)
        end = min(len(lines), line_end + self.EXCERPT_PADDING)
        return "\n".join(lines[start:end])

    def _infer_page_hint(
        self, lines: list[str], line_start: int, line_end: int
    ) -> int | None:
        """欠陥位置のページヒント推定

        優先順位:
        1. ±PAGE_HINT_RADIUS 行内に画像参照があれば最近接を採用
        2. 見つからない場合、行頭方向で最も近い画像参照を基準に、
           そこから欠陥位置までの "Continued on next page" マーカー数を加算
        """
        radius = self.PAGE_HINT_RADIUS
        win_start = max(0, line_start - radius)
        win_end = min(len(lines), line_end + radius)

        # Phase 1: 近距離内の最近接ヒット
        best_page: int | None = None
        best_dist: int | None = None
        for i in range(win_start, win_end):
            m = _PAGE_HINT_PATTERN.search(lines[i])
            if not m:
                continue
            if i < line_start:
                dist = line_start - i
            elif i >= line_end:
                dist = i - line_end + 1
            else:
                dist = 0
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_page = int(m.group(1))
        if best_page is not None:
            return best_page

        # Phase 2: 広域フォールバック — 行頭方向に最も近い画像参照 +
        # その位置から欠陥位置までの "Continued on next page" 数を加算
        ref_line: int | None = None
        ref_page: int | None = None
        for i in range(line_start - 1, -1, -1):
            m = _PAGE_HINT_PATTERN.search(lines[i])
            if m:
                ref_line = i
                ref_page = int(m.group(1))
                break
        if ref_page is None or ref_line is None:
            return None

        # 欠陥範囲内に "Continued on next page" が含まれることが多いため
        # line_start ではなく line_end までカウントする。
        continued_count = sum(
            1
            for i in range(ref_line + 1, line_end)
            if _CONTINUED_NEXT_PATTERN.search(lines[i])
        )
        return ref_page + continued_count


# ---------------------------------------------------------------------------
# PdfPageRenderer
# ---------------------------------------------------------------------------


class PdfPageRenderer:
    """PyMuPDF (fitz) で PDF を PNG に変換するレンダラ（キャッシュ対応）"""

    def __init__(
        self,
        cache_dir: Path,
        max_pages_per_defect: int = 3,
    ):
        self.cache_dir = cache_dir
        self.max_pages_per_defect = max_pages_per_defect

    async def render_pages(
        self,
        pdf_path: Path,
        page_numbers: list[int],
        dpi: int = 200,
    ) -> list[bytes]:
        """指定ページを PNG 化して返す（キャッシュ参照あり）

        Args:
            pdf_path: 入力 PDF ファイルパス
            page_numbers: 0-indexed のページ番号リスト
            dpi: レンダリング DPI

        Returns:
            PNG バイト列のリスト（生成順）
        """
        if not pdf_path.exists():
            logger.error(f"PDF not found for rendering: {pdf_path}")
            return []

        if len(page_numbers) > self.max_pages_per_defect:
            logger.warning(
                f"Page count {len(page_numbers)} exceeds limit "
                f"{self.max_pages_per_defect}, truncating."
            )
            page_numbers = page_numbers[: self.max_pages_per_defect]

        return await asyncio.to_thread(self._render_sync, pdf_path, page_numbers, dpi)

    def _render_sync(
        self,
        pdf_path: Path,
        page_numbers: list[int],
        dpi: int,
    ) -> list[bytes]:
        try:
            import fitz  # type: ignore[import-untyped]
        except ImportError as e:
            logger.error(
                "PyMuPDF (fitz) is not installed. Install with: uv add pymupdf"
            )
            raise LLMError("PyMuPDF not installed") from e

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        result: list[bytes] = []

        doc = None
        try:
            for page_num in page_numbers:
                cache_path = self.cache_dir / f"page_{page_num:03d}.png"
                if cache_path.exists():
                    result.append(cache_path.read_bytes())
                    logger.debug(f"Cache hit: {cache_path}")
                    continue

                if doc is None:
                    doc = fitz.open(str(pdf_path))

                if page_num < 0 or page_num >= doc.page_count:
                    logger.warning(
                        f"Page {page_num} out of range (PDF has {doc.page_count} pages)"
                    )
                    continue

                page = doc.load_page(page_num)
                # DPI -> zoom 変換: 72 DPI が等倍
                zoom = dpi / 72.0
                matrix = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                png_bytes = pix.tobytes("png")
                cache_path.write_bytes(png_bytes)
                result.append(png_bytes)
                logger.debug(f"Rendered page {page_num} -> {cache_path}")
        finally:
            if doc is not None:
                doc.close()

        return result


# ---------------------------------------------------------------------------
# VlmRepairer
# ---------------------------------------------------------------------------


class VlmRepairer:
    """multimodal LLM 経由でテーブル復元・図要約を実行"""

    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 4, 8]
    MAX_CONCURRENT = 2

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        thinking_level: Optional[str] = None,
        client: Optional[BaseLLMClient] = None,
    ):
        if client is not None:
            self.client = client
            self.provider = provider or "custom"
        else:
            self.client = get_llm_client(
                provider=provider, model=model, thinking_level=thinking_level
            )
            self.provider = provider or "default"
        self.thinking_level = thinking_level
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)

    async def repair_table(
        self,
        defect: ParseDefect,
        page_images: list[bytes],
    ) -> str:
        """テーブル修復: VLM でテーブル断片を Markdown 形式で再生成"""
        if self.provider == "ollama":
            logger.warning("Ollama multimodal not supported; skipping repair.")
            return ""
        prompt = TABLE_REPAIR_PROMPT.format(excerpt=defect.excerpt)
        return await self._call_with_retry(prompt, page_images)

    async def repair_figure(
        self,
        defect: ParseDefect,
        page_images: list[bytes],
        caption: str,
    ) -> str:
        """図要約: VLM で日本語Markdown要約を生成"""
        if self.provider == "ollama":
            logger.warning("Ollama multimodal not supported; skipping figure summary.")
            return ""
        prompt = FIGURE_SUMMARY_PROMPT.format(caption=caption or "(no caption)")
        return await self._call_with_retry(prompt, page_images)

    async def _call_with_retry(self, prompt: str, images: list[bytes]) -> str:
        async with self._semaphore:
            last_error: Optional[Exception] = None
            for attempt in range(self.MAX_RETRIES):
                try:
                    result = await self.client.generate_from_images(
                        prompt=prompt,
                        images=images,
                    )
                    return result
                except Exception as e:
                    last_error = e
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self.RETRY_DELAYS[attempt]
                        logger.warning(
                            f"VLM call failed (attempt {attempt + 1}/{self.MAX_RETRIES}): "
                            f"{e}. Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"VLM call failed after {self.MAX_RETRIES} attempts: {e}"
                        )
            if last_error:
                raise LLMError(
                    f"VLM call failed after {self.MAX_RETRIES} attempts"
                ) from last_error
            return ""


# ---------------------------------------------------------------------------
# MarkdownPatcher
# ---------------------------------------------------------------------------


_FIGURE_NOTE_PREFIX = "> [図解説]"


class MarkdownPatcher:
    """修復済断片を raw markdown の指定範囲に反映"""

    def apply(
        self,
        markdown: str,
        patches: list[tuple[ParseDefect, str]],
    ) -> tuple[str, int, int]:
        """修復パッチを適用

        Args:
            markdown: 元のMarkdown
            patches: (ParseDefect, 修復済テキスト) のリスト

        Returns:
            (更新後のMarkdown, applied件数, skipped件数)
        """
        # 改行を保持して行分割
        lines = markdown.splitlines(keepends=True)
        # 後ろから前に処理（行番号ずれ回避）
        applied = 0
        skipped = 0
        for defect, repaired_text in sorted(
            patches, key=lambda p: p[0].line_start, reverse=True
        ):
            if not repaired_text:
                skipped += 1
                continue
            if defect.kind == "table":
                cleaned = self._strip_code_fences(repaired_text)
                if not self._validate_markdown_table(cleaned):
                    logger.warning(
                        f"Repaired table validation failed at lines "
                        f"{defect.line_start}-{defect.line_end}, keeping original."
                    )
                    skipped += 1
                    continue
                replacement = self._ensure_trailing_newline(cleaned)
                lines = (
                    lines[: defect.line_start]
                    + [replacement]
                    + lines[defect.line_end :]
                )
                applied += 1
            elif defect.kind == "figure":
                # 直後の行が既に図解説ならスキップ（冪等性）
                next_idx = defect.line_end
                if next_idx < len(lines) and lines[next_idx].lstrip().startswith(
                    _FIGURE_NOTE_PREFIX
                ):
                    skipped += 1
                    continue
                summary = repaired_text.strip()
                if not summary:
                    skipped += 1
                    continue
                note = f"\n{_FIGURE_NOTE_PREFIX} {summary}\n\n"
                lines = lines[:next_idx] + [note] + lines[next_idx:]
                applied += 1
            else:
                skipped += 1

        return "".join(lines), applied, skipped

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """````markdown ... ```` 形式のフェンスを除去"""
        s = text.strip()
        m = re.match(r"^```(?:markdown)?\s*\n(.*?)\n```\s*$", s, re.DOTALL)
        if m:
            return m.group(1).strip()
        return s

    @staticmethod
    def _ensure_trailing_newline(text: str) -> str:
        if not text.endswith("\n"):
            text = text + "\n"
        return text

    @staticmethod
    def _validate_markdown_table(text: str) -> bool:
        rows = [line for line in text.splitlines() if line.strip()]
        if len(rows) < 2:
            return False
        # `|---|`風の区切り行が必要
        sep_idx = None
        for i, row in enumerate(rows):
            if _TABLE_SEP_PATTERN.match(row) and "-" in row:
                sep_idx = i
                break
        if sep_idx is None or sep_idx == 0:
            return False
        header_cells = ParseErrorDetector._split_cells(rows[0])
        if not header_cells:
            return False
        # データ行のセル数は見出しと一致が望ましい（多少の揺らぎ許容: ±1）
        for row in rows[sep_idx + 1 :]:
            if not _TABLE_ROW_PATTERN.match(row):
                continue
            cells = ParseErrorDetector._split_cells(row)
            if abs(len(cells) - len(header_cells)) > 1:
                return False
        return True


# ---------------------------------------------------------------------------
# VlmParseRepairer (オーケストレータ)
# ---------------------------------------------------------------------------


class VlmParseRepairer:
    """VLM 修復の高レベル API: 検出→画像化→VLM呼出→Markdown更新"""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        thinking_level: Optional[str] = None,
        max_pages_per_defect: int = 3,
        max_total_calls: int = 15,
        repair_tables: bool = True,
        repair_figures: bool = True,
        dpi: int = 200,
        client: Optional[BaseLLMClient] = None,
    ):
        self.provider = provider
        self.model = model
        self.thinking_level = thinking_level
        self.max_pages_per_defect = max_pages_per_defect
        self.max_total_calls = max_total_calls
        self.repair_tables = repair_tables
        self.repair_figures = repair_figures
        self.dpi = dpi
        self.detector = ParseErrorDetector()
        self.repairer = VlmRepairer(
            provider=provider,
            model=model,
            thinking_level=thinking_level,
            client=client,
        )
        self.patcher = MarkdownPatcher()

    async def repair(
        self,
        raw_md_path: Path,
        pdf_path: Path,
        dry_run: bool = False,
    ) -> RepairResult:
        """修復処理の主入口

        Args:
            raw_md_path: 修復対象の raw markdown (本ファイルは上書きしない)
            pdf_path: 対応する元PDF
            dry_run: True の場合、検出のみで Markdown 書き換えなし

        Returns:
            RepairResult。`applied > 0` の場合、修復結果は
            `repaired_output_path(raw_md_path)` に保存される。
        """
        if not raw_md_path.exists():
            logger.error(f"Raw markdown not found: {raw_md_path}")
            return RepairResult()

        markdown = raw_md_path.read_text(encoding="utf-8")
        defects = self.detector.detect(markdown)
        logger.info(f"Detected {len(defects)} parse defects in {raw_md_path.name}")

        if dry_run:
            for d in defects:
                preview = d.excerpt[:100].replace("\n", " ")
                logger.info(
                    f"[DRY RUN] kind={d.kind} lines={d.line_start}-{d.line_end} "
                    f"page={d.page_hint} excerpt='{preview}...'"
                )
            return RepairResult(detected=defects)

        if not pdf_path.exists():
            logger.error(f"PDF not found, cannot run VLM repair: {pdf_path}")
            return RepairResult(detected=defects)

        # コストキャップ: 検出件数を上限に丸める（figureを優先削減）
        budgeted = self._apply_budget(defects)

        # PdfPageRenderer のキャッシュは論文フォルダ直下の page_images/ に格納
        cache_dir = pdf_path.parent / "page_images"
        renderer = PdfPageRenderer(
            cache_dir=cache_dir,
            max_pages_per_defect=self.max_pages_per_defect,
        )

        # 各defectをVLMにかける（並行制御は VlmRepairer 内 Semaphore）
        tasks = [
            self._repair_one(defect, renderer, pdf_path, markdown)
            for defect in budgeted
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        patches: list[tuple[ParseDefect, str]] = []
        errors = 0
        for defect, repaired in zip(budgeted, results):
            if isinstance(repaired, Exception):
                logger.warning(f"VLM repair error for {defect.kind}: {repaired}")
                errors += 1
                continue
            if isinstance(repaired, str) and repaired:
                patches.append((defect, repaired))

        new_markdown, applied, skipped = self.patcher.apply(markdown, patches)

        output_path: Path | None = None
        if applied > 0:
            output_path = repaired_output_path(raw_md_path)
            output_path.write_text(new_markdown, encoding="utf-8")
            logger.info(
                f"Repaired markdown saved to: {output_path} "
                f"(original {raw_md_path.name} unchanged) "
                f"({applied} applied, {skipped} skipped, {errors} errors)"
            )
        else:
            logger.info(f"No patches applied ({skipped} skipped, {errors} errors)")

        return RepairResult(
            detected=defects,
            applied=applied,
            skipped=skipped,
            errors=errors,
            output_path=output_path,
        )

    def _apply_budget(self, defects: list[ParseDefect]) -> list[ParseDefect]:
        """コストキャップを適用: tables を優先、figures を後ろから削除"""
        if len(defects) <= self.max_total_calls:
            tables = [d for d in defects if d.kind == "table"]
            figures = [d for d in defects if d.kind == "figure"]
            if not self.repair_tables:
                tables = []
            if not self.repair_figures:
                figures = []
            return tables + figures

        tables = [d for d in defects if d.kind == "table"]
        figures = [d for d in defects if d.kind == "figure"]
        if not self.repair_tables:
            tables = []
        if not self.repair_figures:
            figures = []

        budget = self.max_total_calls
        budgeted: list[ParseDefect] = []
        for d in tables:
            if budget <= 0:
                break
            budgeted.append(d)
            budget -= 1
        for d in figures:
            if budget <= 0:
                break
            budgeted.append(d)
            budget -= 1
        if len(budgeted) < len(defects):
            orig_tables = sum(1 for d in defects if d.kind == "table")
            orig_figures = sum(1 for d in defects if d.kind == "figure")
            budgeted_tables = sum(1 for d in budgeted if d.kind == "table")
            budgeted_figures = sum(1 for d in budgeted if d.kind == "figure")
            logger.warning(
                f"VLM call budget {self.max_total_calls} reached; "
                f"{len(defects) - len(budgeted)} defects skipped "
                f"(table: {orig_tables - budgeted_tables}, "
                f"figure: {orig_figures - budgeted_figures})."
            )
        return budgeted

    async def _repair_one(
        self,
        defect: ParseDefect,
        renderer: PdfPageRenderer,
        pdf_path: Path,
        markdown: str,
    ) -> str:
        page_numbers: list[int] = []
        if defect.page_hint is not None:
            page_numbers = [defect.page_hint]
            # テーブルが連続ページにまたがる場合は次ページも追加
            if defect.kind == "table":
                page_numbers.append(defect.page_hint + 1)

        if not page_numbers:
            logger.warning(
                f"No page hint for defect at lines "
                f"{defect.line_start}-{defect.line_end}, skipping."
            )
            return ""

        images = await renderer.render_pages(
            pdf_path=pdf_path,
            page_numbers=page_numbers,
            dpi=self.dpi,
        )
        if not images:
            return ""

        if defect.kind == "table":
            return await self.repairer.repair_table(defect, images)
        elif defect.kind == "figure":
            caption = self._extract_caption(markdown, defect)
            return await self.repairer.repair_figure(defect, images, caption)
        return ""

    @staticmethod
    def _extract_caption(markdown: str, defect: ParseDefect) -> str:
        """画像参照の直後にあるキャプション風の行を抽出"""
        lines = markdown.splitlines()
        for j in range(defect.line_end, min(defect.line_end + 3, len(lines))):
            line = lines[j].strip()
            if line and not line.startswith("!["):
                return line[:300]
        return ""
