#!/usr/bin/env python3
"""
Discover recent Medium articles from Notion DB and output JSON to stdout.

Usage:
    uv run discover-notion-medium
    uv run discover-notion-medium --days 3
    uv run discover-notion-medium --days 7 --database-id "abc123"
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from dotenv import load_dotenv
from minitools.readers.notion import NotionReader

load_dotenv()


def _redirect_logging_to_stderr() -> None:
    """既存ロガーの stdout ハンドラを stderr に向け直し、stdout を JSON 専用に保つ。"""
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


async def discover(days: int, database_id: str) -> list[dict]:
    reader = NotionReader()
    today = datetime.now(tz=timezone.utc)
    start = today - timedelta(days=days)
    articles = await reader.get_articles_by_date_range(
        database_id=database_id,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=today.strftime("%Y-%m-%d"),
    )

    results = []
    for a in articles:
        results.append(
            {
                "url": a.get("url") or "",
                "title": a.get("title") or "",
                "japanese_title": a.get("japanese_title") or "",
                "claps": a.get("claps") or 0,
                "summary": a.get("summary") or "",
                "date": _extract_date(a.get("date") or ""),
                "author": a.get("author") or "",
            }
        )

    results.sort(key=lambda x: x["date"], reverse=True)
    return results


def _extract_date(value: object) -> str:
    """date フィールドの値を YYYY-MM-DD 文字列に正規化する。"""
    if not value:
        return ""
    if isinstance(value, dict):
        value = value.get("start") or ""
    s = str(value)
    return s[:10] if len(s) >= 10 else s


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover recent Medium articles from Notion DB (JSON output)."
    )
    parser.add_argument(
        "--days", type=int, default=7, help="How many days back to query (default: 7)"
    )
    parser.add_argument(
        "--database-id", default=None, help="Notion database ID (overrides env var)"
    )
    args = parser.parse_args()

    api_key = os.getenv("NOTION_API_KEY")
    if not api_key:
        print("ERROR: NOTION_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    database_id = (
        args.database_id
        or os.getenv("NOTION_MEDIUM_DATABASE_ID")
        or os.getenv("NOTION_DB_ID_DAILY_DIGEST")
    )
    if not database_id:
        print(
            "ERROR: database ID is required (--database-id or NOTION_MEDIUM_DATABASE_ID env var)",
            file=sys.stderr,
        )
        sys.exit(1)

    articles = asyncio.run(discover(args.days, database_id))
    print(json.dumps(articles, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
