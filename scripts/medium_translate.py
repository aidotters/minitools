#!/usr/bin/env python3
"""
Medium article full-text translation script.

Fetches Medium articles via Playwright, translates them using LLM,
and appends the translation to existing Notion pages.

Usage:
    uv run medium-translate --url "https://medium.com/..."
    uv run medium-translate --url "https://..." --url "https://..."
    uv run medium-translate --url "https://..." --provider openai --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from minitools.scrapers.medium_scraper import MediumScraper
from minitools.scrapers.markdown_converter import MarkdownConverter
from minitools.processors.full_text_translator import FullTextTranslator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.notion_block_builder import NotionBlockBuilder
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger

load_dotenv()

logger: logging.Logger


async def process_article(
    url: str,
    scraper: MediumScraper,
    converter: MarkdownConverter,
    translator: FullTextTranslator,
    block_builder: NotionBlockBuilder,
    publisher: NotionPublisher | None,
    database_id: str | None,
    dry_run: bool = False,
) -> str:
    """
    1記事を処理する（取得→変換→翻訳→Notion追記）

    Args:
        url: Medium記事のURL
        scraper: MediumScraperインスタンス
        converter: MarkdownConverterインスタンス
        translator: FullTextTranslatorインスタンス
        block_builder: NotionBlockBuilderインスタンス
        publisher: NotionPublisherインスタンス（dry-run時はNone可）
        database_id: NotionデータベースID（dry-run時はNone可）
        dry_run: Trueの場合Notionに保存しない

    Returns:
        処理結果（"success", "skipped", "failed"）
    """
    try:
        # 1. Notion既存ページを検索（翻訳前にチェックしてコスト節約）
        page_info = None
        if not dry_run:
            if not publisher or not database_id:
                logger.error("NotionPublisher or database_id not configured")
                return "failed"

            page_info = await publisher.find_page_by_url(database_id, url)
            if not page_info:
                logger.warning(f"Page not found for URL: {url}")
                return "skipped"

            if page_info.is_translated:
                logger.info(f"Already translated, skipping: {url}")
                return "skipped"

        # 2. 記事HTML取得
        logger.info(f"Fetching article: {url}")
        html = await scraper.scrape_article(url)
        if not html:
            logger.error(f"Failed to fetch article: {url}")
            return "failed"

        # 3. HTML→Markdown変換
        logger.info("Converting HTML to Markdown...")
        markdown = converter.convert(html)
        if not markdown:
            logger.error(f"Failed to convert HTML to Markdown: {url}")
            return "failed"
        logger.info(f"Markdown: {len(markdown)} chars")

        # 4. 全文翻訳
        logger.info("Translating full text...")
        translated = await translator.translate(markdown)
        if not translated:
            logger.error(f"Translation failed: {url}")
            return "failed"
        logger.info(f"Translated: {len(translated)} chars")

        # 5. dry-runの場合はターミナルに出力して終了
        if dry_run:
            logger.info("=" * 60)
            logger.info("[DRY RUN] Translation result:")
            logger.info("=" * 60)
            print(translated)
            logger.info("=" * 60)
            return "success"

        # 6. Markdown→Notionブロック変換
        blocks = block_builder.build_blocks(translated)
        logger.info(f"Built {len(blocks)} Notion blocks")

        # 7. Notionページに追記（dry_run=Falseの場合、上のガードで確認済み）
        assert publisher is not None
        assert page_info is not None
        success = await publisher.append_blocks(page_info.page_id, blocks)
        if success:
            await publisher.update_page_properties(
                page_info.page_id, {"Translated": {"checkbox": True}}
            )
            logger.info(f"Translation appended to Notion page: {page_info.page_id}")
            return "success"
        else:
            logger.error(f"Failed to append blocks to page: {page_info.page_id}")
            return "failed"

    except Exception as e:
        logger.error(f"Error processing {url}: {e}")
        return "failed"


async def main_async(args):
    """メイン処理（非同期版）"""
    config = get_config()
    # コンポーネントの初期化
    converter = MarkdownConverter()
    translator = FullTextTranslator(
        provider=args.provider,
        model=config.get("defaults.medium.translate_model"),
        thinking_level=config.get("defaults.medium.translate_thinking_level"),
    )
    block_builder = NotionBlockBuilder()

    # Notion設定（dry-runでない場合のみ）
    publisher = None
    database_id = None
    if not args.dry_run:
        database_id = os.getenv("NOTION_MEDIUM_DATABASE_ID") or os.getenv(
            "NOTION_DB_ID_DAILY_DIGEST"
        )
        if not database_id:
            logger.error(
                "NOTION_MEDIUM_DATABASE_ID or NOTION_DB_ID_DAILY_DIGEST not set"
            )
            return
        publisher = NotionPublisher(source_type="medium")

    # 結果統計
    stats = {"success": 0, "skipped": 0, "failed": 0}

    # Playwrightセッション内で全記事を処理
    async with MediumScraper(cdp_mode=args.cdp) as scraper:
        for i, url in enumerate(args.url):
            logger.info(f"Processing article {i + 1}/{len(args.url)}: {url}")
            result = await process_article(
                url=url,
                scraper=scraper,
                converter=converter,
                translator=translator,
                block_builder=block_builder,
                publisher=publisher,
                database_id=database_id,
                dry_run=args.dry_run,
            )
            stats[result] += 1

    # 結果サマリー
    logger.info("=" * 60)
    logger.info("Translation Summary")
    logger.info("=" * 60)
    logger.info(f"  Total:   {len(args.url)}")
    logger.info(f"  Success: {stats['success']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info(f"  Failed:  {stats['failed']}")
    logger.info("=" * 60)


def main():
    """CLIエントリーポイント"""
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Medium記事の全文を翻訳してNotionに保存",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run medium-translate --url "https://medium.com/article-slug"
  uv run medium-translate --url "https://..." --url "https://..."
  uv run medium-translate --url "https://..." --provider openai
  uv run medium-translate --url "https://..." --dry-run
        """,
    )

    parser.add_argument(
        "--url",
        type=str,
        action="append",
        required=True,
        help="翻訳するMedium記事のURL（複数指定可）",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "gemini"],
        default=config.get(
            "defaults.medium.translate_provider",
            config.get("llm.provider", "ollama"),
        ),
        help="LLMプロバイダー",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="翻訳結果をターミナルに表示するのみ（Notionに保存しない）",
    )
    parser.add_argument(
        "--cdp",
        action="store_true",
        help="実際のChromeにCDP接続（Cloudflare回避、推奨）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="デバッグモードで実行",
    )

    args = parser.parse_args()

    # ロガー初期化
    default_log_level = config.get("logging.level", "INFO").upper()
    log_level = (
        logging.DEBUG
        if args.debug
        else getattr(logging, default_log_level, logging.INFO)
    )

    global logger
    logger = setup_logger(
        "scripts.medium_translate",
        log_file="medium_translate.log",
        level=log_level,
    )

    logger.info("=" * 60)
    logger.info("Medium Full-Text Translator")
    logger.info("=" * 60)
    logger.info(f"URLs: {len(args.url)}")
    logger.info(f"Provider: {args.provider}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
