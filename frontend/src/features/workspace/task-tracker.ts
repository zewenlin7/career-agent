/** Persist handles only. Task outcomes always come from the server, never HTTP acceptance. */
export type TrackedTask = {
  key: string;
  family: string;
  id: string;
  title: string;
  href: string;
  baseline?: number;
  requestId?: string;
  dismissedState?: string;
  shownState?: string;
  notice?: TaskState;
  seenQuestions?: string[];
  seenCompletion?: boolean;
  seenError?: boolean;
  executionRevision?: number;
};
const storage = "career-task-handles-v1";
const titles = new Map<string, string>();
const locations = new Map<string, string>();
export function rememberTask(path: string, value: unknown) {
  if (path.startsWith("mock-interviews") && value && typeof value === "object") {
    const session = value as { id?: string; application_id?: string };
    if (session.id && session.application_id)
      locations.set(
        session.id,
        `/applications/${session.application_id}/interview/mock?session=${session.id}`,
      );
  }
  if (!path.startsWith("product-drafts") || !value || typeof value !== "object") return;
  const data = value as {
    id?: string;
    task?: string;
    intent?: string;
    lineage?: { intent?: string };
  };
  const labels: Record<string, string> = {
    base_resume_drafting: "简历生成",
    resume_library_compression: "简历精简",
    resume_claim_refinement: "简历内容调整",
    resume_refinement: "简历优化",
    greeting_refinement: "招呼语调整",
    interview_preparation_refinement: "面试准备调整",
  };
  if (data.id && data.task && labels[data.task])
    titles.set(
      data.id,
      data.task === "resume_refinement"
        ? (data.intent || data.lineage?.intent) === "regenerate"
          ? "简历重新生成"
          : "简历调整"
        : (data.intent || data.lineage?.intent) === "regenerate"
          ? labels[data.task].replace(/调整$/, "重新生成")
          : labels[data.task],
    );
}
export const taskChange = "career-task-handles";
export function trackedTasks(): TrackedTask[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(storage) || "[]") as TrackedTask[];
  } catch {
    return [];
  }
}
function store(tasks: TrackedTask[]) {
  try {
    localStorage.setItem(storage, JSON.stringify(tasks));
  } catch {
    /* Storage may be disabled. */
  }
  window.dispatchEvent(new Event(taskChange));
}
export function dismissTask(key: string, state: string) {
  store(trackedTasks().map((t) => (t.key === key ? { ...t, dismissedState: state } : t)));
}
export function trackExecution(path: string, method: string, body?: unknown) {
  if (typeof window === "undefined" || method !== "POST") return;
  const match =
    /^(operations|product-drafts|mock-interviews|interview-debriefs)\/([0-9a-f-]{36})\/(execute|generate|answers)$/.exec(
      path,
    );
  if (!match) return;
  const [, family, id] = match;
  const data = (body || {}) as {
    request_id?: string;
    expected_revision?: number;
    execution_revision?: number;
    application_id?: string;
  };
  const key =
    family === "mock-interviews" ? `${family}:${id}:${data.request_id}` : `${family}:${id}`;
  const tasks = trackedTasks();
  const previous = tasks.find((t) => t.key === key);
  if (previous) {
    if (
      family === "interview-debriefs" &&
      (data.execution_revision || 0) > (previous.executionRevision || 0)
    )
      store(
        tasks.map((t) =>
          t.key === key
            ? {
                ...t,
                executionRevision: data.execution_revision,
                notice: undefined,
                dismissedState: undefined,
                shownState: undefined,
              }
            : t,
        ),
      );
    return;
  }
  const pathname = window.location.pathname;
  const title =
    titles.get(id) ||
    (family === "mock-interviews"
      ? "模拟面试"
      : family === "interview-debriefs"
        ? "面试复盘"
        : pathname.endsWith("/company")
          ? "公司研究"
          : pathname.endsWith("/fit")
            ? "岗位匹配"
            : pathname.includes("greeting")
              ? "招呼语"
              : pathname.includes("prep")
                ? "面试准备"
                : "简历优化");
  store([
    ...tasks,
    {
      key,
      family,
      id,
      title,
      href:
        family === "interview-debriefs"
          ? `${data.application_id ? `/applications/${data.application_id}/review/debriefs` : pathname}?task=${id}`
          : locations.get(id) || pathname + window.location.search,
      executionRevision: data.execution_revision,
      baseline: data.expected_revision,
      requestId: data.request_id,
    },
  ]);
}
export type TaskState = {
  workspace?: { application_id: string; available: boolean; reason: string | null } | null;
  execution_revision?: number;
  decision?: {
    action: "ask" | "finish";
    kind?: "primary" | "follow_up" | null;
    primary_entry_id?: string | null;
  } | null;
  completion_type?: string | null;
  state: string;
  reason?: string;
  selection: Record<string, string>;
  revision?: number;
};
export function taskDestination(task: TrackedTask, state: TaskState): string {
  if (
    state.workspace?.available === false ||
    !["success", "reused", "partial"].includes(state.state)
  ) {
    const query = new URLSearchParams({ return_to: task.href });
    if (task.requestId) query.set("request_id", task.requestId);
    return `/tasks/${task.family}/${task.id}?${query}`;
  }
  const url = new URL(task.href, "http://local");
  for (const [key, value] of Object.entries(state.selection)) url.searchParams.set(key, value);
  return url.pathname + url.search;
}
export function taskFinished(task: TrackedTask, state: TaskState): boolean {
  if (
    task.family === "mock-interviews" &&
    state.state === "success" &&
    !task.requestId &&
    task.baseline !== undefined &&
    (state.revision ?? 0) <= task.baseline
  )
    return false;
  return [
    "success",
    "failure",
    "cancelled",
    "reused",
    "unknown",
    "partial",
    "awaiting_save",
    "removed",
  ].includes(state.state);
}

