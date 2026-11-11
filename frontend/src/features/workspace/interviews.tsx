"use client";
import { InterviewChoiceSelect, useInterviewChoices, interviewHref } from "./interview-choice";
import {
  recordTaskState,
  acknowledgeTaskState,
  visibleTaskStates,
  markMockQuestionsSeen,
  markTaskErrorSeen,
  visibleMockQuestions,
  visibleMockCompletions,
  visibleTaskErrors,
  type TaskState,
} from "./task-tracker";
import { mockGroups } from "./mock-contract";
import { ResultDestination } from "./result-destination";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { SourceLinks } from "./source-links";
import { formatTime } from "@/lib/date-time";
import type { ApplicationBinding } from "./application-binding";
import { readHistory } from "./history";
import { ActualDetail } from "./actual-interview";
export { ActualPage, ActualDetail } from "./actual-interview";
import { useState, useEffect, useRef, useCallback } from "react";
import { useConfirmation } from "../profile-area/confirmation";
import { Button } from "@/components/ui/button";
import type { Context, Mock, Page, SessionRow } from "./contracts";
import { api, useAction, useRead, useRequestId } from "./client";
import { control, ErrorNotice, Field, ReadState, Select } from "./ui";
export function MockPage({ ctx }: { ctx: Context }) {
  const search = useSearchParams();
  const binding = useRead<ApplicationBinding>(`applications/${ctx.application.id}/context`);
  const id = search.get("session") || "";
  const [initial, setInitial] = useState<Mock>();
  const [initialRequest, setInitialRequest] = useState("");
  const sessions = useRead<Page<SessionRow>>(
    !id ? `mock-interviews?application_id=${ctx.application.id}` : null,
    readHistory,
  );
  const unfinished = sessions.data?.items.filter((row) => row.status !== "completed") || [];
  const [focus, setFocus] = useState("mixed"),
    [policy, setPolicy] = useState("quick"),
    [primary, setPrimary] = useState(3),
    [follow, setFollow] = useState(1);
  const action = useAction();
  const requestId = useRequestId();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return (
    <div className="space-y-6 text-base font-normal leading-relaxed">
      {!id && (
        <section className="space-y-4">
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                if (!binding.data?.profile_id || !binding.data.resume_revision_id) return;
                setInitial(undefined);
                setInitialRequest("");
                const creation = {
                  application_binding: {
                    application_id: ctx.application.id,
                    revision: binding.data.revision,
                  },
                  context: {
                    profile_id: binding.data.profile_id,
                    job_revision_id: binding.data.job_revision_id,
                    resume_revision_id: binding.data.resume_revision_id,
                  },
                  focus,
                  policy: {
                    mode: policy,
                    ...(policy === "custom"
                      ? { primary_target: primary, followup_max: follow }
                      : {}),
                  },
                  mode: "live",
                };
                // Retain creation identity through response loss and reload, without
                // storing user text or replaying automatically on navigation.
                const storageKey = `mock-creation:${ctx.application.id}`;
                const fingerprint = JSON.stringify(creation);
                let creationId = requestId(creation);
                try {
                  const previous = JSON.parse(sessionStorage.getItem(storageKey) || "null");
                  if (previous?.fingerprint === fingerprint) creationId = previous.id;
                  sessionStorage.setItem(
                    storageKey,
                    JSON.stringify({ fingerprint, id: creationId }),
                  );
                } catch {
                  /* Optional local retry identity. */
                }
                let result: Mock;
                try {
                  result = await api<Mock>("mock-interviews", "POST", {
                    ...creation,
                    request_id: creationId,
                  });
                } catch (error) {
                  // A lost creation response may already have committed. Resolve its
                  // exact identity before offering another explicit attempt.
                  const history = await readHistory<SessionRow>(
                    `mock-interviews?application_id=${ctx.application.id}`,
                    new AbortController().signal,
                  );
                  const saved = history.items.find((row) => row.creation_request_id === creationId);
                  if (!saved) {
                    sessions.reload();
                    throw error;
                  }
                  result = await api<Mock>(`mock-interviews/${saved.id}`);
                }
                if (mounted.current) {
                  setInitial(result);
                  window.history.replaceState(
                    null,
                    "",
                    `/applications/${ctx.application.id}/interview/mock?session=${result.id}`,
                  );
                }
                try {
                  if (result.revision !== 1 || result.status !== "ready_to_generate") return;
                  const body = { expected_revision: result.revision };
                  const generationRequest = requestId({ session: result.id, ...body });
                  if (mounted.current) setInitialRequest(generationRequest);
                  const generated = await api<Mock>(
                    `mock-interviews/${result.id}/generate`,
                    "POST",
                    {
                      ...body,
                      request_id: generationRequest,
                    },
                  );
                  if (mounted.current) setInitial(generated);
                } finally {
                  try {
                    sessionStorage.removeItem(storageKey);
                  } catch {
                    /* Optional storage. */
                  }
                }
              });
            }}
          >
            <fieldset disabled={action.busy} className="space-y-4">
              <ErrorNotice code={binding.error} />
              {!binding.data?.resume_revision_id && (
                <p>
                  请先在
                  <Link href={`/applications/${ctx.application.id}/summary`} className="underline">
                    概览
                  </Link>
                  中选择简历。
                </p>
              )}
              <div className="flex flex-wrap items-center justify-center gap-4">
                <Select
                  inline
                  recordWidth="content"
                  label="练习重点"
                  value={focus}
                  onChange={(e) => setFocus(e.target.value)}
                >
                  {["mixed", "technical", "project", "behavioral", "company_specific"].map((v) => (
                    <option key={v} value={v}>
                      {
                        (
                          {
                            mixed: "综合",
                            technical: "技术",
                            project: "项目",
                            behavioral: "行为",
                            company_specific: "公司相关",
                          } as Record<string, string>
                        )[v]
                      }
                    </option>
                  ))}
                </Select>
                <Select
                  inline
                  recordWidth="content"
                  label="问题数量模式"
                  value={policy}
                  onChange={(e) => setPolicy(e.target.value)}
                >
                  <option value="quick">快速 · 3 主问题 / 最多 1 追问</option>
                  <option value="standard">标准 · 5 主问题 / 最多 3 追问</option>
                  <option value="long">完整 · 8 主问题 / 最多 5 追问</option>
                  <option value="custom">自定义</option>
                </Select>
              </div>
              {policy === "custom" && (
                <>
                  <Field label="主问题数量" labelClassName="text-lg font-semibold">
                    <input
                      className={control.replace("text-sm", "text-base")}
                      type="number"
                      min={1}
                      max={8}
                      required
                      value={primary}
                      onChange={(e) => setPrimary(Number(e.target.value))}
                    />
                  </Field>
                  <Field label="追问上限" labelClassName="text-lg font-semibold">
                    <input
                      className={control.replace("text-sm", "text-base")}
                      type="number"
                      min={0}
                      max={Math.min(5, primary)}
                      required
                      value={follow}
                      onChange={(e) => setFollow(Number(e.target.value))}
                    />
                  </Field>
                </>
              )}
              <div className="text-center">
                <Button
                  type="submit"
                  variant="primary"
                  disabled={!binding.data?.resume_revision_id}
                >
                  {action.busy ? "正在创建模拟面试…" : "开始模拟面试"}
                </Button>
                <div className="mt-2">
                  <SourceLinks
                    applicationId={ctx.application.id}
                    jd={binding.data?.job_revision_id}
                    resume={binding.data?.resume_revision_id}
                    resumeName={binding.data?.resume_name}
                  />
                </div>
              </div>
            </fieldset>
          </form>
          <ErrorNotice code={!initial ? action.error : undefined} />
          <ErrorNotice code={sessions.error} />
          <UnfinishedMocks unfinished={unfinished} applicationId={ctx.application.id} />
        </section>
      )}
      {id && (
        <MockDetail
          key={id}
          id={id}
          ctx={ctx}
          initial={initial?.id === id ? initial : undefined}
          starting={action.busy && initial?.id === id}
          initialRequest={initial?.id === id ? initialRequest : ""}
          initialError={initial?.id === id ? action.error : undefined}
        />
      )}
    </div>
  );
}
function UnfinishedMocks({
  unfinished,
  applicationId,
}: {
  unfinished: SessionRow[];
  applicationId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      {!!unfinished.length && (
        <div className="space-y-3">
          <button
            className="text-base font-semibold leading-relaxed text-secondary underline"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            继续未完成的模拟面试（{unfinished.length}）
          </button>
          {expanded && (
            <ul className="space-y-3">
              {unfinished.map((row) => (
                <li
                  key={row.id}
                  className="flex min-w-0 flex-wrap items-center justify-between gap-3 border-b border-line pb-3 last:border-0 last:pb-0"
                >
                  <div className="min-w-0 [overflow-wrap:anywhere]">
                    <p className="font-semibold">
                      {row.display_number
                        ? `第 ${row.display_number} 次模拟面试`
                        : `模拟面试 · ${formatTime(row.created_at)}`}
                    </p>
                    <p className="text-base font-normal leading-relaxed text-secondary">
                      {(
                        {
                          mixed: "综合",
                          technical: "技术",
                          project: "项目",
                          behavioral: "行为",
                          company_specific: "公司相关",
                        } as Record<string, string>
                      )[row.focus || ""] || "模拟练习"}
                      {row.policy &&
                        ` · ${({ quick: "快速", standard: "标准", long: "完整", custom: "自定义" } as Record<string, string>)[row.policy.mode] || "练习"}`}
                      {row.primary_question_count !== undefined &&
                        ` · 主问题 ${row.primary_question_count}${row.policy ? ` / ${row.policy.primary_target}` : ""} · 追问 ${row.followup_count ?? 0}`}
                      {` · ${row.generation_active ? "正在准备题目" : row.stop_reason ? "需要处理" : row.status === "waiting_answer" ? "等待回答" : "待生成题目"}`}
                    </p>
                  </div>
                  <Link
                    className="shrink-0 text-accent-ink underline"
                    href={`/applications/${applicationId}/interview/mock?session=${row.id}`}
                  >
                    继续模拟
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </>
  );
}
function MockLoading({ first = false }: { first?: boolean }) {
  return (
    <p
      role="status"
      className="flex items-center gap-2 text-base font-normal leading-relaxed text-secondary"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="size-4 shrink-0 animate-spin motion-reduce:animate-none"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="12" cy="12" r="9" opacity=".25" />
        <path d="M12 3a9 9 0 0 1 9 9" />
      </svg>
      {first ? "正在准备第 1 题…" : "正在准备下一道问题…"}
    </p>
  );
}
export function MockDetail({
  id,
  ctx,
  readOnly = false,
  initial,
  starting = false,
  initialRequest = "",
  initialError,
}: {
  id: string;
  ctx: Context;
  readOnly?: boolean;
  initial?: Mock;
  starting?: boolean;
  initialRequest?: string;
  initialError?: string;
}) {
  const read = useRead<Mock>(`mock-interviews/${id}`),
    [updated, setUpdated] = useState<Mock>(),
    [draft, setDraft] = useState({ question: "", text: "" }),
    [answerError, setAnswerError] = useState("");
  const { confirm, confirmation } = useConfirmation();
  const search = useSearchParams();
  const action = useAction(),
    requestId = useRequestId();
  const [activeRequest, setActiveRequest] = useState("");
  const currentRequest = activeRequest || initialRequest;
  const [requestOutcome, setRequestOutcome] = useState<{ request: string; state: TaskState }>();
  const actionError =
    requestOutcome?.request === currentRequest && requestOutcome.state.state === "success"
      ? undefined
      : action.error || (!activeRequest ? initialError : undefined);
  useEffect(() => {
    if (!actionError || !currentRequest) return;
    const key = `mock-interviews:${id}:${currentRequest}`;
    visibleTaskErrors.add(key);
    return () => {
      visibleTaskErrors.delete(key);
    };
  }, [actionError, id, currentRequest]);
  const data = [updated, read.data, initial]
    .filter((value): value is Mock => !!value)
    .sort((a, b) => b.revision - a.revision)[0];
  const answer = draft.question === data?.pending_question_id ? draft.text : "";
  const apply = useCallback((value: Mock) => {
    setUpdated((current) => (current && current.revision > value.revision ? current : value));
  }, []);
  useEffect(() => {
    if (
      readOnly ||
      !data?.stop_reason ||
      !data.latest_request_id ||
      data.application_id !== ctx.application.id
    )
      return;
    const key = `mock-interviews:${id}:${data.latest_request_id}`;
    visibleTaskErrors.add(key);
    const observe = () => markTaskErrorSeen(key);
    observe();
    document.addEventListener("visibilitychange", observe);
    return () => {
      visibleTaskErrors.delete(key);
      document.removeEventListener("visibilitychange", observe);
    };
  }, [
    id,
    data?.stop_reason,
    data?.latest_request_id,
    data?.application_id,
    ctx.application.id,
    readOnly,
  ]);
  useEffect(() => {
    const key = `mock-answer:${id}:${data?.pending_question_id || ""}`;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        setDraft({
          question: data?.pending_question_id || "",
          text: sessionStorage.getItem(key) || "",
        });
      } catch {
        /* Optional local recovery. */
      }
    });
    return () => {
      active = false;
    };
  }, [id, data?.pending_question_id]);
  useEffect(() => {
    if (!data || data.application_id !== ctx.application.id) return;
    visibleMockQuestions.set(id, new Set(data.turns.map((turn) => turn.id)));
    if (data.status === "completed") visibleMockCompletions.add(id);
    markMockQuestionsSeen(
      id,
      data.turns.map((turn) => turn.id),
      data.status === "completed",
    );
    return () => {
      visibleMockQuestions.delete(id);
      visibleMockCompletions.delete(id);
    };
  }, [id, data, ctx.application.id]);

  useEffect(() => {
    if (readOnly || !data || data.application_id !== ctx.application.id) return;
    const request = currentRequest || data.latest_request_id;
    if (!request) return;
    const key = `mock-interviews:${id}:${request}`;
    const outcome = requestOutcome?.request === request ? requestOutcome.state : undefined;
    const observe = () => {
      // A success is acknowledged only once its exact question/completion renders.
      const rendered =
        outcome?.state !== "success" ||
        (outcome.decision?.action === "finish"
          ? data.status === "completed"
          : data.turns.some((t) => t.id === outcome.selection.question));
      if (outcome && rendered) acknowledgeTaskState(key, outcome);
      else if (data.generation_active || starting || action.busy)
        visibleTaskStates.set(key, "running");
      else visibleTaskStates.delete(key);
    };
    observe();
    document.addEventListener("visibilitychange", observe);
    return () => {
      visibleTaskStates.delete(key);
      document.removeEventListener("visibilitychange", observe);
    };
  }, [
    id,
    data,
    ctx.application.id,
    readOnly,
    currentRequest,
    requestOutcome,
    starting,
    action.busy,
  ]);

  const shouldPoll = !!data && (data.generation_active || starting || action.busy || !!actionError);
  useEffect(() => {
    if (!shouldPoll) return;
    let active = true;
    const timer = setInterval(() => {
      const request = activeRequest || initialRequest;
      // Publish the transcript and its receipt together. A fast successful receipt
      // must not stop polling and cancel the still-pending transcript read.
      void Promise.all([
        api<Mock>(`mock-interviews/${id}`),
        request
          ? api<TaskState>(`task-status/mock-interviews/${id}?request_id=${request}`).catch(
              () => undefined,
            )
          : Promise.resolve(undefined),
      ])
        .then(([value, state]) => {
          if (!active) return;
          apply(value);
          if (state) {
            setRequestOutcome({ request, state });
            recordTaskState(`mock-interviews:${id}:${request}`, state);
          }
        })
        .catch(() => {});
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [id, shouldPoll, initialRequest, activeRequest, apply]);
  const refresh = () => action.run(async () => apply(await api<Mock>(`mock-interviews/${id}`)));
  const act = (type: "answers" | "generate" | "end" | "recover") =>
    action.run(async () => {
      if (!data) return;
      let requestForStatus = activeRequest || initialRequest;
      if (type === "recover") {
        const current = await api<Mock>(`mock-interviews/${id}`);
        apply(current);
        if (current.latest_request_id) {
          requestForStatus = current.latest_request_id;
          setActiveRequest(requestForStatus);
          const state = await api<TaskState>(
            `task-status/mock-interviews/${id}?request_id=${current.latest_request_id}`,
          );
          setRequestOutcome({ request: current.latest_request_id, state });
          recordTaskState(`mock-interviews:${id}:${current.latest_request_id}`, state);
          if (state.state === "success" || state.state === "running") return;
        }
        if (
          current.generation_active ||
          current.revision !== data.revision ||
          current.status !== "ready_to_generate"
        )
          return;
      }
      if (type === "answers" && !answer.trim()) {
        setAnswerError("请输入回答后再提交。");
        return;
      }
      setAnswerError("");
      const saveAndEnd = type === "end" && !!answer.trim() && data.status === "waiting_answer";
      const payload = {
        expected_revision: data.revision,
        ...(type === "answers" || saveAndEnd
          ? {
              pending_question_id: data.pending_question_id,
              answer: answer.trim(),
              end_early: saveAndEnd,
            }
          : {}),
      };
      const submittedRequest = requestId({ type, ...payload });
      if (type !== "recover" || !requestForStatus) requestForStatus = submittedRequest;
      setActiveRequest(requestForStatus);
      setRequestOutcome(undefined);
      let result: Mock;
      try {
        result = await api<Mock>(`mock-interviews/${id}/${saveAndEnd ? "answers" : type}`, "POST", {
          ...payload,
          request_id: submittedRequest,
        });
      } catch (error) {
        try {
          apply(await api<Mock>(`mock-interviews/${id}`));
          const request = requestForStatus;
          const state = await api<TaskState>(
            `task-status/mock-interviews/${id}?request_id=${request}`,
          );
          setRequestOutcome({ request, state });
          if (state.state === "success") return;
        } catch {
          /* Unknown: never replay. */
        }
        throw error;
      }
      apply(result);
      if (
        type === "answers" &&
        result.turns.some((t) => t.id === data.pending_question_id && t.answer !== null)
      ) {
        try {
          sessionStorage.removeItem(`mock-answer:${id}:${data.pending_question_id}`);
        } catch {
          /* Optional local recovery. */
        }
      }
    });
  const end = async () => {
    if (await confirm("结束本场练习？当前填写的回答会一并保存。")) void act("end");
  };
  const invalid = data && data.application_id !== ctx.application.id;
  const generating =
    !readOnly &&
    data?.status === "ready_to_generate" &&
    (data.generation_active || ((starting || action.busy) && !data.stop_reason));
  const groups = mockGroups(data?.turns || []);
  return (
    <section className="min-w-0 space-y-5 text-base font-normal leading-relaxed [overflow-wrap:anywhere]">
      {confirmation}
      <ReadState
        loaded={!!data}
        error={invalid ? "context_revision_mismatch" : !data ? read.error : undefined}
      />
      {data && !invalid && (
        <ResultDestination
          identity={data.id}
          requested={search.get("session")}
          ready={data.turns.length > 0 || data.status === "completed"}
          anchor={
            search.get("question") && data.turns.some((t) => t.id === search.get("question"))
              ? `[data-question-id="${search.get("question")}"]`
              : data.status !== "completed"
                ? "[data-current-question=true]"
                : undefined
          }
        >
          {data.status === "completed" && (
            <p className="text-base text-secondary">模拟面试已完成</p>
          )}
          {data.interviewer_turn_count > 0 && (
            <p className="text-base text-secondary">
              主问题 {data.primary_question_count} / {data.policy.primary_target} · 追问{" "}
              {data.followup_count} / {data.policy.followup_max}
            </p>
          )}

          {data.stop_reason && <ErrorNotice code={data.stop_reason} />}
          <ol className="space-y-5">
            {groups.map((group) => (
              <li
                key={group[0].id}
                className="space-y-5 border-b border-line pb-5 last:border-0 last:pb-0"
              >
                {group.map((t) => (
                  <div
                    key={t.id}
                    data-current-question={t.id === data.pending_question_id}
                    data-question-id={t.id}
                    className={t.question.kind === "follow_up" ? "ml-5" : undefined}
                  >
                    <p className="font-semibold text-ink">问题 {t.question_number}</p>
                    <p className="whitespace-pre-wrap">{t.question.question}</p>
                    {t.answer !== null && (
                      <div className="mt-3 space-y-1" data-saved-answer>
                        <p className="text-secondary">我的回答</p>
                        <p className="whitespace-pre-wrap">{t.answer}</p>
                      </div>
                    )}
                    {!readOnly &&
                      t.id === data.pending_question_id &&
                      t.answer === null &&
                      data.status === "waiting_answer" && (
                        <form
                          className="mt-3 space-y-3"
                          onSubmit={(event) => {
                            event.preventDefault();
                            void act("answers");
                          }}
                        >
                          <textarea
                            aria-label="本题回答"
                            placeholder="输入你的回答…"
                            className={control.replace("text-sm", "text-base") + " leading-relaxed"}
                            required
                            maxLength={20000}
                            value={answer}
                            disabled={action.busy || data.generation_active}
                            onChange={(event) => {
                              setDraft({ question: t.id, text: event.target.value });
                              try {
                                sessionStorage.setItem(
                                  `mock-answer:${id}:${t.id}`,
                                  event.target.value,
                                );
                              } catch {
                                /* Optional local recovery. */
                              }
                            }}
                          />
                          {answerError && (
                            <p role="alert" className="text-base text-error">
                              {answerError}
                            </p>
                          )}
                          <div className="flex flex-wrap items-center gap-3">
                            <Button
                              type="submit"
                              variant="primary"
                              disabled={action.busy || data.generation_active}
                            >
                              {action.busy && draft.question === t.id
                                ? "正在提交…"
                                : "提交回答并继续"}
                            </Button>
                            <Button
                              disabled={action.busy || data.generation_active}
                              onClick={() => void end()}
                            >
                              提前结束
                            </Button>
                          </div>
                        </form>
                      )}
                    {generating && t.id === data.turns.at(-1)?.id && t.answer !== null && (
                      <div className="mt-3">
                        <MockLoading />
                      </div>
                    )}
                  </div>
                ))}
              </li>
            ))}
          </ol>
          {!readOnly && data.status === "ready_to_generate" && !generating && (
            <Button
              disabled={action.busy}
              onClick={() =>
                void act(
                  [
                    "recovery_decision_required",
                    "execution_outcome_unknown",
                    "artifact_save_failed",
                  ].includes(data.stop_reason || "") || !!actionError
                    ? "recover"
                    : "generate",
                )
              }
            >
              {[
                "recovery_decision_required",
                "execution_outcome_unknown",
                "artifact_save_failed",
              ].includes(data.stop_reason || "") || !!actionError
                ? "检查状态"
                : data.stop_reason
                  ? "重试生成"
                  : "生成下一题"}
            </Button>
          )}
          {generating && !data.turns.length && <MockLoading first />}
          {!readOnly && data.status === "ready_to_generate" && !generating && (
            <Button disabled={action.busy} onClick={() => void end()}>
              提前结束
            </Button>
          )}
          {data.stop_reason && (
            <Button disabled={action.busy} onClick={() => void refresh()}>
              重新加载
            </Button>
          )}
          {readOnly && data.status !== "completed" && (
            <div className="mt-5">
              <Link
                className="text-base text-accent-ink underline"
                href={`/applications/${ctx.application.id}/interview/mock?session=${id}`}
              >
                继续模拟
              </Link>
            </div>
          )}
        </ResultDestination>
      )}
      <ErrorNotice code={actionError !== data?.stop_reason ? actionError : undefined} />
    </section>
  );
}
export function HistoryPage({ ctx }: { ctx: Context }) {
  const search = useSearchParams();
  const [selected, setSelected] = useState(
    search.get("actual")
      ? `actual:${search.get("actual")}`
      : search.get("session")
        ? `mock:${search.get("session")}`
        : "",
  );
  const choices = useInterviewChoices(ctx);
  const [kind, id] = selected.split(":");
  return (
    <section className="min-w-0 space-y-6 [overflow-wrap:anywhere]">
      <InterviewChoiceSelect
        rows={choices.data || []}
        value={selected}
        onChange={(key) => {
          setSelected(key);
          const [type, value] = key.split(":");
          window.history.replaceState(
            null,
            "",
            key
              ? interviewHref(ctx.application.id, type as "actual" | "mock", value)
              : `/applications/${ctx.application.id}/interview/history`,
          );
        }}
      />
      <ReadState loaded={!!choices.data} error={choices.error} />
      {id &&
        (kind === "mock" ? (
          <MockDetail key={selected} ctx={ctx} id={id} readOnly />
        ) : (
          <ActualDetail key={selected} ctx={ctx} id={id} />
        ))}
    </section>
  );
}
