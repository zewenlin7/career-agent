"use client";
import Link from "next/link";
import type { ApplicationBinding } from "./application-binding";
import { ActualDetail } from "./actual-interview";
export { ActualPage, ActualDetail } from "./actual-interview";
import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import type { Actual, Context, Mock, Mode, Page, SessionRow } from "./contracts";
import { api, useAction, useRead, useRequestId } from "./client";
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
export function MockPage({ ctx }: { ctx: Context }) {
  const binding = useRead<ApplicationBinding>(`applications/${ctx.application.id}/context`);
  const [mode, setMode] = useState<Mode>("live"),
    [focus, setFocus] = useState("mixed"),
    [policy, setPolicy] = useState("quick"),
    [primary, setPrimary] = useState(3),
    [follow, setFollow] = useState(1),
    [id, setId] = useState("");
  const action = useAction();
  const requestId = useRequestId();
  return (
    <div className="space-y-6">
      <Panel title="开始模拟面试">
        <form
          className="max-w-[760px] space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              if (!binding.data?.profile_id || !binding.data.resume_revision_id) return;
              const result = await api<Mock>("mock-interviews", "POST", {
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
                  ...(policy === "custom" ? { primary_target: primary, followup_max: follow } : {}),
                },
                mode,
              });
              try {
                const body = { expected_revision: result.revision };
                await api<Mock>(`mock-interviews/${result.id}/generate`, "POST", {
                  ...body,
                  request_id: requestId({ session: result.id, ...body }),
                });
              } finally {
                setId(result.id);
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
            <Select label="练习重点" value={focus} onChange={(e) => setFocus(e.target.value)}>
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
            <Select label="问题数量模式" value={policy} onChange={(e) => setPolicy(e.target.value)}>
              <option value="quick">快速 · 3 主问题 / 最多 1 追问</option>
              <option value="standard">标准 · 5 主问题 / 最多 3 追问</option>
              <option value="long">完整 · 8 主问题 / 最多 5 追问</option>
              <option value="custom">自定义</option>
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
            <p className="text-sm">选定简历后开始练习，可随时回来继续。</p>
            <Button type="submit" variant="primary" disabled={!binding.data?.resume_revision_id}>
              开始模拟面试
            </Button>
          </fieldset>
        </form>
        <ErrorNotice code={action.error} />
      </Panel>
      {id && (
        <MockDetail
          key={id}
          id={id}
          ctx={ctx}
          onNew={() => {
            setId("");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      )}
    </div>
  );
}
export function MockDetail({ id, ctx, onNew }: { id: string; ctx: Context; onNew?: () => void }) {
  const read = useRead<Mock>(`mock-interviews/${id}`),
    [updated, setUpdated] = useState<Mock>(),
    [answer, setAnswer] = useState(""),
    [answerError, setAnswerError] = useState("");
  const question = useRef<HTMLLIElement>(null);
  const action = useAction(),
    requestId = useRequestId();
  const data = updated || read.data;
  useEffect(() => {
    question.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [data?.pending_question_id]);
  const refresh = () =>
    action.run(async () => setUpdated(await api<Mock>(`mock-interviews/${id}`)));
  const act = (type: "answers" | "generate" | "end") =>
    action.run(async () => {
      if (!data) return;
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
      const result = await api<Mock>(
        `mock-interviews/${id}/${saveAndEnd ? "answers" : type}`,
        "POST",
        {
          ...payload,
          request_id: requestId({ type, ...payload }),
        },
      );
      setUpdated(result);
      if (type === "answers") setAnswer("");
    });
  const invalid = data && data.context.job_id !== ctx.job.id;
  return (
    <Panel title="模拟面试">
      <ReadState loaded={!!data} error={invalid ? "context_revision_mismatch" : read.error} />
      {data && !invalid && (
        <>
          {data.status === "completed" && <p className="font-semibold">模拟面试已完成</p>}
          <p>
            主问题 {data.primary_question_count} / {data.policy.primary_target} · 追问{" "}
            {data.followup_count} / {data.policy.followup_max} · 总问题{" "}
            {data.interviewer_turn_count}
          </p>

          <Refs
            values={{ session_id: data.id, revision: data.revision, ...data.context.binding }}
          />
          {data.stop_reason && <ErrorNotice code={data.stop_reason} />}
          <ol className="space-y-5">
            {data.turns.map((t) => (
              <li
                key={t.id}
                ref={t.id === data.pending_question_id ? question : undefined}
                className={`border-l border-line pl-4 ${t.question.kind === "follow_up" ? "ml-5" : "pt-4"}`}
              >
                <p className="text-sm text-secondary">
                  {t.question_number} · {t.question.topic}
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
              <Field label="本题回答">
                <textarea
                  className={control}
                  required
                  maxLength={20000}
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  disabled={action.busy}
                />
              </Field>
              {answerError && (
                <p role="alert" className="text-sm text-error">
                  {answerError}
                </p>
              )}
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
          {data.generation_active && <p role="status">正在生成问题…</p>}
          {data.status !== "completed" && !data.generation_active && (
            <Button
              disabled={action.busy}
              onClick={() => {
                if (window.confirm("结束本场练习？当前填写的回答会一并保存。")) void act("end");
              }}
            >
              提前结束
            </Button>
          )}
          {data.stop_reason && (
            <Button disabled={action.busy} onClick={() => void refresh()}>
              重新加载
            </Button>
          )}
          {data.status === "completed" && onNew && (
            <Button onClick={onNew}>开始新的模拟面试</Button>
          )}
          {data.status === "completed" && (
            <Link
              href={`/applications/${ctx.application.id}/interview/history`}
              className="underline"
            >
              查看记录
            </Link>
          )}
        </>
      )}
      <ErrorNotice code={action.error} />
      {action.busy && <p role="status">请求处理中…</p>}
    </Panel>
  );
}
export function HistoryPage({ ctx }: { ctx: Context }) {
  const [type, setType] = useState<"mock" | "actual">("mock");
  return (
    <div className="space-y-6">
      <Panel title="历史面试">
        <div className="flex gap-3">
          <Button aria-pressed={type === "mock"} onClick={() => setType("mock")}>
            模拟面试
          </Button>
          <Button aria-pressed={type === "actual"} onClick={() => setType("actual")}>
            真实面试
          </Button>
        </div>
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
        {type === "mock" ? "模拟面试按创建时间倒序" : "真实面试按录入时间正序"}，每页 10 条。
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
              {"round_name" in r ? r.round_name : "模拟面试"} ·{" "}
              {new Date(r.created_at).toLocaleString("zh-CN")}
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
