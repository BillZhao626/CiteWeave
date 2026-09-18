"""Freeze source-grounded new questions before opening any candidate holdout results."""

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from citeweave.evidence import Scope, bind_span, resolve_span
from citeweave.parsing import parse_simple_pdf
from citeweave.settings import ROOT


def lines(source, page, *numbers):
    return [(source, f"page-{page}-line-{n}") for n in numbers]


# Authored against original RFC text and inspected local rendering, not any model output.
QUESTIONS = [
    (
        "multi_evidence",
        "RFC 2606 为测试和文档保留了哪四个顶级域名？",
        "The four TLDs are .test, .example, .invalid, and .localhost.",
        lines(2606, 1, 19, 20, 21, 22, 23, 24),
    ),
    (
        "direct",
        "按 RFC 2606，.test 推荐用于测试哪类代码？",
        "Testing current or new DNS-related code.",
        lines(2606, 1, 25, 26),
    ),
    (
        "multi_evidence",
        "RFC 2606 中 .example 与 .invalid 的预定用途有什么区别？",
        ".example is for documentation/examples; .invalid is for constructing domain names that are certainly and obviously invalid.",
        lines(2606, 1, 27, 28, 29, 30),
    ),
    (
        "multi_evidence",
        "RFC 2606 描述 .localhost 传统上具有哪类 DNS 记录、指向什么地址？",
        "A statically defined A record pointing to the loopback IP address.",
        lines(2606, 1, 31, 32, 33),
    ),
    (
        "localization",
        "请定位 RFC 2606 第 3 节列出的三个保留示例二级域名。",
        "example.com, example.net, and example.org.",
        lines(2606, 2, 1, 2, 3),
    ),
    (
        "boundary",
        "依据 RFC 2606，本地测试随意使用目前未用的 TLD，为什么可能影响以后访问真实 DNS 数据？",
        "The TLD may later enter real global use, and local test versions can thwart attempts to reference the real data.",
        lines(2606, 1, 7, 8, 9, 10, 11, 12),
    ),
    (
        "direct",
        "RFC 2606 的 IANA Considerations 记录 IANA 同意采取什么措施？",
        "IANA agreed to the four TLD reservations and will reserve them for the indicated uses.",
        lines(2606, 2, 5, 6, 7),
    ),
    (
        "multi_evidence",
        "按 RFC 8174，关键词全大写与未大写时分别按什么含义理解？",
        "Only all-capital keywords have the defined special meanings; otherwise they retain their normal English meanings and are unaffected by this document.",
        lines(8174, 2, 24, 25, 26, 27),
    ),
    (
        "boundary",
        "RFC 8174 是否要求规范性文本必须包含 MUST 等关键词才算规范性内容？",
        "No. Such keywords are optional; text can still be normative without using them.",
        lines(8174, 2, 19, 20, 21, 22, 23),
    ),
    (
        "multi_evidence",
        "RFC 8174 更新了哪个 RFC，并属于哪个 BCP？",
        "It updates RFC 2119 and is part of BCP 14.",
        lines(8174, 1, 25, 26, 27),
    ),
    (
        "multi_evidence",
        "RFC 8174 是否要求 IANA 操作，它是否提出相关安全事项？",
        "It requires no IANA actions and is purely procedural with no related security considerations.",
        lines(8174, 3, 2, 4, 5),
    ),
    (
        "direct",
        "RFC 8174 建议的声明引用哪两份 RFC，并在什么大小写条件下解释关键词？",
        "BCP 14 cites RFC 2119 and RFC 8174, when and only when the keywords appear in all capitals.",
        lines(8174, 2, 30, 31, 32, 33, 34),
    ),
    (
        "direct",
        "RFC 7405 的 ABNF 字符串前缀 %s 和 %i 分别表示什么？",
        "%s means case-sensitive; %i means case-insensitive.",
        lines(7405, 2, 13, 14),
    ),
    (
        "boundary",
        "按 RFC 7405，不带前缀的 ABNF 字符串是否区分大小写，等价于哪个前缀？",
        "It is case-insensitive and equivalent to the %i prefix, preserving prior behavior.",
        lines(7405, 2, 15, 16, 17),
    ),
    (
        "boundary",
        '依据 RFC 7405，规则 %s"aBc" 能匹配 abc 或 ABC 吗？它只匹配什么？',
        "No. It matches only aBc, not abc or ABC.",
        lines(7405, 2, 25, 26, 27),
    ),
    (
        "direct",
        "RFC 7405 说明旧 ABNF 怎样表达区分大小写的字符串，为什么需要改进？",
        "Using numeric representations of individual characters, which is inconvenient and error-prone to write and read.",
        lines(7405, 1, 13, 14, 15, 16),
    ),
    ("direct", "RFC 7405 的 literal text strings 使用哪个字符集？", "US-ASCII.", lines(7405, 2, 8)),
    (
        "multi_evidence",
        "RFC 7405 示例中 %d97 %d98 %d99 与 %x61.62.63 都只匹配哪个字符串？",
        "They both match only the lowercase string abc.",
        lines(7405, 3, 2, 4, 5, 6),
    ),
    (
        "cross_document",
        "分别依据 RFC 2606 和 RFC 7405：文档示例推荐哪个 TLD，区分大小写的字符串用哪个前缀？",
        "Use .example for documentation/examples, and %s for case-sensitive string matching.",
        lines(2606, 1, 27) + lines(7405, 2, 13),
    ),
    (
        "cross_document",
        "分别依据 RFC 8174 和 RFC 7405：未大写关键词如何解释，不带前缀的 ABNF 字符串如何匹配？",
        "Non-capitalized keywords have normal English meanings; unprefixed ABNF strings use case-insensitive matching equivalent to %i.",
        lines(8174, 2, 26, 27) + lines(7405, 2, 15, 16, 17),
    ),
    (
        "unanswerable",
        "仅依据这些 RFC，example.com 在 2026 年 9 月 17 日实际解析到哪个 IPv6 地址？",
        "The documents do not provide a live 2026 DNS resolution result.",
        [],
    ),
    (
        "unanswerable",
        "这些 RFC 为生产递归 DNS 服务指定的运维管理员登录密码是什么？",
        "The documents contain no production administrator password.",
        [],
    ),
    (
        "unanswerable",
        "仅依据 RFC 7405，它指定使用哪个 Python 库实现 ABNF 解析器？",
        "RFC 7405 specifies syntax rather than a required Python implementation library.",
        [],
    ),
    (
        "unanswerable",
        "仅依据 RFC 8174，它为违规使用小写 must 的作者规定了多少元罚款？",
        "The RFC provides capitalization interpretation rules, not a monetary fine.",
        [],
    ),
]


