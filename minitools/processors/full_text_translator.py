"""
Full-text Markdown translator using LLM abstraction layer.
Translates structured Markdown while preserving formatting.
"""

import asyncio
import re
from typing import List, Optional

from minitools.llm import get_llm_client, BaseLLMClient
from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)

# デフォルトのチャンクサイズ（文字数）
# LLMの出力トークン制限による翻訳切れを防ぐため、控えめに設定
DEFAULT_CHUNK_SIZE = 3000

# 翻訳結果が元テキストに対してこの比率未満の場合、切れている可能性がある
TRUNCATION_RATIO_THRESHOLD = 0.3

TRANSLATION_PROMPT = """あなたはプロの翻訳者です。以下のMarkdownテキストを日本語に翻訳してください。

## 翻訳ルール

1. **Markdown構造を維持**: 見出し（#, ##, ###）、箇条書き（-）、番号付きリスト（1.）、引用（>）、太字（**）、イタリック（*）、リンク（[text](url)）の形式をそのまま維持してください。
2. **コードブロック非翻訳**: ```で囲まれたコードブロック内のコード本体は翻訳しないでください。ただし、コード内のコメント（#や//で始まる行）は翻訳してください。
3. **インラインコード非翻訳**: `バッククォート`で囲まれたインラインコードは翻訳しないでください。
4. **画像リンク非翻訳**: ![alt](url) 形式の画像リンクはそのまま維持してください。
5. **URL非翻訳**: URLはそのまま維持してください。
6. **数式非翻訳**: インライン数式 `$...$` およびブロック数式 `$$...$$` は翻訳せず、LaTeX形式のまま維持してください。
7. **文体統一**: 文末表現は「である調（常体）」で統一してください。「ですます調（敬体）」と混在させないでください。技術記事・論文として自然な常体で記述してください。
8. **自然な日本語**: 技術的に正確で、自然な日本語にしてください。
9. **テーブル構造維持**: `|` 区切りのMarkdownテーブルは行・列構造を維持し、ヘッダー・セル内容のみ翻訳してください。区切り行（`|---|---|` 等）はそのまま変更せず、セル数・改行位置も崩さないでください。
10. **PDFハイフン分割の修復**: 行末がハイフン `-` で終わり、次行先頭に単語の続きがある場合（例: `evalu-` 改行 `ation`）、それは PDF の自動ハイフネーションです。1 単語に連結してから翻訳してください。連結後の行頭が `-` や数字 `1.` で始まっても、それを箇条書き記号として再出力しないでください。
11. **コードフェンスで包まない**: 出力全体を ```` ```markdown ```` や ```` ``` ```` で囲まないでください。原文に存在するコードブロック以外、新たな ```` ``` ```` を追加してはいけません。
12. **原文を残さない**: 英語原文をそのまま残してから日本語訳を併記しないでください。出力は日本語訳のみです（コード・URL・引用記号など非翻訳要素を除く）。
13. **見出しも翻訳**: `#`/`##`/`###` で始まる見出し行も日本語に翻訳してください。原文をそのまま残してはいけません。

## 翻訳対象テキスト

{text}

## 翻訳結果（Markdownのみ、説明なし）
"""


