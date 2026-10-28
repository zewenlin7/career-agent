"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PageHeading } from "@/components/ui/typography";
import { Button } from "@/components/ui/button";
import { api, ApiError, useAction, useRead } from "@/features/workspace/client";
import { Field, Select, ReadState, ErrorNotice, control } from "@/features/workspace/ui";
import type { Page } from "@/features/workspace/contracts";
import { UUID_PATTERN } from "@/features/applications/contracts";
type Company = { id: string; name: string; created_at: string };
type Requirement = {
  text: string;
  category: string;
  importance: "must" | "nice_to_have" | "unknown";
  source_quote: string | null;
};
export function NewApplication() {
  const [mode, setMode] = useState(""),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [company, setCompany] = useState<Company>(),
    [requirements, setRequirements] = useState<Requirement[]>([]),
    [attempted, setAttempted] = useState(false);
  const action = useAction(),
    router = useRouter();
  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);
  const companies = useRead<Page<Company>>(
    mode === "existing" && query
      ? `companies?q=${encodeURIComponent(query)}&limit=8&offset=0`
      : null,
  );
  return (
    <>
      <PageHeading title="添加职位" description="选择公司，粘贴职位描述，开始准备申请。" />
      <Link href="/applications" className="text-accent-ink underline">
        返回申请列表
      </Link>
      <form
        className="mt-6 max-w-[760px] space-y-8"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setAttempted(true);
          void action.run(async () => {
            const r = await api<{ application_id: string }>("jobs", "POST", {
              ...(mode === "existing" ? { company_id: company!.id } : {}),
              company_name: mode === "existing" ? company!.name : f.get("company_name"),
              title: f.get("title"),
              jd_text: f.get("jd_text"),
              requirements,
            });
            if (!UUID_PATTERN.test(r.application_id)) throw new ApiError("invalid_response");
            router.push(`/applications/${r.application_id}/summary`);
            router.refresh();
          });
        }}
      >
        <fieldset disabled={action.busy || attempted} className="min-w-0 space-y-8">
          <section className="space-y-4">
            <h2 className="font-serif text-lg">公司信息</h2>
            <Select
              label="公司来源"
              value={mode}
              required
              onChange={(e) => {
                setMode(e.target.value);
                setCompany(undefined);
                setSearch("");
              }}
            >
              <option value="">请选择</option>
              <option value="existing">已有公司</option>
              <option value="new">新建公司</option>
            </Select>
            {mode === "existing" && (
              <>
                <Field label="输入公司名称">
                  <input
                    className={control}
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setCompany(undefined);
                    }}
                    maxLength={200}
                  />
                </Field>
                {query && !company && (
                  <>
                    <ReadState
                      loaded={!!companies.data}
                      error={companies.error}
                      empty={companies.data?.items.length === 0}
                    />
                    <ul aria-label="匹配的公司" className="space-y-2">
                      {companies.data?.items.map((c) => (
                        <li key={c.id}>
                          <Button onClick={() => setCompany(c)}>{c.name}</Button>
                        </li>
                      ))}
                    </ul>
                    {companies.data?.has_more && (
                      <p className="text-sm">请输入更完整的公司名称缩小范围。</p>
                    )}
                  </>
                )}
                {company && <p role="status">已选择：{company.name}</p>}
              </>
            )}
            {mode === "new" && (
              <Field label="公司名称">
                <input name="company_name" required maxLength={200} className={control} />
              </Field>
            )}
          </section>
          <section className="space-y-4 border-t border-line pt-6">
            <h2 className="font-serif text-lg">职位信息</h2>
            <Field label="职位名称">
              <input name="title" required maxLength={200} className={control} />
            </Field>
            <Field label="职位描述">
              <textarea name="jd_text" required maxLength={20000} rows={9} className={control} />
            </Field>
            <p className="text-sm text-secondary">
              直接粘贴招聘信息即可；开始岗位匹配时会提取其中的要求。
            </p>
          </section>
          <details className="space-y-4">
            <summary className="cursor-pointer">岗位要求（高级，可选）</summary>
            {requirements.map((r, i) => (
              <div key={i} className="space-y-3 border-l border-line pl-4">
                <Field label={`要求 ${i + 1}`}>
                  <textarea
                    required
                    className={control}
                    value={r.text}
                    onChange={(e) =>
                      setRequirements(
                        requirements.map((x, n) => (n === i ? { ...x, text: e.target.value } : x)),
                      )
                    }
                  />
                </Field>
                <Field label="原文依据">
                  <textarea
                    required
                    className={control}
                    value={r.source_quote || ""}
                    onChange={(e) =>
                      setRequirements(
                        requirements.map((x, n) =>
                          n === i ? { ...x, source_quote: e.target.value } : x,
                        ),
                      )
                    }
                  />
                </Field>
                <Select
                  label="重要性"
                  value={r.importance}
                  onChange={(e) =>
                    setRequirements(
                      requirements.map((x, n) =>
                        n === i
                          ? { ...x, importance: e.target.value as Requirement["importance"] }
                          : x,
                      ),
                    )
                  }
                >
                  <option value="unknown">未指定</option>
                  <option value="must">必须</option>
                  <option value="nice_to_have">加分项</option>
                </Select>
                <Button onClick={() => setRequirements(requirements.filter((_, n) => n !== i))}>
                  移除要求
                </Button>
              </div>
            ))}
            <Button
              disabled={requirements.length >= 200}
              onClick={() =>
                setRequirements([
                  ...requirements,
                  { text: "", category: "general", importance: "unknown", source_quote: null },
                ])
              }
            >
              添加要求
            </Button>
          </details>
          <Button
            type="submit"
            variant="primary"
            disabled={!mode || (mode === "existing" && !company)}
          >
            创建职位
          </Button>
        </fieldset>
        <ErrorNotice code={action.error} />
        {action.error && (
          <div className="space-y-3">
            <p>请先核对申请列表，确认没有创建成功，再重新提交。</p>
            <Link href="/applications" className="text-accent-ink underline">
              查看申请列表
            </Link>
            <Button onClick={() => setAttempted(false)}>已核对，重新填写</Button>
          </div>
        )}
      </form>
    </>
  );
}
