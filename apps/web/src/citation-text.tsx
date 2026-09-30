import type { Citation } from "./api";
import { citationForPart, citationParts } from "./citation-tokens";

export function CitationText({
  text,
  citations,
  selected,
  onSelect,
}: {
  text: string;
  citations: Citation[];
  selected: Citation | null;
  onSelect: (citation: Citation) => void;
}) {
  return citationParts(text).map((part, i) => {
    const citation = citationForPart(part, citations);
    return citation ? (
      <button
        key={i}
        className="inline-citation"
        aria-pressed={
          selected?.evidence_id === citation.evidence_id &&
          selected?.document_version_id === citation.document_version_id
        }
        title={`打开 ${citation.label} · ${citation.filename} 原文证据`}
        onClick={() => onSelect(citation)}
        aria-label={`查看引用 ${citation.label}`}
      >
        [{citation.label}]
      </button>
    ) : (
      part
    );
  });
}
