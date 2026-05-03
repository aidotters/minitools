# アーキテクチャ設計書

このドキュメントは、minitoolsプロジェクトのシステムアーキテクチャを説明します。

## システム概要

minitoolsは、複数のソースからコンテンツを収集し、Ollama LLMで処理して、NotionやSlackに出力する自動化フレームワークです。

```mermaid
flowchart TB
    subgraph Sources["データソース"]
        ArXiv["ArXiv API"]
        Gmail["Gmail API"]
        YouTube["YouTube"]
        NotionDB["Notion Database"]
        TwitterAPI["TwitterAPI.io"]
    end

    subgraph Collectors["収集レイヤー"]
        AC["ArxivCollector"]
        MC["MediumCollector"]
        GAC["GoogleAlertsCollector"]
        YC["YouTubeCollector"]
        XTC["XTrendCollector"]
    end

    subgraph Readers["読み取りレイヤー"]
        NR["NotionReader"]
    end

    subgraph Researchers["リサーチレイヤー"]
        TrendR["TrendResearcher"]
        HFR["HFPapersResearcher"]
    end

    subgraph Scrapers["スクレイピングレイヤー"]
        MS["MediumScraper"]
        MDC["MarkdownConverter"]
    end

    subgraph LLMLayer["LLM抽象化レイヤー"]
        LLMFactory["get_llm_client()"]
        OC["OllamaClient"]
        OpenAIC["OpenAIClient"]
        GeminiC["GeminiClient"]
    end

    subgraph Processors["処理レイヤー"]
        TR["Translator"]
        SU["Summarizer"]
        FTT["FullTextTranslator"]
        VPR["VlmParseRepairer"]
        WDP["WeeklyDigestProcessor"]
        AWP["ArxivWeeklyProcessor"]
        XTP["XTrendProcessor"]
        DD["DuplicateDetector"]
    end

    subgraph EmbeddingLayer["Embedding抽象化レイヤー"]
        EmbFactory["get_embedding_client()"]
        OllamaEmb["OllamaEmbeddingClient"]
        OpenAIEmb["OpenAIEmbeddingClient"]
    end

    subgraph Publishers["出力レイヤー"]
        NP["NotionPublisher"]
        NBB["NotionBlockBuilder"]
        SP["SlackPublisher"]
    end

    subgraph Outputs["出力先"]
        Notion["Notion Database"]
        Slack["Slack Channel"]
    end

    ArXiv --> AC
    Gmail --> MC
    Gmail --> GAC
    YouTube --> YC
    NotionDB --> NR
    TwitterAPI --> XTC

    AC --> TR
    MC --> TR
    GAC --> TR
    YC --> SU
    NR --> WDP
    XTC --> XTP

    MS --> MDC
    MDC --> FTT
    FTT <--> LLMFactory
    FTT --> NBB
    NBB --> NP

    LLMFactory --> OC
    LLMFactory --> OpenAIC
    LLMFactory --> GeminiC
    TR <--> OC
    SU <--> OC
    WDP <--> LLMFactory
    WDP --> DD
    AWP <--> LLMFactory
    AWP --> TrendR
    AWP --> HFR
    DD <--> EmbFactory
    EmbFactory --> OllamaEmb
    EmbFactory --> OpenAIEmb

    TR --> NP
    TR --> SP
    SU --> NP
    SU --> SP
    WDP --> SP
    AWP --> SP
    XTP --> SP

    NP --> Notion
    SP --> Slack
```

## モジュール依存関係

