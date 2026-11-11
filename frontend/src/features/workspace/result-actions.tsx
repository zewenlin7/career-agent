"use client";
import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { useConfirmation } from "../profile-area/confirmation";
import { useResumeReplacement } from "./resume-replacement";
import { api, useAction, useRequestId } from "./client";
import type { Result } from "./contracts";
import { DraftAction } from "./draft-action";
import { taskMessage } from "./task-feedback";
import { ResultContent } from "./results";
import { ErrorNotice, Field, control } from "./ui";
export function ResultActions({
  result,
  applicationId,
  onSaved,
  disabled = false,
  onBusyChange,
}: {
  disabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
  result: Result;
  applicationId?: string;
  onSaved?: () => void;
}) {
  const [adjusting, setAdjusting] = useState<"adjust" | "regenerate" | null>(null),
    [vote, setVote] = useState(""),
    [feedbackId, setFeedbackId] = useState<string>(),
    [negative, setNegative] = useState(false),
    [comment, setComment] = useState("");
  const [draftBusy, setDraftBusy] = useState(false);
  const [generation, setGeneration] = useState(0);
  const action = useAction();
  const requestId = useRequestId();
  const confirmation = useConfirmation();
  const [deletionMessage, setDeletionMessage] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    onBusyChange?.(draftBusy);
    return () => onBusyChange?.(false);
  }, [draftBusy, onBusyChange]);
  const remove = () =>
    action.run(async () => {
      const path = `applications/${applicationId}/greetings/${result.target_artifact_id}`;
      const showUsed = (numbers: number[]) =>
        setDeletionMessage(`已在第 ${numbers.join("、")} 次投递中使用此招呼语，无法删除`);
      const state = await api<{ used_in: number[] }>(path);
      if (state.used_in.length) return showUsed(state.used_in);
      if (!(await confirmation.confirm("确定删除这条招呼语吗？"))) return;
      const deleted = await api<{ deleted: boolean; used_in: number[] }>(path, "DELETE", {
        request_id: requestId({ remove: result.target_artifact_id }),
      });
      if (!deleted.deleted) return showUsed(deleted.used_in);
      if (!mounted.current) return;
      onSaved?.();
      window.history.replaceState(null, "", location.pathname);
    });
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
  const replacement = useResumeReplacement(applicationId);
  const tasks = {
    resume_tailoring: "resume_refinement",
    greeting_generation: "greeting_refinement",
    interview_preparation: "interview_preparation_refinement",
  };
  const task = tasks[result.kind as keyof typeof tasks];
  return (
    <div className="space-y-3">
      {replacement.confirmation}
      {confirmation.confirmation}
      <div className="flex flex-wrap gap-3">
        {result.kind === "greeting_generation" && applicationId && (
          <Button disabled={disabled || action.busy || draftBusy} onClick={() => void remove()}>
            删除
          </Button>
        )}
        {task && (
          <Button
            disabled={disabled || action.busy || draftBusy}
            onClick={() => setAdjusting(adjusting ? null : "adjust")}
          >
            {adjusting ? "取消调整" : "调整"}
          </Button>
        )}
        {task && (
          <Button
            variant="primary"
            disabled={disabled || action.busy || draftBusy}
            onClick={() => {
              setDraftBusy(true);
              setGeneration((n) => n + 1);
              setAdjusting("regenerate");
            }}
          >
            {draftBusy && adjusting === "regenerate" ? "正在生成…" : "重新生成"}
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
      {deletionMessage && (
        <p role="alert" className="text-sm text-error">
          {deletionMessage}
        </p>
      )}
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
      {action.error?.startsWith("resume_binding_") ? (
        <p role="alert" className="text-base text-error">
          {taskMessage("简历优化", { state: "failure", reason: action.error })}
        </p>
      ) : (
        <ErrorNotice code={action.error} />
      )}
      {adjusting && task && result.target_artifact_id && (
        <DraftAction
          key={`${adjusting}:${generation}`}
          onBusyChange={setDraftBusy}
          task={task}
          disabled={disabled || action.busy}
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
          label="开始调整"
          autoAdopt={true}
          render={(output) => <ResultContent result={{ ...result, content: output }} />}
          onSaved={(draft) => {
            void action.run(async () => {
              const id = draft.adopted?.resume_revision_id;
              if (typeof id === "string") await replacement.offer(id);
              if (!mounted.current) return;
              onSaved?.();
              const target = draft.adopted?.target_artifact_id;
              if (typeof target === "string")
                window.history.replaceState(null, "", `${location.pathname}?result=${target}`);
            });
          }}
        />
      )}
    </div>
  );
}
