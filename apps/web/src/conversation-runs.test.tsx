// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { api } from "./api";
import {
  ConversationRunsPage,
  ConversationRunSummary,
  type Inspection,
} from "./conversation-runs";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const created = "2026-10-05T00:00:00Z";
const rows = [
  {
    run_id: "first-run",
    conversation_id: "clean-conversation",
    turn_id: "first-turn",
    question: "First original synthetic question",
    status: "ACCEPTED",
    created_at: created,
    completed_at: created,
    publication: "PUBLISHED",
  },
  {
    run_id: "second-run",
    conversation_id: "clean-conversation",
    turn_id: "second-turn",
    question: "Second original synthetic question",
    status: "ACCEPTED",
    created_at: created,
    completed_at: created,
    publication: "PUBLISHED",
  },
  {
    run_id: "other-run",
    conversation_id: "other-conversation",
    turn_id: "other-turn",
    question: "Other scope question",
    status: "FAILED",
    created_at: created,
    completed_at: created,
    publication: "NOT_PUBLISHED",
  },
];
function inspection(index = 0): Inspection {
  const row = rows[index];
  return {
    revision: "conversation-inspection-v1",
    run: {
      revision: "conversation-api-v1",
      id: row.run_id,
      conversation_id: row.conversation_id,
      turn_id: row.turn_id,
      retry_of: null,
      expected_head: null,
      status: "ACCEPTED",
      created_at: created,
      completed_at: created,
      deadline_elapsed: false,
      accepted: {
        revision: "conversation-result-v1",
        acceptance_id: "synthetic-acceptance",
        conversation_id: row.conversation_id,
        turn_id: row.turn_id,
        run_id: row.run_id,
        created_at: created,
        result: {
          kind: "clarification",
          text: "Original synthetic safe result",
        },
      },
    },
    publication: {
      decision: "PUBLISHED",
      acceptance_id: "synthetic-acceptance",
      recorded_at: created,
      conversation_head_id: "synthetic-acceptance",
      head_relation: "CURRENT",
      working_state: null,
    },
    trace: {
      revision: "conversation-trace-v1",
      conversation_id: row.conversation_id,
      turn_id: row.turn_id,
      run_id: row.run_id,
      retry_of: null,
      input_head_id: null,
      acceptance_id: "synthetic-acceptance",
      output_state_id: "synthetic-acceptance",
      original_question: row.question,
      scope: { kb_id: "synthetic-kb", version_ids: ["synthetic-version"] },
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
          latency_ms: 1170,
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
function page(run = "first-run") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <MemoryRouter
      initialEntries={[
        `/runs?view=conversation&conversation=clean-conversation&run=${run}`,
      ]}
    >
      <QueryClientProvider client={client}>
        <ConversationRunsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}
function readMock(transform = (value: Inspection) => value) {
  return vi.spyOn(api, "GET").mockImplementation(async (path, options) => {
    const ids = options as { params?: { path?: { run_id?: string } } };
    const data =
      String(path) === "/v1/runtime/conversation-runs"
        ? rows
        : transform(
            inspection(ids?.params?.path?.run_id === "second-run" ? 1 : 0),
          );
    return { data, response: new Response("", { status: 200 }) } as never;
  });
}
it("reads the selected conversation and Run without dispatch, and follows another real selection", async () => {
  const get = readMock();
  const post = vi.spyOn(api, "POST");
  page();
  await screen.findByText("1.17 s");
  expect(screen.queryByText("Other scope question")).toBeNull();
  expect(
    screen.getByRole("link", { name: "检查发布记录 →" }).getAttribute("href"),
  ).toBe("/runtime/publication?run=first-run");
  fireEvent.click(screen.getByRole("button", { name: "查看运行 second-run" }));
  await waitFor(() =>
    expect(
      screen.getByRole("link", { name: "检查发布记录 →" }).getAttribute("href"),
    ).toBe("/runtime/publication?run=second-run"),
  );
  expect(
    (get.mock.calls as unknown[][]).every(
      ([path]) =>
        String(path) === "/v1/runtime/conversation-runs" ||
        String(path).endsWith("/inspection"),
    ),
  ).toBe(true);
  expect(post).not.toHaveBeenCalled();
});
it("does not display a summary from a mismatched durable identity", async () => {
  readMock((value) => ({
    ...value,
    trace: { ...value.trace, run_id: "unrelated-run" },
  }));
  page();
  expect((await screen.findByRole("alert")).textContent).toContain(
    "身份与所选记录不一致",
  );
  expect(screen.queryByRole("region", { name: "所选会话运行摘要" })).toBeNull();
});
it("does not silently substitute another Run when it is outside the current conversation", async () => {
  const get = readMock();
  page("other-run");
  expect((await screen.findByRole("alert")).textContent).toContain(
    "所选 Run 不在当前页与会话范围内",
  );
  expect(screen.queryByRole("region", { name: "所选会话运行摘要" })).toBeNull();
  expect(
    (get.mock.calls as unknown[][]).every(
      ([path]) => String(path) === "/v1/runtime/conversation-runs",
    ),
  ).toBe(true);
});
it("keeps missing historical measurements unavailable rather than inventing zeros", () => {
  const value = inspection();
  value.trace.operational = undefined;
  render(
    <MemoryRouter>
      <ConversationRunSummary value={value} />
    </MemoryRouter>,
  );
  expect(screen.getAllByText("未记录")).toHaveLength(4);
  expect(screen.queryByText("0.00 s")).toBeNull();
});
