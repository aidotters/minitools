#!/usr/bin/env python3
"""
ArXiv Weekly Digest - Generate weekly summary of ArXiv papers from Notion DB.

Usage:
    uv run arxiv-weekly --days 7 --top 10
    uv run arxiv-weekly --provider openai --dry-run
    uv run arxiv-weekly --no-trends
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from minitools.llm import get_llm_client
from minitools.processors import ArxivWeeklyProcessor
from minitools.publishers.slack import SlackPublisher
from minitools.readers.notion import NotionReader
from minitools.researchers.hf_papers import HFPapersResearcher
from minitools.researchers.trend import TrendResearcher
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger

logger = setup_logger(name="scripts.arxiv_weekly", log_file="arxiv_weekly.log")


async def generate_digest(
    days: int,
    top_n: int,
    provider: str,
    dry_run: bool,
    output_file: str | None,
    no_trends: bool = False,
    hf_top_n: int = 5,
    llm_top_n: int = 5,
) -> int:
    """
    ArXiv週次ダイジェストを生成

    Args:
        days: 過去何日分の論文を取得するか
        top_n: 上位何件の論文を選出するか（後方互換、HF未使用時）
        provider: LLMプロバイダー（ollama/openai/gemini）
        dry_run: True の場合はSlack送信をスキップ
        output_file: 出力ファイルパス（指定時はファイルに保存）
        no_trends: True の場合はトレンド調査をスキップ
        hf_top_n: HFセクションの取得件数
        llm_top_n: LLMセクションの取得件数

    Returns:
        実際に処理された論文数
    """
    # 日付範囲を計算
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    logger.info(
        f"Generating ArXiv weekly digest for {start_date_str} to {end_date_str}"
    )
    logger.info(
        f"LLM Provider: {provider}, HF top: {hf_top_n}, LLM top: {llm_top_n}, "
        f"Trends: {'disabled' if no_trends else 'enabled'}"
    )

    # Notion DBからArXiv論文を取得
    database_id = os.getenv("NOTION_ARXIV_DATABASE_ID")
    if not database_id:
        logger.error("NOTION_ARXIV_DATABASE_ID is not set")
        sys.exit(1)

    reader = NotionReader()
    logger.info(f"Fetching papers from Notion DB: {database_id[:8]}...")

    try:
        papers = await reader.get_arxiv_papers_by_date_range(
            start_date=start_date_str,
            end_date=end_date_str,
            database_id=database_id,
        )
    except Exception as e:
        logger.error(f"Failed to fetch papers from Notion: {e}")
        sys.exit(1)

    if not papers:
        logger.warning("No papers found in the specified date range")
        print(
            f"期間 {start_date_str} - {end_date_str} に該当する論文がありませんでした。"
        )
        return 0

    logger.info(f"Found {len(papers)} papers")

    # LLMクライアントを取得
    try:
        llm_client = get_llm_client(provider=provider)
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}")
        sys.exit(1)

    # TrendResearcherを初期化（トレンド調査が有効な場合のみ）
    trend_researcher = None
    if not no_trends:
        trend_researcher = TrendResearcher()

    # HFPapersResearcherを使用して2層構成のダイジェストを生成
    async with HFPapersResearcher() as hf_researcher:
        processor = ArxivWeeklyProcessor(
            llm_client=llm_client,
            trend_researcher=trend_researcher,
            hf_researcher=hf_researcher,
        )
        result = await processor.process(
            papers=papers,
            top_n=top_n,
            use_trends=not no_trends,
            hf_top_n=hf_top_n,
            llm_top_n=llm_top_n,
        )

    trend_info = result.get("trend_info")
    top_papers = result["papers"]
    hf_papers = result.get("hf_papers", [])
    llm_papers = result.get("llm_papers", [])
    total_papers = result["total_papers"]

    trend_summary = trend_info.get("summary") if trend_info else None

    logger.info(
        f"Processing complete: {len(hf_papers)} HF + {len(llm_papers)} LLM papers "
        f"selected from {total_papers}"
    )

    # Slackフォーマットでメッセージを生成
    slack = SlackPublisher()
    message = slack.format_arxiv_weekly(
        start_date=start_date_str,
        end_date=end_date_str,
        papers=top_papers,
        trend_summary=trend_summary,
        hf_papers=hf_papers,
        llm_papers=llm_papers,
    )

    # ファイル出力
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(message, encoding="utf-8")
        logger.info(f"Digest saved to: {output_path}")
        print(f"ダイジェストを保存しました: {output_path}")

    # dry-runの場合は標準出力に表示
    if dry_run:
        print("\n" + "=" * 60)
        print("【DRY RUN】以下のメッセージがSlackに送信されます:")
        print("=" * 60 + "\n")
        print(message)
        print("\n" + "=" * 60)
        logger.info("Dry run complete - Slack message not sent")
        return len(top_papers)

    # Slackに送信
    webhook_url = os.getenv("SLACK_ARXIV_WEEKLY_WEBHOOK_URL")
    if not webhook_url:
        logger.warning(
            "SLACK_ARXIV_WEEKLY_WEBHOOK_URL is not set. Skipping Slack notification."
        )
        print("Slack Webhook URLが設定されていないため、通知をスキップしました。")
        return len(top_papers)

    async with SlackPublisher(webhook_url=webhook_url) as slack_publisher:
        success = await slack_publisher.send_message(message)
        if success:
            logger.info("ArXiv weekly digest sent to Slack successfully")
            print("ArXiv週次ダイジェストをSlackに送信しました。")
            return len(top_papers)
        else:
            logger.error("Failed to send ArXiv weekly digest to Slack")
            sys.exit(1)


def main():
    """CLIエントリーポイント"""
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Generate weekly ArXiv paper digest from Notion DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run arxiv-weekly                              # デフォルト設定で実行
  uv run arxiv-weekly --days 14                    # 過去14日分を取得
  uv run arxiv-weekly --top 20                     # 上位20件を選出
  uv run arxiv-weekly --provider openai            # OpenAI APIを使用
  uv run arxiv-weekly --dry-run                    # Slack送信をスキップ
  uv run arxiv-weekly --no-trends                  # トレンド調査をスキップ
  uv run arxiv-weekly --output out.md              # ファイルに保存
        """,
    )

    parser.add_argument(
        "--days",
        type=int,
        default=config.get("defaults.arxiv_weekly.days_back", 7),
        help="過去何日分の論文を取得するか（デフォルト: 7）",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="LLMセクションの選出件数を上書き（--llm-top のショートカット）",
    )

    parser.add_argument(
        "--hf-top",
        type=int,
        default=config.get("defaults.arxiv_weekly.hf_top_n", 5),
        help="HFセクションの取得件数（デフォルト: 5）",
    )

    parser.add_argument(
        "--llm-top",
        type=int,
        default=config.get("defaults.arxiv_weekly.llm_top_n", 5),
        help="LLMセクションの取得件数（デフォルト: 5）",
    )

    # プロバイダーのデフォルト値: arxiv_weekly.provider → llm.provider の順でフォールバック
    default_provider = config.get(
        "defaults.arxiv_weekly.provider", config.get("llm.provider", "ollama")
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "gemini"],
        default=default_provider,
        help=f"LLMプロバイダー（デフォルト: {default_provider}）",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Slack送信をスキップし、出力内容を表示",
    )

    parser.add_argument(
        "--no-trends",
        action="store_true",
        help="Tavily APIによるトレンド調査をスキップ",
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="出力ファイルパス（指定時はファイルに保存）",
    )

    args = parser.parse_args()

    hf_top_n = args.hf_top
    llm_top_n = args.top if args.top is not None else args.llm_top
    top_n = llm_top_n

    logger.info("=" * 60)
    logger.info("ArXiv Weekly Digest")
    logger.info("=" * 60)
    logger.info(f"Days: {args.days}")
    logger.info(f"HF top N: {hf_top_n}")
    logger.info(f"LLM top N: {llm_top_n}")
    logger.info(f"Provider: {args.provider}")
    logger.info(f"Trends: {'disabled' if args.no_trends else 'enabled'}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Output file: {args.output or 'None'}")
    logger.info("=" * 60)

    processed_count = asyncio.run(
        generate_digest(
            days=args.days,
            top_n=top_n,
            provider=args.provider,
            dry_run=args.dry_run,
            output_file=args.output,
            no_trends=args.no_trends,
            hf_top_n=hf_top_n,
            llm_top_n=llm_top_n,
        )
    )

    logger.info(f"処理完了: {processed_count}件の論文を処理しました")


if __name__ == "__main__":
    main()
