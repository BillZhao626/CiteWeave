// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { JobView } from "./operations";
import { CitationStatus } from "./citation-status";
import { PdfEvidence } from "./pdf-evidence";
import type { components } from "./generated/api";
import type { Citation } from "./api";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const job: components["schemas"]["Job"] = {
  id: "job-identity",
  document_version_id: "version-identity",
  status: "READY",
  kind: "ingest",
  attempt: 2,
  max_attempts: 3,
  created_at: "2026-10-04T00:00:00Z",
  started_at: null,
  finished_at: null,
  error_code: null,
  error_message: null,
  pipeline_version: "test",
  events: [],
};
describe("truthful presentation of persisted state", () => {
  it("does not reconstruct events from READY and keeps complete identities", () => {
    render(<JobView job={job} />);
    expect(screen.getByText("version-identity")).toBeTruthy();
    expect(screen.getByText("未记录任务事件。")).toBeTruthy();
    expect(screen.queryByText("PARSING")).toBeNull();
    expect(screen.queryByRole("list", { name: "任务时间线" })).toBeNull();
  });
  it("preserves retry attempts, final failure and absent fields", () => {
    const { container } = render(
      <JobView
        job={{
          ...job,
          status: "FAILED_FINAL",
          events: [
            { status: "PARSING", attempt: 1, at: "first" },
            { status: "RETRY_WAIT", attempt: 1, at: "retry" },
            {
              status: "FAILED_FINAL",
              attempt: 2,
              at: "last",
              code: "parse_failed",
            },
            { future: "value" },
          ],
        }}
      />,
    );
    const events = container.querySelectorAll(".job-timeline li");
    expect(events).toHaveLength(4);
    expect(events[2].textContent).toContain("尝试 2");
    expect(events[3].textContent).toContain("未记录");
    expect(container.querySelector(".job-timeline")?.textContent).not.toContain(
      "READY",
    );
  });
  it("states source binding only when citations exist and retains accessible help", () => {
    const { rerender } = render(<CitationStatus hasCitations />);
    expect(screen.getByText("引用已绑定来源片段")).toBeTruthy();
    expect(screen.getByText("引用说明").tagName).toBe("SUMMARY");
    expect(screen.getByText(/物理引用校验不证明语义支持/)).toBeTruthy();
    expect(screen.queryByText("已定位引用原文")).toBeNull();
    rerender(<CitationStatus hasCitations={false} />);
    expect(screen.queryByText("引用已绑定来源片段")).toBeNull();
  });
  it("never paints a location highlight after PDF loading failure", async () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false })),
    );
    const citation = {
      label: "E1",
      evidence_id: "e",
      document_version_id: "v",
      filename: "source.pdf",
      content_url: "/v1/document-versions/v/content",
      span: {
        quote: "source",
        boxes: [{ page_index: 0, left: 0, top: 0, right: 1, bottom: 1 }],
      },
    } as Citation;
    const { container } = render(<PdfEvidence citation={citation} />);
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "无法读取授权文档",
      ),
    );
    expect(container.querySelector(".evidence-highlight")).toBeNull();
    expect(screen.queryByText("已定位引用原文")).toBeNull();
  });
});
