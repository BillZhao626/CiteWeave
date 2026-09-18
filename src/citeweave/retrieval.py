"""Snapshot-scoped BM25 dot products and an explicit, deterministic RRF contract."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass

import jieba

ANALYZER_REVISION = "jieba-0.42.1-precise-hmm-off+identifier-v1"
_TOKENIZER = jieba.Tokenizer()


def tokenize(text: str) -> list[str]:
    result = []
    for piece in re.findall(r"[a-zA-Z0-9]+(?:[._/+\-][a-zA-Z0-9]+)*|[\u3400-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", piece):
            result.extend(t for t in _TOKENIZER.cut(piece, HMM=False) if t.strip())
        else:
            result.append(piece)
    return result


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


@dataclass
class BM25Encoder:
    vocabulary: dict[str, int]
    idf: dict[str, float]
    documents: list[list[str]]
    average_length: float
    fingerprint: str
    k1: float = 1.5
    b: float = 0.75

    @classmethod
    def fit(cls, texts: list[str]) -> BM25Encoder:
        if not texts:
            raise ValueError("empty_snapshot")
        docs = [tokenize(t) for t in texts]
        df = Counter(token for doc in docs for token in set(doc))
        vocabulary = {token: i for i, token in enumerate(sorted(df))}
        idf = {
            token: math.log(1 + (len(docs) - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in df.items()
        }
        identity = json.dumps([ANALYZER_REVISION, 1.5, 0.75, texts], ensure_ascii=False)
        return cls(
            vocabulary,
            idf,
            docs,
            sum(map(len, docs)) / len(docs),
            hashlib.sha256(identity.encode()).hexdigest(),
        )

    def query_vector(self, query: str) -> SparseVector:
        # Each distinct term votes once. Query TF is intentionally not applied.
        tokens = sorted(set(tokenize(query)) & self.vocabulary.keys(), key=self.vocabulary.get)
        return SparseVector([self.vocabulary[t] for t in tokens], [self.idf[t] for t in tokens])

    def document_vector(self, index: int) -> SparseVector:
        tokens = self.documents[index]
        counts = Counter(tokens)
        ordered = sorted(counts, key=self.vocabulary.get)
        norm = self.k1 * (1 - self.b + self.b * len(tokens) / (self.average_length or 1))
        return SparseVector(
            [self.vocabulary[t] for t in ordered],
            [counts[t] * (self.k1 + 1) / (counts[t] + norm) for t in ordered],
        )

    def scores(self, query: str) -> list[float]:
        q = self.query_vector(query)
        weights = dict(zip(q.indices, q.values, strict=True))
        scores = []
        for i in range(len(self.documents)):
            d = self.document_vector(i)
            scores.append(sum(weights.get(t, 0) * v for t, v in zip(d.indices, d.values, strict=True)))
        return scores


def fuse_rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    if k <= 0:
        raise ValueError("invalid_rank_constant")
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, identity in enumerate(dict.fromkeys(ranking), start=1):
            scores[identity] = scores.get(identity, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
