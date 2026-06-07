# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Quick Start with Makefile (Docker - Recommended)
```bash
# Simple commands for Docker execution
make arxiv                           # Run ArXiv with defaults
make -- arxiv --date 2025-09-04 --max-results 100
make -- medium --date 2024-01-15 --notion
make -- google --hours 24
make -- youtube --url https://youtube.com/watch?v=...

# Test modes
make arxiv-test                      # Process 1 paper for testing
make medium-test                     # Process 1 article for testing

# Note: Use -- (double dash) before target name when passing options with dashes

# Docker management
make build                           # Build Docker images
make shell                           # Open interactive shell
make help                            # Show all available commands
```

### Environment Setup and Dependencies
```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync                      # Basic features
uv sync --extra whisper     # Include YouTube transcription

# Add new dependencies
uv add package-name         # Regular dependency
uv add --dev pytest black ruff mypy  # Dev dependencies
```

### Running Tools (Local)
```bash
# ArXiv paper search and translation
uv run arxiv --keywords "LLM" "RAG" --days 7
uv run arxiv --date 2024-01-15 --max-results 100

# Medium Daily Digest processing (uses email preview by default)
uv run medium --date 2024-01-15
uv run medium --use-jina              # Use Jina AI Reader for full article content
uv run medium --translate --notion    # Auto-translate articles with claps >= threshold
uv run medium --translate --cdp --notion  # CDPモード（Cloudflare回避、推奨）

# Medium Full-Text Translation (Playwright + LLM)
# Notion Medium DB に該当ページが無い URL の場合は新規ページを作成して翻訳本文を保存
uv run medium-translate --url "https://medium.com/..."
uv run medium-translate --url "https://..." --url "https://..."  # Multiple articles
uv run medium-translate --url "https://..." --provider openai    # Use OpenAI
uv run medium-translate --url "https://..." --dry-run            # Preview only
uv run medium-translate --url "https://..." --debug              # Dump fetched HTML to outputs/medium_translate_debug/

# Medium Scrape (English Markdown to stdout, no translation)
# 翻訳・要約・Notion保存は一切行わず、英語原文 Markdown を stdout に出力（llm-wiki 連携用）
uv run scrape-medium --url "https://medium.com/..."              # Standalone Playwright (Cloudflare に弱い)
uv run scrape-medium --url "https://medium.com/..." --cdp        # CDP モード（ログイン済み Chrome 利用、推奨）

# Discover Medium articles from Notion (JSON to stdout)
# Notion Medium DB から直近 N 日分の記事を JSON 配列で stdout 出力（llm-wiki 連携用）
uv run discover-notion-medium                                    # 直近7日分（デフォルト）
uv run discover-notion-medium --days 3                           # 直近3日分
uv run discover-notion-medium --days 7 --database-id "abc123"    # DB ID 明示指定

# ArXiv Paper Full-Text Translation (PDF + marker-pdf + LLM)
uv run arxiv-translate --url "https://arxiv.org/abs/2401.12345"  # Full pipeline (with VLM repair)
uv run arxiv-translate --url "https://..." --provider openai     # Use OpenAI
uv run arxiv-translate --url "https://..." --dry-run             # Preview only
uv run arxiv-translate --url "https://..." --no-vlm-repair       # Skip VLM parse repair
# Individual steps (for retry on failure)
uv run arxiv-translate parse     --url "https://arxiv.org/abs/..."  # PDF→Markdown（出力は outputs/arxiv_translate/{safe_id}/ 配下、VLM修復実行）
uv run arxiv-translate parse     --url "https://..." --no-vlm-repair  # PDF→Markdownのみ、VLM修復スキップ
uv run arxiv-translate translate --url "https://arxiv.org/abs/..."  # Markdown→日本語
uv run arxiv-translate upload    --url "https://arxiv.org/abs/..."  # 日本語→Notion（画像アップロード + Abstract 日本語訳）
uv run arxiv-translate upload    --url "https://..." --provider openai  # Abstract翻訳プロバイダ指定
uv run arxiv-translate repair    --url "https://arxiv.org/abs/..."  # 既存 raw.md に対し VLM 修復のみ実行
uv run arxiv-translate repair    --url "https://..." --dry-run      # 検出のみログ出力（書き換えなし）

# X (Twitter) AI Trend Digest
uv run x-trend                                    # デフォルト設定で実行
uv run x-trend --dry-run                          # Slack送信なしのプレビュー
uv run x-trend --region japan                     # 日本トレンドのみ
uv run x-trend --region global                    # グローバルトレンドのみ
uv run x-trend --provider gemini                  # Gemini APIを使用
uv run x-trend --test                             # テストモード（トレンド3件、ツイート5件）
uv run x-trend --no-trends                        # トレンド検索をスキップ
uv run x-trend --no-keywords                      # キーワード検索をスキップ
uv run x-trend --no-timeline                      # ユーザータイムライン監視をスキップ

# X (Twitter) フォロー中アカウント一覧取得
uv run x-followings --user YOUR_USERNAME           # フォロー一覧を取得
uv run x-followings --user YOUR_USERNAME --limit 50  # 上限指定
uv run x-followings --user YOUR_USERNAME --format yaml  # settings.yaml用YAML出力

# Google Alerts processing
uv run google-alerts --hours 12

# Google Alerts Article Full-Text Translation (Jina AI Reader + LLM)
uv run google-alerts-translate --url "https://example.com/article"
uv run google-alerts-translate --url "https://..." --url "https://..."  # Multiple
uv run google-alerts-translate --url "https://..." --provider openai    # Use OpenAI
uv run google-alerts-translate --url "https://..." --dry-run            # Preview only

# YouTube video summarization (requires whisper extra)
uv run youtube --url "https://youtube.com/watch?v=..."

# YouTube Mail Digest（特定送信元メール内のYouTube動画を要約しSlack配信+Notion保存）
# settings.yaml の youtube_mail_digest.profiles に「送信元→保存先」を複数定義して実行
# 字幕優先（無ければWhisperフォールバック）。重複は per-profile で processed.json に記録しスキップ
uv run youtube-mail-digest                          # 全プロファイルを直近24時間分処理
uv run youtube-mail-digest --hours 24               # 取得期間を指定
uv run youtube-mail-digest --date 2026-06-07        # 特定日のメールを処理
uv run youtube-mail-digest --profile ai-newsletter  # 特定プロファイルのみ
uv run youtube-mail-digest --profile x --no-notion  # Slackのみ（Notion保存なし）
uv run youtube-mail-digest --profile x --no-slack   # Notionのみ（Slack配信なし）
uv run youtube-mail-digest --test                   # 各プロファイル先頭1動画のみ
uv run youtube-mail-digest --dry-run                # Slack/Notion送信なしのプレビュー
uv run youtube-mail-digest --provider openai        # 要約LLMプロバイダを指定

# Google Alert Weekly Digest (summarizes top articles from Notion)
# Default provider: openai (for fast batch scoring)
uv run google-alert-weekly-digest --days 7 --top 20
uv run google-alert-weekly-digest --dry-run  # Preview without sending to Slack
uv run google-alert-weekly-digest --provider ollama  # Use local Ollama instead

# Google Alert Daily Digest (Top10 / past 24h, scheduled via launchd at 19:00 JST)
# Default provider: openai
uv run google-alert-daily-digest --hours 24 --top 10
uv run google-alert-daily-digest --dry-run            # Preview without sending to Slack
uv run google-alert-daily-digest --quiet              # Skip Slack send when 0 articles
uv run google-alert-daily-digest --provider gemini    # Use Gemini instead

# ArXiv Weekly Digest (LLM scoring with optional Tavily trend context)
# Default provider: openai (for fast batch scoring)
uv run arxiv-weekly --days 7 --top 10
uv run arxiv-weekly --dry-run              # Preview without sending to Slack
uv run arxiv-weekly --no-trends            # Skip Tavily trend research
uv run arxiv-weekly --provider ollama      # Use local Ollama instead
uv run arxiv-weekly --provider gemini      # Use Gemini API

# Test modes (process only 1 article for testing)
uv run medium --test --notion
uv run arxiv --test --max-results 1
```

