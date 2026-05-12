"""
Weekly digest processor for generating AI-powered summaries.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.llm.embeddings import BaseEmbeddingClient, get_embedding_client
from minitools.processors.duplicate_detector import deduplicate_articles
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# 重要度判定プロンプト（単一記事用）
IMPORTANCE_PROMPT_TEMPLATE = """あなたはAI/テクノロジーニュースの専門アナリストです。
以下の記事の重要度を評価してください。

## 評価基準（各項目1-10点）
1. **技術的影響度**: 技術的なブレークスルーや革新性の程度
2. **業界インパクト**: 業界全体への影響範囲と深刻度
3. **話題性**: 現在の注目度、メディアでの言及頻度
4. **新規性**: 新しい発見・発表か、既存情報の焼き直しか

## 記事情報
タイトル: {title}
要約: {summary}

## 回答形式
以下のJSON形式で回答してください:
{{
  "technical_impact": <1-10の整数>,
  "industry_impact": <1-10の整数>,
  "trending": <1-10の整数>,
  "novelty": <1-10の整数>,
  "reason": "<50文字以内の簡潔な評価理由>"
}}
"""

# バッチスコアリング用プロンプトテンプレート
BATCH_IMPORTANCE_PROMPT_TEMPLATE = """あなたはAI/テクノロジーニュースの専門アナリストです。
以下の{count}件の記事それぞれの重要度を評価してください。

## 評価基準（各項目1-10点）
1. **技術的影響度**: 技術的なブレークスルーや革新性の程度
2. **業界インパクト**: 業界全体への影響範囲と深刻度
3. **話題性**: 現在の注目度、メディアでの言及頻度
4. **新規性**: 新しい発見・発表か、既存情報の焼き直しか

## 記事リスト
{articles_text}

## 回答形式
以下のJSON形式で回答してください。必ず全{count}件の記事について回答してください:
{{
  "results": [
    {{
      "index": 0,
      "technical_impact": <1-10の整数>,
      "industry_impact": <1-10の整数>,
      "trending": <1-10の整数>,
      "novelty": <1-10の整数>,
      "reason": "<50文字以内の簡潔な評価理由>"
    }},
    ...
  ]
}}
"""

# トレンド総括プロンプト
TREND_SUMMARY_PROMPT_TEMPLATE = """あなたはAI/テクノロジー分野の専門ジャーナリストです。
以下の記事リストを分析し、今週のAI分野のトレンドを総括してください。

## 記事リスト
{articles_text}

## 指示
- 300-400文字の日本語で総括を作成してください
- 主要なトレンドや注目すべき動向を3-4点挙げてください
- 具体的な記事タイトルに言及する必要はありません
- ビジネスパーソンが読んで価値のある洞察を含めてください

## 総括:
"""

# 記事要約プロンプト
ARTICLE_SUMMARY_PROMPT_TEMPLATE = """以下の記事を3-4文（100-150文字）の日本語で要約してください。

タイトル: {title}
内容: {content}

