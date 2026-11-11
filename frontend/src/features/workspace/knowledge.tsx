"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { EntryMenu } from "../applications/entry-menu";
import { useConfirmation } from "../profile-area/confirmation";
import { formatTime } from "@/lib/date-time";
import type { Context, Knowledge, Page } from "./contracts";
import { api, ApiError, useAction, useRead } from "./client";
import { readHistory } from "./history";
import { reviewRequest } from "./review-request";
import { control, ErrorNotice, Field, ReadState } from "./ui";
export function KnowledgePage({ ctx }: { ctx: Context }) {
  const [editor, setEditor] = useState<{ note?: Knowledge; title: string; content: string }>();
  const [saved, setSaved] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  const rows = useRead<Page<Knowledge>>(
    `applications/${ctx.application.id}/knowledge-notes`,
    readHistory,
  );
  const action = useAction(),
    confirmation = useConfirmation();
  useEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height = `${Math.max(180, textarea.current.scrollHeight)}px`;
    }
  }, [editor?.content]);
  const dirty =
    !!editor &&
    (editor.title !== (editor.note?.title || "") ||
      editor.content !== (editor.note?.content || ""));
  return (
    <section className="min-w-0 space-y-6 text-base font-normal leading-relaxed [overflow-wrap:anywhere]">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold leading-8">求职笔记</h1>
        {!editor && <Button onClick={() => setEditor({ title: "", content: "" })}>新增笔记</Button>}
      </div>
      {editor ? (
        <form
          className="max-w-[760px] space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            const draft = editor;
            void action.run(async () => {
              const payload = {
                application_id: ctx.application.id,
                title: draft.title.trim(),
                content: draft.content.trim(),
              };
              if (!payload.title || !payload.content) throw new ApiError("note_content_required");
              const key = `knowledge-create:${ctx.application.id}`;
              const row = await api<Knowledge>(
                draft.note ? `knowledge-notes/${draft.note.id}` : "knowledge-notes",
                draft.note ? "PATCH" : "POST",
                {
                  ...payload,
                  ...(draft.note
                    ? { expected_revision: draft.note.revision }
                    : { request_id: await reviewRequest(key, payload) }),
                },
              );
              if (!draft.note) sessionStorage.removeItem(key);
              setSaved(row.id);
              setEditor(undefined);
              rows.reload();
            });
          }}
        >
          <fieldset disabled={action.busy} className="space-y-5">
            <Field label="笔记标题" labelClassName="text-base font-medium leading-relaxed">
              <input
                className={control.replace("text-sm", "text-base")}
                placeholder="输入笔记标题"
                value={editor.title}
                maxLength={200}
                required
                onChange={(e) => setEditor({ ...editor, title: e.target.value })}
              />
            </Field>
            <Field label="笔记内容" labelClassName="text-base font-medium leading-relaxed">
              <textarea
                ref={textarea}
                className={`${control.replace("text-sm", "text-base")} min-h-44 resize-y leading-relaxed`}
                placeholder="输入笔记内容"
                maxLength={20000}
                required
                value={editor.content}
                onChange={(e) => setEditor({ ...editor, content: e.target.value })}
              />
            </Field>
            <div className="flex flex-wrap gap-3">
              <Button type="submit" variant="primary">
                保存
              </Button>
              <Button
                onClick={() =>
                  void (async () => {
                    if (!dirty || (await confirmation.confirm("放弃尚未保存的修改？")))
                      setEditor(undefined);
                  })()
                }
              >
                取消
              </Button>
            </div>
          </fieldset>
        </form>
      ) : (
        <>
          <ReadState loaded={!!rows.data} error={rows.error} />
          {rows.data?.items.length === 0 && (
            <div>
              <p>还没有笔记</p>
              <p className="mt-2 text-secondary">记录求职过程中的收获和待补充的知识。</p>
            </div>
          )}
          <div className="w-full min-w-0 divide-y divide-line">
            {rows.data?.items.map((note) => (
              <article
                key={note.id}
                data-note-id={note.id}
                className="relative space-y-3 py-5 first:pt-0"
                aria-label={note.title}
              >
                <div className="flex w-full min-w-0 items-start justify-between gap-3">
                  <h2 className="min-w-0 flex-1 text-lg font-semibold">{note.title}</h2>
                  <EntryMenu label={`管理笔记：${note.title}`} persistent inline>
                    <button
                      role="menuitem"
                      className="w-full px-3 py-2 text-left"
                      disabled={action.busy}
                      onClick={() => setEditor({ note, title: note.title, content: note.content })}
                    >
                      编辑
                    </button>
                    <button
                      role="menuitem"
                      className="w-full px-3 py-2 text-left text-error"
                      disabled={action.busy}
                      onClick={() =>
                        void (async () => {
                          if (await confirmation.confirm("确定删除这条笔记吗？"))
                            await action.run(async () => {
                              await api(
                                `knowledge-notes/${note.id}?expected_revision=${note.revision}&application_id=${ctx.application.id}`,
                                "DELETE",
                              );
                              rows.reload();
                            });
                        })()
                      }
                    >
                      删除
                    </button>
                  </EntryMenu>
                </div>
                <p className="text-sm text-secondary">
                  {note.updated_at ? "修改于" : "创建于"}{" "}
                  {formatTime(note.updated_at || note.created_at)}
                </p>
                {saved === note.id && (
                  <span className="sr-only" role="status">
                    已保存
                  </span>
                )}

                <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{note.content}</p>
              </article>
            ))}
          </div>
        </>
      )}
      <ErrorNotice code={action.error} />
      {confirmation.confirmation}
    </section>
  );
}
