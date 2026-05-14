# リポジトリ構造定義書

このドキュメントは、minitoolsプロジェクトのディレクトリ構造とモジュールの役割を説明します。

## ディレクトリ構造

```
minitools/
├── minitools/                      # コアパッケージ
│   ├── __init__.py                 # パッケージエクスポート
│   ├── collectors/                 # データ収集レイヤー
│   │   ├── __init__.py
│   │   ├── arxiv.py               # ArXiv論文検索
│   │   ├── medium.py              # Medium Daily Digest収集
│   │   ├── google_alerts.py       # Google Alerts収集
│   │   ├── youtube.py             # YouTube文字起こし
│   │   └── x_trend.py             # X トレンド収集（TwitterAPI.io）
│   ├── llm/                        # LLM抽象化レイヤー
│   │   ├── __init__.py            # get_llm_client()ファクトリ
│   │   ├── base.py                # BaseLLMClient抽象基底クラス
│   │   ├── embeddings.py          # Embedding抽象化レイヤー
│   │   ├── ollama_client.py       # Ollama APIクライアント（ネイティブ）
│   │   ├── openai_client.py       # OpenAI APIクライアント（ネイティブ）
│   │   ├── langchain_ollama.py    # LangChain Ollamaクライアント
│   │   ├── langchain_openai.py    # LangChain OpenAIクライアント
│   │   └── langchain_gemini.py    # LangChain Geminiクライアント
│   ├── readers/                    # 読み取りレイヤー
│   │   ├── __init__.py
│   │   └── notion.py              # Notionデータベース読み取り
│   ├── researchers/                # リサーチレイヤー
│   │   ├── __init__.py
│   │   ├── trend.py               # Tavily APIでトレンド調査
│   │   └── hf_papers.py           # Hugging Face Daily Papersから論文取得
│   ├── scrapers/                   # スクレイピングレイヤー
│   │   ├── __init__.py
│   │   ├── medium_scraper.py      # Playwright Medium記事取得（CDP/スタンドアロン）
│   │   ├── arxiv_scraper.py       # ArXiv PDFダウンロード + marker-pdf変換
│   │   ├── jina_reader.py         # Jina AI Reader経由のMarkdown取得（Google Alerts用）
│   │   └── markdown_converter.py  # HTML→Markdown変換
│   ├── processors/                 # コンテンツ処理レイヤー
│   │   ├── __init__.py
│   │   ├── translator.py          # Ollama翻訳
│   │   ├── summarizer.py          # Ollama要約
│   │   ├── full_text_translator.py # 全文翻訳（チャンク分割・構造維持）
│   │   ├── vlm_parse_repairer.py  # marker-pdfパース欠陥のVLM修復
│   │   ├── weekly_digest.py       # 週次ダイジェスト生成
│   │   ├── arxiv_weekly.py        # ArXiv週次ダイジェスト生成
│   │   ├── x_trend.py             # X トレンド処理（LLMフィルタ・要約）
│   │   └── duplicate_detector.py  # 類似記事検出
│   ├── publishers/                 # 出力レイヤー
│   │   ├── __init__.py
│   │   ├── notion.py              # Notionデータベース連携
│   │   ├── notion_block_builder.py # Markdown→Notionブロック変換
│   │   └── slack.py               # Slack通知
│   └── utils/                      # ユーティリティ
│       ├── __init__.py
│       ├── config.py              # 設定管理（シングルトン）
│       └── logger.py              # カラーログ出力
│
├── scripts/                        # CLIエントリーポイント
│   ├── arxiv.py                   # arxiv コマンド
│   ├── medium.py                  # medium コマンド
│   ├── medium_translate.py        # medium-translate コマンド
│   ├── arxiv_translate.py         # arxiv-translate コマンド（PDF→Markdown→翻訳→Notion）
│   ├── google_alerts.py           # google-alerts コマンド
│   ├── google_alerts_translate.py # google-alerts-translate コマンド（Jina→翻訳→Notion）
│   ├── youtube.py                 # youtube コマンド
│   ├── google_alert_weekly_digest.py  # google-alert-weekly-digest コマンド
│   ├── google_alert_daily_digest.py   # google-alert-daily-digest コマンド
│   ├── arxiv_weekly.py            # arxiv-weekly コマンド
│   ├── x_trend.py                 # x-trend コマンド
│   ├── x_followings.py            # x-followings コマンド
│   └── launchd/                   # macOS launchd plist（定期実行設定）
│       └── com.tak.minitools.google-alert-daily-digest.plist
│
├── docs/                           # ドキュメント
│   ├── core/                      # コアドキュメント
│   └── ideas/                     # アイデア・ブレインストーム
│
├── outputs/                        # 実行時出力
│   ├── logs/                      # ログファイル
│   └── temp/                      # 一時ファイル
│
├── tests/                         # テスト
│   ├── __init__.py
│   ├── conftest.py               # テスト共通フィクスチャ
│   ├── test_arxiv_weekly.py      # ArXiv週次ダイジェストテスト
│   ├── test_duplicate_detector.py # 重複検出テスト
│   ├── test_arxiv_scraper.py     # ArXiv PDFスクレイパーテスト
│   ├── test_full_text_translator.py # 全文翻訳テスト
│   ├── test_google_alerts_translate.py # Google Alerts全文翻訳テスト
│   ├── test_hf_papers.py         # Hugging Face Papersリサーチテスト
│   ├── test_langchain_gemini.py  # LangChain Gemini クライアントテスト
│   ├── test_markdown_converter.py # Markdown変換テスト
│   ├── test_medium_collector.py  # Medium収集テスト
│   ├── test_medium_scraper.py    # Mediumスクレイパーテスト
│   ├── test_medium_translate.py  # Medium全文翻訳テスト
│   ├── test_notion_arxiv.py      # Notion ArXivテスト
│   ├── test_notion_block_builder.py # Notionブロックビルダーテスト
│   ├── test_notion_publisher.py  # Notionパブリッシャーテスト
│   ├── test_notion_upload_file.py # Notion File Upload APIテスト
│   ├── test_vlm_parse_repairer.py # VLMパース修復テスト
│   ├── test_slack_arxiv_format.py # Slack ArXivフォーマットテスト
│   ├── test_slack_publisher.py   # Slackパブリッシャーテスト
│   ├── test_trend_researcher.py  # トレンドリサーチテスト
│   ├── test_slack_x_trend_format.py # X トレンドSlackフォーマットテスト
│   ├── test_x_trend_collector.py # X トレンド収集テスト
│   ├── test_x_trend_processor.py # X トレンド処理テスト
│   └── test_weekly_digest.py     # 週次/日次ダイジェストテスト
│
├── pyproject.toml                 # プロジェクト設定・依存関係
├── settings.yaml.example          # 設定ファイルテンプレート
├── .env.docker.example            # 環境変数テンプレート
├── Dockerfile                     # Dockerイメージ定義
├── docker-compose.yml             # Docker Compose設定
├── docker-compose.mac.yml         # macOS向けDocker設定
├── docker-compose.windows.yml     # Windows向けDocker設定
├── docker-entrypoint.sh           # Dockerエントリーポイント
├── Makefile                       # ビルド自動化
├── README.md                      # プロジェクト説明
├── CLAUDE.md                      # 開発ガイダンス
├── .python-version                # Pythonバージョン固定
├── uv.lock                        # 依存関係ロック
└── .gitignore                     # Git除外設定
```

