import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import {
  ConversationSession,
  type ConversationTransport,
  type PublicRun,
} from "./conversation-session";

const conversation = {
  revision: "conversation-api-v1" as const,
  id: "c",
  head_id: null as string | null,
  active_turn_id: null,
  active_run_id: null,
};
const scope = { kb_id: "kb", version_ids: ["v1"] };
function setup() {
  let saved: string | null = null;
  const storage = {
    getItem: () => saved,
    setItem: (_: string, value: string) => {
      saved = value;
    },
  };
  const accepted: PublicRun = {
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
      result: { kind: "clarification", text: "Which receiver?" },
    },
  };
  const api: ConversationTransport = {
    create: vi.fn(async () => ({ ...conversation })),
    conversation: vi.fn(async () => ({
      ...conversation,
      head_id: "durable-head",
    })),
    submit: vi.fn(async () => accepted),
    run: vi.fn(async () => accepted),
    trace: vi.fn(),
  };
  const session = new ConversationSession("kb", storage, api);
  return { session, api, storage, accepted };
}

describe("durable conversation session", () => {
  it("fails closed before dispatch when the recovery journal cannot be saved", async () => {
    const { api } = setup();
    const storage = {
      getItem: () => null,
      setItem: vi.fn<(key: string, value: string) => void>(() => {
        throw new Error("storage full");
      }),
    };
    const session = new ConversationSession("kb", storage, api);
    await session.start();
    expect(api.create).not.toHaveBeenCalled();
    expect(session.getSnapshot().notice).toContain("无法保存恢复记录");
    const key = JSON.parse(storage.setItem.mock.calls[0][1]).createKey;
    storage.setItem.mockImplementation(() => {});
    await session.start();
    expect(api.create).toHaveBeenCalledWith(key);
  });
  it("keeps a known Run across a failed readback and recovers using GET only", async () => {
    const { session, api } = setup();
    await session.start();
    vi.mocked(api.conversation).mockRejectedValueOnce(
      new TypeError("private transport body"),
    );
    await session.submit("question", scope);
    expect(session.getSnapshot().conversation).toBeUndefined();
    expect(session.getSnapshot().notice).not.toContain("private");
    expect(session.getSnapshot().pending?.runId).toBe("r");
    await session.recover();
    expect(session.getSnapshot().runs[0].status).toBe("ACCEPTED");
    expect(api.submit).toHaveBeenCalledTimes(1);
  });
  it("does not replay an unknown submission before durable refresh succeeds", async () => {
    const { session, api } = setup();
    await session.start();
    vi.mocked(api.submit).mockRejectedValueOnce(new TypeError("lost"));
    await session.submit("question", scope);
    vi.mocked(api.conversation).mockRejectedValueOnce(
      new ApiError(401, "unauthorized"),
    );
    await session.recover();
    expect(api.submit).toHaveBeenCalledTimes(1);
    expect(session.getSnapshot().conversation).toBeUndefined();
    expect(session.getSnapshot().notice).toContain("重新登录");
  });
  it("refreshing a revoked scope hides cached accepted results and forbids a follow-up", async () => {
    const { session, api } = setup();
    await session.start();
    await session.submit("question", scope);
    vi.mocked(api.conversation).mockRejectedValueOnce(
      new ApiError(404, "conversation_not_found"),
    );
    await session.refresh();
    expect(session.getSnapshot().runs).toEqual([]);
    await session.submit("next", scope);
    expect(api.submit).toHaveBeenCalledTimes(1);
  });
  it("creates only on intent and reuses creation identity after lost response", async () => {
    const { session, api } = setup();
    await session.refresh();
    expect(api.create).not.toHaveBeenCalled();
    vi.mocked(api.create).mockRejectedValueOnce(new TypeError("network"));
    await session.start();
    await session.start();
    expect(vi.mocked(api.create).mock.calls[0][0]).toBe(
      vi.mocked(api.create).mock.calls[1][0],
    );
    expect(session.getSnapshot().conversation?.id).toBe("c");
  });
  it("uses durable head and exact explicit scope; a follow-up gets a new key", async () => {
    const { session, api } = setup();
    await session.start();
    await session.submit("  original question  ", scope);
    expect(vi.mocked(api.submit).mock.calls[0][2]).toEqual({
      question: "  original question  ",
      scope,
      expected_head: null,
    });
    await session.submit("follow-up", { ...scope, version_ids: ["v2"] });
    const calls = vi.mocked(api.submit).mock.calls;
    expect(calls[1][2].expected_head).toBe("durable-head");
    expect(calls[1][2].scope.version_ids).toEqual(["v2"]);
    expect(calls[0][1]).not.toBe(calls[1][1]);
  });
  it("keeps the identical request/key across 503, reload and explicit recovery", async () => {
    const { session, api, storage } = setup();
    await session.start();
    vi.mocked(api.submit).mockRejectedValueOnce(
      new ApiError(503, "conversation_runtime_outcome_unavailable"),
    );
    await session.submit("uncertain", scope);
    expect(session.getSnapshot().notice).toContain("未确认");
    const restored = new ConversationSession("kb", storage, api);
    await restored.refresh();
    expect(api.submit).toHaveBeenCalledTimes(1);
    await restored.recover();
    expect(vi.mocked(api.submit).mock.calls[1]).toEqual(
      vi.mocked(api.submit).mock.calls[0],
    );
    expect(restored.getSnapshot().runs[0].accepted?.acceptance_id).toBe("a");
  });
  it("does not admit twice on concurrent handlers or readback/rerender", async () => {
    const { session, api } = setup();
    await session.start();
    await Promise.all([
      session.submit("question", scope),
      session.submit("question", scope),
    ]);
    await Promise.all([session.refresh(), session.refresh()]);
    expect(api.submit).toHaveBeenCalledTimes(1);
  });
  it("reads pending Runs without redispatch and recovers the terminal head", async () => {
    const { session, api, accepted } = setup();
    await session.start();
    vi.mocked(api.submit).mockResolvedValueOnce({
      ...accepted,
      status: "ADMITTED",
      accepted: null,
      completed_at: null,
    });
    vi.mocked(api.run).mockResolvedValueOnce({
      ...accepted,
      status: "ADMITTED",
      accepted: null,
      completed_at: null,
    });
    await session.submit("pending", scope);
    expect(session.getSnapshot().runs[0].status).toBe("ADMITTED");
    await session.recover();
    expect(api.submit).toHaveBeenCalledTimes(1);
    expect(session.getSnapshot().conversation?.head_id).toBe("durable-head");
    expect(session.getSnapshot().pending).toBeUndefined();
  });
  it("refreshes conflicts without silently rebasing or resubmitting", async () => {
    const { session, api } = setup();
    await session.start();
    vi.mocked(api.submit).mockRejectedValueOnce(
      new ApiError(409, "head_conflict"),
    );
    await session.submit("stale", scope);
    expect(api.conversation).toHaveBeenCalled();
    expect(api.submit).toHaveBeenCalledTimes(1);
    expect(session.getSnapshot().notice).toContain("冲突");
    expect(session.getSnapshot().conversation?.head_id).toBe("durable-head");
  });
  it("shows runtime unavailable without inventing a FAILED Run or leaking errors", async () => {
    const { session, api } = setup();
    await session.start();
    vi.mocked(api.submit).mockRejectedValueOnce(
      new ApiError(503, "conversation_runtime_unavailable"),
    );
    await session.submit("question", scope);
    expect(session.getSnapshot().notice).toContain("运行时不可用");
    expect(session.getSnapshot().runs).toEqual([]);
    expect(session.getSnapshot().pending).toBeDefined();
  });
  it("stores no accepted results/head and rereads accepted state after reload", async () => {
    const { session, api, storage } = setup();
    await session.start();
    await session.submit("question", scope);
    expect(storage.getItem()).not.toContain("Which receiver?");
    expect(storage.getItem()).not.toContain("durable-head");
    const restored = new ConversationSession("kb", storage, api);
    expect(restored.getSnapshot().runs).toEqual([]);
    await restored.refresh();
    expect(restored.getSnapshot().runs[0].accepted?.result.text).toBe(
      "Which receiver?",
    );
    expect(api.submit).toHaveBeenCalledTimes(1);
  });
});
