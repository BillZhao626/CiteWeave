"""Generate the README SVG without HTML labels or browser-specific Mermaid sizing."""

from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs/assets/architecture/readme-architecture.svg"


def build_svg():
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="1260" '
        'viewBox="0 0 1160 1260" role="img" aria-labelledby="title desc">',
        '<title id="title">CiteWeave query and ingestion architecture</title>',
        '<desc id="desc">History and Working State interpret the request. Dense and BM25 '
        "retrieval, RRF and BGE rerank form current EvidencePack. Authorized generation, "
        "citation validation and atomic Acceptance publish PostgreSQL state. Ingestion "
        "uses PostgreSQL jobs, Redis/Celery, LocalBlobStore and a rebuildable Qdrant index; "
        "visibility requires a durable READY commit.</desc>",
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" '
        'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
        '<path d="M1 1 L8 5 L1 9" fill="none" stroke="#64748b" stroke-width="1.5"/>'
        "</marker></defs>",
        '<rect width="1160" height="1260" fill="#fff"/>',
        '<g font-family="Arial, Helvetica, sans-serif" fill="#172f34">',
    ]

    def text(x, y, label, size=22, weight=400, color="#172f34"):
        parts.append(
            f'<text x="{x}" y="{y}" text-anchor="middle" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{escape(label)}</text>'
        )

    def node(x, y, width, lines, height=64):
        parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="5" '
            'fill="#f5f8f7" stroke="#8ba59b" stroke-width="1.6"/>'
        )
        top = y + height / 2 - (len(lines) - 1) * 14 + 8
        for index, label in enumerate(lines):
            text(x + width / 2, top + index * 28, label)

    def arrow(path, dashed=False):
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        parts.append(
            f'<path d="{path}" fill="none" stroke="#64748b" stroke-width="1.8" '
            f'marker-end="url(#arrow)"{dash}/>'
        )

    text(329, 34, "QUERY / CONVERSATION", 20, 600)
    text(900, 34, "INGESTION", 20, 600)

    # Main request flow: explicit lines keep BGE and all other labels inside native SVG text.
    query = [
        (70, ["React Workspace"], 64),
        (170, ["FastAPI"], 64),
        (270, ["Conversation / Turn / Run"], 64),
        (370, ["Context Interpretation", "Relevant / Recent History", "Working State"], 108),
        (514, ["Dense + BM25", "RRF", "BGE rerank"], 108),
        (658, ["Current EvidencePack"], 64),
        (758, ["Authorized LLM generation"], 64),
        (858, ["Citation / original span validation"], 64),
        (958, ["Atomic Acceptance"], 64),
        (1058, ["PostgreSQL", "Business state / Run / Trace"], 88),
    ]
    for index, (y, lines, height) in enumerate(query):
        node(60, y, 538, lines, height)
        if index:
            previous_y, _, previous_height = query[index - 1]
            arrow(f"M329 {previous_y + previous_height} V{y - 3}")

    # PostgreSQL readers return to both request admission and the authorized workspace.
    arrow("M60 1102 H28 V102 H57", True)
    arrow("M28 302 H57", True)
    text(329, 1204, "History / State: intent   |   Current Evidence: factual support", 18)

    node(706, 70, 388, ["PDF Upload"])
    arrow("M706 102 H662 V202 H601")
    node(706, 270, 388, ["PostgreSQL Job", "Immutable DocumentVersion"], 88)
    arrow("M598 202 H650 V314 H703")
    node(706, 394, 388, ["Redis / Celery"])
    arrow("M900 358 V391")
    node(706, 494, 388, ["Parse / Chunk", "Encode / Index"], 88)
    arrow("M900 458 V491")
    node(706, 618, 388, ["Qdrant", "Rebuildable index"], 88)
    arrow("M900 582 V615")
    arrow("M706 662 H670 V568 H601")
    node(706, 742, 388, ["PostgreSQL READY commit", "Index becomes queryable"], 88)
    arrow("M900 706 V739")

    # Storage is a separate API-owned adapter; Celery and Redis do not own business state.
    node(706, 890, 388, ["LocalBlobStore"])
    arrow("M598 202 H1128 V922 H1097")
    arrow("M1094 922 H1112 V538 H1097")
    node(706, 1010, 388, ["Evidence / original PDF"])
    arrow("M900 954 V1007")
    text(900, 1174, "PostgreSQL = business authority", 18)
    text(900, 1204, "Redis = recoverable task transport", 18)
    parts.append("</g></svg>\n")
    return "\n".join(parts)


def main():
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(build_svg(), encoding="utf-8")
    print(TARGET.relative_to(ROOT))


if __name__ == "__main__":
    main()
