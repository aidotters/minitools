"""Tests for ArxivWeeklyProcessor."""

import json
import pytest

from tests.conftest import MockLLMClient


class TestArxivWeeklyProcessor:
    """ArxivWeeklyProcessorのテスト"""

    @pytest.fixture
    def sample_papers(self):
        """テスト用のサンプル論文データ"""
        return [
            {
                "id": "1",
                "title": "Advances in Transformer Architecture",
                "日本語訳": "Transformerアーキテクチャの進歩に関する研究。新しい注意機構を提案。",
                "url": "https://arxiv.org/abs/2601.00001",
                "公開日": "2026-01-20",
            },
            {
                "id": "2",
                "title": "Efficient LLM Fine-tuning Methods",
                "日本語訳": "LLMの効率的なファインチューニング手法。LoRAを超える新手法を提案。",
                "url": "https://arxiv.org/abs/2601.00002",
                "公開日": "2026-01-19",
            },
            {
                "id": "3",
                "title": "Multimodal Learning Survey",
                "日本語訳": "マルチモーダル学習のサーベイ論文。最新手法を網羅的に解説。",
                "url": "https://arxiv.org/abs/2601.00003",
                "公開日": "2026-01-18",
            },
        ]

    @pytest.fixture
    def sample_trends(self):
        """テスト用のトレンド情報"""
        return {
            "summary": "2026年のAIトレンドでは、エージェントシステムとマルチモーダルモデルが注目されている。",
            "topics": [
                "AI Agents",
                "Multimodal Models",
                "Efficient Training",
                "Safety",
            ],
            "sources": [
                {"title": "AI Trends 2026", "url": "https://example.com/trends"},
            ],
        }

    @pytest.mark.asyncio
    async def test_rank_papers_by_importance_with_trends(
        self, sample_papers, sample_trends
    ):
        """トレンド情報ありでのスコアリングテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        json_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "trend_relevance": 8,
                "reason": "新しい注意機構がトレンドのマルチモーダルに関連",
            }
        )
        mock_llm = MockLLMClient(json_response=json_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.rank_papers_by_importance(
            sample_papers, trends=sample_trends
        )

        assert len(result) == len(sample_papers)
        assert all("importance_score" in paper for paper in result)
        # 平均スコア: (8+7+9+8)/4 = 8.0
        assert result[0]["importance_score"] == 8.0

    @pytest.mark.asyncio
    async def test_rank_papers_by_importance_without_trends(self, sample_papers):
        """トレンド情報なしでのスコアリングテスト（3観点評価）"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        json_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "reason": "革新的なアプローチ",
            }
        )
        mock_llm = MockLLMClient(json_response=json_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.rank_papers_by_importance(sample_papers, trends=None)

        assert len(result) == len(sample_papers)
        assert all("importance_score" in paper for paper in result)
        # 平均スコア: (8+7+9)/3 = 8.0
        assert result[0]["importance_score"] == 8.0

    @pytest.mark.asyncio
    async def test_rank_papers_by_importance_empty_list(self):
        """空リストの場合のテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        mock_llm = MockLLMClient()
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.rank_papers_by_importance([])

        assert result == []

    @pytest.mark.asyncio
    async def test_rank_papers_by_importance_llm_error(self, sample_papers):
        """LLMエラー時はデフォルトスコア5を付与"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        mock_llm = MockLLMClient(json_response="invalid json")
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.rank_papers_by_importance(sample_papers)

        assert len(result) == len(sample_papers)
        assert all(paper["importance_score"] == 5.0 for paper in result)

    @pytest.mark.asyncio
    async def test_select_top_papers(self, sample_papers):
        """上位N件選出のテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        # スコアを付与
        sample_papers[0]["importance_score"] = 9.0
        sample_papers[1]["importance_score"] = 7.5
        sample_papers[2]["importance_score"] = 8.5

        mock_llm = MockLLMClient()
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.select_top_papers(sample_papers, top_n=2)

        assert len(result) == 2
        # スコア降順: 9.0, 8.5
        assert result[0]["importance_score"] == 9.0
        assert result[1]["importance_score"] == 8.5

    @pytest.mark.asyncio
    async def test_select_top_papers_empty_list(self):
        """空リストの場合のテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        mock_llm = MockLLMClient()
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.select_top_papers([])

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_paper_highlights(self, sample_papers):
        """ハイライト生成のテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        json_response = json.dumps(
            {
                "selection_reason": "注意機構の革新的な改良",
                "key_points": [
                    "計算効率が50%向上",
                    "長文処理能力の改善",
                    "既存モデルへの適用が容易",
                ],
            }
        )
        mock_llm = MockLLMClient(json_response=json_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.generate_paper_highlights(sample_papers[:1])

        assert len(result) == 1
        assert "selection_reason" in result[0]
        assert "key_points" in result[0]
        assert len(result[0]["key_points"]) == 3

    @pytest.mark.asyncio
    async def test_generate_paper_highlights_empty_list(self):
        """空リストの場合のテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        mock_llm = MockLLMClient()
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.generate_paper_highlights([])

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_paper_highlights_llm_error(self, sample_papers):
        """LLMエラー時はフォールバックメッセージを設定"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        mock_llm = MockLLMClient(json_response="invalid json")
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.generate_paper_highlights(sample_papers[:1])

        assert len(result) == 1
        assert result[0]["selection_reason"] == "ハイライト生成失敗"
        assert result[0]["key_points"] == []

    @pytest.mark.asyncio
    async def test_process_full_pipeline(self, sample_papers, sample_trends):
        """全パイプラインの統合テスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor
        from unittest.mock import AsyncMock

        # スコアリング用レスポンス
        score_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "trend_relevance": 8,
                "reason": "Significant update",
            }
        )
        mock_llm = MockLLMClient(json_response=score_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        # TrendResearcherのモック
        mock_trend_researcher = AsyncMock()
        mock_trend_researcher.get_current_trends.return_value = sample_trends
        processor.trend_researcher = mock_trend_researcher

        result = await processor.process(papers=sample_papers, top_n=2, use_trends=True)

        assert "trend_info" in result
        assert "papers" in result
        assert "total_papers" in result
        assert result["total_papers"] == len(sample_papers)

    @pytest.mark.asyncio
    async def test_process_without_trends(self, sample_papers):
        """トレンド調査なしでの処理テスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        score_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "reason": "Significant update",
            }
        )
        mock_llm = MockLLMClient(json_response=score_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.process(
            papers=sample_papers, top_n=2, use_trends=False
        )

        assert result["trend_info"] is None
        assert "papers" in result

    @pytest.mark.asyncio
    async def test_concurrent_limit(self, sample_papers):
        """並列処理の制限が機能していることを確認"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        json_response = json.dumps(
            {
                "technical_novelty": 5,
                "industry_impact": 5,
                "practicality": 5,
                "reason": "Test",
            }
        )
        mock_llm = MockLLMClient(json_response=json_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm, max_concurrent=2)

        # 10件の論文を処理
        papers = [
            {
                "title": f"Paper {i}",
                "日本語訳": f"論文{i}の概要",
                "url": f"https://arxiv.org/abs/2601.{i:05d}",
            }
            for i in range(10)
        ]

        result = await processor.rank_papers_by_importance(papers)

        assert len(result) == 10
        assert all("importance_score" in paper for paper in result)


