#!/usr/bin/env python3
"""
Medium article scraper — outputs English Markdown to stdout.

Usage:
    uv run scrape-medium --url "https://medium.com/..."
    uv run scrape-medium --url "https://medium.com/..." --cdp
"""

import argparse
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from dotenv import load_dotenv
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


async def scrape(url: str, cdp: bool) -> str:
    """Medium 記事を取得して Markdown を返す。失敗時は空文字列を返す。"""
    converter = MarkdownConverter()
    async with MediumScraper(cdp_mode=cdp) as scraper:
        html = await scraper.scrape_article(url)
    if not html:
        return ""
    return converter.convert(html)


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
    args = parser.parse_args()

    markdown = asyncio.run(scrape(args.url, args.cdp))
    if not markdown:
        print(f"ERROR: failed to scrape {args.url}", file=sys.stderr)
        sys.exit(1)

    print(markdown)


if __name__ == "__main__":
    main()
