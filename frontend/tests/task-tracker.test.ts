import { test } from "node:test";
import assert from "node:assert/strict";
import {
  taskDestination,
  taskFinished,
  taskStatusPath,
  type TrackedTask,
} from "../src/features/workspace/task-tracker.ts";
const task: TrackedTask = {
  key: "x",
  family: "operations",
  id: "x",
  title: "岗位匹配",
  href: "/applications/example/research-fit/fit?result=old",
};
test("notifications select the exact saved result without executing or changing its page", () => {
  assert.equal(
    taskDestination(task, { state: "success", selection: { result: "exact" } }),
    "/applications/example/research-fit/fit?result=exact",
  );
  for (const state of ["pending", "running", "ready"])
    assert.equal(taskFinished(task, { state, selection: {} }), false);
  for (const state of ["success", "failure", "cancelled", "unknown", "reused"])
    assert.equal(taskFinished(task, { state, selection: {} }), true);
});
test("a preceding Mock question is not completion of the submitted turn", () => {
  const turn = { ...task, family: "mock-interviews", baseline: 3 };
  assert.equal(
    taskFinished(turn, { state: "success", revision: 3, selection: { session: "exact" } }),
    false,
  );
  assert.equal(
    taskFinished(turn, { state: "success", revision: 4, selection: { session: "exact" } }),
    true,
  );
});

test("Mock status uses the exact request rather than the latest session outcome", () => {
  assert.equal(
    taskStatusPath({ ...task, family: "mock-interviews", requestId: "request" }),
    "task-status/mock-interviews/x?request_id=request",
  );
});

test("failed task links remain readable without the original page session", () => {
  const url = new URL(taskDestination(task, { state: "failure", selection: {} }), "http://local");
  assert.equal(url.pathname, "/tasks/operations/x");
  assert.equal(url.searchParams.get("return_to"), task.href);
});

test("Debrief retry replaces its prior notice only for a newer persisted execution revision", async () => {
  const { trackExecution, trackedTasks, recordTaskState, dismissTask } =
    await import("../src/features/workspace/task-tracker.ts");
  const values = new Map<string, string>();
  const target = Object.assign(new EventTarget(), {
    location: { pathname: "/applications/a/review/debriefs", search: "" },
  });
  Object.defineProperty(globalThis, "window", { configurable: true, value: target });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => values.get(k) || null,
      setItem: (k: string, v: string) => values.set(k, v),
    },
  });
  const id = "00000000-0000-4000-8000-000000000001",
    key = `interview-debriefs:${id}`;
  try {
    trackExecution(`interview-debriefs/${id}/execute`, "POST", { execution_revision: 0 });
    recordTaskState(key, { state: "failure", selection: {} });
    dismissTask(key, "failure");
    trackExecution(`interview-debriefs/${id}/execute`, "POST", { execution_revision: 0 });
    assert.equal(trackedTasks()[0].dismissedState, "failure");
    trackExecution(`interview-debriefs/${id}/execute`, "POST", { execution_revision: 1 });
    assert.equal(trackedTasks().length, 1);
    assert.equal(trackedTasks()[0].notice, undefined);
    assert.equal(trackedTasks()[0].dismissedState, undefined);
    recordTaskState(key, { state: "success", selection: { debrief: id } });
    assert.equal(trackedTasks()[0].notice?.state, "success");
    assert.equal(taskFinished(trackedTasks()[0], { state: "removed", selection: {} }), true);
  } finally {
    Reflect.deleteProperty(globalThis, "window");
    Reflect.deleteProperty(globalThis, "localStorage");
  }
});

test("a failed or cancelled exact Mock request is terminal without a session revision increment", () => {
  const turn = { ...task, family: "mock-interviews", baseline: 3, requestId: "exact-request" };
  for (const state of ["failure", "cancelled", "unknown"])
    assert.equal(taskFinished(turn, { state, revision: 3, selection: {} }), true);
});

