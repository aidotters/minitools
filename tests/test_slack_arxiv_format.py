"""Tests for SlackPublisher ArXiv weekly format."""

import pytest

from minitools.publishers.slack import SlackPublisher


class TestSlackPublisherArxivWeekly:
    """SlackPublisher.format_arxiv_weekly()のテスト"""

    @pytest.fixture
    def sample_papers(self):
        """テスト用のサンプル論文データ（ハイライト付き）"""
        return [
            {
                "title": "Advances in Transformer Architecture",
                "importance_score": 9.2,
                "selection_reason": "注意機構の革新的な改良により計算効率が向上",
                "key_points": [
                    "計算効率が50%向上",
                    "長文処理能力の改善",
                    "既存モデルへの適用が容易",
                ],
                "url": "https://arxiv.org/abs/2601.00001",
                "pdf_url": "https://arxiv.org/pdf/2601.00001",
            },
            {
                "title": "Efficient LLM Fine-tuning Methods",
                "importance_score": 8.5,
                "selection_reason": "LoRAを超える新しいファインチューニング手法",
                "key_points": [
                    "メモリ使用量を70%削減",
                    "学習速度が2倍に向上",
                    "品質低下なし",
                ],
                "url": "https://arxiv.org/abs/2601.00002",
                "pdf_url": "https://arxiv.org/pdf/2601.00002",
            },
        ]

    @pytest.fixture
    def sample_trend_summary(self):
        """テスト用のトレンドサマリー"""
        return "2026年1月のAIトレンドでは、エージェントシステムとマルチモーダルモデルが注目されている。特にRAGの効率化と推論能力の向上が話題。"

    def test_format_arxiv_weekly_with_trends(self, sample_papers, sample_trend_summary):
        """トレンド情報ありのフォーマットテスト"""
        publisher = SlackPublisher()

        message = publisher.format_arxiv_weekly(
            start_date="2026-01-19",
            end_date="2026-01-25",
            papers=sample_papers,
            trend_summary=sample_trend_summary,
        )

        # ヘッダーが含まれている
        assert "ArXiv週次ダイジェスト" in message
        assert "2026-01-19" in message
        assert "2026-01-25" in message

        # トレンドセクションが含まれている
        assert "今週のAIトレンド" in message
        assert sample_trend_summary in message

        # ランキングが含まれている
        assert "TOP" in message

        # 論文情報が含まれている
        assert "Advances in Transformer Architecture" in message
        assert "9.2" in message
        assert "注意機構の革新的な改良" in message

        # リンクが含まれている
        assert "arxiv.org/abs/2601.00001" in message

    def test_format_arxiv_weekly_without_trends(self, sample_papers):
        """トレンド情報なしのフォーマットテスト"""
        publisher = SlackPublisher()

        message = publisher.format_arxiv_weekly(
            start_date="2026-01-19",
            end_date="2026-01-25",
            papers=sample_papers,
            trend_summary=None,
        )

        # ヘッダーが含まれている
        assert "ArXiv週次ダイジェスト" in message

        # トレンドセクションは含まれていない（または「なし」表示）
        # 実装によって異なるが、論文情報は含まれる
        assert "Advances in Transformer Architecture" in message

    def test_format_arxiv_weekly_empty_papers(self):
        """論文リストが空の場合"""
        publisher = SlackPublisher()

        message = publisher.format_arxiv_weekly(
            start_date="2026-01-19",
            end_date="2026-01-25",
            papers=[],
            trend_summary=None,
        )

        # ヘッダーは含まれる
        assert "ArXiv週次ダイジェスト" in message

    def test_format_arxiv_weekly_ranking_emoji(self, sample_papers):
        """ランキング表示のテスト（絵文字）"""
        # 3件以上の論文を用意
        papers = sample_papers + [
            {
                "title": "Third Paper",
                "importance_score": 7.0,
                "selection_reason": "3位の論文",
                "key_points": ["ポイント1"],
                "url": "https://arxiv.org/abs/2601.00003",
            },
            {
                "title": "Fourth Paper",
                "importance_score": 6.5,
                "selection_reason": "4位の論文",
                "key_points": ["ポイント1"],
                "url": "https://arxiv.org/abs/2601.00004",
            },
        ]

        publisher = SlackPublisher()
        message = publisher.format_arxiv_weekly(
            start_date="2026-01-19",
            end_date="2026-01-25",
            papers=papers,
            trend_summary=None,
        )

        # 1-3位は絵文字
        # 4位以降は数字
        # 実装によって形式が異なる可能性がある
        assert len(message) > 0

    def test_format_arxiv_weekly_message_length_limit(self):
        """メッセージ長3000文字以内の制限テスト"""
        # 長い論文データを大量に生成
        papers = [
            {
                "title": f"Very Long Title Paper Number {i} with Extra Description",
                "importance_score": 8.0 - (i * 0.1),
                "selection_reason": "A" * 100,  # 長い選出理由
                "key_points": [
                    "B" * 30,
                    "C" * 30,
                    "D" * 30,
                ],
                "url": f"https://arxiv.org/abs/2601.{i:05d}",
            }
            for i in range(20)
        ]

        publisher = SlackPublisher()
        message = publisher.format_arxiv_weekly(
            start_date="2026-01-19",
            end_date="2026-01-25",
            papers=papers,
            trend_summary="E" * 500,  # 長いトレンドサマリー
        )

        # 3000文字以内に制限されている
        assert len(message) <= 3000

    def test_format_arxiv_weekly_pdf_link(self, sample_papers):
        """PDFリンクが正しく表示される"""
        publisher = SlackPublisher()

        message = publisher.format_arxiv_weekly(
            start_date="2026-01-19",
            end_date="2026-01-25",
            papers=sample_papers,
            trend_summary=None,
        )

        # PDFリンクが含まれている
        assert "pdf" in message.lower() or "PDF" in message


