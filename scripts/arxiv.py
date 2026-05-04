#!/usr/bin/env python3
"""
ArXiv paper collection script - backward compatibility wrapper.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
import logging
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv

from minitools.collectors.arxiv import ArxivCollector
from minitools.processors.translator import Translator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.slack import SlackPublisher
from minitools.utils.logger import setup_logger
from minitools.utils.config import get_config

load_dotenv()

# ロガーは後で初期化（argparseの前には基本設定のみ）
logger = None


def main():
    """エントリーポイント（同期版）"""
    asyncio.run(main_async())


async def main_async():
    # デフォルトの基準日（昨日）を計算
    jst = pytz.timezone("Asia/Tokyo")
    yesterday = (datetime.now(jst) - timedelta(days=1)).strftime("%Y-%m-%d")

    parser = argparse.ArgumentParser(
        description="arXiv論文を検索して要約をNotionに保存"
    )
    parser.add_argument(
        "--keywords",
        "-q",
        "--queries",
        nargs="+",
        default=["LLM", "(RAG OR FINETUNING OR AGENT)"],
        help="検索キーワード（複数指定可）",
    )
    parser.add_argument("--days", type=int, default=1, help="何日前から検索するか")
    parser.add_argument(
        "--date", "-d", type=str, default=yesterday, help="基準日（YYYY-MM-DD形式）"
    )
    parser.add_argument(
        "--max-results",
        "-r",
        "--max_results",
        type=int,
        default=50,
        help="取得する最大論文数",
    )
    parser.add_argument("--notion", action="store_true", help="Notionへの保存のみ実行")
    parser.add_argument("--slack", action="store_true", help="Slackへの送信のみ実行")
    parser.add_argument("--debug", action="store_true", help="デバッグモードで実行")
    parser.add_argument(
        "--test", action="store_true", help="テストモード（最初の1論文のみ処理）"
    )

    args = parser.parse_args()

    # 設定ファイルからデフォルトログレベルを取得
    config = get_config()
    default_log_level = config.get("logging.level", "INFO").upper()

    # デバッグオプションが指定されている場合は上書き
    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = getattr(logging, default_log_level, logging.INFO)

    # ロガーの初期化
    global logger
    logger = setup_logger("scripts.arxiv", log_file="arxiv.log", level=log_level)

    # NotionPublisherのロガーも設定（同じログファイルとレベルを使用）
    # notion_logger = setup_logger("minitools.publishers.notion", log_file="arxiv.log", level=log_level)

    # 日付範囲の設定（base_dateを基準に計算）
    base_date = datetime.strptime(args.date, "%Y-%m-%d")

    # 月曜日かつ--daysが明示的に指定されていない場合は3日検索（土日分をカバー）
    if base_date.weekday() == 0 and "--days" not in sys.argv:
        effective_days = 3
        logger.info("月曜日検索：土日分をカバーするため過去3日間を検索します")
    else:
        effective_days = args.days

    start_date = base_date - timedelta(days=effective_days - 1)
    end_date = base_date

    # フラグの処理
    save_notion = not args.slack or args.notion
    send_slack = not args.notion or args.slack

    # コレクターの初期化
    collector = ArxivCollector()

    # 論文を検索
    logger.info(
        f"Searching max {args.max_results} papers from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (effective_days: {effective_days}) with queries: {args.keywords}"
    )
    papers = collector.search(
        queries=args.keywords,
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        max_results=args.max_results,
    )

    if not papers:
        logger.info("No papers found")
    else:
        logger.info(f"Found {len(papers)} papers")

    # テストモードの場合は最初の1件のみ処理
    if args.test and papers:
        papers = papers[:1]
        logger.info("テストモード: 最初の1論文のみ処理します")

    # 翻訳と要約
    translator = Translator()
    processed_papers = []

    if papers:  # 論文がある場合のみ処理
        logger.info(f"翻訳・要約処理を開始: {len(papers)}件の論文を処理中...")
        async with collector:
            for i, paper in enumerate(papers, 1):
                try:
                    logger.info(
                        f"  論文処理中 ({i}/{len(papers)}): {paper['title'][:60]}..."
                    )

                    # タイトルと要約を翻訳
                    result = await translator.translate_with_summary(
                        title=paper["title"],
                        content=paper["abstract"],
                        author=paper["authors"],
                    )

                    paper["japanese_title"] = result["japanese_title"]
                    paper["japanese_summary"] = result["japanese_summary"]
                    processed_papers.append(paper)

                    logger.info(f"    -> 翻訳完了: {result['japanese_title'][:40]}...")

                except Exception as e:
                    logger.error(
                        f"    -> 処理エラー ({i}/{len(papers)}): {paper['title'][:50]}... - {e}"
                    )

    # Notionに保存
    if save_notion and processed_papers:
        # 環境変数名の統一（フォールバック対応）
        database_id = os.getenv("NOTION_ARXIV_DATABASE_ID") or os.getenv("NOTION_DB_ID")
        if database_id:
            try:
                logger.info(
                    f"Notion保存開始: {len(processed_papers)}件の論文を保存中..."
                )
                publisher = NotionPublisher(source_type="arxiv")
                result = await publisher.batch_save_articles(
                    database_id, processed_papers
                )
                stats = result.get("stats", {})
                logger.info("=" * 60)
                logger.info("Notion保存結果:")
                logger.info(f"  成功: {stats.get('success', 0)}件")
                logger.info(f"  スキップ (既存): {stats.get('skipped', 0)}件")
                logger.info(f"  失敗: {stats.get('failed', 0)}件")
                logger.info("=" * 60)
            except Exception as e:
                logger.error(f"Notion保存エラー: {e}")
        else:
            logger.warning("NOTION_ARXIV_DATABASE_ID環境変数が設定されていません")

    # Slackに送信（論文が0件でも通知）
    if send_slack:
        # 環境変数名の統一（フォールバック対応）
        webhook_url = os.getenv("SLACK_ARXIV_WEBHOOK_URL") or os.getenv(
            "SLACK_WEBHOOK_URL"
        )
        if webhook_url:
            try:
                async with SlackPublisher(webhook_url) as slack:
                    await slack.send_articles(
                        processed_papers,
                        date=end_date.strftime("%Y-%m-%d"),
                        title=f"arXiv Papers ({', '.join(args.keywords)})",
                    )
                logger.info("Sent to Slack")
            except Exception as e:
                logger.error(f"Error sending to Slack: {e}")

    logger.info("Processing completed")


if __name__ == "__main__":
    main()
