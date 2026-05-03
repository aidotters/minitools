# 変更履歴 (CHANGELOG)

このドキュメントは、minitoolsプロジェクトの変更履歴をまとめたものです。

## [Unreleased]

### Changed
- **`arxiv_translate.vlm_repair.*` 設定キーを `defaults.arxiv_translate.vlm_repair.*` に統一** (2026-05-03)
  - 旧: トップレベル `arxiv_translate.vlm_repair.*` を `scripts/arxiv_translate.py:_build_repairer()` が直接参照
  - 新: `defaults.arxiv_translate.vlm_repair.*` 配下に統一（他の用途別設定キー命名と整合）
  - **既存ユーザの移行手順**: `settings.yaml` のトップレベル `arxiv_translate:` セクション配下の `vlm_repair:` ブロックを、`defaults.arxiv_translate:` 配下に移動する。例:
    ```yaml
    # Before
    arxiv_translate:
      vlm_repair:
        enabled: true
        model: "gemini-3-flash-preview"
        ...

    # After
    defaults:
      arxiv_translate:
        translate_provider: gemini
        translate_model: "gemini-3.1-flash-lite-preview"
        ...
        vlm_repair:
          enabled: true
          model: "gemini-3-flash-preview"
          ...
    ```
  - 影響: 旧キーは読み込まれなくなる。移行しない場合 `langchain_gemini.py` のフォールバック値（`gemini-3.1-flash-lite-preview` + `minimal`）が使われ VLM 修復精度が低下する
  - `settings.yaml.example` は既に `defaults.arxiv_translate.vlm_repair.*` で記述されており変更なし

- **Gemini 3.1 Flash-Lite Preview への移行と用途別 `thinking_level` 対応** (2026-05-02)
  - `LangChainGeminiClient` に `thinking_level: Optional[str]` 引数を追加
    - `_get_chat_model()` の `model_kwargs` を `thinking_config: {thinking_level: ...}` に変更（旧 `thinking_budget: 0` ハードコードを廃止）
    - JSON モード（`chat_json`）でも同じ `thinking_config` を継承
    - 不正値（`minimal` / `low` / `medium` / `high` 以外）は `ValueError`
    - 未指定時は `llm.gemini.default_thinking_level` → `minimal` の順でフォールバック（Gemini 3 Flash/Pro の高コストデフォルト挙動を回避）
  - `get_llm_client()` / `_get_gemini_client()` に `thinking_level` 引数を追加（OpenAI / Ollama 経路では無視）
  - `FullTextTranslator` / `VlmRepairer` / `VlmParseRepairer` に `thinking_level` 引数を追加し、`get_llm_client()` まで伝搬
  - `scripts/arxiv_translate.py:_build_repairer()` / 新規ヘルパー `_build_translator()` で設定値から読み出し
  - `scripts/medium_translate.py` / `scripts/google_alerts_translate.py` でも各機能セクションから読み出し
  - 設定変更:
    - `llm.gemini.default_model`: `gemini-2.5-flash` → `gemini-3.1-flash-lite-preview`
    - `llm.gemini.default_thinking_level`: 新規（`minimal`）
    - `defaults.arxiv_translate.translate_model` / `translate_thinking_level`: 新規（`gemini-3.1-flash-lite-preview` / `minimal`）
    - `arxiv_translate.vlm_repair.model`: `gemini-2.5-flash` → `gemini-3-flash-preview`（精度重視）
    - `arxiv_translate.vlm_repair.thinking_level`: 新規（`medium`）
    - `defaults.medium.translate_model` / `translate_thinking_level`: Gemini 3.1 Flash-Lite + minimal に更新
  - 効果: 翻訳タスクのコスト削減と思考レベルの明示的制御による想定外コスト発生防止
  - 追加修正: Gemini 3 系のレスポンス `content` が parts list 形式（``[{"type": "text", "text": "..."}]``）になる挙動に対応する `_extract_text()` ヘルパーを追加し、`chat()` / `chat_json()` / `generate_from_images()` で利用。Gemini 2.x の str 形式とも後方互換

