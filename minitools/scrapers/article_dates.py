"""記事の元日付（公開日 / 更新日）抽出ロジック（Playwright 非依存・単体テスト可能）。

Medium 等の記事ページから取得した構造化シグナル（JSON-LD / OpenGraph meta）を
``published_at`` / ``last_modified``（``YYYY-MM-DD``）へ正規化する純関数群。

出所（source）は llm-wiki Phase 5 の出所 enum に合わせ、構造化 head メタ由来は
``html-meta``、取得不能は ``unknown`` とする。

設計メモ（実機検証 2026-06-12 で確定）:
    - **JSON-LD（``SocialMediaPosting`` の ``datePublished`` / ``dateModified``）を正本**とする。
    - OpenGraph ``<meta property="article:published_time">`` は published の信頼ソースにならない
      （更新時刻を指すケースを実測）ため、JSON-LD 欠落時の補助フォールバックに限定する。
"""

import re
from datetime import datetime
from typing import Optional, TypedDict


class ArticleDates(TypedDict):
    """記事の元日付メタ（llm-wiki raw フロントマター 4 フィールドに対応）。"""

    published_at: Optional[str]  # YYYY-MM-DD or None
    last_modified: Optional[str]  # YYYY-MM-DD or None
    published_at_source: str  # "html-meta" | "unknown"
    last_modified_source: str  # "html-meta" | "unknown"


def empty_dates() -> ArticleDates:
    """未取得状態の ``ArticleDates``。"""
    return ArticleDates(
        published_at=None,
        last_modified=None,
        published_at_source="unknown",
        last_modified_source="unknown",
    )


def normalize_iso_date(value: Optional[str]) -> Optional[str]:
    """ISO 8601 文字列を ``YYYY-MM-DD`` に整形する。失敗時は ``None``。"""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    candidates = [value]
    if value.endswith("Z"):
        candidates.append(value[:-1] + "+00:00")

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # 単純な YYYY-MM-DD プレフィックスにフォールバック
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
    if match:
        return match.group(1)

    return None


def extract_dates_from_signals(
    jsonld_pairs: list[dict],
    og_published: Optional[str] = None,
    og_modified: Optional[str] = None,
) -> ArticleDates:
    """構造化シグナルから ``published_at`` / ``last_modified`` を決定する。

    Args:
        jsonld_pairs: JSON-LD から抽出した ``{"datePublished", "dateModified"}`` の配列。
            ページ DOM から収集する（``@graph`` / 配列は呼び出し側で平坦化済みを想定）。
        og_published: OpenGraph ``article:published_time`` の content（補助フォールバック）。
        og_modified: OpenGraph ``article:modified_time`` の content（補助フォールバック）。

    Returns:
        正規化済みの ``ArticleDates``。JSON-LD を優先し、欠落時のみ Og にフォールバック。
        いずれも取れなければ ``None`` ＋ source ``unknown``。
    """
    published_raw: Optional[str] = None
    modified_raw: Optional[str] = None

    # JSON-LD を正本として最初に見つかった値を採用する
    for pair in jsonld_pairs or []:
        if not isinstance(pair, dict):
            continue
        if published_raw is None and pair.get("datePublished"):
            published_raw = pair["datePublished"]
        if modified_raw is None and pair.get("dateModified"):
            modified_raw = pair["dateModified"]
        if published_raw and modified_raw:
            break

    # JSON-LD 欠落時のみ OpenGraph meta にフォールバック（補助）
    if published_raw is None and og_published:
        published_raw = og_published
    if modified_raw is None and og_modified:
        modified_raw = og_modified

    published_at = normalize_iso_date(published_raw)
    last_modified = normalize_iso_date(modified_raw)

    return ArticleDates(
        published_at=published_at,
        last_modified=last_modified,
        published_at_source="html-meta" if published_at else "unknown",
        last_modified_source="html-meta" if last_modified else "unknown",
    )
