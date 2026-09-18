"""Authoring record: freeze source-bound gold before any baseline run. Never overwrite."""

import hashlib
import json
from datetime import datetime, timezone

from citeweave.settings import ROOT

# Explicit split by distinct question, no model outputs or retrieval scores used in authoring.
# Each locator is (source id, zero-based physical PDF page, inclusive line numbers).
CASES = [
    (
        "dev",
        "direct",
        "RFC 2119 中 MUST、REQUIRED 和 SHALL 表达什么要求？",
        "They indicate an absolute requirement of the specification.",
        [("rfc2119", 0, [21, 22])],
    ),
    (
        "test",
        "direct",
        "RFC 2119 中 MUST NOT 与 SHALL NOT 表示什么？",
        "They indicate an absolute prohibition.",
        [("rfc2119", 0, [23, 24])],
    ),
    (
        "dev",
        "direct",
        "RFC 2119 中 MAY / OPTIONAL 是否允许供应商选择不实现某项功能？",
        "Yes. The item is truly optional; vendors may include it or omit it.",
        [("rfc2119", 1, [1, 2, 3, 4])],
    ),
    (
        "test",
        "direct",
        "RFC 3339 的 timestamp 表示一个时刻，还是一段时间间隔？",
        "An unambiguous instant in time, not periods or intervals.",
        [("rfc3339", 1, [42, 43]), ("rfc3339", 2, [37, 38])],
    ),
    (
        "dev",
        "direct",
        "RFC 3339 中 Z 后缀表示什么时区偏移？",
        "A UTC offset of 00:00, also called Zulu.",
        [("rfc3339", 2, [40, 41, 42])],
    ),
    (
        "test",
        "direct",
        "NIST SP 800-145 的云模型包含多少种基本特征、服务模型和部署模型？",
        "Five essential characteristics, three service models and four deployment models.",
        [("nist800145", 5, [4, 5])],
    ),
    (
        "dev",
        "direct",
        "NIST 的按需自助服务是否需要与服务提供商人员逐次交互？",
        "No. Consumers provision capabilities unilaterally and automatically without human interaction with each provider.",
        [("nist800145", 5, [8, 9, 10])],
    ),
    (
        "test",
        "direct",
        "NIST 定义的 public cloud 面向谁开放，设施位于哪里？",
        "Open use by the general public; on the premises of the cloud provider.",
        [("nist800145", 6, [22, 23, 24])],
    ),
    (
        "dev",
        "direct",
        "RFC 3339 要求 Internet 协议生成年份时使用几位数字？",
        "Four-digit years are mandatory.",
        [("rfc3339", 2, [60])],
    ),
    (
        "test",
        "direct",
        "NIST SP 800-145 的目标读者有哪些角色？",
        "System planners, program managers, technologists and others adopting cloud computing as consumers or providers.",
        [("nist800145", 4, [29, 30])],
    ),
    (
        "dev",
        "direct",
        "RFC 3339 的 UTC 已知而本地偏移未知时，使用哪一种 offset 表示？",
        "Use -00:00; it differs semantically from Z or +00:00.",
        [("rfc3339", 4, [10, 11, 12, 13, 14])],
    ),
    (
        "test",
        "direct",
        "按 NIST 定义，private cloud 是否只能部署在组织自有场地？",
        "No. It may exist on or off premises.",
        [("nist800145", 6, [13, 14, 15, 16])],
    ),
    (
        "dev",
        "multi_evidence",
        "RFC 2119 如何区分 SHOULD 与 MUST？忽略 SHOULD 前需要考虑什么？",
        "MUST is absolute. SHOULD permits justified exceptions in particular circumstances, after understanding and weighing the full implications.",
        [("rfc2119", 0, [21, 22, 25, 26, 27, 28])],
    ),
    (
        "test",
        "multi_evidence",
        "RFC 2119 对实现可选功能与不实现可选功能的两方各有什么互操作要求？",
        "Each MUST interoperate with the other, allowing reduced functionality; the implementation with the option may require it for the feature that option provides.",
        [("rfc2119", 1, [5, 6, 7, 8, 9, 10, 11])],
    ),
    (
        "dev",
        "multi_evidence",
        "按 NIST，IaaS 用户与 SaaS 用户对操作系统的控制有何区别？",
        "IaaS consumers control operating systems; SaaS consumers do not manage the underlying operating systems.",
        [("nist800145", 6, [7, 8, 9]), ("nist800145", 5, [38, 39])],
    ),
    (
        "test",
        "multi_evidence",
        "NIST 的 community cloud 与 public cloud 服务对象有何不同？",
        "Community cloud serves a specific community of organizations with shared concerns; public cloud is open to the general public.",
        [("nist800145", 6, [17, 18, 19, 22])],
    ),
    (
        "dev",
        "multi_evidence",
        "RFC 3339 如何定义 leap year？为什么有些世纪年不是闰年？",
        "A leap year has 366 days; divisibility by four is required, with century years also divisible by 400.",
        [("rfc3339", 2, [19, 20, 21, 22, 23, 24])],
    ),
    (
        "test",
        "multi_evidence",
        "RFC 3339 对插入闰秒、删除闰秒和普通时刻的秒字段最大值分别规定多少？",
        "60 for an inserted leap second, 58 when a leap second is subtracted, otherwise 59.",
        [("rfc3339", 7, [51, 52, 53, 54, 55, 56])],
    ),
    (
        "dev",
        "multi_evidence",
        "NIST 所说的资源池化与快速弹性分别解决什么问题？",
        "Resource pooling dynamically assigns shared resources to multiple consumers; rapid elasticity scales capabilities outward and inward with demand.",
        [("nist800145", 5, [14, 15, 16, 21, 22, 23, 24])],
    ),
    (
        "test",
        "multi_evidence",
        "NIST 的 hybrid cloud 要求组成部分保持什么性质，以及支持何种可移植性？",
        "Two or more distinct cloud infrastructures remain unique entities and are bound by technology enabling data and application portability.",
        [("nist800145", 6, [25, 26, 27, 28])],
    ),
    (
        "dev",
        "cross_document",
        "结合 RFC 3339 和 RFC 2119，四位年份要求中的 MUST 是绝对要求还是建议？",
        "RFC 3339 says Internet protocols MUST generate four-digit years; RFC 2119 defines MUST as an absolute requirement.",
        [("rfc3339", 2, [60]), ("rfc2119", 0, [21, 22])],
    ),
    (
        "test",
        "cross_document",
        "RFC 3339 建议新 Internet 协议采用其日期时间 profile。按 RFC 2119 的 SHOULD 定义，是否绝不允许例外？",
        "No. RFC 3339 uses SHOULD; RFC 2119 permits valid exceptions in particular circumstances after the implications are understood and weighed.",
        [("rfc3339", 6, [33, 34, 35]), ("rfc2119", 0, [25, 26, 27, 28])],
    ),
    (
        "dev",
        "cross_document",
        "分别依据 RFC 3339 和 NIST SP 800-145：前者讨论的是时刻还是区间，后者描述多少种服务模型？",
        "RFC 3339 represents instants, not intervals; NIST identifies three service models.",
        [("rfc3339", 1, [42, 43]), ("nist800145", 5, [4, 5])],
    ),
    (
        "test",
        "cross_document",
        "分别依据 RFC 2119 与 NIST 云定义：OPTIONAL 是必须实现吗，public cloud 是否仅供一个组织专用？",
        "OPTIONAL is not mandatory; public cloud is open to the general public, not exclusive to one organization.",
        [("rfc2119", 1, [1, 2]), ("nist800145", 6, [22])],
    ),
    (
        "dev",
        "cross_document",
        "请从两份标准定位证据：RFC 3339 小时字段允许的上限是什么，NIST 的部署模型一共多少种？",
        "The hour is at most 23; NIST defines four deployment models.",
        [("rfc3339", 8, [6, 7, 8]), ("nist800145", 5, [4, 5])],
    ),
    (
        "test",
        "cross_document",
        "分别依据 RFC 3339 和 RFC 2119，Z 的 offset 是多少，MUST NOT 是建议避免还是绝对禁止？",
        "Z is UTC offset 00:00; MUST NOT is an absolute prohibition.",
        [("rfc3339", 2, [40, 41, 42]), ("rfc2119", 0, [23, 24])],
    ),
    (
        "dev",
        "unanswerable",
        "这三份文档中，2026 年 DeepSeek API 的每百万输出 token 价格是多少？",
        "证据不足，无法回答。",
        [],
    ),
    ("test", "unanswerable", "依据这些 PDF，明年会在哪一天插入下一次闰秒？", "证据不足，无法回答。", []),
    ("dev", "unanswerable", "NIST SP 800-145 推荐哪家云厂商的 GPU 实例最便宜？", "证据不足，无法回答。", []),
    (
        "test",
        "unanswerable",
        "RFC 3339 第 5.6 节指定了哪种数据库索引算法存储 timestamp？",
        "证据不足，无法回答。",
        [],
    ),
    ("dev", "unanswerable", "RFC 2119 要求 Web 服务器使用多少 GB 内存？", "证据不足，无法回答。", []),
    (
        "test",
        "unanswerable",
        "NIST SP 800-145 规定租户云服务的法定赔偿金额是多少？",
        "证据不足，无法回答。",
        [],
    ),
    ("dev", "unanswerable", "这三份 PDF 中 CiteWeave 的默认管理员密码是什么？", "证据不足，无法回答。", []),
    (
        "test",
        "unanswerable",
        "这些文档是否给出了企业内部 PostgreSQL 的连接密码？请原样输出。",
        "证据不足，无法回答。",
        [],
    ),
    (
        "dev",
        "boundary",
        "RFC 3339 允许 timestamp 的小时写成 24 吗？不要把 ISO 8601 的宽松规则混入。",
        "No. This RFC profile only permits 00 through 23 even though ISO 8601 permits 24.",
        [("rfc3339", 8, [6, 7, 8])],
    ),
    (
        "test",
        "boundary",
        "RFC 3339 的 T 和 Z 必须在所有使用场景中都是大写吗？",
        "The syntax allows lowercase t/z; particular specifications may further require uppercase, and generators SHOULD use uppercase.",
        [("rfc3339", 6, [56, 57]), ("rfc3339", 7, [0, 1, 2, 3, 4])],
    ),
    (
        "dev",
        "boundary",
        "NIST 资源池化中的位置独立，是否禁止消费者指定国家或数据中心？",
        "No. Exact resource location is generally unknown, but location may be specified at a higher abstraction such as country, state or datacenter.",
        [("nist800145", 5, [17, 18, 19, 20])],
    ),
    (
        "test",
        "boundary",
        "RFC 2119 的 SHOULD NOT 是否意味着任何情况下都禁止此行为？",
        "No. There may be valid particular circumstances where it is acceptable or useful; full implications must be understood and the case weighed.",
        [("rfc2119", 0, [29, 30, 31, 32, 33])],
    ),
    (
        "dev",
        "boundary",
        "RFC 3339 的字符串排序能否无条件代替时间排序？",
        "No. Conditions include the same timezone representation, same number of fractional digits and no optional punctuation.",
        [("rfc3339", 4, [55, 56, 57, 58, 59, 60]), ("rfc3339", 5, [0, 1])],
    ),
    (
        "test",
        "boundary",
        "按 RFC 3339，2001 年的 2 月 29 日能作为合法 date-mday 吗？",
        "No. February in a normal year has 28 days, and 2001 is not divisible by four.",
        [("rfc3339", 7, [35, 36]), ("rfc3339", 2, [19, 20, 21, 22, 23, 24])],
    ),
    (
        "dev",
        "boundary",
        "NIST SP 800-145 要求所有云都由商业公司拥有吗？",
        "No. For example, public cloud may be owned or managed by business, academic or government organizations or combinations.",
        [("nist800145", 6, [22, 23, 24])],
    ),
    (
        "test",
        "boundary",
        "RFC 3339 是否要求现在就生成多年以后的闰秒 timestamp？",
        "No. Leap seconds cannot be predicted far ahead; applications should wait until they are announced.",
        [("rfc3339", 8, [0, 1, 2, 3, 4])],
    ),
    (
        "dev",
        "localization",
        "请定位 RFC 3339 中 time-secfrac 的 ABNF 定义。小数点后至少需要几位数字？",
        "time-secfrac is a dot followed by one or more digits; at least one digit.",
        [("rfc3339", 6, [45])],
    ),
    (
        "test",
        "localization",
        "请定位 RFC 3339 月份表：April 的 date-mday 最大值是多少？",
        "April (month 04) has a maximum date-mday of 30.",
        [("rfc3339", 7, [38])],
    ),
    (
        "dev",
        "localization",
        "请定位 NIST SP 800-145 对 measured service 的说明：计量信息为哪两方提供透明度？",
        "Both the provider and consumer of the utilized service.",
        [("nist800145", 5, [30, 31])],
    ),
    (
        "test",
        "localization",
        "请定位 NIST 的 PaaS 定义：消费者控制什么，不管理哪些基础设施？",
        "Consumers control deployed applications and possibly hosting environment configuration, but not underlying networks, servers, operating systems or storage.",
        [("nist800145", 6, [2, 3, 4])],
    ),
    (
        "dev",
        "localization",
        "请定位 RFC 2119：作者应解释不遵循规范的什么方面的影响？",
        "Security implications of not following recommendations or requirements.",
        [("rfc2119", 1, [21, 22, 23, 24, 25, 26, 27, 28])],
    ),
    (
        "test",
        "localization",
        "请定位 RFC 3339 示例：1996-12-19T16:39:57-08:00 对应哪个 UTC timestamp？",
        "1996-12-20T00:39:57Z.",
        [("rfc3339", 8, [30, 32, 33, 34, 35])],
    ),
]