### Added
- **ArXiv Weekly Digest 2層構成（HF Upvotes + LLMスコア）**: 客観的指標と主観的評価の2層構成でより有用な論文推薦を実現
  - 新規コンポーネント:
    - `minitools/researchers/hf_papers.py` - HFPapersResearcher（HuggingFace Papers APIクライアント、async + Semaphore(5) + exponential backoff）
    - `HFPaperStats` dataclass（arxiv_id, upvotes, num_comments, found_on_hf）
  - ArxivWeeklyProcessor拡張: `hf_researcher`パラメータ追加、`process()`を2層構成に拡張
    - セクション1: HF upvote上位（客観的、再現性あり）
    - セクション2: LLMスコアリング上位（セクション1除外、文脈理解）
    - HF統計取得とトレンド調査を`asyncio.gather`で並列実行
  - SlackPublisher拡張: `format_arxiv_weekly()`に`hf_papers`/`llm_papers`引数追加、2セクション構成出力
  - NotionPublisher拡張: `_build_arxiv_properties()`に`HF Upvotes`（number）プロパティ追加
  - CLI拡張: `--provider gemini`選択肢追加、`hf_top_n`/`llm_top_n`をsettings.yamlから読み込み
  - 新規設定項目: `defaults.arxiv_weekly.hf_top_n`（デフォルト: 5）、`defaults.arxiv_weekly.llm_top_n`（デフォルト: 5）

- **Google Alerts記事全文翻訳機能**: `google-alerts-translate` コマンドを追加。指定URLをJina AI Reader経由で取得し、`FullTextTranslator` で日本語化したうえでGoogle Alerts用Notion DBに反映する
  - 新規コンポーネント:
    - `minitools/scrapers/jina_reader.py` - `JinaReader`（`r.jina.ai` 取得、指数バックオフ、`Title:` / `Published Time:` メタデータ抽出）
    - `scripts/google_alerts_translate.py` - CLIスクリプト（`process_url` / `build_new_page_metadata` / `build_new_page_properties` / `ensure_translated_property`）
  - 既存ページ（`Translated == false`）は本文末尾に divider を挟んで翻訳ブロックを追記し、`Translated` を `true` に更新（A 案）
  - 新規ページは `Translated: True` を含む properties を `create_page` 1 回で書き込み、追加の `update_page_properties` を不要化
  - DBスキーマ事前チェック: `Translated` (checkbox) プロパティ未追加の DB に対しては起動時にエラー終了（手動マイグレーション運用）
  - 設定: `defaults.google_alerts.translate_provider`（`settings.yaml`）

- **ArXiv論文全文翻訳機能**: `arxiv-translate` コマンドを追加。arXiv論文PDFをダウンロードし、marker-pdfでMarkdownに変換、LLMで日本語翻訳してNotionに保存
  - 新規コンポーネント:
    - `minitools/scrapers/arxiv_scraper.py` - `ArxivScraper`（httpx PDFダウンロード + marker-pdf変換 + ArXiv APIメタデータ取得）
    - 補助dataclass: `PaperImage`, `PaperMetadata`, `PaperContent`
    - `scripts/arxiv_translate.py` - CLIスクリプト（`parse` / `translate` / `upload` / `repair` サブコマンド対応）
  - `FullTextTranslator` 拡張: arXiv向けに強化（DO NOT TRANSLATEマーカー対応、テーブルブロックのマージ、外側コードフェンス除去、切り詰め検出）
  - 数式の保持: インライン `$...$` とブロック `$$...$$`（marker-pdfネイティブサポート）
  - 出力構造: 論文ごとに `outputs/arxiv_translate/{safe_id}/` フォルダを作成（`{safe_id}.pdf`, `metadata.json`, `raw.md`, `repaired.md`, `translated.md`, 画像, `page_images/`）
  - 新規依存: `marker-pdf>=1.10.0`（surya OCRモデルの最新APIと安定したMarkdown出力フォーマットを採用したバージョン）、`pymupdf>=1.24.0`（VLM修復用のページレンダリングで利用する `Page.get_pixmap()` の引数互換を確保するバージョン）、`opencv-python-headless>=4.11.0.86`（marker-pdf の依存解決で要求されるバージョン下限。GUI 不要のヘッドレス版を採用しコンテナサイズを抑制）

