"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { api, ApiError, useAction } from "@/features/workspace/client";
import { Field, ErrorNotice, control } from "@/features/workspace/ui";
import { CompanySearch, type Company } from "@/features/applications/company-search";
import { UUID_PATTERN } from "@/features/applications/contracts";
import { clearJobRequest, jobRequest, pendingJobRequest } from "./job-request";
import { useConfirmation } from "@/features/profile-area/confirmation";
export function NewApplication() {
  const { confirm, confirmation } = useConfirmation();
  const [notice, setNotice] = useState("");
  const [checking, setChecking] = useState(true);

  const [search, setSearch] = useState(""),
    [company, setCompany] = useState<Company>(),
    [attempted, setAttempted] = useState(false);
  const composition = useRef(false);
  const submitted = useRef(false);
  const action = useAction(),
    router = useRouter();
  useEffect(() => {
    let active = true;
    const recover = async () => {
      try {
        const saved = pendingJobRequest();
        if (!saved) return;
        setAttempted(true);
        const row = await api<{
          request_id: string;
          application_id: string;
          workspace_available: boolean;
        }>(`job-create-requests/${saved.id}`);
        if (!active) return;
        if (
          row.request_id !== saved.id ||
          !UUID_PATTERN.test(row.application_id) ||
          typeof row.workspace_available !== "boolean"
        )
          throw new ApiError("invalid_response");
        clearJobRequest();
        setAttempted(false);
        if (row.workspace_available) router.replace(`/applications/${row.application_id}/summary`);
        else setNotice("此前创建的申请已删除，无法打开工作区。");
      } catch {
        if (active)
          setNotice("上次创建结果尚未确认。请重新填写原内容后继续提交，或先核对申请列表。");
      } finally {
        if (active) setChecking(false);
      }
    };
    void recover();
    return () => {
      active = false;
    };
  }, [router]);
  return (
    <>
      <Link href="/applications" className="mb-5 inline-block text-sm text-secondary">
        ← 返回申请列表
      </Link>
      <form
        className="max-w-[760px] space-y-6 [&_label]:font-semibold [&_input]:font-normal [&_textarea]:font-normal [&_select]:font-normal"
        onSubmit={(e) => {
          e.preventDefault();
          if (composition.current || submitted.current) return;
          const f = new FormData(e.currentTarget);
          if (
            ![search, f.get("title"), f.get("jd_text")].every(
              (v) => typeof v === "string" && v.trim(),
            )
          ) {
            e.currentTarget.reportValidity();
            return;
          }
          submitted.current = true;
          setAttempted(true);
          setNotice("");
          void action.run(async () => {
            try {
              const payload = {
                ...(company ? { company_id: company.id } : {}),
                company_name: search.trim(),
                title: f.get("title"),
                jd_text: f.get("jd_text"),
              };
              let requestId: string;
              try {
                requestId = await jobRequest(payload);
              } catch (error) {
                setNotice(
                  error instanceof Error && error.message === "request_identity_conflict"
                    ? "内容与上次提交不同。请恢复原内容重试；若要新增另一条申请，请选择“另建一条申请”。"
                    : "无法保存创建请求，请检查浏览器存储设置后重试。",
                );
                return;
              }
              const r = await api<{ application_id: string | null }>("jobs", "POST", {
                ...payload,
                request_id: requestId,
              });
              if (r.application_id !== null && !UUID_PATTERN.test(r.application_id))
                throw new ApiError("invalid_response");
              clearJobRequest();
              setAttempted(false);
              if (r.application_id === null) {
                setNotice("此前创建的申请已删除，无法打开工作区。");
                return;
              }
              router.push(`/applications/${r.application_id}/summary`);
              router.refresh();
            } catch (error) {
              if (
                error instanceof ApiError &&
                [400, 403, 404, 409, 422].includes(error.status) &&
                error.code !== "request_identity_conflict"
              ) {
                clearJobRequest();
                setAttempted(false);
              } else setNotice("创建结果尚未确认。再次提交会核对同一次请求，不会另建申请。");
              throw error;
            } finally {
              submitted.current = false;
            }
          });
        }}
      >
        <fieldset disabled={action.busy || checking} className="min-w-0 space-y-6">
          <CompanySearch
            label="公司名称"
            value={search}
            required
            showEmpty={false}
            onComposing={(value) => {
              composition.current = value;
            }}
            onChange={(value) => {
              setSearch(value);
              setCompany(undefined);
            }}
            onSelect={(value) => {
              setCompany(value);
              setSearch(value.name);
            }}
          />
          <Field label="职位名称">
            <input
              name="title"
              required
              maxLength={200}
              placeholder="输入职位名称"
              className={`${control} placeholder:text-muted`}
            />
          </Field>
          <Field label="职位描述">
            <textarea
              name="jd_text"
              required
              maxLength={20000}
              rows={9}
              placeholder="粘贴完整职位描述"
              className={`${control} placeholder:text-muted`}
            />
          </Field>
          <Button type="submit" variant="primary" disabled={!search.trim()}>
            创建职位
          </Button>
        </fieldset>
        <ErrorNotice code={action.error} />
        {notice && <p role="status">{notice}</p>}
        {checking && <p role="status">正在检查创建记录…</p>}
        {attempted && !action.busy && !checking && (
          <div className="flex flex-wrap items-center gap-3">
            <Link href="/applications" className="text-accent-ink underline">
              查看申请列表
            </Link>
            <Button
              onClick={async () => {
                if (
                  !(await confirm(
                    "另建一条申请会使用新的创建请求。此前的申请可能已经创建成功，确定另建吗？",
                  ))
                )
                  return;
                clearJobRequest();
                submitted.current = false;
                setAttempted(false);
                setNotice("");
              }}
            >
              另建一条申请
            </Button>
          </div>
        )}
      </form>
      {confirmation}
    </>
  );
}