## 各ディレクトリ/モジュールの役割

### minitools/ (コアパッケージ)

プロジェクトのメインライブラリ。4つのサブパッケージで構成されています。

#### collectors/ (データ収集)

外部ソースからコンテンツを収集するモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `arxiv.py` | ArXiv APIから論文を検索・取得 | ArXiv API, feedparser |
| `medium.py` | Gmail経由でMedium Daily Digestを取得 | Gmail API, Jina AI Reader |
| `google_alerts.py` | Gmail経由でGoogle Alertsを取得 | Gmail API |
| `youtube.py` | YouTube動画の音声ダウンロード・文字起こし | yt-dlp, MLX Whisper |
| `x_trend.py` | TwitterAPI.ioからトレンド・キーワード検索・ユーザータイムラインを収集 | TwitterAPI.io |

#### llm/ (LLM抽象化レイヤー)

Ollama/OpenAIを統一的に扱うための抽象化レイヤー。

| モジュール | 役割 | 備考 |
|-----------|------|------|
| `base.py` | BaseLLMClient抽象基底クラス | chat(), generate()の共通インターフェース |
| `embeddings.py` | Embedding抽象化レイヤー | BaseEmbeddingClient, get_embedding_client() |
| `ollama_client.py` | Ollamaクライアント実装（ネイティブ） | 同期APIをrun_in_executorで非同期化 |
| `openai_client.py` | OpenAIクライアント実装（ネイティブ） | AsyncOpenAIを使用 |
| `langchain_ollama.py` | LangChain Ollamaクライアント | LangChain経由でOllamaを使用（推奨） |
| `langchain_openai.py` | LangChain OpenAIクライアント | LangChain経由でOpenAIを使用（推奨） |
| `langchain_gemini.py` | LangChain Geminiクライアント | LangChain経由でGemini APIを使用 |
| `__init__.py` | get_llm_client()ファクトリ | LangChain優先、ネイティブにフォールバック |