class FullTextTranslator:
    """構造化Markdownの全文翻訳を行うクラス"""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        thinking_level: Optional[str] = None,
        llm_client: Optional[BaseLLMClient] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_retries: int = 3,
    ):
        """
        Args:
            provider: LLMプロバイダー名（"ollama" / "openai" / "gemini"）
            model: 使用するモデル名
            thinking_level: Gemini 3系の思考深度（"minimal" / "low" / "medium" / "high"）。
                Gemini 利用時のみ有効。未指定時は ``llm.gemini.default_thinking_level``
                にフォールバック。
            llm_client: LLMクライアント（テスト用に直接注入可能）
            chunk_size: チャンク分割のサイズ（文字数）
            max_retries: 翻訳失敗時のリトライ回数
        """
        config = get_config()
        self.provider = provider or config.get(
            "defaults.medium.translate_provider",
            config.get("llm.provider", "ollama"),
        )
        # モデルはプロバイダーのデフォルトに委譲（明示指定時のみ上書き）
        self.model = model or config.get(f"llm.{self.provider}.default_model", None)
        self.thinking_level = thinking_level
        self.chunk_size = chunk_size
        self.max_retries = max_retries

        if llm_client:
            self.llm = llm_client
        else:
            self.llm = get_llm_client(
                provider=self.provider,
                model=self.model,
                thinking_level=self.thinking_level,
            )

        logger.info(
            f"FullTextTranslator initialized "
            f"(provider={self.provider}, model={self.model}, "
            f"thinking_level={self.thinking_level}, chunk_size={chunk_size})"
        )

    async def translate(self, markdown: str) -> str:
        """
        Markdown全文を日本語に翻訳する

        ``<!-- DO NOT TRANSLATE -->`` マーカーが含まれる場合、
        マーカー以降のテキスト（参考文献等）は翻訳せずそのまま保持する。

        Args:
            markdown: 翻訳対象のMarkdown文字列

        Returns:
            翻訳済みのMarkdown文字列
        """
        if not markdown or not markdown.strip():
            return ""

        # <!-- DO NOT TRANSLATE --> マーカーで分割
        translatable, untranslatable = self._split_by_do_not_translate(markdown)

        if not translatable.strip():
            logger.info("No translatable content (all after DO NOT TRANSLATE marker)")
            return untranslatable

        chunks = self._split_into_chunks(translatable)
        logger.info(f"Translating {len(chunks)} chunk(s)")
        if untranslatable:
            logger.info(
                f"Skipping translation for {len(untranslatable)} chars "
                f"after DO NOT TRANSLATE marker"
            )

        translated_chunks: List[str] = []
        for i, chunk in enumerate(chunks):
            logger.info(
                f"  Translating chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)"
            )
            translated = await self._translate_chunk(chunk)
            translated_chunks.append(translated)

        result = "\n\n".join(translated_chunks)
        if untranslatable:
            result = result + "\n\n" + untranslatable
        return result

    def _split_by_do_not_translate(self, markdown: str) -> tuple[str, str]:
        """
        ``<!-- DO NOT TRANSLATE -->`` マーカーでテキストを分割する

        Args:
            markdown: 分割対象のMarkdown文字列

        Returns:
            (翻訳対象テキスト, 翻訳対象外テキスト) のタプル。
            マーカーがない場合は (全文, "") を返す。
        """
        marker = "<!-- DO NOT TRANSLATE -->"
        idx = markdown.find(marker)
        if idx == -1:
            return markdown, ""
        translatable = markdown[:idx].rstrip()
        untranslatable = markdown[idx:]
        return translatable, untranslatable

    def _split_into_chunks(self, markdown: str) -> List[str]:
        """
        Markdownをセクション単位でチャンクに分割する

        見出し行（# で始まる行）を区切りとして分割し、
        各チャンクがchunk_size以下になるようにする。
        見出しがない大きなセクションは段落単位でさらに分割する。

        Args:
            markdown: 分割対象のMarkdown文字列

        Returns:
            チャンクのリスト
        """
        if len(markdown) <= self.chunk_size:
            return [markdown]

        # 見出し行で分割
        sections: List[str] = []
        current_section: List[str] = []

        for line in markdown.split("\n"):
            # 見出し行を検出（新しいセクションの開始）
            if re.match(r"^#{1,3}\s+", line) and current_section:
                sections.append("\n".join(current_section))
                current_section = [line]
            else:
                current_section.append(line)

        # 最後のセクションを追加
        if current_section:
            sections.append("\n".join(current_section))

        # 大きすぎるセクションを段落単位で分割
        split_sections: List[str] = []
        for section in sections:
            if len(section) <= self.chunk_size:
                split_sections.append(section)
            else:
                split_sections.extend(self._split_large_section(section))

        # セクションをチャンクサイズに収まるようにグルーピング
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_size = 0

        for section in split_sections:
            section_size = len(section)

            if current_size + section_size > self.chunk_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [section]
                current_size = section_size
            else:
                current_chunk.append(section)
                current_size += section_size

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _split_large_section(self, section: str) -> List[str]:
        """
        chunk_sizeを超えるセクションを段落（空行）単位で分割する

        `|` で始まる連続行群（Markdownテーブル）は途中で分割されないよう、
        1段落として結合してから段落分割を行う。

        Args:
            section: 分割対象のセクション文字列

        Returns:
            分割されたセクションのリスト
        """
        paragraphs = self._merge_table_blocks(re.split(r"\n\n+", section))

        chunks: List[str] = []
        current: List[str] = []
        current_size = 0

        for para in paragraphs:
            para_size = len(para)

            if current_size + para_size > self.chunk_size and current:
                chunks.append("\n\n".join(current))
                current = [para]
                current_size = para_size
            else:
                current.append(para)
                current_size += para_size

        if current:
            chunks.append("\n\n".join(current))

        return chunks

    @staticmethod
    def _merge_table_blocks(paragraphs: List[str]) -> List[str]:
        """
        `|` で始まる連続する段落群を 1 段落として結合する

        Markdownテーブルが空行なしで途中改行される場合、段落分割でテーブルが
        途中で切れないようにする。
        """

        def is_table_para(p: str) -> bool:
            lines = p.strip().split("\n")
            if not lines:
                return False
            # 全行が | で始まるか
            return all(line.lstrip().startswith("|") for line in lines)

        merged: List[str] = []
        buffer: List[str] = []
        for para in paragraphs:
            if is_table_para(para):
                buffer.append(para)
            else:
                if buffer:
                    merged.append("\n".join(buffer))
                    buffer = []
                merged.append(para)
        if buffer:
            merged.append("\n".join(buffer))
        return merged

    @staticmethod
    def _unwrap_outer_code_fence(text: str) -> str:
        """LLM が出力全体を ```markdown ... ``` で包んでしまった場合に外側を剥がす

        マッチ条件: 先頭行が ``` で始まり末尾行が ``` の場合のみ。
        言語指定（```markdown など）も許容。内側に独立した ``` が複数ある場合は
        誤剥離を避けるためそのまま返す。
        """
        if not text:
            return text
        stripped = text.strip()
        if not stripped.startswith("```") or not stripped.endswith("```"):
            return text
        lines = stripped.split("\n")
        if len(lines) < 2:
            return text
        if not lines[-1].strip() == "```":
            return text
        # 内側に追加の ``` が無い、または開始/終了の対だけのケースに限定
        inner = lines[1:-1]
        fence_count = sum(1 for ln in inner if ln.strip().startswith("```"))
        if fence_count > 0:
            # 内側に独立コードブロックが含まれる可能性 → そのまま返す
            return text
        return "\n".join(inner)

    def _is_likely_truncated(self, original: str, translated: str) -> bool:
        """
        翻訳結果が途中で切れている可能性があるか判定する

        Args:
            original: 元テキスト
            translated: 翻訳結果

        Returns:
            切れている可能性がある場合True
        """
        if not original or not translated:
            return False

        # 翻訳結果が元テキストに対して極端に短い場合
        ratio = len(translated) / len(original)
        if ratio < TRUNCATION_RATIO_THRESHOLD:
            logger.warning(
                f"Translation may be truncated: "
                f"original={len(original)} chars, "
                f"translated={len(translated)} chars, "
                f"ratio={ratio:.2f}"
            )
            return True

        return False

    async def _translate_chunk(self, chunk: str) -> str:
        """
        1つのチャンクを翻訳する（リトライ付き）

        Args:
            chunk: 翻訳対象のチャンク

        Returns:
            翻訳済みテキスト
        """
        prompt = TRANSLATION_PROMPT.format(text=chunk)

        for attempt in range(self.max_retries):
            try:
                result = await self.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model,
                )
                translated = self._unwrap_outer_code_fence(result.strip())
                if not translated:
                    logger.warning(f"Empty translation result (attempt {attempt + 1})")
                    continue

                # 翻訳切れ検出: 比率が極端に低い場合はリトライ
                if self._is_likely_truncated(chunk, translated):
                    if attempt < self.max_retries - 1:
                        delay = 2**attempt
                        logger.warning(
                            f"Retrying due to possible truncation "
                            f"(attempt {attempt + 1}/{self.max_retries}), "
                            f"waiting {delay}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # 最終リトライでも切れている場合はそのまま返す
                        logger.warning(
                            "Translation may still be truncated after all retries, "
                            "using best result"
                        )

                return translated
            except Exception as e:
                delay = 2**attempt  # 指数バックオフ: 1, 2, 4秒
                logger.warning(
                    f"Translation error (attempt {attempt + 1}/{self.max_retries}): "
                    f"{e}, retrying in {delay}s..."
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delay)

        logger.error(
            f"Translation failed after {self.max_retries} attempts, "
            f"returning original text"
        )
        return chunk
