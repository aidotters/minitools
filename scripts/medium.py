#!/usr/bin/env python3
"""
Medium Daily Digest collection script - backward compatibility wrapper.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

from minitools.collectors.medium import MediumCollector
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
    """メイン処理（非同期版）"""
    parser = argparse.ArgumentParser(
        description="Medium Daily Digestメールを取得してNotionに保存"
    )
    parser.add_argument("--date", type=str, help="取得する日付 (YYYY-MM-DD形式)")
    parser.add_argument("--slack", action="store_true", help="Slackへの送信のみ実行")
    parser.add_argument("--notion", action="store_true", help="Notionへの保存のみ実行")
    parser.add_argument("--debug", action="store_true", help="デバッグモードで実行")
    parser.add_argument(
        "--test", action="store_true", help="テストモード（最初の1記事のみ処理）"
    )
    parser.add_argument(
        "--use-jina",
        action="store_true",
        help="Jina AI Readerを使用して記事本文を取得（デフォルトはメールのプレビューを使用）",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="拍手数が閾値以上の記事を全文翻訳してNotionに追記",
    )
    parser.add_argument(
        "--cdp",
        action="store_true",
        help="実際のChromeにCDP接続（Cloudflare回避、--translate使用時に推奨）",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "gemini"],
        default=None,
        help="全文翻訳のLLMプロバイダー（--translate使用時）",
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
    logger = setup_logger(
        "scripts.medium", log_file="medium_daily_digest.log", level=log_level
    )

    # 日付の設定
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            logger.error("日付は YYYY-MM-DD 形式で指定してください")
            return
    else:
        target_date = datetime.now()

    # フラグの処理
    save_notion = not args.slack or args.notion
    send_slack = not args.notion or args.slack

    # コレクターの初期化
    collector = MediumCollector()

    # メールを取得
    logger.info(
        f"Medium Daily Digest ({target_date.strftime('%Y-%m-%d')}) の処理を開始します..."
    )

    async with collector:
        messages = await collector.get_digest_emails(target_date)

        if not messages:
            logger.info("Medium Daily Digestメールが見つかりません")
            return

        # メール本文から記事を抽出
        email_body = collector.extract_email_body(messages[0])
        articles = collector.parse_articles(email_body)

        if not articles:
            logger.info("メールに記事が見つかりません")
            return

        logger.info(f"{len(articles)}件の記事を検出しました")

        # テストモードの場合は最初の1件のみ処理
        if args.test:
            articles = articles[:1]
            logger.info("テストモード: 最初の1記事のみ処理します")

        # Jina Reader使用設定（コマンドラインオプション > 設定ファイル）
        use_jina_reader = args.use_jina or config.get(
            "defaults.medium.use_jina_reader", False
        )
        if use_jina_reader:
            logger.info("Jina AI Readerを使用して記事本文を取得します")
        else:
            logger.info(
                "メールのプレビューテキストを使用します（Jina Readerはスキップ）"
            )

        # 翻訳と要約
        translator = Translator()
        processed_articles = []

        logger.info("記事の翻訳と要約を開始します...")
        # バッチ処理のための設定
        batch_size = 10 if not use_jina_reader else 5  # Jina不使用時は並列数を増やせる
        total_batches = (len(articles) + batch_size - 1) // batch_size

        async def process_article(article, index, total):
            """個別記事の処理"""
            try:
                logger.info(f"  記事 {index}/{total} 処理開始: {article.title[:50]}...")

                content = ""
                author = None

                # Jina Readerを使用する場合のみ記事内容を取得
                if use_jina_reader:
                    content, author = await collector.fetch_article_content(article.url)
                    if author:
                        article.author = author
                    # コンテンツ取得失敗時はメールのプレビューをフォールバックとして使用
                    if not content and article.preview:
                        content = article.preview
                        logger.info(
                            f"  -> プレビューをフォールバックとして使用: {len(content)} chars"
                        )
                else:
                    # Jina Readerを使用しない場合はプレビューを直接使用
                    content = article.preview

                # 翻訳と要約
                if content:
                    result = await translator.translate_with_summary(
                        title=article.title, content=content, author=article.author
                    )
                    article.japanese_title = result["japanese_title"]
                    article.japanese_summary = result["japanese_summary"]
                    logger.info(
                        f"  -> 翻訳・要約完了: {article.japanese_title[:30]}..."
                    )
                else:
                    logger.warning(f"  -> コンテンツ取得失敗: {article.title[:50]}...")

                # 辞書形式に変換
                return {
                    "title": article.title,
                    "url": article.url,
                    "author": article.author,
                    "claps": article.claps,
                    "japanese_title": article.japanese_title,
                    "japanese_summary": article.japanese_summary,
                    "date": target_date.strftime("%Y-%m-%d"),
                }
            except Exception as e:
                logger.error(f"  -> 処理エラー '{article.title[:50]}...': {e}")
                return None

        # バッチごとに処理
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(articles))
            batch = articles[start_idx:end_idx]

            logger.info(
                f"バッチ {batch_num + 1}/{total_batches} を処理中 ({len(batch)}件)..."
            )

            # バッチ内の記事を並列処理
            tasks = [
                process_article(article, start_idx + i + 1, len(articles))
                for i, article in enumerate(batch)
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 成功した記事のみを追加
            for result in batch_results:
                if result and not isinstance(result, Exception):
                    processed_articles.append(result)

    # Notionに保存
    if save_notion and processed_articles:
        # 環境変数名の統一（フォールバック対応）
        database_id = os.getenv("NOTION_MEDIUM_DATABASE_ID") or os.getenv(
            "NOTION_DB_ID_DAILY_DIGEST"
        )
        if database_id:
            try:
                logger.info(f"Notionに{len(processed_articles)}件の記事を保存中...")
                publisher = NotionPublisher(source_type="medium")
                result = await publisher.batch_save_articles(
                    database_id, processed_articles
                )
                stats = result.get("stats", {})
                logger.info("=" * 60)
                logger.info("Notionへの保存結果:")
                logger.info(f"  成功: {stats.get('success', 0)}件")
                logger.info(f"  スキップ (既存): {stats.get('skipped', 0)}件")
                logger.info(f"  失敗: {stats.get('failed', 0)}件")
                logger.info("=" * 60)
            except Exception as e:
                logger.error(f"Notionへの保存エラー: {e}")

    # Slackに送信
    if send_slack and processed_articles:
        # 環境変数名の統一（フォールバック対応）
        webhook_url = os.getenv("SLACK_MEDIUM_WEBHOOK_URL") or os.getenv(
            "SLACK_WEBHOOK_URL_MEDIUM_DAILY_DIGEST"
        )
        if webhook_url:
            try:
                async with SlackPublisher(webhook_url) as slack:
                    await slack.send_articles(
                        processed_articles,
                        date=target_date.strftime("%Y-%m-%d"),
                        title="Medium Daily Digest",
                    )
                logger.info("Slackへの送信が完了しました")
            except Exception as e:
                logger.error(f"Slackへの送信エラー: {e}")

    # 全文翻訳モード
    if args.translate and processed_articles:
        clap_threshold = config.get("defaults.medium.translate_clap_threshold", 100)
        translate_targets = [
            a for a in processed_articles if a.get("claps", 0) >= clap_threshold
        ]

        if translate_targets:
            logger.info(
                f"全文翻訳対象: {len(translate_targets)}件 (拍手数 >= {clap_threshold})"
            )

            from minitools.scrapers.medium_scraper import MediumScraper
            from minitools.scrapers.markdown_converter import MarkdownConverter
            from minitools.processors.full_text_translator import FullTextTranslator
            from minitools.publishers.notion_block_builder import NotionBlockBuilder

            database_id = os.getenv("NOTION_MEDIUM_DATABASE_ID") or os.getenv(
                "NOTION_DB_ID_DAILY_DIGEST"
            )
            if database_id:
                converter = MarkdownConverter()
                ft_translator = FullTextTranslator(provider=args.provider)
                block_builder = NotionBlockBuilder()
                notion_pub = NotionPublisher(source_type="medium")

                # 翻訳済み記事を事前にフィルタリング
                pending_targets = []
                already_translated = 0
                for article in translate_targets:
                    url = article.get("url", "")
                    page_info = await notion_pub.find_page_by_url(database_id, url)
                    if not page_info:
                        logger.warning(f"Page not found for URL: {url}")
                        continue
                    if page_info.is_translated:
                        logger.info(f"Already translated, skipping: {url}")
                        already_translated += 1
                        continue
                    pending_targets.append((article, page_info))

                if already_translated > 0:
                    logger.info(f"翻訳済み: {already_translated}件（スキップ）")

                if not pending_targets:
                    logger.info("全記事が翻訳済みです")
                else:
                    logger.info(f"未翻訳: {len(pending_targets)}件を翻訳します")
                    translate_stats = {"success": 0, "failed": 0}

                    async with MediumScraper(cdp_mode=args.cdp) as scraper:
                        for idx, (article, page_info) in enumerate(pending_targets, 1):
                            url = article.get("url", "")
                            title = article.get("title", "")[:50]
                            logger.info(
                                f"[{idx}/{len(pending_targets)}] 全文翻訳開始: "
                                f"{title}..."
                            )
                            try:
                                html = await scraper.scrape_article(url)
                                if not html:
                                    logger.warning(f"  HTML取得失敗（空）: {url}")
                                    translate_stats["failed"] += 1
                                    continue

                                md = converter.convert(html)
                                logger.info(f"  Markdown変換: {len(md)} chars")
                                translated = await ft_translator.translate(md)
                                logger.info(f"  翻訳完了: {len(translated)} chars")

                                blocks = block_builder.build_blocks(translated)
                                logger.info(
                                    f"  Notionブロック構築: {len(blocks)} blocks"
                                )
                                if not blocks:
                                    logger.warning(
                                        f"  ブロックが空のためスキップ: {url}"
                                    )
                                    translate_stats["failed"] += 1
                                    continue

                                success = await notion_pub.append_blocks(
                                    page_info.page_id, blocks
                                )
                                if not success:
                                    logger.error(
                                        f"  Notionブロック追記失敗: "
                                        f"page_id={page_info.page_id}"
                                    )
                                    translate_stats["failed"] += 1
                                    continue

                                logger.info(
                                    f"  Notionブロック追記成功: "
                                    f"page_id={page_info.page_id}"
                                )

                                update_props = {"Translated": {"checkbox": True}}
                                claps = article.get("claps")
                                if claps is not None:
                                    update_props["Claps"] = {"number": claps}
                                prop_success = await notion_pub.update_page_properties(
                                    page_info.page_id,
                                    update_props,
                                )
                                if not prop_success:
                                    logger.error(
                                        f"  Translatedチェックボックス更新失敗: "
                                        f"page_id={page_info.page_id}"
                                    )
                                    # ブロックは追記済みなので成功扱い
                                    # だがチェックボックスは未更新

                                translate_stats["success"] += 1
                                logger.info(f"  完了: {title}...")
                            except Exception as e:
                                logger.error(f"  Translation error for {url}: {e}")
                                translate_stats["failed"] += 1

                    logger.info("=" * 60)
                    logger.info("全文翻訳結果:")
                    logger.info(f"  成功: {translate_stats['success']}件")
                    logger.info(f"  失敗: {translate_stats['failed']}件")
                    if already_translated > 0:
                        logger.info(f"  翻訳済み: {already_translated}件")
                    logger.info("=" * 60)
        else:
            logger.info(
                f"拍手数 >= {clap_threshold} の記事がないため、全文翻訳はスキップします"
            )

    logger.info("処理が完了しました")
    if processed_articles:
        logger.info(f"  処理記事数: {len(processed_articles)}件")
        logger.info(f"  対象日付: {target_date.strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    main()
