#!/usr/bin/env python3
"""
Medium article full-text translation script.

Fetches Medium articles via Playwright, translates them using LLM,
and either appends the translation to an existing Notion page or creates
a new page when the URL is not yet registered in the Medium DB.

Usage:
    uv run medium-translate --url "https://medium.com/..."
    uv run medium-translate --url "https://..." --url "https://..."
    uv run medium-translate --url "https://..." --provider openai --dry-run
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from minitools.llm import BaseLLMClient, get_llm_client
from minitools.scrapers.medium_scraper import MediumScraper
from minitools.scrapers.markdown_converter import MarkdownConverter
from minitools.processors.full_text_translator import FullTextTranslator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.notion_block_builder import NotionBlockBuilder
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger, setup_logger

load_dotenv()

logger: logging.Logger = get_logger("scripts.medium_translate")

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


def _fallback_title_from_url(url: str) -> str:
    """URL のパス末尾を読みやすい文字列にして返す（タイトル不明時の fallback）"""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return url
    last = parts[-1]
    # Medium スラグの hash 部分を除去（例: title-slug-abc123def → title-slug）
    last = re.sub(r"-[0-9a-f]{8,}$", "", last)
    last = last.replace("-", " ").replace("_", " ").strip()
    return last or url


def _normalize_medium_display_date(value: str) -> Optional[str]:
    """Medium の ``data-testid="storyPublishDate"`` 表示形式を ``YYYY-MM-DD`` に変換

    例: ``"Feb 11, 2026"`` / ``"February 11, 2026"`` → ``"2026-02-11"``。
    年が省略された当年表記 ``"Feb 11"`` は実行年を補う。失敗時 None。
    """
    if not value:
        return None
    text = value.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    for fmt in ("%b %d", "%B %d"):
        try:
            dt = datetime.strptime(text, fmt).replace(year=datetime.now().year)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_clap_count(text: str) -> Optional[int]:
    """``"55"`` / ``"1.2K"`` / ``"3M"`` 形式の文字列を整数に変換。失敗時 None"""
    if not text:
        return None
    cleaned = text.strip().replace(",", "")
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KkMm]?)$", cleaned)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    suffix = match.group(2).upper()
    if suffix == "K":
        number *= 1_000
    elif suffix == "M":
        number *= 1_000_000
    return int(number)


def _extract_clap_count_from_html(html: str) -> Optional[int]:
    """``headerClapButton`` 近傍の数値ボタンから clap 数を抽出

    Medium 記事ページの構造: clap アイコンボタン (``data-testid="headerClapButton"``)
    の後続に ``<button>...数値...</button>`` が現れる。SVG を含むボタンを除外し、
    純テキストの数値を持つ最初のボタンを採用する。
    """
    if not html:
        return None
    anchor = html.find('data-testid="headerClapButton"')
    if anchor < 0:
        return None
    # 後続 3000 文字以内を走査
    window = html[anchor : anchor + 3000]
    for match in re.finditer(r"<button[^>]*>(.*?)</button>", window, re.DOTALL):
        inner = match.group(1)
        if "<svg" in inner:
            continue
        text = re.sub(r"<[^>]+>", "", inner).strip()
        count = _parse_clap_count(text)
        if count is not None:
            return count
    return None


def _normalize_iso_date(value: Optional[str]) -> Optional[str]:
    """ISO 8601 文字列を ``YYYY-MM-DD`` に正規化。失敗時は None"""
    if not value:
        return None
    try:
        # ``Z`` は ``+00:00`` に変換して datetime.fromisoformat に渡せるようにする
        cleaned = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        # 末尾のタイムゾーン情報を切り捨てて再試行
        match = re.match(r"(\d{4}-\d{2}-\d{2})", value.strip())
        if match:
            return match.group(1)
        return None


def _extract_from_json_ld(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    """JSON-LD ブロックから author / published_at を抽出する"""
    result: Dict[str, Optional[str]] = {"author": None, "published_at": None}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = script.string or script.get_text()
            if not raw:
                continue
            data = json.loads(raw)
        except Exception:
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if result["author"] is None:
                author = item.get("author")
                if isinstance(author, dict):
                    name = author.get("name")
                    if isinstance(name, str) and name.strip():
                        result["author"] = name.strip()
                elif isinstance(author, list) and author:
                    first = author[0]
                    if isinstance(first, dict):
                        name = first.get("name")
                        if isinstance(name, str) and name.strip():
                            result["author"] = name.strip()
                elif isinstance(author, str) and author.strip():
                    result["author"] = author.strip()
            if result["published_at"] is None:
                published = item.get("datePublished")
                if isinstance(published, str) and published.strip():
                    result["published_at"] = published.strip()
            if result["author"] and result["published_at"]:
                return result
    return result


def _extract_medium_metadata(html: str, url: str) -> Dict[str, Any]:
    """Medium 記事 HTML から ``title`` / ``author`` / ``published_at`` を抽出する

    抽出失敗時は個別フィールドに fallback 値（``Unknown`` や URL 由来の文字列）を入れて返す。
    例外は呼び出し元へ投げない。
    """
    title: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None

    try:
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception as e:
        logger.warning(f"Failed to parse HTML for metadata extraction: {e}")
        soup = None

    def _meta_content(tag: Any) -> Optional[str]:
        if not tag:
            return None
        content = tag.get("content")
        if isinstance(content, str):
            value = content.strip()
            return value or None
        return None

    if soup is not None:
        title = _meta_content(soup.find("meta", attrs={"property": "og:title"}))
        if not title:
            title_tag = soup.find("title")
            if title_tag and title_tag.get_text(strip=True):
                title = title_tag.get_text(strip=True)
        if not title:
            story_title = soup.find(attrs={"data-testid": "storyTitle"})
            if story_title and story_title.get_text(strip=True):
                title = story_title.get_text(strip=True)

        author = _meta_content(soup.find("meta", attrs={"name": "author"}))

        if not author:
            author_tag = soup.find(attrs={"data-testid": "authorName"})
            if author_tag and author_tag.get_text(strip=True):
                author = author_tag.get_text(strip=True)

        if not author:
            photo_tag = soup.find(attrs={"data-testid": "authorPhoto"})
            if photo_tag:
                alt = photo_tag.get("alt") if hasattr(photo_tag, "get") else None
                if isinstance(alt, str) and alt.strip():
                    author = alt.strip()
                else:
                    img = photo_tag.find("img") if hasattr(photo_tag, "find") else None
                    if img:
                        alt = img.get("alt")
                        if isinstance(alt, str) and alt.strip():
                            author = alt.strip()

        if not author or not published_at:
            jsonld = _extract_from_json_ld(soup)
            if not author:
                author = jsonld.get("author")
            if not published_at:
                published_at = jsonld.get("published_at")

        if not author:
            author = _meta_content(
                soup.find("meta", attrs={"property": "article:author"})
            )

        if not published_at:
            published_at = _meta_content(
                soup.find("meta", attrs={"property": "article:published_time"})
            )

        if not published_at:
            date_tag = soup.find(attrs={"data-testid": "storyPublishDate"})
            if date_tag and date_tag.get_text(strip=True):
                display = date_tag.get_text(strip=True)
                published_at = _normalize_medium_display_date(display) or display

    if not title:
        title = _fallback_title_from_url(url)

    normalized_date = _normalize_iso_date(
        published_at
    ) or _normalize_medium_display_date(published_at or "")

    claps = _extract_clap_count_from_html(html or "")

    return {
        "title": title,
        "author": author or "Unknown",
        "published_at": normalized_date,
        "claps": claps,
    }


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
    japanese_markdown: str,
    html_metadata: Dict[str, Any],
    llm_client: BaseLLMClient,
) -> Dict[str, Any]:
    """新規ページ用の中間メタデータ辞書を構築する

    Returns:
        {
            "title": str,              # 英語タイトル
            "japanese_title": str,     # 日本語タイトル
            "url": str,                # 元 URL（正規化前）
            "author": str,             # 著者名
            "japanese_summary": str,   # 200 文字要約
            "date": "YYYY-MM-DD",
        }
    """
    english_title = html_metadata.get("title") or _fallback_title_from_url(url)
    japanese_title = await _translate_title(english_title, llm_client)
    japanese_summary = await _summarize_japanese(japanese_markdown, llm_client)

    published_at = html_metadata.get("published_at")
    date = published_at if published_at else datetime.now().strftime("%Y-%m-%d")

    claps = html_metadata.get("claps")
    if not isinstance(claps, int) or claps < 0:
        claps = None

    return {
        "title": english_title,
        "japanese_title": japanese_title,
        "url": url,
        "author": html_metadata.get("author") or "Unknown",
        "japanese_summary": japanese_summary,
        "date": date,
        "claps": claps,
    }


def build_new_page_properties(
    metadata: Dict[str, Any], normalized_url: str
) -> Dict[str, Any]:
    """Notion API に渡す Medium DB 用 properties dict を構築する

    ``Translated: True`` を含め、``create_page`` 1 回で完結する形にする。
    """
    english_title = metadata.get("title", "")
    japanese_title = metadata.get("japanese_title") or english_title
    summary = (metadata.get("japanese_summary") or "")[:NOTION_TEXT_LIMIT]
    author = metadata.get("author") or "Unknown"
    date = metadata.get("date") or datetime.now().strftime("%Y-%m-%d")

    properties: Dict[str, Any] = {
        "Title": {"title": [{"text": {"content": english_title}}]},
        "Japanese Title": {"rich_text": [{"text": {"content": japanese_title}}]},
        "URL": {"url": normalized_url},
        "Author": {"rich_text": [{"text": {"content": author}}]},
        "Date": {"date": {"start": date}},
        "Summary": {"rich_text": [{"text": {"content": summary}}]},
        "Translated": {"checkbox": True},
    }
    claps = metadata.get("claps")
    if isinstance(claps, int) and claps >= 0:
        properties["Claps"] = {"number": claps}
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


async def process_article(
    url: str,
    scraper: MediumScraper,
    converter: MarkdownConverter,
    translator: FullTextTranslator,
    block_builder: NotionBlockBuilder,
    publisher: Optional[NotionPublisher],
    database_id: Optional[str],
    llm_client: Optional[BaseLLMClient],
    dry_run: bool = False,
    dump_html_dir: Optional[Path] = None,
) -> str:
    """1記事を処理する（取得→変換→翻訳→Notion 反映）

    既存ページがあれば本文 append + Translated 更新。
    既存ページがなければ新規ページを作成して本文を投入。

    Returns:
        ``"success"`` / ``"skipped"`` / ``"failed"``
    """
    try:
        # 1. Notion 既存ページ検索（dry-run 時はスキップ）
        page_info = None
        if not dry_run:
            if not publisher or not database_id:
                logger.error("NotionPublisher or database_id not configured")
                return "failed"

            page_info = await publisher.find_page_by_url(database_id, url)
            if page_info and page_info.is_translated:
                logger.info(f"Already translated, skipping: {url}")
                return "skipped"

        # 2. 記事 HTML 取得
        logger.info(f"Fetching article: {url}")
        html = await scraper.scrape_article(url)
        if not html:
            logger.error(f"Failed to fetch article: {url}")
            return "failed"

        # 2.5 デバッグ用に HTML をダンプ
        if dump_html_dir is not None:
            try:
                dump_html_dir.mkdir(parents=True, exist_ok=True)
                slug_parts = [p for p in urlparse(url).path.split("/") if p]
                slug = slug_parts[-1] if slug_parts else "article"
                slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", slug)[:120] or "article"
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dump_path = dump_html_dir / f"{timestamp}_{slug}.html"
                dump_path.write_text(html, encoding="utf-8")
                logger.info(f"[DEBUG] HTML dumped to: {dump_path}")
            except Exception as e:
                logger.warning(f"Failed to dump HTML: {e}")

        # 3. HTML→Markdown 変換
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

        # 5. dry-run の場合はターミナル出力で終了
        if dry_run:
            logger.info("=" * 60)
            logger.info("[DRY RUN] Translation result:")
            logger.info("=" * 60)
            print(translated)
            logger.info("=" * 60)
            return "success"

        assert publisher is not None
        assert database_id is not None

        # 6. 既存ページがある場合: 本文追記 + Translated 更新
        if page_info is not None:
            blocks = block_builder.build_blocks(translated)
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
        if llm_client is None:
            logger.error("LLM client is required for new page creation")
            return "failed"

        html_metadata = _extract_medium_metadata(html, url)
        metadata = await build_new_page_metadata(
            url=url,
            japanese_markdown=translated,
            html_metadata=html_metadata,
            llm_client=llm_client,
        )
        normalized_url = publisher._normalize_url_by_source(url)
        properties = build_new_page_properties(metadata, normalized_url)
        page_id = await publisher.create_page(database_id, properties)
        if not page_id:
            logger.error(f"Failed to create new Notion page: {url}")
            return "failed"

        blocks = block_builder.build_blocks(translated)
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
    """メイン処理（非同期版）"""
    config = get_config()
    translate_model = config.get("defaults.medium.translate_model")
    translate_thinking_level = config.get("defaults.medium.translate_thinking_level")

    converter = MarkdownConverter()
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
        database_id = os.getenv("NOTION_MEDIUM_DATABASE_ID") or os.getenv(
            "NOTION_DB_ID_DAILY_DIGEST"
        )
        if not database_id:
            logger.error(
                "NOTION_MEDIUM_DATABASE_ID or NOTION_DB_ID_DAILY_DIGEST not set"
            )
            return
        publisher = NotionPublisher(source_type="medium")
        if not await ensure_translated_property(publisher, database_id):
            return

    stats: Dict[str, int] = {"success": 0, "skipped": 0, "failed": 0}

    dump_html_dir: Optional[Path] = None
    if args.debug:
        dump_html_dir = Path("outputs/medium_translate_debug")
        logger.info(f"[DEBUG] HTML dump directory: {dump_html_dir}")

    urls: List[str] = args.url
    async with MediumScraper(cdp_mode=args.cdp) as scraper:
        for i, url in enumerate(urls):
            logger.info(f"Processing article {i + 1}/{len(urls)}: {url}")
            result = await process_article(
                url=url,
                scraper=scraper,
                converter=converter,
                translator=translator,
                block_builder=block_builder,
                publisher=publisher,
                database_id=database_id,
                llm_client=llm_client,
                dry_run=args.dry_run,
                dump_html_dir=dump_html_dir,
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
