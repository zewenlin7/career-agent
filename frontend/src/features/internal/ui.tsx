"use client";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { PageHeading } from "@/components/ui/typography";
import { Field, Panel, Pages, control } from "@/features/workspace/ui";
import { ApiError, useRead, useAction } from "@/features/workspace/client";
export { Button, Field, Panel, Pages, control, useAction };
export function ErrorNotice({ code }: { code?: string }) {
  const messages: Record<string, string> = {
    internal_not_configured: "Internal server 配置缺失；请在服务器设置 API origin 与 Ops token。",
    operator_authorization_required: "服务器 Ops credential 未被后端接受。",
    controller_not_ready: "Controller 尚未 ready；本次查询或操作未完成。",
    revision_conflict: "CAS revision 已变化。先重新查询当前 state，再确认操作。",
    case_incompatible: "Frozen case 与当前 contract 不兼容；不能推测补值执行。",
    origin_config_unavailable: "原始 execution contract 不可恢复，不会静默使用当前配置。",
    connection_interrupted: "连接中断，执行是否已提交未知。请先查询状态，不要盲目重试。",
    invalid_response: "响应不符合列表 contract，不能当作空数据。",
  };
  return code ? (
    <p
      role="alert"
      className="rounded-control border border-error-line bg-error-soft p-3 text-sm text-error"
    >
      {messages[code] || "请求未完成。请核对输入、权限、状态和版本。"}{" "}
      <span className="break-all">({code})</span>
    </p>
  ) : null;
}
export function ReadState({
  error,
  loaded,
  empty = false,
}: {
  error?: string;
  loaded: boolean;
  empty?: boolean;
}) {
  return error ? (
    <ErrorNotice code={error} />
  ) : !loaded ? (
    <p role="status">正在读取…</p>
  ) : empty ? (
    <p className="text-sm text-secondary">暂无记录。</p>
  ) : null;
}
export type Data = Record<string, unknown>;
export const obj = (v: unknown): Data =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Data) : {};
export const list = (v: unknown): Data[] => (Array.isArray(v) ? v.map(obj) : []);
export const str = (v: unknown): string => (v === null || v === undefined ? "unknown" : String(v));
export async function internal<T = Data>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/internal/${path}`, {
      method,
      headers: { "Content-Type": "application/json", "X-Internal-Request": "1" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal,
    });
  } catch {
    throw new ApiError("connection_interrupted");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(data?.error?.code || "request_failed", response.status);
  }
  return response.json() as Promise<T>;
}
const loader = (path: string, signal: AbortSignal) =>
  internal<unknown>(path, "GET", undefined, signal);
export function useInternal(path: string | null) {
  return useRead<unknown>(path, loader);
}
export function Screen({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <>
      <PageHeading title={title} description={description} />
      <div className="min-w-0 space-y-6">{children}</div>
    </>
  );
}
const labels: Record<string, string> = {
  attempts: "真实 attempts",
  logical_operations: "Logical operations",
  workflow_runs: "Workflow runs",
  business_actions: "Business actions",
  steps: "Steps",
  estimated_cost_usd_known: "已知 estimated cost · USD",
  actual_billed_cost_usd: "Actual billed cost · USD",
  unknown_usage_attempts: "Usage 未知 attempts",
  outstanding_unknown_attempts: "全部 outstanding unknown attempts",
  outstanding_unknown_budget_reserved_usd: "全部 outstanding unknown reservation · USD",
  window_unknown_budget_reserved_usd: "窗口新增 unknown reservation · USD",
  scope: "Quota scope",
  window_start: "窗口起点",
  window_seconds: "窗口秒数",
  latency_ms: "Latency · ms",
  reservation_accuracy: "Output reservation accuracy",
  provider_health: "Provider attempt health",
  retry_attempts: "Retry attempts",
  routing_roles: "Routing roles",
  routes: "Routes",
  admission_decisions: "Admission decisions",
  input_tokens: "Input tokens",
  cached_tokens: "Cached tokens",
  cache_write_tokens: "Cache write tokens",
  actual_billed_savings_usd: "Actual billed savings · USD",
  estimated_savings_usd: "Estimated savings · USD",
};
/** Structured inspection, not a score or a synthesized state. Null remains unknown. */
export function Facts({ data }: { data: unknown }) {
  if (data === null || data === undefined)
    return <span className="text-secondary">unknown / unavailable</span>;
  if (typeof data !== "object")
    return (
      <span className="whitespace-pre-wrap break-words">
        {typeof data === "boolean" ? (data ? "true" : "false") : String(data)}
      </span>
    );
  if (Array.isArray(data))
    return data.length ? (
      <ol className="space-y-3">
        {data.map((v, i) => (
          <li key={i} className="min-w-0 border-l border-line pl-3">
            <Facts data={v} />
          </li>
        ))}
      </ol>
    ) : (
      <span className="text-secondary">无记录</span>
    );
  const entries = Object.entries(data);
  return entries.length ? (
    <dl className="grid min-w-0 gap-3 text-sm">
      {entries.map(([key, value]) => (
        <div key={key} className="min-w-0">
          <dt className="break-words text-secondary">{labels[key] || key}</dt>
          <dd className="min-w-0 break-words [overflow-wrap:anywhere]">
            {value !== null && typeof value === "object" ? (
              <details>
                <summary className="cursor-pointer py-1">展开 {key}</summary>
                <div className="mt-2 border-l border-line pl-3">
                  <Facts data={value} />
                </div>
              </details>
            ) : (
              <Facts data={value} />
            )}
          </dd>
        </div>
      ))}
    </dl>
  ) : (
    <span className="text-secondary">无记录</span>
  );
}
export function pick(data: unknown, keys: string[]) {
  const value = obj(data);
  return Object.fromEntries(keys.filter((k) => k in value).map((k) => [k, value[k]]));
}
export function Remote({
  path,
  title,
  children,
}: {
  path: string;
  title: string;
  children?: (v: unknown, reload: () => void) => ReactNode;
}) {
  const read = useInternal(path);
  return (
    <Panel title={title}>
      <Button onClick={read.reload}>重新查询</Button>
      <ReadState error={read.error} loaded={read.data !== undefined} />
      {read.data !== undefined &&
        (children ? children(read.data, read.reload) : <Facts data={read.data} />)}
    </Panel>
  );
}
export type Filter = { key: string; label: string; options?: string[] };
export function Discovery({
  path,
  title,
  filters = [],
  onSelect,
  array = false,
  fixed = {},
}: {
  path: string;
  title: string;
  filters?: Filter[];
  onSelect?: (row: Data) => void;
  array?: boolean;
  fixed?: Record<string, string>;
}) {
  const [values, setValues] = useState<Record<string, string>>({}),
    [offset, setOffset] = useState(0);
  const params = new URLSearchParams({
    ...Object.fromEntries(Object.entries(values).filter(([, v]) => v)),
    ...fixed,
    limit: "10",
    offset: String(offset),
  });
  const read = useInternal(`${path}?${params}`);
  const data = obj(read.data);
  const invalid =
    read.data !== undefined &&
    (array
      ? !Array.isArray(read.data)
      : !Array.isArray(data.items) || typeof data.has_more !== "boolean");
  const items = invalid ? [] : array ? list(read.data) : list(data.items);
  return (
    <Panel title={title}>
      <form
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          setValues(Object.fromEntries(filters.map((f) => [f.key, String(form.get(f.key) || "")])));
          setOffset(0);
        }}
      >
        {filters.map((f) => (
          <Field key={f.key} label={f.label}>
            {f.options ? (
              <select name={f.key} className={control}>
                <option value="">全部</option>
                {f.options.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            ) : (
              <input name={f.key} className={control} />
            )}
          </Field>
        ))}
        <div className="flex items-end gap-2">
          <Button type="submit">筛选</Button>
          <Button onClick={read.reload}>刷新</Button>
        </div>
      </form>
      <ReadState
        error={read.error || (invalid ? "invalid_response" : undefined)}
        loaded={read.data !== undefined}
        empty={read.data !== undefined && !items.length}
      />
      <ul className="divide-y divide-line">
        {items.map((row, i) => (
          <li className="min-w-0 space-y-3 py-4" key={`${str(row.source)}:${str(row.id)}:${i}`}>
            <Facts data={row} />
            {onSelect && <Button onClick={() => onSelect(row)}>查看 {str(row.id)}</Button>}
          </li>
        ))}
      </ul>
      <Pages
        offset={offset}
        setOffset={setOffset}
        more={array ? items.length === 10 : data.has_more === true}
      />
      {array && (
        <p className="text-sm text-secondary">
          此接口无 has_more；满页时允许继续查询，下一页可能为空。
        </p>
      )}
    </Panel>
  );
}
export function ConfirmAction({
  label,
  path,
  body = {},
  description,
  onSuccess,
  disabled = false,
}: {
  label: string;
  path: string;
  body?: unknown;
  description: string;
  onSuccess?: (v: Data) => void;
  disabled?: boolean;
}) {
  const action = useAction(),
    [confirmed, setConfirmed] = useState(false),
    [result, setResult] = useState<Data>();
  return (
    <div className="space-y-3 border-t border-line pt-4">
      <p className="text-sm text-secondary">{description}</p>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        <span>确认：{label}</span>
      </label>
      <Button
        disabled={disabled || !confirmed || action.busy || !!result}
        onClick={() =>
          void action.run(async () => {
            const value = await internal(path, "POST", body);
            setResult(value);
            setConfirmed(false);
            onSuccess?.(value);
          })
        }
      >
        {action.busy ? "正在执行…" : label}
      </Button>
      <ErrorNotice code={action.error} />
      {action.error && (
        <p className="text-sm">请求可能已经提交。请先重新查询状态，不要盲目重复执行。</p>
      )}
      {result && (
        <div role="status">
          <p>请求已返回</p>
          <Facts data={result} />
        </div>
      )}
    </div>
  );
}
export function PrivateView({ path, title }: { path: string; title: string }) {
  const [openPath, setOpenPath] = useState<string | null>(null);
  const open = openPath === path;
  return (
    <Panel title={title}>
      <p className="text-sm text-secondary">
        这是显式私有审阅，不是普通运行日志。内容仅在本页读取，不写入浏览器存储。
      </p>
      <Button onClick={() => setOpenPath(open ? null : path)}>
        {open ? "关闭私有内容" : "确认读取私有内容"}
      </Button>
      {open && <Remote path={`${path}?private=confirmed`} title="私有审阅内容" />}
    </Panel>
  );
}
export function JsonEditor({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label}>
      <textarea
        rows={8}
        spellCheck={false}
        className={`${control} font-mono text-xs`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}
