"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type {
  Actual,
  Context,
  Debrief,
  DebriefRow,
  Knowledge,
  Mock,
  Mode,
  Page,
} from "./contracts";
import { api, ApiError, endpoint, useAction, useRead } from "./client";
import { consumeEvents, type BusinessEvent } from "./events";
import {
  BindingFields,
  control,
  ErrorNotice,
  Field,
  ModeSelect,
  Panel,
  Pages,
  ReadState,
  Refs,
  Select,
  Status,
} from "./ui";
import { InterviewList } from "./interviews";
import { Evaluation } from "./results";
function TargetFields({
  question,
  setQuestion,
  overall,
  setOverall,
  primary,
  setPrimary,
  entries,
}: {
  question: string;
  setQuestion: (s: string) => void;
  overall: boolean;
  setOverall: (v: boolean) => void;
  primary: string;
  setPrimary: (s: string) => void;
  entries: { id: string; question: string }[];
}) {
  return (
    <div className="space-y-3">
      <Select
        label="题组分析范围"
        value={question}
        onChange={(e) => {
          setQuestion(e.target.value);
          setPrimary("");
        }}
      >
        <option value="none">不分析题组</option>
        <option value="single">一个主问题及其全部追问</option>
        <option value="all">全部题组</option>
      </Select>
      {question === "single" && (
        <Select
          label="主问题题组"
          value={primary}
          required
          onChange={(e) => setPrimary(e.target.value)}
        >
          <option value="">请选择主问题</option>
          {entries.map((e) => (
            <option key={e.id} value={e.id}>
              {e.question}
            </option>
          ))}
        </Select>
      )}
      <label className="flex gap-2">
        <input type="checkbox" checked={overall} onChange={(e) => setOverall(e.target.checked)} />
        独立生成 Overall 综合复盘
      </label>
      {question === "none" && !overall && <p role="status">至少启用一个分析目标。</p>}
    </div>
  );
}
export function DebriefsPage({ ctx }: { ctx: Context }) {
  const [source, setSource] = useState<"actual" | "mock">("actual"),
    [sourceId, setSourceId] = useState(""),
    [mode, setMode] = useState<Mode>("fixture"),
    [question, setQuestion] = useState("all"),
    [overall, setOverall] = useState(true),
    [primary, setPrimary] = useState(""),
    [withContext, setWithContext] = useState(false),
    [profile, setProfile] = useState(""),
    [resume, setResume] = useState(""),
    [selected, setSelected] = useState<{ id: string; historical: boolean }>(),
    [offset, setOffset] = useState(0);
  const actual = useRead<Actual>(sourceId && source === "actual" ? `interviews/${sourceId}` : null),
    mock = useRead<Mock>(sourceId && source === "mock" ? `mock-interviews/${sourceId}` : null),
    history = useRead<Page<DebriefRow>>(
      `interview-debriefs?application_id=${ctx.application.id}&limit=10&offset=${offset}`,
    ),
    action = useAction();
  const entries =
    source === "actual"
      ? actual.data?.entries
          .filter((e) => e.kind === "primary")
          .map((e) => ({ id: e.entry_id, question: e.question }))
      : mock.data?.turns
          .filter((t) => t.question.kind === "primary")
          .map((t) => ({ id: t.id, question: t.question.question }));
  const revision = source === "actual" ? actual.data?.content_revision : mock.data?.revision;
  return (
    <div className="space-y-6">
      <Panel title="创建独立 Debrief">
        <Select
          label="面试来源"
          value={source}
          onChange={(e) => {
            setSource(e.target.value as "actual" | "mock");
            setSourceId("");
            setPrimary("");
          }}
        >
          <option value="actual">Actual Interview</option>
          <option value="mock">Mock Interview</option>
        </Select>
        <InterviewList
          key={source}
          ctx={ctx}
          type={source}
          onSelect={(id) => {
            setSourceId(id);
            setPrimary("");
          }}
        />
        {sourceId && (
          <p className="break-all">
            已选择来源 {sourceId} · revision {revision ?? "读取中"}
          </p>
        )}
        <ErrorNotice code={actual.error || mock.error} />
        {source === "mock" && mock.data && mock.data.status !== "completed" && (
          <p role="status">请先完成或提前结束该 Mock，再冻结来源进行复盘。</p>
        )}
        <form
          className="max-w-[760px] space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              if (!revision) throw new ApiError("source_required");
              const result = await api<Debrief>("interview-debriefs", "POST", {
                source_kind: source,
                interview_id: sourceId,
                expected_source_revision: revision,
                question_analysis: question,
                overall_analysis: overall,
                primary_entry_id: question === "single" ? primary : null,
                mode,
                ...(source === "actual" && withContext
                  ? {
                      context: {
                        profile_id: profile,
                        job_revision_id: ctx.job.job_revision_id,
                        resume_revision_id: resume,
                      },
                    }
                  : {}),
              });
              setSelected({ id: result.id, historical: true });
              history.reload();
            });
          }}
        >
          <fieldset disabled={action.busy} className="space-y-4">
            <TargetFields
              question={question}
              setQuestion={setQuestion}
              overall={overall}
              setOverall={setOverall}
              primary={primary}
              setPrimary={setPrimary}
              entries={entries || []}
            />
            {source === "actual" && (
              <>
                <label className="flex gap-2">
                  <input
                    type="checkbox"
                    checked={withContext}
                    onChange={(e) => setWithContext(e.target.checked)}
                  />
                  显式附加 Profile / JD / Resume context
                </label>
                {withContext && (
                  <BindingFields
                    ctx={ctx}
                    profile={profile}
                    setProfile={setProfile}
                    resume={resume}
                    setResume={setResume}
                  />
                )}
              </>
            )}
            <ModeSelect value={mode} onChange={setMode} />
            <p className="text-sm">
              创建时冻结来源；以后编辑实际面试不会修改这份 snapshot。Mock 使用 session 已冻结的
              context。
            </p>
            <Button
              type="submit"
              variant="primary"
              disabled={
                !revision ||
                (question === "none" && !overall) ||
                (source === "mock" &&
                  (mock.data?.status !== "completed" || mock.data?.generation_active))
              }
            >
              创建复盘 run
            </Button>
          </fieldset>
        </form>
        <ErrorNotice code={action.error} />
      </Panel>
      <Panel title="Debrief 历史与 selected generation">
        <ReadState
          loaded={!!history.data}
          error={history.error}
          empty={history.data?.items.length === 0}
        />
        <ul className="space-y-3">
          {history.data?.items.map((r) => (
            <li key={r.id}>
              <p>
                {r.source_kind} · {r.created_at} ·{" "}
                {r.is_selected ? "Selected generation" : "Historical generation"}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setSelected({ id: r.root_run_id, historical: false })}>
                  查看 selected result
                </Button>
                <Button onClick={() => setSelected({ id: r.generation_id, historical: true })}>
                  查看此历史 generation
                </Button>
              </div>
            </li>
          ))}
        </ul>
        {history.data && (
          <Pages offset={offset} setOffset={setOffset} more={history.data.has_more} />
        )}
      </Panel>
      {selected && (
        <DebriefDetail
          key={`${selected.id}:${selected.historical}`}
          id={selected.id}
          historical={selected.historical}
          onRegenerated={(id) => {
            setSelected({ id, historical: true });
            history.reload();
          }}
        />
      )}
    </div>
  );
}
function DebriefDetail({
  id,
  historical,
  onRegenerated,
}: {
  id: string;
  historical: boolean;
  onRegenerated: (id: string) => void;
}) {
  const read = useRead<Debrief>(`interview-debriefs/${id}?historical=${historical}`),
    [updated, setUpdated] = useState<Debrief>(),
    [events, setEvents] = useState<BusinessEvent[]>([]),
    [question, setQuestion] = useState("all"),
    [overall, setOverall] = useState(true),
    [primary, setPrimary] = useState("");
  const data = updated || read.data,
    action = useAction(),
    abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);
  const refresh = async () => {
    const exact = data?.id || id;
    const fresh = await api<Debrief>(`interview-debriefs/${exact}?historical=true`);
    setUpdated(fresh);
    const saved = await api<BusinessEvent[]>(`interview-debriefs/${exact}/events?after=0`);
    setEvents(saved);
  };
  const execute = () =>
    action.run(async () => {
      if (!data) return;
      abort.current = new AbortController();
      const response = await fetch(endpoint(`interview-debriefs/${data.id}/execute`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
        signal: abort.current.signal,
      });
      if (!response.ok) {
        const e = await response.json().catch(() => null);
        throw new ApiError(e?.error?.code || "request_failed");
      }
      if (!response.body) throw new ApiError("invalid_event_response");
      await consumeEvents(response.body, async (event) => {
        if (event.error_code) throw new ApiError(event.error_code);
        setEvents((old) =>
          old.some((e) => e.sequence === event.sequence) ? old : [...old, event],
        );
        if (
          event.event?.endsWith("_started") ||
          event.event?.endsWith("_retrying") ||
          event.event?.endsWith("_completed") ||
          event.event?.endsWith("_failed") ||
          event.event === "run_partial"
        )
          setUpdated(await api<Debrief>(`interview-debriefs/${data.id}?historical=true`));
      });
      await refresh();
    });
  return (
    <Panel title="复盘 generation">
      <ReadState loaded={!!data} error={read.error} />
      {data && (
        <>
          <Status value={data.status} />
          <Refs
            values={{
              generation_id: data.id,
              run_id: data.run_id,
              root_run_id: data.root_run_id,
              source_hash: data.source_hash,
              interview_id: data.snapshot.interview_id,
              content_revision: data.snapshot.content_revision,
            }}
          />
          <div className="flex flex-wrap gap-3">
            {data.status === "ready" && (
              <Button disabled={action.busy} variant="primary" onClick={() => void execute()}>
                执行复盘（POST SSE）
              </Button>
            )}
            <Button disabled={action.busy} onClick={() => void action.run(refresh)}>
              重新查询结果与持久化事件
            </Button>
            {action.busy && <Button onClick={() => abort.current?.abort()}>断开本次读取</Button>}
          </div>
          <p className="text-sm">
            事件表示已保存 artifact 的进度，不是 token
            流。断开后请查询已有结果；不假定后台继续执行，不自动重试执行。
          </p>
          <ol aria-label="复盘事件" className="text-sm text-secondary">
            {events.map((e, i) => (
              <li key={e.sequence ?? i}>
                {e.sequence} · {e.event} {e.group_index ? `· 第 ${e.group_index} 题` : ""}
                {e.reason_code ? ` · ${e.reason_code}` : ""}
              </li>
            ))}
          </ol>
          <div className="space-y-6">
            {[...data.artifacts]
              .sort(
                (a, b) =>
                  (a.kind === "overall" ? 1 : 0) - (b.kind === "overall" ? 1 : 0) ||
                  a.presentation.display_order - b.presentation.display_order,
              )
              .map((a) => (
                <article
                  key={a.id}
                  className="space-y-3 border-t border-line pt-4"
                  aria-label={
                    a.kind === "overall" ? "Overall 综合复盘" : `第 ${a.group_index} 题组`
                  }
                >
                  <h3 className="font-serif text-lg">
                    {a.kind === "overall" ? "Overall 综合复盘" : `第 ${a.group_index} 题组`}
                  </h3>
                  <Status value={a.status} />
                  {a.status === "retrying" && <p>该题分析暂时失败，系统正在自动重试。</p>}
                  {a.status === "failed" && (
                    <p>本次分析失败，可稍后对该题单独请求新 generation；不会生成替代评价。</p>
                  )}
                  {a.error_code && <ErrorNotice code={a.error_code} />}{" "}
                  {a.presentation.qa?.map((q, i) => (
                    <section key={i}>
                      <p className="text-sm text-secondary">{q.label}</p>
                      <p className="whitespace-pre-wrap">{q.question}</p>
                      <p className="whitespace-pre-wrap">
                        {q.answer_missing ? "未记录回答，不评价回答质量" : q.answer}
                      </p>
                    </section>
                  ))}
                  {a.presentation.evaluation && <Evaluation value={a.presentation.evaluation} />}
                </article>
              ))}
          </div>
          <details>
            <summary className="cursor-pointer">针对同一 frozen source 重新生成</summary>
            <form
              className="mt-4 space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                void action.run(async () => {
                  const result = await api<Debrief>(
                    `interview-debriefs/${data.id}/regenerate`,
                    "POST",
                    {
                      question_analysis: question,
                      overall_analysis: overall,
                      primary_entry_id: question === "single" ? primary : null,
                    },
                  );
                  onRegenerated(result.id);
                });
              }}
            >
              <TargetFields
                question={question}
                setQuestion={setQuestion}
                overall={overall}
                setOverall={setOverall}
                primary={primary}
                setPrimary={setPrimary}
                entries={data.snapshot.entries
                  .filter((e) => e.kind === "primary")
                  .map((e) => ({ id: e.entry_id, question: e.question }))}
              />
              <p className="text-sm">
                新 generation 保留旧结果与冻结来源；不等于负面反馈。创建后需单独执行。
              </p>
              <Button disabled={action.busy || (question === "none" && !overall)} type="submit">
                创建新 generation
              </Button>
            </form>
          </details>
        </>
      )}
      <ErrorNotice code={action.error} />
    </Panel>
  );
}
export function KnowledgePage({ ctx }: { ctx: Context }) {
  const [offset, setOffset] = useState(0),
    [title, setTitle] = useState(""),
    [content, setContent] = useState("");
  const rows = useRead<Page<Knowledge>>(
      `applications/${ctx.application.id}/knowledge-notes?limit=10&offset=${offset}`,
    ),
    action = useAction();
  return (
    <div className="space-y-6">
      <Panel title="创建 Application Knowledge Note">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              await api("knowledge-notes", "POST", {
                application_id: ctx.application.id,
                title,
                content,
              });
              setTitle("");
              setContent("");
              rows.reload();
            });
          }}
          className="max-w-[760px] space-y-4"
        >
          <Field label="笔记标题">
            <input
              className={control}
              required
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field label="笔记内容">
            <textarea
              className={`${control} min-h-40`}
              required
              maxLength={20000}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
          </Field>
          <Button disabled={action.busy} type="submit" variant="primary">
            保存 Knowledge Note
          </Button>
        </form>
        <ErrorNotice code={action.error} />
        <p className="text-sm">保存为当前 Application 的笔记，不自动成为 verified PersonalFact。</p>
      </Panel>
      <Panel title="当前 Application 的 Knowledge Notes">
        <ReadState loaded={!!rows.data} error={rows.error} empty={rows.data?.items.length === 0} />
        {rows.data?.items.map((n) => (
          <article key={n.id} className="space-y-2 border-b border-line pb-4">
            <h3 className="font-semibold">{n.title}</h3>
            <p className="whitespace-pre-wrap break-words">{n.content}</p>
            <Refs
              values={{
                id: n.id,
                application_id: n.application_id,
                interview_id: n.interview_id,
                created_at: n.created_at,
              }}
            />
          </article>
        ))}
        {rows.data && <Pages offset={offset} setOffset={setOffset} more={rows.data.has_more} />}
      </Panel>
    </div>
  );
}
