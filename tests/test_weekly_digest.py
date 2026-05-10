"""Tests for WeeklyDigestProcessor."""

import json
import pytest

from minitools.processors.weekly_digest import (
    DigestProcessor,
    WeeklyDigestProcessor,
)
from tests.conftest import MockLLMClient, MockEmbeddingClient


def test_digest_processor_alias():
    """WeeklyDigestProcessor は DigestProcessor のエイリアスである"""
    assert WeeklyDigestProcessor is DigestProcessor


@pytest.mark.asyncio
async def test_summarize_all_articles_empty():
    mock_llm = MockLLMClient()
    processor = DigestProcessor(llm_client=mock_llm)
    result = await processor.summarize_all_articles([])
    assert result == ""
    assert len(mock_llm.generate_calls) == 0


@pytest.mark.asyncio
async def test_summarize_all_articles_single_chunk():
    """件数が chunk_size 以下の場合、LLM 1回呼び出し"""
    mock_llm = MockLLMClient(chat_response="本日のサマリ。")
    processor = DigestProcessor(llm_client=mock_llm)
    articles = [{"title": f"Article {i}", "summary": f"summary {i}"} for i in range(5)]
    result = await processor.summarize_all_articles(articles, chunk_size=50)
    assert result == "本日のサマリ。"
    assert len(mock_llm.generate_calls) == 1


@pytest.mark.asyncio
async def test_summarize_all_articles_two_stage():
    """件数が chunk_size 超のとき2段階要約"""
    mock_llm = MockLLMClient(chat_response="統合サマリ")
    processor = DigestProcessor(llm_client=mock_llm)
    articles = [{"title": f"A{i}", "summary": f"s{i}"} for i in range(7)]
    result = await processor.summarize_all_articles(articles, chunk_size=3)
    assert result == "統合サマリ"
    # 3チャンク（3+3+1）の部分要約 + 1回の統合 = 4回
    assert len(mock_llm.generate_calls) == 4


@pytest.mark.asyncio
async def test_summarize_all_articles_llm_failure_returns_empty():
    """LLM 失敗時は空文字を返し、例外を伝播しない"""
    from minitools.llm.base import LLMError

    class FailingLLM(MockLLMClient):
        async def generate(self, prompt, model=None):
            raise LLMError("simulated failure")

    processor = DigestProcessor(llm_client=FailingLLM())
    result = await processor.summarize_all_articles([{"title": "x", "summary": "y"}])
    assert result == ""


@pytest.mark.asyncio
async def test_rank_articles_by_importance_basic(sample_articles):
    """基本的なスコアリングテスト"""
    # JSONレスポンスを設定
    json_response = json.dumps(
        {
            "technical_impact": 8,
            "industry_impact": 7,
            "trending": 9,
            "novelty": 8,
            "reason": "Major release announcement",
        }
    )
    mock_llm = MockLLMClient(json_response=json_response)
    processor = WeeklyDigestProcessor(llm_client=mock_llm)

    result = await processor.rank_articles_by_importance(sample_articles)

    assert len(result) == len(sample_articles)
    assert all("importance_score" in article for article in result)
    # 平均スコア: (8+7+9+8)/4 = 8.0
    assert result[0]["importance_score"] == 8.0


@pytest.mark.asyncio
async def test_rank_articles_by_importance_empty_list():
    """空リストの場合のテスト"""
    mock_llm = MockLLMClient()
    processor = WeeklyDigestProcessor(llm_client=mock_llm)

    result = await processor.rank_articles_by_importance([])

    assert result == []


@pytest.mark.asyncio
async def test_rank_articles_by_importance_no_title():
    """タイトルなし記事のテスト"""
    mock_llm = MockLLMClient()
    processor = WeeklyDigestProcessor(llm_client=mock_llm)
    articles = [{"id": "1", "summary": "Some summary without title"}]

    result = await processor.rank_articles_by_importance(articles)

    assert len(result) == 1
    assert result[0]["importance_score"] == 0
    assert result[0]["score_reason"] == "タイトルなし"


@pytest.mark.asyncio
async def test_rank_articles_by_importance_invalid_json():
    """不正なJSONレスポンスの場合のテスト"""
    mock_llm = MockLLMClient(json_response="not valid json")
    processor = WeeklyDigestProcessor(llm_client=mock_llm)
    articles = [{"title": "Test Article", "summary": "Test summary"}]

    result = await processor.rank_articles_by_importance(articles)

    assert len(result) == 1
    # JSONパース失敗時はデフォルトスコア5
    assert result[0]["importance_score"] == 5
    assert result[0]["score_reason"] == "スコアリング失敗"