test("foreground rendered Mock receipts do not enter unread; background and other sessions do", async () => {
  const {
    recordTaskState,
    pendingNotices,
    trackedTasks,
    visibleMockQuestions,
    visibleMockCompletions,
    markMockQuestionsSeen,
  } = await import("../src/features/workspace/task-tracker.ts");
  const values = new Map<string, string>();
  const target = new EventTarget();
  Object.defineProperty(globalThis, "window", { configurable: true, value: target });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) || null,
      setItem: (key: string, value: string) => values.set(key, value),
    },
  });
  const doc = { visibilityState: "visible" };
  Object.defineProperty(globalThis, "document", { configurable: true, value: doc });
  const tracked = { ...task, family: "mock-interviews", requestId: "request", id: "session" };
  const state = { state: "success", selection: { session: "session", question: "question" } };
  const seed = () => values.set("career-task-handles-v1", JSON.stringify([tracked]));
  try {
    seed();
    visibleMockQuestions.set("session", new Set());
    recordTaskState("x", state);
    assert.equal(trackedTasks()[0].notice, undefined);
    visibleMockQuestions.set("session", new Set(["question"]));
    recordTaskState("x", state);
    assert.equal(pendingNotices(trackedTasks()).length, 0);
    recordTaskState("x", state);
    assert.equal(pendingNotices(trackedTasks()).length, 0);
    seed();
    doc.visibilityState = "hidden";
    recordTaskState("x", state);
    assert.equal(pendingNotices(trackedTasks()).length, 1);
    values.set(
      "career-task-handles-v1",
      JSON.stringify([
        { ...tracked, notice: { state: "unknown", selection: {} }, dismissedState: "unknown" },
        {
          ...tracked,
          key: "different",
          requestId: "different",
          notice: { state: "failure", reason: "provider_timeout", selection: {} },
        },
      ]),
    );
    recordTaskState("x", state);
    assert.equal(trackedTasks()[0].notice?.state, "success");
    assert.equal(trackedTasks()[0].dismissedState, "success");
    assert.equal(pendingNotices(trackedTasks()).length, 1);
    assert.equal(trackedTasks()[1].notice?.state, "failure");
    seed();
    doc.visibilityState = "visible";
    visibleMockQuestions.clear();
    Object.assign(target, {
      location: { pathname: "/applications/example/interview/mock", search: "?session=session" },
    });
    recordTaskState("x", state);
    assert.equal(trackedTasks()[0].notice, undefined, "wait for the exact page to finish mounting");
    visibleMockQuestions.set("session", new Set(["question"]));
    recordTaskState("x", state);
    assert.equal(pendingNotices(trackedTasks()).length, 0);
    seed();
    visibleMockQuestions.clear();
    Object.assign(target, { location: { pathname: "/applications/example/summary", search: "" } });
    recordTaskState("x", state);
    assert.equal(pendingNotices(trackedTasks()).length, 1);
    seed();
    markMockQuestionsSeen("session", ["question"]);
    visibleMockQuestions.clear();
    recordTaskState("x", state);
    assert.equal(
      pendingNotices(trackedTasks()).length,
      0,
      "seeing the question survives navigation before receipt polling",
    );
    seed();
    visibleMockQuestions.set("session", new Set(["question"]));
    const finish = {
      state: "success",
      selection: { session: "session" },
      decision: { action: "finish" as const },
    };
    recordTaskState("x", finish);
    assert.equal(
      trackedTasks()[0].notice,
      undefined,
      "do not acknowledge finish before completed body mounts",
    );
    visibleMockCompletions.add("session");
    markMockQuestionsSeen("session", ["question"], true);
    recordTaskState("x", finish);
    assert.equal(pendingNotices(trackedTasks()).length, 0);
    visibleMockQuestions.clear();
    visibleMockCompletions.clear();
    recordTaskState("x", finish);
    assert.equal(
      pendingNotices(trackedTasks()).length,
      0,
      "seen finish does not reappear after leaving",
    );
    seed();
    recordTaskState("x", finish);
    assert.equal(
      pendingNotices(trackedTasks()).length,
      1,
      "background finish remains a real completion",
    );
  } finally {
    visibleMockCompletions.clear();
    visibleMockQuestions.clear();
    Reflect.deleteProperty(globalThis, "document");
    Reflect.deleteProperty(globalThis, "window");
    Reflect.deleteProperty(globalThis, "localStorage");
  }
});

test("acknowledged Debrief unknown updates in place without reappearing", async () => {
  const { trackExecution, trackedTasks, recordTaskState, dismissTask, pendingNotices } =
    await import("../src/features/workspace/task-tracker.ts");
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: Object.assign(new EventTarget(), {
      location: { pathname: "/applications/a/review/debriefs", search: "" },
    }),
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => values.get(k) || null,
      setItem: (k: string, v: string) => values.set(k, v),
    },
  });
  const id = "00000000-0000-4000-8000-000000000001",
    key = `interview-debriefs:${id}`;
  try {
    trackExecution(`interview-debriefs/${id}/execute`, "POST");
    recordTaskState(key, { state: "unknown", selection: {} });
    dismissTask(key, "unknown");
    recordTaskState(key, { state: "partial", selection: { debrief: id } });
    assert.equal(trackedTasks().length, 1);
    assert.equal(pendingNotices(trackedTasks()).length, 0);
  } finally {
    Reflect.deleteProperty(globalThis, "window");
    Reflect.deleteProperty(globalThis, "localStorage");
  }
});

