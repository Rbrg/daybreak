"""RAG 子系统测试：分块、分词、BM25 检索、KnowledgeBase 管线。全部离线。"""

from daybreak.rag import KnowledgeBase
from daybreak.rag.chunker import chunk_documents, chunk_text
from daybreak.rag.index import BM25Index, tokenize


class TestChunker:
    def test_paragraph_packing(self):
        text = "第一段。\n\n第二段。\n\n第三段。"
        chunks = chunk_text(text, "t.md", max_chars=500, overlap=50)
        assert len(chunks) == 1
        assert "第一段" in chunks[0].text and "第三段" in chunks[0].text

    def test_overlap_between_chunks(self):
        # 段落均小于上限时，贪心合并 + 重叠窗口：后块应含前块尾部
        para = "段落内容" * 8  # 32 字
        text = "\n\n".join([para] * 6)
        chunks = chunk_text(text, "t.md", max_chars=100, overlap=20)
        assert len(chunks) >= 2
        assert chunks[0].text[-20:] in chunks[1].text
        assert all(len(c.text) <= 100 for c in chunks)

    def test_long_paragraph_hard_split(self):
        text = "长" * 1200
        chunks = chunk_text(text, "t.md", max_chars=500, overlap=50)
        assert len(chunks) == 3
        assert all(len(c.text) <= 500 for c in chunks)

    def test_chunk_metadata(self):
        chunks = chunk_documents([("a.md", "内容一。\n\n内容二。"), ("b.md", "另一篇。")])
        assert {c.source for c in chunks} == {"a.md", "b.md"}
        assert all(c.index >= 0 for c in chunks)

    def test_empty_text(self):
        assert chunk_text("", "t.md") == []


class TestTokenizer:
    def test_filters_stopwords(self):
        toks = tokenize("如何添加新工具")
        assert "如何" not in toks
        assert "工具" in toks

    def test_filters_punctuation(self):
        toks = tokenize("你好，世界！")
        assert all(any(ch.isalnum() for ch in t) for t in toks)


class TestBM25:
    def _build(self):
        docs = [
            ("手册.md", "添加新工具需要三步：写函数、加 @beta_tool 装饰器、注册进 TOOLS 列表。"),
            ("api.md", "thinking blocks 必须随 history 完整回传，只存文本会导致多轮对话出错。"),
            ("无关.md", "今天天气不错，适合出门散步和爬山。"),
        ]
        return BM25Index(chunk_documents(docs))

    def test_relevant_ranked_first(self):
        idx = self._build()
        top = idx.search("怎么添加新工具", top_k=1)
        assert top[0][0].source == "手册.md"

    def test_second_query(self):
        idx = self._build()
        top = idx.search("thinking blocks 要注意什么", top_k=1)
        assert top[0][0].source == "api.md"

    def test_irrelevant_query_returns_empty(self):
        idx = self._build()
        assert idx.search("量子力学的薛定谔方程", top_k=3) == []

    def test_empty_index(self):
        assert BM25Index([]).search("任何查询") == []


class TestKnowledgeBase:
    def test_build_and_search(self, tmp_path):
        (tmp_path / "doc.md").write_text(
            "# 标题\n\nBM25 是一种词法检索算法，不依赖 embedding 模型。",
            encoding="utf-8",
        )
        kb = KnowledgeBase(tmp_path)
        kb.build()
        assert not kb.is_empty
        results = kb.search("BM25 是什么检索算法", top_k=1)
        assert results
        assert "BM25" in results[0][0].text

    def test_empty_directory(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        kb.build()
        assert kb.is_empty
        assert kb.search("任意查询") == []

    def test_describe_lists_documents(self, tmp_path):
        (tmp_path / "a.md").write_text("内容甲" * 100, encoding="utf-8")
        kb = KnowledgeBase(tmp_path)
        kb.build()
        desc = kb.describe()
        assert "a.md" in desc
        assert "分块" in desc
