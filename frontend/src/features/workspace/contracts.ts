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
  label?: string | null;
  resume_revision_id: string;
  resume_variant_id: string;
  revision: number;
  profile_id: string;
  job_revision_id: string | null;
  created_at: string;
  hints: { same_job: boolean; same_jd: boolean; original: boolean };
};
export type Entry = {
  main_question_number?: number | null;
  followup_index?: number | null;
  entry_id: string;
  order: number;
  kind: "primary" | "follow_up";
  question: string;
  answer: string | null;
  primary_entry_id: string | null;
};
export type Actual = {
  status: "draft" | "completed";
  round_number: number | null;
  interview_type: string | null;
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
  available?: boolean;
  resume_name?: string;
  feedback_target?: {
    subject_id: string;
    task_type: string;
    accepted_model_call_id?: string | null;
    operation_id?: string | null;
    origin?: "business" | "evaluation";
  } | null;
  kind: Target;
  status: string;
  result_id: string | null;
  target_artifact_id: string | null;
  resume_revision_id: string | null;
  source_resume_revision_id: string | null;
  source_resume_name?: string | null;
  source_research_id?: string | null;
  source_profile_id?: string | null;
  source_original_target_id?: string | null;
  refinement_resume_revision_id?: string | null;
  refinement_resume_name?: string | null;
  refinement_profile_id?: string | null;
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
  display_number: number;
  revision: number;
  resume_name: string | null;
  greeting_name: string | null;
  greeting_target_id: string | null;
  status_changed: boolean;
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
  compatible_for_interview?: boolean;
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
    attempts?: {
      number: number;
      decisions: { action: "short_text" | "remove_item" | "remove_section"; target_id: string }[];
    }[];
  };
};
export type Mock = {
  latest_request_id?: string | null;
  application_id: string | null;
  display_number?: number | null;
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
    question_number?: string;
    main_question_number?: number;
    followup_index?: number | null;
    id: string;
    sequence: number;
    question: {
      kind: "primary" | "follow_up";
      question: string;
      topic?: string;
      primary_entry_id: string | null;
    };
    answer: string | null;
    accepted_model_call_id: string | null;
  }[];
};
export type SessionRow = {
  creation_request_id?: string | null;
  focus?: string;
  policy?: { mode: string; primary_target: number; followup_max: number };
  primary_question_count?: number;
  followup_count?: number;
  generation_active?: boolean;
  stop_reason?: string | null;
  application_id?: string | null;
  display_number?: number | null;
  id: string;
  created_at: string;
  status: string;
  revision: number;
  round_name?: string;
  content_revision?: number;
};
export type DebriefRow = {
  source_name?: string;
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
  source_name?: string;
  source_changed?: boolean | null;
  created_at?: string;
  reused?: boolean;
  execution_revision?: number;
  execution_active?: boolean;
  recovery?: Record<string, string>;
  transcript?: (Entry & { question_number: string })[];
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
    notes?: { text: string; recorded_at: string }[];
  };
  artifacts: {
    id: string;
    kind: "group" | "overall";
    group_index: number | null;
    group_ref?: string | null;
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
  updated_at?: string | null;
  revision: number;
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
  if (code === "debrief_removed") return "这条复盘记录已删除，请选择其他记录。";
  if (code === "debrief_running") return "这次复盘仍在执行，请稍后检查状态。";
  if (code === "debrief_not_retryable") return "当前没有可安全重试的失败项，请检查已保存结果。";
  if (code === "note_removed") return "这条笔记已删除，原输入已保留。";
  if (code === "note_content_required") return "请填写笔记标题和内容。";
  if (code === "layout_budget_exceeded") return "生成内容超出简历篇幅限制，未保存为新简历。";
  if (["invalid_output", "output_schema_invalid", "schema_validation_failed"].includes(code))
    return "模型返回的内容格式不完整，本次未保存。原有结果不受影响。";
  if (["grounding_failed", "hard_field_mismatch", "invalid_reference"].includes(code))
    return "生成内容未通过事实核验，本次未保存。原有结果不受影响。";
  if (code === "research_scope_invalid") return "研究内容超出公司资料范围，请重新研究。";
  if (code === "entry_read_only") return "这条记录不能修改。";
  if (code === "note_required") return "请输入笔记内容。";
  if (code === "application_not_closed") return "仅已关闭的申请可以删除，请刷新后核对状态。";
  if (code === "application_deleted") return "申请已删除，无法继续操作。";
  if (code === "company_selection_required") return "找到多家同名公司，请从候选列表中选择。";
  if (["unsupported_requirement_inference", "requirement_evidence_missing"].includes(code))
    return "未能从职位描述中可靠提取要求，匹配分析尚未开始。请检查职位描述后重试。";
  if (["missing_verified_fact", "verified_facts_required"].includes(code))
    return "当前材料缺少可用的个人经历依据，请补充个人资料后重试。";
  if (code === "profile_required" || code === "not_found")
    return "未找到所需资料，请先完善资料或刷新页面。";

  if (code === "resume_claims_unsupported") return "请在简历库修改缺少个人资料依据的描述后重试。";
  if (code === "resume_selection_required") return "请先在申请概览中选择要使用的简历。";
  if (code === "interview_round_conflict") return "该轮次已有面试记录，请选择其他轮次。";
  if (code === "interview_questions_required") return "请至少填写一道有效主问题。";
  if (code === "interview_source_contract_incompatible")
    return "这份历史记录的输入不兼容当前生成方式。原记录仍可查看，请基于当前绑定材料新建。";
  if (code === "historical_reference_unavailable")
    return "暂时无法确认这条历史记录的归属或引用，未删除。";
  if (code === "research_removed" || code === "result_removed")
    return "所选记录已删除，请重新选择。";
  if (code === "feedback_required") return "请填写希望调整的内容。";
  if (code === "budget_exhausted" || code === "insufficient_token_budget")
    return "本次任务的预算不足，未能继续生成。请检查任务预算或精简输入；等待不会自动增加预算。";
  if (["provider_429", "provider_rate_limited"].includes(code))
    return "模型服务请求过多，请稍后重试。";
  if (code === "operation_attempt_limit") return "本次任务已达到尝试次数上限，请核对已保存结果。";
  if (code === "context_too_large") return "输入资料过长，请精简后重试。";
  if (code === "no_eligible_model") return "当前没有符合任务限制的可用模型，请检查模型配置与预算。";
  if (code === "model_admission_denied") return "模型服务暂未接受本次请求，请稍后重试。";
  if (code === "operation_deadline_exceeded") return "本次任务已超出执行时间，请先核对已保存状态。";
  if (/timeout/.test(code)) return "本次生成超时，请先核对已保存状态。";
  if (code === "greeting_deleted") return "该招呼语已删除，请重新选择。";
  if (/revision|conflict|stale/.test(code))
    return "记录已变化或请求冲突。请重新读取后核对，未自动重试。";
  if (/recovery|unknown/.test(code))
    return "执行结果需要人工恢复确认。请查看已保存状态，不要重复生成。";
  if (/interrupted|unavailable|request_failed/.test(code))
    return "连接中断或暂时无法读取。操作可能已经保存，请先重新查询状态。";
  if (code === "artifact_save_failed") return "结果已生成，但保存失败，请重试保存。";
  if (code === "resume_library_save_failed") return "优化结果已生成，但保存失败，请重试保存。";
  if (code === "fit_result_unavailable")
    return "匹配已结束，但暂时无法读取结果，请重新打开匹配记录。";
  if (code === "no_current_research") return "暂无近期公司研究，可以开始研究。";
  return "本次请求未能完成，原有结果不受影响。请先查看任务状态。";
}