### Development
```bash
# Code formatting and linting
uv run ruff format minitools/
uv run ruff check minitools/
uv run mypy minitools/

# Run tests
uv run pytest tests/
```

## Architecture Overview

This is a content aggregation and processing system that collects articles from various sources (ArXiv, Medium, Google Alerts, YouTube), translates/summarizes them using Ollama LLMs, and publishes to Notion and Slack.

### Core Components

#### Collectors (`minitools/collectors/`)
- **ArxivCollector**: Searches ArXiv for papers using specified keywords
- **MediumCollector**: Extracts articles from Medium Daily Digest emails via Gmail API
  - Uses email preview text by default (faster, avoids Cloudflare blocking)
  - Optionally uses Jina AI Reader (`r.jina.ai`) with `--use-jina` flag
- **GoogleAlertsCollector**: Processes Google Alerts emails via Gmail API
- **YouTubeCollector**: Downloads and transcribes YouTube videos
  - `fetch_subtitles()`: yt-dlp で字幕（手動→自動、ja→en 優先）を取得し VTT をプレーンテキスト化（`parse_subtitle_to_text`）。取得失敗・字幕なしは None
  - `get_transcript()`: 字幕優先→無ければ既存 `process_video`（音声DL + MLX Whisper）にフォールバック。`source` を `"subtitle"`/`"whisper"` で返す
