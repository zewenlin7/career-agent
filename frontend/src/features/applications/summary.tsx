"use client";
import Link from "next/link";
import { SummaryGrid } from "./summary-grid";
import { Badge } from "@/components/ui/badge";
import { EntryMenu } from "./entry-menu";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";
import { DateTime } from "@/components/product/read-state";
import { api, useAction, useRead, useRequestId } from "../workspace/client";
import { control, ErrorNotice } from "../workspace/ui";
import { BindingEditor, type ApplicationBinding } from "../workspace/application-binding";
import { applicationStatuses, statusLabels, type ApplicationStatus } from "./contracts";
import { useConfirmation } from "../profile-area/confirmation";

type Reference = { label: string; href: string; created_at: string | null; stale?: boolean };
type Entry = {
  id: string;
  kind: "created" | "status" | "note";
  text: string | null;
  created_at: string;
  revision: number;
  status: ApplicationStatus | null;
  editable: boolean;
};
export type SummaryData = {
  revision: number;
  status: ApplicationStatus;
  jd: { text: string; saved_at: string | null; id: string };
  resume: Reference | null;
  preparation: (Reference & { kind: string; available: boolean; stale: boolean })[];
  submission: { resume: Reference; greeting: Reference | null; created_at: string } | null;
  mock: (Reference & { status: string; completion_type: string | null }) | null;
  actual: { count: number; latest: Reference | null };
  debrief: { count: number; latest: Reference | null };
  notes: Entry[];
  records: Entry[];
};
function Card({
  title,
  children,
  action,
  fixed = false,
  editing = false,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  fixed?: boolean;
  editing?: boolean;
}) {
  return (
    <Surface
      aria-label={title}
      data-summary-editing={editing}
      data-summary-fixed={fixed}
      className={`flex min-w-0 flex-col ${fixed ? "h-[430px]" : ""} summary-card`}
    >
      <h2 className="summary-title mb-4 shrink-0">{title}</h2>
      <div
        className={`min-h-0 flex-1 ${fixed ? "overflow-y-auto overscroll-contain p-1.5 -m-1.5" : ""}`}
      >
        <div data-summary-content className="space-y-3">
          {children}
        </div>
      </div>
      {action && (
        <div data-summary-action className="mt-4 flex shrink-0 justify-end gap-3">
          {action}
        </div>
      )}
    </Surface>
  );
}
function ReferenceView({
  value,
  prefix,
  status,
}: {
  value: Reference | null;
  prefix?: string;
  status?: string;
}) {
  if (!value) return <p className="text-secondary">尚无记录</p>;
  return (
    <div>
      {prefix && <p className="mb-2 text-sm text-secondary">{prefix}</p>}
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <Link
          className="min-w-0 max-w-full break-words text-accent-ink underline underline-offset-4"
          href={value.href}
          prefetch={false}
          scroll={!/[?&](research|result|artifact|session|debrief)=/.test(value.href)}
        >
          {value.label}
        </Link>
        {status && <Badge className="shrink-0 text-sm! font-normal">{status}</Badge>}
      </div>
      {value.stale && <p className="mt-1 text-sm text-secondary">基于修改前的职位描述</p>}
      {value.created_at && (
        <p className="mt-2 text-sm text-secondary">
          <DateTime value={value.created_at} />
        </p>
      )}
    </div>
  );
}
export function ApplicationSummary({ id }: { id: string }) {
  const router = useRouter();
  const [read, setRead] = useState<{ id: string; data?: SummaryData; error?: string }>({ id });
  const request = useRef(0);
  const reload = useCallback(async () => {
    const sequence = ++request.current;
    try {
      const data = await api<SummaryData>(`applications/${id}/summary`);
      if (sequence === request.current) setRead({ id, data });
    } catch {
      if (sequence === request.current) setRead({ id, error: "unavailable" });
    }
  }, [id]);
  useEffect(() => {
    let active = true;
    const sequence = ++request.current;
    const abort = new AbortController();
    api<SummaryData>(`applications/${id}/summary`, "GET", undefined, abort.signal)
      .then((data) => {
        if (active && sequence === request.current) setRead({ id, data });
      })
      .catch(() => {
        if (active && sequence === request.current) setRead({ id, error: "unavailable" });
      });
    const refresh = () => {
      void reload();
    };
    window.addEventListener("pageshow", refresh);
    return () => {
      active = false;
      abort.abort();
      window.removeEventListener("pageshow", refresh);
    };
  }, [id, reload]);
  const data = read.id === id ? read.data : undefined;
  const refresh = async () => {
    // Keep the saving editor busy until the shared CAS baseline has been reloaded.
    await reload();
    router.refresh();
  };
  if (!data)
    return (
      <p role="status">{read.error ? "暂时无法读取申请概览，请重新打开页面。" : "正在读取…"}</p>
    );
  return (
    <SummaryGrid>
      <Card
        title="职位描述"
        action={
          <Link
            className="text-sm text-accent-ink underline"
            href={`/applications/${id}/research-fit/description#job-description`}
          >
            查看完整职位描述
          </Link>
        }
      >
        {data.jd.saved_at && (
          <p className="text-sm text-secondary">
            <DateTime value={data.jd.saved_at} />
          </p>
        )}
        <p className="line-clamp-6 whitespace-pre-wrap break-words leading-relaxed">
          {data.jd.text}
        </p>
      </Card>
      <Card title="最新准备结果">
        <ul className="space-y-3">
          {data.preparation.map((item) => (
            <li
              key={item.kind}
              className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1"
            >
              <div>
                <Link
                  href={item.href}
                  prefetch={false}
                  scroll={false}
                  className="text-accent-ink underline underline-offset-4"
                >
                  {item.label}
                </Link>
                {item.stale && <p className="text-xs text-secondary">基于修改前的职位描述</p>}
              </div>
              <span className="text-sm text-secondary">
                {item.available ? (
                  item.created_at ? (
                    <DateTime value={item.created_at} />
                  ) : (
                    ""
                  )
                ) : (
                  "尚未生成"
                )}
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <ResumeCard id={id} value={data.resume} onSaved={refresh} />
      <StatusCard id={id} data={data} onSaved={refresh} />
      <Card title="最新投递材料">
        {data.submission ? (
          <>
            <ReferenceView value={{ ...data.submission.resume, created_at: null }} />
            {data.submission.greeting && <ReferenceView value={data.submission.greeting} />}
            <p className="text-sm text-secondary">
              记录于 <DateTime value={data.submission.created_at} />
            </p>
          </>
        ) : (
          <p className="text-secondary">尚无记录</p>
        )}
      </Card>
      <Card title="最新模拟面试">
        <ReferenceView
          value={data.mock}
          status={
            data.mock
              ? data.mock.status === "completed"
                ? data.mock.completion_type === "user_ended_early"
                  ? "提前结束"
                  : "已完成"
                : "进行中"
              : undefined
          }
        />
      </Card>
      <Card title="真实面试记录">
        <ReferenceView
          value={data.actual.latest}
          prefix={`共 ${data.actual.count} 条 · 最新录入`}
        />
      </Card>
      <Card title="面试复盘">
        <ReferenceView
          value={data.debrief.latest}
          prefix={`共 ${data.debrief.count} 份 · 最新复盘`}
        />
      </Card>
      <EntryCard id={id} data={data} notes onSaved={refresh} />
      <EntryCard id={id} data={data} onSaved={refresh} />
    </SummaryGrid>
  );
}
function ResumeCard({
  id,
  value,
  onSaved,
}: {
  id: string;
  value: Reference | null;
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const binding = useRead<ApplicationBinding>(editing ? `applications/${id}/context` : null);
  return (
    <Card
      title="当前使用简历"
      editing={editing}
      action={!editing && <Button onClick={() => setEditing(true)}>更换</Button>}
    >
      {editing ? (
        binding.data ? (
          <BindingEditor
            binding={binding.data}
            onDone={async () => {
              await onSaved();
              setEditing(false);
            }}
          />
        ) : (
          <p>正在读取…</p>
        )
      ) : value ? (
        <ReferenceView value={{ ...value, created_at: null }} />
      ) : (
        <p>尚未选择</p>
      )}
      <ErrorNotice code={binding.error} />
    </Card>
  );
}
function StatusCard({
  id,
  data,
  onSaved,
}: {
  id: string;
  data: SummaryData;
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false),
    [target, setTarget] = useState(data.status),
    [reason, setReason] = useState(""),
    [baseline, setBaseline] = useState(data.revision);
  const action = useAction();
  return (
    <Card
      title="申请状态"
      editing={editing}
      action={
        !editing && (
          <Button
            onClick={() => {
              setBaseline(data.revision);
              setTarget(data.status);
              setReason("");
              setEditing(true);
            }}
          >
            更改
          </Button>
        )
      }
    >
      {editing ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              await api(`applications/${id}`, "PATCH", {
                expected_revision: baseline,
                status: target,
                reason: reason.trim() || null,
              });
              await onSaved();
              setEditing(false);
            });
          }}
        >
          <label className="grid gap-2 text-sm font-semibold">
            状态
            <select
              aria-label="状态"
              className={`${control} font-normal`}
              value={target}
              onChange={(e) => setTarget(e.target.value as ApplicationStatus)}
            >
              {applicationStatuses.map((s) => (
                <option key={s} value={s}>
                  {statusLabels[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-semibold">
            备注（可选）
            <textarea
              className={`${control} font-normal`}
              value={reason}
              maxLength={20000}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <ErrorNotice code={action.error} />
          <div className="flex justify-end gap-3">
            <Button type="submit" disabled={action.busy || target === data.status}>
              保存
            </Button>
            <Button disabled={action.busy} onClick={() => setEditing(false)}>
              取消
            </Button>
          </div>
        </form>
      ) : (
        <p className="summary-body">{statusLabels[data.status]}</p>
      )}
    </Card>
  );
}
function EntryCard({
  id,
  data,
  notes = false,
  onSaved,
}: {
  id: string;
  data: SummaryData;
  notes?: boolean;
  onSaved: () => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const entries = notes ? data.notes : data.records;
  return (
    <Card
      fixed
      title={notes ? "申请笔记" : "申请记录"}
      action={
        notes && (
          <button
            aria-label="添加申请笔记"
            className="mx-auto px-5 text-2xl text-secondary hover:text-primary"
            onClick={() => setAdding(true)}
          >
            ＋
          </button>
        )
      }
    >
      {adding && (
        <EntryEditor
          id={id}
          revision={data.revision}
          onSaved={async () => {
            await onSaved();
            setAdding(false);
          }}
          onCancel={() => setAdding(false)}
        />
      )}
      {!entries.length && !adding && (
        <p className="text-secondary">{notes ? "暂无笔记" : "尚无记录"}</p>
      )}
      <ol className="divide-y divide-line">
        {entries.map((entry) => (
          <EntryRow
            key={entry.id}
            id={id}
            entry={entry}
            revision={data.revision}
            onSaved={onSaved}
          />
        ))}
      </ol>
    </Card>
  );
}
function EntryRow({
  id,
  entry,
  revision,
  onSaved,
}: {
  id: string;
  entry: Entry;
  revision: number;
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false),
    confirm = useConfirmation(),
    action = useAction(),
    requestId = useRequestId();
  const label =
    entry.kind === "created"
      ? "创建申请"
      : entry.kind === "status"
        ? `状态变更 · ${entry.status ? statusLabels[entry.status] : ""}`
        : "";
  return (
    <li className="group relative px-2 py-4">
      {label && <p className="pr-10">{label}</p>}
      {editing ? (
        <EntryEditor
          id={id}
          entry={entry}
          revision={revision}
          onCancel={() => setEditing(false)}
          onSaved={async () => {
            await onSaved();
            setEditing(false);
          }}
        />
      ) : (
        <>
          <p
            className="whitespace-pre-wrap break-words pr-8"
            onDoubleClick={() => {
              if (entry.editable) setEditing(true);
            }}
          >
            {entry.text}
          </p>
          {entry.editable && (
            <EntryMenu label="管理记录">
              <button
                role="menuitem"
                className="w-full p-2 text-sm"
                onClick={() => setEditing(true)}
              >
                编辑
              </button>
              <button
                role="menuitem"
                className="w-full p-2 text-sm text-error"
                disabled={action.busy}
                onClick={async () => {
                  if (
                    !(await confirm.confirm(
                      entry.kind === "status"
                        ? "移除这条记录？不更改当前申请状态。"
                        : "删除这条笔记？",
                    ))
                  )
                    return;
                  void action.run(async () => {
                    const body = {
                      expected_revision: revision,
                      expected_entry_revision: entry.revision,
                    };
                    await api(`applications/${id}/entries/${entry.id}`, "DELETE", {
                      ...body,
                      request_id: requestId(body),
                    });
                    await onSaved();
                  });
                }}
              >
                删除
              </button>
            </EntryMenu>
          )}
        </>
      )}
      <p className="mt-2 text-sm text-secondary">
        <DateTime value={entry.created_at} />
      </p>
      <ErrorNotice code={action.error} />
      {confirm.confirmation}
    </li>
  );
}
function EntryEditor({
  id,
  entry,
  revision,
  onSaved,
  onCancel,
}: {
  id: string;
  entry?: Entry;
  revision: number;
  onSaved: () => Promise<void>;
  onCancel: () => void;
}) {
  const [text, setText] = useState(entry?.text || ""),
    [baseline] = useState({ revision, entryRevision: entry?.revision }),
    action = useAction(),
    requestId = useRequestId(),
    ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, []);
  const noChange = !!entry && text.trim() === (entry.text || "").trim();
  const valid = entry?.kind === "status" || !!text.trim();
  const save = () => {
    if (!valid || noChange || action.busy) return;
    void action.run(async () => {
      const body = {
        text: text.trim(),
        expected_revision: baseline.revision,
        ...(entry ? { expected_entry_revision: baseline.entryRevision } : {}),
      };
      await api(
        `applications/${id}/${entry ? `entries/${entry.id}` : "notes"}`,
        entry ? "PATCH" : "POST",
        { ...body, request_id: requestId(body) },
      );
      await onSaved();
    });
  };
  return (
    <div className="relative pb-2 pr-10">
      <label className="grid gap-2 text-sm">
        {entry ? (entry.kind === "status" ? "备注" : "笔记") : "新笔记"}
        <textarea
          ref={ref}
          aria-label={entry ? (entry.kind === "status" ? "备注" : "笔记") : "新笔记"}
          className={control}
          value={text}
          maxLength={20000}
          rows={4}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing &&
              e.keyCode !== 229
            ) {
              e.preventDefault();
              save();
            }
          }}
        />
      </label>
      <EntryMenu label="编辑操作" persistent>
        <button
          role="menuitem"
          className="w-full p-2 text-sm disabled:text-secondary"
          disabled={!valid || noChange || action.busy}
          onClick={save}
        >
          保存
        </button>
        <button
          role="menuitem"
          className="w-full p-2 text-sm"
          disabled={action.busy}
          onClick={onCancel}
        >
          取消
        </button>
      </EntryMenu>
      <ErrorNotice code={action.error} />
    </div>
  );
}