```mermaid
flowchart TB
    subgraph scripts["scripts/"]
        arxiv["arxiv.py"]
        medium["medium.py"]
        medium_translate["medium_translate.py"]
        google_alerts["google_alerts.py"]
        youtube["youtube.py"]
        google_alert_weekly_digest["google_alert_weekly_digest.py"]
        arxiv_weekly["arxiv_weekly.py"]
        x_trend["x_trend.py"]
    end

    subgraph collectors["minitools/collectors/"]
        AC["ArxivCollector"]
        MC["MediumCollector"]
        GAC["GoogleAlertsCollector"]
        YC["YouTubeCollector"]
        XTC["XTrendCollector"]
    end

    subgraph scrapers["minitools/scrapers/"]
        MS["MediumScraper"]
        MDC["MarkdownConverter"]
    end

    subgraph processors["minitools/processors/"]
        TR["Translator"]
        SU["Summarizer"]
        FTT["FullTextTranslator"]
        WDP["WeeklyDigestProcessor"]
        AWP["ArxivWeeklyProcessor"]
        XTP["XTrendProcessor"]
        DD["DuplicateDetector"]
    end

    subgraph researchers["minitools/researchers/"]
        TrendR["TrendResearcher"]
        HFR["HFPapersResearcher"]
    end

    subgraph publishers["minitools/publishers/"]
        NP["NotionPublisher"]
        NBB["NotionBlockBuilder"]
        SP["SlackPublisher"]
    end

    subgraph utils["minitools/utils/"]
        Config["Config"]
        Logger["Logger"]
    end

    arxiv --> AC
    arxiv --> TR
    arxiv --> NP
    arxiv --> SP

    medium --> MC
    medium --> TR
    medium --> NP
    medium --> SP
    medium --> MS
    medium --> FTT
    medium --> NBB

    medium_translate --> MS
    medium_translate --> MDC
    medium_translate --> FTT
    medium_translate --> NBB
    medium_translate --> NP

    google_alerts --> GAC
    google_alerts --> TR
    google_alerts --> NP
    google_alerts --> SP

    youtube --> YC
    youtube --> SU
    youtube --> TR

    google_alert_weekly_digest --> NR
    google_alert_weekly_digest --> WDP
    google_alert_weekly_digest --> SP

    arxiv_weekly --> NR
    arxiv_weekly --> AWP
    arxiv_weekly --> TrendR
    arxiv_weekly --> HFR
    arxiv_weekly --> SP

    x_trend --> XTC
    x_trend --> XTP
    x_trend --> SP

    AC --> Logger
    MC --> Logger
    GAC --> Logger
    YC --> Logger
    XTC --> Logger

    TR --> Config
    TR --> Logger
    SU --> Config
    SU --> Logger
    WDP --> Config
    WDP --> Logger
    AWP --> Logger
    XTP --> Logger
    TrendR --> Logger
    DD --> Logger

    NP --> Logger
    SP --> Logger

    Config --> Logger
```

## データフロー図

### ArXiv 論文処理フロー

```mermaid
flowchart LR
    A["ArXiv API"] --> B["feedparser解析"]
    B --> C["論文メタデータ"]
    C --> D["Translator"]
    D --> E["日本語タイトル/要約"]
    E --> F{"保存先"}
    F -->|Notion| G["NotionPublisher"]
    F -->|Slack| H["SlackPublisher"]
    G --> I["Notion DB"]
    H --> J["Slack Channel"]
```

### Medium Daily Digest 処理フロー

```mermaid
flowchart LR
    A["Gmail API"] --> B["メール取得"]
    B --> C["HTML解析"]
    C --> D["記事リンク抽出"]
    D --> E["Jina AI Reader"]
    E --> F["記事コンテンツ"]
    F --> G["Translator"]
    G --> H["日本語タイトル/要約"]
    H --> I{"保存先"}
    I -->|Notion| J["NotionPublisher"]
    I -->|Slack| K["SlackPublisher"]
```

### Medium 全文翻訳フロー

```mermaid
flowchart LR
    A["Medium URL"] --> B["MediumScraper\n(Playwright CDP)"]
    B --> C["記事HTML"]
    C --> D["MarkdownConverter"]
    D --> E["構造化Markdown"]
    E --> F["FullTextTranslator"]
    F --> G["日本語Markdown"]
    G --> H["NotionBlockBuilder"]
    H --> I["Notionブロック"]
    I --> J["NotionPublisher\nappend_blocks()"]
    J --> K["既存ページに追記"]
```

### Google Alerts 処理フロー

```mermaid
flowchart LR
    A["Gmail API"] --> B["Alertsメール取得"]
    B --> C["HTML解析"]
    C --> D["アラート抽出"]
    D --> E["記事コンテンツ取得"]
    E --> F["Translator"]
    F --> G["日本語タイトル/要約"]
    G --> H{"保存先"}
    H -->|Notion| I["NotionPublisher"]
    H -->|Slack| J["SlackPublisher"]
```

### YouTube 処理フロー

