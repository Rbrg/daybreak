"""BM25 词法检索索引。

BM25 是 TF-IDF 的改进版：词频饱和（k1 控制）+ 长文档惩罚（b 控制），
在中小规模文档集上的检索质量稳定优于纯 TF-IDF，且完全离线、可解释。

检索层刻意与上层解耦：KnowledgeBase 只依赖本模块的 build/search 接口，
以后要换成向量检索（embedding + 余弦相似度）时，替换本文件即可，
工具层和 Agent 主循环都不用动。
"""

from __future__ import annotations

import logging
import math
from collections import Counter

import jieba

from .chunker import Chunk

# jieba 默认会往 stderr 打印词典加载日志，CLI 场景下调至 INFO 静音
jieba.setLogLevel(logging.INFO)

# 高频虚词：不进索引也不参与查询打分，否则会淹没实义词的区分度
STOPWORDS = frozenset(
    "的 了 在 是 我 你 他 她 它 们 这 那 有 和 就 不 人 都 一 一个 上 也 很 到 "
    "说 要 去 会 着 没有 看 好 自己 还 可以 什么 怎么 为什么 如何 哪些 吗 呢 "
    "吧 啊 呀 并 以及 或者 如果 因为 所以 但是 然后 对于 通过 进行 相关 "
    "a an the is are was were be been of to in on for with as at by it this that".split()
)

# BM25 标准参数：k1 词频饱和速度，b 长文档惩罚强度
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """jieba 搜索引擎模式分词 + 停用词/标点过滤。

    cut_for_search 对查询词会额外产出子词（如 "计算器" → "计算/算器"），
    提高召回；索引和查询用同一套分词，保证打分一致。
    """
    tokens = []
    for token in jieba.cut_for_search(text):
        token = token.strip()
        if not token or token in STOPWORDS:
            continue
        if not any(ch.isalnum() for ch in token):  # 纯标点/空白
            continue
        tokens.append(token)
    return tokens


class BM25Index:
    """对一组 Chunk 建立 BM25 索引并支持 top-k 检索。"""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self._tokenized = [tokenize(c.text) for c in chunks]
        self._tf: list[Counter] = [Counter(toks) for toks in self._tokenized]
        self._doc_len = [len(toks) for toks in self._tokenized]
        self._avgdl = sum(self._doc_len) / len(chunks) if chunks else 1.0

        # 文档频率：出现在多少个块中（用于 IDF）
        df: Counter = Counter()
        for toks in self._tokenized:
            df.update(set(toks))
        n = len(chunks)
        # +1 变体保证 IDF 非负（词出现在所有块中时也不会变负数）
        self._idf = {
            term: math.log((n - freq + 0.5) / (freq + 0.5) + 1)
            for term, freq in df.items()
        }

    def _score(self, query_tokens: list[str], i: int) -> float:
        tf = self._tf[i]
        dl = self._doc_len[i] or 1
        score = 0.0
        for term in query_tokens:
            if term not in tf:
                continue
            idf = self._idf.get(term, 0.0)
            freq = tf[term]
            score += idf * (freq * (_K1 + 1)) / (freq + _K1 * (1 - _B + _B * dl / self._avgdl))
        return score

    def search(self, query: str, top_k: int = 3) -> list[tuple[Chunk, float]]:
        """返回 [(块, 分数)]，按分数降序；只返回分数 > 0 的结果。

        查询词在索引中完全没出现时返回空列表——宁可告诉模型"没找到"，
        也不返回低质量结果诱导模型硬答。
        """
        if not self.chunks:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored = [(self._score(query_tokens, i), i) for i in range(len(self.chunks))]
        scored = [(s, i) for s, i in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(self.chunks[i], s) for s, i in scored[:top_k]]
