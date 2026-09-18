import { describe, expect, it } from "vitest";
import { EventDecoder, readAnswer } from "./stream";

const id = "2469c7cb-3a3a-4119-8c90-e2c0e4c0e7d1";
describe("Fetch SSE boundary", () => {
  it("cancels the upstream reader when rendering rejects an event", async () => {
    let cancelled = false;
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode(
            `data: ${JSON.stringify({ type: "stage", run_id: id, stage: "retrieval" })}\n\n`,
          ),
        );
      },
      cancel() {
        cancelled = true;
      },
    });
    await expect(
      readAnswer(
        new Response(stream, {
          headers: { "content-type": "text/event-stream" },
        }),
        () => {
          throw new Error("consumer_failed");
        },
      ),
    ).rejects.toThrow("consumer_failed");
    expect(cancelled).toBe(true);
  });
  it("preserves every Chinese and emoji byte over arbitrary network splits", () => {
    const decoder = new EventDecoder();
    const text = `data: ${JSON.stringify({ type: "delta", run_id: id, text: "中文😀", provisional: true })}\n\n`;
    const events = [...new TextEncoder().encode(text)].flatMap((byte) =>
      decoder.push(new Uint8Array([byte])),
    );
    expect(events).toHaveLength(1);
    expect(events[0].text).toBe("中文😀");
  });
  it("rejects malformed final and unsafe draft envelopes", () => {
    for (const event of [
      { type: "final", run_id: id },
      { type: "delta", run_id: id, text: "bad" },
    ]) {
      expect(() =>
        new EventDecoder().push(
          new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`),
        ),
      ).toThrow();
    }
  });
  it("requires a terminal event and rejects truncated frames", async () => {
    const response = new Response(
      `data: ${JSON.stringify({ type: "stage", run_id: id, stage: "retrieval" })}\n\n`,
      { headers: { "content-type": "text/event-stream" } },
    );
    await expect(readAnswer(response, () => {})).rejects.toThrow(
      "stream_incomplete",
    );
    expect(() =>
      new EventDecoder().push(new TextEncoder().encode("data: {"), true),
    ).toThrow("stream_incomplete");
  });
});