```mermaid
flowchart LR
    A["YouTube URL"] --> B["yt-dlp"]
    B --> C["音声ダウンロード"]
    C --> D["MLX Whisper"]
    D --> E["文字起こし"]
    E --> F["Summarizer"]
    F --> G["英語要約"]
    G --> H["Translator"]
    H --> I["日本語要約"]
    I --> J["ファイル保存"]
```

### X トレンド処理フロー（3ソース統合）

```mermaid
flowchart LR
    subgraph Collect["XTrendCollector (並列収集)"]
        T["トレンド取得\n(Japan/Global WOEID)"]
        K["キーワード検索\n(settings.yaml)"]
        U["ユーザーTL取得\n(settings.yaml)"]
    end

    subgraph Process["XTrendProcessor (LLM処理)"]
        TF["トレンド名\nLLMフィルタ"]
        TT["AI関連のみ\nツイート取得"]
        TS["トレンド要約"]
        KS["キーワード要約"]
        UF["AI関連ツイート\nLLMフィルタ"]
        US["タイムライン要約"]
    end

    T --> TF --> TT --> TS
    K --> KS
    U --> UF --> US

    TS --> SP["SlackPublisher\nformat_x_trend_digest_sections()\n→ send_messages()"]
    KS --> SP
    US --> SP
    SP --> Slack["Slack Channel"]
```

## 外部サービス連携

### LLM抽象化レイヤー

Ollama/OpenAIの両方をサポートするLLM抽象化レイヤー。

| プロバイダー | 用途 | デフォルトモデル | 設定キー |
|-------------|-----|----------------|---------|
| Ollama | 翻訳・要約 | gemma3:27b | `llm.ollama.default_model` |
| OpenAI | 高速処理 | gpt-4o-mini | `llm.openai.default_model` |
| Gemini | 全文翻訳（無料枠活用） | gemini-2.5-flash | `llm.gemini.default_model` |

**連携パターン（LLM抽象化レイヤー経由）:**
```python
from minitools.llm import get_llm_client

# プロバイダーを指定して取得（省略時は設定ファイルから）
client = get_llm_client(provider="ollama")

# 共通インターフェースで呼び出し
response = await client.chat(
    messages=[{"role": "user", "content": prompt}]
)
```

**従来のパターン（直接使用）:**
```python
import ollama

client = ollama.Client()
response = client.chat(
    model="gemma3:27b",
    messages=[{"role": "user", "content": prompt}]
)
```

### Ollama LLM

ローカルで動作するLLMサーバー。翻訳と要約に使用。

| 用途 | モデル | 設定キー |
|-----|--------|---------|
| 翻訳 | gemma3:27b | `models.translation` |
| 要約 | gemma3:27b | `models.summarization` |
| YouTube要約 | gemma3:12b | `models.youtube_summary` |

### Gmail API

Medium Daily DigestとGoogle Alertsメールの取得に使用。

**認証フロー:**
1. OAuth2認証（初回のみブラウザ認証）
2. `token.pickle`にリフレッシュトークン保存
3. 以降は自動更新

**必要なスコープ:**
- `https://www.googleapis.com/auth/gmail.readonly`

**連携パターン:**
```python
from googleapiclient.discovery import build

service = build('gmail', 'v1', credentials=creds)
response = service.users().messages().list(
    userId='me',
    q='from:noreply@medium.com'
).execute()
```

### Notion API

処理結果の保存先データベース。

**機能:**
- ページ作成
- 重複チェック（URL検索）
- バッチ保存

**連携パターン:**
```python
from notion_client import Client

client = Client(auth=api_key)
page = client.pages.create(
    parent={"database_id": database_id},
    properties=properties
)
```

**プロパティマッピング（ソース別）:**

| ソース | Title | URL | Summary | その他 |
|-------|-------|-----|---------|-------|
| ArXiv | タイトル | URL | 日本語訳 | 公開日, 概要, HF Upvotes (Number) |
| Medium | Title | URL | Summary | Japanese Title, Author, Date, Claps (Number), Translated (Checkbox) |
| Google Alerts | Title (日本語) | URL | Summary | Original Title, Source, Tags |

### Slack Webhook

処理完了通知の送信先。

