/** One safe presentation for execution areas and browser-local notifications. */
export type TaskFeedbackState = {
  state: string;
  reason?: string | null;
  decision?: { action: "ask" | "finish" } | null;
};
export function taskMessage(action: string, value: TaskFeedbackState): string {
  if (value.state === "removed") return "这条复盘记录已删除。";
  if (value.state === "partial")
    return value.reason
      ? `${action}部分完成。${taskMessage("未完成项", { ...value, state: "failure" })}`
      : `${action}部分完成，请查看已保存结果。`;
  const code = value.reason || "";
  if (code === "invalid_evidence_reference") return `${action}失败：生成内容的问答依据未通过核验。`;
  if (code === "resume_binding_read_failed")
    return "简历已保存，暂时无法读取申请使用的资料，请稍后重试更换。";
  if (code === "resume_binding_conflict")
    return "简历已保存，但申请使用的资料已变化。请重新选择要使用的简历。";
  if (code === "resume_binding_unknown")
    return "简历已保存，替换结果尚未确认，请查看申请当前使用的简历。";
  if (value.state === "success" && value.decision?.action === "ask")
    return `${action}：新题已准备好。`;
  if (value.state === "success") return `${action}已完成`;
  if (value.state === "reused") return `${action}：已使用已有结果，未重新生成。`;
  if (
    ["unknown", "recovery_required"].includes(value.state) ||
    [
      "connection_interrupted",
      "execution_interrupted",
      "execution_outcome_unknown",
      "recovery_decision_required",
    ].includes(code)
  )
    return `${action}结果尚未确认，请稍后查看已保存结果；不要重复提交。`;
  if (value.state === "cancelled" || code === "execution_cancelled") return `${action}已停止。`;
  if (["resume_library_save_failed", "artifact_save_failed"].includes(code))
    return `${action}失败：生成结果未能保存，已生成内容保留，可重试保存。`;
  if (value.state === "awaiting_save") return `${action}内容已生成，待确认保存。`;
  if (
    [
      "product_input_too_large",
      "context_too_large",
      "debrief_input_too_large",
      "mock_input_too_large",
    ].includes(code)
  )
    return `${action}未开始：输入内容过长，请精简后重试。`;
  if (
    [
      "budget_exhausted",
      "call_budget_exhausted",
      "insufficient_token_budget",
      "session_budget_exhausted",
    ].includes(code)
  )
    return `${action}未能继续：当前生成预算不足。`;
  if (["operation_attempt_limit", "model_attempt_limit"].includes(code))
    return `${action}未能继续：本次任务已达到尝试次数上限。`;
  if (["provider_429", "provider_rate_limited", "rate_limit_exceeded"].includes(code))
    return `${action}失败：模型服务请求过多，请稍后重试。`;
  if (
    [
      "provider_timeout",
      "model_timeout",
      "request_timeout",
      "operation_timeout",
      "operation_deadline_exceeded",
    ].includes(code)
  )
    return `${action}请求超时，结果尚未确认，请先查看已保存结果。`;
  if (
    [
      "invalid_output",
      "output_schema_invalid",
      "schema_validation_failed",
      "structured_output_invalid",
      "output_validation_failed",
      "illegal_question_kind",
      "illegal_interview_finish",
      "invalid_interview_decision",
      "interview_output_guardrail_failed",
      "grounding_failed",
      "hard_field_mismatch",
      "invalid_reference",
      "requirement_coverage_invalid",
      "requirement_evidence_missing",
      "unsupported_requirement_inference",
      "missing_personal_evidence",
      "research_scope_invalid",
      "locale_invalid",
      "invalid_story_reference",
      "variant_identity_invalid",
      "layout_budget_exceeded",
      "unsupported_claim",
      "resume_claims_unsupported",
      "invalid_resume_source",
      "compression_not_shorter",
      "compression_required_changed",
    ].includes(code)
  )
    return `${action}失败：生成内容未通过校验。`;
  if (
    [
      "provider_error",
      "provider_5xx",
      "provider_rejected",
      "provider_incomplete",
      "provider_authentication_failed",
      "provider_permission_denied",
      "provider_model_unavailable",
    ].includes(code)
  )
    return `${action}失败：模型服务未能返回可用结果，请稍后重试。`;
  if (code === "provider_connection")
    return `${action}请求连接中断，结果尚未确认，请先查看已保存结果。`;
  if (code === "context_revision_mismatch")
    return `${action}未能继续：所选材料已变化，请重新打开结果后再操作。`;
  if (code === "feedback_required") return "请输入调整意见。";
  return `${action}未完成：暂时无法确认具体原因，请稍后查看任务结果。`;
}
