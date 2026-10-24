import type { Application, Job, Company } from "../applications/contracts";
export type Context = { application: Application; job: Job; company: Company };
export type Page<T> = { items: T[]; has_more: boolean; limit: number; offset: number };
export type Mode = "fixture" | "live";
export type Target =
  "fit_analysis" | "resume_tailoring" | "greeting_generation" | "interview_preparation";
export type Profile = {
  id: string;
  revision: number;
  created_at: string;
  data: { display_name: string };
};
export type ResumeChoice = {
  resume_revision_id: string;
  resume_variant_id: string;
  revision: number;
  profile_id: string;
  job_revision_id: string | null;
  created_at: string;
  hints: { same_job: boolean; same_jd: boolean; original: boolean };
};
export type Entry = {
  entry_id: string;
  order: number;
  kind: "primary" | "follow_up";
  question: string;
  answer: string | null;
  primary_entry_id: string | null;
};
export type Actual = {
  id: string;
  application_id: string;
  content_revision: number;
  round_name: string;
  occurred_at: string | null;
  created_at: string;
  entries: Entry[];
  notes: { text: string; recorded_at: string }[];
};
export type Operation = {
  id: string;
  kind: string;
  request_id: string;
  status: string;
  reason: string | null;
  package_id: string | null;
  research_report_id: string | null;
  run_id: string;
  created_at: string;
  allowed_actions: string[];
};
export type PackageRow = {
  id: string;
  run_id: string;
  profile_id: string;
  job_revision_id: string;
  outcome: { status: string } | null;
};
export type Result = {
  kind: Target;
  status: string;
  result_id: string | null;
  target_artifact_id: string | null;
  resume_revision_id: string | null;
  source_resume_revision_id: string | null;
  resume_variant_id: string | null;
  revision: number | null;
  render_artifact_id: string | null;
  download_url: string | null;
  content: Record<string, unknown> | null;
  context: {
    profile_id: string;
    profile_revision: number;
    job_id: string;
    job_revision_id: string;
    job_revision: number;
    job_title: string;
    company_id: string;
  };
  reused: boolean;
  versions: Record<string, unknown>;
  reason: string | null;
  allowed_actions: string[];
};
export type PackageView = { package_id: string; run_id: string; status: string; results: Result[] };
export type Submission = {
  id: string;
  application_id: string;
  created_at: string;
  event_id: string;
  request_id: string;
  expected_revision: number;
  resume_revision_id: string;
  render_artifact_id: string;
  greeting_id: string | null;
  package_id: string | null;
  note: string | null;
};
export type Research = {
  id: string;
  company_id: string;
  research_version: number;
  fetched_at: string;
  expires_at: string;
  reusable_for_current_execution?: boolean;
  data: {
    mode: Mode;
    report: {
      conclusions: { text: string; evidence_refs: string[] }[];
      unknowns: string[];
      inference: { text: string; evidence_refs: string[] }[];
    };
    evidence: {
      id: string;
      title: string;
      source_url: string;
      retrieved_at: string;
      provider: string;
      content: string;
    }[];
  };
};
export type Variant = {
  id: string;
  resume_revision_id: string;
  revision: number;
  created_at: string;
  document: Record<string, unknown>;
};
export type Render = {
  id: string;
  resume_variant_id: string;
  resume_variant_revision: number;
  report: {
    render_status: string;
    validation_status: string;
    error_code?: string;
    page_count: number | null;
    findings: { code?: string; message?: string }[];
  };
};
export type Mock = {
  id: string;
  revision: number;
  status: string;
  generation_active: boolean;
  pending_question_id: string | null;
  stop_reason: string | null;
  completion_type: string | null;
  primary_question_count: number;
  followup_count: number;
  interviewer_turn_count: number;
  policy: { primary_target: number; followup_max: number };
  context: {
    job_id: string;
    binding: { profile_id: string; job_revision_id: string; resume_revision_id: string };
  };
  turns: {
    id: string;
    sequence: number;
    question: { kind: string; question: string; topic: string; primary_entry_id: string | null };
    answer: string | null;
    accepted_model_call_id: string | null;
  }[];
};
export type SessionRow = {
  id: string;
  created_at: string;
  status: string;
  revision: number;
  round_name?: string;
  content_revision?: number;
};
export type DebriefRow = {
  id: string;
  generation_id: string;
  selected_run_id: string;
  root_run_id: string;
  is_selected: boolean;
  status: string;
  source_kind: "actual" | "mock";
  source_id: string;
  created_at: string;
};
export type Debrief = {
  id: string;
  root_run_id: string;
  run_id: string;
  status: string;
  source_hash: string;
  event_sequence: number;
  snapshot: {
    source_kind: "actual" | "mock";
    interview_id: string;
    content_revision: number;
    entries: Entry[];
  };
  artifacts: {
    id: string;
    kind: "group" | "overall";
    group_index: number | null;
    status: string;
    error_code: string | null;
    attempts: number;
    presentation: {
      display_order: number;
      qa?: { question: string; answer: string | null; answer_missing: boolean; label: string }[];
      evaluation?: Record<string, unknown>;
    };
  }[];
};
export type Knowledge = {
  id: string;
  application_id: string;
  title: string;
  content: string;
  interview_id: string | null;
  created_at: string;
};
export const statusText: Record<string, string> = {
  pending: "待执行",
  running: "执行中",
  success: "成功",
  completed: "完成",
  partial: "部分完成",
  failure: "失败",
  failed: "失败",
  blocked: "被阻止",
  needs_input: "需要补充输入",
  decision_required: "需要用户决定",
  recovery_required: "需要人工恢复",
  ready: "待执行",
  ready_to_generate: "可生成问题",
  waiting_answer: "等待回答",
  retrying: "自动重试中",
  accepted: "PDF 已验收",
  layout_failed: "版面无法通过",
  target_reached: "已达到问题数量",
  user_ended_early: "用户提前结束",
};
export function errorText(code: string) {
  if (/revision|conflict|stale/.test(code))
    return "记录已变化或请求冲突。请重新读取后核对，未自动重试。";
  if (/recovery|unknown/.test(code))
    return "执行结果需要人工恢复确认。请查看已保存状态，不要重复生成。";
  if (/interrupted|unavailable|request_failed/.test(code))
    return "连接中断或暂时无法读取。操作可能已经保存，请先重新查询状态。";
  if (code === "no_current_research") return "当前模式下没有新鲜且兼容的公司研究。";
  return "请求未完成。请核对输入、版本和来源后再操作。";
}
