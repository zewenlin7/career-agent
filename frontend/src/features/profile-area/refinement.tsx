"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, ApiError, useAction, useRequestId } from "../workspace/client";
import { Field, control } from "../workspace/ui";
import { InlineError } from "./common";
import type { Draft } from "../workspace/draft-action";

export function ResumeRefinement({
  id,
  workspace = false,
  onSaved,
  disabled = false,
  onToggle,
}: {
  id: string;
  workspace?: boolean;
  onSaved: (id: string) => void | Promise<void>;
  disabled?: boolean;
  onToggle?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false),
    [instruction, setInstruction] = useState("");
  const action = useAction(),
    requestId = useRequestId();
  return (
    <div className="space-y-3">
      {!open && (
        <div className="flex gap-3">
          <Button
            disabled={disabled || action.busy}
            onClick={() => {
              setOpen(true);
              onToggle?.(true);
            }}
          >
            AI 优化
          </Button>
        </div>
      )}
      {open && (
        <div className="space-y-3">
          <Field label="你希望怎么优化？">
            <textarea
              className={`${control} font-normal`}
              rows={3}
              disabled={action.busy}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
          </Field>
          <Button
            disabled={disabled || action.busy || !instruction.trim()}
            onClick={() =>
              void action.run(async () => {
                const body = {
                  task: "resume_refinement",
                  source_workspace_id: workspace ? id : null,
                  source_resume_revision_id: workspace ? null : id,
                  feedback: instruction.trim(),
                  feedback_id: null,
                  mode: "live",
                };
                let result = await api<Draft>("product-drafts", "POST", {
                  ...body,
                  request_id: requestId(body),
                });
                result = await api<Draft>(`product-drafts/${result.id}/execute`, "POST");
                if (result.status !== "completed")
                  throw new ApiError(result.reason || "generation_failed");
                result = await api<Draft>(`product-drafts/${result.id}/adopt`, "POST", {});
                const revision = result.adopted?.resume_revision_id;
                if (typeof revision !== "string") throw new ApiError("generation_failed");
                await onSaved(revision);
              })
            }
          >
            {action.busy ? "正在优化…" : "优化"}
          </Button>
          <Button
            disabled={action.busy}
            onClick={() => {
              setOpen(false);
              onToggle?.(false);
            }}
          >
            取消
          </Button>
        </div>
      )}
      <InlineError code={action.error} />
    </div>
  );
}
