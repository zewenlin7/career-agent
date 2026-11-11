"""Annotated synthetic decision contrasts, separate from execution-only fixtures.

Annotations are evaluation evidence, never model inputs or production reasoning fields.
The unchanged default provider can fail these quality checks while executing legally.
"""

import copy
from typing import Any
from uuid import UUID

from career_agent.evaluation.contracts import EvalCase, Expectation
from career_agent.evaluation.fixtures import initial_cases
from career_agent.infrastructure import entities as e
from career_agent.interview.contracts import MockPolicy
from career_agent.interview.decisions import inputs_for


def fixture_inputs(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    history = [
        e.MockInterviewTurn(
            id=UUID(t["entry_id"]),
            sequence=i + 1,
            data={k: t[k] for k in ("kind", "question", "primary_entry_id")},
            answer=t["answer"],
        )
        for i, t in enumerate(state["history"])
    ]
    primary = sum(t.data["kind"] == "primary" for t in history)
    row = e.MockInterviewSession(
        context=context,
        policy=state["policy"],
        focus="technical",
        primary_question_count=primary,
        followup_count=len(history) - primary,
        interviewer_turn_count=len(history),
    )
    return inputs_for(row, history)


def quality_cases() -> list[EvalCase]:
    original = next(
        c for c in initial_cases() if c.case_id == "mock_interview_turn_generation.normal"
    )
    context = copy.deepcopy(original.source_snapshot["context"])
    question = (
        "同一请求因网络超时重复到达时，如何避免重复写入？"
        "请明确说明并发竞争与提交后响应丢失的处理边界。"
    )
    complete = (
        "使用稳定请求键，事务内用唯一约束仲裁并发写入；竞争失败读取已提交结果。"
        "提交后响应丢失时，客户端仍用原键查询或重试，服务端返回同一已存结果。"
    )
    brief = "请求键唯一约束与写入同事务；并发冲突读已提交结果，提交后超时也用原键返回该结果。"
    missing = "用请求键保存处理结果；提交后响应丢失时，客户端用原键重试，服务端返回已保存的结果。"
    contradiction = (
        "先查询请求键，不存在才写入，不需要唯一约束或锁；"
        "并发先查后写也一定只执行一次。提交后响应丢失则按原键返回结果。"
    )
    conditional = (
        "所有写入限定经过同一个串行消费者，查询键与写入不会并发交错；"
        "结果持久化后原键重试返回旧结果。这个结论依赖单消费者约束，"
        "多消费者部署需要数据库唯一约束仲裁。"
    )

    def entry(n: int, q: str, a: str, parent: int | None = None) -> dict[str, Any]:
        return {
            "entry_id": str(UUID(int=n)),
            "kind": "primary" if parent is None else "follow_up",
            "question": q,
            "answer": a,
            "primary_entry_id": str(UUID(int=parent)) if parent is not None else None,
        }

    cases: list[EvalCase] = []

    def add(
        name: str,
        pair: str,
        history: list[dict[str, Any]],
        preferred: str,
        acceptable: list[str],
        rationale: str,
        gap: str,
        *,
        final: bool = False,
    ) -> None:
        state = {
            "policy": MockPolicy(mode="standard").model_dump(mode="json"),
            "history": history,
        }
        # Final-group contrasts keep an unused allowance; finish must remain a choice.
        if final:
            state["policy"] = MockPolicy(
                mode="custom", primary_target=3, followup_max=3
            ).model_dump(mode="json")
        inputs = fixture_inputs(context, state)

        def expectation(check: str, choices: list[str], tier: int, material: bool) -> Expectation:
            if len(choices) > 1:
                assert set(choices) == {"primary", "follow_up"}
                path, value = "output.action", "ask"
            elif choices == ["finish"]:
                path, value = "output.action", "finish"
            else:
                path, value = "output.turn.kind", choices[0]
            return Expectation(
                check_id=check,
                category="quality",
                tier=tier,
                material=material,
                operator="equals",
                path=path,
                value=value,
            )

        cases.append(
            original.model_copy(
                deep=True,
                update={
                    "case_id": "mock_decision_quality." + name,
                    "case_version": 1,
                    "tags": ["model_task", "decision_quality", "pair:" + pair],
                    "model_input": inputs,
                    "source_snapshot": {
                        "context": copy.deepcopy(context),
                        "decision_fixture": state,
                        "decision_quality": {
                            "annotation_version": "mock-decision-quality-v1",
                            "pair": pair,
                            "preferred": preferred,
                            "acceptable": acceptable,
                            "rationale": rationale,
                            "gap_to_probe": gap,
                            "scope": (
                                "Decision labels alone do not grade the relevance "
                                "of the generated question."
                            ),
                        },
                    },
                    "expectations": [
                        Expectation(check_id="execution_legal", operator="valid", path="valid"),
                        expectation("decision_acceptable", acceptable, 1, True),
                        # The existing runner marks any failed check as a failed trial.
                        # Multi-answer preference is advisory; acceptable alternatives pass.
                        *(
                            [expectation("decision_preferred", [preferred], 2, False)]
                            if len(acceptable) == 1
                            else []
                        ),
                    ],
                },
            )
        )

    for name, answer, preferred, acceptable, rationale, gap in [
        (
            "complete",
            complete,
            "primary",
            ["primary"],
            "题目明确要求的并发与提交后超时边界均已回答，继续覆盖其他能力。",
            "",
        ),
        (
            "brief_accurate",
            brief,
            "primary",
            ["primary"],
            "答案短但已覆盖两个关键边界，不把长度当成缺口。",
            "",
        ),
        (
            "missing_boundary",
            missing,
            "follow_up",
            ["follow_up"],
            "遗漏题目明确要求的并发仲裁，是正确性关键而非额外扩展。",
            "并发请求同时检查不存在时由谁保证唯一写入？",
        ),
        (
            "contradiction",
            contradiction,
            "follow_up",
            ["follow_up"],
            "无约束的先查后写与并发只执行一次存在直接矛盾。",
            "并发交错下先查后写为什么不会重复？",
        ),
        (
            "conditional_judgment",
            conditional,
            "primary",
            ["primary", "follow_up"],
            "已明确结论成立条件及失效边界，优先扩展覆盖；也可核实单消费者约束如何保证，不能泛泛要求展开。",
            "仅在核实单消费者约束可执行性有新增价值时追问。",
        ),
    ]:
        add(
            name,
            "first_answer",
            [entry(9, question, answer)],
            preferred,
            acceptable,
            rationale,
            gap,
        )

    follow_question = "如果客户端用同一个请求键但请求参数不同，如何避免返回错误结果？"
    for name, answer, preferred, rationale, gap in [
        (
            "group_sufficient",
            "保存请求参数摘要；相同键的摘要不同就拒绝冲突，相同才返回旧结果。",
            "primary",
            "已有题组已覆盖并发、响应丢失和参数冲突；仍有额度也应扩大能力覆盖。",
            "",
        ),
        (
            "group_new_gap",
            "不比较请求参数；同一键始终返回旧结果，即使参数改变也当成成功。",
            "follow_up",
            "当前追问新暴露了参数冲突被错误复用的问题，连续追问有新增验证价值。",
            "参数不同却复用旧结果如何保证请求语义？",
        ),
    ]:
        add(
            name,
            "current_group",
            [entry(9, question, complete), entry(10, follow_question, answer, 9)],
            preferred,
            [preferred],
            rationale,
            gap,
        )

    prior = [
        entry(7, "如何确定服务指标？", "按请求成功率和延迟分位数设置指标。"),
        entry(8, "如何定位性能瓶颈？", "通过分段耗时和负载实验定位。"),
    ]
    for name, answer, preferred, rationale, gap in [
        (
            "finish_sufficient",
            complete,
            "finish",
            "规定主问题全部回答，最后题组核心边界已解决；额度未用完也无需继续。",
            "",
        ),
        (
            "finish_unresolved",
            contradiction,
            "follow_up",
            "主问题虽已回答完，最后一组仍有直接影响正确性的矛盾，追问比立即结束有价值。",
            "并发交错下先查后写为什么不会重复？",
        ),
    ]:
        add(
            name,
            "last_answer",
            [*prior, entry(9, question, answer)],
            preferred,
            [preferred],
            rationale,
            gap,
            final=True,
        )
    return cases