- **VLMによるmarker-pdfパース欠陥修復機能**: multimodal LLM を使い、壊れた表や孤立した図参照を該当ページの画像から再構築する
  - 新規コンポーネント: `minitools/processors/vlm_parse_repairer.py`
    - `ParseDefect` / `RepairResult` dataclass
    - `ParseErrorDetector` - ヒューリスティック検出（壊れた表・短行ラン・継続マーカー・孤立図、LLMコストなし）
    - `PdfPageRenderer` - PyMuPDFベースのPNGレンダリング、ディスクキャッシュ対応
    - `VlmRepairer` - VLMによる表再構築 + 図の日本語要約生成（Semaphore=2、最大3回リトライ）
    - `MarkdownPatcher` - 検証付きin-place置換（idempotent）
    - `VlmParseRepairer` - オーケストレーター
  - `arxiv-translate parse` サブコマンドに統合、`--no-vlm-repair` でスキップ可能
  - 単独実行: `arxiv-translate repair --url ... [--dry-run]`
  - 設定キー: `arxiv_translate.vlm_repair.{enabled,provider,model,max_total_calls,...}`

- **multimodal LLMサポート**: `BaseLLMClient.generate_from_images()` を追加
  - Gemini / OpenAI クライアントは `HumanMessage` の content list 形式で画像とプロンプトを送信
  - Ollama / 未対応プロバイダはデフォルト実装（warning + 空文字列）

- **Notion画像アップロード機能**: `NotionPublisher.upload_file()` を追加
  - 2段階API呼び出し: `POST /v1/file_uploads` で `upload_url` 取得 → multipart/form-data で画像送信（3回リトライ）
  - 5MB超の画像はwarningログを出力してNoneを返す
  - mime_typeはNone時に `mimetypes.guess_type()` で推定
  - `NotionBlockBuilder.build_blocks()` 拡張: `image_uploads` 引数（ローカルファイル名→file_upload_idマッピング）でローカル画像を `file_upload` 型ブロックとして埋め込み可能

- **NotionBlockBuilder の数式・テーブル対応**: ArXiv論文のMarkdown表現に対応
  - ブロック数式 (`$$...$$`) → Notion `equation` ブロック
  - インライン数式 (`$...$`) → rich_text内の `equation`、エスケープ `\$` は通常文字
  - Markdownテーブル → Notion `table` ブロック

- **X フォロー中アカウント一覧取得ユーティリティ**: `x-followings` コマンドを追加
  - `scripts/x_followings.py` - フォロー中アカウント一覧を取得
  - `--user`（必須）、`--limit`、`--format`（list/yaml）オプション
  - `settings.yaml`の`watch_accounts`設定用にYAML出力可能

- **X (Twitter) AI トレンドダイジェスト v2**: キーワード検索とユーザータイムライン監視を追加し、3ソース構成に拡張
  - 新規データクラス: `KeywordSearchResult`, `UserTimelineResult`, `CollectResult`, `KeywordSummary`, `TimelineSummary`, `ProcessResult`
  - XTrendCollector拡張: `search_by_keyword()`, `get_user_timeline()`, `collect_keywords()`, `collect_timelines()`, `collect_all()`
  - XTrendProcessor拡張: `filter_ai_tweets()`, `summarize_keyword_results()`, `summarize_timeline_results()`, `process_all()`
  - SlackPublisher拡張: `format_x_trend_digest()` を `ProcessResult` 対応（3セクション構成: トレンド/キーワード/タイムライン）
  - CLIオプション追加: `--no-trends`, `--no-keywords`, `--no-timeline`
  - コスト最適化: トレンド名でLLMフィルタリング後にのみツイート取得（`fetch_tweets=False`）
  - 設定項目追加: `x_trend.keywords`, `x_trend.watch_accounts`, `x_trend.tweets_per_keyword`, `x_trend.tweets_per_account`

