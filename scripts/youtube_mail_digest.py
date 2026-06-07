#!/usr/bin/env python3
"""
youtube-mail-digest: 特定送信元メール内の YouTube 動画を要約し Slack 配信 + Notion 保存。

settings.yaml の `youtube_mail_digest.profiles` で「送信元 → 保存先」を複数定義し、
プロファイルごとに Gmail 取得 → YouTube URL 抽出 → 字幕優先（無ければ Whisper）→
要約文+ポイント生成 → Slack/Notion 出力 を行う。重複は per-profile で記録しスキップ。
"""

import os
import asyncio
import logging
import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from minitools.collectors.youtube import YouTubeCollector
from minitools.collectors.youtube_email import YouTubeEmailCollector
from minitools.processors.youtube_summary import Summary, YouTubeSummarizer
from minitools.publishers.notion import NotionPublisher
from minitools.publishers.notion_block_builder import NotionBlockBuilder
from minitools.publishers.slack import SlackPublisher
from minitools.utils.config import get_config
from minitools.utils.logger import setup_logger
from minitools.utils.processed_store import ProcessedStore

load_dotenv()

logger = None  # setup_logger で初期化


def resolve_outputs(
    profile_slack: bool,
    profile_notion: bool,
    no_slack: bool,
    no_notion: bool,
) -> Tuple[bool, bool]:
    """
    プロファイル設定と CLI フラグから、有効な出力先を解決する。

    Args:
        profile_slack: プロファイルの slack フラグ
        profile_notion: プロファイルの notion フラグ
        no_slack: --no-slack（実行時に Slack を無効化）
        no_notion: --no-notion（実行時に Notion を無効化）

    Returns:
        (slack 有効, notion 有効)
    """
    slack_on = bool(profile_slack) and not no_slack
    notion_on = bool(profile_notion) and not no_notion
    return slack_on, notion_on


def build_notion_markdown(video: Dict[str, Any]) -> str:
    """動画要約を Notion 本文用 Markdown に整形する（メタは本文ブロックとして記録）"""
    summary: Summary = video["summary"]
    md = f"## 要約\n\n{summary.text}\n\n"
    if summary.points:
        md += "## ポイント\n\n"
        md += "\n".join(f"- {p}" for p in summary.points)
        md += "\n\n"
    md += "## 情報\n\n"
    md += f"- チャンネル: {video.get('author', 'Unknown')}\n"
    md += f"- URL: {video['url']}\n"
    if video.get("email_date"):
        md += f"- 配信日: {video['email_date']}\n"
    md += f"- 文字起こし元: {video.get('source', 'unknown')}\n"
    return md


def main():
    """エントリーポイント（同期版）"""
    asyncio.run(main_async())


