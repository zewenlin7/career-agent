"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import type {
  Context,
  Page,
  Profile,
  ResumeChoice,
  Variant,
  Render,
  Submission,
  PackageRow,
  PackageView,
} from "./contracts";
import { api, useRead, useAction, useRequestId, ApiError } from "./client";
import {
  BindingFields,
  Panel,
  Select,
  Pages,
  ReadState,
  ErrorNotice,
  Status,
  Refs,
  Field,
  control,
} from "./ui";
import { PdfLinks, ResumeContent, readSubmissions } from "./results";
import { PreparationPage } from "./preparation";
export function ResumePage({ ctx }: { ctx: Context }) {
  const [profile, setProfile] = useState(""),
    [offset, setOffset] = useState(0),
    [po, setPo] = useState(0),
    [choice, setChoice] = useState<ResumeChoice>();
  const profiles = useRead<Page<Profile>>(`profile/revisions?limit=10&offset=${po}`),
    rows = useRead<ResumeChoice[]>(
      profile
        ? `resume-revisions?profile_id=${profile}&job_revision_id=${ctx.job.job_revision_id}&limit=10&offset=${offset}`
        : null,
    );
  return (
    <div className="space-y-6">
      <PreparationPage ctx={ctx} target="resume_tailoring" />
      <Panel title="Resume variant / revision 历史">
        <Select
          label="查看哪个 Profile 的简历"
          value={profile}
          onChange={(e) => {
            setProfile(e.target.value);
            setChoice(undefined);
            setOffset(0);
          }}
        >
          <option value="">请选择 Profile</option>
          {profiles.data?.items.map((p) => (
            <option key={p.id} value={p.id}>
              {p.data.display_name} · revision {p.revision}
            </option>
          ))}
        </Select>
        <ErrorNotice code={profiles.error} />
        {profiles.data && <Pages offset={po} setOffset={setPo} more={profiles.data.has_more} />}
        <ReadState
          loaded={!profile || !!rows.data}
          error={rows.error}
          empty={rows.data?.length === 0}
        />
        <ul className="space-y-2">
          {rows.data?.map((r) => (
            <li key={r.resume_revision_id}>
              <Button onClick={() => setChoice(r)}>
                revision {r.revision} · {r.hints.same_job ? "同一 Job" : "其他来源 / base"} ·{" "}
                {r.resume_revision_id}
              </Button>
            </li>
          ))}
        </ul>
        {rows.data && (
          <Pages offset={offset} setOffset={setOffset} more={rows.data.length === 10} />
        )}
        <p className="text-sm">
          列表展示 exact revision；没有通用 current / selected pointer。不同 variant 的 revision
          不构成同一条历史。
        </p>
        {choice && <VariantDetail key={choice.resume_revision_id} choice={choice} ctx={ctx} />}
      </Panel>
    </div>
  );
}
function VariantDetail({ choice, ctx }: { choice: ResumeChoice; ctx: Context }) {
  const variant = useRead<Variant>(
      `resume-variants/${choice.resume_variant_id}?revision=${choice.revision}`,
    ),
    [render, setRender] = useState<Render>(),
    [offset, setOffset] = useState(0);
  const submissions = useRead<Submission[]>(
      `applications/${ctx.application.id}/submissions`,
      readSubmissions,
    ),
    action = useAction();
  const used =
    submissions.data?.filter((s) => s.resume_revision_id === choice.resume_revision_id) || [];
  const invalid = variant.data && variant.data.resume_revision_id !== choice.resume_revision_id;
  return (
    <section className="space-y-4">
      <ReadState
        loaded={!!variant.data}
        error={invalid ? "context_revision_mismatch" : variant.error}
      />
      {variant.data && !invalid && (
        <>
          <Refs
            values={{
              resume_variant_id: variant.data.id,
              resume_revision_id: variant.data.resume_revision_id,
              revision: variant.data.revision,
              profile_id: variant.data.document.profile_id,
              profile_revision: variant.data.document.profile_revision,
              job_revision_id: variant.data.document.job_revision_id,
            }}
          />
          <ResumeContent content={variant.data.document} />
          <Button
            disabled={action.busy}
            onClick={() =>
              void action.run(async () =>
                setRender(
                  await api<Render>(`resume-variants/${choice.resume_variant_id}/render`, "POST", {
                    revision: choice.revision,
                  }),
                ),
              )
            }
          >
            渲染此 exact revision 的 PDF
          </Button>
          <ErrorNotice code={action.error} />
          {action.busy && <p role="status">正在编译 PDF…</p>}
          {render && (
            <>
              <Status value={render.report.render_status} />
              <p className="text-sm break-all">
                RenderArtifact：{render.id} · 页数 {render.report.page_count ?? "未知"}
              </p>
              {render.report.render_status === "accepted" ? (
                <PdfLinks id={render.id} />
              ) : (
                <p>PDF 未通过验收，不提供下载。{render.report.error_code}</p>
              )}
            </>
          )}
        </>
      )}
      <h3 className="font-semibold">实际使用核对</h3>
      <ReadState loaded={!!submissions.data} error={submissions.error} />
      {submissions.data && (
        <>
          <p className="text-sm">
            {used.length
              ? `已用于真实 Submission · 共 ${used.length} 条匹配记录`
              : "完整读取当前 Application 的投递记录后，未发现该 revision 被使用。"}
          </p>
          {used.slice(offset, offset + 10).map((s) => (
            <Refs
              key={s.id}
              values={{
                submission_id: s.id,
                render_artifact_id: s.render_artifact_id,
                created_at: s.created_at,
              }}
            />
          ))}
          <Pages offset={offset} setOffset={setOffset} more={used.length > offset + 10} />
        </>
      )}
    </section>
  );
}
export function SubmissionsPage({ ctx }: { ctx: Context }) {
  const [offset, setOffset] = useState(0),
    [profile, setProfile] = useState(""),
    [resume, setResume] = useState(""),
    [pdf, setPdf] = useState(""),
    [greeting, setGreeting] = useState(""),
    [packageId, setPackageId] = useState(""),
    [sourcePackage, setSourcePackage] = useState(""),
    [po, setPo] = useState(0),
    [note, setNote] = useState(""),
    [saved, setSaved] = useState<Submission>();
  const rows = useRead<Page<Submission>>(
      `applications/${ctx.application.id}/submissions?limit=10&offset=${offset}`,
    ),
    app = useRead<{ revision: number; status: string }>(`applications/${ctx.application.id}`),
    packages = useRead<PackageRow[]>(
      `applications/${ctx.application.id}/preparation-packages?limit=10&offset=${po}`,
    ),
    detail = useRead<PackageView>(
      sourcePackage ? `preparation-artifacts/${sourcePackage}/product-view` : null,
    );
  const action = useAction(),
    requestId = useRequestId(),
    router = useRouter();
  const submit = () =>
    action.run(async () => {
      if (!app.data) throw new ApiError("application_unavailable");
      const body = {
        expected_revision: app.data.revision,
        resume_revision_id: resume,
        render_artifact_id: pdf,
        greeting_id: greeting || null,
        package_id: packageId || null,
        note: note || null,
      };
      const result = await api<Submission>(
        `applications/${ctx.application.id}/submissions`,
        "POST",
        { ...body, request_id: requestId(body) },
      );
      setSaved(result);
      rows.reload();
      app.reload();
      router.refresh();
    });
  return (
    <div className="space-y-6">
      <Panel title="记录真实投递">
        <p>
          仅在你确实已经投递后记录。后端会记录投递事件并按生命周期更新为
          applied；生成、预览或下载材料不会触发此动作。
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          key={saved?.id || "draft"}
          className="max-w-[760px] space-y-4"
        >
          <fieldset disabled={action.busy || !!saved} className="space-y-4">
            <BindingFields
              ctx={ctx}
              profile={profile}
              setProfile={setProfile}
              resume={resume}
              setResume={(s) => {
                setResume(s);
                setPdf("");
                setGreeting("");
                setPackageId("");
              }}
            />
            <Select
              label="查看准备 package 中的 exact 材料（可选）"
              value={sourcePackage}
              onChange={(e) => setSourcePackage(e.target.value)}
            >
              <option value="">不使用 package</option>
              {packages.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.id}
                </option>
              ))}
            </Select>
            <ErrorNotice code={packages.error} />
            {packages.data && (
              <Pages offset={po} setOffset={setPo} more={packages.data.length === 10} />
            )}
            <ErrorNotice code={detail.error} />
            {detail.data && (
              <div className="space-y-2">
                {detail.data.results
                  .filter(
                    (r) =>
                      r.resume_revision_id === resume && r.download_url && r.render_artifact_id,
                  )
                  .map((r) => (
                    <Button
                      key={r.kind}
                      onClick={() => {
                        setPdf(r.render_artifact_id!);
                        setPackageId(sourcePackage);
                      }}
                    >
                      使用此 package 的 PDF：{r.render_artifact_id}
                    </Button>
                  ))}
                {detail.data.results
                  .filter(
                    (r) =>
                      r.kind === "greeting_generation" &&
                      r.source_resume_revision_id === resume &&
                      r.result_id,
                  )
                  .map((r) => (
                    <Button
                      key={r.kind}
                      onClick={() => {
                        setGreeting(r.result_id!);
                      }}
                    >
                      使用 Greeting：{r.result_id}
                    </Button>
                  ))}
              </div>
            )}
            <Field label="实际使用的 accepted RenderArtifact ID">
              <input
                className={control}
                required
                value={pdf}
                pattern="[0-9a-fA-F-]{36}"
                onChange={(e) => setPdf(e.target.value)}
              />
            </Field>
            <Field label="Greeting result ID（可选，不是 target wrapper ID）">
              <input
                className={control}
                value={greeting}
                pattern="[0-9a-fA-F-]{36}"
                onChange={(e) => setGreeting(e.target.value)}
              />
            </Field>
            <Field label="关联 package ID（可选）">
              <input
                className={control}
                value={packageId}
                pattern="[0-9a-fA-F-]{36}"
                onChange={(e) => setPackageId(e.target.value)}
              />
            </Field>
            <Field label="投递记录说明（可选）">
              <textarea
                className={control}
                maxLength={20000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </Field>
            <p className="text-sm">
              Application revision：{app.data?.revision ?? "正在读取"}。服务端核验 exact
              Resume/PDF/Greeting/package 关系；冲突时不会自动重新提交。
            </p>
            <ErrorNotice code={app.error} />
            <label className="flex gap-2">
              <input type="checkbox" required />
              确认这是已经发生的实际投递
            </label>
            <Button type="submit" variant="primary" disabled={!app.data}>
              记录真实 Submission
            </Button>
            <Button onClick={app.reload}>重新读取 Application revision</Button>
          </fieldset>
        </form>
        <ErrorNotice code={action.error} />
        {saved && <Button onClick={() => setSaved(undefined)}>开始另一条投递记录</Button>}
        {saved && (
          <p role="status" className="break-all">
            已记录 Submission {saved.id}，关联事件 {saved.event_id}。
          </p>
        )}
      </Panel>
      <Panel title="实际投递历史">
        <ReadState loaded={!!rows.data} error={rows.error} empty={rows.data?.items.length === 0} />
        {rows.data?.items.map((s) => (
          <article key={s.id} className="space-y-3 border-b border-line pb-4">
            <p>{s.created_at}</p>
            {s.note && <p>{s.note}</p>}
            <Refs values={s} />
            <PdfLinks id={s.render_artifact_id} />
          </article>
        ))}
        {rows.data && <Pages offset={offset} setOffset={setOffset} more={rows.data.has_more} />}
      </Panel>
    </div>
  );
}
