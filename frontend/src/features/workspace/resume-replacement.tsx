"use client";
import { useConfirmation } from "../profile-area/confirmation";
import { api, ApiError } from "./client";
import type { ApplicationBinding } from "./application-binding";

export function useResumeReplacement(applicationId?: string) {
  const confirmation = useConfirmation("确认替换", "取消替换", "替换当前申请简历？");
  return {
    confirmation: confirmation.confirmation,
    offer: async (resumeId: string) => {
      if (!applicationId) return;
      let binding: ApplicationBinding;
      try {
        binding = await api<ApplicationBinding>(`applications/${applicationId}/context`);
      } catch {
        throw new ApiError("resume_binding_read_failed");
      }
      if (
        await confirmation.confirm("优化简历已保存到简历库，是否将当前申请使用的简历替换为这一份？")
      ) {
        try {
          await api(`applications/${applicationId}/context`, "PUT", {
            expected_revision: binding.revision,
            profile_id: null,
            job_revision_id: binding.job_revision_id,
            resume_revision_id: resumeId,
          });
        } catch (error) {
          throw new ApiError(
            error instanceof ApiError && /revision|conflict|stale/.test(error.code)
              ? "resume_binding_conflict"
              : "resume_binding_unknown",
          );
        }
      }
    },
  };
}
