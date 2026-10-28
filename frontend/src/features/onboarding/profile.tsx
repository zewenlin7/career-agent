"use client";
import { DraftAction } from "@/features/workspace/draft-action";
import { ResumeContent } from "@/features/workspace/results";
import { canonical } from "./drafts";
import { useState } from "react";
import Link from "next/link";
import { PageHeading } from "@/components/ui/typography";
import { api, useRead, useAction } from "@/features/workspace/client";
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
import type { Page } from "@/features/workspace/contracts";
import {
  blankProfile,
  type Profile,
  type ProfileData,
  type Fact,
  type Experience,
} from "./contracts";
import { FactPicker } from "./fact-picker";
import { BaseResumes } from "./resumes";
export async function readAllFacts(_path: string, signal: AbortSignal): Promise<Fact[]> {
  const found: Fact[] = [];
  for (let offset = 0; ; offset += 100) {
    const rows = await api<Fact[]>(`facts?limit=100&offset=${offset}`, "GET", undefined, signal);
    found.push(...rows);
    if (rows.length < 100) return found;
  }
}
export function ProfilePage() {
  const current = useRead<Profile>("profile"),
    facts = useRead<Fact[]>("facts", readAllFacts),
    [historyOffset, setHistoryOffset] = useState(0),
    [selected, setSelected] = useState(""),
    [editing, setEditing] = useState(false);
  const history = useRead<Page<Profile>>(`profile/revisions?limit=10&offset=${historyOffset}`),
    historical = useRead<Profile>(selected ? `profile/revisions/${selected}` : null);
  const refresh = () => {
    current.reload();
    facts.reload();
    history.reload();
  };
  return (
    <>
      <PageHeading title="个人资料" description="整理经历与事实，让申请材料有据可依。" />
      <div className="space-y-6">
        <Panel title="个人资料">
          <Button onClick={refresh}>刷新资料</Button>
          {current.error === "not_found" ? (
            <p>先创建个人资料，再添加并确认你的经历事实。</p>
          ) : (
            <ReadState loaded={!!current.data} error={current.error} />
          )}
          <ErrorNotice code={facts.error} />
          {current.data && !editing && (
            <>
              <ProfileDetail profile={current.data} />
              <Button onClick={() => setEditing(true)}>编辑个人资料</Button>
            </>
          )}
          {(editing || current.error === "not_found") && facts.data && (
            <ProfileEditor
              key={current.data?.id || "new"}
              profile={current.data}
              facts={facts.data}
              onSaved={() => {
                setEditing(false);
                refresh();
              }}
            />
          )}
          {editing && <Button onClick={() => setEditing(false)}>取消编辑</Button>}
        </Panel>
        {current.data && (
          <Panel title="从经历整理事实">
            <DraftAction
              key={current.data.id}
              task="profile_fact_extraction"
              profileId={current.data.id}
              profileRevision={current.data.revision}
              label="AI 提取经历事实"
              onSaved={refresh}
              render={(output) => (
                <ul className="space-y-2">
                  {(output.facts as { statement: string }[]).map((f, i) => (
                    <li key={i}>{f.statement}</li>
                  ))}
                </ul>
              )}
            />
          </Panel>
        )}
        <FactsManager facts={facts.data} error={facts.error} onChanged={refresh} />
        {current.data && (
          <Panel title="生成基础简历草稿">
            <DraftAction
              key={current.data.id}
              task="base_resume_drafting"
              profileId={current.data.id}
              label="AI 整理基础简历"
              render={(output) => <ResumeContent content={output} />}
              onSaved={refresh}
            />
          </Panel>
        )}
        <details className="rounded-control border border-line p-4">
          <summary className="cursor-pointer">查看资料历史版本</summary>
          <Panel title="资料历史">
            <ReadState loaded={!!history.data} error={history.error} />
            <ul className="space-y-2">
              {history.data?.items.map((p) => (
                <li key={p.id}>
                  <Button onClick={() => setSelected(p.id)}>
                    查看第 {p.revision} 版 · {p.data.display_name}
                  </Button>
                </li>
              ))}
            </ul>
            {history.data && (
              <Pages
                offset={historyOffset}
                setOffset={setHistoryOffset}
                more={history.data.has_more}
              />
            )}{" "}
            {selected && (
              <>
                <ReadState loaded={!!historical.data} error={historical.error} />
                {historical.data && <ProfileDetail profile={historical.data} />}
              </>
            )}
          </Panel>
        </details>
        <section id="base-resumes" className="scroll-mt-6">
          <BaseResumes
            key={current.data?.id || "empty"}
            currentProfile={current.data}
            facts={facts.data || []}
            factsError={facts.error}
            factsLoaded={!!facts.data}
          />
        </section>
        <Link
          href="/applications/new"
          className="inline-flex min-h-11 items-center text-accent-ink underline"
        >
          添加求职职位
        </Link>
      </div>
    </>
  );
}
function ProfileEditor({
  profile,
  facts,
  onSaved,
}: {
  profile?: Profile;
  facts: Fact[];
  onSaved: () => void;
}) {
  const [data, setData] = useState<ProfileData>(() =>
      structuredClone(profile?.data || blankProfile()),
    ),
    [preferences, setPreferences] = useState(
      JSON.stringify(profile?.data.preferences || {}, null, 2),
    ),
    [saved, setSaved] = useState(false);
  const action = useAction();
  let dirty = true;
  try {
    dirty =
      !profile ||
      canonical({
        ...data,
        skills: data.skills.map((s) => s.trim()).filter(Boolean),
        preferences: JSON.parse(preferences),
      }) !== canonical(profile.data);
  } catch {
    /* Invalid editing input is rejected by submission validation. */
  }
  const edit = (key: "education" | "experiences" | "projects", index: number, value: Experience) =>
    setData((d) => ({ ...d, [key]: d[key].map((e, i) => (i === index ? value : e)) }));
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!dirty) return;
        void action.run(async () => {
          await api("profile", "PUT", {
            expected_revision: profile?.revision || 0,
            data: {
              ...data,
              skills: data.skills.map((s) => s.trim()).filter(Boolean),
              preferences: JSON.parse(preferences),
            },
          });
          setSaved(true);
          onSaved();
        });
      }}
    >
      <fieldset disabled={action.busy || saved} className="min-w-0 space-y-5">
        <p className="text-sm text-secondary">填写你的基本资料。</p>
        <Field label="姓名">
          <input
            required
            maxLength={200}
            className={control}
            value={data.display_name}
            onChange={(e) => setData({ ...data, display_name: e.target.value })}
          />
        </Field>
        {(
          [
            ["education", "教育经历"],
            ["experiences", "工作经历"],
            ["projects", "项目经历"],
          ] as const
        ).map(([key, label]) => (
          <section key={key} className="space-y-3">
            <h3 className="font-semibold">{label}</h3>
            {data[key].map((entry, i) => (
              <div key={i} className="space-y-3 rounded-control border border-line p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label={`${label} ${i + 1} · 单位名称`}>
                    <input
                      required
                      maxLength={200}
                      className={control}
                      value={entry.organization}
                      onChange={(e) => edit(key, i, { ...entry, organization: e.target.value })}
                    />
                  </Field>
                  <Field label={`${label} ${i + 1} · 职位或角色`}>
                    <input
                      required
                      maxLength={200}
                      className={control}
                      value={entry.role}
                      onChange={(e) => edit(key, i, { ...entry, role: e.target.value })}
                    />
                  </Field>
                </div>
                <Field label={`${label} ${i + 1} · 经历描述`}>
                  <textarea
                    maxLength={20000}
                    className={control}
                    value={entry.description}
                    onChange={(e) => edit(key, i, { ...entry, description: e.target.value })}
                  />
                </Field>
                <FactPicker
                  facts={facts}
                  value={entry.fact_ids}
                  onChange={(ids) => edit(key, i, { ...entry, fact_ids: ids })}
                />
                <Button
                  onClick={() => setData({ ...data, [key]: data[key].filter((_, n) => n !== i) })}
                >
                  移除{label} {i + 1}
                </Button>
              </div>
            ))}
            <Button
              onClick={() =>
                setData({
                  ...data,
                  [key]: [
                    ...data[key],
                    { organization: "", role: "", description: "", fact_ids: [] },
                  ],
                })
              }
            >
              添加{label}
            </Button>
          </section>
        ))}
        <Field label="技能（每行一项）">
          <textarea
            className={control}
            value={data.skills.join("\n")}
            onChange={(e) => setData({ ...data, skills: e.target.value.split("\n") })}
          />
        </Field>
        <p className="text-sm text-secondary">请把简历中需要使用的经历关联到已确认的事实。</p>
        <details>
          <summary className="cursor-pointer">偏好设置（高级）</summary>
          <p className="text-sm text-secondary">自由记录偏好，暂不用于自动筛选岗位。</p>
          <Field label="偏好设置 JSON">
            <textarea
              className={control}
              value={preferences}
              onChange={(e) => setPreferences(e.target.value)}
            />
          </Field>
        </details>
        <Button type="submit" disabled={!dirty}>
          {action.busy ? "正在保存…" : profile ? "保存资料" : "创建个人资料"}
        </Button>
      </fieldset>
      <ErrorNotice code={action.error} />
      {action.error === "revision_conflict" && (
        <p className="text-sm">
          当前草稿仍保留。刷新资料会加载已提交版本，请先复制需要保留的编辑内容。
        </p>
      )}
      {saved && <p role="status">资料已保存。</p>}
    </form>
  );
}
function ProfileDetail({ profile }: { profile: Profile }) {
  return (
    <div className="space-y-3">
      <h3 className="font-semibold">
        {profile.data.display_name} · 第 {profile.revision} 版
      </h3>
      <Refs
        values={{
          profile_id: profile.id,
          revision: profile.revision,
          created_at: profile.created_at,
        }}
      />
      {(["education", "experiences", "projects"] as const).map((k) => (
        <div key={k}>
          <h4>{{ education: "教育经历", experiences: "工作经历", projects: "项目经历" }[k]}</h4>
          {profile.data[k].map((e, i) => (
            <div key={i} className="mt-2 border-l border-line pl-3">
              <p>
                {e.organization} · {e.role}
              </p>
              <p className="whitespace-pre-wrap">{e.description}</p>
              <Refs values={{ fact_ids: e.fact_ids }} />
            </div>
          ))}
        </div>
      ))}
      <p>技能：{profile.data.skills.join(" / ") || "未填写"}</p>
      <Refs values={{ preferences: profile.data.preferences }} />
    </div>
  );
}
function FactsManager({
  facts,
  error,
  onChanged,
}: {
  facts?: Fact[];
  error?: string;
  onChanged: () => void;
}) {
  const action = useAction(),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<Fact>(),
    [created, setCreated] = useState(false);
  return (
    <Panel title="经历事实">
      <p className="text-sm text-secondary">请核对以下经历，确认准确后再用于简历。</p>
      <details>
        <summary className="cursor-pointer text-sm">手工补充事实</summary>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget,
              f = new FormData(form);
            void action.run(async () => {
              await api("facts", "POST", {
                statement: f.get("statement"),
                category: f.get("category"),
              });
              form.reset();
              setCreated(true);
              onChanged();
            });
          }}
        >
          <Field label="事实描述">
            <textarea name="statement" required maxLength={20000} className={control} />
          </Field>
          <Field label="事实类别">
            <input name="category" required maxLength={200} className={control} />
          </Field>
          <Button type="submit" disabled={action.busy}>
            添加待确认事实
          </Button>
          <ErrorNotice code={action.error} />
          {action.error && (
            <p className="text-sm">没有自动重试。若连接中断，先刷新事实列表核对是否已创建。</p>
          )}
          {created && <p role="status">事实已添加，请核对后确认。</p>}
        </form>
      </details>
      <ReadState loaded={!!facts} error={error} empty={facts?.length === 0} />
      <ul className="space-y-3">
        {facts?.slice(offset, offset + 10).map((f) => (
          <li key={f.id} className="space-y-2 border-t border-line pt-3">
            <p className="whitespace-pre-wrap break-words">{f.statement}</p>
            <p className="text-sm">
              {(
                {
                  skill: "技能",
                  experience: "工作经历",
                  project: "项目",
                  education: "教育经历",
                } as Record<string, string>
              )[f.category] || f.category}{" "}
              ·{" "}
              {
                (
                  {
                    proposed: "待确认",
                    verified: "已确认",
                    rejected: "不采用",
                    superseded: "已更正",
                  } as Record<string, string>
                )[f.status]
              }
            </p>
            <Refs
              values={{
                fact_id: f.id,
                lineage_id: f.lineage_id,
                replaces_id: f.replaces_id,
                verified_at: f.verified_at,
              }}
            />
            <Button onClick={() => setSelected(f)}>管理事实 {f.statement.slice(0, 40)}</Button>
          </li>
        ))}
      </ul>
      <Pages offset={offset} setOffset={setOffset} more={(facts?.length || 0) > offset + 10} />
      {selected && (
        <FactActions
          key={`${selected.id}:${facts?.find((f) => f.id === selected.id)?.status}`}
          fact={facts?.find((f) => f.id === selected.id) || selected}
          onChanged={onChanged}
        />
      )}
    </Panel>
  );
}
function FactActions({ fact, onChanged }: { fact: Fact; onChanged: () => void }) {
  const [operation, setOperation] = useState(""),
    [confirm, setConfirm] = useState(false),
    [done, setDone] = useState(false);
  const action = useAction();
  return (
    <section className="space-y-3 border-t border-line pt-4" aria-label="事实生命周期操作">
      <p>{fact.statement}</p>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          void action.run(async () => {
            await api(
              `facts/${fact.id}/${operation}`,
              "POST",
              operation === "supersede"
                ? {
                    expected_revision: fact.revision,
                    statement: f.get("replacement"),
                    category: f.get("category"),
                  }
                : {},
            );
            setDone(true);
            setConfirm(false);
            onChanged();
          });
        }}
      >
        <Select
          label="事实操作"
          value={operation}
          onChange={(e) => {
            setOperation(e.target.value);
            setConfirm(false);
          }}
        >
          <option value="">请选择操作</option>
          {fact.status === "proposed" && <option value="verify">确认属实</option>}
          {["proposed", "verified"].includes(fact.status) && (
            <option value="reject">标为不采用</option>
          )}
          {fact.status === "verified" && <option value="supersede">更正事实内容</option>}
        </Select>
        {operation === "supersede" && (
          <>
            <Field label="替代后的事实描述">
              <textarea
                name="replacement"
                required
                maxLength={20000}
                defaultValue={fact.statement}
                className={control}
              />
            </Field>
            <Field label="事实类别">
              <input
                name="category"
                required
                maxLength={200}
                defaultValue={fact.category}
                className={control}
              />
            </Field>
          </>
        )}
        <label className="flex gap-2 text-sm">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          我已核对这项事实
        </label>
        <Button type="submit" disabled={!operation || !confirm || done || action.busy}>
          确认操作
        </Button>
        <ErrorNotice code={action.error} />
        {done && <p role="status">操作已提交，请按最新状态继续。</p>}
      </form>
    </section>
  );
}
