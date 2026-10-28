/** Empty-store fixture. No authoritative Profile/Fact/Resume/Job exists until a UI write. */
import { id, time } from "./product-api.ts";
import { workspaceResponse, resetWorkspace, profileRow } from "./workspace-api.ts";
import type {
  Fact,
  Profile,
  Variant,
  ResumeDocument,
} from "../../src/features/onboarding/contracts.ts";
import { linkedFacts, transitions } from "../../src/features/onboarding/contracts.ts";
import type { ApplicationStatus } from "../../src/features/applications/contracts.ts";
type D = Record<string, unknown>;
type Reply = { status: number; body: unknown; sse?: string; pdf?: boolean };
let blank = false,
  seq = 51000,
  researchReady = false;
const profiles: Profile[] = [],
  facts: Fact[] = [],
  variants: Variant[] = [],
  companies: D[] = [],
  jobs: D[] = [],
  apps: D[] = [],
  receipts = new Map<string, D>();
const operations = new Map<string, D>();
const bindings = new Map<string, D>();
export function resetOnboarding(empty = false) {
  blank = empty;
  seq = 51000;
  researchReady = false;
  profiles.length = 0;
  facts.length = 0;
  variants.length = 0;
  companies.length = 0;
  jobs.length = 0;
  apps.length = 0;
  receipts.clear();
  operations.clear();
  bindings.clear();
  if (empty) resetWorkspace();
}
const uid = () => id(seq++),
  ok = (body: unknown, status = 200): Reply => ({ status, body }),
  fail = (code: string, status = 409) => ok({ error: { code } }, status);
