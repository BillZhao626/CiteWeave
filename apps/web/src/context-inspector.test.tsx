// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { ContextView, type ContextObservation } from "./context-inspector";
import type { Inspection } from "./publication-inspector";

afterEach(cleanup);
const ref = { acceptance_id: "prior-acceptance", turn_id: "prior-turn" };
function fixture(): { value: Inspection; context: ContextObservation } {
  const created = "2026-10-06T00:00:00Z";
  const value: Inspection = {
    revision: "conversation-inspection-v1",
    run: {
      revision: "conversation-api-v1",
      id: "current-run",
      conversation_id: "conversation",
      turn_id: "current-turn",
      retry_of: null,
      expected_head: ref.acceptance_id,
      status: "ACCEPTED",
      created_at: created,
      completed_at: created,
      deadline_elapsed: false,
      accepted: {
        revision: "conversation-result-v1",
        acceptance_id: "current-acceptance",
        conversation_id: "conversation",
        turn_id: "current-turn",
        run_id: "current-run",
        created_at: created,
        result: {
          kind: "documentary_answer",
          text: "Synthetic current answer",
          documents: [{ document_id: "doc", document_version_id: "version" }],
          citations: [],
        },
      },
    },
    publication: {
      decision: "PUBLISHED",
      acceptance_id: "current-acceptance",
      recorded_at: created,
      working_state: null,
      conversation_head_id: "current-acceptance",
      head_relation: "CURRENT",
    },
    trace: {
      revision: "conversation-trace-v1",
      conversation_id: "conversation",
      turn_id: "current-turn",
      run_id: "current-run",
      retry_of: null,
      input_head_id: ref.acceptance_id,
      acceptance_id: "current-acceptance",
      output_state_id: "current-acceptance",
      original_question: "那 DATA 帧呢？",
      scope: { kb_id: "kb", version_ids: ["version"] },
      persistence_profile: "conversation-core-v1",
      status: "ACCEPTED",
      created_at: created,
      completed_at: created,
      metadata_availability: "documentary_bundle",
      interpretation_mode: "USE_REWRITE",
      interpretation_identity: "interpretation-hash",
      selected_query: "那 DATA 帧呢？\nPrior protocol context",
      history_sources: [ref],
      input_state_item_ids: [],
      documents: [{ document_id: "doc", document_version_id: "version" }],
      evidence_ids: ["fresh-evidence-one", "fresh-evidence-two"],
      evidence_pack_identity: "current-pack",
      citations: [],
      validation: "CURRENT_PACK_PHYSICAL_ONLY",
      semantic_support: "NOT_ASSESSED",
      reliability_events: [],
      reliability_truncated: false,
    },
  };
  const context: ContextObservation = {
    revision: "context-observation-v1",
    run_id: "current-run",
    availability: "VERIFIED_LOCAL_RECEIPT",
    candidates: [
      {
        source: ref,
        question: "Original selected question",
        run_id: "prior-run",
        origins: ["A"],
        relevant: true,
        selected_group: true,
        recent_candidate: true,
      },
      {
        source: { acceptance_id: "noise-acceptance", turn_id: "noise-turn" },
        question: "Unrelated recent question",
        run_id: "noise-run",
        origins: ["A"],
        relevant: false,
        selected_group: false,
        recent_candidate: true,
      },
    ],
    relevant_sources: [ref],
    recent_sources: [
      ref,
      { acceptance_id: "noise-acceptance", turn_id: "noise-turn" },
    ],
    working_state: [],
    used_state_item_ids: [],
    references: [],
    inherited_facts: [
      { kind: "topic", value: "Prior protocol context", source: ref },
    ],
    topic_relation: "continue",
    dependency: "required",
  };
  return { value, context };
}

describe("read-only context truth", () => {
  it("shows real selection and does not promote recent noise to relevant", () => {
    const f = fixture();
    render(<ContextView {...f} />);
    const relevant = screen.getByRole("region", { name: "Relevant History" });
    expect(
      within(relevant).getByText("Original selected question"),
    ).toBeTruthy();
    expect(
      within(relevant).queryByText("Unrelated recent question"),
    ).toBeNull();
    expect(screen.getByText("仅近期候选 · 未选为 Relevant")).toBeTruthy();
    expect(screen.queryByText(/weight|权重|0\.\d/i)).toBeNull();
  });
  it("keeps current Evidence separate from history requests and inherited intent", () => {
    const f = fixture();
    render(<ContextView {...f} />);
    const evidence = screen.getByRole("region", { name: "Current Evidence" });
    expect(within(evidence).getByText("当前 Evidence 片段")).toBeTruthy();
    expect(within(evidence).getByText("2")).toBeTruthy();
    expect(
      within(evidence).queryByText("Original selected question"),
    ).toBeNull();
    expect(within(evidence).queryByText("Prior protocol context")).toBeNull();
  });
  it("shows empty state without generating content from old answers", () => {
    const f = fixture();
    render(<ContextView {...f} />);
    expect(
      screen.getByText("空 · 0 个输入状态项，0 个本轮使用项。"),
    ).toBeTruthy();
  });
  it("renders input state as used or unused according to real IDs", () => {
    const f = fixture();
    f.context.working_state = [
      {
        item: {
          id: "item-1",
          kind: "constraint",
          key: "budget",
          value: "Original state constraint",
          replaces: [],
        },
        introduced_by: ref,
        scope: { kb_id: "kb", version_ids: ["version"] },
        active: true,
      },
    ];
    f.context.used_state_item_ids = [];
    render(<ContextView {...f} />);
    expect(screen.getByText(/Original state constraint/)).toBeTruthy();
    expect(screen.getByText(/输入中存在 · 本轮未使用/)).toBeTruthy();
    expect(
      screen.queryByText("空 · 0 个输入状态项，0 个本轮使用项。"),
    ).toBeNull();
  });
  it("distinguishes missing observations from empty inputs", () => {
    const f = fixture();
    f.context = {
      revision: "context-observation-v1",
      run_id: "current-run",
      availability: "NOT_RECORDED",
    };
    render(<ContextView {...f} />);
    expect(
      screen.getByText("候选参与情况未记录 / 无法核对，不能按时间顺序推断。"),
    ).toBeTruthy();
    expect(
      screen.queryByText("空 · 0 个输入状态项，0 个本轮使用项。"),
    ).toBeNull();
  });
});