**連携パターン:**
```python
import aiohttp

async with aiohttp.ClientSession() as session:
    async with session.post(webhook_url, json={"text": message}) as response:
        return response.status == 200
```

### Jina AI Reader

Medium記事のコンテンツ取得に使用。

**エンドポイント:** `https://r.jina.ai/{url}`

**特徴:**
- HTMLをMarkdown形式で返却
- Cloudflareによるブロックあり
- User-Agentローテーションで回避

### Tavily API

ArXiv週次ダイジェストでのトレンド調査に使用。

**機能:**
- AI/機械学習分野の最新トレンド検索
- 検索結果のサマリー生成（`include_answer=True`）
- トピック抽出

**連携パターン:**
```python
from tavily import TavilyClient

client = TavilyClient(api_key=api_key)
response = client.search(
    query="AI machine learning latest trends",
    search_depth="basic",
    max_results=5,
    include_answer=True,
)
# response: {answer, results: [{title, url, content}, ...]}
```

**必要な環境変数:**
- `TAVILY_API_KEY`: Tavily APIキー（オプション、未設定時はトレンド調査をスキップ）

### HuggingFace Papers API

ArXiv週次ダイジェストで論文のコミュニティ注目度（upvote数・コメント数）を取得するために使用。

**エンドポイント:** `GET https://huggingface.co/api/papers/{arxiv_id}`

**特徴:**
- 認証不要（公開API）
- arXiv IDで直接検索可能
- 未登録論文は404（upvotes=0として処理）

**連携パターン:**
```python
from minitools.researchers import HFPapersResearcher

async with HFPapersResearcher(max_concurrent=5) as researcher:
    stats = await researcher.get_papers_stats(arxiv_ids)
    # stats: {arxiv_id: HFPaperStats(upvotes, num_comments, found_on_hf)}
```

**レスポンスフィールド:**
- `upvotes`: 論文のupvote数
- `numComments`: コメント数

### TwitterAPI.io

X (Twitter) のトレンド取得、ツイート検索、ユーザータイムライン取得に使用。

**エンドポイント:**
- `GET /twitter/trends` — トレンド取得（WOEID指定）
- `GET /twitter/tweet/advanced_search` — ツイート検索（トレンド名/キーワード）
- `GET /twitter/user/last_tweets` — ユーザータイムライン取得

**連携パターン:**
```python
async with XTrendCollector() as collector:
    result = await collector.collect_all(
        regions=["japan", "global"],
        keywords=["Claude Code", "AI Agent"],
        watch_accounts=["kaboratory"],
    )
```

**必要な環境変数:**
- `TWITTER_API_IO_KEY`: TwitterAPI.io APIキー
- `SLACK_X_TIMELINE_SUMMARY_WEBHOOK_URL`: X トレンドダイジェスト用Slack Webhook URL

## 設定システム概要

```mermaid
flowchart TB
    subgraph "設定ソース"
        ENV[".env ファイル"]
        YAML["settings.yaml"]
        DEFAULT["デフォルト値"]
    end

    subgraph "Config クラス"
        LOAD["load_config()"]
        GET["get(key_path)"]
        API["get_api_key(service)"]
    end

    subgraph "利用側"
        TRANS["Translator"]
        SUMM["Summarizer"]
        NOTION["NotionPublisher"]
        SLACK["SlackPublisher"]
    end

    ENV -->|セキュリティ情報| API
    YAML -->|アプリ設定| LOAD
    DEFAULT -->|フォールバック| LOAD

    LOAD --> GET
    GET --> TRANS
    GET --> SUMM
    API --> NOTION
    API --> SLACK
```

### 設定の優先順位

1. **環境変数** (最高優先)
2. **settings.yaml**
3. **デフォルト値** (最低優先)

### 設定ファイルの役割分担

| ファイル | 内容 | 例 |
|---------|------|---|
| `.env` | セキュリティ情報 | APIキー、Webhook URL |
| `settings.yaml` | アプリ設定 | モデル名、並列数、デフォルト値 |

## 非同期処理アーキテクチャ

