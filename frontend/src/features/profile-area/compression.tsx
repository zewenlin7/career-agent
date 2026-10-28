"use client";
import { Button } from "@/components/ui/button";
import { api, ApiError, useAction, useRequestId } from "../workspace/client";
import type { Draft } from "../workspace/draft-action";
import type { ResumeSection } from "../onboarding/contracts";
import { InlineError } from "./common";

export function Compression({
  resumeId,
  workspaceId,
  onReady,
}: {
  sections: ResumeSection[];
  resumeId?: string;
  workspaceId?: string;
  onReady: (sections: ResumeSection[], generationId: string, generatedIds: string[]) => void;
}) {
  const action = useAction(),
    requestId = useRequestId();
  return (
    <div>
      <Button
        disabled={action.busy}
        onClick={() =>
          void action.run(async () => {
            const body = {
              task: "resume_library_compression",
              source_resume_revision_id: resumeId || null,
              source_workspace_id: workspaceId || null,
              mode: "live",
            };
            const created = await api<Draft>("product-drafts", "POST", {
              ...body,
              request_id: requestId(body),
            });
            const result = await api<Draft>(`product-drafts/${created.id}/execute`, "POST", {});
            if (result.status !== "completed")
              throw new ApiError(result.reason || "generation_failed");
            const saved = await api<Draft>(`product-drafts/${created.id}/adopt`, "POST", {});
            const proposal = saved.adopted?.resume_edit as
              | {
                  document?: { sections: ResumeSection[] };
                  generation_id?: string;
                  generated_item_ids?: string[];
                }
              | undefined;
            if (!proposal?.document || !proposal.generation_id)
              throw new ApiError("generation_failed");
            onReady(
              proposal.document.sections,
              proposal.generation_id,
              proposal.generated_item_ids || [],
            );
          })
        }
      >
        {action.busy ? "正在精简…" : "AI 精简"}
      </Button>
      <InlineError
        code={action.error}
        message={
          action.error === "compression_not_needed"
            ? "没有需要生成精简表达的内容。"
            : action.error === "grounding_failed"
              ? "精简结果包含原文未支持的数字，未保存。请重试或手动精简。"
              : undefined
        }
      />
    </div>
  );
}
