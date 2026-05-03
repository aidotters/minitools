#!/usr/bin/env python3
"""
Google Alerts article full-text translation script.

Fetches arbitrary Google Alerts URLs via Jina AI Reader, translates them
to Japanese using LLM, and stores the result in the Google Alerts Notion
database. Existing pages are appended to; missing pages are created.

Usage:
    uv run google-alerts-translate --url "https://example.com/article"
    uv run google-alerts-translate --url "https://..." --url "https://..."
    uv run google-alerts-translate --url "https://..." --provider openai --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from minitools.llm import BaseLLMClient, get_llm_client
from minitools.processors.full_text_translator import FullTextTranslator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.notion_block_builder import NotionBlockBuilder
from minitools.scrapers.jina_reader import JinaReader
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger, setup_logger

load_dotenv()

logger: logging.Logger = get_logger("scripts.google_alerts_translate")

# Notion rich_text の最大文字数
NOTION_TEXT_LIMIT = 2000

# 要約生成時に LLM へ渡す最大文字数
SUMMARY_INPUT_LIMIT = 3000

# 要約 LLM 失敗時の fallback 抜粋長
SUMMARY_FALLBACK_LENGTH = 200

TITLE_TRANSLATION_PROMPT = (
    "以下の英語タイトルを、ニュース記事として自然な日本語タイトルに簡潔に訳してください。"
    "出力はタイトル文字列のみで、補足説明や引用符は不要です。\n\nタイトル: {title}"
)

SUMMARY_PROMPT = (
    "以下の日本語記事本文から、200文字程度の簡潔な要約を作成してください。"
    "本文の主旨を漏らさず、重要なキーワードを残してください。"
    "出力は要約のみで、見出しや前置きは不要です。\n\n本文:\n{text}"
)


def _extract_domain(url: str) -> str:
    """URL からドメインを抽出する（``www.`` 接頭辞を除去、小文字化）"""
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _fallback_title_from_url(url: str) -> str:
    """URL のパス末尾を読みやすい文字列にして返す（タイトル不明時の fallback）"""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return url
    last = parts[-1]
    # 拡張子除去
    if "." in last:
        last = last.rsplit(".", 1)[0]
    last = last.replace("-", " ").replace("_", " ").strip()
    return last or url


async def _translate_title(english_title: str, llm_client: BaseLLMClient) -> str:
    """英語タイトルを 1 行で日本語化。失敗時は英語タイトルを返す"""
    try:
        result = await llm_client.chat(
            messages=[
                {
                    "role": "user",
                    "content": TITLE_TRANSLATION_PROMPT.format(title=english_title),
                }
            ]
        )
        japanese = result.strip().splitlines()[0].strip() if result else ""
        if japanese:
            return japanese
    except Exception as e:
        logger.warning(f"Title translation failed: {e}")
    return english_title


async def _summarize_japanese(japanese_markdown: str, llm_client: BaseLLMClient) -> str:
    """日本語本文の冒頭から 200 文字程度の要約を生成。失敗時は冒頭抜粋"""
    text = japanese_markdown.strip()[:SUMMARY_INPUT_LIMIT]
    if not text:
        return ""
    try:
        result = await llm_client.chat(
            messages=[{"role": "user", "content": SUMMARY_PROMPT.format(text=text)}]
        )
        summary = result.strip() if result else ""
        if summary:
            return summary
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
    return text[:SUMMARY_FALLBACK_LENGTH]


async def build_new_page_metadata(
    url: str,
    english_markdown: str,
    japanese_markdown: str,
    jina_metadata: Dict[str, Optional[str]],
    llm_client: BaseLLMClient,
) -> Dict[str, Any]:
    """新規ページ用の中間メタデータ辞書を構築する

    Returns:
        {
            "title": str,                  # 英語タイトル
            "japanese_title": str,         # 日本語タイトル
            "url": str,                    # 元 URL（正規化前）
            "source": str,                 # ドメイン
            "japanese_summary": str,       # 200 文字要約
            "date": "YYYY-MM-DD",
        }
    """
    english_title = jina_metadata.get("title") or _fallback_title_from_url(url)

    japanese_title = await _translate_title(english_title, llm_client)
    japanese_summary = await _summarize_japanese(japanese_markdown, llm_client)

    published_at = jina_metadata.get("published_at")
    date = published_at if published_at else datetime.now().strftime("%Y-%m-%d")

    return {
        "title": english_title,
        "japanese_title": japanese_title,
        "url": url,
        "source": _extract_domain(url),
        "japanese_summary": japanese_summary,
        "date": date,
    }


def build_new_page_properties(
    metadata: Dict[str, Any], normalized_url: str
) -> Dict[str, Any]:
    """Notion API に渡す新規ページの properties dict を構築する

    ``Translated: True`` を含め、``create_page`` 1 回で完結する形にする。
    """
    japanese_title = metadata.get("japanese_title") or metadata.get("title", "")
    english_title = metadata.get("title", "")
    summary = metadata.get("japanese_summary", "")[:NOTION_TEXT_LIMIT]
    source = metadata.get("source", "")
    date = metadata.get("date") or datetime.now().strftime("%Y-%m-%d")

    properties: Dict[str, Any] = {
        "Title": {"title": [{"text": {"content": japanese_title}}]},
        "Original Title": {"rich_text": [{"text": {"content": english_title}}]},
        "URL": {"url": normalized_url},
        "Source": {"rich_text": [{"text": {"content": source}}]},
        "Summary": {"rich_text": [{"text": {"content": summary}}]},
        "Snippet": {"rich_text": [{"text": {"content": ""}}]},
        "Date": {"date": {"start": date}},
        "Tags": {"multi_select": []},
        "Translated": {"checkbox": True},
    }
    return properties


async def ensure_translated_property(
    publisher: NotionPublisher, database_id: str
) -> bool:
    """DB に ``Translated`` (checkbox) プロパティが存在するか確認する"""
    try:
        db = await publisher._retry_api_call(
            lambda: publisher.client.databases.retrieve(database_id=database_id),
            description="ensure_translated_property",
        )
    except Exception as e:
        logger.error(f"Failed to retrieve database schema: {e}")
        return False

    properties = cast(Dict[str, Any], db).get("properties", {}) if db else {}
    if "Translated" not in properties:
        logger.error(
            "Notion DB に 'Translated' (checkbox) プロパティが見つかりません。"
            "DB に手動で追加してから再実行してください。"
        )
        return False
    return True


async def process_url(
    url: str,
    jina: JinaReader,
    translator: FullTextTranslator,
    block_builder: NotionBlockBuilder,
    publisher: Optional[NotionPublisher],
    database_id: Optional[str],
    llm_client: BaseLLMClient,
    dry_run: bool = False,
) -> str:
    """1 URL を処理する（取得→翻訳→Notion 反映）

    Returns:
        ``"success"`` / ``"skipped"`` / ``"failed"``
    """
    try:
        # 1. 既存ページ検索（dry-run 時はスキップ）
        page_info = None
        if not dry_run:
            if not publisher or not database_id:
                logger.error("NotionPublisher or database_id not configured")
                return "failed"

            page_info = await publisher.find_page_by_url(database_id, url)
            if page_info and page_info.is_translated:
                logger.warning(f"Already translated, skipping: {url}")
                return "skipped"

        # 2. Jina AI Reader で英語 Markdown 取得
        logger.info(f"Fetching article via Jina: {url}")
        english_markdown = await jina.fetch_markdown(url)
        if not english_markdown:
            logger.error(f"Failed to fetch article: {url}")
            return "failed"
        logger.info(f"Fetched {len(english_markdown)} chars")

        # 3. メタデータ抽出
        jina_metadata = JinaReader.extract_metadata(english_markdown)

        # 4. 全文翻訳
        logger.info("Translating full text...")
        japanese_markdown = await translator.translate(english_markdown)
        if not japanese_markdown:
            logger.error(f"Translation failed: {url}")
            return "failed"
        logger.info(f"Translated: {len(japanese_markdown)} chars")

        # 5. dry-run の場合はターミナル出力で終了
        if dry_run:
            logger.info("=" * 60)
            logger.info("[DRY RUN] Translation result:")
            logger.info("=" * 60)
            print(japanese_markdown)
            logger.info("=" * 60)
            return "success"

        assert publisher is not None
        assert database_id is not None

        # 6. 既存ページがある場合: 本文追記 + Translated 更新
        if page_info is not None:
            blocks = block_builder.build_blocks(japanese_markdown)
            logger.info(f"Built {len(blocks)} Notion blocks (with leading divider)")
            success = await publisher.append_blocks(page_info.page_id, blocks)
            if not success:
                logger.error(f"Failed to append blocks to page: {page_info.page_id}")
                return "failed"
            await publisher.update_page_properties(
                page_info.page_id, {"Translated": {"checkbox": True}}
            )
            logger.info(f"Translation appended to existing page: {page_info.page_id}")
            return "success"

        # 7. 新規ページ作成
        normalized_url = publisher._normalize_url_by_source(url)
        metadata = await build_new_page_metadata(
            url=url,
            english_markdown=english_markdown,
            japanese_markdown=japanese_markdown,
            jina_metadata=jina_metadata,
            llm_client=llm_client,
        )
        properties = build_new_page_properties(metadata, normalized_url)
        page_id = await publisher.create_page(database_id, properties)
        if not page_id:
            logger.error(f"Failed to create new Notion page: {url}")
            return "failed"

        blocks = block_builder.build_blocks(japanese_markdown)
        if blocks and blocks[0].get("type") == "divider":
            blocks = blocks[1:]
        logger.info(f"Built {len(blocks)} Notion blocks (no leading divider)")

        success = await publisher.append_blocks(page_id, blocks)
        if not success:
            logger.error(f"Failed to append blocks to new page: {page_id}")
            return "failed"

        logger.info(f"New page created with translation: {page_id}")
        return "success"

    except Exception as e:
        logger.error(f"Error processing {url}: {e}")
        return "failed"


async def main_async(args: argparse.Namespace) -> None:
    """非同期メイン処理"""
    config = get_config()
    jina = JinaReader()
    translate_model = config.get("defaults.google_alerts.translate_model")
    translate_thinking_level = config.get(
        "defaults.google_alerts.translate_thinking_level"
    )
    translator = FullTextTranslator(
        provider=args.provider,
        model=translate_model,
        thinking_level=translate_thinking_level,
    )
    block_builder = NotionBlockBuilder()
    llm_client = get_llm_client(
        provider=args.provider,
        model=translate_model,
        thinking_level=translate_thinking_level,
    )

    publisher: Optional[NotionPublisher] = None
    database_id: Optional[str] = None
    if not args.dry_run:
        database_id = os.getenv("NOTION_GOOGLE_ALERTS_DATABASE_ID") or os.getenv(
            "NOTION_DB_ID_GOOGLE_ALERTS"
        )
        if not database_id:
            logger.error(
                "NOTION_GOOGLE_ALERTS_DATABASE_ID or NOTION_DB_ID_GOOGLE_ALERTS not set"
            )
            return
        publisher = NotionPublisher(source_type="google_alerts")
        if not await ensure_translated_property(publisher, database_id):
            return

    stats: Dict[str, int] = {"success": 0, "skipped": 0, "failed": 0}

    urls: List[str] = args.url
    for i, url in enumerate(urls):
        logger.info(f"Processing article {i + 1}/{len(urls)}: {url}")
        result = await process_url(
            url=url,
            jina=jina,
            translator=translator,
            block_builder=block_builder,
            publisher=publisher,
            database_id=database_id,
            llm_client=llm_client,
            dry_run=args.dry_run,
        )
        stats[result] += 1

    logger.info("=" * 60)
    logger.info("Translation Summary")
    logger.info("=" * 60)
    logger.info(f"  Total:   {len(urls)}")
    logger.info(f"  Success: {stats['success']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info(f"  Failed:  {stats['failed']}")
    logger.info("=" * 60)


def main() -> None:
    """CLI エントリーポイント"""
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Google Alerts記事の全文を翻訳してNotionに保存",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run google-alerts-translate --url "https://example.com/article"
  uv run google-alerts-translate --url "https://..." --url "https://..."
  uv run google-alerts-translate --url "https://..." --provider openai
  uv run google-alerts-translate --url "https://..." --dry-run
        """,
    )

    parser.add_argument(
        "--url",
        type=str,
        action="append",
        required=True,
        help="翻訳する記事のURL（複数指定可）",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "gemini"],
        default=config.get(
            "defaults.google_alerts.translate_provider",
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
        "--debug",
        action="store_true",
        help="デバッグモードで実行",
    )

    args = parser.parse_args()

    default_log_level = config.get("logging.level", "INFO").upper()
    log_level = (
        logging.DEBUG
        if args.debug
        else getattr(logging, default_log_level, logging.INFO)
    )

    global logger
    logger = setup_logger(
        "scripts.google_alerts_translate",
        log_file="google_alerts_translate.log",
        level=log_level,
    )

    logger.info("=" * 60)
    logger.info("Google Alerts Full-Text Translator")
    logger.info("=" * 60)
    logger.info(f"URLs: {len(args.url)}")
    logger.info(f"Provider: {args.provider}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
