import type { ApplicationStatus } from "../applications/contracts";
export type Experience = {
  organization: string;
  role: string;
  description: string;
  fact_ids: string[];
};
export type ProfileData = {
  display_name: string;
  education: Experience[];
  experiences: Experience[];
  projects: Experience[];
  skills: string[];
  preferences: Record<string, string>;
};
export type Profile = { id: string; created_at: string; revision: number; data: ProfileData };
export type ResumeItem = {
  item_id: string;
  kind: "bullet" | "summary" | "entry";
  text: string;
  short_text: string | null;
  fact_refs: string[];
  requirement_refs: string[];
  hard_claims: {
    kind: "organization" | "title" | "degree" | "date" | "number";
    value: string;
    fact_ref: string;
  }[];
  priority: number;
  required: boolean;
  ordering: number;
};
export type ResumeSection = {
  section_id: string;
  name: "summary" | "experience" | "projects" | "education" | "skills";
  ordering: number;
  priority: number;
  required: boolean;
  items: ResumeItem[];
};
export type ResumeDocument = {
  locale: "zh-CN";
  metadata: { label: string | null };
  schema_version: "resume-v2";
  template: "resume_zh_cn_a4_single_v1";
  target_page_count: 1;
  profile_id: string;
  profile_revision: number;
  job_revision_id: string | null;
  sections: ResumeSection[];
};
export type Variant = {
  input_snapshot?: {
    display_name: string;
    personal?: {
      phone?: string;
      email?: string;
      city?: string;
      github?: string;
      website?: string;
      other_contact?: string;
      photo_id?: string | null;
    } | null;
  };
  id: string;
  resume_revision_id: string;
  revision: number;
  created_at: string;
  document: ResumeDocument;
};
export const sectionLabels: Record<ResumeSection["name"], string> = {
  summary: "个人简介",
  experience: "工作经历",
  projects: "项目经历",
  education: "教育经历",
  skills: "技术栈",
};
export const blankProfile = (): ProfileData => ({
  display_name: "",
  education: [],
  experiences: [],
  projects: [],
  skills: [],
  preferences: {},
});
export const transitions: Record<ApplicationStatus, ApplicationStatus[]> = {
  tracking: ["preparing", "applied", "withdrawn", "closed"],
  preparing: ["applied", "withdrawn", "closed"],
  applied: ["interviewing", "offer", "rejected", "withdrawn", "closed"],
  interviewing: ["offer", "rejected", "withdrawn", "closed"],
  offer: ["withdrawn", "closed"],
  rejected: [],
  withdrawn: [],
  closed: [],
};