async def main_async():
    global logger
    config = get_config()

    parser = argparse.ArgumentParser(
        description="特定メール内の YouTube 動画を要約し Slack 配信 + Notion 保存"
    )
    parser.add_argument(
        "--profile", help="処理するプロファイル名（未指定で全プロファイル）"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=config.get("defaults.youtube_mail_digest.hours_back", 24),
        help="過去何時間分のメールを取得するか",
    )
    parser.add_argument("--date", help="特定日のメールを取得（YYYY-MM-DD）")
    parser.add_argument("--no-slack", action="store_true", help="Slack 配信を無効化")
    parser.add_argument("--no-notion", action="store_true", help="Notion 保存を無効化")
    parser.add_argument(
        "--test", action="store_true", help="各プロファイル先頭1動画のみ処理"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Slack/Notion 送信なしのプレビュー"
    )
    parser.add_argument(
        "--provider", help="要約 LLM プロバイダ（gemini/openai/ollama）"
    )
    parser.add_argument("--debug", action="store_true", help="デバッグログ")
    args = parser.parse_args()

    log_level = (
        logging.DEBUG
        if args.debug
        else getattr(logging, config.get("logging.level", "INFO").upper(), logging.INFO)
    )
    logger = setup_logger(
        "scripts.youtube_mail_digest",
        log_file="youtube_mail_digest.log",
        level=log_level,
    )

    date: Optional[datetime] = None
    if args.date:
        try:
            date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            logger.error(f"--date の形式が不正です（YYYY-MM-DD）: {args.date}")
            return

    profiles: List[Dict[str, Any]] = (
        config.get("youtube_mail_digest.profiles", []) or []
    )
    if not profiles:
        logger.error(
            "settings.yaml に youtube_mail_digest.profiles が定義されていません"
        )
        return

    if args.profile:
        profiles = [p for p in profiles if p.get("name") == args.profile]
        if not profiles:
            logger.error(f"プロファイルが見つかりません: {args.profile}")
            return

    # 共有コンポーネント
    yt_output_dir = config.get("defaults.youtube.temp_dir", "outputs/temp")
    whisper_model = config.get(
        "defaults.youtube.whisper_model", "mlx-community/whisper-large-v3-turbo"
    )
    yt_collector = YouTubeCollector(
        output_dir=yt_output_dir, whisper_model=whisper_model
    )
    summarizer = YouTubeSummarizer(provider=args.provider)
    block_builder = NotionBlockBuilder()
    store = ProcessedStore()

    # Notion クライアントは必要時に遅延生成（API キー無し環境で dry-run できるように）
    notion_client: Optional[NotionPublisher] = None

    def get_notion() -> NotionPublisher:
        nonlocal notion_client
        if notion_client is None:
            notion_client = NotionPublisher(source_type="youtube_mail")
        return notion_client

    # 動画処理の並列度（Whisper は重いので控えめ）
    sem = asyncio.Semaphore(
        config.get("defaults.youtube_mail_digest.max_concurrent", 2)
    )

    async def process_one(ref) -> Optional[Dict[str, Any]]:
        """1動画を文字起こし→要約（エラーは分離）"""
        async with sem:
            loop = asyncio.get_event_loop()
            try:
                data = await loop.run_in_executor(
                    None, yt_collector.get_transcript, ref.url
                )
            except Exception as e:
                logger.error(f"文字起こし取得エラー ({ref.url}): {e}")
                return None
            if not data or not data.get("transcript"):
                logger.warning(f"文字起こし取得失敗・スキップ: {ref.url}")
                return None
            try:
                summary = await summarizer.summarize(
                    data["transcript"], data.get("title", "")
                )
            except Exception as e:
                logger.error(f"要約エラー ({ref.url}): {e}")
                return None
            if not summary.text and not summary.points:
                logger.warning(f"要約が空・スキップ: {ref.url}")
                return None
            return {
                "video_id": ref.video_id,
                "title": data.get("title", "Unknown"),
                "author": data.get("author", "Unknown"),
                "url": ref.url,
                "summary": summary,
                "source": data.get("source", "unknown"),
                "email_date": ref.email_date,
            }

    total_processed = 0

    for profile in profiles:
        name = profile.get("name", "(no-name)")
        sender = profile.get("from")
        try:
            if not sender:
                logger.error(f"[{name}] from（送信元）が未設定。スキップ")
                continue

            slack_on, notion_on = resolve_outputs(
                profile.get("slack", True),
                profile.get("notion", True),
                args.no_slack,
                args.no_notion,
            )
            if not slack_on and not notion_on:
                logger.warning(f"[{name}] 出力先が無効。スキップ")
                continue

            logger.info(
                f"[{name}] 処理開始 (from={sender}, slack={slack_on}, "
                f"notion={notion_on}, dry_run={args.dry_run})"
            )

            collector = YouTubeEmailCollector(sender=sender)
            refs = collector.collect(hours_back=args.hours, date=date)
            new_refs = store.filter_new(name, refs)
            if args.test:
                new_refs = new_refs[:1]
            if not new_refs:
                logger.info(f"[{name}] 新規動画なし")
                continue

            logger.info(f"[{name}] {len(new_refs)}件の新規動画を処理")
            results_raw = await asyncio.gather(*[process_one(r) for r in new_refs])
            results = [r for r in results_raw if r]
            if not results:
                logger.warning(f"[{name}] 有効な要約結果なし")
                continue

            # Notion 保存（子ページ）
            if notion_on:
                parent_id = profile.get("notion_parent_page_id")
                if not parent_id:
                    logger.error(f"[{name}] notion_parent_page_id 未設定")
                elif args.dry_run:
                    logger.info(
                        f"[{name}] dry-run: Notion {len(results)}件の保存をスキップ"
                    )
                else:
                    notion = get_notion()
                    for v in results:
                        blocks = block_builder.build_blocks(build_notion_markdown(v))
                        page_id = await notion.create_child_page(
                            parent_id, v["title"], blocks
                        )
                        if page_id:
                            logger.info(f"[{name}] Notion保存: {v['title']}")
                        else:
                            logger.error(f"[{name}] Notion保存失敗: {v['title']}")

            # Slack 配信
            if slack_on:
                videos = [
                    {
                        "title": v["title"],
                        "author": v["author"],
                        "url": v["url"],
                        "summary": v["summary"].text,
                        "points": v["summary"].points,
                    }
                    for v in results
                ]
                async with SlackPublisher() as slack:
                    messages = slack.format_youtube_digest(videos, date=args.date)
                    if args.dry_run:
                        logger.info(f"[{name}] dry-run: Slackプレビュー")
                        for m in messages:
                            print(m)
                            print("---")
                    else:
                        webhook = os.getenv(profile.get("slack_webhook_env", ""))
                        if not webhook:
                            logger.error(
                                f"[{name}] Slack webhook 環境変数が未設定: "
                                f"{profile.get('slack_webhook_env')}"
                            )
                        else:
                            await slack.send_messages(messages, webhook)
                            logger.info(f"[{name}] Slack配信完了")

            # 処理済み記録（gather 後にまとめて永続化、dry-run 時はスキップ）
            if not args.dry_run:
                store.mark_many(name, [v["video_id"] for v in results])
                store.save()

            total_processed += len(results)
            logger.info(f"[{name}] 完了: {len(results)}件")

        except Exception as e:
            logger.error(f"[{name}] プロファイル処理エラー: {e}")
            continue

    logger.info(f"全プロファイル処理完了: 合計 {total_processed}件")


if __name__ == "__main__":
    main()