- **X (Twitter) AI トレンドダイジェスト v1**: TwitterAPI.ioからAI関連トレンドを収集・要約してSlackに送信する機能
  - 新規コンポーネント:
    - `minitools/collectors/x_trend.py` - XTrendCollector（トレンド取得、ツイート検索）
    - `minitools/processors/x_trend.py` - XTrendProcessor（AI関連フィルタリング、要約生成）
    - `scripts/x_trend.py` - CLIスクリプト
  - SlackPublisher拡張: `format_x_trend_digest()`, 地域別2セクション構成
  - 新規CLIコマンド: `x-trend`
  - 新規環境変数: `TWITTER_API_IO_KEY`, `SLACK_X_TIMELINE_SUMMARY_WEBHOOK_URL`
  - 設定項目: `defaults.x_trend.max_trends`, `defaults.x_trend.tweets_per_trend`, `defaults.x_trend.provider`

- **Medium Claps数の出力**: NotionデータベースとSlack通知にClaps（拍手数）を追加
  - Notion: `Claps` (Number型) プロパティとして保存、フィルタ・ソート可能
  - Slack: 著者名の下に👏アイコン付きでカンマ区切り表示（0の場合は非表示）
  - Article dataclass: `claps: int = 0` フィールド追加
- **全文翻訳済みチェックボックス**: 全文翻訳成功時にNotionページの`Translated` (Checkbox型) を自動チェック
  - `scripts/medium.py --translate` 経由の翻訳に対応
  - `scripts/medium_translate.py` 経由の翻訳に対応
  - NotionPublisher拡張: `update_page_properties()` メソッド追加
- **Mediumコマンドオプション拡張**: `--translate`（claps閾値以上の記事を全文翻訳）、`--cdp`（CDP接続でCloudflare回避）オプション追加
  - 設定項目: `defaults.medium.translate_clap_threshold`, `defaults.medium.translate_provider`, `defaults.medium.translate_model`

- **Medium全文翻訳機能**: Medium記事の全文をPlaywrightで取得し、LLMで日本語翻訳してNotionに追記する機能
  - 新規コンポーネント:
    - `minitools/scrapers/medium_scraper.py` - MediumScraper（CDP/スタンドアロン、Cloudflare回避）
    - `minitools/scrapers/markdown_converter.py` - MarkdownConverter（HTML→構造化Markdown変換）
    - `minitools/processors/full_text_translator.py` - FullTextTranslator（チャンク分割翻訳・構造維持）
    - `minitools/publishers/notion_block_builder.py` - NotionBlockBuilder（Markdown→Notionブロック変換）
    - `minitools/llm/langchain_gemini.py` - LangChainGeminiClient（Gemini APIプロバイダー）
    - `scripts/medium_translate.py` - CLIスクリプト
  - NotionPublisher拡張: `find_page_by_url()`, `append_blocks()` メソッド（100ブロックバッチ対応）
  - LLMファクトリ拡張: `get_llm_client(provider="gemini")` サポート
  - `medium` コマンドに `--translate`, `--cdp` オプション追加
  - 新規CLIコマンド: `medium-translate`
  - 新規環境変数: `GEMINI_API_KEY`
  - 設定項目: `defaults.medium.translate_clap_threshold`, `defaults.medium.translate_provider`, `defaults.medium.translate_model`

- **バッチスコアリング機能**: `WeeklyDigestProcessor` と `ArxivWeeklyProcessor` にバッチ処理を導入し、スコアリング処理を高速化
  - 20件を1回のLLM呼び出しでまとめてスコアリング（約8倍の速度向上）
  - デフォルトプロバイダーをOpenAIに変更（`defaults.weekly_digest.provider`, `defaults.arxiv_weekly.provider`）
  - バッチ処理失敗時は自動的に個別処理にフォールバック
  - 新規設定項目: `defaults.weekly_digest.batch_size`, `defaults.arxiv_weekly.batch_size`
  - 500件以上の記事を40分以上 → 数分で処理可能に

