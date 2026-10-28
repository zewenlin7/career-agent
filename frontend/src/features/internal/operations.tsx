"use client";
import { useState } from "react";
import Link from "next/link";
import { useRequestId } from "@/features/workspace/client";
import {
  Button,
  Field,
  Panel,
  ReadState,
  ErrorNotice,
  control,
  useAction,
  useInternal,
  internal,
  Screen,
  Facts,
  pick,
  obj,
  str,
  list,
  Remote,
  Discovery,
  ConfirmAction,
  type Data,
} from "./ui";
export function Overview() {
  const [window, setWindow] = useState("3600");
  const metrics = useInternal(`ops/metrics?window_seconds=${window}`);
  const data = obj(metrics.data);
  return (
    <Screen
      title="Overview"
      description="当前 controller snapshot 与窗口聚合。不是完整时序监控，也不合成为统一健康或质量评分。"
    >
      <Field label="聚合窗口">
        <select className={control} value={window} onChange={(e) => setWindow(e.target.value)}>
          <option value="300">最近 5 分钟</option>
          <option value="3600">最近 1 小时</option>
          <option value="86400">最近 24 小时</option>
        </select>
      </Field>
      <Button onClick={metrics.reload}>刷新窗口数据</Button>
      <ReadState loaded={metrics.data !== undefined} error={metrics.error} />
      {metrics.data !== undefined && (
        <>
          <div className="grid items-start gap-5 lg:grid-cols-2">
            <Panel title="执行与 usage population">
              <Facts
                data={pick(data, [
                  "scope",
                  "window_start",
                  "window_seconds",
                  "attempts",
                  "unknown_dispatch_intents",
                  "logical_operations",
                  "workflow_runs",
                  "business_actions",
                  "steps",
                  "retry_attempts",
                  "estimated_cost_usd_known",
                  "actual_billed_cost_usd",
                  "unknown_usage_attempts",
                  "latency_ms",
                ])}
              />
              <p className="mt-3 text-sm text-secondary">
                Attempt、operation、action、workflow 是独立统计单位，不相加。Estimated cost
                不是实际账单。
              </p>
            </Panel>
            <Panel title="Routing / resilience">
              <Facts
                data={pick(data, [
                  "provider_health",
                  "attempt_outcome",
                  "routes",
                  "routing_roles",
                  "admission_decisions",
                  "automatic_adjustments",
                  "operator_and_lifecycle_events",
                  "journal_status",
                ])}
              />
            </Panel>
            <Panel title="Reservations / recovery">
              <Facts
                data={pick(data, [
                  "window_unknown_budget_reserved_usd",
                  "outstanding_unknown_budget_reserved_usd",
                  "outstanding_unknown_attempts",
                  "reservation_accuracy",
                  "recovery_incidents",
                ])}
              />
              <Link className="text-accent underline" href="/internal/operations/incidents">
                查看需要关注的记录
              </Link>
            </Panel>
            <Panel title="Provider token cache">
              <Facts data={data.provider_token_cache} />
              <p className="text-sm text-secondary">
                仅 provider-reported usage；未知值保持 unknown。
              </p>
            </Panel>
            <Panel title="External observation reuse">
              <Facts data={obj(data.reuse_global_population).external_observation} />
            </Panel>
            <Panel title="Business artifact reuse">
              <Facts data={obj(data.reuse_global_population).business_artifact} />
            </Panel>
            <Panel title="Production quality population">
              <Facts data={data.quality_global_population} />
              <p className="text-sm text-secondary">
                Random 与 targeted 分开，severity 保留分类语义。
              </p>
            </Panel>
          </div>
        </>
      )}
      <Remote path="ops/controller" title="Controller / effective limits / circuits" />
      <ControlEvents />
    </Screen>
  );
}
function ControlEvents() {
  const [after, setAfter] = useState(0),
    read = useInternal(`ops/events?after=${after}&limit=20`);
  const events = list(read.data);
  return (
    <Panel title="Ordered control events">
      <Button onClick={read.reload}>刷新事件</Button>
      <ReadState loaded={read.data !== undefined} error={read.error} />
      <Facts data={events} />
      <div className="flex gap-3">
        <Button disabled={!after} onClick={() => setAfter(0)}>
          从头查询
        </Button>
        <Button disabled={!events.length} onClick={() => setAfter(Number(events.at(-1)?.sequence))}>
          下一批事件
        </Button>
      </div>
      <p className="text-sm text-secondary">按 sequence 查询，不将累计 decisions 重新求和。</p>
    </Panel>
  );
}
export function Runs() {
  const [selected, setSelected] = useState<Data>();
  return (
    <Screen
      title="Runs"
      description="按真实 run 查询执行事实；ModelCall 成功不代表业务 action 成功。"
    >
      <Discovery
        path="runs"
        title="Run discovery"
        filters={[
          { key: "kind", label: "Run kind", options: ["agent", "workflow"] },
          { key: "workflow", label: "Workflow" },
          { key: "status", label: "Status" },
        ]}
        onSelect={setSelected}
      />
      {selected && <RunDetail key={str(selected.id)} row={selected} />}
    </Screen>
  );
}
function Steps({ id }: { id: string }) {
  const [offset, setOffset] = useState(0),
    read = useInternal(`runs/${id}/steps?limit=20&offset=${offset}`),
    items = list(read.data);
  return (
    <Panel title="Steps">
      <ReadState loaded={read.data !== undefined} error={read.error} />
      <Facts data={items} />
      <div className="flex gap-3">
        <Button disabled={!offset} onClick={() => setOffset((v) => v - 20)}>
          上一批 steps
        </Button>
        <Button disabled={items.length < 20} onClick={() => setOffset((v) => v + 20)}>
          下一批 steps
        </Button>
      </div>
    </Panel>
  );
}
export function RunDetail({ row }: { row: Data }) {
  const id = str(row.id);
  const [attempt, setAttempt] = useState("");
  return (
    <div className="space-y-5">
      <Remote path={`runs/${id}`} title="Run detail / budget / outcome" />
      <Steps id={id} />
      <Remote path={`runs/${id}/calls`} title="ModelCall / ToolCall / versions / diagnostics" />
      {row.kind === "agent" && (
        <>
          <Remote path={`agent-runs/${id}`} title="Agent checkpoint / progress" />
          <Remote path={`agent-runs/${id}/plans`} title="Plan revisions" />
          <Remote path={`agent-runs/${id}/observations`} title="Action observations" />
        </>
      )}
      <Panel title="Attempt journal lookup">
        <p className="text-sm text-secondary">
          使用 trace 中的确切 attempt_id；当前 API 没有 run → 全部 journal 的统一详情，不能把
          logical operation ID 当作 attempt ID。
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setAttempt(String(new FormData(e.currentTarget).get("attempt") || ""));
          }}
          className="space-y-3"
        >
          <Field label="Attempt UUID">
            <input name="attempt" required className={control} />
          </Field>
          <Button type="submit">查询 attempt</Button>
        </form>
      </Panel>
      {attempt && <Remote path={`ops/attempts/${attempt}`} title="Attempt metadata" />}
    </div>
  );
}
export function Incidents() {
  const [row, setRow] = useState<Data>();
  return (
    <Screen
      title="Incidents & Recovery"
      description="关注列表包含不同类型的关联记录，不是去重后的事故总数。普通失败、等待输入与 RecoveryIncident 不等价。"
    >
      <Discovery
        path="ops/attention"
        title="Attention discovery"
        filters={[
          {
            key: "source",
            label: "来源",
            options: ["product_operation", "run", "attempt", "recovery_incident"],
          },
          { key: "status", label: "Status" },
          { key: "include_resolved", label: "包含 resolved incident", options: ["false", "true"] },
        ]}
        onSelect={setRow}
      />
      {row && (
        <Panel key={`${str(row.source)}:${str(row.id)}`} title="Selected attention record">
          <Facts data={row} />
          {row.source === "product_operation" && (
            <Remote path={`operations/${str(row.id)}`} title="ProductOperation" />
          )}
          {row.source === "run" && <Remote path={`runs/${str(row.id)}`} title="Run outcome" />}
          {typeof row.attempt_id === "string" && (
            <Remote path={`ops/attempts/${str(row.attempt_id)}`} title="Attempt / uncertainty" />
          )}
          {row.source === "recovery_incident" &&
            Array.isArray(row.allowed_actions) &&
            row.allowed_actions.includes("reconcile") && <Reconcile row={row} />}
        </Panel>
      )}
      <Remote path="ops/recovery-incidents?limit=100" title="Recovery incidents · 最近 100 条" />
    </Screen>
  );
}
function Reconcile({ row }: { row: Data }) {
  const requestId = useRequestId(),
    [resolution, setResolution] = useState("inspect"),
    [reason, setReason] = useState("operator_review");
  const payload = { expected_revision: row.revision, resolution, reason_code: reason };
  return (
    <div className="space-y-3">
      <Field label="Resolution">
        <select
          className={control}
          value={resolution}
          onChange={(e) => setResolution(e.target.value)}
        >
          <option>inspect</option>
          <option>manual_acknowledge</option>
        </select>
      </Field>
      <Field label="Reason code">
        <input className={control} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ConfirmAction
        key={JSON.stringify(payload)}
        label="Reconcile attempt"
        path={`ops/attempts/${str(row.attempt_id)}/reconcile`}
        body={{ ...payload, request_id: requestId(payload) }}
        description={`仅处理此 attempt 的不确定状态，不自动重放模型请求。Incident revision: ${str(row.revision)}。manual_acknowledge 是人工确认，请先核实证据。`}
      />
    </div>
  );
}
export function Controls() {
  const read = useInternal("ops/controller"),
    data = obj(read.data),
    effective = obj(data.effective);
  const action = useAction(),
    requestId = useRequestId();
  const [kind, setKind] = useState("override"),
    [confirmed, setConfirmed] = useState(false),
    [result, setResult] = useState<Data>();
  const revision = effective.revision;
  return (
    <Screen
      title="Controls"
      description="只操作现有 effective controls。不会更改 candidate priority、hard financial budget、grounding 或任意 RPM/TPM policy。"
    >
      <Panel title="Controller snapshot">
        <ReadState error={read.error} loaded={read.data !== undefined} />
        {read.data !== undefined && <Facts data={read.data} />}
      </Panel>
      <Panel title="Operator action">
        <Button
          onClick={() => {
            read.reload();
            setResult(undefined);
            setConfirmed(false);
          }}
        >
          重新读取 CAS revision
        </Button>
        <ReadState error={read.error} loaded={read.data !== undefined} />
        <Facts
          data={pick(effective, [
            "revision",
            "global_revision",
            "generation",
            "ready",
            "kill",
            "global_kill",
            "overrides",
            "automatic",
          ])}
        />
        <form
          key={str(revision)}
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            const payload: Data = { action: kind, expected_revision: revision };
            if (kind === "global_kill")
              payload.expected_global_revision = effective.global_revision;
            if (["kill", "global_kill"].includes(kind))
              payload.enabled = form.get("enabled") === "true";
            if (["override", "clear_override"].includes(kind)) payload.route = form.get("route");
            if (kind === "override") {
              payload.ttl_seconds = Number(form.get("ttl"));
              payload.values = Object.fromEntries(
                ["pressure", "concurrency", "output_reservation", "sampling_rate"]
                  .filter((k) => form.get(k) !== "")
                  .map((k) => [k, Number(form.get(k))]),
              );
            }
            void action.run(async () => {
              const value = await internal("ops/controls", "POST", {
                ...payload,
                request_id: requestId(payload),
              });
              setResult(value);
              setConfirmed(false);
              read.reload();
            });
          }}
        >
          <Field label="Control action">
            <select
              className={control}
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setConfirmed(false);
                setResult(undefined);
              }}
            >
              {["override", "clear_override", "kill", "global_kill", "tick"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
          {["override", "clear_override"].includes(kind) && (
            <Field label="Exact route identifier">
              <input name="route" required className={control} list="known-routes" />
            </Field>
          )}
          <datalist id="known-routes">
            {Object.keys(obj(data.circuits)).map((r) => (
              <option key={r} value={r} />
            ))}
          </datalist>
          {kind === "override" && (
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                {
                  key: "pressure",
                  label: "Admission pressure · (0,1]",
                  min: 0.001,
                  max: 1,
                  step: "any",
                  value: "1",
                },
                { key: "concurrency", label: "Concurrency · 可选", min: 1, step: "1", value: "" },
                {
                  key: "output_reservation",
                  label: "Output reservation tokens · 可选",
                  min: 1,
                  max: 32768,
                  step: "1",
                  value: "",
                },
                {
                  key: "sampling_rate",
                  label: "Sampling rate · 可选",
                  min: 0,
                  max: 1,
                  step: "any",
                  value: "",
                },
                {
                  key: "ttl",
                  label: "Override TTL · 秒",
                  min: 1,
                  max: 86400,
                  step: "1",
                  value: "300",
                },
              ].map((f) => (
                <Field key={f.key} label={f.label}>
                  <input
                    name={f.key}
                    type="number"
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    defaultValue={f.value}
                    required={["pressure", "ttl"].includes(f.key)}
                    className={control}
                  />
                </Field>
              ))}
            </div>
          )}
          {["kill", "global_kill"].includes(kind) && (
            <Field label="目标状态">
              <select name="enabled" className={control}>
                <option value="true">开启 kill · 拒绝新 admission</option>
                <option value="false">关闭 kill · 仍受其他安全限制</option>
              </select>
            </Field>
          )}
          <label className="flex gap-2">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            我已核对目标、CAS revision 和影响范围
          </label>
          <Button
            type="submit"
            disabled={!confirmed || revision === undefined || action.busy || !!result}
          >
            {action.busy ? "正在提交…" : "提交 control action"}
          </Button>
          <ErrorNotice code={action.error} />
          {action.error && <p>提交失败或连接中断；先刷新 state/event 再决定是否重新操作。</p>}
        </form>
        {result && (
          <div role="status">
            <Facts data={result} />
          </div>
        )}
        <p className="text-sm text-secondary">
          优先级：safety / kill &gt; active override &gt; automatic &gt; base。Reconcile 在
          Incidents & Recovery 中按确切 incident 执行。
        </p>
      </Panel>
      <ControlEvents />
    </Screen>
  );
}