@pytest.mark.asyncio
async def test_select_top_articles_without_dedup(scored_articles):
    """重複除去なしでの上位記事選出テスト"""
    mock_llm = MockLLMClient()
    processor = WeeklyDigestProcessor(llm_client=mock_llm)

    result = await processor.select_top_articles(
        scored_articles, top_n=3, deduplicate=False
    )

    assert len(result) == 3
    # スコア降順: 9.0, 8.5, 7.2
    assert result[0]["importance_score"] == 9.0
    assert result[1]["importance_score"] == 8.5
    assert result[2]["importance_score"] == 7.2


@pytest.mark.asyncio
async def test_select_top_articles_empty_list():
    """空リストの場合のテスト"""
    mock_llm = MockLLMClient()
    processor = WeeklyDigestProcessor(llm_client=mock_llm)

    result = await processor.select_top_articles([], top_n=5, deduplicate=False)

    assert result == []


@pytest.mark.asyncio
async def test_generate_trend_summary_basic(scored_articles):
    """トレンド総括生成の基本テスト"""
    expected_summary = "今週のAI分野では、大手企業による新モデルの発表が相次ぎました。"
    mock_llm = MockLLMClient(chat_response=expected_summary)
    processor = WeeklyDigestProcessor(llm_client=mock_llm)

    result = await processor.generate_trend_summary(scored_articles)

    assert result == expected_summary
    assert len(mock_llm.generate_calls) == 1


@pytest.mark.asyncio
async def test_generate_trend_summary_empty_list():
    """空リストの場合のトレンド総括テスト"""
    mock_llm = MockLLMClient()
    processor = WeeklyDigestProcessor(llm_client=mock_llm)

    result = await processor.generate_trend_summary([])

    assert result == "今週は特筆すべきニュースがありませんでした。"


@pytest.mark.asyncio
async def test_generate_article_summaries_basic(scored_articles):
    """記事要約生成の基本テスト"""
    expected_summary = "AIの新技術に関する重要な発表です。"
    mock_llm = MockLLMClient(chat_response=expected_summary)
    processor = WeeklyDigestProcessor(llm_client=mock_llm)

    result = await processor.generate_article_summaries(scored_articles[:2])

    assert len(result) == 2
    assert all("digest_summary" in article for article in result)
    assert result[0]["digest_summary"] == expected_summary


@pytest.mark.asyncio
async def test_generate_article_summaries_with_existing_japanese_summary():
    """既存の日本語要約がある場合のテスト"""
    mock_llm = MockLLMClient()
    processor = WeeklyDigestProcessor(llm_client=mock_llm)
    articles = [
        {
            "title": "Test Article",
            "summary": "English summary",
            "japanese_summary": "既存の日本語要約",
        }
    ]

    result = await processor.generate_article_summaries(articles)

    assert len(result) == 1
    assert result[0]["digest_summary"] == "既存の日本語要約"
    # LLMは呼び出されない
    assert len(mock_llm.generate_calls) == 0


@pytest.mark.asyncio
async def test_generate_article_summaries_empty_list():
    """空リストの場合の要約生成テスト"""
    mock_llm = MockLLMClient()
    processor = WeeklyDigestProcessor(llm_client=mock_llm)

    result = await processor.generate_article_summaries([])

    assert result == []


@pytest.mark.asyncio
async def test_process_full_pipeline(sample_articles):
    """全パイプラインの統合テスト"""
    score_response = json.dumps(
        {
            "technical_impact": 8,
            "industry_impact": 7,
            "trending": 8,
            "novelty": 7,
            "reason": "Significant update",
        }
    )
    summary_response = "今週はAI分野で重要な発表がありました。"

    mock_llm = MockLLMClient(
        chat_response=summary_response, json_response=score_response
    )
    mock_embedding = MockEmbeddingClient()
    processor = WeeklyDigestProcessor(
        llm_client=mock_llm, embedding_client=mock_embedding
    )

    result = await processor.process(
        articles=sample_articles,
        top_n=3,
        deduplicate=False,  # 重複除去なしでテスト
    )

    assert "trend_summary" in result
    assert "top_articles" in result
    assert "total_articles" in result
    assert result["total_articles"] == len(sample_articles)
    assert len(result["top_articles"]) <= 3


@pytest.mark.asyncio
async def test_processor_concurrent_limit():
    """並列処理の制限が機能していることを確認"""
    mock_llm = MockLLMClient(
        json_response=json.dumps(
            {
                "technical_impact": 5,
                "industry_impact": 5,
                "trending": 5,
                "novelty": 5,
                "reason": "Test",
            }
        )
    )
    processor = WeeklyDigestProcessor(llm_client=mock_llm, max_concurrent=2)

    # 10件の記事を処理
    articles = [{"title": f"Article {i}", "summary": f"Summary {i}"} for i in range(10)]

    result = await processor.rank_articles_by_importance(articles)

    assert len(result) == 10
    # 全記事がスコアリングされていることを確認
    assert all("importance_score" in article for article in result)


# ============================================
# バッチスコアリング機能のテスト
# ============================================


