"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, useAction, useRequestId } from "../workspace/client";
import type { Draft } from "../workspace/draft-action";
import { ResumeContent } from "../workspace/results";
import { InlineError } from "./common";
export function Generation({
  profileId,
  onSaved,
}: {
  profileId: string;
  onSaved: (id: string) => void;
}) {
  const [draft, setDraft] = useState<Draft>(),
    [intent, setIntent] = useState(0);
  const action = useAction(),
    requestId = useRequestId();
  return (
    <div className="space-y-4">
      <Button
        disabled={action.busy}
        onClick={() =>
          void action.run(async () => {
            const created = await api<Draft>("product-drafts", "POST", {
              request_id: requestId({ profileId, intent }),
              task: "base_resume_drafting",
              profile_id: profileId,
              mode: "live",
            });
            setDraft(created);
            const result = await api<Draft>(`product-drafts/${created.id}/execute`, "POST", {});
            setDraft(result);
            if (["completed", "failed", "cancelled"].includes(result.status)) setIntent(intent + 1);
          })
        }
      >
        {action.busy ? "正在生成…" : "生成"}
      </Button>
      <InlineError code={action.error || draft?.reason || undefined} />
      {draft?.output && (
        <>
          <ResumeContent content={draft.output} />
          <Button
            disabled={action.busy || !!draft.adopted}
            onClick={() =>
              void action.run(async () => {
                const result = await api<Draft>(`product-drafts/${draft.id}/adopt`, "POST", {});
                setDraft(result);
                onSaved(String(result.adopted?.resume_workspace_id || ""));
              })
            }
          >
            保存
          </Button>
        </>
      )}
    </div>
  );
}