- **ArXiv週次ダイジェスト機能**: Notion DBから過去1週間分のArXiv論文を取得し、AIが重要度を判定して上位論文を選出。週のトレンド総括と各論文のハイライトをSlackに出力する
  - 新規コンポーネント:
    - `minitools/researchers/trend.py` - TrendResearcher（Tavily APIでトレンド調査）
    - `minitools/processors/arxiv_weekly.py` - ArxivWeeklyProcessor（重要度スコアリング・ハイライト生成）
    - `scripts/arxiv_weekly.py` - CLIスクリプト
  - NotionReader拡張: `get_arxiv_papers_by_date_range()` メソッド
  - SlackPublisher拡張: `format_arxiv_weekly()`, `send_arxiv_weekly()` メソッド
  - 新規CLIコマンド: `arxiv-weekly`
  - 新規環境変数: `TAVILY_API_KEY`, `NOTION_ARXIV_DATABASE_ID`, `SLACK_ARXIV_WEEKLY_WEBHOOK_URL`
  - 設定項目: `defaults.arxiv_weekly.days_back`, `defaults.arxiv_weekly.top_papers`

- **ドキュメント自動生成**: `docs/core/` に以下のドキュメントを追加
  - `architecture.md` - システムアーキテクチャ設計書
  - `repo-structure.md` - リポジトリ構造定義書
  - `api-reference.md` - APIリファレンス
  - `diagrams.md` - Mermaid図（シーケンス図、クラス図等）
  - `dev-guidelines.md` - 開発ガイドライン
  - `CHANGELOG.md` - 変更履歴

- **Google Alerts週次AIダイジェスト機能**: Google AlertsのNotion DBから過去1週間分の記事を取得し、AIが重要度を判定して上位20件を選出。週のトレンド総括と各記事の要約をSlackに出力する
  - 新規コンポーネント:
    - `minitools/llm/` - LLM抽象化レイヤー（Ollama/OpenAI切り替え、LangChain統合）
    - `minitools/llm/embeddings.py` - Embedding抽象化レイヤー（類似記事検出用）
    - `minitools/llm/langchain_ollama.py` - LangChain Ollamaクライアント
    - `minitools/llm/langchain_openai.py` - LangChain OpenAIクライアント
    - `minitools/readers/notion.py` - NotionReader（日付フィルタでデータ取得）
    - `minitools/processors/weekly_digest.py` - 週次ダイジェスト処理
    - `minitools/processors/duplicate_detector.py` - 類似記事検出・重複除去
    - `scripts/google_alert_weekly_digest.py` - CLIスクリプト
  - 新規CLIコマンド: `google-alert-weekly-digest`
  - 新規設定項目: `llm.provider`, `llm.ollama.default_model`, `llm.openai.default_model`
  - 新規環境変数: `NOTION_GOOGLE_ALERTS_DATABASE_ID`, `SLACK_WEEKLY_DIGEST_WEBHOOK_URL`

### Changed
- **X トレンドダイジェスト Slack送信の省略撤廃**: 3000文字制限・省略ロジックを撤廃し、全内容を送信するように変更
  - `format_x_trend_digest_sections()` 追加: セクションごとの `list[str]` を返す新メソッド
  - `format_x_trend_digest()` を後方互換ラッパーに変更（内部で sections を結合）
  - `send_messages()` 追加: 複数メッセージを順番に送信（0.5秒間隔）
  - `scripts/x_trend.py`: セクション分割送信に対応、dry-run時はセクション番号付き表示
- **週次ダイジェストスクリプトのリネーム**: `scripts/weekly_digest.py` → `scripts/google_alert_weekly_digest.py`
  - CLIコマンド: `weekly-digest` → `google-alert-weekly-digest`
  - 目的: Google Alerts専用であることを明確化
- **`find_page_by_url()` の返り値変更**: `Optional[str]` → `Optional[PageInfo]`
  - `PageInfo` NamedTuple（`page_id: str`, `is_translated: bool`）を返すように変更
  - 既存のNotionクエリ結果から `Translated` チェックボックスの状態を取得（追加APIコール不要）
- **全文翻訳の重複防止**: 翻訳済み記事のスキップ機能を追加
  - `scripts/medium.py --translate`: Notionページ検索をスクレイピング前に移動し、`Translated`チェック済みの場合は翻訳処理全体をスキップ
  - `scripts/medium_translate.py`: 同様に`Translated`チェック済みの場合はNotionへの追記をスキップ
