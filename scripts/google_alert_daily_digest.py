#!/usr/bin/env python3
"""
Google Alert Daily Digest - 過去24時間の Google Alerts 記事から Top10 を Slack に配信。

Usage:
    uv run google-alert-daily-digest                       # デフォルト設定で実行
    uv run google-alert-daily-digest --hours 24 --top 10
    uv run google-alert-daily-digest --provider openai --dry-run
    uv run google-alert-daily-digest --output outputs/daily.md
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from minitools.llm import get_embedding_client, get_llm_client
from minitools.processors import DigestProcessor
from minitools.publishers.slack import SlackPublisher
from minitools.readers.notion import NotionReader
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger

logger = setup_logger(
    name="scripts.google_alert_daily_digest",
    log_file="google_alert_daily_digest.log",
)


async def generate_digest(
    hours: int,
    top_n: int,
    provider: str,
    dry_run: bool,
    output_file: str | None,
    no_dedup: bool = False,
    quiet: bool = False,
    embedding_provider: str | None = None,
) -> int:
    """日次ダイジェストを生成。

    Returns:
        終了コード（0: 成功 / 1: 失敗）
    """
    config = get_config()

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(hours=hours)
    start_date_str = start_dt.strftime("%Y-%m-%d")
    end_date_str = end_dt.strftime("%Y-%m-%d")
    today_str = end_dt.strftime("%Y-%m-%d")

    embed_provider = embedding_provider or provider

    logger.info(
        f"Generating daily digest (hours={hours}, range={start_date_str}..{end_date_str})"
    )
    logger.info(f"LLM provider={provider}, embedding={embed_provider}, top={top_n}")

    # 環境変数チェック
    database_id = os.getenv("NOTION_GOOGLE_ALERTS_DATABASE_ID")
    if not database_id:
        logger.error("NOTION_GOOGLE_ALERTS_DATABASE_ID is not set")
        return 1

    webhook_url = os.getenv("SLACK_GOOGLE_ALERTS_DAILY_DIGEST_WEBHOOK_URL")
    if not webhook_url and not dry_run:
        logger.error("SLACK_GOOGLE_ALERTS_DAILY_DIGEST_WEBHOOK_URL is not set")
        return 1
    if not webhook_url and dry_run:
        logger.warning(
            "SLACK_GOOGLE_ALERTS_DAILY_DIGEST_WEBHOOK_URL is not set (dry-run continues)"
        )

    # Notion から記事取得
    reader = NotionReader()
    try:
        articles = await reader.get_articles_by_date_range(
            database_id=database_id,
            start_date=start_date_str,
            end_date=end_date_str,
            date_property="Date",
        )
    except Exception as e:
        logger.error(f"Failed to fetch articles from Notion: {e}")
        return 1

    logger.info(f"Found {len(articles)} articles")

    slack = SlackPublisher()

    # 0件処理
    if not articles:
        if quiet:
            logger.info("No articles found (--quiet specified, skipping send)")
            return 0
        empty_msg = slack.format_daily_digest(date=today_str, articles=[])
        if dry_run or not webhook_url:
            print(empty_msg)
            return 0
        async with SlackPublisher(webhook_url=webhook_url) as sp:
            ok = await sp.send_message(empty_msg)
        return 0 if ok else 1

    # LLM クライアント
    try:
        llm_client = get_llm_client(provider=provider)
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}")
        return 1

    embedding_client = None
    if not no_dedup:
        try:
            embedding_client = get_embedding_client(provider=embed_provider)
        except Exception as e:
            logger.error(f"Failed to initialize embedding client: {e}")
            return 1

    processor = DigestProcessor(
        llm_client=llm_client,
        embedding_client=embedding_client,
    )

    # スコアリング
    scored = await processor.rank_articles_by_importance(articles)

    # 重複除去 + 上位選出
    top_articles = await processor.select_top_articles(
        scored,
        top_n=top_n,
        deduplicate=False if no_dedup else None,
    )

    # 各記事の要約（先に生成して「今日のまとめ」のハイライト入力にも使う）
    summarized = await processor.generate_article_summaries(top_articles)

    # 「今日のまとめ」生成: 全記事 + Top10 ハイライトを入力に与える
    chunk_size = config.get("defaults.daily_digest.summary_chunk_size", 50)
    daily_summary = await processor.summarize_all_articles(
        scored,
        chunk_size=chunk_size,
        highlight_articles=summarized,
    )
    if not daily_summary:
        logger.info(
            "Daily summary is empty (LLM failure or no articles); 「今日のまとめ」セクションを省略"
        )

    message = slack.format_daily_digest(
        date=today_str,
        articles=summarized,
        daily_summary=daily_summary,
    )

    if output_file:
        out = Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(message, encoding="utf-8")
        logger.info(f"Digest saved to {out}")

    if dry_run:
        print("\n" + "=" * 60)
        print("【DRY RUN】Slack 送信内容:")
        print("=" * 60 + "\n")
        print(message)
        print("\n" + "=" * 60)
        return 0

    if not webhook_url:
        return 1

    async with SlackPublisher(webhook_url=webhook_url) as sp:
        ok = await sp.send_message(message)
        if ok:
            logger.info("Daily digest sent to Slack")
            return 0
        logger.error("Failed to send daily digest to Slack")
        return 1


def main() -> None:
    """CLI エントリーポイント"""
    config = get_config()

    parser = argparse.ArgumentParser(
        description="Generate daily AI digest from Notion Google Alerts DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run google-alert-daily-digest                              # デフォルト設定で実行
  uv run google-alert-daily-digest --hours 24 --top 10
  uv run google-alert-daily-digest --provider openai
  uv run google-alert-daily-digest --dry-run                    # Slack送信をスキップ
  uv run google-alert-daily-digest --no-dedup                   # 類似記事除去をスキップ
  uv run google-alert-daily-digest --quiet                      # 0件時は送信スキップ
        """,
    )

    parser.add_argument(
        "--hours",
        type=int,
        default=config.get("defaults.daily_digest.hours_back", 24),
        help="過去何時間分の記事を取得するか（デフォルト: 24）",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=config.get("defaults.daily_digest.top_articles", 10),
        help="上位何件の記事を選出するか（デフォルト: 10）",
    )
    default_provider = config.get(
        "defaults.daily_digest.provider", config.get("llm.provider", "openai")
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
        "--output",
        type=str,
        default=None,
        help="出力ファイルパス（指定時はファイルに保存）",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="類似記事除去をスキップ",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="記事0件のとき Slack 送信をスキップ",
    )
    parser.add_argument(
        "--embedding",
        choices=["ollama", "openai"],
        default=None,
        help="Embeddingプロバイダー（省略時はLLMプロバイダーと同じ）",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Google Alert Daily Digest")
    logger.info("=" * 60)
    logger.info(f"Hours: {args.hours}")
    logger.info(f"Top: {args.top}")
    logger.info(f"Provider: {args.provider}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Output: {args.output or 'None'}")
    logger.info(f"Dedup: {'disabled' if args.no_dedup else 'enabled'}")
    logger.info(f"Quiet: {args.quiet}")
    logger.info("=" * 60)

    exit_code = asyncio.run(
        generate_digest(
            hours=args.hours,
            top_n=args.top,
            provider=args.provider,
            dry_run=args.dry_run,
            output_file=args.output,
            no_dedup=args.no_dedup,
            quiet=args.quiet,
            embedding_provider=args.embedding,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
