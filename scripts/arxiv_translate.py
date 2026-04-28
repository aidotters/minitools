#!/usr/bin/env python3
"""
ArXiv paper full-text translation script.

Supports both full pipeline and individual step execution:

    # Full pipeline (backward compatible)
    uv run arxiv-translate --url "https://arxiv.org/abs/2401.12345"
    uv run arxiv-translate --url "https://..." --provider openai --dry-run

    # Individual steps
    uv run arxiv-translate parse     --url "https://arxiv.org/abs/2401.12345"
    uv run arxiv-translate translate --url "https://arxiv.org/abs/2401.12345"
    uv run arxiv-translate upload    --url "https://arxiv.org/abs/2401.12345"
"""

import argparse
import asyncio
import json
import logging
import mimetypes
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from minitools.scrapers.arxiv_scraper import ArxivScraper, PaperMetadata
from minitools.processors.full_text_translator import FullTextTranslator
from minitools.processors.vlm_parse_repairer import (
    VlmParseRepairer,
    repaired_output_path,
)
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.notion_block_builder import NotionBlockBuilder
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger

load_dotenv()

logger: logging.Logger

OUTPUT_DIR = Path("outputs/arxiv_translate")


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------


def resolve_paths(url: str) -> tuple[str, Path, Path, Path]:
    """URLからファイルパスを解決する

    Returns:
        (safe_id, raw_path, translated_path, metadata_path)

    各論文は ``outputs/arxiv_translate/{safe_id}/`` 直下にまとめて配置される。
    """
    arxiv_id = ArxivScraper.extract_arxiv_id(url) or "unknown"
    safe_id = arxiv_id.replace("/", "_")
    paper_dir = OUTPUT_DIR / safe_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    return (
        safe_id,
        paper_dir / "raw.md",
        paper_dir / "translated.md",
        paper_dir / "metadata.json",
    )


def resolve_pdf_path(url: str) -> Path:
    """URLからPDFファイルパスを解決する"""
    arxiv_id = ArxivScraper.extract_arxiv_id(url) or "unknown"
    safe_id = arxiv_id.replace("/", "_")
    paper_dir = OUTPUT_DIR / safe_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    # PDF はフォルダ外に持ち出した際の識別性を確保するため safe_id を維持
    return paper_dir / f"{safe_id}.pdf"


