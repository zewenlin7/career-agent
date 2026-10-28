"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, useAction, useRead } from "./client";
import type { Actual, Context, Entry } from "./contracts";
import { control, ErrorNotice, Field, Panel, ReadState, Select } from "./ui";
const typeLabels = { technical: "技术", hr: "人力资源", mixed: "综合", other: "其他" };
export function questionNumber(e: Entry): string {
  return e.main_question_number
    ? `${e.main_question_number}${e.followup_index ? `.${e.followup_index}` : ""}`
    : "新问题";
}
export function ActualPage({ ctx }: { ctx: Context }) {
  const drafts = useRead<Actual[]>(
    `interviews?application_id=${ctx.application.id}&status=draft&limit=100`,
  );
  const [saved, setSaved] = useState<Actual>();
  const [fresh, setFresh] = useState(false);
  const draft = saved || (!fresh ? drafts.data?.at(-1) : undefined);
  return (
    <Panel title="记录真实面试">
      <ReadState loaded={!!drafts.data} error={drafts.error} />
      {drafts.data && (
        <ActualEditor key={draft?.id || "new"} ctx={ctx} initial={draft} onSaved={setSaved} />
      )}
      {saved?.status === "completed" && (
        <Button
          onClick={() => {
            setSaved(undefined);
            setFresh(true);
          }}
        >
          记录另一场面试
        </Button>
      )}
    </Panel>
  );
}
export function ActualDetail({ id, ctx }: { id: string; ctx: Context }) {
  const read = useRead<Actual>(`interviews/${id}`);
  const [editing, setEditing] = useState(false),
    [updated, setUpdated] = useState<Actual>();
  const data = updated || read.data;
  return (
    <Panel title="真实面试记录">
      <ReadState loaded={!!data} error={read.error} />
      {data && data.application_id !== ctx.application.id ? (
        <ErrorNotice code="context_revision_mismatch" />
      ) : (
        data && (
          <>
            <h3>
              {data.round_name} ·{" "}
              {data.occurred_at ? new Date(data.occurred_at).toLocaleString("zh-CN") : "时间未记录"}
            </h3>
            {editing ? (
              <ActualEditor
                ctx={ctx}
                initial={data}
                onSaved={(v) => {
                  setUpdated(v);
                  setEditing(false);
                }}
              />
            ) : (
              <>
                <ol className="space-y-5">
                  {data.entries.map((e) => (
                    <li
                      key={e.entry_id}
                      className={e.kind === "follow_up" ? "ml-5 border-l border-line pl-4" : ""}
                    >
                      <h4 className="font-semibold">
                        {questionNumber(e)}. {e.question}
                      </h4>
                      <p className="mt-2 whitespace-pre-wrap">{e.answer || "未记录回答"}</p>
                    </li>
                  ))}
                </ol>
                {data.notes.map((n, i) => (
                  <p className="whitespace-pre-wrap" key={i}>
                    {n.text}
                  </p>
                ))}
                <Button onClick={() => setEditing(true)}>编辑记录</Button>
              </>
            )}
          </>
        )
      )}
    </Panel>
  );
}
function localDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function ActualEditor({
  ctx,
  initial,
  onSaved,
}: {
  ctx: Context;
  initial?: Actual;
  onSaved: (v: Actual) => void;
}) {
  const [current, setCurrent] = useState(initial);
  const [round, setRound] = useState(initial?.round_number || 1);
  const [type, setType] = useState(initial?.interview_type || "technical");
  const [time, setTime] = useState(localDate(initial?.occurred_at));
  const [entries, setEntries] = useState<Entry[]>(initial?.entries || []);
  const [notes, setNotes] = useState(initial?.notes.map((n) => n.text).join("\n") || "");
  const [validation, setValidation] = useState("");
  const action = useAction();
  const update = (entry: Entry) =>
    setEntries((all) => all.map((e) => (e.entry_id === entry.entry_id ? entry : e)));
  const add = (parent?: Entry) => {
    const created: Entry = {
      entry_id: crypto.randomUUID(),
      order: entries.length + 1,
      kind: parent ? "follow_up" : "primary",
      primary_entry_id: parent?.entry_id || null,
      question: "",
      answer: null,
      main_question_number:
        parent?.main_question_number ||
        Math.max(0, ...entries.map((e) => e.main_question_number || 0)) + 1,
      followup_index: parent
        ? Math.max(
            0,
            ...entries
              .filter((e) => e.primary_entry_id === parent.entry_id)
              .map((e) => e.followup_index || 0),
          ) + 1
        : null,
    };
    const next = [...entries];
    if (parent) {
      const last = next.findLastIndex(
        (e) => e.entry_id === parent.entry_id || e.primary_entry_id === parent.entry_id,
      );
      next.splice(last + 1, 0, created);
    } else next.push(created);
    setEntries(next.map((e, i) => ({ ...e, order: i + 1 })));
  };
  const save = (status: "draft" | "completed") => {
    const meaningful = entries.filter((e) => e.question.trim() || e.answer?.trim());
    if (
      meaningful.some((e) => !e.question.trim()) ||
      (status === "completed" && !meaningful.some((e) => e.kind === "primary"))
    ) {
      setValidation("请填写问题后再保存。");
      return;
    }
    if (
      meaningful.some(
        (e) =>
          e.primary_entry_id &&
          !meaningful.some((p) => p.entry_id === e.primary_entry_id && p.kind === "primary"),
      )
    ) {
      setValidation("请先填写追问所属的主问题。");
      return;
    }
    setValidation("");
    void action.run(async () => {
      const base = {
        round_name: `第 ${round} 轮 · ${typeLabels[type as keyof typeof typeLabels]}`,
        round_number: round,
        interview_type: type,
        occurred_at: time ? new Date(time).toISOString() : null,
      };
      let row = current;
      if (!row) {
        row = await api<Actual>("interviews", "POST", {
          ...base,
          application_id: ctx.application.id,
          expected_revision: 0,
          status: "draft",
        });
        setCurrent(row);
      }
      const saved = await api<Actual>(`interviews/${row.id}`, "PATCH", {
        ...base,
        expected_revision: row.content_revision,
        status,
        entries: meaningful.map((e, i) => ({
          ...e,
          order: i + 1,
          question: e.question.trim(),
          answer: e.answer?.trim() || null,
        })),
        notes_text: notes.trim(),
      });
      setCurrent(saved);
      setEntries(saved.entries);
      onSaved(saved);
    });
  };
  return (
    <fieldset disabled={action.busy} className="min-w-0 space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Select label="轮次" value={round} onChange={(e) => setRound(Number(e.target.value))}>
          {Array.from({ length: 20 }, (_, i) => (
            <option key={i} value={i + 1}>
              第 {i + 1} 轮
            </option>
          ))}
        </Select>
        <Select label="面试类型" value={type} onChange={(e) => setType(e.target.value)}>
          {Object.entries(typeLabels).map(([v, label]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      <Field label="面试时间">
        <input
          className={control}
          type="datetime-local"
          value={time}
          onChange={(e) => setTime(e.target.value)}
        />
      </Field>
      {entries.map((entry) => (
        <section
          key={entry.entry_id}
          className={`space-y-3 border-l-2 border-line pl-4 ${entry.kind === "follow_up" ? "ml-4" : "pt-3"}`}
        >
          <h3 className="font-semibold">
            {questionNumber(entry)} {entry.kind === "primary" ? "问题" : "追问"}
          </h3>
          <Field label="问题">
            <textarea
              className={control}
              value={entry.question}
              maxLength={20000}
              onChange={(e) => update({ ...entry, question: e.target.value })}
            />
          </Field>
          <Field label="回答">
            <textarea
              className={control}
              value={entry.answer || ""}
              maxLength={20000}
              onChange={(e) => update({ ...entry, answer: e.target.value })}
            />
          </Field>
          <div className="flex flex-wrap gap-3">
            {entry.kind === "primary" && <Button onClick={() => add(entry)}>添加追问</Button>}
            <Button
              onClick={() => {
                if (window.confirm("删除这道问题及其追问？"))
                  setEntries(
                    entries.filter(
                      (e) => e.entry_id !== entry.entry_id && e.primary_entry_id !== entry.entry_id,
                    ),
                  );
              }}
            >
              删除问题
            </Button>
          </div>
          <details>
            <summary className="text-sm cursor-pointer">调整问题归属</summary>
            <Select
              label="归属"
              value={entry.primary_entry_id || ""}
              onChange={(e) => {
                const parent = entries.find((p) => p.entry_id === e.target.value);
                if (entries.some((x) => x.primary_entry_id === entry.entry_id)) {
                  setValidation("请先调整或删除本题的追问。");
                  return;
                }
                const changed = {
                  ...entry,
                  kind: parent ? ("follow_up" as const) : ("primary" as const),
                  primary_entry_id: parent?.entry_id || null,
                };
                const other = entries.filter((x) => x.entry_id !== entry.entry_id);
                if (parent)
                  other.splice(
                    other.findLastIndex(
                      (x) =>
                        x.entry_id === parent.entry_id || x.primary_entry_id === parent.entry_id,
                    ) + 1,
                    0,
                    changed,
                  );
                else other.push(changed);
                setEntries(other.map((x, i) => ({ ...x, order: i + 1 })));
              }}
            >
              <option value="">独立问题</option>
              {entries
                .filter((p) => p.kind === "primary" && p.entry_id !== entry.entry_id)
                .map((p) => (
                  <option key={p.entry_id} value={p.entry_id}>
                    {questionNumber(p)} {p.question.slice(0, 30)}
                  </option>
                ))}
            </Select>
          </details>
        </section>
      ))}
      <Button onClick={() => add()}>添加问题</Button>
      <Field label="笔记">
        <textarea
          className={control}
          maxLength={20000}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </Field>
      {validation && (
        <p role="alert" className="text-sm text-error">
          {validation}
        </p>
      )}
      <ErrorNotice code={action.error} />
      <div className="flex gap-3">
        {current?.status !== "completed" && <Button onClick={() => save("draft")}>保存草稿</Button>}
        <Button variant="primary" onClick={() => save("completed")}>
          {action.busy ? "正在保存…" : current?.status === "completed" ? "保存修改" : "完成记录"}
        </Button>
      </div>
      {current?.status === "draft" && <p className="text-sm text-secondary">草稿已保存。</p>}
      {current?.status === "completed" && (
        <p className="text-sm text-secondary">面试记录已保存。</p>
      )}
    </fieldset>
  );
}