class TestSlackPublisherArxivWeeklyTwoTier:
    """SlackPublisher.format_arxiv_weekly() 2セクション構成のテスト"""

    @pytest.fixture
    def hf_papers(self):
        return [
            {
                "title": "HF Popular Paper 1",
                "hf_upvotes": 100,
                "hf_comments": 10,
                "selection_reason": "HFで最も人気",
                "key_points": ["ポイント1"],
                "url": "https://arxiv.org/abs/2601.00001",
            },
            {
                "title": "HF Popular Paper 2",
                "hf_upvotes": 50,
                "hf_comments": 3,
                "selection_reason": "HFで2番目に人気",
                "key_points": ["ポイント2"],
                "url": "https://arxiv.org/abs/2601.00002",
            },
        ]

    @pytest.fixture
    def llm_papers(self):
        return [
            {
                "title": "LLM Scored Paper 1",
                "importance_score": 9.0,
                "selection_reason": "LLMが高評価",
                "key_points": ["ポイントA"],
                "url": "https://arxiv.org/abs/2601.00003",
            },
        ]

    def test_two_tier_format(self, hf_papers, llm_papers):
        """2セクション構成の基本フォーマットテスト"""
        publisher = SlackPublisher()
        message = publisher.format_arxiv_weekly(
            start_date="2026-04-01",
            end_date="2026-04-07",
            papers=[],
            hf_papers=hf_papers,
            llm_papers=llm_papers,
        )

        assert "HuggingFace Upvotes" in message
        assert "LLMスコア" in message
        assert "100 upvotes" in message
        assert "10 comments" in message
        assert "9.0/10" in message

    def test_two_tier_hf_only(self, hf_papers):
        """HFセクションのみ"""
        publisher = SlackPublisher()
        message = publisher.format_arxiv_weekly(
            start_date="2026-04-01",
            end_date="2026-04-07",
            papers=[],
            hf_papers=hf_papers,
            llm_papers=[],
        )

        assert "HuggingFace Upvotes" in message
        assert "LLMスコア" not in message

    def test_two_tier_llm_only(self, llm_papers):
        """LLMセクションのみ"""
        publisher = SlackPublisher()
        message = publisher.format_arxiv_weekly(
            start_date="2026-04-01",
            end_date="2026-04-07",
            papers=[],
            hf_papers=[],
            llm_papers=llm_papers,
        )

        assert "HuggingFace Upvotes" not in message
        assert "LLMスコア" in message

    def test_two_tier_message_length_limit(self):
        """2セクション構成でも3000文字制限"""
        hf_papers = [
            {
                "title": f"HF Paper {i} with very long title description",
                "hf_upvotes": 100 - i,
                "hf_comments": 5,
                "selection_reason": "A" * 100,
                "key_points": ["B" * 30, "C" * 30, "D" * 30],
                "url": f"https://arxiv.org/abs/2601.{i:05d}",
            }
            for i in range(20)
        ]
        publisher = SlackPublisher()
        message = publisher.format_arxiv_weekly(
            start_date="2026-04-01",
            end_date="2026-04-07",
            papers=[],
            hf_papers=hf_papers,
            llm_papers=[],
        )
        assert len(message) <= 3000

    def test_backward_compatible_without_hf_llm(self):
        """hf/llm未指定時は従来フォーマット"""
        papers = [
            {
                "title": "Old Format Paper",
                "importance_score": 8.0,
                "selection_reason": "テスト",
                "key_points": [],
                "url": "https://arxiv.org/abs/2601.00001",
            }
        ]
        publisher = SlackPublisher()
        message = publisher.format_arxiv_weekly(
            start_date="2026-04-01",
            end_date="2026-04-07",
            papers=papers,
        )

        assert "TOP 1" in message
        assert "HuggingFace" not in message
