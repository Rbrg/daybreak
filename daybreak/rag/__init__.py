"""RAG 知识库子系统。

组成：
- loader   文档加载（.md/.txt/.pdf → 文本）
- chunker  文本分块（段落聚合 + 重叠窗口，保留来源元数据）
- index    BM25 检索（可替换为向量检索，接口不变）

KnowledgeBase 把三者串成"加载 → 分块 → 建索引 → 检索"的管线，
对上（工具层）只暴露 search / describe / build 三个方法。
"""

from __future__ import annotations

import os
from pathlib import Path

from .chunker import Chunk, chunk_documents
from .index import BM25Index
from .loader import load_documents

# 默认知识库目录：项目根目录下的 knowledge/（可用 AGENT_KNOWLEDGE_DIR 覆盖）
DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"

MAX_CHARS = 500
OVERLAP = 50
TOP_K = 3


class KnowledgeBase:
    """一个可重建的 BM25 知识库。索引在首次 search 或显式 build 时生成。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(
            os.environ.get("AGENT_KNOWLEDGE_DIR", DEFAULT_KNOWLEDGE_DIR)
        )
        self._index: BM25Index | None = None
        self._doc_count = 0

    def build(self) -> None:
        """（重新）加载目录内全部文档并建索引。"""
        documents = load_documents(self.root)
        chunks = chunk_documents(documents, max_chars=MAX_CHARS, overlap=OVERLAP)
        self._index = BM25Index(chunks)
        self._doc_count = len(documents)

    def _ensure_index(self) -> None:
        if self._index is None:
            self.build()

    def search(self, query: str, top_k: int = TOP_K) -> list[tuple[Chunk, float]]:
        self._ensure_index()
        assert self._index is not None
        return self._index.search(query, top_k=top_k)

    def describe(self) -> str:
        """人类可读的知识库概况，供 list_documents 工具和启动横幅使用。"""
        self._ensure_index()
        assert self._index is not None
        if not self._index.chunks:
            return f"知识库为空（目录: {self.root}）"
        by_source: dict[str, int] = {}
        for chunk in self._index.chunks:
            by_source[chunk.source] = by_source.get(chunk.source, 0) + 1
        lines = [f"知识库共 {self._doc_count} 个文档、{len(self._index.chunks)} 个分块："]
        for source, count in sorted(by_source.items()):
            lines.append(f"  - {source}（{count} 块）")
        return "\n".join(lines)

    @property
    def is_empty(self) -> bool:
        self._ensure_index()
        assert self._index is not None
        return not self._index.chunks


# ---------------------------------------------------------------------------
# 进程级单例：工具函数（模块级、无状态）与 CLI（/reindex）共享同一个实例
# ---------------------------------------------------------------------------

_kb: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
