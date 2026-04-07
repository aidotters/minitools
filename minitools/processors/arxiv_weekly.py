"""
ArXiv weekly digest processor for generating paper importance rankings.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from minitools.llm.base import BaseLLMClient, LLMError
from minitools.researchers.hf_papers import HFPapersResearcher
from minitools.researchers.trend import TrendResearcher
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# トレンドあり版の重要度評価プロンプト（4観点）
IMPORTANCE_PROMPT_WITH_TRENDS = """あなたはAI/機械学習分野の専門研究者です。
以下のArXiv論文の重要度を評価してください。

## 現在のAIトレンド（参考情報）
{trend_summary}

注目されているトピック: {trend_topics}

## 評価基準（各項目1-10点）
1. **技術的新規性**: 新しい手法・アプローチの独創性
2. **業界インパクト**: 実務・産業への影響可能性
3. **実用性**: 実際に使える・応用できる度合い
4. **トレンド関連性**: 現在のAIトレンドとの関連度

## 論文情報
タイトル: {title}
概要（日本語訳）: {summary}

## 回答形式（JSON）
{{
  "technical_novelty": <1-10の整数>,
  "industry_impact": <1-10の整数>,
  "practicality": <1-10の整数>,
  "trend_relevance": <1-10の整数>,
  "reason": "<100文字以内の簡潔な評価理由>"
}}
"""

# トレンドなし版の重要度評価プロンプト（3観点）
IMPORTANCE_PROMPT_WITHOUT_TRENDS = """あなたはAI/機械学習分野の専門研究者です。
以下のArXiv論文の重要度を評価してください。

## 評価基準（各項目1-10点）
1. **技術的新規性**: 新しい手法・アプローチの独創性
2. **業界インパクト**: 実務・産業への影響可能性
3. **実用性**: 実際に使える・応用できる度合い

## 論文情報
タイトル: {title}
概要（日本語訳）: {summary}

## 回答形式（JSON）
{{
  "technical_novelty": <1-10の整数>,
  "industry_impact": <1-10の整数>,
  "practicality": <1-10の整数>,
  "reason": "<100文字以内の簡潔な評価理由>"
}}
"""

# バッチスコアリング用プロンプト（トレンドあり）
BATCH_IMPORTANCE_PROMPT_WITH_TRENDS = """あなたはAI/機械学習分野の専門研究者です。
以下の{count}件のArXiv論文それぞれの重要度を評価してください。

## 現在のAIトレンド（参考情報）
{trend_summary}

注目されているトピック: {trend_topics}

## 評価基準（各項目1-10点）
1. **技術的新規性**: 新しい手法・アプローチの独創性
2. **業界インパクト**: 実務・産業への影響可能性
3. **実用性**: 実際に使える・応用できる度合い
4. **トレンド関連性**: 現在のAIトレンドとの関連度

## 論文リスト
{papers_text}

## 回答形式
以下のJSON形式で回答してください。必ず全{count}件の論文について回答してください:
{{
  "results": [
    {{
      "index": 0,
      "technical_novelty": <1-10の整数>,
      "industry_impact": <1-10の整数>,
      "practicality": <1-10の整数>,
      "trend_relevance": <1-10の整数>,
      "reason": "<100文字以内の簡潔な評価理由>"
    }},
    ...
  ]
}}
"""

# バッチスコアリング用プロンプト（トレンドなし）
BATCH_IMPORTANCE_PROMPT_WITHOUT_TRENDS = """あなたはAI/機械学習分野の専門研究者です。
以下の{count}件のArXiv論文それぞれの重要度を評価してください。

## 評価基準（各項目1-10点）
1. **技術的新規性**: 新しい手法・アプローチの独創性
2. **業界インパクト**: 実務・産業への影響可能性
3. **実用性**: 実際に使える・応用できる度合い

## 論文リスト
{papers_text}