- **YouTubeEmailCollector**: 特定送信元(from)の Gmail を取得し本文 HTML から YouTube 動画 URL を抽出（`youtube-mail-digest` 用）
  - Gmail 認証・本文抽出は `GoogleAlertsCollector` のパターンを流用し、`from:` をパラメータ化（token.pickle 共有、`gmail.readonly`）
  - `extract_youtube_urls()` / `normalize_youtube_url()` / `extract_video_id()`: watch / youtu.be / shorts / embed を正規化し video_id で dedup（純粋関数、単体テスト済み）
- **XTrendCollector**: Fetches trending topics, keyword search results, and user timelines from X (Twitter) via TwitterAPI.io
  - 3 sources: Trends (Japan/Global WOEID), keyword search, user timeline monitoring
  - `collect_all()`: Parallel collection of all 3 sources via `asyncio.gather`
  - `collect()`: Trend-only collection with `fetch_tweets=False` option for cost optimization
  - Async HTTP with exponential backoff retry (max 3 retries), Semaphore(5) for parallel API calls

#### Scrapers (`minitools/scrapers/`)
- **MediumScraper**: Fetches full article HTML via Playwright
  - CDP mode (recommended): Connects to real Chrome, bypasses Cloudflare
  - Standalone mode: Uses Playwright built-in Chromium
- **MarkdownConverter**: Converts Medium article HTML to structured Markdown
- **ArxivScraper**: Downloads ArXiv papers as PDF and converts to Markdown using marker-pdf
  - httpx-based PDF download with retry (no Playwright needed)
  - marker-pdf for PDF→Markdown conversion (sections, math, figures, tables)
  - Math preservation: inline `$...$` and block `$$...$$` (marker-pdf native support)
  - Image extraction from PDF (stored as PaperImage dataclass)
  - ArXiv API metadata fetching via feedparser (title, authors, date, abstract)
- **JinaReader**: Async client for `https://r.jina.ai/{url}` Markdown extraction
  - Used by `google-alerts-translate` for English news / blog articles (non-Medium)
  - Exponential backoff retry (1s/2s/4s, max 3), Cloudflare/`error 403`/`just a moment` detection
  - `extract_metadata()` parses `Title:` / `Published Time:` headers (ISO 8601 → YYYY-MM-DD)
  - **Not for Medium**: Medium has site-side Jina blocking; `MediumCollector` keeps its own implementation

