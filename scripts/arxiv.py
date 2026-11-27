#!/usr/bin/env python3
"""
arXiv 論文の収集スクリプト。

Hugging Face Daily Papers に前日載った論文のうち、upvote の多いものだけを
日本語に翻訳・要約して Notion に保存し、Slack に通知する。
土曜日の実行では、その週に保存した論文の上位をまとめた「今週の注目論文」ページも作る。
`--catch-up` は、ログアウト中などで定時の回が走らなかった対象日だけを処理する。
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
import logging
from datetime import date, datetime, timedelta

import pytz
from dotenv import load_dotenv

from minitools.processors.hf_daily_selector import (
    DEFAULT_FOCUS_KEYWORDS,
    DEFAULT_MAX_PAPERS,
    DEFAULT_MIN_UPVOTES,
    build_daily_selection,
)
from minitools.processors.hf_weekly import create_weekly_page
from minitools.processors.translator import Translator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.slack import SlackPublisher
from minitools.researchers.hf_papers import HFPapersResearcher
from minitools.utils.arxiv_catchup import (
    load_last_done,
    missed_targets,
    record_done,
    run_lock,
    scheduled_targets,
)
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger
from minitools.utils.network import wait_for_network

load_dotenv()

logger: logging.Logger = logging.getLogger("scripts.arxiv")

# launchd は火〜土に走り、対象日は前日。土曜の実行（対象日=金曜）で週次ページを作る
WEEKLY_BASE_WEEKDAY = 4


def main():
    """エントリーポイント（同期版）"""
    asyncio.run(main_async())


def _parse_args(yesterday: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hugging Face で注目された arXiv 論文を翻訳して Notion に保存"
    )
    parser.add_argument(
        "--date",
        "-d",
        type=str,
        default=yesterday,
        help="HF Daily Papers の対象日（YYYY-MM-DD・既定は昨日）",
    )
    parser.add_argument("--min-upvotes", type=int, default=None, help="upvote の下限")
    parser.add_argument(
        "--max-papers", type=int, default=None, help="1日に保存する最大件数"
    )
    parser.add_argument("--notion", action="store_true", help="Notionへの保存のみ実行")
    parser.add_argument("--slack", action="store_true", help="Slackへの送信のみ実行")
    parser.add_argument(
        "--no-weekly", action="store_true", help="土曜日の週次ページを作らない"
    )
    parser.add_argument(
        "--weekly-only",
        action="store_true",
        help="日次処理をせず、--date を最終日とする週次ページだけを作る",
    )
    parser.add_argument(
        "--catch-up",
        action="store_true",
        help="定時の回（火〜土 14:30）のうち抜けた分だけを実行する（ログイン時に launchd が呼ぶ）",
    )
    parser.add_argument("--debug", action="store_true", help="デバッグモードで実行")
    parser.add_argument(
        "--test", action="store_true", help="テストモード（最初の1論文のみ処理）"
    )
    return parser.parse_args()


async def _translate(papers: list[dict]) -> list[dict]:
    translator = Translator()
    processed: list[dict] = []
    for i, paper in enumerate(papers, 1):
        try:
            logger.info(f"  論文処理中 ({i}/{len(papers)}): {paper['title'][:60]}...")
            result = await translator.translate_with_summary(
                title=paper["title"],
                content=paper["abstract"],
                author=paper["authors"],
            )
            paper["japanese_title"] = result["japanese_title"]
            paper["japanese_summary"] = result["japanese_summary"]
            processed.append(paper)
            logger.info(f"    -> 翻訳完了: {result['japanese_title'][:40]}...")
        except Exception as e:
            logger.error(
                f"    -> 処理エラー ({i}/{len(papers)}): {paper['title'][:50]}... - {e}"
            )
    return processed


async def main_async():
    jst = pytz.timezone("Asia/Tokyo")
    yesterday = (datetime.now(jst) - timedelta(days=1)).strftime("%Y-%m-%d")
    args = _parse_args(yesterday)

    config = get_config()
    default_log_level = config.get("logging.level", "INFO").upper()
    log_level = (
        logging.DEBUG
        if args.debug
        else getattr(logging, default_log_level, logging.INFO)
    )

    global logger
    logger = setup_logger("scripts.arxiv", log_file="arxiv.log", level=log_level)

    base_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    min_upvotes = (
        args.min_upvotes
        if args.min_upvotes is not None
        else config.get("defaults.arxiv.min_upvotes", DEFAULT_MIN_UPVOTES)
    )
    max_papers = (
        args.max_papers
        if args.max_papers is not None
        else config.get("defaults.arxiv.max_papers", DEFAULT_MAX_PAPERS)
    )
    focus_keywords = config.get("defaults.arxiv.focus_keywords", DEFAULT_FOCUS_KEYWORDS)
    weekly_top = config.get("defaults.arxiv.weekly_top", 10)

    save_notion = not args.slack or args.notion
    send_slack = not args.notion or args.slack
    database_id = os.getenv("NOTION_ARXIV_DATABASE_ID") or os.getenv("NOTION_DB_ID")

    # 定時の回と取り戻しの回が重ならないよう、終わるまで待ってから進める
    with run_lock():
        if args.catch_up:
            now = datetime.now(jst)
            last_done = load_last_done()
            if last_done is None:
                # 入れた直後は、どの回が済んでいるか分からない。最新の回を済みとして記録だけする
                latest = scheduled_targets(now)[-1:]
                if latest:
                    record_done(latest[0])
                logger.info(
                    "取り戻しの記録が無いため、最新の回を処理済みとして記録だけしました"
                )
                return
            target_dates = missed_targets(now, last_done)
            if not target_dates:
                logger.info("取り戻す回はありません（定時の回はすべて処理済み）")
                return
            logger.info(
                "抜けた回を取り戻します: "
                + ", ".join(d.isoformat() for d in target_dates)
            )
        else:
            target_dates = [base_date]

        # スリープ復帰直後の実行に備え、名前解決できるまで待つ
        if not wait_for_network(["huggingface.co", "hooks.slack.com"]):
            logger.error("ネットワーク未接続のため処理を中止します")
            sys.exit(1)

        # 通常の形（Notion と Slack の両方）で日次を終えた回だけ記録する
        records = not args.weekly_only and not args.test and save_notion and send_slack

        async with HFPapersResearcher() as researcher:
            for target in target_dates:
                if not args.weekly_only:
                    await _run_daily(
                        researcher,
                        target,
                        min_upvotes,
                        max_papers,
                        focus_keywords,
                        database_id,
                        save_notion,
                        send_slack,
                        args.test,
                    )
                    if records:
                        record_done(target)

                make_weekly = args.weekly_only or (
                    target.weekday() == WEEKLY_BASE_WEEKDAY
                    and save_notion
                    and not args.no_weekly
                )
                if make_weekly:
                    await _run_weekly(researcher, database_id, target, weekly_top)

    logger.info("Processing completed")


async def _run_daily(
    researcher: HFPapersResearcher,
    base_date: date,
    min_upvotes: int,
    max_papers: int,
    focus_keywords: list[str],
    database_id: str | None,
    save_notion: bool,
    send_slack: bool,
    test_mode: bool,
) -> None:
    hf_date = base_date.isoformat()
    items = await researcher.get_daily_papers(hf_date)
    papers = build_daily_selection(
        items, hf_date, min_upvotes, max_papers, focus_keywords
    )
    logger.info(
        f"HF Daily Papers {hf_date}: {len(items)} 件中、upvote {min_upvotes} 以上の"
        f"上位 {len(papers)} 件を選びました"
    )

    if test_mode and papers:
        papers = papers[:1]
        logger.info("テストモード: 最初の1論文のみ処理します")

    processed = await _translate(papers) if papers else []

    if save_notion and processed:
        if database_id:
            try:
                publisher = NotionPublisher(source_type="arxiv")
                await publisher.ensure_arxiv_properties(database_id)
                result = await publisher.batch_save_articles(database_id, processed)
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
        webhook_url = os.getenv("SLACK_ARXIV_WEBHOOK_URL") or os.getenv(
            "SLACK_WEBHOOK_URL"
        )
        if webhook_url:
            try:
                async with SlackPublisher(webhook_url) as slack:
                    await slack.send_articles(
                        processed,
                        date=hf_date,
                        title="Hugging Face 注目論文",
                    )
                logger.info("Sent to Slack")
            except Exception as e:
                logger.error(f"Error sending to Slack: {e}")


async def _run_weekly(
    researcher: HFPapersResearcher,
    database_id: str | None,
    end: date,
    top_n: int,
) -> None:
    if not database_id:
        logger.warning("NOTION_ARXIV_DATABASE_ID 未設定のため週次ページを作りません")
        return
    try:
        publisher = NotionPublisher(source_type="arxiv")
        await create_weekly_page(publisher, researcher, database_id, end, top_n)
    except Exception as e:
        logger.error(f"週次ページの作成エラー: {e}")


if __name__ == "__main__":
    main()
