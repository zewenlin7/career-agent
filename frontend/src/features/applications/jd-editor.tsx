"use client";
import { useState, useLayoutEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { api, useAction, useRead } from "@/features/workspace/client";
import { formatTime } from "@/lib/date-time";
import { control } from "@/features/workspace/ui";
import { errorText } from "@/features/workspace/contracts";
import type { ApplicationBinding } from "@/features/workspace/application-binding";
export function JDEditor({
  applicationId,
  revision,
  revisionId,
  text,
}: {
  applicationId: string;
  revision: number;
  revisionId: string;
  text: string;
}) {
  const saved = useRead<{ created_at: string }>(`job-revisions/${revisionId}`);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [editing, setEditing] = useState(false),
    [draft, setDraft] = useState(text),
    [baseRevision, setBaseRevision] = useState(revision),
    [bindingRevision, setBindingRevision] = useState<number>();
  const action = useAction(),
    router = useRouter();
  const [error, setError] = useState("");
  useLayoutEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height = `${textarea.current.scrollHeight + 2}px`;
    }
  }, [editing, draft]);
  return (
    <div className="w-full">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">职位描述</h1>
        {!editing && (
          <Button
            disabled={action.busy}
            onClick={() => {
              setBaseRevision(revision);
              setDraft(text);
              setError("");
              setEditing(true);
              setBindingRevision(undefined);
              void action.run(async () => {
                const b = await api<ApplicationBinding>(`applications/${applicationId}/context`);
                setBindingRevision(b.revision);
              });
            }}
          >
            编辑
          </Button>
        )}
      </div>
      {saved.data?.created_at && (
        <p className="mt-2 text-sm text-secondary">
          <time dateTime={saved.data.created_at}>{formatTime(saved.data.created_at)}</time>
        </p>
      )}
      {editing ? (
        <form
          className="mt-3 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!draft.trim()) {
              setError("请输入职位描述。");
              return;
            }
            void action.run(async () => {
              await api(`applications/${applicationId}/jd`, "PUT", {
                expected_revision: baseRevision,
                expected_binding_revision: bindingRevision,
                jd_text: draft,
              });
              setEditing(false);
              router.refresh();
            });
          }}
        >
          <div>
            <textarea
              ref={textarea}
              aria-label="职位描述"
              className={`${control} !text-base !font-normal !leading-relaxed resize-none overflow-hidden`}
              rows={1}
              maxLength={20000}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setError("");
              }}
            />
          </div>
          {(error || action.error) && (
            <p role="alert" className="text-sm text-error">
              {error ||
                (action.error?.includes("revision")
                  ? "资料已被修改，请保留输入，取消后重新打开编辑再核对。"
                  : errorText(action.error!))}
            </p>
          )}
          <div className="flex gap-3">
            <Button
              type="submit"
              disabled={
                action.busy || bindingRevision === undefined || draft.trim() === text.trim()
              }
            >
              保存
            </Button>
            <Button
              disabled={action.busy}
              onClick={() => {
                setBaseRevision(revision);
                setDraft(text);
                setEditing(false);
              }}
            >
              取消
            </Button>
          </div>
        </form>
      ) : (
        <p className="mt-3 whitespace-pre-wrap break-words px-3 py-2 text-base font-normal leading-relaxed">
          {text}
        </p>
      )}
    </div>
  );
}
