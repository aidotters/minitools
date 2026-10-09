#!/usr/bin/env python3
"""
Google Alerts collection script - backward compatibility wrapper.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

from minitools.collectors.google_alerts import GoogleAlertsCollector
from minitools.processors.translator import Translator
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.slack import SlackPublisher
from minitools.utils.logger import setup_logger
from minitools.utils.config import get_config
from minitools.utils.network import wait_for_network

load_dotenv()

# ロガーは後で初期化（argparseの前には基本設定のみ）
logger = None


def main():
    """エントリーポイント（同期版）"""
    asyncio.run(main_async())


async def main_async():
    parser = argparse.ArgumentParser(
        description="Google Alertsメールを処理してNotionに保存"
    )
    parser.add_argument(
        "--hours", type=int, default=6, help="過去何時間分のメールを取得するか"
    )
    parser.add_argument(
        "--date", type=str, help="特定の日付のメールを取得 (YYYY-MM-DD形式)"
    )
    parser.add_argument("--notion", action="store_true", help="Notionへの保存のみ実行")
    parser.add_argument("--slack", action="store_true", help="Slackへの送信のみ実行")
    parser.add_argument("--debug", action="store_true", help="デバッグモードで実行")

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
    logger = setup_logger(
        "scripts.google_alerts", log_file="google_alerts.log", level=log_level
    )

    # スリープ復帰直後の実行に備え、名前解決できるまで待つ
    if not wait_for_network(["gmail.googleapis.com", "hooks.slack.com"]):
        logger.error("ネットワーク未接続のため処理を中止します")
        sys.exit(1)

    # 日付の設定
    target_date = None
    date_specified = False
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
            date_specified = True
            logger.info(f"指定日付 {args.date} のGoogle Alertsメールを取得します")
        except ValueError:
            logger.error("日付は YYYY-MM-DD 形式で指定してください")
            return
    else:
        logger.info(f"過去{args.hours}時間のGoogle Alertsメールを取得します")

    # フラグの処理
    save_notion = not args.slack or args.notion
    send_slack = not args.notion or args.slack

    # 処理内容のログ出力
    if save_notion and send_slack:
        logger.info("処理内容: Notion保存 + Slack送信")
    elif save_notion:
        logger.info("処理内容: Notion保存のみ")
    elif send_slack:
        logger.info("処理内容: Slack送信のみ")

    # コレクターの初期化
    logger.info("Google Alerts Collectorを初期化中...")
    collector = GoogleAlertsCollector()

    # メールを取得
    if date_specified:
        logger.info(
            f"Google Alerts ({target_date.strftime('%Y-%m-%d')}) の処理を開始します..."
        )
        emails = collector.get_alerts_emails(date=target_date)
    else:
        logger.info(f"Google Alerts (過去{args.hours}時間) の処理を開始します...")
        emails = collector.get_alerts_emails(hours_back=args.hours)

    if not emails:
        if date_specified:
            logger.warning(
                f"{target_date.strftime('%Y-%m-%d')} のGoogle Alertsメールが見つかりません"
            )
        else:
            logger.warning(f"過去{args.hours}時間のGoogle Alertsメールが見つかりません")
        return

    logger.info(f"Gmail検索結果: {len(emails)}件のメッセージが見つかりました")

    # アラートを抽出
    all_alerts = []
    logger.info(f"{len(emails)}件のメールからアラートを抽出中...")
    for i, email in enumerate(emails, 1):
        logger.info(f"メール処理中 ({i}/{len(emails)}): {email.get('id', 'unknown')}")
        alerts = collector.parse_alerts(email)
        if alerts:
            logger.info(f"  -> {len(alerts)}件のアラートを抽出")
        all_alerts.extend(alerts)

    if not all_alerts:
        logger.warning("アラートが見つかりませんでした")
        return

    logger.info(f"{len(all_alerts)}件のアラートを検出しました")

    # 記事の本文を取得
    logger.info(f"記事コンテンツ取得開始: {len(all_alerts)}件のアラートを処理中...")
    await collector.fetch_articles_for_alerts(all_alerts)
    logger.info("記事コンテンツ取得完了")

    # 翻訳と要約
    translator = Translator()
    processed_alerts = []

    logger.info(f"翻訳・要約処理開始: {len(all_alerts)}件のアラートを処理中...")
    for i, alert in enumerate(all_alerts, 1):
        try:
            logger.info(
                f"  -> 翻訳・要約処理中 ({i}/{len(all_alerts)}): {alert.title[:50]}..."
            )

            # 記事本文がある場合はそれを、ない場合はスニペットを使用
            content = alert.article_content if alert.article_content else alert.snippet

            # タイトルと内容を翻訳・要約
            result = await translator.translate_with_summary(
                title=alert.title, content=content, author=alert.source
            )

            logger.info(f"    -> 翻訳・要約完了: {result['japanese_title'][:30]}...")

            # 辞書形式に変換
            processed_alerts.append(
                {
                    "title": alert.title,
                    "url": alert.url,
                    "source": alert.source,
                    "japanese_title": result["japanese_title"],
                    "japanese_summary": result["japanese_summary"],
                    "date": alert.email_date
                    if alert.email_date
                    else datetime.now().strftime("%Y-%m-%d"),
                }
            )

        except Exception as e:
            logger.error(f"翻訳・要約エラー ({alert.title}): {e}")

    logger.info(f"翻訳・要約処理完了: {len(processed_alerts)}件を処理")

    # Notionに保存
    if save_notion and processed_alerts:
        # 環境変数名の統一（フォールバック対応）
        database_id = os.getenv("NOTION_GOOGLE_ALERTS_DATABASE_ID") or os.getenv(
            "NOTION_DB_ID_GOOGLE_ALERTS"
        )
        if database_id:
            try:
                logger.info(
                    f"Notion保存開始: {len(processed_alerts)}件のアラートを保存中..."
                )
                publisher = NotionPublisher(source_type="google_alerts")
                stats = await publisher.batch_save_articles(
                    database_id, processed_alerts
                )
                logger.info(f"Notion保存完了: {stats}")
                stats_data = stats.get("stats", {})
                logger.info(f"  -> 成功: {stats_data.get('success', 0)}件")
                logger.info(f"  -> スキップ: {stats_data.get('skipped', 0)}件")
                logger.info(f"  -> 失敗: {stats_data.get('failed', 0)}件")
            except Exception as e:
                logger.error(f"Notion保存エラー: {e}")
        else:
            logger.warning(
                "NOTION_GOOGLE_ALERTS_DATABASE_ID環境変数が設定されていません"
            )

    # Slackに送信
    if send_slack and processed_alerts:
        # 環境変数名の統一（フォールバック対応）
        webhook_url = os.getenv("SLACK_GOOGLE_ALERTS_WEBHOOK_URL") or os.getenv(
            "SLACK_WEBHOOK_URL_GOOGLE_ALERTS"
        )
        if webhook_url:
            try:
                logger.info(
                    f"Slack送信開始: {len(processed_alerts)}件のアラートを送信中..."
                )
                async with SlackPublisher(webhook_url) as slack:
                    await slack.send_articles(processed_alerts, title="Google Alerts")
                logger.info("Slackへの送信が完了しました")
            except Exception as e:
                logger.error(f"Slackへの送信エラー: {e}")
        else:
            logger.warning(
                "SLACK_GOOGLE_ALERTS_WEBHOOK_URL環境変数が設定されていません"
            )

    logger.info("処理が完了しました")


if __name__ == "__main__":
    main()
