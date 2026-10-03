// @vitest-environment jsdom
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  AcceptedAnswer,
  ConversationPanel,
  TraceInspector,
} from "./conversation-panel";
import {
  ConversationSession,
  type ConversationTrace,
  type PublicRun,
} from "./conversation-session";
import type { Citation, Doc } from "./api";

vi.mock("./pdf-evidence", () => ({
  PdfEvidence: ({ citation }: { citation: Citation }) => (
    <div data-testid="pdf-location">
      {citation.content_url} · {citation.document_version_id} ·{" "}
      {citation.span.boxes[0].page_index}
    </div>
  ),
}));
afterEach(cleanup);
const citation: Citation = {
  label: "E1",
  evidence_id: "e1",
  document_version_id: "v1",
  filename: "original.pdf",
  content_url: "/v1/document-versions/v1/content",
  span: {
    id: "e1",
    scope: { workspace_id: "w", kb_id: "kb", revision_id: "v1" },
    block_id: "b",
    source_sha256: "a",
    canonical_text_sha256: "b",
    normalizer_revision: "n",
    start_offset: 0,
    end_offset: 4,
    quote: "Fact",
    quote_sha256: "c",
    locator_kind: "pdf_bbox",
    boxes: [{ page_index: 2, left: 0.1, top: 0.1, right: 0.5, bottom: 0.2 }],
    support_status: "not_assessed",
  },
};
const run: PublicRun = {
  revision: "conversation-api-v1",
  id: "r",
  conversation_id: "c",
  turn_id: "t",
  retry_of: null,
  expected_head: null,
  status: "ACCEPTED",
  created_at: "2026-09-30",
  completed_at: "2026-09-30",
  deadline_elapsed: false,
  accepted: {
    revision: "conversation-result-v1",
    acceptance_id: "a",
    conversation_id: "c",
    turn_id: "t",
    run_id: "r",
    created_at: "2026-09-30",
    result: {
      kind: "documentary_answer",
      text: "Answer [E1]",
      citations: [citation],
      documents: [{ document_id: "d", document_version_id: "v1" }],
    },
  },
};
const trace: ConversationTrace = {
  revision: "conversation-trace-v1",
  conversation_id: "c",
  turn_id: "t",
  run_id: "r",
  retry_of: null,
  input_head_id: null,
  acceptance_id: "a",
  output_state_id: "a",
  original_question: "Original question",
  scope: { kb_id: "kb", version_ids: ["v1"] },
  persistence_profile: "conversation-core-v1",
  status: "ACCEPTED",
  created_at: "2026-09-30",
  completed_at: "2026-09-30",
  metadata_availability: "control_bundle",
  semantic_support: "NOT_ASSESSED",
  reliability_events: [],
  reliability_truncated: false,
};
const doc: Doc = {
  id: "d",
  kb_id: "kb",
  title: "Original document",
  active_version_id: "v1",
  versions: [
    {
      version: {
        id: "v1",
        document_id: "d",
        kb_id: "kb",
        sequence: 1,
        filename: "original.pdf",
        license: "original",
        source_sha256: "a",
        status: "READY",
        chunk_count: 1,
        page_count: 3,
        profile: {},
        index_collection: null,
        created_at: "2026-09-30",
      },
      job: {
        id: "j",
        document_version_id: "v1",
        status: "READY",
        kind: "ingest",
        attempt: 1,
        max_attempts: 1,
        created_at: "2026-09-30",
        started_at: null,
        finished_at: null,
        error_code: null,
        error_message: null,
        pipeline_version: "fixture",
        events: [],
      },
    },
  ],
};