## 回答形式
以下のJSON形式で回答してください。必ず全{count}件の論文について回答してください:
{{
  "results": [
    {{
      "index": 0,
      "technical_novelty": <1-10の整数>,
      "industry_impact": <1-10の整数>,
      "practicality": <1-10の整数>,
      "reason": "<100文字以内の簡潔な評価理由>"
    }},
    ...
  ]
}}
"""

# トレンドサマリー日本語化プロンプト
TREND_SUMMARY_PROMPT = """以下のAIトレンド情報を日本語で要約してください。

## 英語サマリー
{english_summary}

## 注目トピック
{topics}

## 回答形式
- 250文字以内の日本語で要約
- 現在のAI業界で注目されているトレンドを簡潔に説明
- 専門用語はそのまま使用可（例: LLM, RAG, マルチモーダル等）
"""

# ハイライト生成プロンプト
HIGHLIGHTS_PROMPT = """以下のArXiv論文について、重要ポイントを抽出してください。

## 論文情報
タイトル: {title}
概要（日本語訳）: {summary}

## 回答形式（JSON）
{{
  "selection_reason": "<なぜこの論文を選出したかを50文字以内で>",
  "key_points": [
    "<重要ポイント1（30文字以内）>",
    "<重要ポイント2（30文字以内）>",
    "<重要ポイント3（30文字以内）>"
  ]
}}
"""


class ArxivWeeklyProcessor:
    """ArXiv週次ダイジェスト生成プロセッサ"""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        trend_researcher: Optional[TrendResearcher] = None,
        hf_researcher: Optional[HFPapersResearcher] = None,
        max_concurrent: int = 3,
        batch_size: Optional[int] = None,
    ):
        """
        Args:
            llm_client: LLMクライアントインスタンス
            trend_researcher: TrendResearcherインスタンス（省略時は自動生成）
            hf_researcher: HFPapersResearcherインスタンス（省略時はHFセクションをスキップ）
            max_concurrent: 最大並列処理数（デフォルト: 3）
            batch_size: バッチスコアリングのサイズ（省略時は設定ファイルから取得）
        """
        self.llm = llm_client
        self.trend_researcher = trend_researcher
        self.hf_researcher = hf_researcher
        config = get_config()
        self.max_concurrent = max_concurrent or config.get(
            "processing.max_concurrent_ollama", 3
        )
        self.batch_size = batch_size or config.get(
            "defaults.arxiv_weekly.batch_size", 20
        )
        logger.info(
            f"ArxivWeeklyProcessor initialized "
            f"(max_concurrent={max_concurrent}, batch_size={self.batch_size})"
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

    async def _score_single(
        self,
        paper: Dict[str, Any],
        trends: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        単一論文をスコアリング（フォールバック用）

        Args:
            paper: 論文データ
            trends: トレンド情報

        Returns:
            スコア付き論文データ
        """
        title = paper.get("title", paper.get("タイトル", ""))
        summary = paper.get("日本語訳", paper.get("summary", ""))

        if not title and not summary:
            logger.warning("Paper without title or summary, assigning score 0")
            paper["importance_score"] = 0
            paper["score_reason"] = "情報なし"
            return paper

        if trends:
            prompt = IMPORTANCE_PROMPT_WITH_TRENDS.format(
                trend_summary=trends.get("summary", "情報なし"),
                trend_topics=", ".join(trends.get("topics", [])),
                title=title,
                summary=summary[:1000] if summary else "概要なし",
            )
        else:
            prompt = IMPORTANCE_PROMPT_WITHOUT_TRENDS.format(
                title=title,
                summary=summary[:1000] if summary else "概要なし",
            )

        try:
            if hasattr(self.llm, "chat_json"):
                response = await self.llm.chat_json(
                    [{"role": "user", "content": prompt}]
                )
            else:
                response = await self.llm.generate(prompt)

            result = json.loads(response)

            if trends:
                scores = [
                    self._safe_get_score(result.get("technical_novelty"), 5),
                    self._safe_get_score(result.get("industry_impact"), 5),
                    self._safe_get_score(result.get("practicality"), 5),
                    self._safe_get_score(result.get("trend_relevance"), 5),
                ]
            else:
                scores = [
                    self._safe_get_score(result.get("technical_novelty"), 5),
                    self._safe_get_score(result.get("industry_impact"), 5),
                    self._safe_get_score(result.get("practicality"), 5),
                ]

            avg_score = sum(scores) / len(scores)
            paper["importance_score"] = round(avg_score, 1)
            paper["score_reason"] = result.get("reason", "")
            paper["score_details"] = result

            logger.debug(
                f"Scored (single) '{title[:40]}...': {paper['importance_score']}"
            )

        except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
            logger.warning(
                f"Failed to score paper (single) '{title[:40]}...': {type(e).__name__}: {e}"
            )
            paper["importance_score"] = 5.0
            paper["score_reason"] = "スコアリング失敗"

        return paper

    async def _score_batch(
        self,
        papers: List[Dict[str, Any]],
        trends: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        複数論文を1回のLLM呼び出しでスコアリング

        Args:
            papers: 論文リスト（最大batch_size件）
            trends: トレンド情報

        Returns:
            スコア付き論文リスト

        Raises:
            json.JSONDecodeError: レスポンスのパース失敗時
            LLMError: LLM API呼び出し失敗時
        """
        if not papers:
            return []

        # 論文リストをテキスト化
        papers_text_parts = []
        for i, paper in enumerate(papers):
            title = paper.get("title", paper.get("タイトル", ""))
            summary = paper.get("日本語訳", paper.get("summary", ""))
            papers_text_parts.append(
                f"[{i}] タイトル: {title}\n    概要: {summary[:500] if summary else '概要なし'}"
            )

        papers_text = "\n\n".join(papers_text_parts)

        # プロンプト構築
        if trends:
            prompt = BATCH_IMPORTANCE_PROMPT_WITH_TRENDS.format(
                count=len(papers),
                trend_summary=trends.get("summary", "情報なし"),
                trend_topics=", ".join(trends.get("topics", [])),
                papers_text=papers_text,
            )
        else:
            prompt = BATCH_IMPORTANCE_PROMPT_WITHOUT_TRENDS.format(
                count=len(papers),
                papers_text=papers_text,
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

        # 結果を論文にマッピング
        result_map = {r.get("index", -1): r for r in results}

        for i, paper in enumerate(papers):
            title = paper.get("title", paper.get("タイトル", ""))

            if i in result_map:
                result = result_map[i]

                if trends:
                    scores = [
                        self._safe_get_score(result.get("technical_novelty"), 5),
                        self._safe_get_score(result.get("industry_impact"), 5),
                        self._safe_get_score(result.get("practicality"), 5),
                        self._safe_get_score(result.get("trend_relevance"), 5),
                    ]
                else:
                    scores = [
                        self._safe_get_score(result.get("technical_novelty"), 5),
                        self._safe_get_score(result.get("industry_impact"), 5),
                        self._safe_get_score(result.get("practicality"), 5),
                    ]

                avg_score = sum(scores) / len(scores)
                paper["importance_score"] = round(avg_score, 1)
                paper["score_reason"] = result.get("reason", "")
                paper["score_details"] = result

                logger.debug(
                    f"Scored (batch) '{title[:40]}...': {paper['importance_score']}"
                )
            else:
                logger.warning(f"Missing score for index {i}, using default")
                paper["importance_score"] = 5.0
                paper["score_reason"] = "スコアリング結果なし"

        return papers

    async def rank_papers_by_importance(
        self,
        papers: List[Dict[str, Any]],
        trends: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        各論文に重要度スコア(1-10)を付与（バッチ処理対応）

        Args:
            papers: 論文リスト
            trends: TrendResearcherから取得したトレンド情報

        Returns:
            importance_scoreが付与された論文リスト
        """
        if not papers:
            return []

        logger.info(
            f"Ranking {len(papers)} papers by importance "
            f"(batch_size={self.batch_size})..."
        )
        semaphore = asyncio.Semaphore(self.max_concurrent)

        # 論文をバッチに分割
        batches = [
            papers[i : i + self.batch_size]
            for i in range(0, len(papers), self.batch_size)
        ]
        logger.info(f"Split into {len(batches)} batches")

        async def process_batch(
            batch: List[Dict[str, Any]], batch_idx: int
        ) -> List[Dict[str, Any]]:
            """バッチを処理し、失敗時は個別処理にフォールバック"""
            async with semaphore:
                try:
                    result = await self._score_batch(batch, trends=trends)
                    logger.debug(f"Batch {batch_idx + 1} scored successfully")
                    return result

                except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
                    logger.warning(
                        f"Batch {batch_idx + 1} failed ({type(e).__name__}), "
                        f"falling back to individual scoring"
                    )
                    results = []
                    for paper in batch:
                        try:
                            scored = await self._score_single(paper, trends=trends)
                            results.append(scored)
                        except Exception as e2:
                            logger.warning(
                                f"Individual scoring failed: {type(e2).__name__}: {e2}"
                            )
                            paper["importance_score"] = 5.0
                            paper["score_reason"] = "スコアリング失敗"
                            results.append(paper)
                    return results

        # 全バッチを並列処理
        tasks = [process_batch(batch, idx) for idx, batch in enumerate(batches)]
        batch_results = await asyncio.gather(*tasks)

        # バッチ結果を平坦化
        scored_papers = []
        for batch_result in batch_results:
            scored_papers.extend(batch_result)

        logger.info(f"Completed scoring {len(scored_papers)} papers")
        return scored_papers

    async def select_top_papers(
        self,
        papers: List[Dict[str, Any]],
        top_n: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        スコア上位N件を選出

        Args:
            papers: importance_scoreが付与された論文リスト
            top_n: 取得する論文数（デフォルト: 10）

        Returns:
            上位N件の論文リスト
        """
        if not papers:
            return []

        # スコア順でソート
        sorted_papers = sorted(
            papers,
            key=lambda x: x.get("importance_score", 0),
            reverse=True,
        )

        top_papers = sorted_papers[:top_n]

        if top_papers:
            logger.info(
                f"Selected top {len(top_papers)} papers "
                f"(score range: {top_papers[0].get('importance_score', 0):.1f} - "
                f"{top_papers[-1].get('importance_score', 0):.1f})"
            )
        else:
            logger.info("No papers selected")

        return top_papers

    async def generate_paper_highlights(
        self,
        papers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        選出理由と重要ポイントを生成

        Args:
            papers: 論文リスト

        Returns:
            selection_reason, key_pointsが付与された論文リスト
        """
        if not papers:
            return []

        logger.info(f"Generating highlights for {len(papers)} papers...")
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def generate_highlight(paper: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                title = paper.get("title", paper.get("タイトル", ""))
                summary = paper.get("日本語訳", paper.get("summary", ""))

                if not title and not summary:
                    paper["selection_reason"] = "ハイライト生成失敗"
                    paper["key_points"] = []
                    return paper

                prompt = HIGHLIGHTS_PROMPT.format(
                    title=title,
                    summary=summary[:1000] if summary else "概要なし",
                )

                try:
                    if hasattr(self.llm, "chat_json"):
                        response = await self.llm.chat_json(
                            [{"role": "user", "content": prompt}]
                        )
                    else:
                        response = await self.llm.generate(prompt)

                    result = json.loads(response)

                    paper["selection_reason"] = result.get(
                        "selection_reason", "選出理由なし"
                    )
                    paper["key_points"] = result.get("key_points", [])

                    logger.debug(f"Generated highlights for '{title[:40]}...'")

                except (json.JSONDecodeError, LLMError, TypeError, ValueError) as e:
                    logger.warning(
                        f"Failed to generate highlights for '{title[:40]}...': "
                        f"{type(e).__name__}: {e}"
                    )
                    paper["selection_reason"] = "ハイライト生成失敗"
                    paper["key_points"] = []

                return paper

        tasks = [generate_highlight(paper) for paper in papers]
        highlighted_papers = await asyncio.gather(*tasks)

        logger.info(
            f"Completed generating highlights for {len(highlighted_papers)} papers"
        )
        return list(highlighted_papers)

    async def _translate_trend_summary(
        self,
        trend_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        トレンドサマリーを日本語に翻訳

        Args:
            trend_info: TrendResearcherから取得したトレンド情報

        Returns:
            日本語化されたトレンド情報
        """
        english_summary = trend_info.get("summary", "")
        topics = trend_info.get("topics", [])

        if not english_summary:
            return trend_info

        prompt = TREND_SUMMARY_PROMPT.format(
            english_summary=english_summary,
            topics=", ".join(topics) if topics else "なし",
        )

        try:
            if hasattr(self.llm, "chat"):
                response = await self.llm.chat([{"role": "user", "content": prompt}])
            else:
                response = await self.llm.generate(prompt)

            # 日本語サマリーで更新
            japanese_summary = response.strip()
            if japanese_summary:
                trend_info["summary"] = japanese_summary
                logger.info("Trend summary translated to Japanese")

        except Exception as e:
            logger.warning(f"Failed to translate trend summary: {e}")
            # 翻訳失敗時は元のサマリーを維持

        return trend_info

    @staticmethod
    def _extract_arxiv_id(url: str) -> str:
        """URLからarXiv IDを抽出

        Args:
            url: arXiv URL (例: "https://arxiv.org/abs/2601.00001v1")

        Returns:
            arXiv ID (例: "2601.00001")、抽出できない場合は空文字列
        """
        match = re.search(r"(\d{4}\.\d{4,5})", url)
        return match.group(1) if match else ""

    async def _fetch_hf_stats(
        self, papers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """論文にHF統計情報を付与

        Args:
            papers: 論文リスト

        Returns:
            hf_upvotes, hf_commentsが付与された論文リスト
        """
        if not self.hf_researcher:
            return papers

        # arXiv IDを抽出
        arxiv_ids = []
        for paper in papers:
            url = paper.get("url", paper.get("URL", ""))
            arxiv_id = self._extract_arxiv_id(url)
            if arxiv_id:
                arxiv_ids.append(arxiv_id)

        if not arxiv_ids:
            logger.warning("No arXiv IDs found in papers")
            return papers

        try:
            stats_map = await self.hf_researcher.get_papers_stats(arxiv_ids)
        except Exception as e:
            logger.warning(f"Failed to fetch HF stats: {e}")
            return papers

        # 各論文にHF統計を付与
        for paper in papers:
            url = paper.get("url", paper.get("URL", ""))
            arxiv_id = self._extract_arxiv_id(url)
            if arxiv_id and arxiv_id in stats_map:
                stats = stats_map[arxiv_id]
                paper["hf_upvotes"] = stats.upvotes
                paper["hf_comments"] = stats.num_comments

        return papers

    async def _select_hf_top_papers(
        self,
        papers: List[Dict[str, Any]],
        hf_top_n: int,
    ) -> List[Dict[str, Any]]:
        """HF upvote上位の論文を選出

        Args:
            papers: hf_upvotesが付与された論文リスト
            hf_top_n: 選出する件数

        Returns:
            upvote > 0 の論文をupvote降順で上位hf_top_n件
        """
        # upvote > 0 の論文のみ
        hf_candidates = [p for p in papers if p.get("hf_upvotes", 0) > 0]

        # upvote降順ソート（同値はコメント数で二次ソート）
        hf_candidates.sort(
            key=lambda x: (x.get("hf_upvotes", 0), x.get("hf_comments", 0)),
            reverse=True,
        )

        selected = hf_candidates[:hf_top_n]
        if selected:
            logger.info(
                f"HF section: selected {len(selected)} papers "
                f"(upvotes range: {selected[0].get('hf_upvotes', 0)} - "
                f"{selected[-1].get('hf_upvotes', 0)})"
            )
        else:
            logger.info("HF section: no papers with upvotes > 0")

        return selected

    async def process(
        self,
        papers: List[Dict[str, Any]],
        top_n: int = 10,
        use_trends: bool = True,
        hf_top_n: int = 5,
        llm_top_n: int = 5,
    ) -> Dict[str, Any]:
        """
        一括処理: HF統計取得 → トレンド調査 → スコアリング → 選出 → ハイライト生成

        2層構成:
        - セクション1: HF upvote上位 (hf_researcher が指定されている場合)
        - セクション2: LLMスコアリング上位 (セクション1を除外した残り)

        Args:
            papers: 全論文リスト
            top_n: 上位論文数（後方互換、hf_researcher未指定時に使用）
            use_trends: Trueの場合、Tavily APIでトレンドを調査
            hf_top_n: HFセクションの取得件数（デフォルト: 5）
            llm_top_n: LLMセクションの取得件数（デフォルト: 5）

        Returns:
            処理結果の辞書:
            - trend_info: トレンド情報（use_trends=Falseの場合はNone）
            - papers: 全セクションの論文をマージ（後方互換）
            - total_papers: 処理した論文総数
            - hf_papers: セクション1の論文リスト（HF upvote上位）
            - llm_papers: セクション2の論文リスト（LLMスコア上位）
        """
        logger.info(
            f"Starting ArXiv weekly digest processing ({len(papers)} papers)..."
        )

        # 1. HF統計取得 & トレンド調査を並列実行
        trend_info = None

        if self.hf_researcher:
            # HF統計取得とトレンド調査を並列実行
            hf_task = self._fetch_hf_stats(papers)

            if use_trends and self.trend_researcher:
                trend_task = self.trend_researcher.get_current_trends()
                papers, trend_info = await asyncio.gather(hf_task, trend_task)
            else:
                papers = await hf_task
        else:
            # HFなしの場合はトレンド調査のみ
            if use_trends and self.trend_researcher:
                trend_info = await self.trend_researcher.get_current_trends()

        # トレンドサマリーの日本語化
        if trend_info:
            logger.info(
                f"Trend info obtained: {len(trend_info.get('topics', []))} topics"
            )
            trend_info = await self._translate_trend_summary(trend_info)
        elif use_trends and self.trend_researcher:
            logger.warning("Failed to get trend info, proceeding without trends")

        if self.hf_researcher:
            # 2層構成フロー
            # セクション1: HF upvote上位
            hf_papers = await self._select_hf_top_papers(papers, hf_top_n)

            # セクション2: HF選出論文を除外 → LLMスコアリング
            hf_urls = {p.get("url", p.get("URL", "")) for p in hf_papers}
            remaining_papers = [
                p for p in papers if p.get("url", p.get("URL", "")) not in hf_urls
            ]

            logger.info(
                f"LLM section: scoring {len(remaining_papers)} remaining papers"
            )
            scored_papers = await self.rank_papers_by_importance(
                remaining_papers, trends=trend_info
            )
            llm_papers = await self.select_top_papers(scored_papers, llm_top_n)

            # 両セクションにハイライト生成
            hf_count = len(hf_papers)
            all_selected = hf_papers + llm_papers
            highlighted = await self.generate_paper_highlights(all_selected)
            hf_papers = highlighted[:hf_count]
            llm_papers = highlighted[hf_count:]

            logger.info("ArXiv weekly digest processing completed (2-tier)")

            return {
                "trend_info": trend_info,
                "papers": highlighted,
                "total_papers": len(papers),
                "hf_papers": hf_papers,
                "llm_papers": llm_papers,
            }

        else:
            # 従来のLLMのみフロー（後方互換）
            scored_papers = await self.rank_papers_by_importance(
                papers, trends=trend_info
            )
            top_papers = await self.select_top_papers(scored_papers, top_n)
            highlighted_papers = await self.generate_paper_highlights(top_papers)

            logger.info("ArXiv weekly digest processing completed")

            return {
                "trend_info": trend_info,
                "papers": highlighted_papers,
                "total_papers": len(papers),
                "hf_papers": [],
                "llm_papers": [],
            }
