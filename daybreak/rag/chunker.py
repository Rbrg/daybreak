"""文本分块：按段落聚合成不超过上限的块，块间保留重叠窗口。

策略：
1. 先按空行拆成自然段（尊重文档结构，不在句子中间硬切）；
2. 贪心地把段落并进当前块，直到达到 max_chars；
3. 开新块时把上一块的尾部 overlap 字符带过来，避免答案正好跨越块边界
   时两边都检索不到；
4. 单段本身就超长时按 max_chars 硬切（硬切不重叠，避免无限增长）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PARA_SPLIT = re.compile(r"\n\s*\n")


@dataclass
class Chunk:
    """一个检索单元。source 用于引用溯源，index 是它在文档内的序号。"""

    text: str
    source: str
    index: int


def chunk_text(text: str, source: str, max_chars: int = 500, overlap: int = 50) -> list[Chunk]:
    paragraphs = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]

    # 超长单段先硬切，保证后续贪心合并的前提（每段 <= max_chars）
    pieces: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            pieces.append(para)
        else:
            pieces.extend(para[i:i + max_chars] for i in range(0, len(para), max_chars))

    chunks: list[Chunk] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if current and len(candidate) > max_chars:
            chunks.append(Chunk(text=current, source=source, index=len(chunks)))
            tail = current[-overlap:] if overlap > 0 else ""
            # 重叠 + 新段装不下上限时截断重叠，保证任何块都不超过 max_chars
            if tail and len(tail) + len(piece) + 2 > max_chars:
                tail = tail[: max(0, max_chars - len(piece) - 2)]
            current = f"{tail}\n\n{piece}" if tail else piece
        else:
            current = candidate
    if current:
        chunks.append(Chunk(text=current, source=source, index=len(chunks)))
    return chunks


def chunk_documents(
    documents: list[tuple[str, str]],
    max_chars: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """对 [(来源, 文本)] 列表批量分块。"""
    chunks: list[Chunk] = []
    for source, text in documents:
        chunks.extend(chunk_text(text, source, max_chars=max_chars, overlap=overlap))
    return chunks