- ruff による静的解析チェックを追加 (bf4f777)

### Fixed
- **XTrendCollector APIレスポンスパーシング修正**: TwitterAPI.ioのレスポンス構造がネスト形式（`{"status": "success", "data": {"tweets": [...]}}`）であることに対応
  - `_parse_tweets()`: `data.data.tweets` のネスト構造に対応（従来は `data.tweets` のフラット構造のみ対応）
  - `get_trends()`: 同様にネスト構造対応を追加
  - テストのサンプルレスポンスを実際のAPI構造に合わせて更新

### Removed
- **レガシードキュメントの削除**: 以下のドキュメントを削除し、`docs/core/` に統合
  - `docs/arxiv_async_usage.md` → `docs/core/architecture.md` に統合
  - `docs/docker-gmail-auth.md` → README.md に統合
  - `docs/gmail_alerts_parallel_processing.md` → `docs/core/architecture.md` に統合
  - `docs/medium_daily_digest_async_usage.md` → `docs/core/architecture.md` に統合
  - `docs/medium_daily_digest_error_fixes.md` → `docs/core/dev-guidelines.md` に統合
  - `GPU_SETUP.md` → 削除（未使用）

## [0.1.0] - 2024

### Added

#### 機能追加
- **Makefileの導入** (035e8aa)
  - Docker実行を簡略化する `make arxiv`, `make medium` 等のコマンド
  - `make build`, `make shell`, `make help` コマンド

- **Docker対応** (374a737, 6c833a7)
  - マルチステージビルドによるDockerイメージ
  - docker-compose.yml によるサービス定義
  - macOS向け、Windows向けの個別Compose設定
  - ollama-setup サービスによるモデル自動ダウンロード

- **並列処理機能** (6b429a8)
  - asyncio.Semaphore による並列数制限
  - バッチ処理によるパフォーマンス改善
  - 3-5倍の処理速度向上

- **ログ機能** (1bcf19f)
  - ColoredFormatter によるカラー出力
  - ファイルとコンソールへの二重出力
  - ログレベルに応じた色分け

- **タグ付け機能** (2911dc9)
  - Google Alertsのタグ自動付与
  - settings.yaml でのタグマッピング設定

- **Medium Daily Digest機能** (2027df0)
  - Gmail APIからのメール取得
  - メールHTML解析による記事抽出
  - Jina AI Readerによるコンテンツ取得

- **Slack通知機能** (3147620)
  - Webhook URLによる通知送信
  - 記事リストのフォーマット機能

- **YouTube要約機能** (01cfe20)
  - yt-dlp による音声ダウンロード
  - MLX Whisper による文字起こし
  - 要約と日本語翻訳

- **ArXiv論文検索機能** (aa51c1f)
  - ArXiv API連携
  - feedparser による結果解析
  - Notion保存機能

- **Notion保存機能** (c5c9634)
  - Notion API連携
  - 重複検出機能
  - バッチ保存機能

### Changed

#### 改善・変更
- **Medium記事取得ロジックの更新** (0091741, e692971)
  - bot検出回避のためのUser-Agentローテーション
  - 並列数の削減（5接続に制限）
  - ブラウザを模倣したヘッダー追加
  - リクエスト間のランダム遅延

- **コマンド名の簡略化** (a58e225)
  - `minitools-arxiv` → `arxiv`
  - `minitools-medium` → `medium`
  - `minitools-google-alerts` → `google-alerts`
  - `minitools-youtube` → `youtube`

- **パッケージマネージャー変更** (002e885)
  - Poetry から uv への移行
  - 高速な依存関係解決

- **モデル更新** (e5d293a, 1489ff1)
  - デフォルトモデルを `gemma3:27b` に変更
  - YouTube用に軽量モデル `gemma2` を設定

- **プロジェクト構造のリファクタリング** (5ffb4b0, f7beede, da0ccda)
  - 共通ロギング関数の外部化
  - ソースコードを `minitools/` パッケージに整理
  - Collectors, Processors, Publishers の分離

#### バグ修正
- 各種バグ修正 (820c578, b91aefc, b173cb0, 68d4d58, 1afb4fb, 0383d83, b4c8d82, 6ea8347)
  - Gmail API認証フローの修正
  - URL正規化の改善
  - エラーハンドリングの強化
  - 重複検出ロジックの修正

