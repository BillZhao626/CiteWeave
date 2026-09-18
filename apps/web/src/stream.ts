import { z } from "zod";
import type { Event } from "./api";

// The transport envelope is a runtime boundary. Domain types come from OpenAPI.
const envelope = z.object({
  type: z.enum(["stage", "delta", "final", "error"]),
  run_id: z.uuid(),
  text: z.string().optional(),
  provisional: z.boolean().optional(),
  stage: z.string().optional(),
  code: z.string().optional(),
  answer: z
    .object({
      run_id: z.uuid(),
      text: z.string(),
      citations: z.array(
        z
          .object({
            label: z.string(),
            evidence_id: z.uuid(),
            document_version_id: z.uuid(),
            filename: z.string(),
            content_url: z.string().startsWith("/v1/document-versions/"),
            span: z
              .object({
                quote: z.string(),
                boxes: z
                  .array(
                    z.object({
                      page_index: z.number().int().nonnegative(),
                      left: z.number().min(0).max(1),
                      top: z.number().min(0).max(1),
                      right: z.number().min(0).max(1),
                      bottom: z.number().min(0).max(1),
                    }),
                  )
                  .min(1),
              })
              .passthrough(),
          })
          .passthrough(),
      ),
      prompt_version: z.string(),
    })
    .passthrough()
    .optional(),
});

export class EventDecoder {
  private decoder = new TextDecoder("utf-8", { fatal: true });
  private buffer = "";
  push(bytes: Uint8Array, done = false): Event[] {
    this.buffer += this.decoder.decode(bytes, { stream: !done });
    this.buffer = this.buffer.replace(/\r\n/g, "\n");
    if (this.buffer.length > 2_000_000) throw new Error("stream_frame_limit");
    const frames = this.buffer.split("\n\n");
    this.buffer = frames.pop() ?? "";
    if (done && this.buffer.trim()) throw new Error("stream_incomplete");
    return frames
      .filter((f) => f.startsWith("data:"))
      .map((frame) => {
        const value = envelope.parse(JSON.parse(frame.slice(5).trim()));
        if (value.type === "final" && !value.answer)
          throw new Error("final_answer_missing");
        if (
          value.type === "delta" &&
          (value.provisional !== true || value.text === undefined)
        )
          throw new Error("unsafe_delta");
        return value as Event;
      });
  }
}

export async function readAnswer(
  response: Response,
  onEvent: (event: Event) => void,
) {
  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.error?.code ?? "query_failed");
  }
  if (
    !response.body ||
    !response.headers.get("content-type")?.includes("text/event-stream")
  )
    throw new Error("stream_missing");
  const reader = response.body.getReader(),
    decoder = new EventDecoder();
  let terminal = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      for (const event of decoder.push(value ?? new Uint8Array(), done)) {
        if (terminal) throw new Error("event_after_terminal");
        terminal = event.type === "final" || event.type === "error";
        onEvent(event);
      }
      if (done) break;
    }
    if (!terminal) throw new Error("stream_incomplete");
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
