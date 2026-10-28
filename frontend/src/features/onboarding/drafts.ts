import type { Fact, Profile, ResumeDocument, ResumeSection } from "./contracts";

/** Canonical object equality preserves meaningful array order. */
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, v]) => `${JSON.stringify(key)}:${canonical(v)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

/** Editable proposal only: missing evidence remains missing and cannot be saved as grounded. */
export function draftFromProfile(
  profile: Profile,
  facts: Fact[],
  id = () => crypto.randomUUID(),
): ResumeDocument {
  const sections: ResumeSection[] = [];
  for (const [key, name] of [
    ["education", "education"],
    ["experiences", "experience"],
    ["projects", "projects"],
  ] as const) {
    const entries = profile.data[key];
    if (!entries.length) continue;
    sections.push({
      section_id: id(),
      name,
      ordering: sections.length,
      priority: 80,
      required: true,
      items: entries.map((entry, ordering) => ({
        item_id: id(),
        kind: "entry",
        text: [entry.organization, entry.role, entry.description].filter(Boolean).join(" · "),
        short_text: null,
        fact_refs: [...entry.fact_ids],
        requirement_refs: [],
        hard_claims: [],
        priority: 80,
        required: true,
        ordering,
      })),
    });
  }
  const linked = new Set(
    [...profile.data.education, ...profile.data.experiences, ...profile.data.projects].flatMap(
      (e) => e.fact_ids,
    ),
  );
  if (profile.data.skills.length)
    sections.push({
      section_id: id(),
      name: "skills",
      ordering: sections.length,
      priority: 50,
      required: false,
      items: profile.data.skills.map((skill, ordering) => ({
        item_id: id(),
        kind: "bullet",
        text: skill,
        short_text: null,
        fact_refs: facts
          .filter((f) => linked.has(f.id) && f.status === "verified" && f.statement.includes(skill))
          .map((f) => f.id),
        requirement_refs: [],
        hard_claims: [],
        priority: 50,
        required: false,
        ordering,
      })),
    });
  return {
    locale: "zh-CN",
    metadata: { label: "基础简历" },
    schema_version: "resume-v2",
    template: "resume_zh_cn_a4_single_v1",
    target_page_count: 1,
    profile_id: profile.id,
    profile_revision: profile.revision,
    job_revision_id: null,
    sections,
  };
}