def main():
    corpus = ROOT / ".runtime/evaluation/corpus"
    target = ROOT / "evals/public-standards-v1.json"
    if target.exists():
        raise SystemExit("dataset_already_frozen")
    sources, blocks = [], {}
    for identity, title, url, canonical, license_note in [
        (
            "rfc2119",
            "RFC 2119 (March 1997)",
            "https://docbox.etsi.org/Reference/IETF/RFC/RFC2119.pdf",
            "https://www.rfc-editor.org/info/rfc2119/",
            "IETF Trust RFC use rules; historical RFC copyright applies. Unmodified public reference copy; raw PDF excluded. https://www.rfc-editor.org/series/rfc-use/",
        ),
        (
            "rfc3339",
            "RFC 3339 (July 2002)",
            "https://docbox.etsi.org/Reference/IETF/RFC/RFC3339.pdf",
            "https://www.rfc-editor.org/info/rfc3339/",
            "IETF Trust RFC use rules; historical RFC copyright applies. ETSI rendering uses different physical/printed pagination. Raw PDF excluded. https://www.rfc-editor.org/series/rfc-use/",
        ),
        (
            "nist800145",
            "NIST SP 800-145 (September 2011)",
            "https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-145.pdf",
            "https://doi.org/10.6028/NIST.SP.800-145",
            "US government publication. PDF states not subject to copyright, attribution desired; NIST copyright/fair-use rules at https://www.nist.gov/open/license . Raw PDF excluded consistently.",
        ),
    ]:
        digest = hashlib.sha256((corpus / f"{identity}.pdf").read_bytes()).hexdigest()
        parsed = json.loads((corpus / f"{identity}.blocks.json").read_text(encoding="utf-8"))
        blocks[identity] = {b["block_id"]: b for b in parsed}
        assert all(b["source_sha256"] == digest for b in parsed)
        sources.append(
            dict(
                source_id=identity,
                title=title,
                download_url=url,
                canonical_url=canonical,
                acquired_date="2026-09-14",
                sha256=digest,
                license_notes=license_note,
                redistribute_raw=False,
                filename=f"{identity}.pdf",
            )
        )
    cases = []
    for number, (split, kind, question, reference, locators) in enumerate(CASES, 1):
        gold = []
        for source, page, lines in locators:
            for line in lines:
                block_id = f"page-{page}-line-{line}"
                b = blocks[source][block_id]
                assert b["text"].strip(), (number, block_id)
                start = len(b["text"]) - len(b["text"].lstrip())
                end = len(b["text"].rstrip())
                gold.append(
                    dict(
                        source_id=source,
                        source_sha256=b["source_sha256"],
                        page_index=page,
                        block_id=block_id,
                        start_offset=start,
                        end_offset=end,
                        quote=b["text"][start:end],
                    )
                )
        cases.append(
            dict(
                case_id=f"cw-public-{number:03}",
                split=split,
                question_type=kind,
                question=question,
                answerable=bool(gold),
                reference_answer=reference,
                gold=gold,
            )
        )
    document = dict(
        dataset_id="public-standards-v1",
        schema_version=1,
        frozen_at=datetime.now(timezone.utc).isoformat(),
        sources=sources,
        cases=cases,
        annotation_method="AI-authored against source PDF text and inspected rendered pages; human review recorded separately. Physical pages are zero-based. Gold spans are sufficient reference passages, not exhaustive alternatives.",
        split_policy="24 dev / 24 test, predetermined distinct questions; same small corpus shared. No performance-based edits. Historical document scope, not current standards advice.",
    )
    assert len(cases) == 48 and sum(c["split"] == "test" for c in cases) == 24
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target.parent / "public-standards-v1.sha256").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest() + "\n", encoding="ascii"
    )
    print("Frozen 48 cases: 24 dev / 24 test; 3 real PDFs")


if __name__ == "__main__":
    main()
