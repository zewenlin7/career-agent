"use client";
import { useState, useEffect, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { api, ApiError, useAction, useRequestId } from "./client";
import { control, ErrorNotice, Field } from "./ui";
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
  profileRevision,
  sourceArtifactId,
  feedbackId,
  applicationId,
  refinementIntent,
  label,
  fixedFeedback,
  autoStart = false,
  render,
  onSaved,
  onBusyChange,
}: {
  task: string;
  disabled?: boolean;
  profileId?: string;
  profileRevision?: number;
  sourceArtifactId?: string;
  feedbackId?: string;
  applicationId?: string;
  refinementIntent?: "refine" | "regenerate";
  label: string;
  fixedFeedback?: string;
  autoStart?: boolean;
  render: (output: Record<string, unknown>) => ReactNode;
  onSaved?: (draft: Draft) => void;
  onBusyChange?: (busy: boolean) => void;
}) {
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
    const timer = setInterval(() => {
      void api<Draft>(`product-drafts/${draft.id}`)
        .then(setDraft)
        .catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
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
      if (!["pending", "running", "recovery_required"].includes(result.status))
        setIntent((n) => n + 1);
    });
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
            placeholder="例如：突出项目中的测试与错误恢复，减少泛泛描述。"
          />
        </Field>
      )}
      <Button
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
      <ErrorNotice code={action.error || draft?.reason || undefined} />
      {draft?.output && (
        <div className="space-y-4 rounded-control border border-line p-4">
          {render(draft.output)}
          {!draft.adopted ? (
            <Button
              disabled={action.busy}
              variant="primary"
              onClick={() =>
                void action.run(async () => {
                  const saved = await api<Draft>(`product-drafts/${draft.id}/adopt`, "POST", {
                    expected_profile_revision: profileRevision ?? null,
                  });
                  setDraft(saved);
                  onSaved?.(saved);
                })
              }
            >
              {task === "profile_fact_extraction" ? "保存为待确认事实" : "保存"}
            </Button>
          ) : (
            <p className="text-sm">已保存。</p>
          )}
        </div>
      )}
    </div>
  );
}
