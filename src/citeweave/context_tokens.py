"""Count the actual serialized prompt pack using the pinned real BGE tokenizer."""

import json

from citeweave.evidence import digest
from citeweave.structural_contract import QUERY_CONTRACT
from citeweave.tokenization import TOKENIZERS


class ContextTokenizer:
    def __init__(self, model):
        self.model = model

    def count(self, texts):
        batches, batch = [], []
        for text in texts:
            if batch and (
                len(batch) == 20
                or len(json.dumps(dict(contract=QUERY_CONTRACT, texts=[*batch, text])).encode()) > 128 * 1024
            ):
                batches.append(batch)
                batch = []
            batch.append(text)
        if batch:
            batches.append(batch)
        return [row for batch in batches for row in self._count(batch)]

    def _count(self, texts):
        response = self.model.call("/context-tokenize", dict(contract=QUERY_CONTRACT, texts=texts))
        if (
            response.get("contract") != QUERY_CONTRACT
            or response.get("tokenizers") != TOKENIZERS
            or response.get("hashes") != [digest(t) for t in texts]
        ):
            raise ValueError("context_tokenizer_identity_mismatch")
        counts = response.get("counts")
        if (
            not isinstance(counts, list)
            or len(counts) != len(texts)
            or any(type(c) is not int or c < 0 for c in counts)
        ):
            raise ValueError("context_tokenizer_count_mismatch")
        return [{"bge": c} for c in counts]
