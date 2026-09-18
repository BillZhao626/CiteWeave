import createClient from "openapi-fetch";
import type { components, paths } from "./generated/api";

export type KB = components["schemas"]["KnowledgeBase"];
export type Doc = components["schemas"]["Document"];
export type Citation = components["schemas"]["Citation"];
export type Answer = components["schemas"]["Answer"];
export type Event = components["schemas"]["StreamEvent"];
export const api = createClient<paths>({
  baseUrl: "",
  credentials: "same-origin",
});

export class ApiError extends Error {
  constructor(
    public status: number,
    code: string,
  ) {
    super(code);
  }
}
export function unwrap<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (!result.response.ok || result.data === undefined) {
    const error = result.error as { error?: { code?: string } } | undefined;
    throw new ApiError(
      result.response.status,
      error?.error?.code ?? "request_failed",
    );
  }
  return result.data;
}
export const listKBs = async () => unwrap(await api.GET("/v1/knowledge-bases"));
export const listDocs = async (id: string) =>
  unwrap(
    await api.GET("/v1/knowledge-bases/{kb_id}/documents", {
      params: { path: { kb_id: id } },
    }),
  );
export function message(error: unknown): string {
  const code = error instanceof Error ? error.message : "request_failed";
  return (
    (
      {
        unauthorized: "会话已过期，请重新登录。",
        no_ready_documents: "请等待至少一份文档处理完成。",
        single_query_capacity: "正在处理另一个问题，请稍后重试。",
        llm_key_missing: "尚未配置 DeepSeek API Key。",
        query_timeout: "本次回答超时，请查看记录后重试。",
        model_gateway_unavailable: "本地模型服务暂不可用。",
        monthly_budget_reserved: "本月预算已用完或被未完成请求预留。",
        invalid_or_missing_citation: "回答的引用未通过校验，请重新提问。",
        origin_mismatch: "页面来源验证失败，请从本地入口打开。",
      } as Record<string, string>
    )[code] ?? `操作未完成：${code}`
  );
}