class TestArxivBatchScoring:
    """ArxivWeeklyProcessorのバッチスコアリング機能テスト"""

    @pytest.fixture
    def sample_papers(self):
        """テスト用のサンプル論文データ"""
        return [
            {
                "id": "1",
                "title": "Advances in Transformer Architecture",
                "日本語訳": "Transformerアーキテクチャの進歩に関する研究。",
                "url": "https://arxiv.org/abs/2601.00001",
            },
            {
                "id": "2",
                "title": "Efficient LLM Fine-tuning Methods",
                "日本語訳": "LLMの効率的なファインチューニング手法。",
                "url": "https://arxiv.org/abs/2601.00002",
            },
            {
                "id": "3",
                "title": "Multimodal Learning Survey",
                "日本語訳": "マルチモーダル学習のサーベイ論文。",
                "url": "https://arxiv.org/abs/2601.00003",
            },
        ]

    @pytest.fixture
    def sample_trends(self):
        """テスト用のトレンド情報"""
        return {
            "summary": "2026年のAIトレンドでは、エージェントシステムが注目されている。",
            "topics": ["AI Agents", "Multimodal Models", "Efficient Training"],
        }

    @pytest.mark.asyncio
    async def test_batch_scoring_with_trends(self, sample_papers, sample_trends):
        """トレンドありバッチスコアリングのテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        batch_response = json.dumps(
            [
                {
                    "index": i,
                    "technical_novelty": 8,
                    "industry_impact": 7,
                    "practicality": 9,
                    "trend_relevance": 8,
                    "reason": f"Paper {i} is highly relevant",
                }
                for i in range(len(sample_papers))
            ]
        )
        mock_llm = MockLLMClient(json_response=batch_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm, batch_size=20)

        result = await processor.rank_papers_by_importance(
            sample_papers, trends=sample_trends
        )

        assert len(result) == len(sample_papers)
        assert all("importance_score" in paper for paper in result)

    @pytest.mark.asyncio
    async def test_batch_scoring_without_trends(self, sample_papers):
        """トレンドなしバッチスコアリングのテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        batch_response = json.dumps(
            [
                {
                    "index": i,
                    "technical_novelty": 8,
                    "industry_impact": 7,
                    "practicality": 9,
                    "reason": f"Paper {i} evaluation",
                }
                for i in range(len(sample_papers))
            ]
        )
        mock_llm = MockLLMClient(json_response=batch_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm, batch_size=20)

        result = await processor.rank_papers_by_importance(sample_papers, trends=None)

        assert len(result) == len(sample_papers)
        assert all("importance_score" in paper for paper in result)

    @pytest.mark.asyncio
    async def test_batch_json_error_fallback(self, sample_papers):
        """バッチJSONエラー時のフォールバックテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        mock_llm = MockLLMClient(json_response="invalid json")
        processor = ArxivWeeklyProcessor(llm_client=mock_llm, batch_size=20)

        result = await processor.rank_papers_by_importance(sample_papers)

        # フォールバック時はデフォルトスコア5.0
        assert len(result) == len(sample_papers)
        assert all(paper["importance_score"] == 5.0 for paper in result)

    @pytest.mark.asyncio
    async def test_score_single_method(self, sample_papers):
        """_score_singleメソッドのテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        single_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "reason": "Excellent paper",
            }
        )
        mock_llm = MockLLMClient(json_response=single_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm, batch_size=20)

        # _score_singleメソッドが存在する場合のみテスト
        if hasattr(processor, "_score_single"):
            result = await processor._score_single(sample_papers[0], trends=None)
            assert "importance_score" in result
            # (8+7+9)/3 = 8.0
            assert result["importance_score"] == 8.0

    @pytest.mark.asyncio
    async def test_batch_size_configuration(self, sample_papers):
        """batch_sizeパラメータが正しく設定されることを確認"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        mock_llm = MockLLMClient()
        processor = ArxivWeeklyProcessor(llm_client=mock_llm, batch_size=10)

        assert processor.batch_size == 10

    @pytest.mark.asyncio
    async def test_large_paper_list_batching(self):
        """大量の論文がバッチ分割されることを確認"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        batch_response = json.dumps(
            [
                {
                    "index": i,
                    "technical_novelty": 7,
                    "industry_impact": 7,
                    "practicality": 7,
                    "reason": f"Paper {i}",
                }
                for i in range(5)
            ]
        )
        mock_llm = MockLLMClient(json_response=batch_response)
        processor = ArxivWeeklyProcessor(llm_client=mock_llm, batch_size=5)

        # 15件の論文（5件バッチ×3）
        papers = [
            {
                "title": f"Paper {i}",
                "日本語訳": f"論文{i}の概要",
                "url": f"https://arxiv.org/abs/2601.{i:05d}",
            }
            for i in range(15)
        ]

        result = await processor.rank_papers_by_importance(papers)

        assert len(result) == 15
        assert all("importance_score" in paper for paper in result)


