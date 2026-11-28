#!/usr/bin/env python3
"""
Google Alerts が届かなかった期間のニュースを、Google ニュースの検索で取り戻して Notion に保存する。

使い方:
    uv run google-alerts-backfill --from 2026-11-20 --to 2026-11-26 --dry-run
    uv run google-alerts-backfill --from 2026-11-20 --to 2026-11-26

--dry-run では検索と URL の復元だけを行い、本文取得・翻訳・Notion 保存はしない。
既に Notion にある URL は、本文取得と翻訳の前に1件ずつ確かめて外す（取り戻しを再実行したとき、
保存済みの記事をもう一度翻訳しない）。期間が通常のアラートと重なってもよい。
Notion のレート制限に当たらないよう、確認も保存も1件ずつ行う。
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
import logging
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv

from minitools.collectors.google_alerts import GoogleAlertsCollector
from minitools.collectors.google_news_backfill import GoogleNewsBackfillCollector
from minitools.publishers.notion import NotionPublisher
from minitools.utils.logger import setup_logger
from minitools.utils.network import wait_for_network
from scripts import google_alerts

load_dotenv()


def main():
    asyncio.run(main_async())


# 1件ごとの Notion への問い合わせの間隔（秒）。Notion の上限は平均で毎秒3回
NOTION_CHECK_INTERVAL = 0.4


async def drop_already_saved(
    alerts, publisher, database_id, logger, interval=NOTION_CHECK_INTERVAL
):
    """Notion に既にある URL を外す。確認は1件ずつ行う。

    check_existing は問い合わせに失敗すると「ある」とみなす（安全のためスキップ）ので、
    その記事はこの実行では処理されず、次の実行で拾われる。
    """
    remaining = []
    for i, alert in enumerate(alerts):
        if i and interval:
            await asyncio.sleep(interval)
        if not await publisher.check_existing(database_id, alert.url):
            remaining.append(alert)
    logger.info(
        f"Notion に既にある（または確かめられなかった）{len(alerts) - len(remaining)}件を外しました。"
        f"残り {len(remaining)}件を処理します"
    )
    return remaining


def _parse_day(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("日付は YYYY-MM-DD 形式で指定してください")


async def main_async():
    parser = argparse.ArgumentParser(
        description="届かなかった期間の Google Alerts を Google ニュース検索で取り戻す"
    )
    parser.add_argument("--from", dest="start", type=_parse_day, required=True)
    parser.add_argument("--to", dest="end", type=_parse_day, required=True)
    parser.add_argument(
        "--per-keyword",
        type=int,
        default=10,
        help="キーワードごと1日あたりの上限（既定 10＝通常のアラートメールのニュース欄と同じくらい）",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="検索だけして件数と見出しを表示する"
    )
    parser.add_argument(
        "--output",
        help="dry-run の一覧（TSV: 日付・ソース・見出し・URL）を書き出すファイル。省略時は標準出力",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.end < args.start:
        parser.error("--to は --from 以降の日付にしてください")

    logger = setup_logger(
        "scripts.google_alerts_backfill",
        log_file="google_alerts_backfill.log",
        level=logging.DEBUG if args.debug else logging.INFO,
    )
    google_alerts.logger = logger

    if not wait_for_network(["news.google.com"]):
        logger.error("ネットワーク未接続のため処理を中止します")
        sys.exit(1)

    collector = GoogleNewsBackfillCollector(per_keyword_per_day=args.per_keyword)
    alerts = await collector.collect(args.start, args.end)

    by_day = Counter(a.email_date for a in alerts)
    for day in sorted(by_day):
        logger.info(f"  {day}: {by_day[day]}件")

    if args.dry_run:
        lines = [f"{a.email_date}\t{a.source}\t{a.title}\t{a.url}" for a in alerts]
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
        else:
            for line in lines:
                print(line)
        logger.info(f"dry-run: {len(alerts)}件（保存はしていません）")
        return

    if not alerts:
        logger.warning("取り戻せる記事がありませんでした")
        return

    database_id = os.getenv("NOTION_GOOGLE_ALERTS_DATABASE_ID") or os.getenv(
        "NOTION_DB_ID_GOOGLE_ALERTS"
    )
    if database_id:
        publisher = NotionPublisher(source_type="google_alerts")
        alerts = await drop_already_saved(alerts, publisher, database_id, logger)
        if not alerts:
            logger.info("新しく保存する記事はありません")
            return

    fetcher = GoogleAlertsCollector(authenticate=False)
    await google_alerts.process_and_save_alerts(fetcher, alerts, max_concurrent_saves=1)
    logger.info("取り戻しが完了しました")


if __name__ == "__main__":
    main()
