"use client";
import { useState } from "react";
import {
  Button,
  Panel,
  Screen,
  Facts,
  obj,
  str,
  Discovery,
  Remote,
  PrivateView,
  type Data,
} from "./ui";
import { JsonMutation, Export } from "./evaluation";
export function Triage() {
  const [queue, setQueue] = useState<Data>(),
    [capture, setCapture] = useState<Data>(),
    [calibration, setCalibration] = useState(false);
  return (
    <Screen
      title="Calibration & Triage"
      description="HumanAnnotation、UserFeedback、JudgeEvaluation 独立保存。盲标提交前不在此展示 Judge 结果；regenerate 不等于负反馈。"
    >
      <Discovery
        path="evaluation/annotations/queue"
        title="Blind annotation queue"
        array
        filters={[
          { key: "status", label: "Queue status", options: ["pending", "annotated"] },
          { key: "population", label: "Population", options: ["random", "targeted"] },
        ]}
        onSelect={(r) => {
          setQueue(r);
          setCalibration(false);
        }}
      />
      {queue && (
        <Panel key={str(queue.id)} title="Blind labeling">
          <Button onClick={() => setQueue(undefined)}>关闭当前盲标</Button>
          <Facts data={queue} />
          <PrivateView
            path={`evaluation/annotations/queue/${str(queue.id)}`}
            title="盲标 authoritative input/output"
          />
          <p className="text-sm text-secondary">
            请按来源填写确切 Subject task_type / accepted_model_call_id / operation_id；队列 API
            不返回这些完整 binding。后端验证 subject，不能猜测或使用 Judge 结果填入 human rating。
          </p>
          <JsonMutation
            title="提交 blind annotation"
            path={`evaluation/annotations/queue/${str(queue.id)}`}
            initial={JSON.stringify(
              {
                subject: {
                  subject_id: queue.subject_id,
                  task_type: "",
                  accepted_model_call_id: null,
                  operation_id: null,
                  origin: "business",
                },
                annotator: "",
                population: queue.population,
                rubric_version: "quality-rubric-v1",
                criteria: [
                  {
                    criterion: "",
                    rating: "insufficient_evidence",
                    confidence: "low",
                    uncertainty_reasons: [],
                    reason: "",
                    evidence_refs: [],
                  },
                ],
                blind: true,
              },
              null,
              2,
            )}
            description="Criteria rating: pass / minor_issue / major_issue / insufficient_evidence；confidence: low / medium / high。必须独立人工填写。提交成功后返回 annotation ID；后端目前没有 annotation 历史列表。"
          />
        </Panel>
      )}
      <details className="rounded-panel border border-line p-5">
        <summary className="cursor-pointer">显式创建 annotation queue</summary>
        <div className="mt-4">
          <JsonMutation
            title="加入 annotation queue"
            path="evaluation/annotations/queue"
            initial={
              '{"subject":{"subject_id":"","task_type":"","accepted_model_call_id":null,"operation_id":null,"origin":"business"},"population":"targeted"}'
            }
            description="使用确切 subject provenance。Random calibration 与 targeted diagnostic 必须明确区分。"
          />
        </div>
      </details>
      <Panel title="Calibration report">
        <p className="text-sm text-secondary">
          按后端 versioned selection rule 展示 unique subjects、pair 明细、agreement、weighted
          Kappa、confusion、precision/recall/F1 和 confidence calibration。小样本不表示总体 Judge
          质量。
        </p>
        <Button disabled={!!queue} onClick={() => setCalibration((v) => !v)}>
          {calibration ? "关闭 calibration" : "读取 calibration report"}
        </Button>
        {queue && <p className="text-sm">当前正在盲标；关闭盲标后才可读取 calibration。</p>}
        {calibration && !queue && (
          <Remote
            path="evaluation/calibration"
            title="Calibration statistics / population slices"
          />
        )}
      </Panel>
      <Discovery
        path="evaluation/captures"
        title="Capture metadata / triage discovery"
        filters={[
          {
            key: "status",
            label: "Capture status",
            options: ["captured", "triaged", "promoted", "dismissed"],
          },
          { key: "subject_id", label: "Subject UUID" },
          { key: "task_type", label: "Task type" },
        ]}
        onSelect={setCapture}
      />
      {capture && <CaptureDetail key={str(capture.id)} row={capture} />}
    </Screen>
  );
}
function CaptureDetail({ row }: { row: Data }) {
  const id = str(row.id);
  return (
    <div className="space-y-5">
      <Remote
        path={`evaluation/captures/${id}`}
        title="Capture identity / immutable payload metadata / events"
      />
      <Panel title="Triage decision">
        <JsonMutation
          title="保存 triage"
          path={`evaluation/captures/${id}/triage`}
          initial={'{"status":"triaged","reason_code":"manual_review"}'}
          description="status 仅 triaged / dismissed。仅更新 triage metadata，不覆盖 frozen payload。"
        />
      </Panel>
      <Export path={`evaluation/captures/${id}/sanitized`} title="Sanitized capture export" />
      <Panel title="Explicit promotion">
        <p className="text-sm text-secondary">
          先审阅 sanitized export，再构造 EvalCase。source/model_input 必须与 sanitizer 输出和
          entrypoint 匹配；历史信息不足应明确 incompatible。不得覆盖 authoritative origin identity。
        </p>
        <JsonMutation
          title="Promote regression case"
          path={`evaluation/captures/${id}/promote`}
          initial={'{"case":{},"confirmed_repo_safe":false}'}
          description="需要完整 canonical EvalCase、人工 repo-safe 确认，以及 confirmed_repo_safe=true。不会自动写入 Git。"
        />
      </Panel>
      <p className="text-sm text-secondary">
        Capture 原始私有正文不会通过普通详情返回；显式导出只使用后端 sanitized contract。
      </p>
      <Facts data={obj(row)} />
    </div>
  );
}