#### readers/ (データ読み取り)

外部データベースからデータを読み取るモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `notion.py` | Notionデータベースからの記事取得 | Notion API |

#### researchers/ (リサーチ)

外部APIを使用してリサーチを行うモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `trend.py` | AI/機械学習分野のトレンド調査 | Tavily API |
| `hf_papers.py` | Hugging Face Daily Papersから注目論文を取得 | Hugging Face Papers |

#### scrapers/ (スクレイピング)

Playwrightを使用して外部サイトからコンテンツを取得し、構造化データに変換するモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `medium_scraper.py` | Playwright経由でMedium記事の全文HTMLを取得 | Playwright (CDP/スタンドアロン) |
| `markdown_converter.py` | Medium記事HTMLを構造化Markdownに変換 | BeautifulSoup4 |
| `arxiv_scraper.py` | ArXiv PDFをダウンロードしmarker-pdfでMarkdownに変換 | httpx, marker-pdf, feedparser |
| `jina_reader.py` | `r.jina.ai/{url}` 経由で記事Markdownを取得（Google Alerts用） | aiohttp, Jina AI Reader |

#### processors/ (コンテンツ処理)

LLMを使用してコンテンツを処理するモジュール群。

| モジュール | 役割 | 使用モデル |
|-----------|------|----------|
| `translator.py` | テキストの日本語翻訳 | gemma3:27b (Ollama) |
| `summarizer.py` | テキストの要約・キーポイント抽出 | gemma3:27b (Ollama) |
| `full_text_translator.py` | 記事全文の日本語翻訳（チャンク分割・構造維持） | LLM抽象化レイヤー経由 |
| `vlm_parse_repairer.py` | marker-pdfのパース欠陥（壊れた表・孤立図）をVLMで修復 | multimodal LLM (Gemini/OpenAI) |
| `weekly_digest.py` | 週次ダイジェスト生成 | LLM抽象化レイヤー経由 |
| `arxiv_weekly.py` | ArXiv週次ダイジェスト生成 | LLM抽象化レイヤー経由 |
| `x_trend.py` | X トレンド処理・AI関連フィルタ・Tweet要約 | LLM抽象化レイヤー経由 |
| `duplicate_detector.py` | 類似記事検出・重複除去 | Embedding抽象化レイヤー経由 |

#### publishers/ (出力)

処理結果を外部サービスに出力するモジュール群。

| モジュール | 役割 | 外部サービス |
|-----------|------|------------|
| `notion.py` | Notionデータベースへの保存・ブロック追記 | Notion API |
| `notion_block_builder.py` | MarkdownからNotionブロック形式への変換 | - |
| `slack.py` | Slackチャンネルへの通知 | Slack Webhook |

#### utils/ (ユーティリティ)

共通機能を提供するモジュール群。

| モジュール | 役割 | パターン |
|-----------|------|---------|
| `config.py` | 設定ファイル管理 | シングルトン |
| `logger.py` | カラー対応ログ出力 | ColoredFormatter |

### scripts/ (CLIエントリーポイント)

各ツールのコマンドラインインターフェース。`pyproject.toml`で定義されたエントリーポイント。

| スクリプト | コマンド | 用途 |
|-----------|---------|-----|
| `arxiv.py` | `arxiv` | ArXiv論文の検索・翻訳・保存 |
| `medium.py` | `medium` | Medium記事の収集・翻訳・保存 |
| `medium_translate.py` | `medium-translate` | Medium記事の全文翻訳・Notion追記 |
| `arxiv_translate.py` | `arxiv-translate` | ArXiv論文PDFの全文翻訳・Notion保存（parse / translate / upload / repair サブコマンド） |
| `google_alerts.py` | `google-alerts` | Google Alertsの収集・翻訳・保存 |
| `google_alerts_translate.py` | `google-alerts-translate` | Google Alerts記事の全文翻訳・Notion追記 |
| `youtube.py` | `youtube` | YouTube動画の文字起こし・要約 |
| `google_alert_weekly_digest.py` | `google-alert-weekly-digest` | Google Alerts週次ダイジェストの生成・Slack通知 |
| `google_alert_daily_digest.py` | `google-alert-daily-digest` | Google Alerts日次ダイジェスト（過去24時間 Top10 + 「今日のまとめ」）の生成・Slack通知 |
| `arxiv_weekly.py` | `arxiv-weekly` | ArXiv週次ダイジェストの生成・Slack通知 |
| `x_trend.py` | `x-trend` | X トレンドの収集・AI関連フィルタ・Slack通知 |
| `x_followings.py` | `x-followings` | X フォロー中アカウント一覧取得・YAML出力 |

