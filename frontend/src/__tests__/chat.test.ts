import { describe, expect, it } from "vitest";
import { readSSE } from "../features/assistant/useChat";

const streamOf = (chunks: string[]) => new Response(new ReadableStream({ start(c) { chunks.forEach((x) => c.enqueue(new TextEncoder().encode(x))); c.close(); } }));

describe("readSSE", () => {
  it("parses events split across network chunks and skips malformed frames", async () => {
    const res = streamOf(['data: {"type":"tok', 'en","text":"Hi"}\n\ndata: not-json\n\ndata: {"type":"done"}\n\n']);
    const out: unknown[] = [];
    for await (const e of readSSE(res)) out.push(e);
    expect(out).toEqual([{ type: "token", text: "Hi" }, { type: "done" }]);
  });
});