def save_metadata(metadata: PaperMetadata, path: Path) -> None:
    """PaperMetadataをJSONファイルに保存"""
    path.write_text(
        json.dumps(asdict(metadata), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_metadata(path: Path) -> PaperMetadata | None:
    """JSONファイルからPaperMetadataを読み込み"""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PaperMetadata(**data)
    except Exception as e:
        logger.warning(f"Failed to load metadata from {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# ステップ関数
# ---------------------------------------------------------------------------


async def step_parse(
    url: str,
    scraper: ArxivScraper,
    enable_repair: bool = True,
    repairer: VlmParseRepairer | None = None,
) -> str:
    """Step 1: PDF取得→Markdown変換→メタデータ保存→（任意）VLM修復

    Args:
        url: arxiv URL
        scraper: ArxivScraper インスタンス
        enable_repair: True の場合、PDF を永続化して VLM 修復を実行
        repairer: enable_repair=True 時の VlmParseRepairer インスタンス

    Returns:
        "success", "skipped", "failed"
    """
    if not scraper.validate_arxiv_url(url):
        logger.error(f"ArXiv URLではありません: {url}")
        return "failed"

    safe_id, raw_path, _, metadata_path = resolve_paths(url)
    pdf_path = resolve_pdf_path(url)

    if raw_path.exists():
        logger.info(f"Raw markdown already exists, skipping parse: {raw_path}")
        return "skipped"

    logger.info(f"Fetching and parsing paper: {url}")
    paper = await scraper.fetch_and_parse(url)
    if not paper:
        logger.error(f"Failed to fetch/parse paper: {url}")
        return "failed"

    logger.info(f"Markdown: {len(paper.markdown)} chars")
    if paper.metadata:
        logger.info(f"Title: {paper.metadata.title}")
    if paper.images:
        # 画像はマーカー由来の裸ファイル名のまま論文フォルダ直下に保存。
        # markdown 内の image refs (`![](_page_X_Figure_Y.jpeg)`) と一致するため
        # ローカルプレビューもそのまま動作する。
        images_dir = OUTPUT_DIR / safe_id
        images_dir.mkdir(parents=True, exist_ok=True)
        for img in paper.images:
            safe_name = Path(img.filename).name
            (images_dir / safe_name).write_bytes(img.data)
        logger.info(f"Saved {len(paper.images)} images to {images_dir}")

    # 保存
    raw_path.write_text(paper.markdown, encoding="utf-8")
    logger.info(f"Raw markdown saved to: {raw_path}")

    if paper.metadata:
        save_metadata(paper.metadata, metadata_path)
        logger.info(f"Metadata saved to: {metadata_path}")

    # PDF永続化（修復有効時のみ）
    if enable_repair and paper.pdf_bytes:
        pdf_path.write_bytes(paper.pdf_bytes)
        logger.info(f"PDF persisted to: {pdf_path}")

    # VLM 修復実行
    if enable_repair and repairer is not None and pdf_path.exists():
        logger.info("Running VLM parse repair...")
        try:
            repair_result = await repairer.repair(raw_path, pdf_path)
            logger.info(
                f"Repair result: detected={len(repair_result.detected)}, "
                f"applied={repair_result.applied}, "
                f"skipped={repair_result.skipped}, "
                f"errors={repair_result.errors}"
            )
        except Exception as e:
            logger.warning(f"VLM repair failed but parse succeeded: {e}")

    return "success"


async def step_repair(
    url: str,
    repairer: VlmParseRepairer,
    dry_run: bool = False,
) -> str:
    """Step (optional): raw.md と PDF が既に存在する状態で VLM 修復のみ再実行"""
    _, raw_path, _, _ = resolve_paths(url)
    pdf_path = resolve_pdf_path(url)

    if not raw_path.exists():
        logger.error(
            f"Raw markdown not found: {raw_path}\n"
            f'  Run `arxiv-translate parse --url "{url}"` first.'
        )
        return "failed"

    if not pdf_path.exists() and not dry_run:
        logger.error(
            f"PDF not found: {pdf_path}\n"
            f'  Re-run `arxiv-translate parse --url "{url}"` to fetch the PDF.'
        )
        return "failed"

    try:
        result = await repairer.repair(raw_path, pdf_path, dry_run=dry_run)
    except Exception as e:
        logger.error(f"VLM repair failed: {e}")
        return "failed"

    logger.info(
        f"Repair result: detected={len(result.detected)}, "
        f"applied={result.applied}, "
        f"skipped={result.skipped}, "
        f"errors={result.errors}"
    )
    return "success"


async def step_translate(url: str, translator: FullTextTranslator) -> str:
    """Step 2: 翻訳前Markdown→日本語翻訳→保存

    Returns:
        "success", "skipped", "failed"
    """
    _, raw_path, translated_path, _ = resolve_paths(url)

    if translated_path.exists():
        logger.info(f"Translation already exists, skipping: {translated_path}")
        return "skipped"

    if not raw_path.exists():
        logger.error(
            f"Raw markdown not found: {raw_path}\n"
            f'  Run `arxiv-translate parse --url "{url}"` first.'
        )
        return "failed"

    # 修復済 repaired.md があれば優先（VLM 修復後の翻訳用）
    repaired_path = repaired_output_path(raw_path)
    source_path = repaired_path if repaired_path.exists() else raw_path
    raw_markdown = source_path.read_text(encoding="utf-8")
    logger.info(f"Loaded markdown: {len(raw_markdown)} chars from {source_path}")

    logger.info("Translating full text...")
    translated = await translator.translate(raw_markdown)
    if not translated:
        logger.error(f"Translation failed: {url}")
        return "failed"
    logger.info(f"Translated: {len(translated)} chars")

    translated_path.write_text(translated, encoding="utf-8")
    logger.info(f"Translation saved to: {translated_path}")
    return "success"


async def step_upload(
    url: str,
    block_builder: NotionBlockBuilder,
    publisher: NotionPublisher | None,
    database_id: str | None,
    dry_run: bool = False,
    translator: FullTextTranslator | None = None,
) -> str:
    """Step 3: 翻訳済みMarkdown→Notion保存

    Returns:
        "success", "skipped", "failed"
    """
    safe_id, _, translated_path, metadata_path = resolve_paths(url)

    if not translated_path.exists():
        logger.error(
            f"Translated markdown not found: {translated_path}\n"
            f'  Run `arxiv-translate translate --url "{url}"` first.'
        )
        return "failed"

    translated = translated_path.read_text(encoding="utf-8")
    logger.info(f"Loaded translation: {len(translated)} chars from {translated_path}")

    # dry-run
    if dry_run:
        logger.info("=" * 60)
        logger.info("[DRY RUN] Translation result:")
        logger.info("=" * 60)
        print(translated)
        logger.info("=" * 60)
        # dry-run でもブロック数を確認
        blocks = block_builder.build_blocks(translated)
        logger.info(f"[DRY RUN] Built {len(blocks)} Notion blocks")
        return "success"

    # Notion設定チェック
    if not publisher or not database_id:
        logger.error("NotionPublisher or database_id not configured")
        return "failed"

    # Notion翻訳済みチェック
    page_info = await publisher.find_page_by_url(database_id, url)
    if page_info and page_info.is_translated:
        logger.info(f"Already translated in Notion, skipping: {url}")
        return "skipped"

    # 画像アップロード（論文フォルダ直下から拡張子で抽出）
    image_uploads: dict[str, str] = {}
    images_dir = OUTPUT_DIR / safe_id
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    if images_dir.exists():
        image_files = sorted(
            p
            for p in images_dir.iterdir()
            if p.is_file() and p.suffix.lower() in image_exts
        )
        if image_files:
            logger.info(f"Uploading {len(image_files)} images from {images_dir}")
            for img_path in image_files:
                mime, _ = mimetypes.guess_type(img_path.name)
                upload_id = await publisher.upload_file(img_path, mime)
                if upload_id:
                    image_uploads[img_path.name] = upload_id
            logger.info(f"Uploaded {len(image_uploads)} images successfully")
        else:
            logger.info(f"No images found in {images_dir}, skipping uploads")
    else:
        logger.info(f"Paper directory not found at {images_dir}, skipping uploads")

    # ブロック変換（画像アップロードマッピングを渡す）
    blocks = block_builder.build_blocks(translated, image_uploads=image_uploads)
    logger.info(f"Built {len(blocks)} Notion blocks")

    # メタデータ読み込み（metadata.json から、なければAPI）
    metadata = load_metadata(metadata_path)
    if not metadata:
        arxiv_id = ArxivScraper.extract_arxiv_id(url)
        if arxiv_id:
            async with ArxivScraper() as scraper:
                metadata = await scraper.fetch_metadata(arxiv_id)

    # Abstract 翻訳
    japanese_summary: str | None = None
    if translator and metadata and metadata.abstract:
        try:
            logger.info("Translating abstract for 日本語訳 property...")
            translated_abstract = await translator.translate(metadata.abstract)
            if translated_abstract:
                japanese_summary = translated_abstract[:2000]
        except Exception as e:
            logger.warning(f"Abstract translation failed: {e}")

    if page_info:
        # 既存ページに追記
        success = await publisher.append_blocks(page_info.page_id, blocks)
        if success:
            await _update_after_upload(publisher, page_info.page_id, japanese_summary)
            logger.info(f"Translation appended to Notion page: {page_info.page_id}")
            return "success"
        else:
            logger.error(f"Failed to append blocks to page: {page_info.page_id}")
            return "failed"
    else:
        # 新規ページを作成
        properties = _build_new_page_properties(url, metadata, japanese_summary)
        page_id = await publisher.create_page(database_id, properties)
        if not page_id:
            logger.error(f"Failed to create Notion page for: {url}")
            return "failed"

        success = await publisher.append_blocks(page_id, blocks)
        if success:
            await _update_after_upload(publisher, page_id, japanese_summary)
            logger.info(f"New Notion page created and translated: {page_id}")
            return "success"
        else:
            logger.error(f"Failed to append blocks to new page: {page_id}")
            return "failed"


# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------


async def _update_after_upload(
    publisher: NotionPublisher,
    page_id: str,
    japanese_summary: str | None = None,
) -> None:
    """アップロード後にTranslatedフラグと日本語訳プロパティを更新する

    プロパティが存在しない場合は警告のみで処理を続行する。
    """
    properties: dict = {"Translated": {"checkbox": True}}
    if japanese_summary:
        properties["日本語訳"] = {
            "rich_text": [{"text": {"content": japanese_summary[:2000]}}]
        }
    try:
        await publisher.update_page_properties(page_id, properties)
    except Exception as e:
        logger.warning(f"プロパティ更新をスキップ（プロパティが存在しない可能性）: {e}")


def _build_new_page_properties(
    url: str,
    metadata: PaperMetadata | None,
    japanese_summary: str | None = None,
) -> dict:
    """新規ページ用のNotionプロパティを構築（メタデータがあればリッチに）"""
    url_normalized = url.replace("http://", "https://").replace(
        "export.arxiv.org", "arxiv.org"
    )

    if metadata:
        properties: dict = {
            "タイトル": {"title": [{"text": {"content": metadata.title}}]},
            "URL": {"url": url_normalized},
        }
        if metadata.authors:
            authors_str = ", ".join(metadata.authors)
            properties["概要"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": f"Authors: {authors_str}\n\n{metadata.abstract}"[
                                :2000
                            ]
                        }
                    }
                ]
            }
        if metadata.published:
            properties["公開日"] = {"date": {"start": metadata.published}}
        if japanese_summary:
            properties["日本語訳"] = {
                "rich_text": [{"text": {"content": japanese_summary[:2000]}}]
            }
        return properties
    else:
        arxiv_id = ArxivScraper.extract_arxiv_id(url) or url
        properties = {
            "タイトル": {"title": [{"text": {"content": arxiv_id}}]},
            "URL": {"url": url_normalized},
        }
        if japanese_summary:
            properties["日本語訳"] = {
                "rich_text": [{"text": {"content": japanese_summary[:2000]}}]
            }
        return properties


