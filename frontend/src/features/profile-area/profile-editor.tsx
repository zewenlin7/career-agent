"use client";
import { useEffect, useState, type ReactNode } from "react";
import { useConfirmation } from "./confirmation";
import { Button } from "@/components/ui/button";
import { api, useAction } from "../workspace/client";
import { Field, control } from "../workspace/ui";
import { canonical } from "../onboarding/drafts";
import { entryFields, personalFields, preferenceFields, type Data, type Entry } from "./contracts";
import { InlineError } from "./common";
import { Photo, PhotoPreview } from "./photo";
import { YearMonth } from "./year-month";
import type { NamedProfile } from "./personal";
export type EditingProfile = { id: string; revision: number; data: Data };
const titles = { education: "教育经历", experiences: "工作经历", projects: "项目经历" };
const emptyPersonal: Data["personal"] = {
  phone: "",
  email: "",
  city: "",
  github: "",
  website: "",
  other_contact: "",
  photo_id: null,
};

function Section({
  title,
  children,
  actions,
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section aria-label={title} className="group border-b border-line py-6">
      <header className="mb-4 flex items-center justify-between gap-3">
        <h3 className="font-serif text-xl">{title}</h3>
        {actions}
      </header>
      {children}
    </section>
  );
}
export function ProfileEditor({
  record,
  initial,
  done,
}: {
  record: NamedProfile;
  initial: EditingProfile;
  done: (record: NamedProfile) => void;
}) {
  const [session, setSession] = useState(initial);
  const [data, setData] = useState(initial.data);
  const [invalid, setInvalid] = useState(false);
  const [notice, setNotice] = useState("");
  const [photoBusy, setPhotoBusy] = useState(false);
  const action = useAction();
  const { confirm, confirmation } = useConfirmation();
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 2000);
    return () => clearTimeout(timer);
  }, [notice]);
  const path = `profile-library/${record.id}/editing`;
  async function persist(value: Data) {
    const result = await api<EditingProfile>(path, "PUT", {
      edit_id: session.id,
      expected_revision: session.revision,
      data: value,
    });
    setSession(result);
    setNotice("已保存");
    return result;
  }
  function local(value: Data) {
    void action.run(() => persist(value));
  }
  function singleton(keys: (keyof Data)[], clear: Partial<Data>) {
    const value = { ...session.data };
    for (const key of keys) Object.assign(value, { [key]: data[key] });
    return (
      <div className="flex gap-3 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <button
          type="button"
          disabled={action.busy || canonical(value) === canonical(session.data)}
          onClick={() => local(value)}
        >
          保存
        </button>
        <button
          type="button"
          disabled={action.busy || photoBusy}
          onClick={async () => {
            if (await confirm("确定清空这一部分的内容吗？")) {
              setData({ ...data, ...clear });
              setNotice("");
            }
          }}
        >
          清空
        </button>
      </div>
    );
  }
  return (
    <div>
      {confirmation}
      <fieldset disabled={action.busy || photoBusy}>
        <Section
          title="个人信息"
          actions={singleton(["display_name", "personal"], {
            display_name: "",
            personal: emptyPersonal,
          })}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {personalFields.map(([key, label, placeholder, required]) => (
              <div key={key}>
                <Field label={label + (required ? "" : "（选填）")}>
                  <input
                    className={control}
                    placeholder={placeholder}
                    value={key === "display_name" ? data.display_name : data.personal[key] || ""}
                    onChange={(e) =>
                      setData(
                        key === "display_name"
                          ? { ...data, display_name: e.target.value }
                          : { ...data, personal: { ...data.personal, [key]: e.target.value } },
                      )
                    }
                  />
                </Field>
                {required && invalid && !data.display_name.trim() && (
                  <InlineError message="请填写姓名。" />
                )}
              </div>
            ))}
          </div>
          <div className="mt-4">
            <Photo
              onBusy={setPhotoBusy}
              id={data.personal.photo_id}
              onChange={(id) => setData({ ...data, personal: { ...data.personal, photo_id: id } })}
            />
          </div>
        </Section>
        {(["education", "experiences", "projects"] as const).map((kind) => (
          <Section key={kind} title={titles[kind]}>
            <div className="divide-y divide-line">
              {data[kind].map((entry, index) => {
                const update = (patch: Partial<Entry>) =>
                  setData({
                    ...data,
                    [kind]: data[kind].map((value, i) =>
                      i === index ? { ...value, ...patch } : value,
                    ),
                  });
                return (
                  <div key={entry.entry_id || index} className="group/item py-4 first:pt-0">
                    <header className="mb-4 flex justify-between gap-3">
                      <h4>
                        {titles[kind]} {index + 1}
                      </h4>
                      <div className="flex gap-3 sm:opacity-0 sm:group-hover/item:opacity-100 sm:group-focus-within/item:opacity-100">
                        <button
                          type="button"
                          onClick={() => {
                            if (!entry.organization.trim()) {
                              setInvalid(true);
                              return;
                            }
                            const saved = session.data[kind];
                            const exists = saved.some((item) => item.entry_id === entry.entry_id);
                            local({
                              ...session.data,
                              [kind]: exists
                                ? saved.map((item) =>
                                    item.entry_id === entry.entry_id ? entry : item,
                                  )
                                : [...saved, entry],
                            });
                          }}
                        >
                          保存
                        </button>
                        <button
                          type="button"
                          onClick={async () => {
                            if (await confirm("确定删除这段经历吗？")) {
                              setData({
                                ...data,
                                [kind]: data[kind].filter((_, i) => i !== index),
                              });
                              local({
                                ...session.data,
                                [kind]: session.data[kind].filter(
                                  (item) => item.entry_id !== entry.entry_id,
                                ),
                              });
                            }
                          }}
                        >
                          删除
                        </button>
                      </div>
                    </header>
                    <div className="grid gap-4 sm:grid-cols-2">
                      {entryFields[kind].map(([key, label, placeholder, required]) => (
                        <div
                          key={key}
                          className={
                            key === "description" || key === "achievements" ? "sm:col-span-2" : ""
                          }
                        >
                          <Field label={label + (required ? "" : "（选填）")}>
                            {key.endsWith("_date") ? (
                              <YearMonth
                                value={String(entry[key as keyof Entry] || "")}
                                onChange={(value) => update({ [key]: value })}
                              />
                            ) : key === "description" || key === "achievements" ? (
                              <textarea
                                rows={3}
                                className={control}
                                value={String(entry[key as keyof Entry] || "")}
                                placeholder={placeholder}
                                onChange={(e) => update({ [key]: e.target.value })}
                              />
                            ) : (
                              <input
                                className={control}
                                value={String(entry[key as keyof Entry] || "")}
                                placeholder={placeholder}
                                onChange={(e) => update({ [key]: e.target.value })}
                              />
                            )}
                          </Field>
                          {required && invalid && !entry.organization.trim() && (
                            <InlineError message={`请填写${label}。`} />
                          )}
                        </div>
                      ))}
                    </div>
                    <details className="mt-3 text-sm">
                      <summary className="cursor-pointer text-secondary">简历展示字段</summary>
                      <div className="mt-2 flex flex-wrap gap-3">
                        {entryFields[kind]
                          .filter((field) => !field[3])
                          .map(([key, label]) => (
                            <label key={key} className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={!entry.hidden_fields?.includes(key)}
                                onChange={(event) =>
                                  update({
                                    hidden_fields: event.target.checked
                                      ? (entry.hidden_fields || []).filter((field) => field !== key)
                                      : [...(entry.hidden_fields || []), key],
                                  })
                                }
                              />
                              {label}
                            </label>
                          ))}
                      </div>
                    </details>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 text-center">
              <button
                type="button"
                aria-label={`添加${titles[kind]}`}
                className={`px-6 py-2 text-xl ${data[kind].length ? "text-secondary opacity-60 group-hover:opacity-100 focus:opacity-100" : "text-primary"}`}
                onClick={() =>
                  setData({
                    ...data,
                    [kind]: [
                      ...data[kind],
                      {
                        entry_id: crypto.randomUUID(),
                        organization: "",
                        role: "",
                        description: "",
                        fact_ids: [],
                      },
                    ],
                  })
                }
              >
                +
              </button>
            </div>
          </Section>
        ))}
        <Section
          title="技能"
          actions={singleton(["skills_text", "skills"], { skills_text: "", skills: [] })}
        >
          <Field label="技能">
            <textarea
              rows={5}
              className={control}
              value={data.skills_text || ""}
              onChange={(e) =>
                setData({
                  ...data,
                  skills_text: e.target.value,
                  skills: e.target.value
                    .split("\n")
                    .map((line) => line.trim())
                    .filter(Boolean),
                })
              }
            />
          </Field>
        </Section>
        <Section title="求职偏好" actions={singleton(["preferences"], { preferences: {} })}>
          <div className="grid gap-4 sm:grid-cols-2">
            {preferenceFields.map(([key, label]) => (
              <Field key={key} label={`${label}（选填）`}>
                <input
                  className={control}
                  value={data.preferences[key] || ""}
                  onChange={(e) =>
                    setData({
                      ...data,
                      preferences: { ...data.preferences, [key]: e.target.value },
                    })
                  }
                />
              </Field>
            ))}
          </div>
        </Section>
      </fieldset>
      <InlineError message={action.error ? "保存失败，请重试" : undefined} />
      {notice && (
        <p
          role="status"
          className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-control border border-line bg-paper px-5 py-3 text-sm shadow-sm"
        >
          {notice}
        </p>
      )}
      <div className="flex justify-center gap-4 py-8">
        <Button
          variant="primary"
          disabled={action.busy || photoBusy}
          onClick={() => {
            if (
              !data.display_name.trim() ||
              [...data.education, ...data.experiences, ...data.projects].some(
                (entry) => !entry.organization.trim(),
              )
            ) {
              setInvalid(true);
              return;
            }
            void action.run(async () => {
              const saved = await persist(data);
              done(
                await api<NamedProfile>(`${path}/commit`, "POST", {
                  edit_id: saved.id,
                  expected_revision: saved.revision,
                }),
              );
            });
          }}
        >
          保存
        </Button>
        <Button
          disabled={action.busy || photoBusy}
          onClick={() =>
            void action.run(async () =>
              done(
                await api<NamedProfile>(`${path}/cancel`, "POST", {
                  edit_id: session.id,
                  expected_revision: session.revision,
                }),
              ),
            )
          }
        >
          取消
        </Button>
      </div>
    </div>
  );
}

export function ProfileView({ data }: { data: Data }) {
  return (
    <div>
      <Section title="个人信息">
        <h3 className="font-serif text-xl">{data.display_name || "未填写"}</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {personalFields
            .filter(([key]) => key !== "display_name")
            .map(([key, label]) =>
              key !== "display_name" && data.personal[key] ? (
                <p key={key} className="break-words">
                  {label}：{data.personal[key]}
                </p>
              ) : null,
            )}
        </div>
        {data.personal.photo_id && <PhotoPreview id={data.personal.photo_id} />}
      </Section>
      {(["education", "experiences", "projects"] as const).map((kind) => (
        <Section title={titles[kind]} key={kind}>
          {data[kind].map((entry, i) => (
            <div key={entry.entry_id || i} className="mb-4 space-y-1">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <strong>{entry.organization}</strong>
                <span>
                  {kind === "education"
                    ? [entry.degree, entry.major].filter(Boolean).join(" · ")
                    : entry.role}
                </span>
                <span className="ml-auto whitespace-nowrap text-sm text-secondary">
                  {[entry.start_date, entry.end_date].filter(Boolean).join(" – ")}
                </span>
              </div>
              {entry.technology_stack && (
                <p className="text-sm text-secondary">{entry.technology_stack}</p>
              )}
              {[entry.description, entry.achievements].filter(Boolean).map((value, n) => (
                <p key={n} className="whitespace-pre-wrap">
                  {value}
                </p>
              ))}
            </div>
          ))}
        </Section>
      ))}
      <Section title="技能">
        <p className="whitespace-pre-wrap">{data.skills_text || data.skills.join("\n")}</p>
      </Section>
      <Section title="求职偏好">
        {preferenceFields.map(([key, label]) =>
          data.preferences[key] ? (
            <p key={key}>
              {label}：{data.preferences[key]}
            </p>
          ) : null,
        )}
      </Section>
    </div>
  );
}