class TestBatchScoring:
    """バッチスコアリング機能のテスト"""

    @pytest.mark.asyncio
    async def test_score_batch_success(self, sample_articles):
        """バッチスコアリングの正常系テスト"""
        # バッチ用JSONレスポンス（複数記事分）
        batch_response = json.dumps(
            [
                {
                    "index": 0,
                    "technical_impact": 8,
                    "industry_impact": 7,
                    "trending": 9,
                    "novelty": 8,
                    "reason": "Major release",
                },
                {
                    "index": 1,
                    "technical_impact": 7,
                    "industry_impact": 6,
                    "trending": 8,
                    "novelty": 7,
                    "reason": "Significant update",
                },
            ]
        )
        mock_llm = MockLLMClient(json_response=batch_response)
        processor = WeeklyDigestProcessor(llm_client=mock_llm, batch_size=20)

        # _score_batchメソッドが存在する場合のみテスト
        if hasattr(processor, "_score_batch"):
            result = await processor._score_batch(sample_articles[:2])
            assert len(result) == 2
            assert all("importance_score" in article for article in result)

    @pytest.mark.asyncio
    async def test_score_batch_json_parse_error_raises(self, sample_articles):
        """バッチJSONパースエラー時に例外が発生することを確認"""
        import json as json_module

        # 不正なJSONレスポンス
        mock_llm = MockLLMClient(json_response="invalid json for batch")
        processor = WeeklyDigestProcessor(llm_client=mock_llm, batch_size=20)

        # _score_batch は例外を上げる（フォールバックは rank_articles_by_importance で行う）
        if hasattr(processor, "_score_batch"):
            with pytest.raises(json_module.JSONDecodeError):
                await processor._score_batch(sample_articles[:2])

    @pytest.mark.asyncio
    async def test_batch_processing_in_rank_articles(self, sample_articles):
        """rank_articles_by_importanceでバッチ処理が動作することを確認"""
        batch_response = json.dumps(
            [
                {
                    "index": i,
                    "technical_impact": 8,
                    "industry_impact": 7,
                    "trending": 8,
                    "novelty": 7,
                    "reason": f"Article {i} evaluation",
                }
                for i in range(len(sample_articles))
            ]
        )
        mock_llm = MockLLMClient(json_response=batch_response)
        processor = WeeklyDigestProcessor(llm_client=mock_llm, batch_size=20)

        result = await processor.rank_articles_by_importance(sample_articles)

        assert len(result) == len(sample_articles)
        assert all("importance_score" in article for article in result)

    @pytest.mark.asyncio
    async def test_batch_size_splitting(self):
        """バッチサイズに応じた分割テスト"""
        batch_response = json.dumps(
            [
                {
                    "index": i,
                    "technical_impact": 7,
                    "industry_impact": 7,
                    "trending": 7,
                    "novelty": 7,
                    "reason": f"Test {i}",
                }
                for i in range(3)
            ]
        )
        mock_llm = MockLLMClient(json_response=batch_response)
        processor = WeeklyDigestProcessor(llm_client=mock_llm, batch_size=3)

        # 10件の記事（3件バッチ×3 + 1件バッチ）
        articles = [
            {"title": f"Article {i}", "summary": f"Summary {i}"} for i in range(10)
        ]

        result = await processor.rank_articles_by_importance(articles)

        assert len(result) == 10
        assert all("importance_score" in article for article in result)

    @pytest.mark.asyncio
    async def test_score_single_fallback(self):
        """個別スコアリング（フォールバック）のテスト"""
        single_response = json.dumps(
            {
                "technical_impact": 8,
                "industry_impact": 7,
                "trending": 9,
                "novelty": 8,
                "reason": "Important article",
            }
        )
        mock_llm = MockLLMClient(json_response=single_response)
        processor = WeeklyDigestProcessor(llm_client=mock_llm, batch_size=20)

        # _score_singleメソッドが存在する場合のみテスト
        if hasattr(processor, "_score_single"):
            article = {"title": "Test Article", "summary": "Test summary"}
            result = await processor._score_single(article)
            assert "importance_score" in result
            assert result["importance_score"] == 8.0  # (8+7+9+8)/4

    @pytest.mark.asyncio
    async def test_partial_batch_failure_continues(self):
        """バッチ処理の部分失敗時に処理が継続することを確認"""
        # バッチは失敗するが、個別処理でフォールバック
        mock_llm = MockLLMClient(json_response="invalid")
        processor = WeeklyDigestProcessor(llm_client=mock_llm, batch_size=20)

        articles = [
            {"title": f"Article {i}", "summary": f"Summary {i}"} for i in range(5)
        ]

        result = await processor.rank_articles_by_importance(articles)

        # 失敗してもデフォルトスコアで処理が完了する
        assert len(result) == 5
        assert all("importance_score" in article for article in result)
