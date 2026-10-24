export type BusinessEvent = {
  sequence?: number;
  event?: string;
  group_index?: number;
  display_order?: number;
  display_section?: string;
  reason_code?: string;
  error_code?: string;
};
/** POST SSE framing; artifact notifications only, never model token text. */
export async function consumeEvents(
  body: ReadableStream<Uint8Array>,
  receive: (event: BusinessEvent) => Promise<void> | void,
) {
  const reader = body.getReader(),
    decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let end: number;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        const data = frame
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");
        if (data) await receive(JSON.parse(data));
      }
      if (buffer.length > 100000) throw new Error("invalid_event");
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
