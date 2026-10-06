// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  PublicationView,
  ReliabilityView,
  type Inspection,
} from "./publication-inspector";

afterEach(cleanup);
const created = "2026-10-04T00:00:00Z";
function inspection(): Inspection {
  return {
    revision: "conversation-inspection-v1",
    run: {
      revision: "conversation-api-v1",
      id: "original-run",
      conversation_id: "original-conversation",
      turn_id: "original-turn",
      retry_of: null,
      expected_head: null,
      status: "ACCEPTED",
      created_at: created,
      completed_at: created,
      deadline_elapsed: false,
      accepted: {
        revision: "conversation-result-v1",
        acceptance_id: "original-acceptance",
        conversation_id: "original-conversation",
        turn_id: "original-turn",
        run_id: "original-run",
        created_at: created,
        result: {
          kind: "clarification",
          text: "Original synthetic accepted answer",
        },
      },
    },
    publication: {
      decision: "PUBLISHED",
      acceptance_id: "original-acceptance",
      recorded_at: created,
      conversation_head_id: "original-acceptance",
      head_relation: "CURRENT",
      working_state: {
        snapshot_id: "original-acceptance",
        revision: "conversation-core-v1",
        source_turn_id: "original-turn",
        previous_snapshot_id: null,
        topic_signal: null,
        active_entries: null,
        retired_entries: null,
      },
    },
    trace: {
      revision: "conversation-trace-v1",
      conversation_id: "original-conversation",
      turn_id: "original-turn",
      run_id: "original-run",
      retry_of: null,
      input_head_id: null,
      acceptance_id: "original-acceptance",
      output_state_id: "original-acceptance",
      original_question: "Original synthetic question",
      scope: { kb_id: "original-kb", version_ids: ["original-version"] },
      persistence_profile: "conversation-core-v1",
      status: "ACCEPTED",
      created_at: created,
      completed_at: created,
      metadata_availability: "control_bundle",
      semantic_support: "NOT_ASSESSED",
      reliability_events: [],
      reliability_truncated: false,
      operational: {
        revision: "operational-trace-v1",
        timeline: [],
        truncated: false,
        durations: [],
        total: {
          phase: "total",
          availability: "AVAILABLE",
          latency_ms: 0,
          measurement: "db_timestamp_difference",
        },
        provider_phases: [],
        retry_decision: "TERMINAL_NO_DISPATCH",
        publication: "ACCEPTED",
        unknown_reason: null,
      },
    },
  };
}
describe("publication and reliability evidence presentation", () => {
  it("keeps a historical published answer when the head advances", () => {
    const value = inspection();
    value.publication.head_relation = "ADVANCED";
    value.publication.conversation_head_id = "later-acceptance";
    render(<PublicationView value={value} />);
    expect(screen.getByText("Original synthetic accepted answer")).toBeTruthy();
    expect(screen.getByText("后续轮次已推进 Conversation head")).toBeTruthy();
    expect(
      screen.queryByText("Conversation head 指向同一份 Acceptance"),
    ).toBeNull();
    expect(screen.getByText("later-acceptance")).toBeTruthy();
    const expand = screen.getByRole("button", { name: "查看完整答案" });
    fireEvent.click(expand);
    expect(
      screen
        .getByRole("button", { name: "收起答案" })
        .getAttribute("aria-expanded"),
    ).toBe("true");
  });
  it("does not invent legacy topic, entries or a publication timeline", () => {
    render(<PublicationView value={inspection()} />);
    expect(screen.getByText("此快照未记录主题信号")).toBeTruthy();
    expect(screen.getByText("未记录 / 未记录")).toBeTruthy();
    expect(screen.getByText("此历史记录未采集发布事件")).toBeTruthy();
    expect(screen.queryByText("ADMITTED → ACCEPTED")).toBeNull();
  });
  it("withholds answers and state when the requested attempt has no Acceptance", () => {
    const value = inspection();
    value.run.status = "FAILED";
    value.run.accepted = null;
    value.publication.decision = "NOT_PUBLISHED";
    value.publication.acceptance_id = null;
    value.publication.working_state = null;
    render(<PublicationView value={value} />);
    expect(screen.getByText("本次运行没有正式发布结果")).toBeTruthy();
    expect(screen.queryByText("Original synthetic accepted answer")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Working State" })).toBeNull();
  });
  it("distinguishes observed provider response without Acceptance from uncertain transport", () => {
    const value = inspection();
    value.run.status = "UNKNOWN";
    value.run.accepted = null;
    value.publication.decision = "NOT_PUBLISHED";
    value.publication.acceptance_id = null;
    value.publication.working_state = null;
    const op = value.trace.operational!;
    op.retry_decision = "BLOCKED_UNKNOWN";
    op.publication = "NOT_ACCEPTED";
    op.unknown_reason = "KNOWN_RESULT_NOT_ACCEPTED";
    const { rerender } = render(<ReliabilityView value={value} />);
    expect(screen.getByText("自动重发已阻止")).toBeTruthy();
    expect(screen.getByText("无正式结果发布")).toBeTruthy();
    expect(
      screen.getByText("上游响应已记录；后续处理未通过，未形成 Acceptance。"),
    ).toBeTruthy();
    expect(
      screen.getByText("此历史记录未采集事件，不重建执行过程。"),
    ).toBeTruthy();
    expect(screen.queryByRole("list", { name: "可靠性持久事件" })).toBeNull();
    op.unknown_reason = "PROVIDER_UNCERTAIN";
    rerender(<ReliabilityView value={value} />);
    expect(
      screen.getByText("上游执行结果无法确认；未形成 Acceptance。"),
    ).toBeTruthy();
    expect(
      screen.queryByText("上游响应已记录；后续处理未通过，未形成 Acceptance。"),
    ).toBeNull();
  });
});
