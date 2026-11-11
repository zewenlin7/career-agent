"use client";
import { formatTime } from "@/lib/date-time";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Context, Page, Submission, Result } from "./contracts";
import { api, useRead, useAction, useRequestId, ApiError, endpoint } from "./client";
import { Select, Pages, ReadState, ErrorNotice, Field, control } from "./ui";
import { PreparationPage } from "./preparation";
import { readHistory } from "./history";
import { resumeChoices, resolveResume, type ResumeChoice } from "../profile-area/library";
import { useConfirmation } from "../profile-area/confirmation";
import { EntryMenu } from "../applications/entry-menu";

export function ResumePage({ ctx }: { ctx: Context }) {
  return <PreparationPage ctx={ctx} target="resume_tailoring" />;
}

export function SubmissionsPage({ ctx }: { ctx: Context }) {
  const [preview, setPreview] = useState(false);
  const [offset, setOffset] = useState(0),
    [resume, setResume] = useState(""),
    [exactResume, setExactResume] = useState(""),
    [greeting, setGreeting] = useState(""),
    [note, setNote] = useState(""),
    [saved, setSaved] = useState(""),
    [intent, setIntent] = useState(0);
  const choices = useRead<{ items: ResumeChoice[] }>(
    "resume-library/versions?limit=100",
    resumeChoices,
  );
  const renders = useRead<{ id: string; created_at: string }[]>(
    exactResume ? `resume-revisions/${exactResume}/renders` : null,
  );
  const greetings = useRead<Page<{ created_at: string; result: Result }>>(
    `applications/${ctx.application.id}/results?target=greeting_generation&limit=100`,
    readHistory,
  );
  const rows = useRead<Page<Submission>>(
    `applications/${ctx.application.id}/submissions?limit=10&offset=${offset}`,
  );
  const app = useRead<{ revision: number; status: string }>(`applications/${ctx.application.id}`);
  const action = useAction(),
    requestId = useRequestId(),
    reset = useConfirmation("确认切换", "取消切换");
  const pdf = renders.data?.[0]?.id;
  const refresh = () => {
    rows.reload();
    app.reload();
  };
  const afterDelete = async () => {
    const remaining = await api<Page<Submission>>(
      `applications/${ctx.application.id}/submissions?limit=1`,
    );
    if (offset > 0 && rows.data?.items.length === 1) setOffset(Math.max(0, offset - 10));
    refresh();
    const latest = await api<{ revision: number; status: string }>(
      `applications/${ctx.application.id}`,
    );
    if (
      !remaining.items.length &&
      latest.status === "applied" &&
      (await reset.confirm("这条申请已没有投递记录，是否将状态改为「关注中」？"))
    ) {
      await api(`applications/${ctx.application.id}`, "PATCH", {
        expected_revision: latest.revision,
        status: "tracking",
        correction: false,
        reason: null,
      });
      app.reload();
    }
  };
  return (
    <div className="space-y-8">
      <section aria-label="新增投递" className="space-y-4">
        <h1 className="text-xl font-semibold">新增投递</h1>
        <form
          className="max-w-4xl space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void action.run(async () => {
              if (!app.data || !pdf || !exactResume) throw new ApiError("invalid_input");
              const body = {
                expected_revision: app.data.revision,
                resume_revision_id: exactResume,
                render_artifact_id: pdf,
                greeting_id: greeting || null,
                package_id: null,
                note: note.trim() || null,
              };
              const result = await api<Submission>(
                `applications/${ctx.application.id}/submissions`,
                "POST",
                { ...body, request_id: requestId({ intent, ...body }) },
              );
              setSaved(
                result.status_changed ? "投递已记录，申请状态已更新为「已投递」" : "投递已记录",
              );
              setResume("");
              setExactResume("");
              setPreview(false);
              setGreeting("");
              setNote("");
              setIntent((n) => n + 1);
              setOffset(0);
              refresh();
            });
          }}
        >
          <fieldset disabled={action.busy} className="space-y-4">
            <div className="flex flex-wrap items-center gap-4">
              <Select
                inline
                label="简历"
                value={resume}
                onChange={(event) => {
                  const id = event.target.value;
                  setResume(id);
                  setExactResume("");
                  setPreview(false);
                  setSaved("");
                  const choice = choices.data?.items.find((item) => item.id === id);
                  if (choice)
                    void action.run(async () => setExactResume((await resolveResume(choice)).id));
                }}
              >
                <option value="">请选择简历</option>
                {choices.data?.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
              {pdf && (
                <Button onClick={() => setPreview(!preview)}>
                  {preview ? "关闭 PDF 预览" : "预览 PDF"}
                </Button>
              )}
            </div>
            {pdf && preview && (
              <iframe
                title="简历 PDF 预览"
                src={endpoint(`artifacts/${pdf}/download?inline=true`)}
                className="h-[640px] w-full border border-line"
              />
            )}
            {resume && !pdf && (
              <p className="text-sm text-secondary">这份简历尚无可用 PDF，请先到简历库生成。</p>
            )}
            <Select
              inline
              recordWidth="company"
              label="招呼语"
              value={greeting}
              onChange={(event) => setGreeting(event.target.value)}
            >
              <option value="">不使用</option>
              {greetings.data?.items.map((item) => (
                <option key={item.result.result_id} value={item.result.result_id || ""}>
                  {ctx.company.name} · {item.result.context.job_title} ·{" "}
                  {formatTime(item.created_at)}
                </option>
              ))}
            </Select>
            <Field label="备注" labelClassName="text-lg font-semibold">
              <textarea
                className={control}
                placeholder="补充投递备注"
                maxLength={20000}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </Field>
            <Button
              type="submit"
              variant="primary"
              disabled={!app.data || !pdf || !exactResume || action.busy}
            >
              {action.busy ? "正在记录…" : "记录投递"}
            </Button>
          </fieldset>
        </form>
        <ErrorNotice
          code={choices.error || renders.error || greetings.error || app.error || action.error}
        />
        {saved && <p role="status">{saved}</p>}
      </section>
      <section aria-label="投递记录" className="space-y-4 border-t border-line pt-6">
        <h2 className="text-xl font-semibold">投递记录</h2>
        <ReadState loaded={!!rows.data} error={rows.error} empty={!rows.data?.items.length} />
        <div className="space-y-4">
          {rows.data?.items.map((item) => (
            <SubmissionRow
              key={item.id}
              item={item}
              ctx={ctx}
              onSaved={refresh}
              onDeleted={() => action.run(afterDelete)}
            />
          ))}
        </div>
        {rows.data && (offset > 0 || rows.data.has_more) && (
          <Pages offset={offset} setOffset={setOffset} more={rows.data.has_more} />
        )}
      </section>
      {reset.confirmation}
    </div>
  );
}

