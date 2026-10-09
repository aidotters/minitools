#!/usr/bin/env python3
"""
X (Twitter) AI Trend Digest - Collect and summarize AI-related trends from X.

Usage:
    uv run x-trend                         # デフォルト設定で実行
    uv run x-trend --dry-run               # Slack送信なしのプレビュー
    uv run x-trend --region japan          # 日本トレンドのみ
    uv run x-trend --region global         # グローバルトレンドのみ
    uv run x-trend --provider gemini       # Gemini APIを使用
    uv run x-trend --test                  # テストモード（最小件数）
    uv run x-trend --no-trends             # トレンド検索をスキップ
    uv run x-trend --no-keywords           # キーワード検索をスキップ
    uv run x-trend --no-timeline           # ユーザータイムライン監視をスキップ
"""

import argparse
import asyncio
import os
import sys
from typing import Optional

from minitools.collectors.x_trend import XTrendCollector
from minitools.llm import get_llm_client
from minitools.processors.x_trend import XTrendProcessor
from minitools.publishers.slack import SlackPublisher
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger
from minitools.utils.network import wait_for_network

logger = setup_logger(name="scripts.x_trend", log_file="x_trend.log")


async def generate_digest(
    regions: list[str],
    provider: str,
    dry_run: bool,
    max_trends: int,
    tweets_per_trend: int,
    keywords: Optional[list[str]] = None,
    watch_accounts: Optional[list[str]] = None,
    tweets_per_keyword: int = 20,
    tweets_per_account: int = 20,
    enable_trends: bool = True,
    enable_keywords: bool = True,
    enable_timeline: bool = True,
) -> int:
    """
    Xトレンドダイジェストを生成

    Args:
        regions: 対象地域リスト
        provider: LLMプロバイダー
        dry_run: Slack送信をスキップするか
        max_trends: 地域ごとの最大トレンド数
        tweets_per_trend: トレンドあたりのツイート取得件数
        keywords: 検索キーワードリスト
        watch_accounts: 監視アカウントリスト
        tweets_per_keyword: キーワードあたりのツイート取得件数
        tweets_per_account: アカウントあたりのツイート取得件数
        enable_trends: トレンド収集を有効にするか
        enable_keywords: キーワード検索を有効にするか
        enable_timeline: タイムライン監視を有効にするか

    Returns:
        処理されたトレンド数
    """
    logger.info(f"Generating X trend digest for regions: {regions}")
    logger.info(f"LLM Provider: {provider}, Max trends: {max_trends}")
    logger.info(
        f"Sources: trends={enable_trends}, keywords={enable_keywords}, "
        f"timeline={enable_timeline}"
    )

    # 3ソースを収集
    async with XTrendCollector() as collector:
        collect_result = await collector.collect_all(
            regions=regions,
            keywords=keywords,
            watch_accounts=watch_accounts,
            tweets_per_trend=tweets_per_trend,
            tweets_per_keyword=tweets_per_keyword,
            tweets_per_account=tweets_per_account,
            enable_trends=enable_trends,
            enable_keywords=enable_keywords,
            enable_timeline=enable_timeline,
        )

        total_collected = (
            sum(len(v) for v in collect_result.trends.values())
            + len(collect_result.keyword_results)
            + len(collect_result.timeline_results)
        )
        if total_collected == 0:
            logger.warning("No data collected from any source")
            print("データを取得できませんでした。APIキーの設定を確認してください。")
            return 0

        logger.info(f"Collected data from {total_collected} sources")

        # LLMクライアントを取得
        try:
            llm_client = get_llm_client(provider=provider)
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            sys.exit(1)

        # 3ソースをフィルタリング・要約
        processor = XTrendProcessor(llm_client=llm_client)
        process_result = await processor.process_all(
            collect_result=collect_result,
            max_trends=max_trends,
            collector=collector,
        )

    total_summaries = (
        sum(len(v) for v in process_result.trend_summaries.values())
        + len(process_result.keyword_summaries)
        + len(process_result.timeline_summaries)
    )
    logger.info(f"Processed {total_summaries} items total")

    # Slackフォーマットでセクションごとのメッセージを生成
    messages = SlackPublisher.format_x_trend_digest_sections(process_result)

    # dry-runの場合は標準出力に表示
    if dry_run:
        for i, msg in enumerate(messages, 1):
            print("\n" + "=" * 60)
            print(f"【DRY RUN】セクション {i}/{len(messages)}:")
            print("=" * 60 + "\n")
            print(msg)
        print("\n" + "=" * 60)
        logger.info("Dry run complete - Slack message not sent")
        return total_summaries

    # Slackに送信
    webhook_url = os.getenv("SLACK_X_TIMELINE_SUMMARY_WEBHOOK_URL")
    if not webhook_url:
        logger.warning(
            "SLACK_X_TIMELINE_SUMMARY_WEBHOOK_URL is not set. Skipping Slack notification."
        )
        print("Slack Webhook URLが設定されていないため、通知をスキップしました。")
        for msg in messages:
            print("\n" + msg)
        return total_summaries

    async with SlackPublisher(webhook_url=webhook_url) as slack_publisher:
        success = await slack_publisher.send_messages(messages)
        if success:
            logger.info("X trend digest sent to Slack successfully")
            print(
                f"XトレンドダイジェストをSlackに送信しました（{len(messages)}セクション）。"
            )
            return total_summaries
        else:
            logger.error("Failed to send X trend digest to Slack")
            sys.exit(1)


