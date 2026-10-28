"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, useAction, ApiError } from "./client";
import type { Result } from "./contracts";
import type { ApplicationBinding } from "./application-binding";
import { DraftAction } from "./draft-action";
import { ResultContent } from "./results";
import { ErrorNotice, Field, control } from "./ui";
export function ResultActions({
  result,
  applicationId,
  onSaved,
}: {
  result: Result;
  applicationId?: string;
  onSaved?: () => void;
}) {
  const [adjusting, setAdjusting] = useState<"adjust" | "regenerate" | null>(null),
    [saved, setSaved] = useState(false),
    [vote, setVote] = useState(""),
    [feedbackId, setFeedbackId] = useState<string>(),
    [negative, setNegative] = useState(false),
    [comment, setComment] = useState("");
  const [draftBusy, setDraftBusy] = useState(false);
  const [generation, setGeneration] = useState(0);
  const action = useAction();
  const recordVote = (v: string) =>
    action.run(async () => {
      const saved = await api<{ id: string }>("evaluation/feedback", "POST", {
        subject: result.feedback_target,
        vote: v,
        application_id: applicationId || null,
        comment: comment.trim() || null,
      });
      setVote(v);
      setFeedbackId(saved.id);
      setNegative(false);
    });
  const saveResume = (id: string) =>
    action.run(async () => {
      await api(`resume-revisions/${id}/save`, "POST", {});
      setSaved(true);
      if (
        applicationId &&
        window.confirm("已保存到简历库。是否将此申请当前使用的简历切换为这一版？")
      ) {
        const binding = await api<ApplicationBinding>(`applications/${applicationId}/context`);
        if (binding.profile_id !== result.context.profile_id)
          throw new ApiError("context_revision_mismatch");
        await api(`applications/${applicationId}/context`, "PUT", {
          expected_revision: binding.revision,
          profile_id: binding.profile_id,
          job_revision_id: binding.job_revision_id,
          resume_revision_id: id,
        });
      }
      onSaved?.();
    });
  const tasks = {
    resume_tailoring: "resume_refinement",
    greeting_generation: "greeting_refinement",
    interview_preparation: "interview_preparation_refinement",
  };
  const task = tasks[result.kind as keyof typeof tasks];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        {result.resume_revision_id && (
          <Button
            disabled={action.busy || draftBusy || saved}
            onClick={() => void saveResume(result.resume_revision_id!)}
          >
            {saved ? "已保存" : "保存到简历库"}
          </Button>
        )}
        {task && (
          <Button
            disabled={action.busy || draftBusy}
            onClick={() => setAdjusting(adjusting ? null : "adjust")}
          >
            {adjusting ? "取消调整" : "调整"}
          </Button>
        )}
        {task && (
          <Button
            disabled={action.busy || draftBusy}
            onClick={() => {
              setGeneration((n) => n + 1);
              setAdjusting("regenerate");
            }}
          >
            重新生成
          </Button>
        )}
        {result.feedback_target &&
          ["thumbs_up", "thumbs_down"].map((v) => (
            <Button
              key={v}
              disabled={action.busy || !!vote}
              aria-label={v === "thumbs_up" ? "有帮助" : "不满意"}
              onClick={() => {
                if (v === "thumbs_down") setNegative(!negative);
                else void recordVote(v);
              }}
            >
              {v === "thumbs_up" ? "👍" : "👎"}
            </Button>
          ))}
      </div>
      {negative && (
        <div className="space-y-3">
          <Field label="意见（选填）">
            <textarea
              className={control}
              maxLength={4000}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </Field>
          <div className="flex gap-2">
            <Button disabled={action.busy} onClick={() => void recordVote("thumbs_down")}>
              保存
            </Button>
            <Button onClick={() => setNegative(false)}>取消</Button>
          </div>
        </div>
      )}
      <ErrorNotice code={action.error} />
      {adjusting && task && result.target_artifact_id && (
        <DraftAction
          key={`${adjusting}:${generation}`}
          onBusyChange={setDraftBusy}
          task={task}
          disabled={action.busy}
          autoStart={adjusting === "regenerate"}
          fixedFeedback={
            adjusting === "regenerate"
              ? "保持已确认事实与原任务范围不变，重新组织表达，生成另一版供我审核。"
              : undefined
          }
          sourceArtifactId={result.target_artifact_id}
          feedbackId={feedbackId}
          applicationId={applicationId}
          refinementIntent={adjusting === "regenerate" ? "regenerate" : "refine"}
          label="根据意见调整"
          render={(output) => <ResultContent result={{ ...result, content: output }} />}
          onSaved={(draft) => {
            const id = draft.adopted?.resume_revision_id;
            if (typeof id === "string") void saveResume(id);
            else onSaved?.();
          }}
        />
      )}
    </div>
  );
}
