"""
Content processors for translation and summarization.
"""

from minitools.processors.translator import Translator
from minitools.processors.summarizer import Summarizer
from minitools.processors.weekly_digest import (
    DigestProcessor,
    WeeklyDigestProcessor,
)
from minitools.processors.duplicate_detector import (
    DuplicateDetector,
    deduplicate_articles,
)
from minitools.processors.arxiv_weekly import ArxivWeeklyProcessor
from minitools.processors.full_text_translator import FullTextTranslator
from minitools.processors.x_trend import XTrendProcessor

__all__ = [
    "Translator",
    "Summarizer",
    "DigestProcessor",
    "WeeklyDigestProcessor",
    "DuplicateDetector",
    "deduplicate_articles",
    "ArxivWeeklyProcessor",
    "FullTextTranslator",
    "XTrendProcessor",
]
