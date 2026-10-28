"use client";
import { useState } from "react";
import {
  Button,
  Field,
  Panel,
  control,
  useAction,
  ErrorNotice,
  Screen,
  Facts,
  obj,
  str,
  list,
  internal,
  Remote,
  Discovery,
  ConfirmAction,
  PrivateView,
  JsonEditor,
  type Data,
} from "./ui";
export function Quality() {
  const [judge, setJudge] = useState<Data>();
  return (
    <Screen
      title="Production Quality"
      description="Sampling、Judge 与用户反馈保持独立。当前列表与 Ops quality population 为全局范围，API 未提供 production-only / origin 筛选；请按 task / subject 核对来源，不把 evaluation 样本当作纯生产统计。Random 与 targeted 不混算。"
    >
      <Remote path="ops/metrics?window_seconds=3600" title="Quality population · 最近 1 小时">
        {(v) => <Facts data={obj(v).quality_global_population} />}
      </Remote>
      <Discovery
        path="evaluation/sampling-records"
        title="Sampling decisions"
        filters={[
          { key: "subject_id", label: "Subject UUID" },
          { key: "task_type", label: "Task type" },
          { key: "population", label: "Population", options: ["random", "targeted"] },
          { key: "sampled", label: "Sampled", options: ["true", "false"] },
        ]}
      />
      <Discovery
        path="evaluation/judges"
        title="Judge evaluations"
        filters={[
          { key: "subject_id", label: "Subject UUID" },
          { key: "task_type", label: "Task type" },
          {
            key: "status",
            label: "Judge status",
            options: ["pending", "running", "completed", "failed", "cancelled"],
          },
          { key: "severity", label: "Severity" },
          { key: "population", label: "Population", options: ["random", "targeted"] },
        ]}
        onSelect={setJudge}
      />
      {judge && (
        <Remote
          key={str(judge.id)}
          path={`evaluation/judges/${str(judge.id)}`}
          title="Judge criteria / confidence / evidence / provenance"
        />
      )}
      <Discovery
        path="evaluation/feedback"
        title="User feedback · 不是 ground truth"
        filters={[{ key: "subject_id", label: "Subject UUID" }]}
      />
      <Panel title="显式 drain pending Judge">
        <p className="text-sm text-secondary">
          不会在页面加载时执行。后端当前 API runner 使用 fixture 默认路径；这不是后台 worker
          或生产实时自动 drain。
        </p>
        <JsonMutation
          title="Drain pending"
          path="evaluation/judges/drain"
          initial={
            '{"limit": 1, "concurrency": 1, "limits": {"max_estimated_cost": "0.05", "max_active_seconds": 120}}'
          }
          description="按输入预算显式执行 pending Judge；读取已有业务 artifact 不受此操作阻塞。"
        />
      </Panel>
    </Screen>
  );
}
export function JsonMutation({
  title,
  path,
  initial = "{}",
  description,
  onSuccess,
}: {
  title: string;
  path: string;
  initial?: string;
  description: string;
  onSuccess?: (v: Data) => void;
}) {
  const [text, setText] = useState(initial),
    [confirmed, setConfirmed] = useState(false),
    [result, setResult] = useState<Data>();
  const action = useAction();
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        void action.run(async () => {
          const value = await internal(path, "POST", JSON.parse(text));
          setResult(value);
          setConfirmed(false);
          onSuccess?.(value);
        });
      }}
    >
      <JsonEditor
        label={`${title} · canonical JSON`}
        value={text}
        onChange={(v) => {
          setText(v);
          setConfirmed(false);
          setResult(undefined);
        }}
      />
      <p className="text-sm text-secondary">{description}</p>
      <label className="flex gap-2 text-sm">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        确认提交 {title}
      </label>
      <Button type="submit" disabled={!confirmed || action.busy || !!result}>
        {action.busy ? "正在执行…" : title}
      </Button>
      <ErrorNotice code={action.error} />
      {action.error && (
        <p className="text-sm">未自动重试。连接中断时，请先 discovery 查询是否已提交。</p>
      )}
      {result && (
        <div role="status">
          <Facts data={result} />
        </div>
      )}
    </form>
  );
}
export function TestRuns() {
  const [suite, setSuite] = useState<Data>(),
    [run, setRun] = useState<Data>(),
    [caseRow, setCase] = useState<Data>();
  return (
    <Screen
      title="Test Runs"
      description="正式回归使用 frozen source / observations / clock。当前 HTTP runner 为 offline fixture 路径，不在此切换到真实付费模型。"
    >
      <Discovery
        path="evaluation/suites"
        title="Suites"
        filters={[{ key: "suite_key", label: "Suite key" }]}
        onSelect={setSuite}
      />
      {suite && (
        <Remote
          key={str(suite.id)}
          path={`evaluation/suites/${str(suite.id)}`}
          title="Exact suite / members"
        />
      )}
      <RunCreate suite={suite} onCreated={setRun} />
      <Discovery
        path="evaluation/runs"
        title="Eval runs"
        filters={[
          { key: "suite_id", label: "Suite row UUID" },
          { key: "status", label: "Run status" },
        ]}
        onSelect={setRun}
      />
      {run && <EvalRunDetail key={str(run.id)} id={str(run.id)} />}
      <Discovery
        path="evaluation/case-index"
        title="Case metadata index"
        filters={[
          { key: "tag", label: "Tag" },
          { key: "task_type", label: "Model task type" },
        ]}
        onSelect={setCase}
      />
      {caseRow && (
        <Panel key={str(caseRow.id)} title="Case origin / export">
          <Facts data={caseRow} />
          <Remote
            path={`evaluation/cases/${str(caseRow.id)}/origin`}
            title="Origin reconstruction · zero model calls"
          />
          <PrivateView
            path={`evaluation/cases/${str(caseRow.id)}/origin`}
            title="Explicit frozen origin review"
          />
          <Export
            path={`evaluation/cases/${str(caseRow.id)}/export`}
            title="Repo-safe case export"
          />
        </Panel>
      )}
      <details className="rounded-panel border border-line p-5">
        <summary className="cursor-pointer">创建 case / suite · 高级 contract 编辑</summary>
        <div className="mt-5 space-y-6">
          <Panel title="Versioned case">
            <p className="text-sm text-secondary">
              输入真实 EvalCase contract，包括
              entrypoint、source_snapshot、evaluation_clock、expectations。FaultPlan
              仅注入测试故障，不编辑生产 retry policy。更新必须使用新的 case_version。
            </p>
            <JsonMutation
              title="保存 EvalCase"
              path="evaluation/cases"
              description="后端验证 schema、content hash 和版本；不在前端猜测缺失的 frozen context。"
            />
          </Panel>
          <Panel title="Versioned suite">
            <JsonMutation
              title="保存 EvalSuite"
              path="evaluation/suites"
              initial={'{"suite_id":"","version":1,"members":[]}'}
              description="members 必须为确切 case_id + case_version；suite row UUID 与 suite key 不同。"
            />
          </Panel>
        </div>
      </details>
    </Screen>
  );
}
function RunCreate({ suite, onCreated }: { suite?: Data; onCreated: (v: Data) => void }) {
  const [mode, setMode] = useState("candidate_replay"),
    [confirmed, setConfirmed] = useState(false);
  const action = useAction();
  return (
    <Panel title="创建 frozen EvalRun">
      <form
        key={str(suite?.id)}
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          void action.run(async () => {
            const payload = {
              suite_id: f.get("suite"),
              suite_version: Number(f.get("version")),
              trials: Number(f.get("trials")),
              max_concurrent_trials: Number(f.get("concurrency")),
              mode,
              explicit_diagnostic: mode === "origin_reexecution",
              limits: JSON.parse(String(f.get("limits"))),
              per_trial_limits: JSON.parse(String(f.get("trial_limits"))),
            };
            onCreated(await internal("evaluation/runs", "POST", payload));
            setConfirmed(false);
          });
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Suite key">
            <input
              name="suite"
              className={control}
              defaultValue={suite ? str(suite.suite_key) : ""}
              required
            />
          </Field>
          <Field label="Suite version">
            <input
              name="version"
              className={control}
              type="number"
              min={1}
              defaultValue={suite ? str(suite.version) : "1"}
              required
            />
          </Field>
          <Field label="Trials per case">
            <input
              name="trials"
              className={control}
              type="number"
              min={1}
              max={5}
              defaultValue={1}
              required
            />
          </Field>
          <Field label="Max concurrent trials">
            <input
              name="concurrency"
              className={control}
              type="number"
              min={1}
              max={8}
              defaultValue={2}
              required
            />
          </Field>
          <Field label="Execution mode">
            <select
              className={control}
              value={mode}
              onChange={(e) => {
                setMode(e.target.value);
                setConfirmed(false);
              }}
            >
              <option>candidate_replay</option>
              <option>origin_reexecution</option>
            </select>
          </Field>
        </div>
        <Field label="EvalRun limits · JSON">
          <textarea
            name="limits"
            rows={4}
            className={control}
            defaultValue={
              '{"max_model_calls":200,"max_web_search_calls":100,"max_input_tokens":5000000,"max_output_tokens":1000000,"max_estimated_cost":"5","max_active_seconds":600}'
            }
          />
        </Field>
        <Field label="Per-trial limits · JSON">
          <textarea
            name="trial_limits"
            rows={3}
            className={control}
            defaultValue={
              '{"max_model_calls":12,"max_web_search_calls":2,"max_input_tokens":200000,"max_output_tokens":40000,"max_estimated_cost":"1","max_semantic_resume_compressions":1}'
            }
          />
        </Field>
        <p className="text-sm text-secondary">
          CandidateConfig 由后端创建并冻结。Origin re-execution 是显式 diagnostic，原 contract
          不可恢复时应返回 unavailable；不会静默换用当前模型。
        </p>
        <label className="flex gap-2">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          确认创建此 {mode} run
        </label>
        <Button type="submit" disabled={!confirmed || action.busy}>
          创建 EvalRun
        </Button>
        <ErrorNotice code={action.error} />
      </form>
    </Panel>
  );
}
export function EvalRunDetail({ id }: { id: string }) {
  const [trial, setTrial] = useState<Data>();
  return (
    <div className="space-y-5">
      <Remote path={`evaluation/runs/${id}`} title="EvalRun / frozen CandidateConfig">
        {(v, reload) => (
          <>
            <Facts data={v} />
            {obj(v).status === "pending" && (
              <ConfirmAction
                label="执行 EvalRun"
                path={`evaluation/runs/${id}/execute`}
                onSuccess={reload}
                description="显式执行 frozen regression；请求中断不承诺后台继续。成功返回后自动重新查询 run。"
              />
            )}
            {["pending", "running"].includes(str(obj(v).status)) && (
              <ConfirmAction
                label="取消 EvalRun"
                path={`evaluation/runs/${id}/cancel`}
                onSuccess={reload}
                description="请求取消当前 run；已提交的 trial/provenance 保留。"
              />
            )}
          </>
        )}
      </Remote>
      <Discovery
        path="evaluation/trials"
        title="Trial discovery"
        fixed={{ run_id: id }}
        filters={[
          { key: "case_id", label: "Case row UUID" },
          { key: "status", label: "Trial status" },
        ]}
        onSelect={setTrial}
      />
      <p className="text-sm text-secondary">
        当前 run ID：{id}。Trial discovery 固定在此 run 内；上方 trials 是本 run 的 authority。
      </p>
      {trial && <TrialDetail key={str(trial.id)} id={str(trial.id)} />}
      <Panel title="按确切 trial ID 查看">
        <Lookup label="Trial UUID" onSelect={(id) => setTrial({ id })} />
      </Panel>
    </div>
  );
}
function TrialDetail({ id }: { id: string }) {
  const [operation, setOperation] = useState("");
  return (
    <>
      <Remote path={`evaluation/trials/${id}`} title="Trial checks / usage / operation provenance">
        {(v) => (
          <>
            <Facts data={obj(v).result} />
            {list(obj(v).operations).map((o) => (
              <div key={str(o.id)} className="mt-4 space-y-2 border-t border-line pt-4">
                <Facts data={o} />
                <Button onClick={() => setOperation(str(o.id))}>查看 operation {str(o.id)}</Button>
              </div>
            ))}
          </>
        )}
      </Remote>
      {operation && (
        <div className="space-y-4">
          <Remote
            path={`evaluation/operations/${operation}`}
            title="OperationInvocationSnapshot metadata"
          />
          <PrivateView
            path={`evaluation/operations/${operation}`}
            title="显式 invocation input/output 审阅"
          />
        </div>
      )}
    </>
  );
}
export function Lookup({ label, onSelect }: { label: string; onSelect: (id: string) => void }) {
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSelect(String(new FormData(e.currentTarget).get("id")));
      }}
    >
      <Field label={label}>
        <input name="id" required className={control} />
      </Field>
      <Button type="submit">查询</Button>
    </form>
  );
}
export function Export({ path, title }: { path: string; title: string }) {
  const [value, setValue] = useState<Data>();
  const action = useAction();
  return (
    <Panel title={title}>
      <Button
        disabled={action.busy}
        onClick={() => void action.run(async () => setValue(await internal(path)))}
      >
        显式读取 {title}
      </Button>
      <ErrorNotice code={action.error} />
      {value && (
        <>
          <Facts data={value} />
          <Button
            onClick={() => {
              const url = URL.createObjectURL(
                new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
              );
              const a = document.createElement("a");
              a.href = url;
              a.download = "evaluation-export.json";
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            下载此 JSON
          </Button>
        </>
      )}
    </Panel>
  );
}
export function Comparisons() {
  const [selected, setSelected] = useState<Data>();
  return (
    <Screen
      title="Comparisons"
      description="保留 priority tiers、dimension deltas、coverage 和 gate。Attribution context 不表示因果，质量缺失不等于 PASS。"
    >
      <Discovery
        path="evaluation/comparisons"
        title="Comparison discovery"
        filters={[
          { key: "baseline_run_id", label: "Baseline UUID" },
          { key: "candidate_run_id", label: "Candidate UUID" },
        ]}
        onSelect={setSelected}
      />
      <Panel title="创建 comparison">
        <JsonMutation
          title="比较两个 EvalRun"
          path="evaluation/comparisons"
          initial={
            '{"baseline_run_id":"","candidate_run_id":"","policy":{"version":"comparison-priority-v2","minimum_trials":1,"efficiency_threshold":null,"efficiency_blocking":false}}'
          }
          description="仅比较已存在的真实执行结果；Tier 0 regression 始终 blocking，不转换为总分。"
          onSuccess={setSelected}
        />
      </Panel>
      {selected && (
        <Remote
          key={str(selected.id)}
          path={`evaluation/comparisons/${str(selected.id)}`}
          title="Comparison outcome / config diff / dimensions / coverage"
        >
          {(v) => (
            <>
              <Facts data={{ gate: obj(v).gate }} />
              <Facts data={v} />
            </>
          )}
        </Remote>
      )}
    </Screen>
  );
}