export function taskStatusPath(task: TrackedTask): string {
  const path = `task-status/${task.family}/${task.id}`;
  const request =
    task.requestId || (task.family === "mock-interviews" ? task.key.split(":")[2] : undefined);
  return task.family === "mock-interviews" && request
    ? `${path}?request_id=${encodeURIComponent(request)}`
    : path;
}

export function recordTaskState(key: string, state: TaskState) {
  const tasks = trackedTasks();
  const task = tasks.find((t) => t.key === key);
  if (!task || !taskFinished(task, state) || JSON.stringify(task.notice) === JSON.stringify(state))
    return;
  if (
    state.execution_revision !== undefined &&
    state.execution_revision < (task.executionRevision || 0)
  )
    return;
  // An exact committed request cannot regress when an earlier poll arrives late.
  if (task.notice?.state === "success" && !["success", "removed"].includes(state.state)) return;
  const foregroundState =
    typeof document !== "undefined" && document.visibilityState === "visible"
      ? visibleTaskStates.get(key)
      : undefined;
  // A mounted execution can observe a receipt before its result renders. Wait for
  // the exact UI state, or notify after navigation; route identity alone is not acknowledgement.
  if (foregroundState !== undefined && foregroundState !== state.state) return;
  if (
    task.family === "interview-debriefs" &&
    foregroundState === undefined &&
    typeof document !== "undefined" &&
    document.visibilityState === "visible" &&
    window.location.pathname.endsWith("/review/debriefs")
  ) {
    const query = new URLSearchParams(window.location.search);
    if (query.get("task") === task.id || query.get("debrief") === task.id) return;
  }
  const displayed = visibleMockQuestions.get(task.id);
  const previouslySeen =
    (!!state.selection.question && task.seenQuestions?.includes(state.selection.question)) ||
    (state.decision?.action === "finish" && task.seenCompletion);
  // The shell can read a completed receipt before the exact session mounts after
  // a reload. Defer classification until that transcript renders (or the user
  // leaves); a route alone never proves that the question has been seen.
  if (
    task.family === "mock-interviews" &&
    state.state === "success" &&
    !previouslySeen &&
    document.visibilityState === "visible" &&
    !displayed &&
    window.location?.pathname.endsWith("/interview/mock") &&
    new URLSearchParams(window.location.search).get("session") === task.id
  )
    return;
  const sameSession =
    task.family === "mock-interviews" &&
    state.state === "success" &&
    document.visibilityState === "visible" &&
    displayed;
  if (
    sameSession &&
    !previouslySeen &&
    state.selection.question &&
    !displayed.has(state.selection.question)
  )
    return;
  if (sameSession && state.decision?.action === "finish" && !visibleMockCompletions.has(task.id))
    return;
  store(
    tasks.map((t) =>
      t.key === key
        ? {
            ...t,
            notice: state,
            ...((t.family === "mock-interviews" && t.seenError) ||
            foregroundState === state.state ||
            sameSession ||
            (t.family === "mock-interviews" && state.state === "success" && previouslySeen) ||
            (["mock-interviews", "interview-debriefs"].includes(t.family) &&
              t.notice &&
              t.dismissedState === t.notice.state)
              ? { dismissedState: state.state, shownState: state.state }
              : {}),
          }
        : t,
    ),
  );
}
export function markTaskShown(key: string, state: string) {
  store(trackedTasks().map((t) => (t.key === key ? { ...t, shownState: state } : t)));
}
/** Remember only question identities actually rendered in the foreground. A delayed
 * receipt read after navigation must not notify for a question the user already saw. */
