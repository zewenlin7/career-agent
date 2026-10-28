"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import type { Context, Page, ResumeChoice, Submission, Result } from "./contracts";
import type { ApplicationBinding } from "./application-binding";
import { api, useRead, useAction, useRequestId, ApiError } from "./client";
import { Panel, Select, Pages, ReadState, ErrorNotice, Field, control } from "./ui";
import { PdfLinks } from "./results";
import { PreparationPage } from "./preparation";
export function ResumePage({ ctx }: { ctx: Context }) {
  return (
    <div className="space-y-6">
      <Link
        href="/profile/resumes"
        className="inline-flex min-h-11 items-center text-accent-ink underline"
      >
        管理简历库
      </Link>
      <PreparationPage ctx={ctx} target="resume_tailoring" />
    </div>
  );
}

export function SubmissionsPage({ ctx }: { ctx: Context }) {
  const [offset, setOffset] = useState(0);
  const [selectedResume, setSelectedResume] = useState<string | null>(null);
  const [greeting, setGreeting] = useState("");
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [saved, setSaved] = useState(false);
  const binding = useRead<ApplicationBinding>(`applications/${ctx.application.id}/context`);
  const resume = selectedResume ?? binding.data?.resume_revision_id ?? "";
  const choices = useRead<ResumeChoice[]>(
    binding.data?.profile_id
      ? `resume-revisions?profile_id=${binding.data.profile_id}&job_revision_id=${binding.data.job_revision_id}&limit=100`
      : null,
  );
  const renders = useRead<{ id: string; created_at: string }[]>(
    resume ? `resume-revisions/${resume}/renders` : null,
  );
  const greetings = useRead<Page<{ created_at: string; result: Result }>>(
    `applications/${ctx.application.id}/results?target=greeting_generation&limit=100`,
  );
  const rows = useRead<Page<Submission>>(
    `applications/${ctx.application.id}/submissions?limit=10&offset=${offset}`,
  );
  const app = useRead<{ revision: number }>(`applications/${ctx.application.id}`);
  const action = useAction(),
    requestId = useRequestId(),
    router = useRouter();
  const pdf = renders.data?.[0]?.id;
  const compatibleGreetings =
    greetings.data?.items.filter((item) => item.result.source_resume_revision_id === resume) ?? [];
  return (
    <div className="space-y-6">
      <Panel title="本次投递材料">
        <form
          className="max-w-[760px] space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void action.run(async () => {
              if (!app.data || !pdf || !confirmed) throw new ApiError("invalid_input");
              const body = {
                expected_revision: app.data.revision,
                resume_revision_id: resume,
                render_artifact_id: pdf,
                greeting_id: greeting || null,
                package_id: null,
                note: note.trim() || null,
              };
              await api(`applications/${ctx.application.id}/submissions`, "POST", {
                ...body,
                request_id: requestId(body),
              });
              setSaved(true);
              setConfirmed(false);
              rows.reload();
              app.reload();
              router.refresh();
            });
          }}
        >
          <fieldset disabled={action.busy} className="space-y-4">
            <Select
              label="简历"
              value={resume}
              onChange={(event) => {
                setSelectedResume(event.target.value);
                setGreeting("");
                setSaved(false);
              }}
            >
              <option value="">请选择简历</option>
              {resume && !choices.data?.some((item) => item.resume_revision_id === resume) && (
                <option value={resume}>{binding.data?.resume_name || "当前使用简历"}</option>
              )}
              {choices.data?.map((item) => (
                <option key={item.resume_revision_id} value={item.resume_revision_id}>
                  {item.label || "简历"} · 第 {item.revision} 版
                </option>
              ))}
            </Select>
            <ErrorNotice
              code={binding.error || choices.error || renders.error || greetings.error}
            />
            {pdf ? (
              <div>
                <p className="mb-2 text-sm">已准备好所选简历的 PDF</p>
                <PdfLinks id={pdf} />
              </div>
            ) : (
              <p className="text-sm text-muted">
                {resume ? "这份简历尚无可用 PDF，请先到简历库生成。" : "选择本次实际使用的简历。"}{" "}
                <Link className="underline" href="/profile/resumes">
                  打开简历库
                </Link>
              </p>
            )}
            <Select
              label="招呼语（可选）"
              value={greeting}
              onChange={(event) => setGreeting(event.target.value)}
            >
              <option value="">不使用</option>
              {compatibleGreetings.map((item) => (
                <option key={item.result.result_id} value={item.result.result_id || ""}>
                  招呼语 · {new Date(item.created_at).toLocaleString("zh-CN")}
                </option>
              ))}
            </Select>
            <Field label="备注（可选）">
              <textarea
                className={control}
                maxLength={20000}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </Field>
            <label className="flex gap-2">
              <input
                type="checkbox"
                required
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              我已完成真实投递
            </label>
            <Button
              type="submit"
              variant="primary"
              disabled={!app.data || !pdf || !resume || !confirmed || action.busy}
            >
              {action.busy ? "正在记录…" : "记录投递"}
            </Button>
          </fieldset>
        </form>
        <ErrorNotice code={app.error || action.error} />
        {saved && <p role="status">投递已记录。</p>}
      </Panel>
      <Panel title="投递记录">
        <ReadState loaded={!!rows.data} error={rows.error} empty={rows.data?.items.length === 0} />
        {rows.data?.items.map((item) => (
          <article key={item.id} className="space-y-3 border-b border-line pb-4">
            <p>{new Date(item.created_at).toLocaleString("zh-CN")}</p>
            {item.note && <p>{item.note}</p>}
            <PdfLinks id={item.render_artifact_id} />
          </article>
        ))}
        {rows.data && <Pages offset={offset} setOffset={setOffset} more={rows.data.has_more} />}
      </Panel>
    </div>
  );
}