function SubmissionRow({
  item,
  ctx,
  onSaved,
  onDeleted,
}: {
  item: Submission;
  ctx: Context;
  onSaved: () => void;
  onDeleted: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false),
    [text, setText] = useState(item.note || "");
  const action = useAction(),
    requestId = useRequestId(),
    confirm = useConfirmation();
  const save = () =>
    action.run(async () => {
      const note = text.trim() || null;
      if (note !== item.note) {
        const body = { expected_revision: item.revision, note };
        await api(`applications/${ctx.application.id}/submissions/${item.id}`, "PATCH", {
          ...body,
          request_id: requestId(body),
        });
        onSaved();
      }
      setEditing(false);
    });
  return (
    <article className="group relative space-y-2 border-b border-line px-2 pb-4 pr-10 text-base last:border-0 last:pb-0">
      <p>第 {item.display_number} 次投递</p>
      <p className="text-sm text-secondary">{formatTime(item.created_at)}</p>
      <p>
        简历　
        <Link
          className="text-accent-ink underline"
          href={`/profile/resumes?revision=${item.resume_revision_id}&pdf=${item.render_artifact_id}`}
        >
          {item.resume_name || "查看简历"}
        </Link>
      </p>
      {item.greeting_id && (
        <p>
          招呼语　
          {item.greeting_target_id ? (
            <Link
              className="text-accent-ink underline"
              href={`/applications/${ctx.application.id}/apply/greeting?result=${item.greeting_target_id}`}
            >
              {item.greeting_name || "查看招呼语"}
            </Link>
          ) : (
            <span className="text-secondary">历史材料暂不可读取</span>
          )}
        </p>
      )}
      {editing ? (
        <textarea
          autoFocus
          aria-label="投递备注"
          className={control}
          maxLength={20000}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing &&
              event.keyCode !== 229
            ) {
              event.preventDefault();
              if (!action.busy) void save();
            }
          }}
        />
      ) : (
        item.note && (
          <p className="whitespace-pre-wrap" onDoubleClick={() => setEditing(true)}>
            {item.note}
          </p>
        )
      )}
      <EntryMenu label="投递记录操作" persistent={editing}>
        {editing ? (
          <>
            <Button disabled={action.busy} onClick={() => void save()}>
              保存
            </Button>
            <Button
              onClick={() => {
                setText(item.note || "");
                setEditing(false);
              }}
            >
              取消
            </Button>
          </>
        ) : (
          <>
            <Button
              onClick={() => {
                setText(item.note || "");
                setEditing(true);
              }}
            >
              编辑备注
            </Button>
            <Button
              onClick={() =>
                void action.run(async () => {
                  if (!(await confirm.confirm("确定删除这条投递记录吗？历史材料将保留。"))) return;
                  const body = { expected_revision: item.revision };
                  await api(`applications/${ctx.application.id}/submissions/${item.id}`, "DELETE", {
                    ...body,
                    request_id: requestId({ remove: true, ...body }),
                  });
                  await onDeleted();
                })
              }
            >
              删除记录
            </Button>
          </>
        )}
      </EntryMenu>
      <ErrorNotice code={action.error} />
      {confirm.confirmation}
    </article>
  );
}