def main():
    """CLIエントリーポイント"""
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Generate AI trend digest from X (Twitter)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run x-trend                              # デフォルト設定で実行
  uv run x-trend --dry-run                    # Slack送信をスキップ
  uv run x-trend --region japan               # 日本トレンドのみ
  uv run x-trend --region global              # グローバルトレンドのみ
  uv run x-trend --provider gemini            # Gemini APIを使用
  uv run x-trend --test                       # テストモード
  uv run x-trend --no-trends                  # トレンド検索をスキップ
  uv run x-trend --no-keywords                # キーワード検索をスキップ
  uv run x-trend --no-timeline                # ユーザータイムライン監視をスキップ
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Slack送信をスキップし、出力内容を表示",
    )

    parser.add_argument(
        "--region",
        choices=["japan", "global"],
        default=None,
        help="対象地域を指定（デフォルト: 両方）",
    )

    default_provider = config.get(
        "defaults.x_trend.provider", config.get("llm.provider", "ollama")
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "gemini"],
        default=default_provider,
        help=f"LLMプロバイダー（デフォルト: {default_provider}）",
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="テストモード（トレンド3件、ツイート5件/トレンド、キーワード2件、アカウント2件）",
    )

    parser.add_argument(
        "--no-trends",
        action="store_true",
        help="トレンド検索をスキップ",
    )

    parser.add_argument(
        "--no-keywords",
        action="store_true",
        help="キーワード検索をスキップ",
    )

    parser.add_argument(
        "--no-timeline",
        action="store_true",
        help="ユーザータイムライン監視をスキップ",
    )

    args = parser.parse_args()

    # 全ソーススキップチェック
    if args.no_trends and args.no_keywords and args.no_timeline:
        print(
            "エラー: すべてのソースがスキップされています。少なくとも1つのソースを有効にしてください。"
        )
        sys.exit(1)

    # スリープ復帰直後の実行に備え、名前解決できるまで待つ
    if not wait_for_network(["api.twitterapi.io", "hooks.slack.com"]):
        logger.error("ネットワーク未接続のため処理を中止します")
        sys.exit(1)

    # 地域の決定
    if args.region:
        regions = [args.region]
    else:
        regions = ["japan", "global"]

    # settings.yamlからキーワードとアカウントを読み込み
    keywords = config.get("defaults.x_trend.keywords", [])
    watch_accounts = config.get("defaults.x_trend.watch_accounts", [])

    # テストモードの設定
    if args.test:
        max_trends = 3
        tweets_per_trend = 5
        tweets_per_keyword = 5
        tweets_per_account = 5
        keywords = keywords[:2] if keywords else []
        watch_accounts = watch_accounts[:2] if watch_accounts else []
    else:
        max_trends = config.get("defaults.x_trend.max_trends", 10)
        tweets_per_trend = config.get("defaults.x_trend.tweets_per_trend", 20)
        tweets_per_keyword = config.get("defaults.x_trend.tweets_per_keyword", 20)
        tweets_per_account = config.get("defaults.x_trend.tweets_per_account", 20)

    enable_trends = not args.no_trends
    enable_keywords = not args.no_keywords
    enable_timeline = not args.no_timeline

    logger.info("=" * 60)
    logger.info("X AI Trend Digest")
    logger.info("=" * 60)
    logger.info(f"Regions: {regions}")
    logger.info(f"Provider: {args.provider}")
    logger.info(f"Max trends: {max_trends}")
    logger.info(f"Tweets per trend: {tweets_per_trend}")
    logger.info(f"Keywords: {keywords}")
    logger.info(f"Watch accounts: {watch_accounts}")
    logger.info(
        f"Sources: trends={enable_trends}, keywords={enable_keywords}, timeline={enable_timeline}"
    )
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Test mode: {args.test}")
    logger.info("=" * 60)

    processed_count = asyncio.run(
        generate_digest(
            regions=regions,
            provider=args.provider,
            dry_run=args.dry_run,
            max_trends=max_trends,
            tweets_per_trend=tweets_per_trend,
            keywords=keywords,
            watch_accounts=watch_accounts,
            tweets_per_keyword=tweets_per_keyword,
            tweets_per_account=tweets_per_account,
            enable_trends=enable_trends,
            enable_keywords=enable_keywords,
            enable_timeline=enable_timeline,
        )
    )

    logger.info(f"処理完了: {processed_count}件のアイテムを処理しました")


if __name__ == "__main__":
    main()
