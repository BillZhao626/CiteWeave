from copy import deepcopy

import pytest
from structure_fixtures import FixtureTokenizer

from citeweave.tokenization import CONTRACT, TOKENIZERS, fits, validate_response, validate_texts


def test_offset_identity_and_pair_nontruncation():
    texts = ["Original protocol example with emoji 🐈."]
    rows = FixtureTokenizer().count(texts)
    response = dict(contract=CONTRACT, tokenizers=TOKENIZERS, rows=rows)
    assert validate_response(texts, response) == rows
    assert fits(texts[0], rows[0])
    bad = deepcopy(response)
    bad["rows"][0]["e5_offsets"][0][1] = 999
    with pytest.raises(ValueError, match="offset"):
        validate_response(texts, bad)
    bad = deepcopy(response)
    bad["tokenizers"]["e5"]["revision"] = "other"
    with pytest.raises(ValueError, match="identity"):
        validate_response(texts, bad)
    for change in ({"e5": 193}, {"e5_input": 257}, {"bge": 321}, {"bge_pair_special": 300}):
        assert not fits(texts[0], {**rows[0], **change})


@pytest.mark.parametrize("texts", [[], ["x"] * 21, ["x" * 16385], [""], [42]])
def test_bounded_tokenizer_requests(texts):
    with pytest.raises(ValueError):
        validate_texts(texts)


def test_client_splits_parent_batches_by_transport_bytes():
    import json

    from citeweave.tokenization import GatewayTokenizer

    class Gateway:
        calls = []

        def call(self, route, body):
            assert len(json.dumps(body, ensure_ascii=False).encode()) <= 128 * 1024
            self.calls.append(body["texts"][:])
            return dict(
                contract=CONTRACT, tokenizers=TOKENIZERS, rows=FixtureTokenizer().count(body["texts"])
            )

    gateway = Gateway()
    rows = GatewayTokenizer(gateway).count(["original " * 1500] * 20)
    assert len(rows) == 20 and len(gateway.calls) > 1
