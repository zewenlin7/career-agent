"use client";
import { useCallback } from "react";
import type { Context, SessionRow } from "./contracts";
import { useRead } from "./client";
import { actualLabel, readActualHistory } from "./actual-interview";
import { readHistory } from "./history";
import { formatTime } from "@/lib/date-time";
import { control } from "./ui";

export type InterviewChoice = {
  key: string;
  id: string;
  kind: "actual" | "mock";
  name: string;
  eligible: boolean;
};
export function useInterviewChoices(ctx: Context) {
  const application = ctx.application.id,
    company = ctx.company.name,
    title = ctx.job.title;
  const loader = useCallback(
    async (_path: string, signal: AbortSignal) => {
      const [actual, mock] = await Promise.all([
        readActualHistory(`interviews?application_id=${application}`, signal),
        readHistory<SessionRow>(`mock-interviews?application_id=${application}`, signal),
      ]);
      return [
        ...mock.items.map((r): InterviewChoice => ({
          key: `mock:${r.id}`,
          id: r.id,
          kind: "mock",
          name: r.display_number
            ? `模拟面试 · 第 ${r.display_number} 场`
            : `模拟面试 · ${formatTime(r.created_at)}`,
          eligible: r.status === "completed" && !r.generation_active,
        })),
        ...actual.map((r): InterviewChoice => ({
          key: `actual:${r.id}`,
          id: r.id,
          kind: "actual",
          name: `真实面试 · ${actualLabel(r, { company: { name: company }, job: { title } } as Context)}`,
          eligible: r.status === "completed",
        })),
      ];
    },
    [application, company, title],
  );
  return useRead<InterviewChoice[]>(`interview-choices:${application}`, loader);
}
export function InterviewChoiceSelect({
  rows,
  value,
  onChange,
  eligibleOnly = false,
}: {
  rows: InterviewChoice[];
  value: string;
  onChange: (value: string) => void;
  eligibleOnly?: boolean;
}) {
  return (
    <label className="flex w-full min-w-0 max-w-[42rem] flex-wrap items-center gap-3 text-base font-medium leading-relaxed">
      <span className="shrink-0">面试记录</span>
      <select
        aria-label="面试记录"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`${control.replace("text-sm", "text-base")} min-w-0 flex-1 basis-60`}
      >
        <option value="">选择一条面试记录</option>
        {(["mock", "actual"] as const).map((kind) => (
          <optgroup key={kind} label={kind === "mock" ? "模拟面试" : "真实面试"}>
            {rows
              .filter((r) => r.kind === kind && (!eligibleOnly || r.eligible))
              .map((r) => (
                <option key={r.key} value={r.key}>
                  {r.name}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}
export function interviewHref(application: string, kind: "actual" | "mock", id: string) {
  return `/applications/${application}/interview/history?${kind === "actual" ? "actual" : "session"}=${id}`;
}
