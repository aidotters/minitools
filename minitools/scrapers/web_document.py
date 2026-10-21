"""
Generic web document helpers for full-text translation.

Converts arbitrary technical web pages (e.g. Sphinx-generated textbooks such as
d2l.ai) into Markdown that ``FullTextTranslator`` / ``NotionBlockBuilder`` can
consume, and derives filesystem-safe document IDs for non-arXiv URLs.

Usage:
    converter = WebDocumentConverter()
    doc = converter.convert(html, base_url="https://d2l.ai/chapter_x/page.html")
    print(doc.title, doc.markdown)
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import MarkdownConverter

from minitools.scrapers.article_dates import normalize_iso_date
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# 文書IDの slug 部分の最大長
MAX_SLUG_LENGTH = 60

# 本文から除去する要素（ナビゲーション・装飾・スクリプト類）
REMOVE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside"]
REMOVE_TAGS += ["form", "button", "iframe", "svg"]
REMOVE_SELECTORS = [
    "a.headerlink",
    "span.eqno",
    ".mdl-tooltip",
    ".mdl-tabs__tab-bar",
    "[role=tablist]",
    ".toctree-wrapper",
    ".pagenation",
    ".related",
    ".sphinxsidebar",
]

# 本文ルート候補（先頭ほど優先）
CONTENT_ROOT_SELECTORS = [
    "[role=main]",
    "article",
    "div.document",
    "div.body",
    "main",
]

# タイトル末尾のサイト名（"Title — Site" / "Title | Site"）
_TITLE_SUFFIX_PATTERN = re.compile(r"\s+(?:—|–|\||::)\s+[^—–|]+$")

# 数式プレースホルダ（markdownify にエスケープされないよう英数字のみ）
_MATH_PLACEHOLDER = "MATHPLACEHOLDER{:04d}X"
_MATH_PLACEHOLDER_PATTERN = re.compile(r"MATHPLACEHOLDER(\d{4})X")

# 数式デリミタ
_INLINE_DELIMS = [(r"\(", r"\)"), ("$", "$")]
_DISPLAY_DELIMS = [(r"\[", r"\]"), ("$$", "$$")]


@dataclass
class WebDocument:
    """Webページの変換結果"""

    markdown: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    published: str = ""  # YYYY-MM-DD形式（不明時は空）
    abstract: str = ""


def derive_document_id(url: str) -> str:
    """非 arXiv URL からファイルシステム安全な文書IDを導出する

    ``{host}_{slug}_{hash8}`` 形式。host は ``www.`` を除去、slug はパス末尾
    （拡張子除去）を英数字と ``_`` に正規化する。同じ slug の別 URL を区別する
    ため URL の SHA-1 先頭8桁を付与する。

    Examples:
        https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf
        → cdn.openai.com_language_models_are_unsupervised_multitask_learners_xxxxxxxx
    """
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "unknown").lower()
    if host.startswith("www."):
        host = host[4:]
    host = re.sub(r"[^a-z0-9.-]", "", host) or "unknown"

    parts = [p for p in parsed.path.split("/") if p]
    last = parts[-1] if parts else ""
    if "." in last:
        last = last.rsplit(".", 1)[0]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", last).strip("_").lower()
    slug = slug[:MAX_SLUG_LENGTH].rstrip("_")

    digest = hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:8]
    return "_".join(p for p in (host, slug, digest) if p)


def extract_title_from_markdown(markdown: str) -> str:
    """Markdown の最初の見出し（# 〜 ##）をタイトルとして返す"""
    for line in markdown.splitlines():
        match = re.match(r"^#{1,2}\s+(.+?)\s*#*\s*$", line.strip())
        if match:
            title = re.sub(r"[*_`]", "", match.group(1)).strip()
            if title:
                return title
    return ""


