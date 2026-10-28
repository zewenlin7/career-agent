"use client";
import { invalidShortText, shortTextErrors, type ResumeFieldError } from "./short-text";
import { useConfirmation } from "./confirmation";
import { ResumeRefinement } from "./refinement";
import { InlineName } from "./inline-name";
import { savedResumes } from "./library";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, ApiError, endpoint, useAction, useRead, useRequestId } from "../workspace/client";
import { control, Field } from "../workspace/ui";
import { PdfLinks } from "../workspace/results";
import type { Render } from "../workspace/contracts";
import type { ResumeDocument, ResumeSection, Variant } from "../onboarding/contracts";
import { sectionLabels } from "../onboarding/contracts";
import { canonical } from "../onboarding/drafts";
import { InlineError, SavedAt } from "./common";
import type { Draft, Version, Presentation } from "./contracts";
import type { NamedProfile } from "./personal";
import type { Draft as GenerationDraft } from "../workspace/draft-action";
import { ResumeView, defaultPresentation } from "./resume-view";
import { Compression } from "./compression";
async function saveResumeFields<T>(
  path: string,
  body: unknown,
  sections: ResumeSection[],
  setErrors: (ids: string[]) => void,
): Promise<T | undefined> {
  function report(fields: ResumeFieldError[]) {
    setErrors(
      fields.flatMap((f) => {
        const item = sections[f.section]?.items[f.item];
        return item ? [item.item_id] : [];
      }),
    );
  }
  const fields = shortTextErrors(sections);
  if (fields.length) {
    report(fields);
    return;
  }
  setErrors([]);
  try {
    return await api<T>(path, "POST", body);
  } catch (error) {
    if (error instanceof ApiError && error.fields.length) {
      report(error.fields);
      return;
    }
    throw error;
  }
}
async function allVersions(_path: string, signal: AbortSignal) {
  const items: Version[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await api<{ items: Version[]; has_more: boolean }>(
      `resume-library/versions?limit=100&offset=${offset}`,
      "GET",
      undefined,
      signal,
    );
    items.push(...page.items);
    if (!page.has_more) return { items, has_more: false };
  }
}
export function ResumeLibrary() {
  const list = useRead<{ items: Version[]; has_more: boolean }>(
      "resume-library/versions?limit=100",
      allVersions,
    ),
    drafts = useRead<Draft[]>("resume-workspaces", savedResumes),
    profiles = useRead<{ items: NamedProfile[] }>("profile-library");
  const [selected, setSelected] = useState(""),
    [created, setCreated] = useState<Draft>(),
    [creating, setCreating] = useState(false),
    [creationIntent, setCreationIntent] = useState(0),
    [source, setSource] = useState(""),
    [mode, setMode] = useState("quick"),
    [editing, setEditing] = useState(false),
    [notice, setNotice] = useState("");
  const action = useAction(),
    requestId = useRequestId(),
    latch = useRef(false);
  const [loaded, setLoaded] = useState<{ version: Version; variant: Variant; render?: Render }>();
  const restoreScroll = useRef<number | null>(null);
  useLayoutEffect(() => {
    if (restoreScroll.current !== null) {
      window.scrollTo({ top: restoreScroll.current, behavior: "instant" });
      restoreScroll.current = null;
    }
  }, [selected, loaded?.version.id]);
  async function publish(id: string, render?: Render) {
    const scroll = window.scrollY;
    const versions = await allVersions("", new AbortController().signal);
    const version = versions.items.find((v) => v.id === id);
    if (!version) throw new ApiError("not_found");
    const variant = await api<Variant>(
      `resume-variants/${version.variant_id}?revision=${version.revision}`,
    );
    setLoaded({ version, variant, render });
    restoreScroll.current = scroll;
    setSelected(version.entry_id || id);
    setCreated(undefined);
    setEditing(false);
    refresh();
  }
  const listedVersion = list.data?.items.find((v) => (v.entry_id || v.id) === selected);
  const loadedVersion =
    loaded && (loaded.version.entry_id || loaded.version.id) === selected
      ? loaded.version
      : undefined;
  const version =
    loadedVersion && (!listedVersion || loadedVersion.revision > listedVersion.revision)
      ? loadedVersion
      : listedVersion || loadedVersion;
  const draft = loadedVersion
    ? undefined
    : (created?.entry_id || created?.id) === selected
      ? created
      : drafts.data?.find((d) => (d.entry_id || d.id) === selected);
  function refresh() {
    list.reload();
    drafts.reload();
  }
  function choose(id: string) {
    setLoaded(undefined);
    setSelected(id);
    setCreated(undefined);
    setEditing(false);
    refresh();
  }
  return (
    <>
      <div className="mb-8 flex items-center justify-between gap-4">
        <h1 className="font-serif text-3xl">简历库</h1>
        <Button
          disabled={editing || action.busy}
          onClick={() => {
            if (!creating) setCreationIntent((n) => n + 1);
            setCreating(!creating);
          }}
        >
          新建
        </Button>
      </div>
      {creating && (
        <section
          aria-label="新建简历"
          className="mb-6 grid gap-3 border-y border-line py-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end"
        >
          <Field label="个人资料">
            <select
              disabled={action.busy}
              className={control}
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="">请选择</option>
              {profiles.data?.items
                .filter((p) => p.profile_id)
                .map((p) => (
                  <option key={p.id} value={p.profile_id!}>
                    {p.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="创建方式">
            <select
              disabled={action.busy}
              className={control}
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="quick">快速创建</option>
              <option value="ai">AI 生成</option>
            </select>
          </Field>
          <Button
            variant="primary"
            disabled={!source || action.busy}
            onClick={() => {
              if (latch.current) return;
              latch.current = true;
              void action
                .run(async () => {
                  let d: Draft;
                  if (mode === "quick")
                    d = await api<Draft>("resume-workspaces", "POST", {
                      request_id: requestId({ source, mode, creationIntent }),
                      profile_id: source,
                    });
                  else {
                    const generation = await api<GenerationDraft>("product-drafts", "POST", {
                      request_id: requestId({ source, mode, creationIntent }),
                      profile_id: source,
                      task: "base_resume_drafting",
                      mode: "live",
                    });
                    const completed = await api<GenerationDraft>(
                      `product-drafts/${generation.id}/execute`,
                      "POST",
                      {},
                    );
                    if (completed.status !== "completed")
                      throw new ApiError(completed.reason || "generation_failed");
                    const adopted = await api<GenerationDraft>(
                      `product-drafts/${generation.id}/adopt`,
                      "POST",
                      {},
                    );
                    d = await api<Draft>(
                      `resume-workspaces/${adopted.adopted?.resume_workspace_id}`,
                    );
                  }
                  setCreated(d);
                  setSelected(d.entry_id || d.id);
                  setCreating(false);
                  setNotice("已创建");
                  drafts.reload();
                })
                .finally(() => {
                  latch.current = false;
                });
            }}
          >
            {action.busy ? "正在创建…" : "创建"}
          </Button>
        </section>
      )}
      <InlineError code={action.error || list.error || drafts.error} />
      {notice && (
        <p role="status" className="mb-4 text-sm">
          {notice}
        </p>
      )}
      <Field label="简历">
        <select
          className={control}
          disabled={editing}
          value={selected}
          onChange={(e) => choose(e.target.value)}
        >
          <option value="">请选择</option>
          {Array.from(
            new Map(
              [
                ...(loaded ? [loaded.version] : []),
                ...(drafts.data || []),
                ...(list.data?.items || []),
                ...(created ? [created] : []),
              ].map((item) => [("entry_id" in item && item.entry_id) || item.id, item]),
            ).values(),
          )
            .sort(
              (a, b) =>
                b.created_at.localeCompare(a.created_at) ||
                (("entry_id" in a && a.entry_id) || a.id).localeCompare(
                  ("entry_id" in b && b.entry_id) || b.id,
                ),
            )
            .map((item) => (
              <option key={item.id} value={("entry_id" in item && item.entry_id) || item.id}>
                {item.name}
              </option>
            ))}
        </select>
      </Field>
      {draft && (
        <DraftEditor
          key={draft.id}
          initial={draft}
          onEditing={setEditing}
          onSaved={(d) => {
            setCreated(d);
            setSelected(d.entry_id || d.id);
            refresh();
          }}
          onPublished={publish}
          onRemoved={() => choose("")}
        />
      )}
      {version && !draft && (
        <VersionView
          key={version.id}
          version={version}
          initial={loaded?.version.id === version.id ? loaded.variant : undefined}
          initialRender={loaded?.version.id === version.id ? loaded.render : undefined}
          onEditing={setEditing}
          refresh={refresh}
          onSaved={(id, workspace) => {
            if (workspace)
              void api<Draft>(`resume-workspaces/${id}`).then((d) => {
                setLoaded(undefined);
                setCreated(d);
                setSelected(d.entry_id || d.id);
                refresh();
              });
            else void publish(id);
          }}
          onRemoved={() => choose("")}
        />
      )}
    </>
  );
}
function ContentEditor({
  sections: inputSections,
  change,
  compact = false,
  presentation: inputPresentation = defaultPresentation,
  onPresentation: persistPresentation,
  fieldErrors = [],
  clearErrors,
}: {
  fieldErrors?: string[];
  clearErrors?: () => void;
  presentation?: Presentation;
  onPresentation: (p: Presentation) => void;
  compact?: boolean;
  sections: ResumeSection[];
  change: (v: ResumeSection[]) => void;
}) {
  const [touched, setTouched] = useState<string[]>([]);
  const presentation = { ...defaultPresentation, ...inputPresentation };
  function onPresentation(value: Presentation) {
    persistPresentation(value);
  }
  const sections = inputSections.map((section) => ({
    ...section,
    items: [...section.items].sort((a, b) => {
      const rank = (id: string, fallback: number) =>
        presentation.item_order?.includes(id)
          ? presentation.item_order.indexOf(id)
          : 500 + fallback;
      return (
        rank(a.item_id, a.ordering) - rank(b.item_id, b.ordering) ||
        a.item_id.localeCompare(b.item_id)
      );
    }),
  }));
  const editor = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!fieldErrors.length) return;
    const field = editor.current?.querySelector<HTMLTextAreaElement>(
      "textarea[data-short-item][aria-invalid='true']",
    );
    if (field) {
      field.closest("details")?.setAttribute("open", "");
      field.focus();
      field.scrollIntoView({ block: "center" });
    }
  }, [fieldErrors]);
  useEffect(() => {
    if (compact)
      editor.current
        ?.querySelector('[data-needs-compact="true"]')
        ?.scrollIntoView({ block: "center" });
  }, [compact]);
  function update(index: number, item: number, key: string, value: unknown) {
    if (key === "text" || (key === "short_text" && !value)) {
      onPresentation({
        ...presentation,
        compact_item_ids: (presentation.compact_item_ids || []).filter(
          (id) => id !== sections[index].items[item].item_id,
        ),
      });
    }
    change(
      sections.map((s, i) =>
        i === index
          ? {
              ...s,
              items: s.items.map((r, j) =>
                j === item
                  ? { ...r, [key]: value, ...(key === "text" ? { short_text: null } : {}) }
                  : r,
              ),
            }
          : s,
      ),
    );
  }
  return (
    <div ref={editor} className="divide-y divide-line">
      {sections
        .map((section, index) => ({ section, index }))
        .sort((a, b) => {
          const order =
            presentation.experience_order === "projects_first"
              ? ["summary", "education", "projects", "experience", "skills"]
              : ["summary", "education", "experience", "projects", "skills"];
          return order.indexOf(a.section.name) - order.indexOf(b.section.name);
        })
        .map(({ section, index }) => (
          <section key={section.section_id} className="space-y-5 py-6">
            <div className="flex items-center gap-3">
              <h3 className="font-serif text-xl font-semibold">{sectionLabels[section.name]}</h3>
              {["experience", "projects"].includes(section.name) && (
                <button
                  aria-label="交换工作与项目顺序"
                  onClick={() =>
                    onPresentation({
                      ...presentation,
                      experience_order:
                        presentation.experience_order === "projects_first"
                          ? "work_first"
                          : "projects_first",
                    })
                  }
                >
                  ↑↓
                </button>
              )}
              {["summary", "skills"].includes(section.name) && (
                <>
                  {presentation.hidden_sections.includes(section.name) && (
                    <span className="text-sm text-secondary">· 已隐藏</span>
                  )}
                  <button
                    className="ml-auto text-sm font-normal text-secondary hover:text-ink"
                    onClick={() =>
                      onPresentation({
                        ...presentation,
                        hidden_sections: presentation.hidden_sections.includes(section.name)
                          ? presentation.hidden_sections.filter((n) => n !== section.name)
                          : [...presentation.hidden_sections, section.name],
                      })
                    }
                  >
                    {presentation.hidden_sections.includes(section.name) ? "显示" : "隐藏"}
                  </button>
                </>
              )}
            </div>
            {section.items.map((item, j) => (
              <div key={item.item_id} className="space-y-3" data-needs-compact={!item.short_text}>
                {!["skills", "summary"].includes(section.name) && (
                  <div className="flex items-center gap-3 text-sm text-secondary">
                    <span className="mr-auto text-base font-medium text-ink">
                      {sectionLabels[section.name]}内容 {j + 1}
                      {presentation.hidden_item_ids?.includes(item.item_id) ? " · 已隐藏" : ""}
                    </span>
                    <button
                      className="text-sm font-normal text-secondary hover:text-ink"
                      onClick={() =>
                        onPresentation({
                          ...presentation,
                          hidden_item_ids: presentation.hidden_item_ids?.includes(item.item_id)
                            ? presentation.hidden_item_ids.filter((id) => id !== item.item_id)
                            : [...(presentation.hidden_item_ids || []), item.item_id],
                        })
                      }
                    >
                      {presentation.hidden_item_ids?.includes(item.item_id) ? "显示" : "隐藏"}
                    </button>
                    <button
                      className="text-sm font-normal text-secondary hover:text-ink"
                      disabled={j === 0}
                      onClick={() => {
                        const next = structuredClone(sections);
                        [next[index].items[j - 1], next[index].items[j]] = [
                          next[index].items[j],
                          next[index].items[j - 1],
                        ];
                        onPresentation({
                          ...presentation,
                          item_order: next.flatMap((s) => s.items.map((i) => i.item_id)),
                        });
                      }}
                    >
                      上移
                    </button>
                    <button
                      className="text-sm font-normal text-secondary hover:text-ink"
                      disabled={j === section.items.length - 1}
                      onClick={() => {
                        const next = structuredClone(sections);
                        [next[index].items[j + 1], next[index].items[j]] = [
                          next[index].items[j],
                          next[index].items[j + 1],
                        ];
                        onPresentation({
                          ...presentation,
                          item_order: next.flatMap((s) => s.items.map((i) => i.item_id)),
                        });
                      }}
                    >
                      下移
                    </button>
                  </div>
                )}
                <div>
                  <textarea
                    aria-label={`${sectionLabels[section.name]}内容 ${j + 1}`}
                    rows={6}
                    className={control}
                    value={item.text}
                    onChange={(e) => update(index, j, "text", e.target.value)}
                  />
                </div>
                <details className="text-sm" open={compact || undefined}>
                  <summary className="cursor-pointer text-secondary">篇幅设置</summary>
                  <div className="mt-3 space-y-3">
                    <label className="grid gap-2 text-sm font-normal">
                      <span>精简表达（选填）</span>
                      <textarea
                        rows={3}
                        className={`${control} font-normal`}
                        value={item.short_text || ""}
                        data-short-item={item.item_id}
                        aria-invalid={
                          fieldErrors.includes(item.item_id) ||
                          (touched.includes(item.item_id) &&
                            invalidShortText(item.text, item.short_text))
                        }
                        aria-describedby={`short-error-${item.item_id}`}
                        onBlur={() => setTouched((ids) => [...new Set([...ids, item.item_id])])}
                        onChange={(e) => {
                          clearErrors?.();
                          update(index, j, "short_text", e.target.value || null);
                        }}
                      />
                    </label>
                    <p
                      id={`short-error-${item.item_id}`}
                      role={
                        fieldErrors.includes(item.item_id) ||
                        (touched.includes(item.item_id) &&
                          invalidShortText(item.text, item.short_text))
                          ? "alert"
                          : undefined
                      }
                      className="min-h-5 text-sm font-normal text-error"
                    >
                      {fieldErrors.includes(item.item_id) ||
                      (touched.includes(item.item_id) &&
                        invalidShortText(item.text, item.short_text))
                        ? "精简表达必须比原文更短"
                        : ""}
                    </p>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={presentation.compact_item_ids?.includes(item.item_id) || false}
                        disabled={!item.short_text}
                        onChange={(e) =>
                          onPresentation({
                            ...presentation,
                            compact_item_ids: e.target.checked
                              ? [...(presentation.compact_item_ids || []), item.item_id]
                              : (presentation.compact_item_ids || []).filter(
                                  (id) => id !== item.item_id,
                                ),
                          })
                        }
                      />
                      使用精简版
                    </label>
                  </div>
                </details>
              </div>
            ))}
          </section>
        ))}
    </div>
  );
}
function DraftEditor({
  initial,
  onSaved,
  onPublished,
  onRemoved,
  onEditing,
}: {
  initial: Draft;
  onSaved: (d: Draft) => void;
  onPublished: (id: string, render?: Render) => Promise<void>;
  onRemoved: () => void;
  onEditing: (v: boolean) => void;
}) {
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);
  const { confirm, confirmation } = useConfirmation();
  const [refining, setRefining] = useState(false);
  const [row, setRow] = useState(initial),
    [document, setDocument] = useState(initial.document),
    [name, setName] = useState(initial.name),
    [editing, setEditing] = useState(
      () =>
        (typeof window !== "undefined"
          ? sessionStorage.getItem(`resume-compact:${initial.id}`)
          : null) === "true",
    ),
    [compact, setCompact] = useState(
      () =>
        (typeof window !== "undefined"
          ? sessionStorage.getItem(`resume-compact:${initial.id}`)
          : null) === "true",
    ),
    [render, setRender] = useState<Render>(),
    [missing, setMissing] = useState<{ item_id: string; text: string }[]>([]),
    [claimError, setClaimError] = useState(false);
  const action = useAction(),
    requestId = useRequestId();

  const [draftPresentation, setDraftPresentation] = useState({
    ...defaultPresentation,
    ...initial.presentation,
  });
  const dirty =
    canonical(draftPresentation) !== canonical({ ...defaultPresentation, ...row.presentation }) ||
    canonical(document) !== canonical(row.document) ||
    name !== row.name;
  async function pdf() {
    const result = await api<{
      claim_issues: { item_id: string; text: string }[];
      artifact: Render | null;
      resume_revision_id?: string;
    }>(`resume-workspaces/${row.id}/render`, "POST", {
      expected_revision: row.revision,
    });
    setMissing(result.claim_issues || []);
    setClaimError(!!result.claim_issues?.length);
    if (result.artifact) {
      setRender(result.artifact);
      if (result.resume_revision_id) await onPublished(result.resume_revision_id, result.artifact);
    }
  }
  return (
    <section className="mt-7 space-y-5">
      {confirmation}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <InlineName
          value={row.name}
          label="修改简历名称"
          disabled={action.busy}
          save={async (nextName) => {
            const d = await api<Draft>(`resume-workspaces/${row.id}`, "PATCH", {
              expected_revision: row.revision,
              document: row.document,
              name: nextName,
            });
            setRow(d);
            setName(d.name);
            onSaved(d);
          }}
        />
        <div className={refining ? "w-full" : "flex gap-3"}>
          {!editing && (
            <ResumeRefinement
              onToggle={setRefining}
              id={row.id}
              workspace
              onSaved={onPublished}
              disabled={action.busy}
            />
          )}
          {!refining && (
            <Button
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  if (!(await confirm(`删除“${row.name}”？历史文件将保留。`))) return;
                  await api(`resume-workspaces/${row.id}`, "DELETE", {
                    expected_revision: row.revision,
                  });
                  onRemoved();
                })
              }
            >
              删除
            </Button>
          )}
        </div>
      </div>
      <SavedAt value={row.saved_at} />
      <InlineError code={action.error} />
      <header className="flex justify-between gap-4">
        <div>
          <h3 className="font-serif text-xl">{row.display_name}</h3>
          <p className="break-words text-sm text-secondary">
            {Object.entries(row.personal || {})
              .filter(([k, v]) => k !== "photo_id" && v)
              .map(([, v]) => v)
              .join(" · ")}
          </p>
        </div>
        {row.personal?.photo_id && (
          <div className="shrink-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              alt="简历照片"
              className="h-28 w-20 object-contain"
              src={endpoint(`profile-photos/${row.personal.photo_id}`)}
            />
          </div>
        )}
      </header>
      {editing ? (
        <ContentEditor
          fieldErrors={fieldErrors}
          clearErrors={() => setFieldErrors([])}
          compact={compact}
          presentation={draftPresentation}
          onPresentation={setDraftPresentation}
          sections={document.sections}
          change={(sections) => setDocument({ sections })}
        />
      ) : (
        <ResumeView
          sections={row.document.sections}
          presentation={row.presentation}
          disabled={action.busy}
          onPresentation={(presentation) =>
            void action.run(async () => {
              const saved = await api<Draft>(`resume-workspaces/${row.id}/presentation`, "PUT", {
                ...presentation,
                expected_revision: row.revision,
              });
              setRow(saved);
              onSaved(saved);
              setRender(undefined);
            })
          }
        />
      )}
      {editing ? (
        <div className="flex gap-3">
          <Button
            disabled={(!dirty && !compact) || action.busy || !name.trim()}
            onClick={() =>
              void action.run(async () => {
                const d = await saveResumeFields<Draft>(
                  `resume-workspaces/${row.id}/editions`,
                  {
                    request_id: requestId({
                      id: row.id,
                      document,
                      name,
                      presentation: draftPresentation,
                    }),
                    expected_revision: row.revision,
                    document,
                    presentation: draftPresentation,
                    name: name.trim(),
                  },
                  document.sections,
                  setFieldErrors,
                );
                if (!d) return;
                if (compact) {
                  const resolved = await api<{
                    resume_revision_id: string | null;
                    claim_issues: { item_id: string; text: string }[];
                  }>(`resume-workspaces/${d.id}/resolve`, "POST", {
                    expected_revision: d.revision,
                  });
                  if (!resolved.resume_revision_id) {
                    setMissing(resolved.claim_issues);
                    setClaimError(true);
                    return;
                  }
                  sessionStorage.removeItem(`resume-compact:${row.id}`);
                  await onPublished(resolved.resume_revision_id);
                } else {
                  setRow(d);
                  onSaved(d);
                }
                setEditing(false);
                onEditing(false);
              })
            }
          >
            保存
          </Button>
          <Button
            onClick={() => {
              setDraftPresentation({ ...defaultPresentation, ...row.presentation });
              setDocument(row.document);
              setName(row.name);
              setEditing(false);
              onEditing(false);
            }}
          >
            取消
          </Button>
        </div>
      ) : (
        <div className="flex justify-between gap-3">
          <Button
            disabled={action.busy}
            onClick={() => {
              setCompact(false);
              setEditing(true);
              onEditing(true);
            }}
          >
            编辑
          </Button>
          <Button
            variant="primary"
            disabled={action.busy}
            onClick={() => void action.run(() => pdf())}
          >
            {action.busy ? "生成中…" : "生成 PDF"}
          </Button>
        </div>
      )}
      {claimError && !!missing.length && (
        <section className="space-y-3 border-y border-line py-4">
          {missing.map((i) => (
            <div key={i.item_id}>
              <p>{i.text}</p>
              <p role="alert" className="text-sm text-error">
                这条描述缺少个人资料依据。
              </p>
            </div>
          ))}
          <div className="flex gap-3">
            <Button
              onClick={() => {
                setMissing([]);
                setEditing(true);
                onEditing(true);
              }}
            >
              修改
            </Button>
            <Button
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  const draft = await api<GenerationDraft>("product-drafts", "POST", {
                    request_id: requestId({ row: row.id, missing: missing.map((i) => i.item_id) }),
                    task: "resume_claim_refinement",
                    source_workspace_id: row.id,
                    selected_item_ids: missing.map((i) => i.item_id),
                    mode: "live",
                    feedback: "仅根据原始个人资料依据调整这些描述，移除没有支持的内容。",
                  });
                  const completed = await api<GenerationDraft>(
                    `product-drafts/${draft.id}/execute`,
                    "POST",
                    {},
                  );
                  if (completed.status !== "completed")
                    throw new ApiError(completed.reason || "generation_failed");
                  const adopted = await api<GenerationDraft>(
                    `product-drafts/${draft.id}/adopt`,
                    "POST",
                    {},
                  );
                  onSaved(
                    await api<Draft>(`resume-workspaces/${adopted.adopted?.resume_workspace_id}`),
                  );
                })
              }
            >
              让 AI 调整
            </Button>
            <a href="/profile" className="text-accent-ink underline">
              补充个人资料
            </a>
          </div>
        </section>
      )}
      {render && (
        <>
          {render.report.render_status !== "accepted" && <p role="alert">{renderError(render)}</p>}
          {render.report.render_status === "accepted" && <PdfLinks downloadFirst id={render.id} />}
        </>
      )}
    </section>
  );
}
function VersionView({
  version,
  initial,
  initialRender,
  onEditing,
  refresh,
  onSaved,
  onRemoved,
}: {
  version: Version;
  initial?: Variant;
  initialRender?: Render;
  onEditing: (v: boolean) => void;
  refresh: () => void;
  onSaved: (id: string, workspace?: boolean) => void;
  onRemoved: () => void;
}) {
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);
  const [compressionGeneration, setCompressionGeneration] = useState<string>();
  const { confirm, confirmation } = useConfirmation();
  const [refining, setRefining] = useState(false);
  const read = useRead<Variant>(
    `resume-variants/${version.variant_id}?revision=${version.revision}`,
  );
  const [expected, setExpected] = useState<number>(),
    [editing, setEditing] = useState(false),
    [compact, setCompact] = useState(false),
    [document, setDocument] = useState<ResumeDocument>(),
    [name, setName] = useState(version.name),
    [render, setRender] = useState<Render>();
  const action = useAction(),
    requestId = useRequestId();
  const renders = useRead<{ id: string; created_at: string; download_url: string }[]>(
    `resume-revisions/${version.id}/renders`,
  );
  const latestRender = useRead<Render>(
    renders.data?.[0] ? `artifacts/${renders.data[0].id}` : null,
  );
  const current = read.data || initial;
  const candidateRender = render || latestRender.data || initialRender;
  const key = (value?: Partial<typeof defaultPresentation>) =>
    canonical({ ...defaultPresentation, ...value });
  const shownRender =
    candidateRender &&
    key(
      (candidateRender.report as unknown as { presentation?: typeof defaultPresentation })
        .presentation,
    ) === key(version.presentation)
      ? candidateRender
      : undefined;
  const [draftPresentation, setDraftPresentation] = useState({
    ...defaultPresentation,
    ...version.presentation,
  });
  const dirty =
    document &&
    current &&
    (canonical(document) !== canonical(current.document) ||
      name !== version.name ||
      canonical(draftPresentation) !==
        canonical({ ...defaultPresentation, ...version.presentation }));
  return (
    <section className="mt-7 space-y-5">
      {confirmation}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <InlineName
            value={version.name}
            label="修改简历名称"
            disabled={action.busy}
            save={async (nextName) => {
              await api(`resume-library/versions/${version.id}`, "PATCH", {
                expected_revision: version.metadata_revision,
                name: nextName,
              });
              setName(nextName);
              refresh();
            }}
          />
          <SavedAt value={version.saved_at} />
        </div>
        <div className={refining ? "w-full" : "flex flex-wrap gap-2"}>
          {!editing && (
            <ResumeRefinement
              onToggle={setRefining}
              id={version.id}
              onSaved={onSaved}
              disabled={action.busy}
            />
          )}
          {!refining && (
            <Button
              onClick={() =>
                void action.run(async () => {
                  if (!(await confirm("删除这份简历？已生成的文件和历史使用记录将保留。"))) return;
                  await api(`resume-library/versions/${version.id}`, "DELETE", {
                    expected_revision: version.metadata_revision,
                  });
                  onRemoved();
                })
              }
            >
              删除
            </Button>
          )}
        </div>
      </div>
      <InlineError code={read.error || action.error} />
      {current &&
        (editing && document ? (
          <>
            <ContentEditor
              fieldErrors={fieldErrors}
              clearErrors={() => setFieldErrors([])}
              compact={compact}
              presentation={draftPresentation}
              onPresentation={setDraftPresentation}
              sections={document.sections}
              change={(sections) => setDocument({ ...document, sections })}
            />
            <div className="flex gap-3">
              <Button
                variant="primary"
                disabled={
                  !dirty ||
                  action.busy ||
                  document.sections.some((s) => s.items.some((i) => !i.text.trim()))
                }
                onClick={() =>
                  void action.run(async () => {
                    const saved = await saveResumeFields<{
                      workspace?: Draft;
                      resume_revision_id?: string;
                    }>(
                      `resume-library/versions/${version.id}/expression`,
                      {
                        request_id: requestId({
                          id: version.id,
                          document,
                          name,
                          presentation: draftPresentation,
                        }),
                        expected_revision: expected,
                        generation_id: compressionGeneration,
                        expected_metadata_revision: version.metadata_revision,
                        presentation: draftPresentation,
                        name,
                        document,
                      },
                      document.sections,
                      setFieldErrors,
                    );
                    if (!saved) return;
                    onSaved(
                      saved.workspace?.id || saved.resume_revision_id || version.id,
                      !!saved.workspace,
                    );
                    onEditing(false);
                    setEditing(false);
                  })
                }
              >
                保存
              </Button>
              <Button
                onClick={() => {
                  setDraftPresentation({ ...defaultPresentation, ...version.presentation });
                  setCompressionGeneration(undefined);
                  setDocument(undefined);
                  setEditing(false);
                  onEditing(false);
                }}
              >
                取消
              </Button>
            </div>
          </>
        ) : (
          <>
            {current.input_snapshot && (
              <header className="flex items-start justify-between gap-5 border-b border-line pb-5">
                <div className="min-w-0">
                  <h3 className="font-serif text-2xl">{current.input_snapshot.display_name}</h3>
                  <p className="mt-2 break-words text-sm text-secondary">
                    {Object.entries(current.input_snapshot.personal || {})
                      .filter(([key, value]) => key !== "photo_id" && value)
                      .map(([, value]) => value)
                      .join(" · ")}
                  </p>
                </div>
                {current.input_snapshot.personal?.photo_id && (
                  <div className="shrink-0">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      alt="简历照片"
                      src={endpoint(`profile-photos/${current.input_snapshot.personal.photo_id}`)}
                      className="h-28 w-20 object-contain"
                    />
                  </div>
                )}
              </header>
            )}
            <ResumeView
              sections={current.document.sections}
              presentation={version.presentation}
              disabled={action.busy}
              onPresentation={(presentation) =>
                void action.run(async () => {
                  await api(`resume-library/versions/${version.id}/presentation`, "PUT", {
                    ...presentation,
                    expected_revision: version.metadata_revision,
                  });
                  setRender(undefined);
                  refresh();
                })
              }
            />
            <div className="flex flex-wrap items-start justify-between gap-3">
              <Button
                disabled={action.busy}
                onClick={() =>
                  void action.run(async () => {
                    const head = await api<Variant>(`resume-variants/${version.variant_id}`);
                    setCompact(false);
                    setExpected(head.revision);
                    setDocument(structuredClone(current.document));
                    setEditing(true);
                    onEditing(true);
                  })
                }
              >
                编辑
              </Button>
              {shownRender?.report.render_status === "accepted" && (
                <PdfLinks downloadFirst id={shownRender.id} />
              )}
              {shownRender?.report.render_status !== "accepted" && (
                <Button
                  variant="primary"
                  disabled={action.busy}
                  onClick={() =>
                    void action.run(async () => {
                      setRender(
                        await api<Render>(`resume-variants/${version.variant_id}/render`, "POST", {
                          revision: version.revision,
                        }),
                      );
                      renders.reload();
                    })
                  }
                >
                  {action.busy ? "生成中…" : "生成 PDF"}
                </Button>
              )}
            </div>
          </>
        ))}
      {shownRender && (
        <>
          {shownRender.report.render_status !== "accepted" && (
            <p role="alert" className="text-sm text-error">
              {renderError(shownRender)}
            </p>
          )}
        </>
      )}
      {!editing && shownRender?.report.error_code === "layout_failed" && current && (
        <div className="flex flex-wrap items-start gap-3">
          <Compression
            sections={current.document.sections}
            resumeId={version.id}
            onReady={(sections, generationId, generatedIds) =>
              void action.run(async () => {
                const head = await api<Variant>(`resume-variants/${version.variant_id}`);
                setExpected(head.revision);
                setDocument({ ...current.document, sections });
                setCompressionGeneration(generationId);
                setDraftPresentation({
                  ...defaultPresentation,
                  ...version.presentation,
                  compact_item_ids: [
                    ...new Set([
                      ...(version.presentation?.compact_item_ids || []),
                      ...generatedIds,
                    ]),
                  ],
                });
                setCompact(true);
                setEditing(true);
                onEditing(true);
              })
            }
          />
          <Button
            onClick={() =>
              void action.run(async () => {
                const head = await api<Variant>(`resume-variants/${version.variant_id}`);
                setExpected(head.revision);
                setDocument(structuredClone(current.document));
                setCompact(true);
                setEditing(true);
                onEditing(true);
              })
            }
          >
            手动精简
          </Button>
        </div>
      )}
    </section>
  );
}

function renderError(render: Render): string {
  const code = render.report.error_code;
  if (code === "layout_failed") return "内容超出一页，请精简后重试。";
  if (code === "grounding_failed") return "部分描述与来源不一致，请修改这些内容后重试。";
  if (code === "font_dependency_missing") return "缺少简历字体，请重新运行启动检查。";
  if (code === "text_validation_failed") return "PDF 文字校验未通过，请调整布局后重试。";
  if (code === "compile_timeout" || code === "compiler_unavailable" || code === "template_error")
    return "PDF 排版失败，请检查本地渲染环境后重试。";
  return "PDF 生成失败，请重试。";
}