## 新規コンポーネント追加手順

### 新しいCollectorの追加

1. `minitools/collectors/` に新しいモジュールを作成
2. クラスを実装（async context manager対応推奨）
3. `minitools/collectors/__init__.py` にエクスポート追加
4. 対応するCLIスクリプトを `scripts/` に作成
5. `pyproject.toml` にエントリーポイント追加

```python
# minitools/collectors/new_source.py
class NewSourceCollector:
    """新しいソースのCollector"""

    def __init__(self, config_param: str = None):
        self.http_session = None

    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        self.http_session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーのクリーンアップ"""
        if self.http_session:
            await self.http_session.close()

    async def collect(self) -> List[Dict]:
        """データを収集"""
        pass
```

### 新しいProcessorの追加

1. `minitools/processors/` に新しいモジュールを作成
2. Ollamaクライアントを使用するクラスを実装
3. `minitools/processors/__init__.py` にエクスポート追加

```python
# minitools/processors/new_processor.py
import ollama

class NewProcessor:
    """新しい処理クラス"""

    def __init__(self, model: Optional[str] = None):
        self.model = model or "gemma3:27b"
        self.client = ollama.Client()

    async def process(self, text: str) -> str:
        """テキストを処理"""
        prompt = f"Process this text: {text}"
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content']
```

### 新しいPublisherの追加

1. `minitools/publishers/` に新しいモジュールを作成
2. 非同期メソッドを持つクラスを実装
3. `minitools/publishers/__init__.py` にエクスポート追加

```python
# minitools/publishers/new_publisher.py
class NewPublisher:
    """新しい出力先のパブリッシャー"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('NEW_SERVICE_API_KEY')
        self.http_session = None

    async def __aenter__(self):
        self.http_session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_session:
            await self.http_session.close()

    async def publish(self, data: Dict[str, Any]) -> bool:
        """データを出力"""
        pass
```

## 設定追加ガイド

### .env (セキュリティ関連)

新しい外部サービスのAPIキーやWebhook URLを追加する場合:

```bash
# .env

# 既存の設定
NOTION_API_KEY=your_key
SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# 新規追加
NEW_SERVICE_API_KEY=your_new_key
NEW_SERVICE_WEBHOOK_URL=https://example.com/webhook
```

### settings.yaml (アプリケーション設定)

新しいモデルやパラメータを追加する場合:

```yaml
# settings.yaml

# 既存の設定
models:
  translation: "gemma3:27b"
  summarization: "gemma3:27b"
  # 新規追加
  new_processor: "new-model:latest"

# 新しいツールのデフォルト設定
defaults:
  new_source:
    param1: "default_value"
    param2: 100
```

### config.py でのアクセス

```python
from minitools.utils.config import get_config, Config

config = get_config()

# 設定値の取得
model = config.get('models.new_processor', 'fallback-model')
param = config.get('defaults.new_source.param1', 'default')

# APIキーの取得
api_key = Config.get_api_key('new_service')  # NEW_SERVICE_API_KEY を検索
```

### pyproject.toml エントリーポイント追加

```toml
[project.scripts]
arxiv = "scripts.arxiv:main"
medium = "scripts.medium:main"
medium-translate = "scripts.medium_translate:main"
google-alerts = "scripts.google_alerts:main"
google-alerts-translate = "scripts.google_alerts_translate:main"
youtube = "scripts.youtube:main"
google-alert-weekly-digest = "scripts.google_alert_weekly_digest:main"
google-alert-daily-digest = "scripts.google_alert_daily_digest:main"
arxiv-weekly = "scripts.arxiv_weekly:main"
arxiv-translate = "scripts.arxiv_translate:main"
x-trend = "scripts.x_trend:main"
x-followings = "scripts.x_followings:main"
# 新規追加
new-source = "scripts.new_source:main"
```

## ファイル命名規則

| 種類 | 規則 | 例 |
|-----|------|---|
| モジュール | スネークケース | `google_alerts.py` |
| クラス | パスカルケース | `GoogleAlertsCollector` |
| 関数/メソッド | スネークケース | `get_alerts_emails` |
| 定数 | 大文字スネークケース | `SCOPES`, `USER_AGENTS` |
| 設定キー | ドット区切り小文字 | `models.translation` |
| 環境変数 | 大文字スネークケース | `NOTION_API_KEY` |
