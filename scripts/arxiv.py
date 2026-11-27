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
from collections.abc import Callable
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
    DeliveryState,
    load_state,
    missed_targets,
    required_destinations,
    run_lock,
    save_state,
    scheduled_targets,
)
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger
from minitools.utils.network import wait_for_network

load_dotenv()

logger: logging.Logger = logging.getLogger("scripts.arxiv")


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

    if args.catch_up and (
        args.test or args.weekly_only or args.notion or args.slack or args.no_weekly
    ):
        raise SystemExit("--catch-up は配信先・テストの指定と併用できません")

    incomplete = False
    # 完了判定・配信・記録を同じロック内で行う。
    with run_lock():
        state = None if args.test else load_state()
        if state is None and not args.test:
            due = scheduled_targets(datetime.now(jst))
            if args.catch_up:
                if due:
                    save_state(DeliveryState(due[-1]))
                logger.info("初回の取り戻しでは過去分を再送しません")
                return
            baseline = min(base_date, due[-1] if due else base_date) - timedelta(days=1)
            state = DeliveryState(baseline)
            save_state(state)

        requested = set()
        if not args.weekly_only:
            if save_notion:
                requested.add("notion")
            if send_slack:
                requested.add("slack")
        if args.weekly_only or (
            save_notion
            and not args.no_weekly
            and "weekly" in required_destinations(base_date)
        ):
            requested.add("weekly")

        if args.catch_up:
            assert state is not None
            targets = missed_targets(datetime.now(jst), state)
            jobs = [
                (target, state.pending(target, required_destinations(target)))
                for target in targets
            ]
        else:
            pending = (
                requested if state is None else state.pending(base_date, requested)
            )
            jobs = [(base_date, pending)] if pending else []

        if not jobs:
            logger.info("未完了の配信はありません")
            return

        if not wait_for_network(["huggingface.co", "hooks.slack.com"]):
            logger.error("ネットワーク未接続のため処理を中止します")
            raise SystemExit(1)

        async with HFPapersResearcher() as researcher:
            for target, pending in jobs:
                done: set[str] = set()

                def confirm(destination: str) -> None:
                    if state is not None:
                        state.completed.setdefault(target, set()).add(destination)
                        save_state(state)
                    done.add(destination)

                if pending & {"notion", "slack"}:
                    await _run_daily(
                        researcher,
                        target,
                        min_upvotes,
                        max_papers,
                        focus_keywords,
                        database_id,
                        "notion" in pending,
                        "slack" in pending,
                        args.test,
                        confirm,
                    )

                # 日次の Notion が未完了なら、不完全な週次ページを作らない。
                if "weekly" in pending and (
                    args.weekly_only or "notion" not in pending or "notion" in done
                ):
                    if await _run_weekly(researcher, database_id, target, weekly_top):
                        confirm("weekly")

                if pending - done:
                    incomplete = True
                    logger.error(
                        "未完了 %s: %s", target, ", ".join(sorted(pending - done))
                    )

    if incomplete:
        raise SystemExit(1)
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
    confirm: Callable[[str], None],
) -> None:
    hf_date = base_date.isoformat()
    try:
        items = await researcher.get_daily_papers(hf_date, strict=True)
    except Exception:
        logger.exception("HF の日次データを取得できません: %s", hf_date)
        return
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

    if len(processed) != len(papers):
        logger.error("翻訳が未完了のため配信を保留: %s", hf_date)
        return

    if save_notion:
        notion_ok = not processed
        if processed and database_id:
            try:
                publisher = NotionPublisher(source_type="arxiv")
                await publisher.ensure_arxiv_properties(database_id)
                stats = (
                    await publisher.batch_save_articles(
                        database_id, processed, strict=True
                    )
                )["stats"]
                notion_ok = stats["failed"] == 0 and (
                    stats["success"] + stats["skipped"] == len(processed)
                )
                logger.info("Notion保存結果: %s", stats)
            except Exception:
                logger.exception("Notion保存エラー: %s", hf_date)
        elif processed:
            logger.error("Notion データベース ID が未設定です")
        if notion_ok:
            confirm("notion")

    if send_slack:
        webhook_url = os.getenv("SLACK_ARXIV_WEBHOOK_URL") or os.getenv(
            "SLACK_WEBHOOK_URL"
        )
        slack_ok = False
        if webhook_url:
            try:
                async with SlackPublisher(webhook_url) as slack:
                    slack_ok = await slack.send_articles(
                        processed,
                        date=hf_date,
                        title="Hugging Face 注目論文",
                    )
            except Exception:
                # Webhook URL をログに含めない。
                logger.error("Slack送信エラー: %s", hf_date)
        else:
            logger.error("Slack Webhook が未設定です")
        if slack_ok:
            confirm("slack")
            logger.info("Sent to Slack")


async def _run_weekly(
    researcher: HFPapersResearcher,
    database_id: str | None,
    end: date,
    top_n: int,
) -> bool:
    if not database_id:
        logger.error("Notion データベース ID が未設定のため週次ページを作れません")
        return False
    try:
        publisher = NotionPublisher(source_type="arxiv")
        return bool(
            await create_weekly_page(publisher, researcher, database_id, end, top_n)
        )
    except Exception:
        logger.exception("週次ページの作成エラー: %s", end)
        return False


if __name__ == "__main__":
    main()
