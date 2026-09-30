import { z } from "zod";
import { api, ApiError, unwrap } from "./api";
import type { components } from "./generated/api";

export type PublicConversation = components["schemas"]["PublicConversation"];
export type PublicRun = components["schemas"]["PublicRun"];
export type ConversationTrace = components["schemas"]["ConversationTrace"];
export type TurnSubmit = components["schemas"]["TurnSubmit"];
export type ConversationScope = components["schemas"]["ConversationScope"];

export interface ConversationTransport {
  create(key: string): Promise<PublicConversation>;
  conversation(id: string): Promise<PublicConversation>;
  submit(id: string, key: string, body: TurnSubmit): Promise<PublicRun>;
  run(id: string, run: string): Promise<PublicRun>;
  trace(id: string, run: string): Promise<ConversationTrace>;
}
export const conversationApi: ConversationTransport = {
  create: async (key) =>
    unwrap(
      await api.POST("/v1/conversations", {
        params: { header: { "idempotency-key": key } },
      }),
    ),
  conversation: async (id) =>
    unwrap(
      await api.GET("/v1/conversations/{conversation_id}", {
        params: { path: { conversation_id: id } },
      }),
    ),
  submit: async (id, key, body) =>
    unwrap(
      await api.POST("/v1/conversations/{conversation_id}/turns", {
        params: {
          path: { conversation_id: id },
          header: { "idempotency-key": key },
        },
        body,
      }),
    ),
  run: async (id, run) =>
    unwrap(
      await api.GET("/v1/conversations/{conversation_id}/runs/{run_id}", {
        params: { path: { conversation_id: id, run_id: run } },
      }),
    ),
  trace: async (id, run) =>
    unwrap(
      await api.GET("/v1/conversations/{conversation_id}/runs/{run_id}/trace", {
        params: { path: { conversation_id: id, run_id: run } },
      }),
    ),
};

// This journal contains recovery identities and an unconfirmed request, never
// accepted output or a cached head. Its schema validates browser storage only.
const journalSchema = z.object({
  revision: z.literal(1),
  createKey: z.string().optional(),
  conversationId: z.string().optional(),
  runIds: z.array(z.string()),
  versions: z.array(z.string()),
  pending: z
    .object({
      key: z.string(),
      runId: z.string().optional(),
      body: z.object({
        question: z.string(),
        expected_head: z.string().nullable(),
        scope: z.object({
          kb_id: z.string(),
          version_ids: z.array(z.string()),
        }),
      }),
    })
    .optional(),
});
type Journal = z.infer<typeof journalSchema>;
type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;
class RecoveryStorageError extends Error {}
export interface ConversationState {
  conversation?: PublicConversation;
  runs: PublicRun[];
  traces: Record<string, ConversationTrace>;
  versions: string[];
  pending?: Journal["pending"];
  hasIdentity: boolean;
  busy: boolean;
  notice: string;
}

function safeNotice(error: unknown): string {
  if (error instanceof RecoveryStorageError)
    return "无法保存恢复记录；请检查浏览器存储权限，再使用同一身份恢复。";
  if (error instanceof ApiError) {
    if (error.message === "conversation_runtime_unavailable")
      return "会话运行时不可用；生产执行尚未开放。可使用同一提交身份重新确认。";
    if (error.status === 409)
      return "提交冲突；已请求刷新持久会话。请核对当前状态后决定下一次提问。";
    if (error.status === 401) return "会话已过期，请重新登录后读取持久状态。";
    if (error.status === 404)
      return "会话或来源当前不可访问；请核对工作空间与范围。";
    if (error.status === 422) return "请求未被接受，请检查问题与文档版本范围。";
  }
  return "请求结果未确认；请读取持久状态，必要时使用同一提交身份恢复。";
}

