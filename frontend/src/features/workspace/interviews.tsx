"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Actual, Context, Entry, Mock, Mode, Page, SessionRow } from "./contracts";
import { api, useAction, useRead, useRequestId } from "./client";
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
export function MockPage({ ctx }: { ctx: Context }) {
  const [profile, setProfile] = useState(""),
    [resume, setResume] = useState(""),
    [mode, setMode] = useState<Mode>("fixture"),
    [focus, setFocus] = useState("mixed"),
    [policy, setPolicy] = useState("quick"),
    [primary, setPrimary] = useState(3),
    [follow, setFollow] = useState(1),
    [id, setId] = useState("");
  const action = useAction();
  return (
    <div className="space-y-6">
      <Panel title="创建新的 Mock Interview">
        <form
          className="max-w-[760px] space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const result = await api<Mock>("mock-interviews", "POST", {
                context: {
                  profile_id: profile,
                  job_revision_id: ctx.job.job_revision_id,
                  resume_revision_id: resume,
                },
                focus,
                policy: {
                  mode: policy,
                  ...(policy === "custom" ? { primary_target: primary, followup_max: follow } : {}),
                },
                mode,
              });
              setId(result.id);
            });
          }}
        >
          <fieldset disabled={action.busy} className="space-y-4">
            <BindingFields
              ctx={ctx}
              profile={profile}
              setProfile={setProfile}
              resume={resume}
              setResume={setResume}
            />
            <Select label="练习重点" value={focus} onChange={(e) => setFocus(e.target.value)}>
              {["mixed", "technical", "project", "behavioral", "company_specific"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </Select>
            <Select label="问题数量模式" value={policy} onChange={(e) => setPolicy(e.target.value)}>
              <option value="quick">Quick · 3 主问题 / 最多 1 追问</option>
              <option value="standard">Standard · 5 主问题 / 最多 3 追问</option>
              <option value="long">Long · 8 主问题 / 最多 5 追问</option>
              <option value="custom">Custom</option>
            </Select>
            {policy === "custom" && (
              <>
                <Field label="主问题数量">
                  <input
                    className={control}
                    type="number"
                    min={1}
                    max={8}
                    required
                    value={primary}
                    onChange={(e) => setPrimary(Number(e.target.value))}
                  />
                </Field>
                <Field label="追问上限">
                  <input
                    className={control}
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
            <ModeSelect value={mode} onChange={setMode} />
            <p className="text-sm">
              创建冻结所选 context，不自动生成 Interview Prep。创建后再明确生成第一题。
            </p>
            <Button type="submit" variant="primary">
              创建 Mock
            </Button>
          </fieldset>
        </form>
        <ErrorNotice code={action.error} />
      </Panel>
      {id && <MockDetail key={id} id={id} ctx={ctx} />}
    </div>
  );
}
export function MockDetail({ id, ctx }: { id: string; ctx: Context }) {
  const read = useRead<Mock>(`mock-interviews/${id}`),
    [updated, setUpdated] = useState<Mock>(),
    [answer, setAnswer] = useState("");
  const action = useAction(),
    requestId = useRequestId();
  const data = updated || read.data;
  const refresh = () =>
    action.run(async () => setUpdated(await api<Mock>(`mock-interviews/${id}`)));
  const act = (type: "answers" | "generate" | "end") =>
    action.run(async () => {
      if (!data) return;
      const payload = {
        expected_revision: data.revision,
        ...(type === "answers" ? { pending_question_id: data.pending_question_id, answer } : {}),
      };
      const result = await api<Mock>(`mock-interviews/${id}/${type}`, "POST", {
        ...payload,
        request_id: requestId({ type, ...payload }),
      });
      setUpdated(result);
      if (type === "answers") setAnswer("");
    });
  const invalid = data && data.context.job_id !== ctx.job.id;
  return (
    <Panel title="Mock session">
      <ReadState loaded={!!data} error={invalid ? "context_revision_mismatch" : read.error} />
      {data && !invalid && (
        <>
          <Status value={data.status} />
          <p className="text-sm">
            继续 / 重试生成沿用创建 session 时的执行模式，可能调用真实模型并产生费用。
          </p>
          <p>
            主问题 {data.primary_question_count} / {data.policy.primary_target} · 追问{" "}
            {data.followup_count} / {data.policy.followup_max} · 总问题{" "}
            {data.interviewer_turn_count}
          </p>
          {data.completion_type && <Status value={data.completion_type} />}
          <Refs
            values={{ session_id: data.id, revision: data.revision, ...data.context.binding }}
          />
          {data.stop_reason && <ErrorNotice code={data.stop_reason} />}
          <ol className="space-y-5">
            {data.turns.map((t) => (
              <li key={t.id} className="border-l border-line pl-4">
                <p className="text-sm text-secondary">
                  {t.question.kind === "follow_up" ? "追问" : "主问题"} · {t.question.topic}
                </p>
                <p className="whitespace-pre-wrap">{t.question.question}</p>
                <p className="mt-3 whitespace-pre-wrap">{t.answer ?? "尚未回答"}</p>
              </li>
            ))}
          </ol>
          {data.status === "waiting_answer" && !data.generation_active && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void act("answers");
              }}
              className="space-y-3"
            >
              <Field label="本题回答（接受后不可编辑）">
                <textarea
                  className={control}
                  required
                  maxLength={20000}
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  disabled={action.busy}
                />
              </Field>
              <p className="text-sm">
                接受答案后会尝试生成下一题。若生成失败，答案仍保留，请只重试生成。
              </p>
              <Button type="submit" disabled={action.busy} variant="primary">
                提交回答并继续
              </Button>
            </form>
          )}
          {data.status === "ready_to_generate" && !data.generation_active && (
            <Button disabled={action.busy} onClick={() => void act("generate")}>
              {data.stop_reason ? "重试生成问题" : "生成下一题"}
            </Button>
          )}
          {data.generation_active && <p role="status">生成进行中。请重新查询，不重复提交。</p>}
          {data.status !== "completed" && !data.generation_active && (
            <Button
              disabled={action.busy}
              onClick={() => {
                if (window.confirm("提前结束本场 Mock？已接受的回答会保留。")) void act("end");
              }}
            >
              提前结束
            </Button>
          )}
          <Button disabled={action.busy} onClick={() => void refresh()}>
            重新查询 session
          </Button>
        </>
      )}
      <ErrorNotice code={action.error} />
      {action.busy && <p role="status">请求处理中…</p>}
    </Panel>
  );
}
export function ActualPage({ ctx }: { ctx: Context }) {
  const [round, setRound] = useState(""),
    [occurred, setOccurred] = useState(""),
    [id, setId] = useState("");
  const action = useAction();
  return (
    <div className="space-y-6">
      <Panel title="记录新的真实面试">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const row = await api<Actual>("interviews", "POST", {
                application_id: ctx.application.id,
                expected_revision: 0,
                round_name: round,
                occurred_at: occurred ? new Date(occurred).toISOString() : null,
              });
              setId(row.id);
            });
          }}
          className="max-w-[760px] space-y-4"
        >
          <Field label="面试轮次（自由文本）">
            <input
              className={control}
              value={round}
              onChange={(e) => setRound(e.target.value)}
              maxLength={200}
              required
            />
          </Field>
          <Field label="面试时间（可选，使用浏览器本地时区）">
            <input
              className={control}
              type="datetime-local"
              value={occurred}
              onChange={(e) => setOccurred(e.target.value)}
            />
          </Field>
          <Button type="submit" variant="primary" disabled={action.busy}>
            创建真实面试记录
          </Button>
        </form>
        <ErrorNotice code={action.error} />
        <p className="text-sm">
          只保存实际轮次与问答，不生成 pass/fail outcome，不修改 Application 状态。
        </p>
      </Panel>
      {id && <ActualDetail key={id} id={id} ctx={ctx} />}
    </div>
  );
}
export function ActualDetail({ id, ctx }: { id: string; ctx: Context }) {
  const read = useRead<Actual>(`interviews/${id}`),
    [updated, setUpdated] = useState<Actual>();
  const action = useAction();
  const data = updated || read.data;
  const refresh = () => action.run(async () => setUpdated(await api<Actual>(`interviews/${id}`)));
  return (
    <Panel title="真实面试记录">
      <ReadState
        loaded={!!data}
        error={
          data && data.application_id !== ctx.application.id
            ? "context_revision_mismatch"
            : read.error
        }
      />
      {data && data.application_id === ctx.application.id && (
        <>
          <h3 className="font-semibold">{data.round_name}</h3>
          <p>
            {data.occurred_at ?? "面试时间未记录"} · content revision {data.content_revision}
          </p>
          <Refs values={{ interview_id: id, application_id: data.application_id }} />
          <ActualEditor key={data.id} data={data} onSaved={setUpdated} />
          <Button disabled={action.busy} onClick={() => void refresh()}>
            重新读取当前 revision
          </Button>
        </>
      )}
      <ErrorNotice code={action.error} />
    </Panel>
  );
}
function ActualEditor({ data, onSaved }: { data: Actual; onSaved: (r: Actual) => void }) {
  const [editing, setEditing] = useState(""),
    [kind, setKind] = useState("primary"),
    [parent, setParent] = useState(""),
    [question, setQuestion] = useState(""),
    [answer, setAnswer] = useState(""),
    [note, setNote] = useState(""),
    [round, setRound] = useState(data.round_name),
    [time, setTime] = useState("");
  const action = useAction();
  const mutate = (path: string, method: string, body: object) =>
    action.run(async () => {
      onSaved(
        await api<Actual>(path, method, { expected_revision: data.content_revision, ...body }),
      );
      if (path.endsWith("/notes")) setNote("");
      if (path.endsWith("/entries") || "entries" in body) {
        setEditing("");
        setQuestion("");
        setAnswer("");
      }
    });
  const saveEntry = () => {
    const existing = data.entries.find((e) => e.entry_id === editing);
    const entry: Entry = {
      entry_id: existing?.entry_id || crypto.randomUUID(),
      order: existing?.order || Math.max(0, ...data.entries.map((e) => e.order)) + 1,
      kind: existing?.kind || (kind as Entry["kind"]),
      primary_entry_id: existing?.primary_entry_id || (kind === "follow_up" ? parent : null),
      question,
      answer: answer || null,
    };
    if (existing)
      void mutate(`interviews/${data.id}`, "PATCH", {
        entries: data.entries.map((e) => (e.entry_id === editing ? entry : e)),
      });
    else void mutate(`interviews/${data.id}/entries`, "POST", { entry });
  };
  return (
    <fieldset disabled={action.busy} className="space-y-5">
      <ol className="space-y-4">
        {data.entries.map((e) => (
          <li key={e.entry_id} className="border-l border-line pl-4">
            <p className="text-sm">
              {e.order} · {e.kind === "primary" ? "主问题" : "追问"}
            </p>
            <p className="whitespace-pre-wrap">{e.question}</p>
            <p className="whitespace-pre-wrap text-secondary">{e.answer ?? "尚未记录回答"}</p>
            <Button
              disabled={action.busy}
              onClick={() => {
                setEditing(e.entry_id);
                setKind(e.kind);
                setParent(e.primary_entry_id || "");
                setQuestion(e.question);
                setAnswer(e.answer || "");
              }}
            >
              更正此问答
            </Button>
          </li>
        ))}
      </ol>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          saveEntry();
        }}
        className="max-w-[760px] space-y-3"
      >
        <fieldset disabled={action.busy} className="space-y-3">
          <h3 className="font-semibold">{editing ? "更正当前问答" : "追加问答"}</h3>
          {!editing && (
            <>
              <Select label="问题类型" value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="primary">主问题</option>
                <option value="follow_up">追问</option>
              </Select>
              {kind === "follow_up" && (
                <Select
                  label="所属主问题"
                  required
                  value={parent}
                  onChange={(e) => setParent(e.target.value)}
                >
                  <option value="">请选择同一场面试的主问题</option>
                  {data.entries
                    .filter((e) => e.kind === "primary")
                    .map((e) => (
                      <option key={e.entry_id} value={e.entry_id}>
                        {e.order} · {e.question}
                      </option>
                    ))}
                </Select>
              )}
            </>
          )}
          <Field label="问题">
            <textarea
              required
              maxLength={20000}
              className={control}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
          </Field>
          <Field label="回答（可留空）">
            <textarea
              maxLength={20000}
              className={control}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
            />
          </Field>
          <Button type="submit">{editing ? "保存更正" : "追加问答"}</Button>
          {editing && (
            <Button
              onClick={() => {
                setEditing("");
                setQuestion("");
                setAnswer("");
                setKind("primary");
                setParent("");
              }}
            >
              取消更正
            </Button>
          )}
        </fieldset>
      </form>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void mutate(`interviews/${data.id}/notes`, "POST", { text: note });
        }}
        className="space-y-3"
      >
        <Field label="追加自由笔记（不会自动解析成问答）">
          <textarea
            className={control}
            required
            maxLength={20000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </Field>
        <Button type="submit" disabled={action.busy}>
          追加笔记
        </Button>
      </form>
      <ul>
        {data.notes.map((n, i) => (
          <li key={i} className="whitespace-pre-wrap">
            <p>{n.text}</p>
            <span className="block text-sm text-secondary">{n.recorded_at}</span>
          </li>
        ))}
      </ul>
      <details>
        <summary className="cursor-pointer">更正轮次 / 时间</summary>
        <form
          className="mt-3 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void mutate(`interviews/${data.id}`, "PATCH", {
              round_name: round,
              ...(time ? { occurred_at: new Date(time).toISOString() } : {}),
            });
          }}
        >
          <Field label="轮次名称">
            <input
              className={control}
              required
              maxLength={200}
              value={round}
              onChange={(e) => setRound(e.target.value)}
            />
          </Field>
          <Field label="更正时间（留空保留原值）">
            <input
              className={control}
              type="datetime-local"
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={action.busy}>
            保存轮次 / 时间
          </Button>
        </form>
      </details>
      <ErrorNotice code={action.error} />
    </fieldset>
  );
}
export function HistoryPage({ ctx }: { ctx: Context }) {
  const [type, setType] = useState<"mock" | "actual">("mock");
  return (
    <div className="space-y-6">
      <Panel title="Previous Interviews">
        <div className="flex gap-3">
          <Button aria-pressed={type === "mock"} onClick={() => setType("mock")}>
            Mock Interviews
          </Button>
          <Button aria-pressed={type === "actual"} onClick={() => setType("actual")}>
            Actual Interviews
          </Button>
        </div>
        <p className="text-sm">两套独立查询和分页，不合并成统一时间线。</p>
        <InterviewList key={type} ctx={ctx} type={type} />
      </Panel>
    </div>
  );
}
export function InterviewList({
  ctx,
  type,
  onSelect,
}: {
  ctx: Context;
  type: "mock" | "actual";
  onSelect?: (id: string) => void;
}) {
  const [offset, setOffset] = useState(0),
    [selected, setSelected] = useState("");
  const mocks = useRead<Page<SessionRow>>(
      type === "mock"
        ? `mock-interviews?application_id=${ctx.application.id}&limit=10&offset=${offset}`
        : null,
    ),
    actuals = useRead<Actual[]>(
      type === "actual"
        ? `interviews?application_id=${ctx.application.id}&limit=10&offset=${offset}`
        : null,
    );
  const rows = type === "mock" ? mocks.data?.items : actuals.data;
  return (
    <div className="space-y-4">
      <p className="text-sm">
        {type === "mock" ? "Mock 按创建时间倒序" : "Actual 按录入时间正序"}，每页 10 条。
      </p>
      <ReadState loaded={!!rows} error={mocks.error || actuals.error} empty={rows?.length === 0} />
      <ul>
        {rows?.map((r) => (
          <li key={r.id}>
            <Button
              onClick={() => {
                setSelected(r.id);
                onSelect?.(r.id);
              }}
            >
              {"round_name" in r ? r.round_name : "Mock"} · {r.created_at} · {r.id}
            </Button>
          </li>
        ))}
      </ul>
      {rows && (
        <Pages
          offset={offset}
          setOffset={setOffset}
          more={type === "mock" ? !!mocks.data?.has_more : rows.length === 10}
        />
      )}{" "}
      {!onSelect &&
        selected &&
        (type === "mock" ? (
          <MockDetail key={selected} ctx={ctx} id={selected} />
        ) : (
          <ActualDetail key={selected} ctx={ctx} id={selected} />
        ))}
    </div>
  );
}