#### LLM Abstraction Layer (`minitools/llm/`)
- **BaseLLMClient**: Abstract base class for LLM clients
- **get_llm_client()**: Factory function supporting Ollama, OpenAI, and Gemini
- **LangChain integration**: Preferred implementation with native fallback
- **Embedding support**: `get_embedding_client()` for similarity detection

#### Readers (`minitools/readers/`)
- **NotionReader**: Reads articles from Notion databases (for weekly digest)

#### Researchers (`minitools/researchers/`)
- **TrendResearcher**: Fetches current AI trends using Tavily API for context-aware scoring

#### Processors (`minitools/processors/`)
- **Translator**: Translates content to Japanese using Ollama models
- **Summarizer**: Creates concise summaries using Ollama models
- **DigestProcessor** (alias: `WeeklyDigestProcessor`): Generates AI digests (weekly/daily) with importance scoring
  - **Batch scoring**: Processes 20 articles per LLM call for 8x speedup
  - **`summarize_all_articles`**: Generates 4–6 sentence Japanese overview of all articles (single-shot ≤ chunk_size, 2-stage map-reduce above) — used for Daily Digest「今日のまとめ」
  - Default provider: OpenAI (configurable via `defaults.weekly_digest.provider` / `defaults.daily_digest.provider`)
  - Used by both `google-alert-weekly-digest` and `google-alert-daily-digest`
- **ArxivWeeklyProcessor**: ArXiv paper ranking via LLM importance scoring
  - **Batch scoring**: Processes 20 papers per LLM call for 8x speedup
  - Optional Tavily trend research for context-aware scoring (`--no-trends` to skip)
  - Default provider: OpenAI (configurable via `defaults.arxiv_weekly.provider`)
- **FullTextTranslator**: Translates full Markdown articles with structure preservation
  - Used by `medium-translate`, `arxiv-translate`, `google-alerts-translate`
  - Default provider: Gemini (`gemini-3.1-flash-lite-preview`, `thinking_level=minimal`) — configurable via `defaults.<feature>.translate_provider` / `translate_model`
  - Chunk splitting by headings for LLM context length management
  - Code block preservation (only comments translated)
  - Retry with exponential backoff
  - `arxiv-translate` 出力構造（論文ごとのフォルダ）:
    ```
    outputs/arxiv_translate/{safe_id}/
    ├── {safe_id}.pdf       # PDF（識別性のため safe_id 維持）
    ├── metadata.json       # PaperMetadata
    ├── raw.md              # marker-pdf 出力
    ├── repaired.md         # VLM 修復後（applied > 0 のときのみ生成）
    ├── translated.md       # 日本語訳（最終出力）
    ├── _page_X_Figure_Y.jpeg ...   # PDF から抽出した画像（裸ファイル名）
    └── page_images/        # VLM 修復用ページレンダリングキャッシュ
    ```
    画像はフォルダ直下に裸ファイル名で保存される（marker-pdf の image refs と一致するためローカルプレビュー可）。
- **VlmParseRepairer**: Repairs marker-pdf parse errors using multimodal LLMs (Gemini/OpenAI)
  - `ParseErrorDetector`: heuristic detection of broken tables / orphan figures (no LLM cost)
  - `PdfPageRenderer`: PyMuPDF-based PNG rendering with disk caching (`outputs/arxiv_translate/{safe_id}/page_images/`)
  - `VlmRepairer`: VLM-based table reconstruction + Japanese figure summaries (Semaphore=2, retry 3x)
  - `MarkdownPatcher`: validation-aware in-place replacement (idempotent figure notes)
  - Integrated into `arxiv-translate parse`; controllable via `--no-vlm-repair`
  - Settings: `defaults.arxiv_translate.vlm_repair.{enabled,provider,model,max_total_calls,...}` in settings.yaml
  - Standalone subcommand: `arxiv-translate repair --url ... [--dry-run]`