def main():
    target = ROOT / "evals/public-protocols-holdout-v1.json"
    if target.exists():
        raise ValueError("holdout_already_frozen_do_not_overwrite")
    folder = ROOT / ".runtime/evaluation/holdout-corpus"
    sources = json.loads((folder / "render-manifest.json").read_text())
    scope = Scope(workspace_id=UUID(int=1), kb_id=UUID(int=2), revision_id=UUID(int=3))
    by_source = {
        int(s["source_id"][3:]): {b.block_id: b for b in parse_simple_pdf(folder / s["filename"], scope)}
        for s in sources
    }
    cases = []
    for index, (kind, question, reference, targets) in enumerate(QUESTIONS, 1):
        gold = []
        for source, block_id in targets:
            block = by_source[source][block_id]
            start, end = len(block.text) - len(block.text.lstrip()), len(block.text.rstrip())
            span = bind_span(block, start, end, block.text[start:end])
            assert resolve_span(span, block, scope) == span.quote
            gold.append(
                dict(
                    source_id=f"rfc{source}",
                    source_sha256=block.source_sha256,
                    page_index=block.boxes[0].page_index,
                    block_id=block_id,
                    start_offset=start,
                    end_offset=end,
                    quote=span.quote,
                )
            )
        assert 0 < len(question) <= 160 and bool(gold) == (kind != "unanswerable")
        cases.append(
            dict(
                case_id=f"cw-holdout-{index:03d}",
                split="test",
                question_type=kind,
                question=question,
                reference_answer=reference,
                answerable=bool(gold),
                gold=gold,
            )
        )
    document = dict(
        dataset_id="public-protocols-holdout-v1",
        schema_version=1,
        frozen_at=datetime.now(timezone.utc).isoformat(),
        sources=sources,
        cases=cases,
        split_policy="New documents/questions. Test-only procedural holdout; no results may be opened before final candidate source freeze. Old public-standards Test is regression-only.",
        provenance="AI-authored reference answers checked against literal official RFC text and local PDF spans. No human-independent adjudication or independent annotation is claimed. Same RFC genre and model pretraining familiarity limit generalization. Original notices retained in local PDFs; raw text/PDF files are excluded from public candidate.",
    )
    raw = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()
    target.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    target.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
    report = dict(
        status="FROZEN_UNOPENED",
        at=document["frozen_at"],
        dataset_id=document["dataset_id"],
        sha256=digest,
        cases=len(cases),
        sources=len(sources),
        physical_pages=sum(s["pages"] for s in sources),
        chunks=sum(s["chunks"] for s in sources),
        exact_gold_spans=sum(len(c["gold"]) for c in cases),
        by_type=dict(Counter(c["question_type"] for c in cases)),
        model_results_opened=False,
        gold_provenance=document["provenance"],
    )
    (ROOT / "docs/reports/m3-revisit/holdout-freeze.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
