import test from "node:test";
import assert from "node:assert/strict";
import {
  productRule,
  validateBody,
  projectResponse,
} from "../src/features/workspace/transport-policy.ts";
import { consumeEvents } from "../src/features/workspace/events.ts";
import { id } from "./fixtures/product-api.ts";
import { workspaceResponse, resetWorkspace } from "./fixtures/workspace-api.ts";
test("Product BFF only exposes reviewed methods, fields and query keys", () => {
  assert.throws(() => productRule("ops/controls", "POST", new URLSearchParams()));
  assert.throws(() => productRule(`interviews/${id(1)}`, "DELETE", new URLSearchParams()));
  assert.throws(() => productRule("operations", "GET", new URLSearchParams("limit=1&limit=2")));
  assert.throws(() => productRule("operations", "GET", new URLSearchParams("url=https://evil")));
  const rule = productRule(`mock-interviews/${id(1)}/answers`, "POST", new URLSearchParams());
  assert.doesNotThrow(() =>
    validateBody(
      { expected_revision: 3, pending_question_id: id(2), request_id: id(3), answer: "回答" },
      rule.body,
    ),
  );
  assert.throws(() => validateBody({ provider: "custom" }, rule.body));
});
test("Product views keep explicit context refs but omit private frozen model context", () => {
  const data = {
    id: id(1),
    context: { binding: { profile_id: id(2) }, data: { prompt: "private" } },
  };
  assert.deepEqual(projectResponse(`mock-interviews/${id(1)}`, data), {
    id: id(1),
    context: { binding: { profile_id: id(2) } },
  });
  assert.deepEqual(
    projectResponse(`interview-debriefs/${id(1)}`, {
      snapshot: { entries: [], context: data.context },
    }),
    { snapshot: { entries: [], context: { binding: { profile_id: id(2) } } } },
  );
});
test("POST SSE parser handles split frames, UTF-8 and independently completed artifacts", async () => {
  const text =
    'event: overall_completed\r\ndata: {"sequence":1,"event":"overall_completed","display_order":1000}\r\n\r\nevent: group_completed\ndata: {"sequence":2,"event":"group_completed","display_order":1,"reason_code":"中文"}\n\n';
  const bytes = new TextEncoder().encode(text),
    seen: unknown[] = [];
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      for (let i = 0; i < bytes.length; i += 3) c.enqueue(bytes.slice(i, i + 3));
      c.close();
    },
  });
  await consumeEvents(stream, (e) => {
    seen.push(e);
  });
  assert.equal(seen.length, 2);
  assert.equal((seen[1] as { reason_code: string }).reason_code, "中文");
});
test("canonical submission fixture enforces expected revision and stable request UUID", () => {
  resetWorkspace();
  const url = new URL(`http://fixture/api/v1/applications/${id(1)}/submissions`);
  const body = {
    request_id: id(99),
    expected_revision: 2,
    resume_revision_id: id(8401),
    render_artifact_id: id(8501),
    greeting_id: null,
    package_id: null,
    note: null,
  };
  const a = workspaceResponse(url, "POST", body),
    b = workspaceResponse(url, "POST", body);
  assert.deepEqual(a, b);
  assert.equal(workspaceResponse(url, "POST", { ...body, request_id: id(100) })?.status, 409);
});

import { collectSubmissionHistory } from "../src/features/workspace/submission-history.ts";
import type { Submission } from "../src/features/workspace/contracts.ts";
test("actual-use projection scans past the first page without inferring absence", async () => {
  const offsets: number[] = [];
  const records = await collectSubmissionHistory(async (offset) => {
    offsets.push(offset);
    return {
      items: [{ id: id(offset + 1) } as Submission],
      limit: 1,
      offset,
      has_more: offset < 2,
    };
  });
  assert.deepEqual(offsets, [0, 1, 2]);
  assert.equal(records.length, 3);
  await assert.rejects(() =>
    collectSubmissionHistory(async () => ({ items: [], has_more: true, offset: 0, limit: 100 })),
  );
});

import { sameOriginWrite } from "../src/features/workspace/transport-policy.ts";
test("BFF checks browser Host rather than Next internal hostname; rejects cross-origin/forwarded host", () => {
  assert.equal(
    sameOriginWrite(
      new Request("http://localhost:3100/api/product/operations", {
        headers: { host: "127.0.0.1:3100", origin: "http://127.0.0.1:3100" },
      }),
    ),
    true,
  );
  assert.equal(
    sameOriginWrite(
      new Request("http://localhost:3100/api/product/operations", {
        headers: {
          host: "127.0.0.1:3100",
          origin: "https://evil.example",
          "x-forwarded-host": "evil.example",
        },
      }),
    ),
    false,
  );
});

test("SSE consumer failure cancels the stream rather than keeping an unread execution connection", async () => {
  let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      c.enqueue(new TextEncoder().encode('data: {"error_code":"execution_failed"}\n\n'));
    },
    cancel() {
      cancelled = true;
    },
  });
  await assert.rejects(() =>
    consumeEvents(stream, () => {
      throw new Error("execution_failed");
    }),
  );
  assert.equal(cancelled, true);
});
