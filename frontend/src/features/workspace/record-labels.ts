import { formatTime } from "../../lib/date-time.ts";

/** Names describe known metadata; exact IDs remain the only record identity. */
export function researchRecordName(company?: string | null, fetchedAt?: string | null): string {
  return [company?.trim() || "公司研究", formatTime(fetchedAt)].filter(Boolean).join(" · ");
}

export function resultRecordName(
  kind: string,
  company?: string | null,
  jobTitle?: string | null,
  createdAt?: string | null,
  resumeName?: string | null,
): string {
  if (kind === "resume_tailoring") return resumeName?.trim() || "简历";
  const parts = kind === "fit_analysis" ? [jobTitle, company] : [company, jobTitle];
  const known = parts.map((value) => value?.trim()).filter(Boolean);
  if (!known.length)
    known.push(
      kind === "fit_analysis"
        ? "匹配记录"
        : kind === "interview_preparation"
          ? "准备记录"
          : "招呼语记录",
    );
  return [...known, formatTime(createdAt)].filter(Boolean).join(" · ");
}
