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
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from minitools.scrapers.arxiv_scraper import ArxivScraper, PaperMetadata
from minitools.processors.full_text_translator import FullTextTranslator
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
    """
    arxiv_id = ArxivScraper.extract_arxiv_id(url) or "unknown"
    safe_id = arxiv_id.replace("/", "_")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return (
        safe_id,
        OUTPUT_DIR / f"{safe_id}_raw.md",
        OUTPUT_DIR / f"{safe_id}.md",
        OUTPUT_DIR / f"{safe_id}_metadata.json",
    )


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


async def step_parse(url: str, scraper: ArxivScraper) -> str:
    """Step 1: PDF取得→Markdown変換→メタデータ保存

    Returns:
        "success", "skipped", "failed"
    """
    if not scraper.validate_arxiv_url(url):
        logger.error(f"ArXiv URLではありません: {url}")
        return "failed"

    _, raw_path, _, metadata_path = resolve_paths(url)

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
        logger.info(
            f"Images: {len(paper.images)} extracted "
            "(will be skipped — Notion file upload API not available)"
        )

    # 保存
    raw_path.write_text(paper.markdown, encoding="utf-8")
    logger.info(f"Raw markdown saved to: {raw_path}")

    if paper.metadata:
        save_metadata(paper.metadata, metadata_path)
        logger.info(f"Metadata saved to: {metadata_path}")

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

    raw_markdown = raw_path.read_text(encoding="utf-8")
    logger.info(f"Loaded raw markdown: {len(raw_markdown)} chars from {raw_path}")

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
) -> str:
    """Step 3: 翻訳済みMarkdown→Notion保存

    Returns:
        "success", "skipped", "failed"
    """
    _, _, translated_path, metadata_path = resolve_paths(url)

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

    # ブロック変換
    blocks = block_builder.build_blocks(translated)
    logger.info(f"Built {len(blocks)} Notion blocks")

    # メタデータ読み込み（_metadata.jsonから、なければAPI）
    metadata = load_metadata(metadata_path)
    if not metadata:
        arxiv_id = ArxivScraper.extract_arxiv_id(url)
        if arxiv_id:
            async with ArxivScraper() as scraper:
                metadata = await scraper.fetch_metadata(arxiv_id)

    if page_info:
        # 既存ページに追記
        success = await publisher.append_blocks(page_info.page_id, blocks)
        if success:
            await _update_translated_flag(publisher, page_info.page_id)
            logger.info(f"Translation appended to Notion page: {page_info.page_id}")
            return "success"
        else:
            logger.error(f"Failed to append blocks to page: {page_info.page_id}")
            return "failed"
    else:
        # 新規ページを作成
        properties = _build_new_page_properties(url, metadata)
        page_id = await publisher.create_page(database_id, properties)
        if not page_id:
            logger.error(f"Failed to create Notion page for: {url}")
            return "failed"

        success = await publisher.append_blocks(page_id, blocks)
        if success:
            await _update_translated_flag(publisher, page_id)
            logger.info(f"New Notion page created and translated: {page_id}")
            return "success"
        else:
            logger.error(f"Failed to append blocks to new page: {page_id}")
            return "failed"


# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------


async def _update_translated_flag(publisher: NotionPublisher, page_id: str) -> None:
    """Translatedプロパティを更新する（プロパティが存在しない場合は警告のみ）"""
    try:
        await publisher.update_page_properties(
            page_id, {"Translated": {"checkbox": True}}
        )
    except Exception as e:
        logger.warning(
            f"Translatedプロパティの更新をスキップ（プロパティが存在しない可能性）: {e}"
        )


def _build_new_page_properties(url: str, metadata: PaperMetadata | None) -> dict:
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
        return properties
    else:
        arxiv_id = ArxivScraper.extract_arxiv_id(url) or url
        return {
            "タイトル": {"title": [{"text": {"content": arxiv_id}}]},
            "URL": {"url": url_normalized},
        }


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


async def main_parse(args):
    """parse サブコマンド: PDF→Markdown"""
    stats = {"success": 0, "skipped": 0, "failed": 0}
    async with ArxivScraper() as scraper:
        for i, url in enumerate(args.url):
            logger.info(f"[parse] Paper {i + 1}/{len(args.url)}: {url}")
            result = await step_parse(url, scraper)
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
            url, block_builder, publisher, database_id, args.dry_run
        )
        stats[result] += 1
    _log_summary(len(args.url), stats)


async def main_pipeline(args):
    """全パイプライン: parse→translate→upload"""
    translator = FullTextTranslator(provider=args.provider)
    block_builder = NotionBlockBuilder()

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
            result = await step_parse(url, scraper)
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
                url, block_builder, publisher, database_id, args.dry_run
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

    subparsers = parser.add_subparsers(dest="subcommand")

    # parse
    sp_parse = subparsers.add_parser("parse", help="PDF→Markdown変換のみ")
    sp_parse.add_argument(
        "--url", type=str, action="append", required=True, help="ArXiv論文のURL"
    )
    sp_parse.add_argument("--debug", action="store_true")

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
    sp_upload.add_argument("--dry-run", action="store_true")
    sp_upload.add_argument("--debug", action="store_true")

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
    else:
        asyncio.run(main_pipeline(args))


if __name__ == "__main__":
    main()