const page = (rows: unknown[], q: URLSearchParams) => {
  const limit = Number(q.get("limit") || 50),
    offset = Number(q.get("offset") || 0);
  return {
    items: rows.slice(offset, offset + limit),
    limit,
    offset,
    has_more: rows.length > offset + limit,
  };
};
const slice = (rows: unknown[], q: URLSearchParams) => page(rows, q).items;
function addEvent(app: D, kind: string, to: string | null, note: unknown = null) {
  const event = {
    id: uid(),
    application_id: app.id,
    created_at: time(),
    sequence: app.revision,
    kind,
    from_status: kind === "status_changed" || kind === "correction" ? app.status : null,
    to_status: to,
    note,
  };
  (app.events as D[]).push(event);
  if (to) app.status = to;
  return event;
}
export function onboardingResponse(url: URL, method: string, body: D): Reply | undefined {
  const p = url.pathname.replace("/api/v1/", ""),
    q = url.searchParams;
  if (/^applications\/[^/]+\/context$/.test(p) && blank) {
    const app = apps.find((item) => item.id === p.split("/")[1]);
    if (!app) return fail("not_found", 404);
    const job = jobs.find((item) => item.id === app.job_id)!;
    let binding = bindings.get(String(app.id));
    if (!binding) {
      binding = {
        application_id: app.id,
        revision: 1,
        profile_id: profiles.at(-1)?.id || null,
        profile_revision: profiles.at(-1)?.revision || null,
        profile_name: profiles.at(-1)?.data.display_name || null,
        resume_revision_id: null,
        resume_name: null,
        resume_revision: null,
        job_revision_id: job.job_revision_id,
        job_revision: job.revision,
      };
      bindings.set(String(app.id), binding);
    }
    if (method === "PUT") {
      if (body.expected_revision !== binding.revision) return fail("revision_conflict");
      Object.assign(binding, body, { revision: Number(binding.revision) + 1 });
      const resume = variants.find((v) => v.resume_revision_id === body.resume_revision_id);
      binding.profile_id = resume?.document.profile_id || null;
      binding.resume_name = resume?.document.metadata.label || null;
      binding.resume_revision = resume?.revision || null;
    }
    return ok(binding);
  }
  if (p === "profile-library" && blank)
    return ok(
      page(
        profiles.map((v) => ({ id: v.id, name: v.data.display_name, profile_id: v.id })),
        q,
      ),
    );
  if (p === "resume-library/versions" && blank)
    return ok(
      page(
        variants.map((v) => ({
          id: v.resume_revision_id,
          variant_id: v.id,
          revision: v.revision,
          name: v.document.metadata.label,
          metadata_revision: 1,
          created_at: v.created_at,
          profile_id: v.document.profile_id,
        })),
        q,
      ),
    );
  if (p === "resume-library" && (blank || variants.length))
    return ok(
      page(
        [...new Map(variants.map((v) => [v.id, v])).values()].reverse().map((v) => ({
          resume_variant_id: v.id,
          resume_revision_id: v.resume_revision_id,
          revision: v.revision,
          profile_id: v.document.profile_id,
          label: v.document.metadata.label,
          created_at: v.created_at,
        })),
        q,
      ),
    );
  if (p === "profile" && method === "GET")
    return profiles.length ? ok(profiles.at(-1)) : blank ? fail("not_found", 404) : ok(profileRow);
  if (p === "profile" && method === "PUT") {
    const current = profiles.at(-1)?.revision || (blank ? 0 : 1);
    if (body.expected_revision !== current) return fail("revision_conflict");
    const data = body.data as Profile["data"];
    if (!data.display_name?.trim()) return fail("validation_error", 422);
    if (linkedFacts(data).some((ref) => !facts.some((f) => f.id === ref)))
      return fail("not_found", 404);
    if (JSON.stringify(profiles.at(-1)?.data) === JSON.stringify(data)) return ok(profiles.at(-1));
    const profile = {
      id: id(9001 + profiles.length),
      revision: current + 1,
      created_at: time(),
      data: structuredClone(data),
    };
    profiles.push(profile);
    return ok(profile);
  }
  if (p === "profile/revisions" && (blank || profiles.length))
    return ok(page([...profiles].reverse(), q));
  if (p.startsWith("profile/revisions/")) {
    const profile = profiles.find((r) => r.id === p.split("/")[2]);
    return profile
      ? ok(profile)
      : !blank && p.endsWith(profileRow.id)
        ? ok(profileRow)
        : fail("not_found", 404);
  }
  if (p === "facts" && method === "GET") return ok(slice(facts, q));
  if (p === "facts" && method === "POST") {
    const f: Fact = {
      id: id(9010 + facts.length),
      created_at: time(),
      lineage_id: uid(),
      revision: 1,
      statement: String(body.statement),
      category: String(body.category),
      status: "proposed",
      replaces_id: null,
      verified_at: null,
    };
    facts.push(f);
    return ok(f, 201);
  }
  let match = p.match(/^facts\/([^/]+)\/(verify|reject|supersede)$/);
  if (match) {
    const f = facts.find((f) => f.id === match![1]);
    if (!f) return fail("not_found", 404);
    const kind = match[2];
    if (kind === "verify") {
      if (f.status !== "proposed") return fail("invalid_fact_transition");
      f.status = "verified";
      f.verified_at = time();
      return ok(f);
    }
    if (kind === "reject") {
      if (!["proposed", "verified"].includes(f.status)) return fail("invalid_fact_transition");
      f.status = "rejected";
      return ok(f);
    }
    if (body.expected_revision !== f.revision) return fail("revision_conflict");
    if (f.status !== "verified") return fail("invalid_fact_transition");
    f.status = "superseded";
    const replacement = {
      ...f,
      id: id(9010 + facts.length),
      revision: f.revision + 1,
      statement: String(body.statement),
      category: String(body.category),
      status: "proposed" as const,
      replaces_id: f.id,
      verified_at: null,
    };
    facts.push(replacement);
    return ok(replacement, 201);
  }
  if (
    (p === "resume-variants" && method === "POST") ||
    (/^resume-variants\/[^/]+\/revisions$/.test(p) && method === "POST")
  ) {
    const creating = p === "resume-variants",
      document = (creating ? body : body.document) as ResumeDocument;
    const profile = profiles.find((r) => r.id === document.profile_id);
    if (!profile || profile.revision !== document.profile_revision)
      return fail("invalid_variant", 422);
    const variantId = creating ? id(8400 + variants.length * 100) : p.split("/")[1];
    const prior = variants.filter((v) => v.id === variantId).at(-1);
    if (!creating && (!prior || body.expected_revision !== prior.revision))
      return fail("revision_conflict");
    if (!document.sections.length || document.sections.some((s) => !s.items.length))
      return fail("validation_error", 422);
    const row: Variant = {
      id: variantId,
      resume_revision_id: creating ? id(8401 + variants.length * 100) : uid(),
      revision: (prior?.revision || 0) + 1,
      created_at: time(),
      document: structuredClone(document),
    };
    variants.push(row);
    return ok(row, 201);
  }
  if (p === "resume-revisions" && (blank || variants.length))
    return ok(
      slice(
        [...variants]
          .reverse()
          .filter((v) => !q.get("variant_id") || v.id === q.get("variant_id"))
          .filter((v) => !q.get("profile_id") || v.document.profile_id === q.get("profile_id"))
          .map((v) => ({
            resume_revision_id: v.resume_revision_id,
            resume_variant_id: v.id,
            revision: v.revision,
            profile_id: v.document.profile_id,
            job_revision_id: v.document.job_revision_id,
            created_at: v.created_at,
            hints: {
              original: v.document.job_revision_id === null,
              same_jd: v.document.job_revision_id === q.get("job_revision_id"),
              same_job: !!v.document.job_revision_id,
              last_used_at: null,
            },
          })),
        q,
      ),
    );
  match = p.match(/^resume-variants\/([^/]+)(\/render)?$/);
  if (match && (blank || variants.some((v) => v.id === match![1]))) {
    const v = variants
      .filter((v) => v.id === match![1])
      .findLast(
        (v) => v.revision === Number(match![2] ? body.revision : q.get("revision") || v.revision),
      );
    if (!v) return fail("not_found", 404);
    if (!match[2]) return ok(v);
    const profile = profiles.find((r) => r.id === v.document.profile_id)!;
    const invalid = v.document.sections.some((s) =>
      s.items.some(
        (i) =>
          !i.fact_refs.length ||
          i.fact_refs.some(
            (ref) =>
              !linkedFacts(profile.data).includes(ref) ||
              !facts.some((f) => f.id === ref && f.status === "verified"),
          ),
      ),
    );
    return ok({
      id: id(8501),
      resume_variant_id: v.id,
      resume_variant_revision: v.revision,
      report: {
        render_status: invalid ? "failed" : "accepted",
        validation_status: invalid ? "failed" : "passed",
        error_code: invalid ? "grounding_failed" : null,
        page_count: invalid ? null : 1,
        findings: invalid ? [{ code: "missing_verified_fact" }] : [],
      },
    });
  }
  if (p === "jobs" && method === "POST") {
    let company = body.company_id ? companies.find((c) => c.id === body.company_id) : undefined;
    if (body.company_id && !company) return fail("not_found", 404);
    if (company && company.name !== body.company_name) return fail("company_name_mismatch", 422);
    if (!company) {
      company = { id: id(1001 + companies.length), name: body.company_name, created_at: time() };
      companies.push(company);
    }
    const n = jobs.length + 1;
    const job = {
      id: id(2000 + n),
      job_revision_id: id(4000 + n),
      revision: 1,
      company_id: company.id,
      company_name: company.name,
      application_id: id(n),
      created_at: time(),
      title: body.title,
      jd_text: body.jd_text,
      requirements: ((body.requirements || []) as D[]).map((r, i) => ({
        ...r,
        id: id(7000 + n + i),
        extraction_metadata: null,
      })),
    };
    jobs.push(job);
    const app = {
      id: id(n),
      job_id: job.id,
      created_at: time(),
      status: "tracking",
      revision: 1,
      events: [],
    };
    addEvent(app, "created", "tracking");
    apps.push(app);
    return ok(job, 201);
  }
  if (blank) {
    if (p === "companies")
      return ok(
        page(
          companies.filter((c) => !q.get("q") || String(c.name).includes(q.get("q")!)),
          q,
        ),
      );
    if (/^companies\/[^/]+$/.test(p))
      return companies.some((c) => c.id === p.split("/")[1])
        ? ok(companies.find((c) => c.id === p.split("/")[1]))
        : fail("not_found", 404);
    if (p === "applications")
      return ok(
        page(
          [...apps]
            .reverse()
            .filter(
              (a) =>
                (!q.get("status") || a.status === q.get("status")) &&
                (!q.get("company_id") ||
                  jobs.find((j) => j.id === a.job_id)?.company_id === q.get("company_id")),
            ),
          q,
        ),
      );
    if (p === "jobs") return ok(slice(jobs, q));
    if (/^jobs\/[^/]+$/.test(p))
      return jobs.some((j) => j.id === p.split("/")[1])
        ? ok(jobs.find((j) => j.id === p.split("/")[1]))
        : fail("not_found", 404);
    if (p.startsWith("job-revisions/")) {
      const j = jobs.find((j) => j.job_revision_id === p.split("/")[1]);
      return j ? ok({ ...j, job_id: j.id }) : fail("not_found", 404);
    }
    if (/^jobs\/[^/]+\/revisions$/.test(p)) {
      const j = jobs.find((j) => j.id === p.split("/")[1]);
      return ok(
        page(
          j
            ? [
                {
                  id: j.job_revision_id,
                  revision: j.revision,
                  title: j.title,
                  created_at: j.created_at,
                },
              ]
            : [],
          q,
        ),
      );
    }
  }
  match = p.match(/^applications\/([^/]+)(\/notes)?$/);
  if (match && (blank || method !== "GET")) {
    const app = apps.find((a) => a.id === match![1]);
    if (!app && !blank) {
      return undefined;
    }
    if (!app) return fail("not_found", 404);
    if (method === "GET") return ok(app);
    if (match[2]) {
      app.revision = Number(app.revision) + 1;
      return ok(addEvent(app, "note", null, body.text), 201);
    }
    if (body.expected_revision !== app.revision) return fail("revision_conflict");
    if (body.status === app.status) return fail("unchanged_application_status");
    if (body.correction && !String(body.reason || "").trim()) return fail("validation_error", 422);
    if (
      !body.correction &&
      !transitions[app.status as ApplicationStatus].includes(body.status as ApplicationStatus)
    )
      return fail("invalid_application_transition");
    app.revision = Number(app.revision) + 1;
    addEvent(
      app,
      body.correction ? "correction" : "status_changed",
      String(body.status),
      body.reason,
    );
    return ok(app);
  }
  if (!blank) return undefined;
  // Remaining business workflows use the existing deterministic provider, with exact newly-created context.
  const profile = profiles.at(-1),
    job = jobs[0],
    base = variants.filter((v) => v.document.job_revision_id === null).at(-1);
  if (method === "POST" && (p === "operations" || /^companies\/[^/]+\/research$/.test(p))) {
    const req = body.request as D;
    if (
      (body.kind !== "company_research" && (!profile || req.profile_id !== profile.id)) ||
      !job ||
      req.job_revision_id !== job.job_revision_id
    )
      return fail("context_revision_mismatch");
    if (
      body.kind !== "company_research" &&
      profile &&
      linkedFacts(profile.data).some(
        (ref) => !facts.some((f) => f.id === ref && f.status === "verified"),
      )
    )
      return fail("missing_verified_fact");
    if (
      (req.targets as string[] | undefined)?.some((t) => t !== "fit_analysis") &&
      !variants.some((v) => v.resume_revision_id === req.resume_revision_id)
    )
      return fail("resume_selection_required");
  }
  if (/^companies\/[^/]+\/research(?:\/current)?$/.test(p) && method === "GET" && !researchReady)
    return p.endsWith("/current") ? fail("no_current_research", 404) : ok(page([], q));
  if (/^operations\/[^/]+\/execute$/.test(p)) {
    const payload = operations.get(p.split("/")[1]);
    if (payload?.kind === "company_research") researchReady = true;
    if (
      (payload?.request as D)?.targets &&
      ((payload!.request as D).targets as string[]).includes("resume_tailoring") &&
      base &&
      job
    ) {
      const row: Variant = {
        id: id(8460),
        resume_revision_id: id(8461),
        revision: 1,
        created_at: time(),
        document: {
          ...structuredClone(base.document),
          job_revision_id: String(job.job_revision_id),
        },
      };
      if (!variants.some((v) => v.id === row.id)) variants.push(row);
    }
    if (job && !(job.requirements as D[]).length)
      job.requirements = [
        {
          id: id(7001),
          text: "熟悉 Python",
          category: "skill",
          importance: "must",
          source_quote: "Python",
          extraction_metadata: null,
        },
      ];
  }
  if (p.endsWith("/submissions") && method === "POST") {
    const old = receipts.get(String(body.request_id));
    if (old) return ok(old);
    const app = apps.find((a) => a.id === p.split("/")[1]);
    if (!app || body.expected_revision !== app.revision) return fail("revision_conflict");
    const row = { ...body, id: uid(), application_id: app.id, event_id: uid(), created_at: time() };
    receipts.set(String(body.request_id), row);
    app.revision = Number(app.revision) + 1;
    addEvent(app, "status_changed", "applied");
    return ok(row, 201);
  }
  if (p.endsWith("/submissions") && method === "GET") return ok(page([...receipts.values()], q));
  const result = workspaceResponse(url, method, body);
  if (result) {
    if (method === "POST" && (p === "operations" || p.endsWith("/research")))
      operations.set(String((result.body as D).id), body);
    const current = variants.find((v) => v.id === id(8460)) || base;
    const replace = (value: unknown, key = ""): unknown => {
      if (Array.isArray(value)) return value.map((v) => replace(v));
      if (value && typeof value === "object")
        return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, replace(v, k)]));
      if (value === id(9001) && profile) return profile.id;
      if (value === id(8401) && current) return current.resume_revision_id;
      if (value === id(8400) && current) return current.id;
      if (key === "profile_revision" && profile) return profile.revision;
      if (key === "job_revision" && job) return job.revision;
      if (key === "job_title" && job) return job.title;
      if (key === "company_name" && job) return job.company_name;
      return value;
    };
    if ((result.body as D)?.results && current) {
      for (const r of (result.body as { results: D[] }).results)
        if (r.kind === "resume_tailoring") r.content = current.document;
    }
    return { ...result, body: replace(result.body) };
  }
  if (p.endsWith("/preparation-packages") || p === "interviews") return ok([]);
  if (p === "mock-interviews" || p === "interview-debriefs" || p.endsWith("/knowledge-notes"))
    return ok(page([], q));
  return fail("not_found", 404);
}
