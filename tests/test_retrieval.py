import pytest

from citeweave.retrieval import BM25Encoder, fuse_rrf, tokenize


def test_rrf_single_vote_and_one_based_formula():
    scores = dict(fuse_rrf([["b", "b", "a"], ["a", "b"]]))
    assert scores["a"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["a"] == scores["b"]
    assert fuse_rrf([["b", "a"], ["a", "b"]])[0][0] == "a"


def test_chinese_terms_and_protocol_numbers_survive():
    terms = tokenize("连接超时与TS 38.331，等待10秒，HTTP/2重试")
    assert "38.331" in terms
    assert "http/2" in terms
    assert "超时" in terms


def test_bm25_matches_hand_computed_scores_and_oov():
    encoder = BM25Encoder.fit(["alpha alpha beta", "beta", "gamma gamma gamma"])
    assert encoder.scores("alpha")[0] > 0
    assert encoder.scores("alpha")[1:] == [0, 0]
    assert encoder.query_vector("unknown").indices == []
    assert encoder.scores("") == [0, 0, 0]
    import math

    idf = math.log(1 + (3 - 1 + 0.5) / (1 + 0.5))
    expected = idf * 2 * 2.5 / (2 + 1.5 * (0.25 + 0.75 * 3 / (7 / 3)))
    assert encoder.scores("alpha")[0] == pytest.approx(expected)


def test_encoder_statistics_are_snapshot_specific():
    a = BM25Encoder.fit(["alpha", "beta"])
    b = BM25Encoder.fit(["alpha", "alpha"])
    assert a.fingerprint != b.fingerprint
    assert a.scores("alpha")[0] != b.scores("alpha")[0]