describe("accepted product surfaces", () => {
  it("renders documentary text with the existing citation parser and exact location", () => {
    const onSelect = vi.fn();
    render(<AcceptedAnswer run={run} selected={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "查看引用 E1" }));
    expect(onSelect).toHaveBeenCalledWith(citation);
    expect(screen.getByText("文档答案")).toBeTruthy();
    expect(screen.getByText(/第 3 页/)).toBeTruthy();
  });
  it.each(["clarification", "evidence_insufficient"] as const)(
    "renders %s with no documentary citations",
    (kind) => {
      render(
        <AcceptedAnswer
          run={{
            ...run,
            accepted: {
              ...run.accepted!,
              result: { kind, text: "Control response" },
            },
          }}
          selected={citation}
          onSelect={vi.fn()}
        />,
      );
      expect(screen.getByText("Control response")).toBeTruthy();
      expect(screen.queryByRole("button", { name: "查看引用 E1" })).toBeNull();
    },
  );
  it.each([
    "ADMITTED",
    "FAILED",
    "UNKNOWN",
    "CANCELLED",
    "INTERRUPTED",
    "STALE",
  ] as const)("never renders an answer as final for %s", (status) => {
    render(
      <AcceptedAnswer
        run={{ ...run, status }}
        selected={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByText("文档答案")).toBeNull();
    expect(screen.getByText("尚无此 Run 的已接受结果。")).toBeTruthy();
  });
  it("displays null Trace fields as unavailable and keeps the physical/semantic distinction", () => {
    const { rerender } = render(<TraceInspector trace={trace} />);
    expect(screen.getAllByText("未记录 / 不可用").length).toBeGreaterThan(3);
    expect(screen.queryByText("CLARIFY")).toBeNull();
    rerender(
      <TraceInspector
        trace={{
          ...trace,
          interpretation_mode: "USE_ORIGINAL",
          selected_query: "Original question",
          validation: "CURRENT_PACK_PHYSICAL_ONLY",
        }}
      />,
    );
    expect(screen.getByText("USE_ORIGINAL")).toBeTruthy();
    expect(screen.getByText(/≠ semantic support/)).toBeTruthy();
  });
  it("creates and submits once under StrictMode, rerender and refresh; reload uses GETs", async () => {
    const storage = {
      getItem: vi.fn((): string | null => null),
      setItem: vi.fn(),
    };
    const transport = {
      create: vi.fn(async () => ({
        revision: "conversation-api-v1" as const,
        id: "c",
        head_id: null,
        active_run_id: null,
        active_turn_id: null,
      })),
      conversation: vi.fn(async () => ({
        revision: "conversation-api-v1" as const,
        id: "c",
        head_id: "a",
        active_run_id: null,
        active_turn_id: null,
      })),
      submit: vi.fn(async () => run),
      run: vi.fn(async () => run),
      trace: vi.fn(async () => trace),
    };
    const session = new ConversationSession("kb", storage, transport);
    const panel = (
      <StrictMode>
        <ConversationPanel
          kbId="kb"
          docs={[doc]}
          selected={null}
          onSelect={vi.fn()}
          session={session}
        />
      </StrictMode>
    );
    const view = render(panel);
    expect(transport.create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("开始会话"));
    await waitFor(() => expect(screen.getByText("新会话")).toBeTruthy());
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.change(screen.getByLabelText("下一条问题或澄清回复"), {
      target: { value: "Original question" },
    });
    fireEvent.click(screen.getByText("发送会话问题"));
    await waitFor(() => expect(screen.getByText("文档答案")).toBeTruthy());
    view.rerender(panel);
    fireEvent.click(screen.getByText("刷新持久状态"));
    await waitFor(() => expect(session.getSnapshot().busy).toBe(false));
    expect(transport.create).toHaveBeenCalledTimes(1);
    expect(transport.submit).toHaveBeenCalledTimes(1);
    expect(transport.submit.mock.calls[0]).toEqual([
      "c",
      expect.any(String),
      {
        question: "Original question",
        expected_head: null,
        scope: { kb_id: "kb", version_ids: ["v1"] },
      },
    ]);
    const saved = storage.setItem.mock.calls.at(-1)!;
    storage.getItem.mockReturnValue(saved[1]);
    view.unmount();
    render(
      <StrictMode>
        <ConversationPanel
          kbId="kb"
          docs={[doc]}
          selected={citation}
          onSelect={vi.fn()}
          session={new ConversationSession("kb", storage, transport)}
        />
      </StrictMode>,
    );
    await waitFor(() => expect(screen.getByText("文档答案")).toBeTruthy());
    expect(screen.getByTestId("pdf-location").textContent).toContain(
      "/v1/document-versions/v1/content · v1 · 2",
    );
    expect(transport.submit).toHaveBeenCalledTimes(1);
  });
});
