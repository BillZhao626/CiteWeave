"""Provider-free real contexts and financial proposal; never a Human grant."""

import json

from citeweave.evaluation.dev_approval import load_human_gold
from citeweave.evaluation.dev_dataset import canonical
from citeweave.evaluation.dev_environment import bind_environment
from citeweave.evaluation.dev_real import prepare_contracts
from citeweave.provider_accounting import DeepSeekAccounting
from citeweave.settings import ROOT


def main():
    # Explicitly no provider construction: all model work is local E5/BGE.
    data, _, _ = load_human_gold(ROOT)
    bind_environment()
    accounting = DeepSeekAccounting(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    )
    packet = prepare_contracts(ROOT, data, accounting)
    folder = ROOT / ".runtime/evaluation/v02-dev-paid-remediation"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "contracts-head0012.json"
    if path.exists() and json.loads(path.read_bytes()) != packet:
        raise ValueError("dev_contract_receipt_immutable")
    if not path.exists():
        path.write_bytes(canonical(packet))
    print(
        json.dumps(
            {
                k: packet[k]
                for k in (
                    "max_calls",
                    "expected_calls",
                    "stage_input_max",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "maximum_yuan",
                    "external_calls",
                )
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("DEV contract preparation failed:", type(exc).__name__)
        raise SystemExit(1) from None
