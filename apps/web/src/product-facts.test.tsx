import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  candidateRanks,
  judgmentLabel,
  statusTone,
  type Run,
} from "./product-facts";
import { StructuralTrace } from "./structural-trace";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { components } from "./generated/api";

const candidate: components["schemas"]["StructuralCandidate"] = {
  candidate_id: "child-original",
  child_id: "child-original",
  document_id: "doc",
  version_id: "version",
  artifact_id: "artifact",
  parent_id: "parent",
  section_path: [{ number: "4.1", title: "Original fixture" }],
  evidence_ids: ["span-original"],
  retrieval: [
    { branch: "dense", rank: 3, raw_score: 0.6, score_scope: "build" },
    { branch: "bm25", rank: 2, raw_score: 7, score_scope: "build" },
  ],
  rrf_rank: 1,
  rrf_score: 0.03,
  pool_reason: "top20",
  seed_rank: 1,
  selection_reason: "selected",
  bge: {
    input_rank: 1,
    output_rank: 2,
    score: 0.7,
    model: { revision: "fixture" },
    pair_tokens: 20,
    body_tokens: 10,
    query_tokens: 5,
    queue_ms: 1,
    inference_ms: 2,
  },
};
describe("truthful product inspection", () => {
  it("does not color unknown or cancelled as successful", () => {
    expect(statusTone("OUTCOME_UNKNOWN")).toBe("failed");
    expect(statusTone("CANCELLED")).toBe("cancelled");
    expect(statusTone("COMPLETED_WITH_ERRORS")).not.toBe("ready");
  });
  it("preserves missing semantic judgment rather than zero", () => {
    expect(judgmentLabel({ status: "UNAVAILABLE" })).toContain("不是 0 分");
    expect(
      judgmentLabel({ status: "COMPLETED", scores: { correctness: 0 } }),
    ).toContain("判断可用");
  });
  it("uses structural branch ranks and suppresses BGE for degraded runs", () => {
    expect(candidateRanks(candidate, false)).toEqual({
      dense: 3,
      bm25: 2,
      rrf: 1,
      bge: 2,
      score: 0.7,
    });
    expect(candidateRanks(candidate, true).bge).toBeNull();
    expect(
      candidateRanks({ ...candidate, retrieval: [] }, false).dense,
    ).toBeNull();
  });
  it("renders Parent-added spans separately without invented ranks or citations", () => {
    const run = {
      id: "run",
      calls: [],
      structural_candidates: [candidate],
      structural_snapshot: { bindings: [] },
      evidence_pack: {
        seed_child_ids: ["child-original"],
        source_coverage: { coverage_unmet: false, missing: [] },
        spans: [
          {
            label: "E2",
            evidence_id: "parent-added",
            document_id: "doc",
            parent_id: "parent",
            seed_child_id: "child-original",
            origin: "sibling",
          },
        ],
        decisions: [],
        added_chars: 40,
        spans_count: 1,
      },
      result: null,
    } as unknown as Run;
    const html = renderToStaticMarkup(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <StructuralTrace run={run} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(html).toContain("parent-added");
    expect(html).toContain("没有独立检索排名");
    expect(html).toContain("未被最终答案引用");
    expect(html).not.toContain("查看引用 E2");
  });
});
