import type { ResumeSection } from "../onboarding/contracts";
export type ResumeFieldError = {
  section: number;
  item: number;
  field: "short_text";
  code: "short_text_not_shorter";
};
export function safeResumeFields(value: unknown): ResumeFieldError[] {
  if (!Array.isArray(value)) return [];
  return value
    .slice(0, 500)
    .filter(
      (v): v is ResumeFieldError =>
        v !== null &&
        typeof v === "object" &&
        Number.isInteger(v.section) &&
        v.section >= 0 &&
        v.section < 10 &&
        Number.isInteger(v.item) &&
        v.item >= 0 &&
        v.item < 1000 &&
        v.field === "short_text" &&
        v.code === "short_text_not_shorter",
    )
    .map(({ section, item, field, code }) => ({ section, item, field, code }));
}
export function invalidShortText(text: string, short: string | null | undefined): boolean {
  return (
    !!short &&
    Array.from(short.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, "")).length >=
      Array.from(text.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, "")).length
  );
}
export function shortTextErrors(sections: ResumeSection[]): ResumeFieldError[] {
  return sections.flatMap((s, section) =>
    s.items.flatMap((v, item) =>
      invalidShortText(v.text, v.short_text)
        ? [{ section, item, field: "short_text" as const, code: "short_text_not_shorter" as const }]
        : [],
    ),
  );
}
