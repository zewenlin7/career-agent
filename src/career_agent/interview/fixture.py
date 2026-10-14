"""Synthetic offline behavior, not a quality claim about interview assessment."""

from typing import Any


def output(task: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if task == "mock_interview_turn_generation":
        policy = inputs["policy"]
        follow = policy["next_kind"] == "follow_up"
        return {
            "kind": policy["next_kind"],
            "question": "请补充说明你的验证方法。"
            if follow
            else "请介绍相关项目的设计与验证方法。",
            "question_type": "technical",
            "topic": "工程设计",
            "primary_entry_id": inputs["current_question"]["entry_id"] if follow else None,
            "requirement_refs": [],
            "fact_refs": [],
            "reason_code": "clarify_answer" if follow else "next_primary",
        }
    if task == "interview_group_debrief":
        group = inputs["group"]
        answered = [entry["entry_id"] for entry in group["entries"] if entry["answer"]]
        return {
            "group_ref": group["group_ref"],
            "strengths": [],
            "issues": [],
            "knowledge_gap_hypotheses": [],
            "improvement_suggestions": [
                {"content": "建议补充可验证的具体例子。", "evidence_refs": answered}
            ]
            if answered
            else [],
            "example_answer": None,
        }
    answered = [entry["entry_id"] for entry in inputs["source"]["entries"] if entry["answer"]]
    return {
        "strengths": [],
        "recurring_issues": [],
        "knowledge_gap_hypotheses": [],
        "practice_recommendations": [
            {"content": "建议结合项目练习具体表达。", "evidence_refs": answered}
        ]
        if answered
        else [],
        "knowledge_candidates": [],
    }