test("exact rendered execution defers early receipts and suppresses only matching foreground state", async () => {
  const {
    trackExecution,
    trackedTasks,
    recordTaskState,
    acknowledgeTaskState,
    visibleTaskStates,
    markTaskErrorSeen,
    pendingNotices,
  } = await import("../src/features/workspace/task-tracker.ts");
  const values = new Map<string, string>();
  const doc = { visibilityState: "visible" };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: Object.assign(new EventTarget(), {
      location: { pathname: "/applications/a/review/debriefs", search: "" },
    }),
  });
  Object.defineProperty(globalThis, "document", { configurable: true, value: doc });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => values.get(k) || null,
      setItem: (k: string, v: string) => values.set(k, v),
    },
  });
  const id = "00000000-0000-4000-8000-000000000001",
    key = `interview-debriefs:${id}`;
  try {
    trackExecution(`interview-debriefs/${id}/execute`, "POST");
    acknowledgeTaskState(key, { state: "running", selection: {} });
    const partial = {
      state: "partial",
      reason: "invalid_evidence_reference",
      selection: { debrief: id },
    };
    recordTaskState(key, partial);
    assert.equal(trackedTasks()[0].notice, undefined);
    acknowledgeTaskState(key, partial);
    assert.equal(trackedTasks()[0].notice?.state, "partial");
    assert.equal(pendingNotices(trackedTasks()).length, 0);
    trackExecution(`interview-debriefs/${id}/execute`, "POST", { execution_revision: 1 });
    acknowledgeTaskState(key, { state: "running", selection: {} });
    doc.visibilityState = "hidden";
    recordTaskState(key, { state: "success", selection: { debrief: id } });
    assert.equal(pendingNotices(trackedTasks()).length, 1);
    // Viewing another request cannot acknowledge this one.
    doc.visibilityState = "visible";
    acknowledgeTaskState("another", { state: "success", selection: {} });
    assert.equal(pendingNotices(trackedTasks()).length, 1);
    visibleTaskStates.delete(key);
    recordTaskState(key, { state: "success", selection: { debrief: id } });
    assert.equal(trackedTasks().length, 1);
    trackExecution(`mock-interviews/${id}/generate`, "POST", { request_id: "seen" });
    markTaskErrorSeen(`mock-interviews:${id}:seen`);
    // The error was visible before the user retried; its receipt arrives later.
    recordTaskState(`mock-interviews:${id}:seen`, { state: "failure", selection: {} });
    assert.equal(pendingNotices(trackedTasks()).length, 1);
    trackExecution(`mock-interviews/${id}/generate`, "POST", { request_id: "other" });
    recordTaskState(`mock-interviews:${id}:other`, { state: "failure", selection: {} });
    assert.equal(pendingNotices(trackedTasks()).length, 2);
  } finally {
    visibleTaskStates.clear();
    for (const k of ["window", "document", "localStorage"]) Reflect.deleteProperty(globalThis, k);
  }
});

test("late Debrief revision and stale Mock unknown cannot replace committed success", async () => {
  const { trackExecution, trackedTasks, recordTaskState } =
    await import("../src/features/workspace/task-tracker.ts");
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { visibilityState: "hidden" },
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: Object.assign(new EventTarget(), {
      location: { pathname: "/applications/a/summary", search: "" },
    }),
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => values.get(k) || null,
      setItem: (k: string, v: string) => values.set(k, v),
    },
  });
  try {
    const id = "00000000-0000-4000-8000-000000000001",
      key = `interview-debriefs:${id}`;
    trackExecution(`interview-debriefs/${id}/execute`, "POST", { execution_revision: 2 });
    recordTaskState(key, { state: "partial", execution_revision: 1, selection: {} });
    assert.equal(trackedTasks()[0].notice, undefined);
    recordTaskState(key, { state: "success", execution_revision: 2, selection: {} });
    recordTaskState(key, { state: "unknown", execution_revision: 2, selection: {} });
    assert.equal(trackedTasks()[0].notice?.state, "success");
    trackExecution(`mock-interviews/${id}/generate`, "POST", { request_id: "request" });
    recordTaskState(`mock-interviews:${id}:request`, { state: "success", selection: {} });
    recordTaskState(`mock-interviews:${id}:request`, { state: "unknown", selection: {} });
    assert.equal(trackedTasks()[1].notice?.state, "success");
  } finally {
    for (const k of ["window", "localStorage", "document"]) Reflect.deleteProperty(globalThis, k);
  }
});

test("a delayed Debrief dispatch keeps its application route after navigation", async () => {
  const { trackExecution, trackedTasks } =
    await import("../src/features/workspace/task-tracker.ts");
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: Object.assign(new EventTarget(), {
      location: { pathname: "/applications/a/review/knowledge-notes", search: "" },
    }),
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => values.get(k) || null,
      setItem: (k: string, v: string) => values.set(k, v),
    },
  });
  const id = "00000000-0000-4000-8000-000000000019";
  try {
    trackExecution(`interview-debriefs/${id}/execute`, "POST", {
      application_id: "a",
      execution_revision: 0,
    });
    assert.equal(trackedTasks()[0].href, `/applications/a/review/debriefs?task=${id}`);
  } finally {
    Reflect.deleteProperty(globalThis, "window");
    Reflect.deleteProperty(globalThis, "localStorage");
  }
});
