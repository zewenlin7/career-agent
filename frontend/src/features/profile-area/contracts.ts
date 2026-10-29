import type {
  ProfileData as LegacyData,
  Experience as LegacyEntry,
  ResumeSection,
} from "../onboarding/contracts";
export type Entry = LegacyEntry & {
  entry_id?: string;
  degree?: string;
  major?: string;
  start_date?: string;
  end_date?: string;
  achievements?: string;
  technology_stack?: string;
  hidden_fields?: string[];
};
export type Personal = {
  phone: string;
  email: string;
  city: string;
  github: string;
  website: string;
  other_contact: string;
  photo_id: string | null;
};
export type Data = Omit<LegacyData, "education" | "experiences" | "projects"> & {
  personal: Personal;
  education: Entry[];
  experiences: Entry[];
  projects: Entry[];
  skills_text: string;
  fact_ids: string[];
};
export type Section =
  "personal" | "education" | "experiences" | "projects" | "skills" | "preferences";
export type Workspace = {
  revision: number;
  base_profile_id: string | null;
  current_profile_id: string | null;
  data: Data;
  section_revisions: Record<Section, number>;
};
export type Snapshot = { id: string; revision: number; created_at: string; data: Data };
export type Presentation = {
  hidden_sections: string[];
  hidden_item_ids?: string[];
  item_order?: string[];
  compact_item_ids?: string[];
  experience_order: "work_first" | "projects_first";
};
export type Draft = {
  entry_id?: string;
  saved_at?: string | null;
  presentation?: Presentation;
  profile_id?: string;
  id: string;
  revision: number;
  name: string;
  created_at: string;
  display_name: string;
  personal: Personal;
  document: { sections: ResumeSection[] };
  accepted_revision_id: string | null;
  source_resume_revision_id?: string | null;
};
export type Version = {
  entry_id?: string;
  saved_at?: string | null;
  presentation?: Presentation;
  id: string;
  variant_id: string;
  revision: number;
  name: string;
  metadata_revision: number;
  created_at: string;
  profile_id: string;
};
export const personalFields = [
  ["display_name", "姓名", "例如：林晓", true],
  ["phone", "手机号", "例如：13800000000", false],
  ["email", "邮箱", "例如：name@example.com", false],
  ["city", "所在城市", "例如：上海", false],
  ["github", "GitHub 地址", "例如：github.com/your-name", false],
  ["website", "个人主页或作品集", "例如：https://example.com", false],
  ["other_contact", "其他联系方式", "例如：微信号", false],
] as const;
export const entryFields = {
  education: [
    ["organization", "学校名称", "例如：上海交通大学", true],
    ["degree", "学历", "例如：本科", false],
    ["major", "专业", "例如：计算机科学与技术", false],
    ["start_date", "入学时间", "", false],
    ["end_date", "毕业时间", "", false],
    ["description", "经历描述与荣誉", "例如：奖学金、课程或补充信息", false],
  ],
  experiences: [
    ["organization", "单位名称", "例如：某科技公司", true],
    ["role", "职位", "例如：后端开发工程师", false],
    ["start_date", "开始时间", "", false],
    ["end_date", "结束时间", "", false],
    ["description", "工作内容", "例如：负责服务端开发与系统维护", false],
    ["achievements", "工作成果", "例如：完成服务迁移和测试建设", false],
  ],
  projects: [
    ["organization", "项目名称", "例如：求职助手", true],
    ["role", "项目角色", "例如：独立开发者", false],
    ["start_date", "开始时间", "", false],
    ["end_date", "结束时间", "", false],
    ["technology_stack", "技术栈", "例如：Python、FastAPI、PostgreSQL", false],
    ["description", "项目描述", "例如：负责检索、重排及回答评估模块", false],
    ["achievements", "主要成果", "例如：完成端到端流程与回归测试", false],
  ],
} as const;
export const preferenceFields = [
  ["expected_role", "期望职位"],
  ["expected_city", "期望城市"],
  ["expected_salary", "期望薪资"],
  ["work_mode", "工作方式"],
  ["industry", "行业方向"],
  ["other", "其他求职偏好"],
] as const;
export function errorMessage(code?: string) {
  if (!code) return "";
  return (
    (
      {
        revision_conflict: "内容已在别处更新。请重新加载后再保存，当前输入仍保留。",
        profile_workspace_outdated: "资料已更新，请重新加载后继续编辑。",
        profile_in_use: "这份资料正被申请使用，请先在申请概览中更换资料。",
        resume_in_use: "这份简历正被申请使用，请先在申请概览中更换简历。",
        resume_draft_needs_review: "部分内容需要确认，请检查后重试。",
        resume_content_required: "请先填写简历内容。",
        debrief_input_too_large: "资料内容较长，请缩短描述或分段优化。",
        invalid_resume_source: "AI 未正确保留资料来源，请重新生成。",
        structured_output_invalid: "AI 返回的内容格式不完整，请重试。",
        compression_not_shorter: "AI 精简改动了原文或关键数字，结果未保存。请重试或手动精简。",
        provider_connection: "暂时无法连接 AI 服务，请稍后重试。",
        resume_source_required: "新增经历请先添加到个人资料。",
        grounding_failed: "部分内容尚无可靠依据，请确认或调整后重试。",
        invalid_photo: "请选择有效的 JPG、PNG 或 WebP 照片。",
        photo_too_large: "照片不能超过 5 MB。",
        profile_name_required: "请先填写姓名。",
        invalid_profile_date: "请使用 YYYY-MM 格式填写年月。",
        invalid_profile_section: "请检查本区块的必填项和输入长度。",
        connection_interrupted: "连接中断，输入已保留。请重新加载确认保存结果。",
      } as Record<string, string>
    )[code] || "未能完成操作，请检查输入后重试。"
  );
}
