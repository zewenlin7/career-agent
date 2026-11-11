"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { formatTime } from "@/lib/date-time";
import type { Actual, Context, Debrief, DebriefRow, Entry, Mock, Page } from "./contracts";
import { api, ApiError, endpoint, useAction, useRead } from "./client";
import { consumeEvents } from "./events";
import {
  trackExecution,
  recordTaskState,
  dismissTask,
  taskChange,
  trackedTasks,
} from "./task-tracker";
import { ReviewGroups } from "./review-groups";
import { acknowledgeTaskState, visibleTaskStates } from "./task-tracker";
import { taskMessage } from "./task-feedback";
import { ResultDestination } from "./result-destination";
import { DeleteRecord } from "./delete-record";
import { InterviewChoiceSelect, useInterviewChoices, interviewHref } from "./interview-choice";
import { readHistory } from "./history";
import { reviewRequest } from "./review-request";
import { control, ErrorNotice, ReadState } from "./ui";
export { KnowledgePage } from "./knowledge";
const terminal = (row: Debrief) => ["completed", "partial", "failed"].includes(row.status);
const readable = (row: Debrief) => row.artifacts.some((a) => a.status === "completed");
const exact = (id: string) => `interview-debriefs/${id}?historical=true`;
export function DebriefsPage({ ctx }: { ctx: Context }) {
  const search = useSearchParams();
  const choices = useInterviewChoices(ctx);
  const [sourceKey, setSourceKey] = useState("");
  const choice = choices.data?.find((c) => c.key === sourceKey);
  const source = useRead<Actual | Mock>(
    choice ? `${choice.kind === "actual" ? "interviews" : "mock-interviews"}/${choice.id}` : null,
  );
  const [question, setQuestion] = useState(true),
    [overall, setOverall] = useState(true);
  const [scope, setScope] = useState("all"),
    [groups, setGroups] = useState<string[]>([]);
  const history = useRead<Page<DebriefRow>>(
    `interview-debriefs?application_id=${ctx.application.id}`,
    readHistory,
  );
  const [result, setResult] = useState<Debrief>(),
    [task, setTask] = useState<Debrief>();
  const [readError, setReadError] = useState<string>();
  const [errorVisible, setErrorVisible] = useState(false);
  const [errorOwner, setErrorOwner] = useState<string>();
  const [executing, setExecuting] = useState(false);
  const [checkedStatus, setCheckedStatus] = useState("");
  const action = useAction(),
    selectionIntent = useRef(0),
    taskRef = useRef<Debrief | undefined>(undefined);
  const alive = useRef(true),
    running = useRef(false);
  const reloadHistory = history.reload;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    const requested = search.get("debrief");
    const taskId = search.get("task");
    const intent = selectionIntent.current;
    if (!requested && !taskId)
      queueMicrotask(() => {
        if (active && intent === selectionIntent.current) {
          setTask(undefined);
          taskRef.current = undefined;
          setResult(undefined);
          setCheckedStatus("");
          setErrorVisible(false);
        }
      });
    if (requested)
      void api<Debrief>(exact(requested))
        .then((row) => {
          if (active && intent === selectionIntent.current) {
            setResult(row);
            if (!terminal(row)) {
              setTask(row);
              taskRef.current = row;
            }
          }
        })
        .catch((e) => {
          if (active && intent === selectionIntent.current) setReadError(e.code);
        });
    if (taskId)
      void api<Debrief>(exact(taskId))
        .then((row) => {
          if (active && intent === selectionIntent.current) {
            setTask(row);
            taskRef.current = row;
          }
        })
        .catch((e) => {
          if (active && intent === selectionIntent.current) setReadError(e.code);
        });
    return () => {
      active = false;
    };
  }, [search]);
  useEffect(() => {
    const signature = () =>
      JSON.stringify(
        trackedTasks()
          .filter(
            (t) =>
              t.family === "interview-debriefs" &&
              t.href.startsWith(`/applications/${ctx.application.id}/review/debriefs`) &&
              t.notice,
          )
          .map((t) => [t.id, t.executionRevision, t.notice?.state]),
      );
    let previous = signature();
    const refresh = () => {
      const current = signature();
      if (current !== previous) {
        previous = current;
        reloadHistory();
      }
    };
    window.addEventListener(taskChange, refresh);
    return () => window.removeEventListener(taskChange, refresh);
  }, [ctx.application.id, reloadHistory]);
  useEffect(() => {
    if (!task || terminal(task) || executing) return;
    const id = task.id;
    const timer = setInterval(() => {
      void api<Debrief>(exact(id))
        .then((row) => {
          if (taskRef.current?.id !== id || !alive.current) return;
          taskRef.current = row;
          setTask(row);
          if (terminal(row)) {
            reloadHistory();
            if (readable(row)) {
              setResult(row);
              window.history.replaceState(null, "", `?debrief=${row.id}`);
            }
          }
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
  }, [task, executing, reloadHistory]);
  useEffect(() => {
    const rows = [task, result?.id === task?.id ? undefined : result].filter(
      (r): r is Debrief => !!r,
    );
    const keys = rows.map((r) => `interview-debriefs:${r.id}`);
    const observe = () =>
      rows.forEach((r) =>
        acknowledgeTaskState(`interview-debriefs:${r.id}`, {
          state:
            r.status === "completed"
              ? "success"
              : r.status === "failed"
                ? Object.values(r.recovery || {}).includes("unknown")
                  ? "unknown"
                  : "failure"
                : r.status === "running" && r.execution_active === false
                  ? "unknown"
                  : r.status,
          reason: Object.values(r.recovery || {}).includes("unknown")
            ? "execution_outcome_unknown"
            : r.artifacts.find((a) => a.status === "failed")?.error_code || undefined,
          selection: { debrief: r.id },
          execution_revision: r.execution_revision,
        }),
      );
    observe();
    document.addEventListener("visibilitychange", observe);
    return () => {
      keys.forEach((key) => visibleTaskStates.delete(key));
      document.removeEventListener("visibilitychange", observe);
    };
  }, [task, result]);
  const entries =
    source.data &&
    ("entries" in source.data
      ? source.data.entries
      : source.data.turns.map((t) => ({
          entry_id: t.id,
          kind: t.question.kind,
          primary_entry_id: t.question.primary_entry_id,
          question: t.question.question,
        })));
  const primary = entries?.filter((e) => e.kind === "primary") || [];
  const revision =
    source.data &&
    ("content_revision" in source.data ? source.data.content_revision : source.data.revision);
  const sourceReady =
    !!choice?.eligible && !!source.data && source.data.id === choice.id && revision;
  const valid =
    sourceReady && (question || overall) && (!question || scope === "all" || groups.length > 0);
  function adoptResult(row: Debrief) {
    setResult(row);
    window.history.replaceState(
      null,
      "",
      `/applications/${ctx.application.id}/review/debriefs?debrief=${row.id}`,
    );
  }
  async function loadResult(id: string) {
    const intent = ++selectionIntent.current;
    setErrorVisible(false);
    setTask(undefined);
    taskRef.current = undefined;
    setCheckedStatus("");
    if (!id) {
      setResult(undefined);
      setReadError(undefined);
      window.history.replaceState(null, "", `/applications/${ctx.application.id}/review/debriefs`);
      return;
    }
    try {
      const row = await api<Debrief>(exact(id));
      if (intent === selectionIntent.current && alive.current) {
        setResult(row);
        setReadError(undefined);
        window.history.replaceState(
          null,
          "",
          `/applications/${ctx.application.id}/review/debriefs?debrief=${id}`,
        );
      }
    } catch (e) {
      if (intent === selectionIntent.current)
        setReadError(e instanceof ApiError ? e.code : "request_failed");
    }
  }
  async function execute(row: Debrief, intent: number) {
    if (running.current) return;
    running.current = true;
    setExecuting(true);
    const accept = async () => {
      const fresh = await api<Debrief>(exact(row.id));
      if (alive.current && terminal(fresh)) reloadHistory();
      if (alive.current && taskRef.current?.id === row.id && selectionIntent.current === intent) {
        setTask(fresh);
        taskRef.current = fresh;
        if (readable(fresh) && selectionIntent.current === intent) adoptResult(fresh);
      }
    };
    try {
      trackExecution(`interview-debriefs/${row.id}/execute`, "POST", {
        execution_revision: row.execution_revision,
        application_id: ctx.application.id,
      });
      const response = await fetch(endpoint(`interview-debriefs/${row.id}/execute`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!response.ok) throw new ApiError((await response.json()).error?.code || "request_failed");
      if (!response.body) throw new ApiError("invalid_event_response");
      await consumeEvents(response.body, async (event) => {
        if (event.error_code) throw new ApiError(event.error_code);
        if (
          event.event?.endsWith("_completed") ||
          event.event?.endsWith("_failed") ||
          event.event === "run_partial"
        )
          await accept();
      });
      await accept();
    } finally {
      running.current = false;
      if (alive.current) setExecuting(false);
    }
  }
  const attach = (row: Debrief) => {
    setCheckedStatus("");
    setErrorOwner(row.id);
    setTask(row);
    taskRef.current = row;
  };
  const historical =
    history.data?.items.filter((r) => ["completed", "partial", "failed"].includes(r.status)) || [];
  const visibleOptions =
    result && !historical.some((r) => r.generation_id === result.id)
      ? [
          {
            generation_id: result.id,
            source_name: result.source_name,
            source_kind: result.snapshot.source_kind,
            created_at: result.created_at || "",
          },
          ...historical,
        ]
      : historical;
  const feedbackTask = task || result;
  const feedback = (
    <div aria-label="复盘执行状态" className="space-y-3">
      {feedbackTask && (
        <>
          {(["ready", "running"].includes(feedbackTask.status) ||
            (executing && task?.id === feedbackTask.id)) && (
            <p role="status" className="text-secondary">
              {(executing && task?.id === feedbackTask.id) ||
              (feedbackTask.status === "running" && feedbackTask.execution_active !== false)
                ? "正在生成复盘…"
                : feedbackTask.status === "running"
                  ? "执行结果尚未确认，请检查状态。"
                  : "待继续执行"}
            </p>
          )}
          {feedbackTask.artifacts
            .filter((a) => a.status === "failed")
            .map((a) => (
              <p key={a.id} className="text-secondary">
                {taskMessage(a.kind === "overall" ? "综合复盘" : `第${a.group_index}题组`, {
                  state: feedbackTask.recovery?.[a.id] === "unknown" ? "unknown" : "failure",
                  reason: a.error_code,
                })}
                {feedbackTask.recovery?.[a.id] === "retryable"
                  ? "可重试此失败项。"
                  : feedbackTask.recovery?.[a.id] === "recoverable"
                    ? "可恢复已生成内容，无需再次生成。"
                    : feedbackTask.recovery?.[a.id] === "incompatible"
                      ? "原执行材料暂不支持恢复，请保留已有结果。"
                      : ""}
              </p>
            ))}
          {checkedStatus && feedbackTask.status !== "completed" && (
            <p role="status" className="text-secondary">
              {checkedStatus}
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            {feedbackTask.status === "ready" && !executing && (
              <Button
                disabled={action.busy}
                onClick={() =>
                  void action.run(() => execute(feedbackTask, selectionIntent.current))
                }
              >
                继续复盘
              </Button>
            )}
            {!executing &&
              Object.values(feedbackTask.recovery || {}).some(
                (s) => s === "retryable" || s === "recoverable",
              ) && (
                <Button
                  disabled={action.busy}
                  onClick={() =>
                    void action.run(async () => {
                      const intent = selectionIntent.current;
                      setErrorVisible(true);
                      setErrorOwner(feedbackTask.id);
                      const payload = {
                        expected_execution_revision: feedbackTask.execution_revision || 0,
                      };
                      const row = await api<Debrief>(
                        `interview-debriefs/${feedbackTask.id}/retry`,
                        "POST",
                        {
                          ...payload,
                          request_id: await reviewRequest(
                            `debrief-retry:${feedbackTask.id}`,
                            payload,
                          ),
                        },
                      );
                      if (!alive.current || intent !== selectionIntent.current) return;
                      attach(row);
                      trackExecution(`interview-debriefs/${row.id}/execute`, "POST", {
                        execution_revision: row.execution_revision,
                      });

                      reloadHistory();
                      if (row.status === "ready") await execute(row, intent);
                      else if (readable(row) && intent === selectionIntent.current)
                        adoptResult(row);
                    })
                  }
                >
                  重试失败项
                </Button>
              )}
            {!executing &&
              ((feedbackTask.status === "running" && feedbackTask.execution_active === false) ||
                Object.values(feedbackTask.recovery || {}).includes("unknown")) && (
                <Button
                  disabled={action.busy}
                  onClick={() =>
                    void action.run(async () => {
                      const intent = selectionIntent.current;
                      setErrorVisible(true);
                      setErrorOwner(feedbackTask.id);
                      const fresh = await api<Debrief>(exact(feedbackTask.id));
                      if (!alive.current || intent !== selectionIntent.current) return;
                      attach(fresh);
                      setCheckedStatus(
                        JSON.stringify(fresh) === JSON.stringify(feedbackTask)
                          ? "状态未变化，尚未确认的执行不会自动重试。"
                          : "状态已更新。",
                      );
                      if (result?.id === fresh.id && readable(fresh)) setResult(fresh);
                      reloadHistory();
                    })
                  }
                >
                  检查状态
                </Button>
              )}
          </div>
        </>
      )}
      <ErrorNotice
        code={errorVisible && errorOwner === feedbackTask?.id ? action.error : undefined}
      />
    </div>
  );
  return (
    <section className="min-w-0 space-y-8 text-base font-normal leading-relaxed [overflow-wrap:anywhere]">
      <form
        className="flex flex-col items-center gap-5"
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid || !choice || !revision) return;
          const payload = {
            source_kind: choice.kind,
            interview_id: choice.id,
            application_id: ctx.application.id,
            expected_source_revision: revision,
            question_analysis: !question ? "none" : scope === "all" ? "all" : "selected",
            overall_analysis: overall,
            ...(question && scope === "selected"
              ? {
                  primary_entry_ids: primary
                    .filter((e) => groups.includes(e.entry_id))
                    .map((e) => e.entry_id),
                }
              : {}),
            mode: "live",
          };
          const intent = ++selectionIntent.current;
          setTask(undefined);
          taskRef.current = undefined;
          setCheckedStatus("");
          setErrorVisible(true);
          setErrorOwner("create");
          void action.run(async () => {
            const row = await api<Debrief>("interview-debriefs", "POST", {
              ...payload,
              request_id: await reviewRequest(`debrief-create:${ctx.application.id}`, payload),
            });
            sessionStorage.removeItem(`debrief-create:${ctx.application.id}`);
            if (alive.current && intent === selectionIntent.current) {
              attach(row);
              window.history.replaceState(null, "", `?task=${row.id}`);
            }
            if (alive.current && readable(row) && intent === selectionIntent.current)
              adoptResult(row);
            reloadHistory();
            if (row.status === "ready") await execute(row, intent);
          });
        }}
      >
        <InterviewChoiceSelect
          rows={choices.data || []}
          eligibleOnly
          value={sourceKey}
          onChange={(key) => {
            setSourceKey(key);
            setGroups([]);
          }}
        />
        <ErrorNotice code={choices.error || source.error} />
        <div className="flex max-w-full flex-wrap items-center justify-center gap-x-6 gap-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-medium">复盘内容</span>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={question}
                onChange={(e) => {
                  setQuestion(e.target.checked);
                  if (!e.target.checked) setGroups([]);
                }}
              />
              逐题分析
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={overall}
                onChange={(e) => setOverall(e.target.checked)}
              />
              整场综合复盘
            </label>
          </div>
          {question && (
            <label className="flex items-center gap-3 font-medium">
              逐题范围
              <select
                aria-label="逐题范围"
                className={`${control.replace("w-full", "w-auto").replace("text-sm", "text-base")}`}
                value={scope}
                onChange={(e) => {
                  setScope(e.target.value);
                  setGroups([]);
                }}
              >
                <option value="all">全部题组</option>
                <option value="selected">指定题组</option>
              </select>
            </label>
          )}
        </div>
        {sourceReady && question && scope === "selected" && (
          <ReviewGroups
            key={sourceKey}
            entries={entries || []}
            selected={groups}
            onChange={setGroups}
          />
        )}
        {!question && !overall && (
          <p role="status" className="text-secondary">
            至少选择一项复盘内容。
          </p>
        )}
        <Button
          variant="primary"
          type="submit"
          disabled={!valid || action.busy || executing || task?.status === "running"}
        >
          开始复盘
        </Button>
        {choice && sourceReady && (
          <p className="text-center text-sm text-secondary">
            基于「
            <Link
              className="underline underline-offset-4"
              href={interviewHref(ctx.application.id, choice.kind, choice.id)}
            >
              {choice.name}
            </Link>
            」生成
          </p>
        )}
      </form>
      {task && task.id !== result?.id && feedback}
      {errorOwner === "create" && <ErrorNotice code={errorVisible ? action.error : undefined} />}
      <div className="space-y-5">
        <label className="flex max-w-[42rem] flex-wrap items-center gap-3 font-medium">
          <span>复盘记录</span>
          <select
            aria-label="复盘记录"
            className={`${control.replace("text-sm", "text-base")} min-w-0 flex-1 basis-64`}
            value={result?.id || ""}
            onChange={(e) => {
              void loadResult(e.target.value);
            }}
          >
            <option value="">选择一条复盘记录</option>
            {visibleOptions.map((r) => (
              <option key={r.generation_id} value={r.generation_id}>
                {r.source_name || (r.source_kind === "actual" ? "真实面试" : "模拟面试")} ·{" "}
                {r.created_at ? formatTime(r.created_at) : "历史记录"}
              </option>
            ))}
          </select>
        </label>
        <ReadState loaded={!!history.data} error={history.error} />
        <ErrorNotice code={readError} />
        {(!task || task.id === result?.id) && feedback}
        {result && (
          <DebriefResult
            key={result.id}
            data={result}
            onDeleted={async () => {
              ++selectionIntent.current;
              setResult(undefined);
              setReadError(undefined);
              sessionStorage.removeItem(`debrief-create:${ctx.application.id}`);
              const key = `interview-debriefs:${result.id}`;
              recordTaskState(key, { state: "removed", selection: {} });
              dismissTask(key, "removed");
              if (task?.id === result.id) {
                setTask(undefined);
                taskRef.current = undefined;
              }
              const page = await readHistory<DebriefRow>(
                `interview-debriefs?application_id=${ctx.application.id}`,
                new AbortController().signal,
              );
              reloadHistory();
              const next = page.items.find((r) =>
                ["completed", "partial", "failed"].includes(r.status),
              );
              if (next) await loadResult(next.generation_id);
              else
                window.history.replaceState(
                  null,
                  "",
                  `/applications/${ctx.application.id}/review/debriefs`,
                );
            }}
          />
        )}
        {!result && history.data && !historical.length && (
          <p className="text-secondary">还没有复盘记录。</p>
        )}
      </div>
    </section>
  );
}
const labels: Record<string, string> = {
  strengths: "优势",
  issues: "问题",
  knowledge_gap_hypotheses: "知识缺口假设",
  improvement_suggestions: "改进建议",
  recurring_issues: "反复问题",
  practice_recommendations: "练习建议",
  knowledge_candidates: "知识候选",
};
const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" ? (v as Record<string, unknown>) : {};
export function DebriefResult({
  data,
  onDeleted,
}: {
  data: Debrief;
  onDeleted: () => Promise<void>;
}) {
  const frozen = useRef<HTMLDetailsElement>(null);
  const entries = data.transcript || data.snapshot.entries;
  const number = (e: Entry) =>
    "question_number" in e
      ? String(e.question_number)
      : `${e.main_question_number || ""}${e.followup_index ? `.${e.followup_index}` : ""}`;
  const reveal = (id?: string) => {
    if (frozen.current) frozen.current.open = true;
    requestAnimationFrame(() => {
      const node = id ? document.getElementById(`frozen-${data.id}-${id}`) : frozen.current;
      node?.scrollIntoView({ block: "center", behavior: "smooth" });
      node?.focus({ preventScroll: true });
    });
  };
  const artifacts = [...data.artifacts].sort(
    (a, b) =>
      (a.kind === "overall" ? 1 : 0) - (b.kind === "overall" ? 1 : 0) ||
      a.presentation.display_order - b.presentation.display_order,
  );
  return (
    <ResultDestination identity={data.id} requested={data.id}>
      <div className="max-w-[860px] space-y-6">
        {data.source_changed === true && (
          <p className="text-secondary">这场面试记录已修改，当前复盘仍基于修改前的内容。</p>
        )}
        <details ref={frozen} className="space-y-4">
          <summary className="cursor-pointer text-secondary">查看原始问答</summary>
          <div className="space-y-5">
            {entries.map((e) => (
              <div
                id={`frozen-${data.id}-${e.entry_id}`}
                key={e.entry_id}
                tabIndex={-1}
                className={e.kind === "follow_up" ? "ml-5 space-y-2" : "space-y-2"}
              >
                <h3 className="font-semibold">问题 {number(e)}</h3>
                <p className="whitespace-pre-wrap">{e.question}</p>
                <p className="whitespace-pre-wrap">{e.answer || "未记录回答"}</p>
              </div>
            ))}
            {!!data.snapshot.notes?.length && (
              <section>
                <h3 className="font-semibold">笔记</h3>
                {data.snapshot.notes.map((n, i) => (
                  <p key={i} className="whitespace-pre-wrap">
                    {n.text}
                  </p>
                ))}
              </section>
            )}
          </div>
        </details>
        <div className="divide-y divide-line">
          {artifacts.map((artifact, i) => {
            const group = entries.filter(
              (e) => e.entry_id === artifact.group_ref || e.primary_entry_id === artifact.group_ref,
            );
            const evaluation = artifact.presentation.evaluation || {};
            return (
              <article
                key={artifact.id}
                className="space-y-4 py-6 first:pt-0"
                aria-label={
                  artifact.kind === "overall" ? "综合复盘" : `第 ${artifact.group_index} 题组`
                }
              >
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-lg font-semibold">
                    {artifact.kind === "overall" ? "综合复盘" : `第 ${artifact.group_index} 题组`}
                  </h2>
                  {group.length === 1 && (
                    <button
                      className="text-sm text-secondary underline underline-offset-4"
                      onClick={() => reveal(group[0].entry_id)}
                    >
                      查看原始问答
                    </button>
                  )}
                  {i === 0 && (
                    <div className="ml-auto">
                      <DeleteRecord path={`interview-debriefs/${data.id}`} onDeleted={onDeleted} />
                    </div>
                  )}
                </div>
                {artifact.status !== "completed" && (
                  <p className="text-secondary">
                    {artifact.status === "failed"
                      ? artifact.kind === "overall"
                        ? "综合复盘未完成"
                        : "此题组分析未完成"
                      : "正在分析…"}
                  </p>
                )}
                {Object.entries(labels).map(([key, label]) =>
                  Array.isArray(evaluation[key]) && (evaluation[key] as unknown[]).length > 0 ? (
                    <section key={key} className="space-y-2">
                      <h3 className="font-semibold">{label}</h3>
                      <ul className="space-y-3">
                        {(evaluation[key] as unknown[]).map((raw, index) => {
                          const finding = obj(raw),
                            evidence = Array.isArray(finding.evidence)
                              ? finding.evidence.map(obj)
                              : [];
                          const implied =
                            artifact.kind === "group" &&
                            group.length === 1 &&
                            evidence.length > 0 &&
                            evidence.every((e) => e.entry_id === group[0].entry_id);
                          return (
                            <li key={index}>
                              <span className="whitespace-pre-wrap">
                                {String(finding.content || "")}
                              </span>
                              {!implied && evidence.length > 0 && (
                                <span className="ml-2 text-sm text-secondary">
                                  依据：
                                  {evidence.map((e, j) => (
                                    <span key={j}>
                                      {j > 0 && "、"}
                                      {typeof e.entry_id === "string" &&
                                      entries.some((entry) => entry.entry_id === e.entry_id) ? (
                                        <button
                                          className="underline underline-offset-4"
                                          onClick={() => reveal(String(e.entry_id))}
                                        >
                                          {String(e.question_number)}
                                        </button>
                                      ) : (
                                        <span>
                                          {e.group_index ? `第${e.group_index}题组` : "来源待核实"}
                                        </span>
                                      )}
                                    </span>
                                  ))}
                                </span>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    </section>
                  ) : null,
                )}
                {!!evaluation.example_answer && (
                  <section className="space-y-2">
                    <h3 className="font-semibold">示例回答</h3>
                    <p className="whitespace-pre-wrap">
                      {String(obj(evaluation.example_answer).content || "")}
                    </p>
                  </section>
                )}
              </article>
            );
          })}
        </div>
      </div>
    </ResultDestination>
  );
}