- **XTrendProcessor**: Filters AI-related trends and generates Japanese summaries for 3 sources
  - Trends: LLM filtering by trend name → tweet fetch for AI-related only → summarization
  - Keywords: Tweet summarization per keyword
  - Timelines: LLM filtering for AI-related tweets → summarization per account
  - `process_all()`: Unified processing of all 3 sources
- **YouTubeSummarizer**: 文字起こしから日本語の要約文＋ポイント箇条書き（3〜7個）を生成（`youtube-mail-digest` 用）
  - `get_llm_client` 経由で provider 切替（デフォルト Gemini、`defaults.youtube_mail_digest.{provider,model,thinking_level}`）
  - 1コールで要約＋ポイントを生成し `_parse_summary_response` でパース、指数バックオフリトライ（`Summary(text, points)` を返す）
- **DuplicateDetector**: Detects similar articles using embeddings
- All use async processing for parallel execution (3-5x performance improvement)

#### Publishers (`minitools/publishers/`)
- **NotionPublisher**: Saves articles to Notion databases with batch processing
  - `_retry_api_call()`: Common retry helper for all Notion API calls with rate limit detection and exponential backoff (2s, 4s, 8s, max 3 retries)
  - `find_page_by_url()`: Find existing page by URL, returns `PageInfo(page_id, is_translated)` to skip already-translated pages
  - `append_blocks()`: Append translated blocks to existing pages (100-block batch)
  - `update_page_properties()`: Update existing page properties (e.g., Translated checkbox)
  - `create_child_page(parent_page_id, title, blocks)`: 親ページ配下に子ページを作成（`parent={"page_id": ...}`、`youtube-mail-digest` 用）。**注意:** 子ページは title 以外の properties を設定できない（DB プロパティを渡すと 400）。メタ情報は全て本文ブロックとして書く
  - Medium properties: Title, Japanese Title, URL, Author, Date, Summary, Claps (number), Translated (checkbox)
- **NotionBlockBuilder**: Converts Markdown to Notion API block format (headings, code, images, lists, quotes)
- **SlackPublisher**: Sends formatted notifications to Slack webhooks (including weekly/daily digest format)
  - Medium Daily Digest includes claps count (👏) per article
  - Google Alerts Daily Digest: `format_daily_digest(date, articles, daily_summary="")` で「📝 今日のまとめ」+「🏆 今日の重要記事 Top N」の2セクション構成
  - X Trend Digest: セクション分割送信で省略なし
    - `format_x_trend_digest_sections(ProcessResult)` → `list[str]`（セクションごとのメッセージリスト）
    - `format_x_trend_digest(ProcessResult)` → `str`（後方互換ラッパー、内部で sections を結合）
    - `send_messages(messages)`: 複数メッセージを順番に送信（0.5秒間隔でレート制限回避）
  - YouTube Mail Digest: `format_youtube_digest(videos, title, date, max_message_length)` → `list[str]`（動画ごとにタイトル・チャンネル・URL・要約・ポイントを整形し、長文はセクション分割して `send_messages` で送信）

### Key Design Patterns

1. **Async Processing**: All processors use asyncio for parallel execution
   - Max 10 concurrent article processing
   - Max 3 concurrent Ollama API calls
   - Max 3 concurrent Notion API calls

2. **Configuration**: Dual config system
   - `.env`: Security credentials (API keys, webhooks)
   - `settings.yaml`: Application settings (models, parameters)

3. **Entry Points**: CLI commands via pyproject.toml
   - `arxiv`, `medium`, `medium-translate`, `arxiv-translate`, `google-alerts`, `google-alerts-translate`, `youtube`, `youtube-mail-digest`, `google-alert-weekly-digest`, `google-alert-daily-digest`, `arxiv-weekly`, `x-trend`, `x-followings`, `scrape-medium`, `discover-notion-medium`

4. **Error Handling**: Retry logic with exponential backoff for API calls
   - NotionPublisher: `_retry_api_call()` detects rate limit errors and retries with 2s/4s/8s backoff (max 3 retries)
   - All Notion API methods (`check_existing`, `create_page`, `find_page_by_url`, `update_page_properties`, `append_blocks`) use this common retry logic