### Removed
- **CSV保存機能の削除** (3147620)
  - Notion保存に一本化

- **レガシーコードの削除** (0091741)
  - 古いMedium取得ロジック

## マイグレーションノート

### Poetry から uv への移行

```bash
# 既存の Poetry 環境を削除
rm -rf .venv poetry.lock

# uv をインストール
curl -LsSf https://astral.sh/uv/install.sh | sh

# 依存関係をインストール
uv sync
```

### コマンド名の変更

| 旧コマンド | 新コマンド |
|-----------|-----------|
| `minitools-arxiv` | `arxiv` |
| `minitools-medium` | `medium` |
| `minitools-google-alerts` | `google-alerts` |
| `minitools-youtube` | `youtube` |

### 環境変数の統一

新しい環境変数名を推奨。旧名は引き続きサポート（フォールバック）。

| 旧環境変数 | 新環境変数 |
|-----------|-----------|
| `NOTION_DB_ID` | `NOTION_ARXIV_DATABASE_ID` |
| `NOTION_DB_ID_DAILY_DIGEST` | `NOTION_MEDIUM_DATABASE_ID` |
| `NOTION_DB_ID_GOOGLE_ALERTS` | `NOTION_GOOGLE_ALERTS_DATABASE_ID` |
| `SLACK_WEBHOOK_URL` | `SLACK_ARXIV_WEBHOOK_URL` |
| `SLACK_WEBHOOK_URL_MEDIUM_DAILY_DIGEST` | `SLACK_MEDIUM_WEBHOOK_URL` |
| `SLACK_WEBHOOK_URL_GOOGLE_ALERTS` | `SLACK_GOOGLE_ALERTS_WEBHOOK_URL` |

### Docker への移行

```bash
# .env.docker.example をコピー
cp .env.docker.example .env

# 環境変数を設定
vim .env

# Docker イメージをビルド
make build

# 実行
make arxiv
make medium
```

## コミット履歴

| コミット | 説明 |
|---------|------|
| bf4f777 | ruff checks |
| 0091741 | updated medium fetch logic and deleted legacy codes |
| e692971 | updated mcollectors/medium.py |
| a58e225 | simplified from minitools-tool to tool |
| 6c833a7 | bugfixes for docker use |
| 035e8aa | introduced makefile |
| 820c578 | bugfixes |
| 374a737 | introduced docker-feature |
| b91aefc | bugfixes |
| b173cb0 | bugfixes |
| 68d4d58 | bugfixes |
| 1afb4fb | bugfixes |
| e8da6f7 | miscellaneous updates |
| 5c8aabf | miscellaneous updates |
| f7beede | executed refactoring |
| 5ffb4b0 | externized common loggin function |
| f1cf4bc | add error handling |
| 8781eee | modified not to save the same papers |
| 7ae39c1 | miscellaneous updates |
| 2911dc9 | include addition of tags and article fetching improvements |
| 1bcf19f | added logging feature |
| 6b429a8 | added parallel processing feature |
| 0383d83 | bugfixes |
| 2027df0 | added medium_daily_digest_to_notion.py |
| 3147620 | added slack notification feature and deleted save to csv feature |
| 002e885 | changed package manager poetry to uv |
| e5d293a | updated model and miscellaneous stuff |
| 1489ff1 | changed default model to gemma3:27b |
| b4c8d82 | Bug fixes |
| d1bdf35 | miscellaneous fixes |
| cbd9f61 | miscellaneous fixes |
| da0ccda | Transferred program files under src folder |
| 01cfe20 | Add get_youtube_sumary_in_japanese.py |
| 6ea8347 | bug fixes |
| 1a1c699 | Modify miscellaneouses |
| cf94841 | Add README.md and modify miscellaneouses |
| 2251c64 | miscellaneous stuff |
| 64f9f19 | modified logging information |
| c5c9634 | Modified to save results to Notion |
| aa51c1f | add get_arxiv_summary_in_japanese.py |
| f13b29b | Initial commit |