def extract_abstract_from_markdown(markdown: str, max_chars: int = 3000) -> str:
    """ "Abstract" 見出し直後の本文を抽出する（次の見出しまで）

    見出しが無い場合、``Abstract.`` / ``**Abstract**`` で始まる段落も対象にする。
    """
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        heading = re.match(r"^#{1,6}\s+[*_]*abstract[*_.:]*\s*$", stripped, re.I)
        if heading:
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                if re.match(r"^#{1,6}\s", nxt.strip()):
                    break
                body.append(nxt)
            text = "\n".join(body).strip()
            if text:
                return text[:max_chars]
        inline = re.match(r"^[*_]*abstract[*_.:—-]*\s+(.+)$", stripped, re.I)
        if inline:
            return inline.group(1).strip()[:max_chars]
    return ""


def clean_page_title(title: str) -> str:
    """``<title>`` 末尾のサイト名サフィックスを除去する"""
    title = " ".join(title.split())
    cleaned = _TITLE_SUFFIX_PATTERN.sub("", title).strip()
    return cleaned or title


class _CodeAwareConverter(MarkdownConverter):
    """コード言語を祖先要素の class からも推定する markdownify 変換器"""

    def convert_pre(self, el: Any, text: str, parent_tags: Any) -> str:
        if not text:
            return ""
        language = _detect_code_language(el)
        code = el.get_text()
        code = code.strip("\n")
        return f"\n\n```{language}\n{code}\n```\n\n"


def _detect_code_language(el: Tag) -> str:
    """``highlight-python`` / ``language-python`` 等の class から言語を推定"""
    node: Optional[Tag] = el
    depth = 0
    while node is not None and depth < 4:
        raw_classes: Any = node.get("class") or []
        classes: list[str] = (
            [raw_classes] if isinstance(raw_classes, str) else list(raw_classes)
        )
        for cls in classes:
            for prefix in ("highlight-", "language-", "lang-"):
                if cls.startswith(prefix):
                    lang = cls[len(prefix) :]
                    if lang not in ("default", "none", "text", "notranslate"):
                        return lang
        node = node.parent if isinstance(node.parent, Tag) else None
        depth += 1
    return ""


