"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { InterviewDate } from "./interview-date";
import { formatTime } from "@/lib/date-time";
import { Button } from "@/components/ui/button";
import { useConfirmation } from "../profile-area/confirmation";
import { api, useAction, useRead, useRequestId } from "./client";
import type { Actual, Context, Entry } from "./contracts";
import { projectEntries, moveEntry } from "./interview-entries";
import { control, ErrorNotice, Field, ReadState, Select } from "./ui";
const typeLabels = { technical: "技术", hr: "人力资源", mixed: "综合", other: "其他" };
export function actualLabel(
  row: { round_name?: string | null; round_number?: number | null; interview_type?: string | null },
  ctx: Context,
): string {
  const name = row.round_name?.trim();
  if (name && !/^\d+$/.test(name)) return name;
  const type = row.interview_type && typeLabels[row.interview_type as keyof typeof typeLabels];
  return [
    ctx.company.name,
    ctx.job.title,
    row.round_number ? `第${row.round_number}轮` : name ? `记录 ${name}` : "面试记录",
    type,
  ]
    .filter(Boolean)
    .join(" · ");
}
export function questionNumber(e: Entry): string {
  return `${e.main_question_number || ""}${e.followup_index ? `.${e.followup_index}` : ""}`;
}
export async function readActualHistory(path: string, signal: AbortSignal): Promise<Actual[]> {
  const items: Actual[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await api<Actual[]>(
      `${path}&limit=100&offset=${offset}`,
      "GET",
      undefined,
      signal,
    );
    items.push(...page);
    if (page.length < 100) return items;
  }
}
export function ActualPage({ ctx }: { ctx: Context }) {
  const router = useRouter(),
    search = useSearchParams();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const [mode, setMode] = useState<"new" | "edit" | "">(
    search.get("actual") || search.get("mode") === "edit" ? "edit" : "",
  );
  const [selected, setSelected] = useState(search.get("actual") || "");
  const records = useRead<Actual[]>(
    `interviews?application_id=${ctx.application.id}`,
    readActualHistory,
  );
  const drafts = useRead<Actual[]>(
    `interviews?application_id=${ctx.application.id}&status=draft`,
    readActualHistory,
  );
  const exact = useRead<Actual>(selected ? `interviews/${selected}` : null);
  const all = [...(records.data || []), ...(drafts.data || [])];
  const closeEditor = (destination: "edit" | "") => {
    setSelected("");
    setMode(destination);
    // Keep the destination recoverable without reopening the completed edit on refresh.
    router.replace(
      `/applications/${ctx.application.id}/interview/actual${destination ? "?mode=edit" : ""}`,
      { scroll: false },
    );
  };
  const finish = (row?: Actual) => {
    if (!mounted.current) return;
    if (row || search.get("return") === "history") {
      router.push(
        `/applications/${ctx.application.id}/interview/history?actual=${row?.id || selected}`,
      );
      return;
    }
    closeEditor("");
  };
  return (
    <section className="space-y-6">
      {!mode ? (
        <div className="flex gap-4">
          <Button onClick={() => setMode("new")}>新增记录</Button>
          <Button onClick={() => setMode("edit")}>编辑记录</Button>
        </div>
      ) : mode === "edit" && !selected ? (
        <>
          <button className="text-sm text-secondary underline" onClick={() => closeEditor("")}>
            ← 返回操作选择
          </button>
          <div className="max-w-xl">
            <Select
              labelClassName="text-base font-medium leading-relaxed"
              label="面试记录"
              value=""
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">选择需要编辑的面试记录</option>
              {all.map((row) => (
                <option key={row.id} value={row.id}>
                  {actualLabel(row, ctx)}
                </option>
              ))}
            </Select>
          </div>
          <ReadState
            loaded={!!records.data && !!drafts.data}
            error={records.error || drafts.error}
          />
        </>
      ) : mode === "new" && records.data && drafts.data ? (
        <ActualEditor
          ctx={ctx}
          nextRound={Math.max(0, ...all.map((r) => r.round_number || 0)) + 1}
          onSaved={finish}
          onCancel={() => finish()}
        />
      ) : exact.data ? (
        exact.data.application_id === ctx.application.id ? (
          <ActualEditor
            key={exact.data.id}
            ctx={ctx}
            initial={exact.data}
            onSaved={finish}
            onCancel={() => {
              if (search.get("return") === "history") finish();
              else closeEditor("edit");
            }}
            onBack={() => {
              if (search.get("return") === "history") finish();
              else closeEditor("");
            }}
          />
        ) : (
          <ErrorNotice code="context_revision_mismatch" />
        )
      ) : (
        <ReadState loaded={false} error={exact.error || records.error || drafts.error} />
      )}
    </section>
  );
}
export function ActualDetail({ id, ctx }: { id: string; ctx: Context }) {
  const read = useRead<Actual>(`interviews/${id}`);
  const data = read.data;
  return (
    <section className="min-w-0 space-y-5 text-base font-normal leading-relaxed [overflow-wrap:anywhere]">
      <ReadState loaded={!!data} error={read.error} />
      {data &&
        (data.application_id !== ctx.application.id ? (
          <ErrorNotice code="context_revision_mismatch" />
        ) : (
          <>
            <h2 className="text-xl font-semibold">{actualLabel(data, ctx)}</h2>
            {data.occurred_at && (
              <p className="text-sm text-secondary">{formatTime(data.occurred_at)}</p>
            )}
            <Transcript entries={data.entries} />
            {data.notes.length > 0 && (
              <section>
                <h3 className="text-lg font-semibold">笔记</h3>
                {data.notes.map((note, index) => (
                  <p className="whitespace-pre-wrap" key={index}>
                    {note.text}
                  </p>
                ))}
              </section>
            )}
            <div className="flex justify-end">
              <Link
                className="text-secondary underline"
                href={`/applications/${ctx.application.id}/interview/actual?actual=${id}&return=history`}
              >
                编辑记录
              </Link>
            </div>
          </>
        ))}
    </section>
  );
}
export function Transcript({ entries }: { entries: Entry[] }) {
  const shown = projectEntries(entries);
  return (
    <div className="space-y-5">
      {shown
        .filter((e) => e.kind === "primary")
        .map((parent) => (
          <section
            className="space-y-4 border-b border-line pb-5 last:border-0"
            key={parent.entry_id}
          >
            {[parent, ...shown.filter((e) => e.primary_entry_id === parent.entry_id)].map(
              (entry) => (
                <div key={entry.entry_id} className={entry.kind === "follow_up" ? "ml-5" : ""}>
                  <h3 className="font-semibold">
                    问题{questionNumber(entry)}　{entry.question}
                  </h3>
                  <p className="mt-2 whitespace-pre-wrap">{entry.answer || "未记录回答"}</p>
                </div>
              ),
            )}
          </section>
        ))}
    </div>
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
  nextRound = 1,
  onSaved,
  onCancel,
  onBack,
}: {
  ctx: Context;
  initial?: Actual;
  nextRound?: number;
  onSaved: (row: Actual) => void;
  onCancel: () => void;
  onBack?: () => void;
}) {
  const [round, setRound] = useState(
    initial ? String(initial.round_number ?? "") : String(nextRound),
  );
  const [type, setType] = useState(initial?.interview_type || "");
  const [dateTime, setDateTime] = useState(localDate(initial?.occurred_at).replace("T", " "));
  const [expanded, setExpanded] = useState<string[]>([]);
  const [dateError, setDateError] = useState("");
  const [entries, setEntries] = useState<Entry[]>(projectEntries(initial?.entries || []));
  const [notes, setNotes] = useState(initial?.notes.map((n) => n.text).join("\n") || "");
  const [validation, setValidation] = useState("");
  const requestId = useRequestId();
  const action = useAction();
  const { confirm, confirmation } = useConfirmation();
  const state = JSON.stringify({ round, type, dateTime, entries, notes });
  const [baseline] = useState(state);
  const dirty = state !== baseline;
  const groups = entries.reduce<Entry[][]>((all, entry) => {
    if (entry.kind === "primary" || !all.length) all.push([]);
    all[all.length - 1].push(entry);
    return all;
  }, []);
  const leave = async (destination = onCancel) => {
    if (!dirty || (await confirm("放弃尚未保存的修改？"))) destination();
  };
  const update = (entry: Entry) =>
    setEntries((all) => all.map((e) => (e.entry_id === entry.entry_id ? entry : e)));
  const add = (parent?: Entry) => {
    const entry: Entry = {
      entry_id: crypto.randomUUID(),
      order: entries.length + 1,
      kind: parent ? "follow_up" : "primary",
      primary_entry_id: parent?.entry_id || null,
      question: "",
      answer: null,
    };
    setEntries(projectEntries([...entries, entry]));
  };
  const save = () => {
    if (!entries.some((e) => e.kind === "primary") || entries.some((e) => !e.question.trim())) {
      setValidation("请填写有效的主问题及已添加的问题。");
      return;
    }
    if (
      (!initial && (!round || !type)) ||
      (!!initial?.round_number && !round) ||
      (!!initial?.interview_type && !type) ||
      (round && (!/^\d+$/.test(round) || +round < 1 || +round > 50))
    ) {
      setValidation("请填写 1–50 的轮次，并选择面试类型。");
      return;
    }
    setDateError("");
    let occurred: string | null = null;
    if (dateTime) {
      const [date, time] = dateTime.split(" ");
      const candidate = new Date(`${date}T${time}`);
      if (
        !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(dateTime) ||
        !/^\d{2}:\d{2}$/.test(time) ||
        !Number.isFinite(candidate.getTime()) ||
        localDate(candidate.toISOString()) !== `${date}T${time}`
      ) {
        setDateError("请填写有效时间 YYYY-MM-DD HH:mm，或留空。");
        return;
      }
      occurred =
        initial?.occurred_at && `${date}T${time}` === localDate(initial.occurred_at)
          ? initial.occurred_at
          : candidate.toISOString();
    }
    setValidation("");
    void action.run(async () => {
      const metadataChanged =
        !initial ||
        round !== String(initial.round_number ?? "") ||
        type !== (initial.interview_type || "");
      const name =
        metadataChanged && round && type
          ? `${ctx.company.name} · ${ctx.job.title} · 第${round}轮 · ${typeLabels[type as keyof typeof typeLabels]}`
          : initial?.round_name;
      const body = {
        round_name: name,
        round_number: round ? Number(round) : null,
        interview_type: type || null,
        occurred_at: occurred,
        status: "completed",
        entries: entries.map((e) => ({
          ...e,
          question: e.question.trim(),
          answer: e.answer?.trim() || null,
        })),
        notes_text: notes,
      };
      const saved = initial
        ? await api<Actual>(`interviews/${initial.id}`, "PATCH", {
            ...body,
            expected_revision: initial.content_revision,
          })
        : await api<Actual>("interviews", "POST", {
            ...body,
            application_id: ctx.application.id,
            request_id: requestId(body),
          });
      onSaved(saved);
    });
  };
  return (
    <>
      {initial && (
        <button
          className="text-sm text-secondary underline"
          disabled={action.busy}
          onClick={() => void leave(onBack || onCancel)}
        >
          ← 返回操作选择
        </button>
      )}
      <fieldset disabled={action.busy} className="min-w-0 space-y-6">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,0.6fr)_minmax(0,1fr)_minmax(0,2fr)]">
          <Field labelClassName="text-base font-medium leading-relaxed" label="轮次">
            <input
              className={control}
              inputMode="numeric"
              value={round}
              onChange={(e) => setRound(e.target.value)}
            />
          </Field>
          <Select
            labelClassName="text-base font-medium leading-relaxed"
            label="面试类型"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="">请选择</option>
            {Object.entries(typeLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </Select>
          <Field labelClassName="text-base font-medium leading-relaxed" label="面试时间">
            <InterviewDate
              value={dateTime}
              error={dateError}
              onChange={(value) => {
                setDateTime(value);
                setDateError("");
              }}
            />
          </Field>
        </div>
        {groups.map((group, groupIndex) => (
          <div
            key={group[0].entry_id}
            className={`min-w-0 space-y-6 ${groupIndex < groups.length - 1 ? "border-b border-line pb-5" : ""}`}
          >
            {group.map((entry) => (
              <section
                key={entry.entry_id}
                className={`space-y-3 ${entry.kind === "follow_up" ? "ml-5" : ""}`}
              >
                <Field
                  labelClassName="text-base font-medium leading-relaxed"
                  label={`问题${questionNumber(entry)}`}
                >
                  <textarea
                    className={control}
                    placeholder="输入问题"
                    value={entry.question}
                    maxLength={20000}
                    onChange={(e) => update({ ...entry, question: e.target.value })}
                  />
                </Field>
                <Field labelClassName="text-base font-medium leading-relaxed" label="回答">
                  <textarea
                    className={control}
                    placeholder="输入回答"
                    value={entry.answer || ""}
                    maxLength={20000}
                    onChange={(e) => update({ ...entry, answer: e.target.value })}
                  />
                </Field>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-3">
                    {entry.kind === "primary" && (
                      <Button onClick={() => add(entry)}>添加追问</Button>
                    )}
                    <button
                      type="button"
                      className="text-sm text-secondary underline"
                      aria-expanded={expanded.includes(entry.entry_id)}
                      onClick={() =>
                        setExpanded((all) =>
                          all.includes(entry.entry_id)
                            ? all.filter((id) => id !== entry.entry_id)
                            : [...all, entry.entry_id],
                        )
                      }
                    >
                      调整归属
                    </button>
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    {([-1, 1] as const).map((direction) => (
                      <button
                        key={direction}
                        type="button"
                        className="inline-flex size-8 shrink-0 items-center justify-center rounded-control border border-line bg-paper text-sm text-secondary enabled:hover:border-accent enabled:hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-50"
                        aria-label={direction === -1 ? "上移问题" : "下移问题"}
                        title={direction === -1 ? "上移问题" : "下移问题"}
                        disabled={
                          JSON.stringify(moveEntry(entries, entry.entry_id, direction)) ===
                          JSON.stringify(entries)
                        }
                        onClick={() => setEntries(moveEntry(entries, entry.entry_id, direction))}
                      >
                        {direction === -1 ? "↑" : "↓"}
                      </button>
                    ))}
                    <Button
                      variant="danger"
                      onClick={async () => {
                        const count = entries.filter(
                          (e) => e.primary_entry_id === entry.entry_id,
                        ).length;
                        if (
                          await confirm(
                            entry.kind === "follow_up"
                              ? "删除这道追问及其回答？"
                              : `删除这道问题、回答及其 ${count} 道追问？`,
                          )
                        )
                          setEntries(
                            projectEntries(
                              entries.filter(
                                (e) =>
                                  e.entry_id !== entry.entry_id &&
                                  e.primary_entry_id !== entry.entry_id,
                              ),
                            ),
                          );
                      }}
                    >
                      删除
                    </Button>
                  </div>
                </div>
                {expanded.includes(entry.entry_id) && (
                  <div>
                    <label className="flex shrink-0 items-center gap-2 whitespace-nowrap text-sm">
                      归属
                      <select
                        aria-label="归属"
                        className={control.replace("w-full", "w-auto")}
                        value={entry.primary_entry_id || ""}
                        onChange={(e) => {
                          if (entries.some((x) => x.primary_entry_id === entry.entry_id)) {
                            setValidation("请先调整本题追问的归属。");
                            return;
                          }
                          const parent = e.target.value || null;
                          setEntries(
                            projectEntries(
                              entries.map((x) =>
                                x.entry_id === entry.entry_id
                                  ? {
                                      ...x,
                                      kind: parent ? "follow_up" : "primary",
                                      primary_entry_id: parent,
                                      order: entries.length + 1,
                                    }
                                  : x,
                              ),
                            ),
                          );
                        }}
                      >
                        <option value="">主问题</option>
                        {entries
                          .filter((e) => e.kind === "primary" && e.entry_id !== entry.entry_id)
                          .map((p) => (
                            <option key={p.entry_id} value={p.entry_id}>
                              问题{questionNumber(p)}
                            </option>
                          ))}
                      </select>
                    </label>
                  </div>
                )}
              </section>
            ))}
          </div>
        ))}
        <Button onClick={() => add()}>添加问题</Button>
        <Field labelClassName="text-base font-medium leading-relaxed" label="笔记">
          <textarea
            className={control}
            placeholder="补充面试笔记"
            value={notes}
            maxLength={20000}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Field>
        {validation && (
          <p role="alert" className="text-sm text-error">
            {validation}
          </p>
        )}
        <ErrorNotice code={action.error} />
        <div className="flex justify-center gap-3">
          <Button variant="primary" onClick={save} disabled={!!initial && !dirty}>
            {action.busy ? "正在保存…" : "保存"}
          </Button>
          <Button onClick={() => void leave()}>取消</Button>
        </div>
      </fieldset>
      {confirmation}
    </>
  );
}