```mermaid
flowchart TB
    subgraph "メインプロセス"
        MAIN["main_async()"]
    end

    subgraph "並列処理"
        SEM["Semaphore(3)"]
        T1["Task 1"]
        T2["Task 2"]
        T3["Task 3"]
        TN["Task N"]
    end

    subgraph "I/O操作"
        HTTP["HTTP Request"]
        OLLAMA["Ollama API"]
        NOTION_API["Notion API"]
    end

    MAIN --> SEM
    SEM --> T1
    SEM --> T2
    SEM --> T3
    SEM -.->|待機| TN

    T1 --> HTTP
    T2 --> OLLAMA
    T3 --> NOTION_API
```

### 並列制限の設定

| 項目 | デフォルト値 | 設定キー |
|-----|------------|---------|
| 記事処理 | 10 | `processing.max_concurrent_articles` |
| Ollama API | 3 | `processing.max_concurrent_ollama` |
| Notion API | 3 | `processing.max_concurrent_notion` |
| HTTP接続 | 10 | `processing.max_concurrent_http` |

### バッチスコアリング

週次ダイジェスト（`WeeklyDigestProcessor`, `ArxivWeeklyProcessor`）では、バッチ処理により複数記事/論文を1回のLLM呼び出しでスコアリングします。

```mermaid
flowchart LR
    A["500件の記事"] --> B["バッチ分割\n(20件ずつ)"]
    B --> C["25バッチ"]
    C --> D["LLM API\n並列呼び出し\n(max: 3)"]
    D --> E["スコア付き記事"]
    E --> F["上位N件選出\n+ 重複除去"]
```

| 設定項目 | デフォルト値 | 設定キー |
|---------|------------|---------|
| バッチサイズ（週次ダイジェスト） | 20 | `defaults.weekly_digest.batch_size` |
| バッチサイズ（ArXiv週次） | 20 | `defaults.arxiv_weekly.batch_size` |
| デフォルトプロバイダー（週次ダイジェスト） | openai | `defaults.weekly_digest.provider` |
| デフォルトプロバイダー（ArXiv週次） | openai | `defaults.arxiv_weekly.provider` |

**エラーハンドリング:**
- バッチ処理が失敗した場合、自動的に個別処理にフォールバック
- 個別処理も失敗した場合、デフォルトスコア（5.0）を付与
- 部分的な失敗でも処理は継続

## デプロイメントアーキテクチャ

### ローカル実行

```mermaid
flowchart LR
    subgraph "ローカルマシン"
        CLI["CLI (uv run)"]
        OLLAMA["Ollama Server"]
    end

    subgraph "外部サービス"
        GMAIL["Gmail API"]
        NOTION["Notion API"]
        SLACK["Slack"]
    end

    CLI <--> OLLAMA
    CLI <--> GMAIL
    CLI --> NOTION
    CLI --> SLACK
```

### Docker実行

```mermaid
flowchart TB
    subgraph "Docker Network"
        subgraph "minitools-container"
            APP["minitools"]
        end
        subgraph "ollama-container"
            OLLAMA["Ollama"]
        end
    end

    subgraph "外部サービス"
        GMAIL["Gmail API"]
        NOTION["Notion API"]
        SLACK["Slack"]
    end

    APP <-->|localhost:11434| OLLAMA
    APP <--> GMAIL
    APP --> NOTION
    APP --> SLACK
```

## エラー回復戦略

```mermaid
flowchart TB
    START["リクエスト開始"] --> TRY["試行"]
    TRY --> CHECK{"成功?"}
    CHECK -->|Yes| SUCCESS["完了"]
    CHECK -->|No| RETRY_CHECK{"リトライ回数 < 上限?"}
    RETRY_CHECK -->|Yes| WAIT["指数バックオフ待機"]
    WAIT --> TRY
    RETRY_CHECK -->|No| FALLBACK{"フォールバック可能?"}
    FALLBACK -->|Yes| FB_ACTION["フォールバック処理"]
    FB_ACTION --> SUCCESS
    FALLBACK -->|No| ERROR["エラーログ出力"]
    ERROR --> CONTINUE["次のアイテムへ"]
```

### フォールバック戦略

| シナリオ | フォールバック |
|---------|--------------|
| Jina Reader ブロック | メールのプレビューテキストを使用 |
| 記事コンテンツ取得失敗 | スニペットを使用 |
| 翻訳エラー | 元のテキストを返却 |
| mlx-whisper 未インストール | エラーメッセージを表示して終了 |
