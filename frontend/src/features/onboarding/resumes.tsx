"use client";
import { canonical, draftFromProfile } from "./drafts";
import { useEffect, useState } from "react";
import { api, useAction, useRead } from "@/features/workspace/client";
import { Button } from "@/components/ui/button";
import {
  Panel,
  Field,
  Select,
  ReadState,
  ErrorNotice,
  Pages,
  Refs,
  control,
} from "@/features/workspace/ui";
import type { Page, ResumeChoice, Render } from "@/features/workspace/contracts";
import { CompressionSummary, PdfLinks, ResumeContent } from "@/features/workspace/results";
import {
  sectionLabels,
  linkedFacts,
  type Profile,
  type Fact,
  type ResumeDocument,
  type ResumeSection,
  type Variant,
} from "./contracts";
import { FactPicker } from "./fact-picker";
export function BaseResumes({
  facts,
  factsError,
  factsLoaded,
  currentProfile,
}: {
  facts: Fact[];
  factsError?: string;
  factsLoaded: boolean;
  currentProfile?: Profile;
}) {
  const [variantId, setVariantId] = useState("");
  const [selected, setSelected] = useState<Variant>();
  const [editing, setEditing] = useState(false),
    [creating, setCreating] = useState(false);
  const [head, setHead] = useState<number>();
  const [offset, setOffset] = useState(0),
    [revisionOffset, setRevisionOffset] = useState(0);
  const action = useAction();
  const library = useRead<Page<ResumeChoice>>(`resume-library?limit=20&offset=${offset}`);
  const revisions = useRead<ResumeChoice[]>(
    variantId ? `resume-revisions?variant_id=${variantId}&limit=20&offset=${revisionOffset}` : null,
  );
  const sourceProfile = useRead<Profile>(
    selected ? `profile/revisions/${selected.document.profile_id}` : null,
  );
  const remember = (value: Variant) =>
    sessionStorage.setItem(
      "base-resume-selection",
      JSON.stringify({ variant: value.id, revision: value.revision }),
    );
  useEffect(() => {
    let active = true;
    const raw = sessionStorage.getItem("base-resume-selection");
    if (raw) {
      try {
        const v = JSON.parse(raw) as { variant: string; revision: number };
        if (/^[0-9a-f-]{36}$/.test(v.variant) && Number.isInteger(v.revision) && v.revision > 0) {
          void api<Variant>(`resume-variants/${v.variant}?revision=${v.revision}`)
            .then((r) => {
              if (active) {
                setVariantId(r.id);
                setSelected(r);
              }
            })
            .catch(() => {});
        }
      } catch {
        /* Invalid local browsing preference has no effect on task bindings. */
      }
    }
    return () => {
      active = false;
    };
  }, []);
  const view = (id: string, revision?: number) =>
    action.run(async () => {
      if (!id) {
        setVariantId("");
        setSelected(undefined);
        setEditing(false);
        return;
      }
      const value = await api<Variant>(
        `resume-variants/${id}${revision ? `?revision=${revision}` : ""}`,
      );
      setVariantId(id);
      setSelected(value);
      setEditing(false);
      setCreating(false);
      remember(value);
    });
  const editProfile = creating ? currentProfile : sourceProfile.data;
  return (
    <Panel title="简历库">
      <ReadState loaded={!!library.data} error={library.error} />
      <Select
        label="简历"
        value={variantId}
        onChange={(e) => {
          setRevisionOffset(0);
          void view(e.target.value);
        }}
      >
        <option value="">请选择简历</option>
        {selected && !library.data?.items.some((r) => r.resume_variant_id === selected.id) && (
          <option value={selected.id}>{selected.document.metadata.label || "简历"}</option>
        )}
        {library.data?.items.map((r) => (
          <option key={r.resume_variant_id} value={r.resume_variant_id}>
            {r.label || "简历"} · {new Date(r.created_at).toLocaleDateString("zh-CN")}
          </option>
        ))}
      </Select>
      {library.data && (offset > 0 || library.data.has_more) && (
        <Pages offset={offset} setOffset={setOffset} more={library.data.has_more} size={20} />
      )}
      {selected && (
        <>
          <Select
            label="版本"
            value={selected.revision}
            onChange={(e) => void view(variantId, Number(e.target.value))}
          >
            {!revisions.data?.some((r) => r.revision === selected.revision) && (
              <option value={selected.revision}>
                第 {selected.revision} 版 · {new Date(selected.created_at).toLocaleString("zh-CN")}
              </option>
            )}
            {revisions.data?.map((r) => (
              <option key={r.resume_revision_id} value={r.revision}>
                第 {r.revision} 版 · {new Date(r.created_at).toLocaleString("zh-CN")}
              </option>
            ))}
          </Select>
          {revisions.data && (revisionOffset > 0 || revisions.data.length === 20) && (
            <Pages
              offset={revisionOffset}
              setOffset={setRevisionOffset}
              more={revisions.data.length === 20}
              size={20}
            />
          )}
          <p className="text-sm text-secondary">
            基于个人资料第 {selected.document.profile_revision} 版创建
          </p>
          <Button
            disabled={action.busy || !sourceProfile.data}
            onClick={() =>
              void action.run(async () => {
                const current = await api<Variant>(`resume-variants/${selected.id}`);
                setHead(current.revision);
                setCreating(false);
                setEditing(true);
              })
            }
          >
            编辑此版本
          </Button>
        </>
      )}
      {currentProfile && (
        <Button
          onClick={() => {
            setCreating(true);
            setEditing(true);
          }}
        >
          从个人资料创建简历
        </Button>
      )}
      <ErrorNotice code={action.error || factsError || sourceProfile.error || revisions.error} />
      {editing && editProfile && factsLoaded && (
        <ResumeEditor
          key={`${creating ? "new" : selected?.resume_revision_id}:${head}`}
          profile={editProfile}
          facts={facts}
          initial={creating ? undefined : selected}
          expectedRevision={head}
          onSaved={(value) => {
            setSelected(value);
            setVariantId(value.id);
            setEditing(false);
            setCreating(false);
            remember(value);
            library.reload();
            revisions.reload();
          }}
        />
      )}
      {editing && (
        <Button
          onClick={() => {
            setEditing(false);
            setCreating(false);
          }}
        >
          取消编辑
        </Button>
      )}
      {!editing && selected && <SavedResume key={selected.resume_revision_id} value={selected} />}
    </Panel>
  );
}
function ResumeEditor({
  profile,
  facts,
  initial,
  expectedRevision,
  onSaved,
}: {
  profile: Profile;
  facts: Fact[];
  initial?: Variant;
  expectedRevision?: number;
  onSaved: (v: Variant) => void;
}) {
  const [document, setDocument] = useState<ResumeDocument>(() =>
      initial ? structuredClone(initial.document) : draftFromProfile(profile, facts),
    ),
    [section, setSection] = useState<ResumeSection["name"]>("projects"),
    [done, setDone] = useState(false);
  const action = useAction();
  const allowed = facts.filter((f) => linkedFacts(profile.data).includes(f.id));
  const change = (s: ResumeSection) =>
    setDocument((d) => ({
      ...d,
      sections: d.sections.map((row) => (row.section_id === s.section_id ? s : row)),
    }));
  const eligible =
    (!initial || canonical(document) !== canonical(initial.document)) &&
    document.sections.length > 0 &&
    document.sections.every(
      (s) =>
        s.items.length > 0 &&
        s.items.every(
          (i) =>
            i.fact_refs.length > 0 &&
            i.fact_refs.every((id) => allowed.some((f) => f.id === id && f.status === "verified")),
        ),
    ) &&
    document.sections.some((s) => s.items.some((i) => i.required));
  return (
    <form
      className="space-y-4 border-t border-line pt-4"
      onSubmit={(e) => {
        e.preventDefault();
        void action.run(async () => {
          const value = await api<Variant>(
            initial ? `resume-variants/${initial.id}/revisions` : "resume-variants",
            "POST",
            initial
              ? { expected_revision: expectedRevision ?? initial.revision, document }
              : document,
          );
          setDone(true);
          onSaved(value);
        });
      }}
    >
      <fieldset disabled={action.busy || done} className="min-w-0 space-y-4">
        <Field label="简历名称">
          <input
            maxLength={200}
            className={control}
            value={document.metadata.label || ""}
            onChange={(e) =>
              setDocument({ ...document, metadata: { label: e.target.value || null } })
            }
          />
        </Field>
        <p className="text-sm">
          {initial
            ? `基于第 ${initial.revision} 版内容创建新版本。`
            : "整理个人经历，作为后续岗位简历的起点。"}
        </p>
        {document.sections.map((s) => (
          <section
            key={s.section_id}
            className="space-y-3 rounded-control border border-line p-4"
            aria-label={`${sectionLabels[s.name]}简历内容`}
          >
            <h3 className="font-semibold">{sectionLabels[s.name]}</h3>
            {s.items.map((item, index) => (
              <div key={item.item_id} className="space-y-3 border-t border-line pt-3">
                <Field label={`${sectionLabels[s.name]}正文 ${index + 1}`}>
                  <textarea
                    required
                    maxLength={12000}
                    className={control}
                    value={item.text}
                    onChange={(e) =>
                      change({
                        ...s,
                        items: s.items.map((i) =>
                          i.item_id === item.item_id ? { ...i, text: e.target.value } : i,
                        ),
                      })
                    }
                  />
                </Field>
                <FactPicker
                  facts={allowed}
                  value={item.fact_refs}
                  label={`${sectionLabels[s.name]}正文 ${index + 1} 的事实依据`}
                  onChange={(ids) =>
                    change({
                      ...s,
                      items: s.items.map((i) =>
                        i.item_id === item.item_id ? { ...i, fact_refs: ids } : i,
                      ),
                    })
                  }
                />
                <Button
                  disabled={!item.fact_refs.length}
                  onClick={() =>
                    change({
                      ...s,
                      items: s.items.map((i) =>
                        i.item_id === item.item_id
                          ? {
                              ...i,
                              text: i.fact_refs
                                .map((id) => allowed.find((f) => f.id === id)?.statement || "")
                                .join("\n"),
                            }
                          : i,
                      ),
                    })
                  }
                >
                  用所选事实原文填入正文 {index + 1}
                </Button>
                <Field label={`精简正文 ${index + 1}（可选）`}>
                  <textarea
                    className={control}
                    maxLength={12000}
                    value={item.short_text || ""}
                    onChange={(e) =>
                      change({
                        ...s,
                        items: s.items.map((i) =>
                          i.item_id === item.item_id
                            ? { ...i, short_text: e.target.value || null }
                            : i,
                        ),
                      })
                    }
                  />
                </Field>
                <label className="flex gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={item.required}
                    onChange={(e) =>
                      change({
                        ...s,
                        items: s.items.map((i) =>
                          i.item_id === item.item_id ? { ...i, required: e.target.checked } : i,
                        ),
                      })
                    }
                  />
                  排版时必须保留
                </label>
                {item.hard_claims.length > 0 && <Refs values={{ hard_claims: item.hard_claims }} />}
                <Button
                  onClick={() =>
                    change({
                      ...s,
                      items: s.items
                        .filter((i) => i.item_id !== item.item_id)
                        .map((i, ordering) => ({ ...i, ordering })),
                    })
                  }
                >
                  移除正文 {index + 1}
                </Button>
              </div>
            ))}
            <Button
              disabled={s.items.length >= 100}
              onClick={() =>
                change({
                  ...s,
                  items: [
                    ...s.items,
                    {
                      item_id: crypto.randomUUID(),
                      kind: s.name === "summary" ? "summary" : "bullet",
                      text: "",
                      short_text: null,
                      fact_refs: [],
                      requirement_refs: [],
                      hard_claims: [],
                      priority: 50,
                      required: true,
                      ordering: s.items.length,
                    },
                  ],
                })
              }
            >
              添加{sectionLabels[s.name]}正文
            </Button>
            <Button
              onClick={() =>
                setDocument({
                  ...document,
                  sections: document.sections
                    .filter((row) => row.section_id !== s.section_id)
                    .map((row, ordering) => ({ ...row, ordering })),
                })
              }
            >
              移除{sectionLabels[s.name]}章节
            </Button>
          </section>
        ))}
        <div className="flex flex-wrap items-end gap-3">
          <Select
            label="添加章节"
            value={section}
            onChange={(e) => setSection(e.target.value as ResumeSection["name"])}
          >
            {Object.entries(sectionLabels).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
          <Button
            disabled={
              document.sections.some((s) => s.name === section) || document.sections.length >= 5
            }
            onClick={() =>
              setDocument({
                ...document,
                sections: [
                  ...document.sections,
                  {
                    section_id: crypto.randomUUID(),
                    name: section,
                    ordering: document.sections.length,
                    priority: 50,
                    required: true,
                    items: [],
                  },
                ],
              })
            }
          >
            添加简历章节
          </Button>
        </div>
        {!eligible && (
          <p className="text-sm text-secondary">
            每章至少填写一条正文并关联已确认事实，至少保留一条必留内容。没有可选事实时，请先在个人资料中关联事实。
          </p>
        )}
        <Button type="submit" disabled={!eligible}>
          {initial ? "保存新版本" : "保存基础简历"}
        </Button>
      </fieldset>
      <ErrorNotice code={action.error} />
      {action.error && (
        <p className="text-sm">
          保存失败时请先刷新列表，确认是否已保存；若内容已被更新，请重新打开后编辑。
        </p>
      )}
      {done && <p role="status">简历已保存，可以生成 PDF。</p>}
    </form>
  );
}
function SavedResume({ value }: { value: Variant }) {
  const [render, setRender] = useState<Render>();
  const head = useRead<Variant>(`resume-variants/${value.id}`);
  const action = useAction();
  return (
    <section className="space-y-3 border-t border-line pt-4" aria-label="已保存的基础简历">
      <h3>
        第 {value.revision} 版{" "}
        {head.data && (head.data.revision === value.revision ? "· 当前版本" : "· 历史版本")}
      </h3>
      <Refs
        values={{
          resume_variant_id: value.id,
          resume_revision_id: value.resume_revision_id,
          revision: value.revision,
          profile_id: value.document.profile_id,
          profile_revision: value.document.profile_revision,
        }}
      />
      <ResumeContent content={value.document as unknown as Record<string, unknown>} />
      <Button
        disabled={action.busy}
        onClick={() =>
          void action.run(async () =>
            setRender(
              await api<Render>(`resume-variants/${value.id}/render`, "POST", {
                revision: value.revision,
              }),
            ),
          )
        }
      >
        生成 PDF
      </Button>
      <ErrorNotice code={action.error} />
      {render && (
        <>
          <p role="status">
            {render.report.render_status === "accepted" ? "PDF 已生成" : "PDF 尚未通过检查"}
          </p>
          <CompressionSummary
            report={render.report}
            content={value.document as unknown as Record<string, unknown>}
          />
          {render.report.render_status === "accepted" ? (
            <PdfLinks id={render.id} />
          ) : (
            <>
              <p>请调整简历内容后再生成。</p>
              <Refs values={{ findings: render.report.findings }} />
            </>
          )}
        </>
      )}
    </section>
  );
}