export function markMockQuestionsSeen(id: string, questions: string[], completed = false) {
  if (document.visibilityState !== "visible" || (!questions.length && !completed)) return;
  const tasks = trackedTasks();
  let changed = false;
  const next = tasks.map((task) => {
    if (task.family !== "mock-interviews" || task.id !== id) return task;
    const seenQuestions = [...new Set([...(task.seenQuestions || []), ...questions])];
    const acknowledged =
      task.notice?.state === "success" &&
      ((!!task.notice.selection.question &&
        seenQuestions.includes(task.notice.selection.question)) ||
        (completed && task.notice.decision?.action === "finish"));
    if (
      seenQuestions.length === task.seenQuestions?.length &&
      (!completed || task.seenCompletion) &&
      (!acknowledged || task.dismissedState === "success")
    )
      return task;
    changed = true;
    return {
      ...task,
      seenQuestions,
      ...(completed ? { seenCompletion: true } : {}),
      ...(acknowledged ? { dismissedState: "success", shownState: "success" } : {}),
    };
  });
  if (changed) store(next);
}
export function pendingNotices(tasks: TrackedTask[]) {
  return tasks.filter((t) => t.notice && t.dismissedState !== t.notice.state);
}
/** A mounted operation error suppresses only its duplicate popup, not the inbox. */
export const visibleTaskErrors = new Set<string>();

/** Populated only by mounted, rendered Mock transcripts; never inferred from revisions. */
export const visibleMockQuestions = new Map<string, Set<string>>();

export const visibleMockCompletions = new Set<string>();

/** Exact execution state currently rendered by the owning page. */
export const visibleTaskStates = new Map<string, string>();
export function acknowledgeTaskState(key: string, state: TaskState) {
  const tracked = trackedTasks().find((t) => t.key === key);
  if (
    state.execution_revision !== undefined &&
    state.execution_revision < (tracked?.executionRevision || 0)
  )
    return;
  visibleTaskStates.set(key, state.state);
  recordTaskState(key, state);
  if (document.visibilityState !== "visible") return;
  const task = trackedTasks().find((t) => t.key === key);
  if (task?.notice?.state === state.state && task.dismissedState !== state.state)
    dismissTask(key, state.state);
}

/** Remember an exact server failure actually rendered, even if its receipt poll
 * arrives after the user has already started a different request. */
export function markTaskErrorSeen(key: string) {
  if (document.visibilityState !== "visible") return;
  const tasks = trackedTasks();
  const task = tasks.find((t) => t.key === key);
  if (!task || task.seenError) return;
  store(
    tasks.map((t) =>
      t.key === key
        ? {
            ...t,
            seenError: true,
            ...(t.notice ? { dismissedState: t.notice.state, shownState: t.notice.state } : {}),
          }
        : t,
    ),
  );
}
