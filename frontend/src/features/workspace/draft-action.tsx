"use client";
import { useState, useEffect, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { api, ApiError, useAction, useRequestId } from "./client";
import { control, Field } from "./ui";
import { taskMessage } from "./task-feedback";
import { visibleTaskErrors, taskChange } from "./task-tracker";
export type Draft = {
  id: string;
  status: string;
  reason: string | null;
  output: Record<string, unknown> | null;
  adopted: Record<string, string | string[]> | null;
};
export function DraftAction({
  task,
  disabled = false,
  profileId,
  sourceArtifactId,
  feedbackId,
  applicationId,
  refinementIntent,
  label,
  fixedFeedback,
  autoStart = false,
  autoAdopt = false,
  render,
  onSaved,
  onBusyChange,
}: {
  task: string;
  disabled?: boolean;
  profileId?: string;
  sourceArtifactId?: string;
  feedbackId?: string;
  applicationId?: string;
  refinementIntent?: "refine" | "regenerate";
  label: string;
  fixedFeedback?: string;
  autoStart?: boolean;
  autoAdopt?: boolean;
  render: (output: Record<string, unknown>) => ReactNode;
  onSaved?: (draft: Draft) => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const [feedback, setFeedback] = useState(fixedFeedback || "");
  const [draft, setDraft] = useState<Draft>();
  const [intent, setIntent] = useState(0);
  const action = useAction(),
    requestId = useRequestId();
  useEffect(() => {
    onBusyChange?.(action.busy || draft?.status === "running");
    return () => onBusyChange?.(false);
  }, [action.busy, draft?.status, onBusyChange]);
  const storageKey = `product-draft:${task}:${profileId || sourceArtifactId || ""}:${refinementIntent || "refine"}:${feedbackId || ""}`;
  useEffect(() => {
    let active = true;
    const id = autoStart ? null : sessionStorage.getItem(storageKey);
    if (id && /^[0-9a-f-]{36}$/.test(id))
      void api<Draft>(`product-drafts/${id}`)
        .then((value) => {
          if (active) setDraft(value);
        })
        .catch(() => {});
    return () => {
      active = false;
    };
  }, [storageKey, autoStart]);
  useEffect(() => {
    if (draft?.status !== "running") return;
    let active = true;
    const timer = setInterval(() => {
      void api<Draft>(`product-drafts/${draft.id}`)
        .then((value) => {
          if (active) setDraft(value);
        })
        .catch(() => {});
    }, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [draft?.id, draft?.status]);
  const start = () =>
    action.run(async () => {
      if (sourceArtifactId && !feedback.trim()) throw new ApiError("feedback_required");
      const body = {
        task,
        profile_id: profileId || null,
        source_artifact_id: sourceArtifactId || null,
        feedback: feedback.trim() || null,
        feedback_id: feedbackId || null,
        application_id: applicationId || null,
        intent: refinementIntent || "refine",
        mode: "live",
      };
      let result = await api<Draft>("product-drafts", "POST", {
        ...body,
        request_id: requestId({ generation: intent, ...body }),
      });
      setDraft(result);
      sessionStorage.setItem(storageKey, result.id);
      if (result.status === "pending") {
        result = await api<Draft>(`product-drafts/${result.id}/execute`, "POST", {});
        setDraft(result);
      }
      if (mounted.current && autoAdopt && result.adopted) onSaved?.(result);
      if (!["pending", "running", "recovery_required"].includes(result.status))
        setIntent((n) => n + 1);
    });
  const error = !action.busy ? action.error || draft?.reason : undefined;
  const actionName =
    task === "resume_refinement"
      ? refinementIntent === "regenerate"
        ? "简历重新生成"
        : "简历调整"
      : task === "greeting_refinement"
        ? refinementIntent === "regenerate"
          ? "招呼语重新生成"
          : "招呼语调整"
        : task === "interview_preparation_refinement"
          ? refinementIntent === "regenerate"
            ? "面试准备重新生成"
            : "面试准备调整"
          : label;
  useEffect(() => {
    if (!error || !draft?.id) return;
    const key = `product-drafts:${draft.id}`;
    visibleTaskErrors.add(key);
    window.dispatchEvent(new Event(taskChange));
    return () => {
      visibleTaskErrors.delete(key);
    };
  }, [error, draft?.id]);
  const started = useRef(false);
  useEffect(() => {
    if (autoStart && !started.current && !disabled) {
      started.current = true;
      void start();
    }
  });
  return (
    <div className="space-y-3">
      {sourceArtifactId && !fixedFeedback && (
        <Field label="告诉 AI 你想怎么调整">
          <textarea
            className={control}
            maxLength={20000}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="输入调整意见"
          />
        </Field>
      )}
      {!autoStart && (
        <div className="flex justify-center">
          <Button
            variant="primary"
            disabled={
              disabled ||
              action.busy ||
              draft?.status === "running" ||
              draft?.status === "recovery_required"
            }
            onClick={() => void start()}
          >
            {action.busy || draft?.status === "running" ? "正在生成…" : label}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-base text-error">
          {taskMessage(actionName, {
            state: draft?.status === "recovery_required" ? "unknown" : "failure",
            reason: error,
          })}
        </p>
      )}
      {draft?.output && !(autoAdopt && draft.adopted) && (
        <div className="space-y-4 rounded-control border border-line p-4">
          {render(draft.output)}
          {!draft.adopted ? (
            <Button
              disabled={action.busy}
              variant="primary"
              onClick={() =>
                void action.run(async () => {
                  const saved = await api<Draft>(`product-drafts/${draft.id}/adopt`, "POST", {});
                  setDraft(saved);
                  onSaved?.(saved);
                })
              }
            >
              {autoAdopt ? "重试保存" : "保存"}
            </Button>
          ) : (
            <p className="text-sm">已保存。</p>
          )}
        </div>
      )}
    </div>
  );
}
