"use client";
import { savedResumes } from "./library";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, useRead } from "../workspace/client";
import { control, Field } from "../workspace/ui";
import type { Draft } from "../workspace/draft-action";
import type { NamedProfile } from "./personal";
import type { Draft as ResumeDraft, Version } from "./contracts";
import { InlineError } from "./common";
type Candidate = { statement: string; section: string };
async function resumeSources(_path: string, signal: AbortSignal) {
  const items: Version[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await api<{ items: Version[]; has_more: boolean }>(
      `resume-library/versions?limit=100&offset=${offset}`,
      "GET",
      undefined,
      signal,
    );
    items.push(...page.items);
    if (!page.has_more) return { items };
  }
}

export function Extraction({ onAdded, existing }: { onAdded: () => void; existing: string[] }) {
  const [open, setOpen] = useState(false),
    [source, setSource] = useState("profile"),
    [choice, setChoice] = useState("");
  const [draft, setDraft] = useState<Draft>(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string>(),
    [selected, setSelected] = useState<number[]>([]),
    [notice, setNotice] = useState("");
  const profiles = useRead<{ items: NamedProfile[] }>("profile-library"),
    resumes = useRead<{ items: Version[] }>("resume-library/versions?limit=100", resumeSources),
    workspaces = useRead<ResumeDraft[]>("resume-workspaces", savedResumes);
  async function start() {
    if (busy || !choice) return;
    setBusy(true);
    setError(undefined);
    setNotice("");
    setDraft(undefined);
    try {
      const value = await api<Draft>("product-drafts", "POST", {
        request_id: crypto.randomUUID(),
        task: "profile_fact_extraction",
        mode: "live",
        profile_id: source === "profile" ? choice : null,
        source_resume_revision_id:
          source === "resume" && !choice.startsWith("workspace:") ? choice : null,
        source_workspace_id:
          source === "resume" && choice.startsWith("workspace:") ? choice.slice(10) : null,
      });
      setDraft(value);
      const result = await api<Draft>(`product-drafts/${value.id}/execute`, "POST", {});
      setDraft(result);
      setSelected([]);
    } catch {
      setError("request_failed");
    } finally {
      setBusy(false);
    }
  }
  const rows = (draft?.output?.facts || []) as Candidate[];
  return (
    <div>
      <Button onClick={() => setOpen(!open)}>提取</Button>
      <section
        hidden={!open}
        aria-label="提取事实"
        className="mt-4 space-y-4 border-y border-line py-4"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-medium">提取事实</h2>
          <button aria-label="收起提取" onClick={() => setOpen(false)}>
            ×
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="来源">
            <select
              disabled={busy}
              className={control}
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setChoice("");
                setDraft(undefined);
                setSelected([]);
              }}
            >
              <option value="profile">个人资料</option>
              <option value="resume">简历</option>
            </select>
          </Field>
          <Field label={source === "profile" ? "个人资料" : "简历"}>
            <select
              disabled={busy}
              className={control}
              value={choice}
              onChange={(e) => {
                setChoice(e.target.value);
                setDraft(undefined);
                setSelected([]);
              }}
            >
              <option value="">请选择</option>
              {source === "profile"
                ? profiles.data?.items
                    .filter((p) => p.profile_id)
                    .map((p) => (
                      <option key={p.id} value={p.profile_id!}>
                        {p.name}
                      </option>
                    ))
                : [
                    ...(workspaces.data || [])
                      .filter((r) => !r.accepted_revision_id)
                      .map((r) => ({ id: `workspace:${r.id}`, name: r.name })),
                    ...(resumes.data?.items || []),
                  ].map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
            </select>
          </Field>
        </div>
        <p className="text-sm text-secondary">此操作会使用 AI。</p>
        {busy ? (
          <div className="flex items-center gap-3">
            <span>正在提取…</span>
            <Button
              disabled={!draft}
              onClick={() => {
                if (draft)
                  void api<Draft>(`product-drafts/${draft.id}/cancel`, "POST", {})
                    .then(setDraft)
                    .catch(() => setError("request_failed"));
              }}
            >
              停止
            </Button>
          </div>
        ) : (
          <Button disabled={!choice} onClick={() => void start()}>
            开始
          </Button>
        )}
        {draft?.status === "cancelled" && <p role="status">已停止</p>}
        <InlineError
          code={error || (draft?.status !== "cancelled" ? draft?.reason || undefined : undefined)}
        />
        {!!rows.length && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    <th className="p-2">选择</th>
                    <th>内容</th>
                    <th>类别</th>
                    <th>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-t border-line">
                      <td className="p-2">
                        <input
                          type="checkbox"
                          aria-label={`选择候选 ${i + 1}`}
                          checked={selected.includes(i)}
                          onChange={(e) =>
                            setSelected(
                              e.target.checked ? [...selected, i] : selected.filter((x) => x !== i),
                            )
                          }
                        />
                      </td>
                      <td className="py-3">
                        {r.statement}
                        {existing.includes(r.statement) && (
                          <span className="ml-2 text-secondary">已存在</span>
                        )}
                      </td>
                      <td>
                        {r.section === "education"
                          ? "教育"
                          : r.section === "experiences"
                            ? "工作"
                            : r.section === "skills"
                              ? "技能"
                              : r.section === "summary"
                                ? "其他"
                                : "项目"}
                      </td>
                      <td>{source === "profile" ? "个人资料提取" : "简历提取"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Button
              disabled={!selected.length || !!draft?.adopted || busy}
              onClick={() => {
                if (!draft) return;
                setBusy(true);
                void api<Draft>(`product-drafts/${draft.id}/adopt`, "POST", {
                  selected_indices: selected,
                })
                  .then((r) => {
                    setDraft(r);
                    setNotice(
                      Array.isArray(r.adopted?.existing_fact_ids) &&
                        r.adopted.existing_fact_ids.length
                        ? "已添加；已有相同内容未重复添加。"
                        : "已添加",
                    );
                    onAdded();
                  })
                  .catch(() => setError("request_failed"))
                  .finally(() => setBusy(false));
              }}
            >
              添加
            </Button>
          </>
        )}
        {notice && <p role="status">{notice}</p>}
      </section>
    </div>
  );
}
