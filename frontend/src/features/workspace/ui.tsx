"use client";
import type { ReactNode, ReactElement, SelectHTMLAttributes } from "react";
import { cloneElement, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Surface } from "@/components/ui/surface";
import { errorText, statusText } from "./contracts";
import { useRead } from "./client";
import type { Mode, Page, Profile, ResumeChoice, Context } from "./contracts";
export const control =
  "w-full min-h-11 rounded-control border border-line bg-paper px-3 py-2 text-sm";
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactElement<{ id?: string }>;
}) {
  const id = useId();
  return (
    <div className="grid gap-2 text-sm font-medium">
      <label htmlFor={id}>{label}</label>
      {cloneElement(children, { id })}
    </div>
  );
}
export function Select({
  label,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  return (
    <Field label={label}>
      <select {...props} className={control}>
        {children}
      </select>
    </Field>
  );
}
export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Surface className="space-y-4" aria-label={title}>
      <h2 className="font-serif text-lg font-semibold">{title}</h2>
      {children}
    </Surface>
  );
}
export function Status({ value }: { value: string }) {
  return (
    <span className="rounded-control border border-line px-2 py-1 text-sm">
      {statusText[value] || value}
    </span>
  );
}
export function ErrorNotice({ code }: { code?: string }) {
  return code ? (
    <p
      role="alert"
      className="rounded-control border border-error-line bg-error-soft p-3 text-sm text-error"
    >
      {errorText(code)} <span className="break-all">({code})</span>
    </p>
  ) : null;
}
export function ReadState({
  error,
  loaded,
  empty = false,
}: {
  error?: string;
  loaded: boolean;
  empty?: boolean;
}) {
  return error ? (
    <ErrorNotice code={error} />
  ) : !loaded ? (
    <p role="status">正在读取…</p>
  ) : empty ? (
    <p className="text-sm text-secondary">暂无记录。</p>
  ) : null;
}
export function Refs({ values }: { values: Record<string, unknown> }) {
  return (
    <details className="text-sm text-secondary">
      <summary className="cursor-pointer">来源与标识</summary>
      <dl className="mt-2 grid gap-2">
        {Object.entries(values)
          .filter(([, v]) => v != null)
          .map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd className="break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
            </div>
          ))}
      </dl>
    </details>
  );
}
export function Pages({
  offset,
  setOffset,
  more,
  size = 10,
}: {
  offset: number;
  setOffset: (n: number) => void;
  more: boolean;
  size?: number;
}) {
  return (
    <nav aria-label="记录分页" className="flex items-center gap-3 text-sm">
      <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - size))}>
        上一页
      </Button>
      <span>第 {Math.floor(offset / size) + 1} 页</span>
      <Button disabled={!more} onClick={() => setOffset(offset + size)}>
        下一页
      </Button>
    </nav>
  );
}
export function ModeSelect({ value, onChange }: { value: Mode; onChange: (v: Mode) => void }) {
  return (
    <div className="space-y-2">
      <Select label="执行模式" value={value} onChange={(e) => onChange(e.target.value as Mode)}>
        <option value="fixture">Fixture · 确定性演示结果</option>
        <option value="live">Live · 真实模型，可能产生费用</option>
      </Select>
      <p className="text-sm text-secondary">仅点击明确的执行按钮才调用；页面读取不会启动任务。</p>
    </div>
  );
}
export function BindingFields({
  ctx,
  profile,
  setProfile,
  resume,
  setResume,
  needResume = true,
}: {
  ctx: Context;
  profile: string;
  setProfile: (s: string) => void;
  resume: string;
  setResume: (s: string) => void;
  needResume?: boolean;
}) {
  const [po, setPo] = useState(0),
    [ro, setRo] = useState(0);
  const profiles = useRead<Page<Profile>>(`profile/revisions?limit=10&offset=${po}`);
  const resumes = useRead<ResumeChoice[]>(
    profile && needResume
      ? `resume-revisions?profile_id=${profile}&job_revision_id=${ctx.job.job_revision_id}&limit=10&offset=${ro}`
      : null,
  );
  return (
    <div className="space-y-4">
      <Select
        label="Profile 历史版本（明确选择）"
        value={profile}
        required
        onChange={(e) => {
          setProfile(e.target.value);
          setResume("");
          setRo(0);
        }}
      >
        <option value="">请选择 Profile</option>
        {profiles.data?.items.map((p) => (
          <option key={p.id} value={p.id}>
            {p.data.display_name} · revision {p.revision} · {p.id}
          </option>
        ))}
      </Select>
      <ErrorNotice code={profiles.error} />
      {profiles.data && (
        <Pages
          offset={po}
          setOffset={(n) => {
            setPo(n);
            setProfile("");
            setResume("");
          }}
          more={profiles.data.has_more}
        />
      )}
      {needResume && (
        <>
          <Select
            label="来源 Resume exact revision（不自动选择）"
            value={resume}
            required
            disabled={!profile}
            onChange={(e) => setResume(e.target.value)}
          >
            <option value="">请选择 Resume revision</option>
            {resumes.data?.map((r) => (
              <option key={r.resume_revision_id} value={r.resume_revision_id}>
                revision {r.revision} ·{" "}
                {r.hints.same_jd ? "当前 JD" : r.hints.same_job ? "同一 Job" : "其他来源"} ·{" "}
                {r.resume_revision_id}
              </option>
            ))}
          </Select>
          <ErrorNotice code={resumes.error} />
          {resumes.data && (
            <>
              <Pages
                offset={ro}
                setOffset={(n) => {
                  setRo(n);
                  setResume("");
                }}
                more={resumes.data.length === 10}
              />
              {!resumes.data.length && (
                <p className="text-sm text-secondary">
                  此 Profile 下暂无简历。请先通过已有后端能力建立合法 base
                  Resume；此页面不会代选或编造。
                </p>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