要約:
"""


class DigestProcessor:
    """週次/日次共通の汎用ダイジェスト Processor

    記事リストを受け取り、重要度スコアリング・重複除去・トレンド総括・
    記事要約を生成する。期間（週次/日次）に依存しない設計のため、
    呼び出し側で取得期間を制御することで再利用可能。
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        embedding_client: Optional[BaseEmbeddingClient] = None,
        max_concurrent: int = 3,
        batch_size: Optional[int] = None,
    ):
        """
        Args:
            llm_client: LLMクライアントインスタンス
            embedding_client: Embeddingクライアント（省略時は自動生成）
            max_concurrent: 最大並列処理数（デフォルト: 3）
            batch_size: バッチスコアリングのサイズ（省略時は設定ファイルから取得）
        """
        self.llm = llm_client
        self.embedding_client = embedding_client
        config = get_config()
        self.max_concurrent = max_concurrent or config.get(
            "processing.max_concurrent_ollama", 3
        )
        # バッチサイズ設定
        self.batch_size = batch_size or config.get(
            "defaults.weekly_digest.batch_size", 20
        )
        # 重複除去設定
        self.dedup_enabled = config.get(
            "defaults.weekly_digest.deduplication.enabled", True
        )
        self.similarity_threshold = config.get(
            "defaults.weekly_digest.deduplication.similarity_threshold", 0.85
        )
        self.buffer_ratio = config.get(
            "defaults.weekly_digest.deduplication.buffer_ratio", 2.5
        )
        logger.info(
            f"DigestProcessor initialized "
            f"(max_concurrent={self.max_concurrent}, "
            f"batch_size={self.batch_size}, "
            f"dedup_enabled={self.dedup_enabled})"
        )

    def _safe_get_score(self, value: Any, default: int = 5) -> int:
        """
        スコア値を安全に取得（型チェックと変換）

        Args:
            value: スコア値（整数、文字列、Noneなど）
            default: デフォルト値

        Returns:
            1-10の範囲の整数スコア
        """
        if value is None:
            return default

        if isinstance(value, int):
            return max(1, min(10, value))

        if isinstance(value, str):
            try:
                num_value = float(value)
                return max(1, min(10, int(num_value)))
            except (ValueError, TypeError):
                return default

        if isinstance(value, float):
            return max(1, min(10, int(value)))

        return default

    async def _score_single(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        単一記事をスコアリング（フォールバック用）

        Args:
            article: 記事データ

        Returns:
            スコア付き記事データ
        """
        title = article.get("title", article.get("original_title", ""))
        summary = article.get("summary", article.get("snippet", ""))

        if not title:
            logger.warning("Article without title, assigning score 0")
            article["importance_score"] = 0
            article["score_reason"] = "タイトルなし"
            return article

        prompt = IMPORTANCE_PROMPT_TEMPLATE.format(
            title=title,
            summary=summary[:500] if summary else "要約なし",
        )

        try:
            if hasattr(self.llm, "chat_json"):
                response = await self.llm.chat_json(
                    [{"role": "user", "content": prompt}]
                )
            else:
                response = await self.llm.generate(prompt)

            result = json.loads(response)

            scores = [
                self._safe_get_score(result.get("technical_impact"), 5),
                self._safe_get_score(result.get("industry_impact"), 5),
                self._safe_get_score(result.get("trending"), 5),
                self._safe_get_score(result.get("novelty"), 5),
            ]
            avg_score = sum(scores) / len(scores)

            article["importance_score"] = round(avg_score, 1)
            article["score_reason"] = result.get("reason", "")
            article["score_details"] = result

            logger.debug(
                f"Scored (single) '{title[:40]}...': {article['importance_score']}"
            )

        except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
            logger.warning(
                f"Failed to score article (single) '{title[:40]}...': {type(e).__name__}: {e}"
            )
            article["importance_score"] = 5.0
            article["score_reason"] = "スコアリング失敗"

        return article

    async def _score_batch(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        複数記事を1回のLLM呼び出しでスコアリング

        Args:
            articles: 記事リスト（最大batch_size件）

        Returns:
            スコア付き記事リスト

        Raises:
            json.JSONDecodeError: レスポンスのパース失敗時
            LLMError: LLM API呼び出し失敗時
        """
        if not articles:
            return []

        # 記事リストをテキスト化
        articles_text_parts = []
        for i, article in enumerate(articles):
            title = article.get("title", article.get("original_title", ""))
            summary = article.get("summary", article.get("snippet", ""))
            articles_text_parts.append(
                f"[{i}] タイトル: {title}\n    要約: {summary[:300] if summary else '要約なし'}"
            )

        articles_text = "\n\n".join(articles_text_parts)

        prompt = BATCH_IMPORTANCE_PROMPT_TEMPLATE.format(
            count=len(articles),
            articles_text=articles_text,
        )

        # LLM呼び出し
        if hasattr(self.llm, "chat_json"):
            response = await self.llm.chat_json([{"role": "user", "content": prompt}])
        else:
            response = await self.llm.generate(prompt)

        # JSONパース（失敗時は例外をそのまま上げる）
        parsed = json.loads(response)

        # オブジェクト形式 {"results": [...]} または配列形式 [...] の両方に対応
        if isinstance(parsed, dict) and "results" in parsed:
            results = parsed["results"]
        elif isinstance(parsed, list):
            results = parsed
        else:
            raise json.JSONDecodeError(
                "Expected JSON object with 'results' key or JSON array", response, 0
            )

        if not isinstance(results, list):
            raise json.JSONDecodeError("Expected results to be a list", response, 0)

        # 結果を記事にマッピング
        result_map = {r.get("index", -1): r for r in results}

        for i, article in enumerate(articles):
            title = article.get("title", article.get("original_title", ""))

            if i in result_map:
                result = result_map[i]
                scores = [
                    self._safe_get_score(result.get("technical_impact"), 5),
                    self._safe_get_score(result.get("industry_impact"), 5),
                    self._safe_get_score(result.get("trending"), 5),
                    self._safe_get_score(result.get("novelty"), 5),
                ]
                avg_score = sum(scores) / len(scores)

                article["importance_score"] = round(avg_score, 1)
                article["score_reason"] = result.get("reason", "")
                article["score_details"] = result

                logger.debug(
                    f"Scored (batch) '{title[:40]}...': {article['importance_score']}"
                )
            else:
                # indexが見つからない場合はデフォルトスコア
                logger.warning(f"Missing score for index {i}, using default")
                article["importance_score"] = 5.0
                article["score_reason"] = "スコアリング結果なし"

        return articles

    async def rank_articles_by_importance(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        各記事に重要度スコア(1-10)を付与（バッチ処理対応）

        Args:
            articles: 記事データのリスト

        Returns:
            importance_scoreが付与された記事リスト
        """
        if not articles:
            return []

        logger.info(
            f"Ranking {len(articles)} articles by importance "
            f"(batch_size={self.batch_size})..."
        )
        semaphore = asyncio.Semaphore(self.max_concurrent)

        # 記事をバッチに分割
        batches = [
            articles[i : i + self.batch_size]
            for i in range(0, len(articles), self.batch_size)
        ]
        logger.info(f"Split into {len(batches)} batches")

        async def process_batch(
            batch: List[Dict[str, Any]], batch_idx: int
        ) -> List[Dict[str, Any]]:
            """バッチを処理し、失敗時は個別処理にフォールバック"""
            async with semaphore:
                try:
                    # バッチ処理を試行
                    result = await self._score_batch(batch)
                    logger.debug(f"Batch {batch_idx + 1} scored successfully")
                    return result

                except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
                    # バッチ処理失敗時は個別処理へフォールバック
                    logger.warning(
                        f"Batch {batch_idx + 1} failed ({type(e).__name__}), "
                        f"falling back to individual scoring"
                    )
                    results = []
                    for article in batch:
                        try:
                            scored = await self._score_single(article)
                            results.append(scored)
                        except Exception as e2:
                            logger.warning(
                                f"Individual scoring failed: {type(e2).__name__}: {e2}"
                            )
                            article["importance_score"] = 5.0
                            article["score_reason"] = "スコアリング失敗"
                            results.append(article)
                    return results

        # 全バッチを並列処理
        tasks = [process_batch(batch, idx) for idx, batch in enumerate(batches)]
        batch_results = await asyncio.gather(*tasks)

        # バッチ結果を平坦化
        scored_articles = []
        for batch_result in batch_results:
            scored_articles.extend(batch_result)

        logger.info(f"Completed scoring {len(scored_articles)} articles")
        return scored_articles

    async def select_top_articles(
        self,
        articles: List[Dict[str, Any]],
        top_n: int = 20,
        deduplicate: Optional[bool] = None,
        buffer_ratio: Optional[float] = None,
        similarity_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        スコア上位N件を取得（オプションで重複除去）

        Args:
            articles: importance_scoreが付与された記事リスト
            top_n: 取得する記事数（デフォルト: 20）
            deduplicate: 重複除去を行うか（省略時は設定ファイルに従う）
            buffer_ratio: 候補記事の倍率（省略時は設定ファイルに従う）
            similarity_threshold: 類似度閾値（省略時は設定ファイルに従う）

        Returns:
            上位N件の記事リスト
        """
        if not articles:
            return []

        # 重複除去の有効/無効を決定
        do_dedupe = deduplicate if deduplicate is not None else self.dedup_enabled

        if do_dedupe:
            # Embeddingクライアントを取得（遅延初期化）
            if self.embedding_client is None:
                self.embedding_client = get_embedding_client()

            # 重複除去を実行
            threshold = (
                similarity_threshold
                if similarity_threshold is not None
                else self.similarity_threshold
            )
            ratio = buffer_ratio if buffer_ratio is not None else self.buffer_ratio

            top_articles = await deduplicate_articles(
                articles=articles,
                embedding_client=self.embedding_client,
                similarity_threshold=threshold,
                buffer_ratio=ratio,
                top_n=top_n,
            )
        else:
            # 重複除去なし: 単純にスコア順でソート
            sorted_articles = sorted(
                articles,
                key=lambda x: x.get("importance_score", 0),
                reverse=True,
            )
            top_articles = sorted_articles[:top_n]

        if top_articles:
            logger.info(
                f"Selected top {len(top_articles)} articles "
                f"(score range: {top_articles[0].get('importance_score', 0):.1f} - "
                f"{top_articles[-1].get('importance_score', 0):.1f})"
                + (f", dedup={do_dedupe}" if do_dedupe else "")
            )
        else:
            logger.info("No articles selected")

        return top_articles

    async def generate_trend_summary(
        self,
        articles: List[Dict[str, Any]],
    ) -> str:
        """
        週のトレンド総括を生成

        Args:
            articles: 上位記事のリスト

        Returns:
            200-400文字の日本語トレンド総括
        """
        if not articles:
            return "今週は特筆すべきニュースがありませんでした。"

        # 記事リストをテキスト化
        articles_text = "\n".join(
            f"- {a.get('title', a.get('original_title', 'タイトルなし'))}"
            for a in articles[:20]  # 上位20件に制限
        )

        prompt = TREND_SUMMARY_PROMPT_TEMPLATE.format(articles_text=articles_text)

        try:
            summary = await self.llm.generate(prompt)
            logger.info(f"Generated trend summary ({len(summary)} chars)")
            return summary.strip()

        except LLMError as e:
            logger.error(f"Failed to generate trend summary: {e}")
            return "トレンド総括の生成に失敗しました。"

    async def generate_article_summaries(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        各記事の3-4行要約を生成

        Args:
            articles: 記事データのリスト

        Returns:
            digest_summaryが付与された記事リスト
        """
        if not articles:
            return []

        logger.info(f"Generating summaries for {len(articles)} articles...")
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def summarize_article(article: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                title = article.get("title", article.get("original_title", ""))
                content = article.get("summary", article.get("snippet", ""))

                # 既に日本語要約があれば使用
                if article.get("japanese_summary"):
                    article["digest_summary"] = article["japanese_summary"]
                    return article

                if not title and not content:
                    article["digest_summary"] = "情報なし"
                    return article

                prompt = ARTICLE_SUMMARY_PROMPT_TEMPLATE.format(
                    title=title or "タイトルなし",
                    content=content[:1000] if content else "内容なし",
                )

                try:
                    summary = await self.llm.generate(prompt)
                    article["digest_summary"] = summary.strip()
                    logger.debug(f"Summarized '{title[:40]}...'")

                except LLMError as e:
                    logger.warning(f"Failed to summarize '{title[:40]}...': {e}")
                    # フォールバック: 既存の要約を使用
                    article["digest_summary"] = content[:200] if content else "要約なし"

                return article

        # 全記事を並列処理
        tasks = [summarize_article(article) for article in articles]
        summarized_articles = await asyncio.gather(*tasks)

        logger.info(f"Completed summarizing {len(summarized_articles)} articles")
        return list(summarized_articles)

    async def process(
        self,
        articles: List[Dict[str, Any]],
        top_n: int = 20,
        deduplicate: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        週次ダイジェストを一括生成

        Args:
            articles: 全記事リスト
            top_n: 上位記事数（デフォルト: 20）
            deduplicate: 重複除去を行うか（省略時は設定ファイルに従う）

        Returns:
            処理結果の辞書:
            - trend_summary: トレンド総括
            - top_articles: 上位記事リスト（要約付き）
            - total_articles: 処理した記事総数
            - duplicate_groups: 検出した重複グループ数（重複除去時のみ）
        """
        logger.info(f"Starting weekly digest processing ({len(articles)} articles)...")

        # 1. 重要度スコアリング
        scored_articles = await self.rank_articles_by_importance(articles)

        # 2. 上位N件を選出（重複除去付き）
        top_articles = await self.select_top_articles(
            scored_articles, top_n, deduplicate=deduplicate
        )

        # 3. トレンド総括を生成
        trend_summary = await self.generate_trend_summary(top_articles)

        # 4. 各記事の要約を生成
        summarized_articles = await self.generate_article_summaries(top_articles)

        logger.info("Weekly digest processing completed")

        result = {
            "trend_summary": trend_summary,
            "top_articles": summarized_articles,
            "total_articles": len(articles),
        }

        # 重複除去が有効な場合、重複グループ数を追加
        duplicate_groups = sum(
            1 for a in summarized_articles if a.get("duplicate_count", 1) > 1
        )
        if duplicate_groups > 0:
            result["duplicate_groups"] = duplicate_groups

        return result

    async def summarize_all_articles(
        self,
        articles: List[Dict[str, Any]],
        *,
        chunk_size: int = 50,
        highlight_articles: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """その日の全記事を俯瞰した日本語サマリ（4〜6文）を LLM で生成。

        具体的な企業名・製品名・固有名詞・特徴的なキーワードを必ず含めるよう
        プロンプトで指示する。highlight_articles が渡された場合は、それらを
        「特に注目された Top 記事」として LLM に提示し、要約に反映させる。

        - 入力件数が chunk_size 以下: 単発 LLM 呼び出し
        - 入力件数が chunk_size 超: 2段階要約（チャンク並列要約 → 統合要約）
        - LLM 失敗時は空文字を返す（呼び出し側で省略表示にフォールバック）

        Args:
            articles: 記事リスト（dedup 済み・Top N 絞り込み前）
            chunk_size: 単発要約の上限件数
            highlight_articles: 当日 Top N 記事（要約に踏み込ませるための追加コンテキスト）

        Returns:
            4〜6文の日本語サマリ。失敗時は空文字
        """
        if not articles:
            return ""

        highlight_block = self._format_highlight_block(highlight_articles)

        if len(articles) <= chunk_size:
            return await self._summarize_chunk(articles, highlight_block)

        chunks = [
            articles[i : i + chunk_size] for i in range(0, len(articles), chunk_size)
        ]
        logger.info(
            f"summarize_all_articles: 2段階要約 ({len(articles)} 件 → {len(chunks)} チャンク)"
        )
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _partial(chunk: List[Dict[str, Any]]) -> str:
            async with semaphore:
                return await self._summarize_chunk(chunk, "")

        partial_summaries = await asyncio.gather(*(_partial(c) for c in chunks))
        partial_summaries = [s for s in partial_summaries if s]
        if not partial_summaries:
            return ""

        merge_prompt = (
            "あなたは AI / テクノロジーニュースの専門アナリストです。"
            "以下は本日収集された AI 関連ニュース記事を分割して要約した部分サマリと、"
            "特に注目された Top 記事の一覧です。これらを統合して本日の AI 業界の動向を"
            "4〜6文の日本語でまとめてください。\n\n"
            "## 必須要件\n"
            "- 企業名・製品名・モデル名・人名などの固有名詞を最低3つ以上含めること（例: OpenAI, GPT-5, Anthropic, Gemini, NVIDIA）\n"
            "- 本日特徴的だった具体的なトピック（新製品発表、買収、研究成果、規制動向等）に必ず触れること\n"
            "- Top 記事の中身に踏み込んだ言及を含めること\n"
            "- 「AI が進化している」「業界が活況」のような一般論や抽象表現は禁止\n"
            "- 箇条書き禁止、自然な文章で記述\n\n"
            f"{highlight_block}"
            "## 部分サマリ\n"
            + "\n\n".join(f"[{i + 1}] {s}" for i, s in enumerate(partial_summaries))
            + "\n\n## 統合サマリ:\n"
        )
        try:
            merged = await self.llm.generate(merge_prompt)
            return merged.strip()
        except LLMError as e:
            logger.warning(f"summarize_all_articles 統合要約失敗: {e}")
            return ""

    @staticmethod
    def _format_highlight_block(
        highlight_articles: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Top 記事ハイライトをプロンプトに差し込むテキストブロックに整形"""
        if not highlight_articles:
            return ""
        lines = []
        for i, a in enumerate(highlight_articles[:10], 1):
            title = a.get("title", a.get("original_title", "")) or ""
            summary = (
                a.get("digest_summary")
                or a.get("japanese_summary")
                or a.get("summary", "")
                or ""
            )
            lines.append(f"{i}. {title}: {summary[:150]}")
        return "## 本日特に注目された Top 記事\n" + "\n".join(lines) + "\n\n"

    async def _summarize_chunk(
        self,
        articles: List[Dict[str, Any]],
        highlight_block: str = "",
    ) -> str:
        """チャンク単位で日本語俯瞰サマリを生成（失敗時は空文字）"""
        if not articles:
            return ""
        lines = []
        for a in articles:
            title = a.get("title", a.get("original_title", ""))
            summary = a.get("summary", a.get("snippet", "")) or ""
            lines.append(f"- {title}: {summary[:200]}")
        prompt = (
            "あなたは AI / テクノロジーニュースの専門アナリストです。"
            "以下は本日収集された AI 関連ニュース記事一覧（タイトル + 要約）です。"
            "本日の AI 業界の動向を4〜6文の日本語でまとめてください。\n\n"
            "## 必須要件\n"
            "- 企業名・製品名・モデル名・人名などの固有名詞を最低3つ以上含めること\n"
            "- 本日特徴的だった具体的なトピック（新製品発表、買収、研究成果、規制動向等）に必ず触れること\n"
            "- 「AI が進化している」のような一般論や抽象表現は禁止\n"
            "- 箇条書き禁止、自然な文章で記述\n\n"
            f"{highlight_block}"
            "## 記事一覧\n" + "\n".join(lines) + "\n\n## サマリ:\n"
        )
        try:
            summary = await self.llm.generate(prompt)
            return summary.strip()
        except LLMError as e:
            logger.warning(f"_summarize_chunk 失敗: {e}")
            return ""


WeeklyDigestProcessor = DigestProcessor