def _log_summary(total: int, stats: dict) -> None:
    """結果サマリーをログ出力"""
    logger.info("=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    logger.info(f"  Total:   {total}")
    logger.info(f"  Success: {stats['success']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info(f"  Failed:  {stats['failed']}")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# エントリポイント（サブコマンド別）
# ---------------------------------------------------------------------------


def _build_repairer(args) -> VlmParseRepairer | None:
    """設定とCLI引数からVlmParseRepairerを構築（修復無効時はNone）"""
    config = get_config()
    enabled = config.get("arxiv_translate.vlm_repair.enabled", True)
    if getattr(args, "no_vlm_repair", False):
        enabled = False
    if not enabled:
        return None
    provider = (
        getattr(args, "provider", None)
        or config.get("arxiv_translate.vlm_repair.provider")
        or config.get("defaults.arxiv_translate.provider", "gemini")
    )
    cli_max_total = getattr(args, "max_total_calls", None)
    max_total_calls = (
        cli_max_total
        if cli_max_total is not None
        else config.get("arxiv_translate.vlm_repair.max_total_calls", 25)
    )
    return VlmParseRepairer(
        provider=provider,
        model=config.get("arxiv_translate.vlm_repair.model"),
        max_pages_per_defect=config.get(
            "arxiv_translate.vlm_repair.max_pages_per_defect", 3
        ),
        max_total_calls=max_total_calls,
        repair_tables=config.get("arxiv_translate.vlm_repair.repair_tables", True),
        repair_figures=config.get("arxiv_translate.vlm_repair.repair_figures", True),
        dpi=config.get("arxiv_translate.vlm_repair.dpi", 200),
    )


async def main_parse(args):
    """parse サブコマンド: PDF→Markdown(+VLM修復)"""
    stats = {"success": 0, "skipped": 0, "failed": 0}
    repairer = _build_repairer(args)
    enable_repair = repairer is not None
    async with ArxivScraper() as scraper:
        for i, url in enumerate(args.url):
            logger.info(f"[parse] Paper {i + 1}/{len(args.url)}: {url}")
            result = await step_parse(
                url, scraper, enable_repair=enable_repair, repairer=repairer
            )
            stats[result] += 1
    _log_summary(len(args.url), stats)


async def main_repair(args):
    """repair サブコマンド: 既存の raw.md に対し VLM 修復のみ実行"""
    repairer = _build_repairer(args)
    if repairer is None:
        logger.error(
            "VLM repair is disabled in settings.yaml; cannot run repair subcommand."
        )
        return
    stats = {"success": 0, "skipped": 0, "failed": 0}
    for i, url in enumerate(args.url):
        logger.info(f"[repair] Paper {i + 1}/{len(args.url)}: {url}")
        result = await step_repair(url, repairer, dry_run=args.dry_run)
        stats[result] += 1
    _log_summary(len(args.url), stats)


async def main_translate(args):
    """translate サブコマンド: Markdown→日本語翻訳"""
    translator = FullTextTranslator(provider=args.provider)
    stats = {"success": 0, "skipped": 0, "failed": 0}
    for i, url in enumerate(args.url):
        logger.info(f"[translate] Paper {i + 1}/{len(args.url)}: {url}")
        result = await step_translate(url, translator)
        stats[result] += 1
    _log_summary(len(args.url), stats)


async def main_upload(args):
    """upload サブコマンド: 翻訳済みMarkdown→Notion保存"""
    block_builder = NotionBlockBuilder()
    publisher = None
    database_id = None
    translator = FullTextTranslator(provider=args.provider)

    if not args.dry_run:
        database_id = os.getenv("NOTION_ARXIV_DATABASE_ID") or os.getenv(
            "NOTION_DB_ID_ARXIV"
        )
        if not database_id:
            logger.error("NOTION_ARXIV_DATABASE_ID or NOTION_DB_ID_ARXIV not set")
            return
        publisher = NotionPublisher(source_type="arxiv")

    stats = {"success": 0, "skipped": 0, "failed": 0}
    for i, url in enumerate(args.url):
        logger.info(f"[upload] Paper {i + 1}/{len(args.url)}: {url}")
        result = await step_upload(
            url,
            block_builder,
            publisher,
            database_id,
            args.dry_run,
            translator=translator,
        )
        stats[result] += 1
    _log_summary(len(args.url), stats)


async def main_pipeline(args):
    """全パイプライン: parse→translate→upload"""
    translator = FullTextTranslator(provider=args.provider)
    block_builder = NotionBlockBuilder()
    repairer = _build_repairer(args)
    enable_repair = repairer is not None

    publisher = None
    database_id = None
    if not args.dry_run:
        database_id = os.getenv("NOTION_ARXIV_DATABASE_ID") or os.getenv(
            "NOTION_DB_ID_ARXIV"
        )
        if not database_id:
            logger.error("NOTION_ARXIV_DATABASE_ID or NOTION_DB_ID_ARXIV not set")
            return
        publisher = NotionPublisher(source_type="arxiv")

    stats = {"success": 0, "skipped": 0, "failed": 0}

    async with ArxivScraper() as scraper:
        for i, url in enumerate(args.url):
            logger.info(f"Processing paper {i + 1}/{len(args.url)}: {url}")

            # Step 1: parse
            result = await step_parse(
                url, scraper, enable_repair=enable_repair, repairer=repairer
            )
            if result == "failed":
                stats["failed"] += 1
                continue

            # Step 2: translate
            result = await step_translate(url, translator)
            if result == "failed":
                stats["failed"] += 1
                continue

            # Step 3: upload
            result = await step_upload(
                url,
                block_builder,
                publisher,
                database_id,
                args.dry_run,
                translator=translator,
            )
            stats[result] += 1

    _log_summary(len(args.url), stats)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    """CLIエントリーポイント"""
    config = get_config()

    default_provider = config.get(
        "defaults.arxiv_translate.provider",
        config.get("llm.provider", "gemini"),
    )

    parser = argparse.ArgumentParser(
        description="ArXiv論文の全文を翻訳してNotionに保存",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline
  uv run arxiv-translate --url "https://arxiv.org/abs/2401.12345"
  uv run arxiv-translate --url "https://..." --provider openai --dry-run

  # Individual steps
  uv run arxiv-translate parse     --url "https://arxiv.org/abs/2401.12345"
  uv run arxiv-translate translate --url "https://arxiv.org/abs/2401.12345"
  uv run arxiv-translate upload    --url "https://arxiv.org/abs/2401.12345"
        """,
    )

    # 全パイプライン用の引数（サブコマンドなしの場合）
    parser.add_argument(
        "--url", type=str, action="append", help="ArXiv論文のURL（複数指定可）"
    )
    parser.add_argument(
        "--provider", choices=["ollama", "openai", "gemini"], default=default_provider
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--no-vlm-repair",
        action="store_true",
        help="VLM によるパース欠陥修復をスキップする",
    )
    parser.add_argument(
        "--max-total-calls",
        type=int,
        default=None,
        help="VLM 修復の1論文あたり呼び出し上限（settings.yaml の値を上書き）",
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    # parse
    sp_parse = subparsers.add_parser("parse", help="PDF→Markdown変換(+VLM修復)")
    sp_parse.add_argument(
        "--url", type=str, action="append", required=True, help="ArXiv論文のURL"
    )
    sp_parse.add_argument(
        "--provider",
        choices=["ollama", "openai", "gemini"],
        default=default_provider,
        help="VLM 修復用 LLM プロバイダ",
    )
    sp_parse.add_argument("--debug", action="store_true")
    sp_parse.add_argument(
        "--no-vlm-repair",
        action="store_true",
        help="VLM によるパース欠陥修復をスキップする",
    )
    sp_parse.add_argument(
        "--max-total-calls",
        type=int,
        default=None,
        help="VLM 修復の1論文あたり呼び出し上限（settings.yaml の値を上書き）",
    )

    # translate
    sp_translate = subparsers.add_parser("translate", help="Markdown→日本語翻訳のみ")
    sp_translate.add_argument(
        "--url", type=str, action="append", required=True, help="ArXiv論文のURL"
    )
    sp_translate.add_argument(
        "--provider", choices=["ollama", "openai", "gemini"], default=default_provider
    )
    sp_translate.add_argument("--debug", action="store_true")

    # upload
    sp_upload = subparsers.add_parser("upload", help="翻訳済みMarkdown→Notion保存のみ")
    sp_upload.add_argument(
        "--url", type=str, action="append", required=True, help="ArXiv論文のURL"
    )
    sp_upload.add_argument(
        "--provider",
        choices=["ollama", "openai", "gemini"],
        default=default_provider,
        help="Abstract 日本語訳用のLLMプロバイダ",
    )
    sp_upload.add_argument("--dry-run", action="store_true")
    sp_upload.add_argument("--debug", action="store_true")

    # repair
    sp_repair = subparsers.add_parser(
        "repair", help="既存 raw.md に対し VLM 修復のみ実行"
    )
    sp_repair.add_argument(
        "--url", type=str, action="append", required=True, help="ArXiv論文のURL"
    )
    sp_repair.add_argument(
        "--provider",
        choices=["ollama", "openai", "gemini"],
        default=default_provider,
        help="VLM 修復用 LLM プロバイダ",
    )
    sp_repair.add_argument(
        "--dry-run",
        action="store_true",
        help="検出のみログ出力し、raw.md は変更しない",
    )
    sp_repair.add_argument(
        "--max-total-calls",
        type=int,
        default=None,
        help="VLM 修復の1論文あたり呼び出し上限（settings.yaml の値を上書き）",
    )
    sp_repair.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    # サブコマンドなしで--urlも指定なしの場合はヘルプ表示
    if not args.subcommand and not args.url:
        parser.print_help()
        return

    # ロガー初期化
    default_log_level = config.get("logging.level", "INFO").upper()
    log_level = (
        logging.DEBUG
        if args.debug
        else getattr(logging, default_log_level, logging.INFO)
    )

    global logger
    logger = setup_logger(
        "scripts.arxiv_translate",
        log_file="arxiv_translate.log",
        level=log_level,
    )

    logger.info("=" * 60)
    logger.info("ArXiv Full-Text Translator (PDF + marker-pdf)")
    logger.info("=" * 60)
    logger.info(f"Mode: {args.subcommand or 'full pipeline'}")
    logger.info(f"URLs: {len(args.url)}")
    logger.info("=" * 60)

    if args.subcommand == "parse":
        asyncio.run(main_parse(args))
    elif args.subcommand == "translate":
        asyncio.run(main_translate(args))
    elif args.subcommand == "upload":
        asyncio.run(main_upload(args))
    elif args.subcommand == "repair":
        asyncio.run(main_repair(args))
    else:
        asyncio.run(main_pipeline(args))


if __name__ == "__main__":
    main()
