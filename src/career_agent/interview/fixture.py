"""Synthetic offline behavior, not a quality claim about interview assessment."""

from typing import Any


def output(task: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if task == "mock_interview_turn_generation":
        policy = inputs["policy"]
        if "legal_actions" in policy:
            # Synthetic default; scenario providers independently choose other legal decisions.
            allowed = policy["legal_actions"]
            choice = "ask_follow_up" if "ask_follow_up" in allowed else allowed[0]
            if choice == "finish":
                return {"action": "finish", "turn": None}
            follow = choice == "ask_follow_up"
            return {
                "action": "ask",
                "turn": {
                    "kind": "follow_up" if follow else "primary",
                    "question": "请补充说明你的验证方法。"
                    if follow
                    else "请介绍相关项目的设计与验证方法。",
                    "question_type": "technical",
                    "primary_entry_id": policy["current_primary_id"] if follow else None,
                    "requirement_refs": [],
                    "fact_refs": [],
                    "reason_code": "clarify_answer" if follow else "next_primary",
                },
            }
        follow = policy["next_kind"] == "follow_up"
        return {
            "kind": policy["next_kind"],
            "question": "请补充说明你的验证方法。"
            if follow
            else "请介绍相关项目的设计与验证方法。",
            "question_type": "technical",
            "primary_entry_id": inputs["current_question"]["entry_id"] if follow else None,
            "requirement_refs": [],
            "fact_refs": [],
            "reason_code": "clarify_answer" if follow else "next_primary",
        }
    if task == "interview_group_debrief":
        group = inputs["group"]
        answered = [
            entry.get("number", entry.get("entry_id"))
            for entry in group["entries"]
            if entry["answer"]
        ]
        return {
            "strengths": [],
            "issues": [],
            "knowledge_gap_hypotheses": [],
            "improvement_suggestions": [
                {"content": "建议补充可验证的具体例子。", "evidence": answered}
            ]
            if answered
            else [],
            "example_answer": None,
        }
    answered = [
        entry.get("number", entry.get("entry_id"))
        for entry in inputs["source"]["entries"]
        if entry["answer"]
    ]
    return {
        "strengths": [],
        "recurring_issues": [],
        "knowledge_gap_hypotheses": [],
        "practice_recommendations": [
            {"content": "建议结合项目练习具体表达。", "evidence": answered}
        ]
        if answered
        else [],
        "knowledge_candidates": [],
    }
