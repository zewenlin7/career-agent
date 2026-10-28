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
  control,
  ErrorNotice,
  Field,
  ModeSelect,
  Panel,
  Pages,
  ReadState,
  Refs,
  Select,
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
        label="分析范围"
        value={question}
        onChange={(e) => {
          setQuestion(e.target.value);
          if (e.target.value === "none") setOverall(true);
          setPrimary("");
        }}
      >
        <option value="none">仅整体总结</option>
        <option value="single">指定题组</option>
        <option value="all">整场面试</option>
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
        包含综合复盘
      </label>
      {question === "none" && !overall && <p role="status">至少启用一个分析目标。</p>}
    </div>
  );
}
export function DebriefsPage({ ctx }: { ctx: Context }) {
  const [source, setSource] = useState<"actual" | "mock">("actual"),
    [sourceId, setSourceId] = useState(""),
    [mode, setMode] = useState<Mode>("live"),
    [question, setQuestion] = useState("all"),
    [overall, setOverall] = useState(true),
    [primary, setPrimary] = useState(""),
    [selected, setSelected] = useState<{ id: string; historical: boolean; start?: boolean }>(),
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
      <Panel title="面试复盘">
        <ReadState loaded={!!history.data} error={history.error} />
        {!!history.data?.items.length && (
          <Select
            label="复盘版本"
            value={selected?.id || ""}
            onChange={(event) => {
              if (event.target.value) setSelected({ id: event.target.value, historical: true });
              else setSelected(undefined);
            }}
          >
            <option value="">新建复盘</option>
            {history.data.items
              .filter((row) => ["completed", "partial"].includes(row.status))
              .map((row) => (
                <option key={row.generation_id} value={row.generation_id}>
                  {row.source_kind === "actual" ? "真实面试复盘" : "模拟面试复盘"} ·{" "}
                  {new Date(row.created_at).toLocaleString("zh-CN")}
                  {row.is_selected ? " · 当前结果" : ""}
                </option>
              ))}
          </Select>
        )}
        {history.data && (offset > 0 || history.data.has_more) && (
          <Pages offset={offset} setOffset={setOffset} more={history.data.has_more} />
        )}

        <Select
          label="面试来源"
          value={source}
          onChange={(e) => {
            setSource(e.target.value as "actual" | "mock");
            setSourceId("");
            setPrimary("");
          }}
        >
          <option value="actual">真实面试</option>
          <option value="mock">模拟面试</option>
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
          <p className="break-all">{revision ? "已选择面试记录" : "正在读取面试记录"}</p>
        )}
        <ErrorNotice code={actual.error || mock.error} />
        {source === "mock" && mock.data && mock.data.status !== "completed" && (
          <p role="status">请先结束模拟面试，再开始复盘。</p>
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
              });
              setSelected({ id: result.id, historical: true, start: true });
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
            <ModeSelect value={mode} onChange={setMode} />
            <p className="text-sm">请选择本次要复盘的面试记录。</p>
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
              开始复盘
            </Button>
          </fieldset>
        </form>
        <ErrorNotice code={action.error} />
      </Panel>
      {selected && (
        <DebriefDetail
          key={`${selected.id}:${selected.historical}`}
          autoStart={selected.start}
          id={selected.id}
          historical={selected.historical}
          onRegenerated={(id) => {
            setSelected({ id, historical: true, start: true });
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
  autoStart = false,
}: {
  id: string;
  historical: boolean;
  autoStart?: boolean;
  onRegenerated: (id: string) => void;
}) {
  const read = useRead<Debrief>(`interview-debriefs/${id}?historical=${historical}`),
    [updated, setUpdated] = useState<Debrief>(),
    [, setEvents] = useState<BusinessEvent[]>([]),
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
  const started = useRef(false);
  useEffect(() => {
    if (autoStart && data?.status === "ready" && !started.current) {
      started.current = true;
      void execute();
    }
  });
  return (
    <Panel title="复盘结果">
      <ReadState loaded={!!data} error={read.error} />
      {data && (
        <>
          {action.busy && <p role="status">正在生成复盘…</p>}
          <section className="space-y-4" aria-label="面试问答">
            <h3 className="font-serif text-lg">面试问答</h3>
            {(data.transcript || data.snapshot.entries).map((entry) => (
              <div
                key={entry.entry_id}
                className={entry.kind === "follow_up" ? "ml-5 border-l border-line pl-4" : ""}
              >
                <p className="font-semibold">
                  {"question_number" in entry ? String(entry.question_number) : ""} {entry.question}
                </p>
                <p className="mt-2 whitespace-pre-wrap">{entry.answer || "未记录回答"}</p>
              </div>
            ))}
          </section>
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
                继续复盘
              </Button>
            )}
            {!action.busy && data.status === "running" && (
              <Button onClick={() => void action.run(refresh)}>重新加载</Button>
            )}
          </div>
          {action.busy && <p className="text-sm">正在逐题分析，请稍候。</p>}
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
                  aria-label={a.kind === "overall" ? "综合复盘" : `第 ${a.group_index} 题组`}
                >
                  <h3 className="font-serif text-lg">
                    {a.kind === "overall" ? "综合复盘" : `第 ${a.group_index} 题组`}
                  </h3>
                  {a.status === "retrying" && <p>该题分析暂时失败，系统正在自动重试。</p>}
                  {a.status === "failed" && <p>本次分析失败，可稍后对该题重新分析。</p>}
                  {a.error_code && <ErrorNotice code={a.error_code} />}{" "}
                  {a.presentation.evaluation && <Evaluation value={a.presentation.evaluation} />}
                </article>
              ))}
          </div>
          <details>
            <summary className="cursor-pointer">根据同一面试记录重新生成</summary>
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
              <p className="text-sm">重新分析会保留已有结果与原面试记录。</p>
              <Button disabled={action.busy || (question === "none" && !overall)} type="submit">
                重新生成复盘
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
    [content, setContent] = useState(""),
    [editing, setEditing] = useState<Knowledge>();
  const rows = useRead<Page<Knowledge>>(
      `applications/${ctx.application.id}/knowledge-notes?limit=10&offset=${offset}`,
    ),
    action = useAction();
  return (
    <div className="space-y-6">
      <Panel title="求职笔记">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              if (!title.trim() || !content.trim()) throw new ApiError("note_content_required");
              await api(
                editing ? `knowledge-notes/${editing.id}` : "knowledge-notes",
                editing ? "PATCH" : "POST",
                {
                  ...(editing
                    ? { expected_revision: editing.revision }
                    : { application_id: ctx.application.id }),
                  title: title.trim(),
                  content: content.trim(),
                },
              );
              setEditing(undefined);
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
            保存笔记
          </Button>
        </form>
        <ErrorNotice code={action.error} />
        {editing && (
          <Button
            onClick={() => {
              setEditing(undefined);
              setTitle("");
              setContent("");
            }}
          >
            取消编辑
          </Button>
        )}
      </Panel>
      <Panel title="已保存笔记">
        <ReadState loaded={!!rows.data} error={rows.error} empty={rows.data?.items.length === 0} />
        {rows.data?.items.map((n) => (
          <article key={n.id} className="space-y-2 border-b border-line pb-4">
            <h3 className="font-semibold">{n.title}</h3>
            <p className="text-xs text-secondary">
              {new Date(n.created_at).toLocaleString("zh-CN")}
            </p>
            <div className="flex gap-3">
              <Button
                onClick={() => {
                  setEditing(n);
                  setTitle(n.title);
                  setContent(n.content);
                }}
              >
                编辑
              </Button>
              <Button
                disabled={action.busy}
                onClick={() => {
                  if (window.confirm("删除这条笔记？"))
                    void action.run(async () => {
                      await api(
                        `knowledge-notes/${n.id}?expected_revision=${n.revision}`,
                        "DELETE",
                      );
                      rows.reload();
                    });
                }}
              >
                删除
              </Button>
            </div>
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