class WebDocumentConverter:
    """技術系 Web ページの HTML を翻訳用 Markdown に変換する"""

    def convert(self, html: str, base_url: str) -> WebDocument:
        """HTML を WebDocument（Markdown + メタデータ）に変換する

        Args:
            html: ページの HTML
            base_url: 相対 URL 解決用のベース URL（リダイレクト後の URL）

        Returns:
            WebDocument
        """
        soup = BeautifulSoup(html, "html.parser")
        metadata = self._extract_metadata(soup)

        root = self._select_content_root(soup)
        self._clean(root)
        self._keep_active_tab_panels(root)
        self._absolutize_urls(root, base_url)
        self._unwrap_linked_images(root)
        math_map = self._replace_math(root, soup)
        self._collapse_soft_line_breaks(root)

        markdown = _CodeAwareConverter(
            heading_style="ATX",
            bullets="-",
            strip=["span"],
        ).convert_soup(root)
        markdown = self._restore_math(markdown, math_map)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip() + "\n"

        title = metadata.get("title") or extract_title_from_markdown(markdown)
        return WebDocument(
            markdown=markdown,
            title=title,
            authors=metadata.get("authors") or [],
            published=metadata.get("published") or "",
            abstract=metadata.get("abstract") or "",
        )

    # -- メタデータ ---------------------------------------------------------

    @staticmethod
    def _meta(soup: BeautifulSoup, *keys: str) -> str:
        for key in keys:
            tag = soup.find("meta", attrs={"name": key}) or soup.find(
                "meta", attrs={"property": key}
            )
            if isinstance(tag, Tag):
                content = tag.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return ""

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, Any]:
        title = self._meta(soup, "citation_title", "og:title", "twitter:title")
        if not title and soup.title and soup.title.string:
            title = clean_page_title(soup.title.string)
        elif title:
            title = clean_page_title(title)

        authors = [
            str(tag.get("content")).strip()
            for tag in soup.find_all("meta", attrs={"name": "citation_author"})
            if isinstance(tag, Tag) and tag.get("content")
        ]
        if not authors:
            author = self._meta(soup, "author", "article:author")
            if author:
                authors = [author]

        published = normalize_iso_date(
            self._meta(
                soup,
                "citation_publication_date",
                "citation_date",
                "article:published_time",
                "date",
            ).replace("/", "-")
        )
        abstract = self._meta(
            soup, "citation_abstract", "description", "og:description"
        )
        return {
            "title": title,
            "authors": authors,
            "published": published or "",
            "abstract": abstract,
        }

    # -- 本文抽出 -----------------------------------------------------------

    @staticmethod
    def _select_content_root(soup: BeautifulSoup) -> Tag:
        for selector in CONTENT_ROOT_SELECTORS:
            found = soup.select_one(selector)
            if isinstance(found, Tag) and found.get_text(strip=True):
                return found
        return soup.body or soup

    @staticmethod
    def _clean(root: Tag) -> None:
        for tag in root.find_all(REMOVE_TAGS):
            # MathJax の <script type="math/tex"> は数式として残す
            if tag.name == "script" and "math/tex" in str(tag.get("type", "")):
                continue
            tag.decompose()
        for selector in REMOVE_SELECTORS:
            for tag in root.select(selector):
                tag.decompose()

    @staticmethod
    def _keep_active_tab_panels(root: Tag) -> None:
        """タブ切替（フレームワーク別コード等）はアクティブなパネルのみ残す"""
        panels = root.select('.mdl-tabs__panel, [role="tabpanel"], .tab-pane')
        groups: dict[int, list[Tag]] = {}
        for panel in panels:
            parent = panel.parent
            if isinstance(parent, Tag):
                groups.setdefault(id(parent), []).append(panel)
        for group in groups.values():
            if len(group) < 2:
                continue
            active = [
                p
                for p in group
                if {"is-active", "active", "show"} & set(p.get("class") or [])
            ]
            keep = active[0] if active else group[0]
            for panel in group:
                if panel is not keep:
                    panel.decompose()

    @staticmethod
    def _absolutize_urls(root: Tag, base_url: str) -> None:
        """img/a の URL を絶対化（Notion は相対 URL を受け付けない）"""
        for img in root.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if isinstance(src, str) and src and not src.startswith("data:"):
                img["src"] = urljoin(base_url, src)
            else:
                img.decompose()
        for a in root.find_all("a"):
            href = a.get("href")
            if not isinstance(href, str) or not href or href.startswith("#"):
                a.unwrap()
                continue
            absolute = urljoin(base_url, href)
            if not absolute.startswith(("http://", "https://")):
                a.unwrap()
                continue
            a["href"] = absolute
            # 参考文献ツールチップ等の title は Markdown リンクを壊すため除去
            if "title" in a.attrs:
                del a["title"]

    @staticmethod
    def _collapse_soft_line_breaks(root: Tag) -> None:
        """HTML ソース上の折り返し改行を空白に畳む（pre/code は除く）

        NotionBlockBuilder は1行=1段落として扱うため、段落内の改行を残すと
        文の途中で段落が分割される。
        """
        for text_node in list(root.find_all(string=True)):
            if not isinstance(text_node, NavigableString) or "\n" not in text_node:
                continue
            if text_node.find_parent(["pre", "code"]) is not None:
                continue
            collapsed = re.sub(r"\s*\n\s*", " ", str(text_node))
            text_node.replace_with(NavigableString(collapsed))

    @staticmethod
    def _unwrap_linked_images(root: Tag) -> None:
        """<a><img></a> は画像単体にする（Notion 画像ブロック化のため）"""
        for a in root.find_all("a"):
            children = [
                c
                for c in a.children
                if not (isinstance(c, NavigableString) and not c.strip())
            ]
            if len(children) == 1 and isinstance(children[0], Tag):
                if children[0].name == "img":
                    a.unwrap()

    # -- 数式 ---------------------------------------------------------------

    def _replace_math(self, root: Tag, soup: BeautifulSoup) -> dict[str, str]:
        """数式ノードをプレースホルダに置換し、Markdown 用の数式文字列を返す"""
        math_map: dict[str, str] = {}

        def register(expr: str, display: bool) -> str:
            key = _MATH_PLACEHOLDER.format(len(math_map))
            expr = expr.strip()
            # Sphinx は \begin{split}\begin{aligned}..\end{aligned}\end{split} と
            # 二重に包むが、KaTeX は split 内の aligned を受け付けないため外す
            split_match = re.fullmatch(
                r"\\begin\{split\}(.*)\\end\{split\}", expr, flags=re.S
            )
            if split_match and "\\begin{aligned}" in split_match.group(1):
                expr = split_match.group(1).strip()
            if display:
                math_map[key] = f"\n\n$$\n{expr}\n$$\n\n"
            else:
                math_map[key] = f"${' '.join(expr.split())}$"
            return key

        # MathJax <script type="math/tex; mode=display">
        for script in root.find_all("script"):
            script_type = str(script.get("type", ""))
            display = "mode=display" in script_type
            placeholder = register(script.get_text(), display)
            node: Any = soup.new_tag("p") if display else NavigableString(placeholder)
            if display:
                node.string = placeholder
            script.replace_with(node)

        # Sphinx / MathJax 静的出力: span.math（インライン）、div.math（ブロック）
        for el in root.select(".math, .arithmatex, .katex-display, .katex"):
            if not isinstance(el, Tag) or el.parent is None:
                continue
            annotation = el.find("annotation", attrs={"encoding": "application/x-tex"})
            raw = annotation.get_text() if annotation else el.get_text()
            display = el.name == "div" or "katex-display" in (el.get("class") or [])
            expr, detected_display = self._strip_math_delimiters(raw)
            display = display or detected_display
            placeholder = register(expr, display)
            if display:
                new_p = soup.new_tag("p")
                new_p.string = placeholder
                el.replace_with(new_p)
            else:
                el.replace_with(NavigableString(placeholder))

        # 地の文に残った \( ... \) / \[ ... \]
        for text_node in list(root.find_all(string=True)):
            if not isinstance(text_node, NavigableString):
                continue
            if text_node.parent is not None and text_node.parent.name in (
                "pre",
                "code",
            ):
                continue
            value = str(text_node)
            if "\\(" not in value and "\\[" not in value:
                continue
            value = re.sub(
                r"\\\[(.+?)\\\]",
                lambda m: register(m.group(1), True),
                value,
                flags=re.S,
            )
            value = re.sub(
                r"\\\((.+?)\\\)",
                lambda m: register(m.group(1), False),
                value,
                flags=re.S,
            )
            text_node.replace_with(NavigableString(value))

        return math_map

    @staticmethod
    def _strip_math_delimiters(raw: str) -> tuple[str, bool]:
        """``\\(..\\)`` / ``\\[..\\]`` / ``$..$`` / ``$$..$$`` を外す"""
        text = raw.strip()
        for left, right in _DISPLAY_DELIMS:
            if text.startswith(left) and text.endswith(right) and len(text) > 4:
                return text[len(left) : -len(right)].strip(), True
        for left, right in _INLINE_DELIMS:
            if text.startswith(left) and text.endswith(right) and len(text) > 2:
                return text[len(left) : -len(right)].strip(), False
        return text, False

    @staticmethod
    def _restore_math(markdown: str, math_map: dict[str, str]) -> str:
        return _MATH_PLACEHOLDER_PATTERN.sub(
            lambda m: math_map.get(m.group(0), m.group(0)), markdown
        )