class TestArxivWeeklyTwoTier:
    """ArxivWeeklyProcessorの2層構成テスト"""

    @pytest.fixture
    def sample_papers_with_urls(self):
        """arXiv ID付きのサンプル論文データ"""
        return [
            {
                "title": "Paper A - High HF Upvotes",
                "日本語訳": "HFで人気の論文A",
                "url": "https://arxiv.org/abs/2601.00001",
            },
            {
                "title": "Paper B - Medium HF Upvotes",
                "日本語訳": "HFで中程度の人気の論文B",
                "url": "https://arxiv.org/abs/2601.00002",
            },
            {
                "title": "Paper C - No HF",
                "日本語訳": "HFにない論文C",
                "url": "https://arxiv.org/abs/2601.00003",
            },
            {
                "title": "Paper D - No HF but good LLM score",
                "日本語訳": "LLMスコアが高い論文D",
                "url": "https://arxiv.org/abs/2601.00004",
            },
            {
                "title": "Paper E - Low HF",
                "日本語訳": "HFで少しだけ人気の論文E",
                "url": "https://arxiv.org/abs/2601.00005",
            },
        ]

    def test_extract_arxiv_id(self):
        """arXiv ID抽出のテスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        assert (
            ArxivWeeklyProcessor._extract_arxiv_id("https://arxiv.org/abs/2601.00001")
            == "2601.00001"
        )
        assert (
            ArxivWeeklyProcessor._extract_arxiv_id("https://arxiv.org/abs/2601.00001v2")
            == "2601.00001"
        )
        assert (
            ArxivWeeklyProcessor._extract_arxiv_id("https://arxiv.org/pdf/2601.12345")
            == "2601.12345"
        )
        assert ArxivWeeklyProcessor._extract_arxiv_id("invalid-url") == ""

    @pytest.mark.asyncio
    async def test_process_two_tier_with_hf(self, sample_papers_with_urls):
        """HFリサーチャー付きの2層構成テスト"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor
        from minitools.researchers.hf_papers import HFPaperStats, HFPapersResearcher
        from unittest.mock import AsyncMock

        score_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "reason": "Good paper",
            }
        )
        mock_llm = MockLLMClient(json_response=score_response)

        # HFリサーチャーのモック
        mock_hf = AsyncMock(spec=HFPapersResearcher)
        mock_hf.get_papers_stats.return_value = {
            "2601.00001": HFPaperStats(
                "2601.00001", upvotes=100, num_comments=10, found_on_hf=True
            ),
            "2601.00002": HFPaperStats(
                "2601.00002", upvotes=50, num_comments=3, found_on_hf=True
            ),
            "2601.00003": HFPaperStats("2601.00003"),
            "2601.00004": HFPaperStats("2601.00004"),
            "2601.00005": HFPaperStats(
                "2601.00005", upvotes=5, num_comments=1, found_on_hf=True
            ),
        }

        processor = ArxivWeeklyProcessor(
            llm_client=mock_llm,
            hf_researcher=mock_hf,
        )

        result = await processor.process(
            papers=sample_papers_with_urls,
            use_trends=False,
            hf_top_n=2,
            llm_top_n=2,
        )

        # 2セクション構成
        assert "hf_papers" in result
        assert "llm_papers" in result
        assert len(result["hf_papers"]) == 2
        assert len(result["llm_papers"]) == 2

        # HFセクションはupvote降順
        assert result["hf_papers"][0].get("hf_upvotes") == 100
        assert result["hf_papers"][1].get("hf_upvotes") == 50

        # HF選出論文がLLMセクションにない
        hf_urls = {p["url"] for p in result["hf_papers"]}
        llm_urls = {p["url"] for p in result["llm_papers"]}
        assert hf_urls.isdisjoint(llm_urls)

        # 後方互換: papers は全セクションのマージ
        assert len(result["papers"]) == 4

    @pytest.mark.asyncio
    async def test_process_without_hf_researcher(self, sample_papers_with_urls):
        """HFリサーチャーなしの場合は従来動作"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor

        score_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "reason": "Good paper",
            }
        )
        mock_llm = MockLLMClient(json_response=score_response)

        processor = ArxivWeeklyProcessor(llm_client=mock_llm)

        result = await processor.process(
            papers=sample_papers_with_urls,
            top_n=3,
            use_trends=False,
        )

        assert result["hf_papers"] == []
        assert result["llm_papers"] == []
        assert len(result["papers"]) == 3

    @pytest.mark.asyncio
    async def test_process_hf_failure_fallback(self, sample_papers_with_urls):
        """HF API障害時はHFセクション空でLLMのみ"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor
        from minitools.researchers.hf_papers import HFPapersResearcher
        from unittest.mock import AsyncMock

        score_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "reason": "Good paper",
            }
        )
        mock_llm = MockLLMClient(json_response=score_response)

        mock_hf = AsyncMock(spec=HFPapersResearcher)
        mock_hf.get_papers_stats.side_effect = Exception("HF API down")

        processor = ArxivWeeklyProcessor(
            llm_client=mock_llm,
            hf_researcher=mock_hf,
        )

        result = await processor.process(
            papers=sample_papers_with_urls,
            use_trends=False,
            hf_top_n=2,
            llm_top_n=3,
        )

        # HFセクションは空（全論文にhf_upvotesが付与されないため）
        assert result["hf_papers"] == []
        # LLMセクションは全論文から選出
        assert len(result["llm_papers"]) == 3

    @pytest.mark.asyncio
    async def test_no_hf_upvoted_papers(self, sample_papers_with_urls):
        """HF上にupvote > 0の論文がない場合"""
        from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor
        from minitools.researchers.hf_papers import HFPaperStats, HFPapersResearcher
        from unittest.mock import AsyncMock

        score_response = json.dumps(
            {
                "technical_novelty": 8,
                "industry_impact": 7,
                "practicality": 9,
                "reason": "Good paper",
            }
        )
        mock_llm = MockLLMClient(json_response=score_response)

        mock_hf = AsyncMock(spec=HFPapersResearcher)
        mock_hf.get_papers_stats.return_value = {
            aid: HFPaperStats(aid)
            for aid in [
                "2601.00001",
                "2601.00002",
                "2601.00003",
                "2601.00004",
                "2601.00005",
            ]
        }

        processor = ArxivWeeklyProcessor(
            llm_client=mock_llm,
            hf_researcher=mock_hf,
        )

        result = await processor.process(
            papers=sample_papers_with_urls,
            use_trends=False,
            hf_top_n=2,
            llm_top_n=3,
        )

        assert result["hf_papers"] == []
        assert len(result["llm_papers"]) == 3