export class ConversationSession {
  private journal: Journal = { revision: 1, runIds: [], versions: [] };
  private state: ConversationState;
  private listeners = new Set<() => void>();
  private storageKey: string;
  constructor(
    kb: string,
    private storage: Storage,
    private transport = conversationApi,
  ) {
    this.storageKey = `citeweave.conversation.v1:${kb}`;
    let notice = "";
    try {
      const saved = storage.getItem(this.storageKey);
      if (saved) this.journal = journalSchema.parse(JSON.parse(saved));
    } catch {
      notice =
        "本地恢复记录不可用；请显式开始新会话。已有服务端会话不会被删除。";
    }
    this.state = {
      runs: [],
      traces: {},
      versions: this.journal.versions,
      pending: this.journal.pending,
      hasIdentity: !!this.journal.createKey,
      busy: false,
      notice,
    };
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private update(patch: Partial<ConversationState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  private save() {
    this.update({
      pending: this.journal.pending,
      hasIdentity: !!this.journal.createKey,
      versions: this.journal.versions,
    });
    try {
      this.storage.setItem(this.storageKey, JSON.stringify(this.journal));
    } catch {
      throw new RecoveryStorageError();
    }
  }
  setVersions(versions: string[]) {
    this.journal.versions = [...new Set(versions)].sort();
    try {
      this.save();
    } catch {
      this.update({ notice: "无法保存恢复记录；请检查浏览器存储权限。" });
    }
  }
  private async operation(work: () => Promise<void>) {
    if (this.state.busy) return;
    this.update({ busy: true, notice: "" });
    try {
      await work();
    } catch (error) {
      this.update({ notice: safeNotice(error) });
    } finally {
      this.update({ busy: false });
    }
  }
  async start(fresh = false) {
    await this.operation(async () => {
      if (fresh) {
        this.journal = {
          revision: 1,
          runIds: [],
          versions: this.journal.versions,
        };
        this.update({ conversation: undefined, runs: [], traces: {} });
      }
      this.journal.createKey ??= crypto.randomUUID();
      this.save(); // Persist before the first side effect, also when retrying creation.
      const conversation = await this.transport.create(this.journal.createKey);
      this.journal.conversationId = conversation.id;
      this.save();
      this.update({ conversation });
      if (this.journal.runIds.length) await this.read();
    });
  }
  private async read() {
    const id = this.journal.conversationId;
    if (!id) return;
    try {
      const conversation = await this.transport.conversation(id);
      const ids = [
        ...new Set([
          ...this.journal.runIds,
          ...(conversation.active_run_id ? [conversation.active_run_id] : []),
        ]),
      ];
      const pairs = await Promise.all(
        ids.map(
          async (run) =>
            [
              await this.transport.run(id, run),
              await this.transport.trace(id, run),
            ] as const,
        ),
      );
      this.journal.runIds = ids;
      if (
        this.journal.pending?.runId &&
        pairs.some(
          ([run]) =>
            run.id === this.journal.pending?.runId && run.status !== "ADMITTED",
        )
      )
        this.journal.pending = undefined;
      this.save();
      this.update({
        conversation,
        runs: pairs.map(([run]) => run),
        traces: Object.fromEntries(
          pairs
            .filter(([, trace]) => trace)
            .map(([run, trace]) => [run.id, trace]),
        ),
      });
    } catch (error) {
      // Do not leave stale authorized answers or an old head usable after a failed refresh.
      this.update({ conversation: undefined, runs: [], traces: {} });
      throw error;
    }
  }
  refresh = async () => {
    if (this.journal.conversationId) await this.operation(() => this.read());
  };
  private async sendPending() {
    const pending = this.journal.pending;
    const id = this.journal.conversationId;
    if (!pending || !id) return;
    this.save();
    try {
      const run = await this.transport.submit(id, pending.key, pending.body);
      pending.runId = run.id;
      this.journal.runIds = [...new Set([...this.journal.runIds, run.id])];
      this.save();
    } catch (error) {
      // A definitive rejection permits a new intentional action, but never an
      // automatic rebase/retry. A 503 or transport loss retains exact identity.
      if (error instanceof ApiError && [409, 422].includes(error.status))
        this.journal.pending = undefined;
      this.save();
      await this.read();
      throw error;
    }
    await this.read(); // Derive head from durable Conversation, never increment locally.
  }
  async submit(question: string, scope: ConversationScope) {
    if (
      this.state.busy ||
      this.journal.pending ||
      !this.state.conversation ||
      this.state.conversation.active_run_id ||
      !question.trim() ||
      !scope.version_ids.length
    )
      return;
    await this.operation(async () => {
      this.journal.pending = {
        key: crypto.randomUUID(),
        body: {
          question,
          scope: {
            kb_id: scope.kb_id,
            version_ids: [...scope.version_ids].sort(),
          },
          expected_head: this.state.conversation!.head_id,
        },
      };
      await this.sendPending();
    });
  }
  recover = async () => {
    await this.operation(async () => {
      await this.read();
      // Known Runs only need GETs; never dispatch on mount, polling or reconnect.
      if (this.journal.pending && !this.journal.pending.runId)
        await this.sendPending();
    });
  };
}
