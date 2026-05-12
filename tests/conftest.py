"""Pytest configuration and fixtures for minitools tests."""

import pytest
from typing import Any, Dict, List, Optional

from minitools.llm.base import BaseLLMClient
from minitools.llm.embeddings import BaseEmbeddingClient


class MockLLMClient(BaseLLMClient):
    """LLMクライアントのモック実装"""

    def __init__(
        self,
        chat_response: str = "mock response",
        json_response: str = '{"key": "value"}',
    ):
        self.chat_response = chat_response
        self.json_response = json_response
        self.chat_calls: List[Dict[str, Any]] = []
        self.generate_calls: List[Dict[str, Any]] = []

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        self.chat_calls.append({"messages": messages, "model": model})
        return self.chat_response

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        self.generate_calls.append({"prompt": prompt, "model": model})
        return self.chat_response

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        self.chat_calls.append({"messages": messages, "model": model, "json": True})
        return self.json_response


class MockEmbeddingClient(BaseEmbeddingClient):
    """Embeddingクライアントのモック実装"""

    def __init__(self, embedding_dim: int = 768):
        self.embedding_dim = embedding_dim
        self.embed_texts_calls: List[List[str]] = []
        self.embed_text_calls: List[str] = []

    def _generate_embedding(self, text: str, index: int = 0) -> List[float]:
        """テキストから擬似的なembeddingを生成（異なるテキストは異なるembeddingになる）

        高次元の独立Gauss乱数ベクトルは期待的にほぼ直交（cosine類似度 ~ 1/√d）になるため、
        異なるテキストは閾値0.95を確実に下回り、同一テキストは完全一致する。
        hashlibで決定論的にシードするため、Pythonのhash randomizationの影響を受けない。
        """
        import hashlib
        import math
        import random

        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        embedding = [rng.gauss(0.0, 1.0) for _ in range(self.embedding_dim)]

        norm = math.sqrt(sum(v * v for v in embedding))
        if norm > 0:
            embedding = [v / norm for v in embedding]

        return embedding

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        self.embed_texts_calls.append(texts)
        # 各テキストに対して異なるembeddingを生成（テスト用）
        embeddings = []
        for i, text in enumerate(texts):
            embedding = self._generate_embedding(text, i)
            embeddings.append(embedding)
        return embeddings

    async def embed_text(self, text: str) -> List[float]:
        self.embed_text_calls.append(text)
        return self._generate_embedding(text)


@pytest.fixture
def mock_llm_client():
    """デフォルトのモックLLMクライアントを提供"""
    return MockLLMClient()


@pytest.fixture
def mock_embedding_client():
    """デフォルトのモックEmbeddingクライアントを提供"""
    return MockEmbeddingClient()


@pytest.fixture
def sample_articles():
    """テスト用のサンプル記事データを提供"""
    return [
        {
            "id": "1",
            "title": "OpenAI releases GPT-5",
            "summary": "OpenAI has announced the release of GPT-5, their latest language model.",
            "url": "https://example.com/article1",
            "date": "2024-01-15",
        },
        {
            "id": "2",
            "title": "Google announces Gemini 2.0",
            "summary": "Google has unveiled Gemini 2.0 with improved capabilities.",
            "url": "https://example.com/article2",
            "date": "2024-01-14",
        },
        {
            "id": "3",
            "title": "Anthropic Claude 4 Launch",
            "summary": "Anthropic launched Claude 4 with enhanced reasoning abilities.",
            "url": "https://example.com/article3",
            "date": "2024-01-13",
        },
        {
            "id": "4",
            "title": "OpenAI GPT-5 Details Revealed",  # Similar to article 1
            "summary": "More details about the GPT-5 release from OpenAI.",
            "url": "https://example.com/article4",
            "date": "2024-01-15",
        },
        {
            "id": "5",
            "title": "Microsoft Azure AI Updates",
            "summary": "Microsoft updates Azure AI services with new features.",
            "url": "https://example.com/article5",
            "date": "2024-01-12",
        },
    ]


@pytest.fixture
def scored_articles(sample_articles):
    """importance_scoreが付与されたサンプル記事"""
    scores = [8.5, 7.2, 9.0, 6.5, 5.8]
    for article, score in zip(sample_articles, scores):
        article["importance_score"] = score
    return sample_articles
