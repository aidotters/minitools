"""Tests for WebDocumentConverter (HTML → translation-ready Markdown)."""

from minitools.publishers.notion_block_builder import NotionBlockBuilder
from minitools.scrapers.web_document import (
    WebDocumentConverter,
    clean_page_title,
    derive_document_id,
    extract_abstract_from_markdown,
    extract_title_from_markdown,
)

BASE_URL = "https://d2l.ai/chapter_attention/self-attention.html"

# d2l.ai（Sphinx）の構造を縮約したフィクスチャ
SPHINX_HTML = """
<html><head>
<title>11.6. Self-Attention — Dive into Deep Learning 1.0.3 documentation</title>
</head><body>
<main class="mdl-layout__content">
  <header class="mdl-layout__drawer"><ul><li class="toctree-l1">TOC ENTRY</li></ul></header>
  <div class="document"><div class="page-content" role="main">
    <div class="section">
      <h1>11.6. Self-Attention<a class="headerlink" href="#self-attention">¶</a></h1>
      <p>Given tokens
      <span class="math notranslate nohighlight">\\(\\mathbf{x}_1, \\ldots, \\mathbf{x}_n\\)</span>
      where <span class="math notranslate nohighlight">\\(x_i^*\\)</span>, see
      <a class="reference internal" href="../chapter_references/zreferences.html#id1"
         title="Vaswani, A. (2017). Attention is all you need.">Vaswani et al.</a>
      and <a href="#local">this section</a>.</p>
      <div class="math notranslate nohighlight" id="equation-eq">
\\[\\begin{split}\\begin{aligned} p_{i, 2j} &amp;= \\sin(i)\\end{aligned}\\end{split}\\]</div>
      <div class="mdl-tabs mdl-js-tabs">
        <div class="mdl-tabs__tab-bar code"><a class="mdl-tabs__tab is-active">pytorch</a><a class="mdl-tabs__tab">jax</a></div>
        <div class="mdl-tabs__panel is-active" id="pytorch-1-0">
          <div class="highlight-python notranslate"><div class="highlight"><pre><span></span><span class="kn">import</span> <span class="nn">torch</span>
x_1 = 2 * 3
</pre></div></div>
        </div>
        <div class="mdl-tabs__panel " id="jax-1-1">
          <div class="highlight-python notranslate"><div class="highlight"><pre>import jax</pre></div></div>
        </div>
      </div>
      <div class="figure align-default">
        <a href="../_images/fig.svg"><img alt="fig" src="../_images/fig.svg"/></a>
        <p class="caption"><span class="caption-text">Comparing architectures.</span></p>
      </div>
    </div>
  </div>
  <div class="pagenation">Previous Next</div>
  </div>
</main>
<script>console.log("x")</script>
</body></html>
"""


class TestWebDocumentConverter:
    def setup_method(self):
        self.doc = WebDocumentConverter().convert(SPHINX_HTML, base_url=BASE_URL)
        self.md = self.doc.markdown

    def test_title_strips_site_suffix(self):
        assert self.doc.title == "11.6. Self-Attention"

    def test_navigation_removed(self):
        assert "TOC ENTRY" not in self.md
        assert "Previous Next" not in self.md
        assert "¶" not in self.md
        assert "console.log" not in self.md

    def test_inline_math_preserved_without_escaping(self):
        assert r"$\mathbf{x}_1, \ldots, \mathbf{x}_n$" in self.md
        assert r"$x_i^*$" in self.md

    def test_display_math_and_split_unwrapped(self):
        assert "$$\n\\begin{aligned} p_{i, 2j} &= \\sin(i)\\end{aligned}\n$$" in (
            self.md
        )
        assert "begin{split}" not in self.md

    def test_only_active_tab_panel_kept(self):
        assert "import torch" in self.md
        assert "import jax" not in self.md
        assert "pytorch" not in self.md.replace("```python", "")

    def test_code_block_fenced_with_language_and_verbatim(self):
        assert "```python\nimport torch\nx_1 = 2 * 3\n```" in self.md

    def test_links_absolute_and_titles_removed(self):
        assert (
            "[Vaswani et al.](https://d2l.ai/chapter_references/zreferences.html#id1)"
            in self.md
        )
        assert "Attention is all you need" not in self.md

    def test_anchor_only_link_becomes_text(self):
        assert "this section" in self.md
        assert "(#local)" not in self.md

    def test_linked_image_unwrapped_and_absolute(self):
        assert "![fig](https://d2l.ai/_images/fig.svg)" in self.md.splitlines()

    def test_soft_line_breaks_collapsed(self):
        paragraph = next(
            line for line in self.md.splitlines() if line.startswith("Given tokens")
        )
        assert "where" in paragraph

    def test_notion_blocks(self):
        blocks = NotionBlockBuilder().build_blocks(self.md)
        types = [b["type"] for b in blocks]
        assert "equation" in types
        assert "code" in types
        assert "image" in types
        image = next(b for b in blocks if b["type"] == "image")
        assert image["image"]["external"]["url"] == "https://d2l.ai/_images/fig.svg"


class TestMetadata:
    def test_citation_meta(self):
        html = """<html><head>
        <meta name="citation_title" content="A Paper">
        <meta name="citation_author" content="Alice">
        <meta name="citation_author" content="Bob">
        <meta name="citation_publication_date" content="2019/02/14">
        <meta name="citation_abstract" content="We show things.">
        </head><body><article><p>Body</p></article></body></html>"""
        doc = WebDocumentConverter().convert(html, base_url="https://x.org/p")
        assert doc.title == "A Paper"
        assert doc.authors == ["Alice", "Bob"]
        assert doc.published == "2019-02-14"
        assert doc.abstract == "We show things."

    def test_title_falls_back_to_heading(self):
        html = "<html><body><article><h1>Heading</h1><p>x</p></article></body></html>"
        doc = WebDocumentConverter().convert(html, base_url="https://x.org/p")
        assert doc.title == "Heading"


class TestHelpers:
    def test_derive_document_id(self):
        doc_id = derive_document_id("https://www.Example.com/a/My-Post.html?x=1")
        assert doc_id.startswith("example.com_my_post_")

    def test_derive_document_id_no_path(self):
        assert derive_document_id("https://example.com/").startswith("example.com_")

    def test_clean_page_title(self):
        assert clean_page_title("Title | Site") == "Title"
        assert clean_page_title("Only Title") == "Only Title"

    def test_extract_title_from_markdown(self):
        assert extract_title_from_markdown("text\n# **Big** Title\n") == "Big Title"
        assert extract_title_from_markdown("no heading") == ""

    def test_extract_abstract_heading(self):
        md = "# T\n\n## Abstract\n\nLine one.\nLine two.\n\n## 1 Intro\n\nx"
        assert extract_abstract_from_markdown(md) == "Line one.\nLine two."

    def test_extract_abstract_inline(self):
        md = "# T\n\n**Abstract.** We propose X.\n"
        assert extract_abstract_from_markdown(md) == "We propose X."
