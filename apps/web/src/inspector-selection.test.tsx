// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "./api";
import { ContextPage } from "./context-inspector";
import { PublicationPage, ReliabilityPage } from "./publication-inspector";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it.each([
  ["context", ContextPage],
  ["publication", PublicationPage],
  ["reliability", ReliabilityPage],
])(
  "%s refuses to replace a requested Run with another record",
  async (_name, Page) => {
    const requestedEndpoints: string[] = [];
    vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
      requestedEndpoints.push(path);
      if (path !== "/v1/runtime/conversation-runs")
        throw new Error("An unrelated Run must not be requested");
      return {
        response: new Response("{}", { status: 200 }),
        data: [
          {
            run_id: "available-run",
            turn_id: "available-turn",
            conversation_id: "available-conversation",
            status: "ACCEPTED",
            question: "Another real record",
            publication: "PUBLISHED",
            created_at: "2026-10-06T00:00:00Z",
            retry_decision: "TERMINAL_NO_DISPATCH",
          },
        ],
      };
    }) as typeof api.GET);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/?run=absent-run"]}>
          <Page />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "所选 Run",
    );
    expect(
      requestedEndpoints.every(
        (endpoint) => endpoint === "/v1/runtime/conversation-runs",
      ),
    ).toBe(true);
  },
);

function Location() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

it.each([
  ["/runtime/publication", "Run / 可靠性", "/runtime/reliability"],
  ["/runtime/reliability", "Acceptance / 发布", "/runtime/publication"],
  ["/runtime/context", "检查一致发布 →", "/runtime/publication"],
])(
  "preserves the selected Run from %s when opening %s",
  async (path, link, target) => {
    const inspectedRuns: (string | undefined)[] = [];
    vi.spyOn(api, "GET").mockImplementation((async (
      endpoint: string,
      options?: { params?: { path?: { run_id?: string } } },
    ) => {
      if (endpoint === "/v1/runtime/conversation-runs")
        return {
          response: new Response("{}", { status: 200 }),
          data: ["newer-run", "selected-run"].map((id) => ({
            run_id: id,
            turn_id: id + "-turn",
            conversation_id: "same-conversation",
            status: "ACCEPTED",
            question: id + " question",
            publication: "PUBLISHED",
            created_at: "2026-10-06T00:00:00Z",
            retry_decision: "TERMINAL_NO_DISPATCH",
          })),
        };
      inspectedRuns.push(options?.params?.path?.run_id);
      return {
        response: new Response("{}", { status: 404 }),
        error: { error: { code: "inspection_unavailable" } },
      };
    }) as typeof api.GET);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`${path}?run=selected-run`]}>
          <Location />
          <Routes>
            <Route path="/runtime/publication" element={<PublicationPage />} />
            <Route path="/runtime/reliability" element={<ReliabilityPage />} />
            <Route path="/runtime/context" element={<ContextPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(
        screen.getByRole("link", { name: link }).getAttribute("href"),
      ).toBe(`${target}?run=selected-run`),
    );
    fireEvent.click(screen.getByRole("link", { name: link }));
    await waitFor(() =>
      expect(screen.getByTestId("location").textContent).toBe(
        `${target}?run=selected-run`,
      ),
    );
    expect(inspectedRuns.length).toBeGreaterThan(0);
    expect(inspectedRuns.every((id) => id === "selected-run")).toBe(true);
  },
);