### External Dependencies

- **Ollama**: Local LLM server for translation/summarization
  - Required for legacy paths (`arxiv` / `medium` / `google-alerts` / `youtube`) that use `Translator` / `Summarizer`
  - Models: `gemma3:27b` (translation/summarization), `gemma3:12b` (YouTube)
  - Not required for `medium-translate` / `arxiv-translate` / `google-alerts-translate` / `arxiv-weekly` / `google-alert-weekly-digest` (default to Gemini or OpenAI)
- **OpenAI** (optional): Alternative LLM provider via `llm.provider` setting
- **Gemini** (optional): Google AI Studio free tier via `langchain-google-genai`
  - Default model: `gemini-3.1-flash-lite-preview`
  - Default thinking_level: `minimal` (configurable via `llm.gemini.default_thinking_level`)
  - VLM 修復用モデル（精度重視）: `gemini-3-flash-preview` + `thinking_level: medium`
  - 用途別モデル指定: `defaults.<機能>.translate_model` / `translate_thinking_level` で上書き可能
  - Requires `GEMINI_API_KEY` environment variable
- **LangChain**: Unified LLM interface (preferred over native clients)
- **Gmail API**: For fetching Medium and Google Alerts emails
- **Jina AI Reader**: Web content extraction service (`https://r.jina.ai/`)
- **Notion API**: For database operations (read and write)
- **Slack Webhooks**: For notifications
- **FFmpeg**: For YouTube audio extraction
- **Tavily API**: For trend research in ArXiv weekly digest (optional)
- **TwitterAPI.io**: For fetching X (Twitter) trends and tweets (requires `TWITTER_API_IO_KEY`)
- **marker-pdf**: PDF→Markdown conversion for ArXiv paper full-text translation (includes surya OCR models)

## Script Architecture

### Modular Architecture
The project uses a modular architecture (`minitools/` + `scripts/`):
- **Collectors**: Data collection from external sources (ArXiv, Medium, Google Alerts, YouTube)
- **LLM**: Abstraction layer for Ollama/OpenAI/Gemini with LangChain integration
- **Scrapers**: Web scraping (Playwright-based Medium article fetching, HTML-to-Markdown conversion)
- **Readers**: Data reading from databases (Notion)
- **Researchers**: External data research (Tavily API for trend analysis)
- **Processors**: Content processing (translation, summarization, full-text translation, weekly digest, arxiv weekly, duplicate detection)
- **Publishers**: Output to destinations (Notion, Slack)
- **CLI Scripts**: Entry points via `pyproject.toml` commands

### Configuration System
- **`.env`**: Security credentials (API keys, webhooks) - never commit
- **`settings.yaml`**: Application settings (models, processing parameters, defaults)
- **Dual configuration lookup**: Environment variables override YAML settings

### Logging Architecture
- **Colored terminal output**: Different colors per log level via `ColoredFormatter`
- **File logging**: Separate log files per tool in `outputs/logs/`
- **Structured logging**: Detailed progress tracking with batch processing indicators
- **Log rotation**: Manual cleanup required (no automatic rotation)

### Data Flow Pattern
1. **Collection**: Source-specific collectors fetch content
2. **Processing**: Async translation/summarization via LLM (Ollama/OpenAI/Gemini)
3. **Publishing**: Batch operations to Notion with duplicate detection
4. **Notification**: Slack webhooks for completion status

### URL Handling
Critical pattern for Medium articles:
- **URL normalization**: Remove tracking parameters, trailing slashes, hash fragments  
- **Duplicate detection**: Based on cleaned URLs across all dates
- **Retry logic**: Exponential backoff for network failures

### Async Processing Patterns
- **Semaphores**: Limit concurrent API calls (3 Ollama, 3 Notion, 10 HTTP)
- **Batch processing**: Articles grouped in batches of 10 for progress tracking
- **Error isolation**: Individual article failures don't stop batch processing
- **Resource cleanup**: Context managers for HTTP sessions and database connections