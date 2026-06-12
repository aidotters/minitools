#!/usr/bin/env python3
"""
Medium article scraper — outputs English Markdown to stdout.

Usage:
    uv run scrape-medium --url "https://medium.com/..."
    uv run scrape-medium --url "https://medium.com/..." --cdp
    uv run scrape-medium --url "https://medium.com/..." --cdp --emit-meta
"""

import argparse
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from dotenv import load_dotenv
from minitools.scrapers.article_dates import ArticleDates, empty_dates
from minitools.scrapers.medium_scraper import MediumScraper
from minitools.scrapers.markdown_converter import MarkdownConverter

load_dotenv()


def _redirect_logging_to_stderr() -> None:
    """既存ロガーの stdout ハンドラを stderr に向け直し、stdout を Markdown 専用に保つ。"""
    loggers = [logging.getLogger()] + [
        logging.getLogger(name) for name in logging.root.manager.loggerDict
    ]
    for lg in loggers:
        for handler in getattr(lg, "handlers", []):
            if (
                isinstance(handler, logging.StreamHandler)
                and getattr(handler, "stream", None) is sys.stdout
            ):
                handler.stream = sys.stderr


_redirect_logging_to_stderr()


async def scrape(url: str, cdp: bool) -> tuple[str, ArticleDates]:
    """Medium 記事を取得して (Markdown, 元日付メタ) を返す。

    本文取得失敗時は ``("", empty_dates())`` を返す。
    """
    converter = MarkdownConverter()
    async with MediumScraper(cdp_mode=cdp) as scraper:
        html = await scraper.scrape_article(url)
        dates: ArticleDates = dict(scraper.last_dates)  # type: ignore[assignment]
    if not html:
        return "", empty_dates()
    return converter.convert(html), dates


def _build_frontmatter(dates: ArticleDates) -> str:
    """元日付メタを YAML フロントマターブロックに整形する。

    値域は llm-wiki Phase 5 schema に合わせ ``YYYY-MM-DD|unknown``、
    source は ``html-meta|unknown``。取得不能フィールドは ``unknown``。
    """
    published = dates.get("published_at") or "unknown"
    modified = dates.get("last_modified") or "unknown"
    return (
        "---\n"
        f"published_at: {published}\n"
        f"last_modified: {modified}\n"
        f"published_at_source: {dates.get('published_at_source') or 'unknown'}\n"
        f"last_modified_source: {dates.get('last_modified_source') or 'unknown'}\n"
        "---\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape a Medium article and output English Markdown to stdout."
    )
    parser.add_argument("--url", required=True, help="Medium article URL")
    parser.add_argument(
        "--cdp",
        action="store_true",
        help="Use Chrome CDP mode (requires Chrome with Medium login session)",
    )
    parser.add_argument(
        "--emit-meta",
        action="store_true",
        help=(
            "Prepend a YAML frontmatter block with published_at / last_modified "
            "date metadata (for llm-wiki ingest). Default off (body-only output)."
        ),
    )
    args = parser.parse_args()

    markdown, dates = asyncio.run(scrape(args.url, args.cdp))
    if not markdown:
        print(f"ERROR: failed to scrape {args.url}", file=sys.stderr)
        sys.exit(1)

    if args.emit_meta:
        print(_build_frontmatter(dates) + markdown)
    else:
        print(markdown)


if __name__ == "__main__":
    main()
