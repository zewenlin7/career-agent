import json
from pathlib import Path
from uuid import UUID

import pytest

from career_agent.domain.rules import DomainError
from career_agent.interview.materials import visible_materials


def test_visible_materials_never_include_hidden_or_unselected_expression():
    document = json.loads(Path("tests/fixtures/resumes/normal_one_page.json").read_text())[
        "document"
    ]
    items = [i for s in document["sections"] for i in s["items"]]
    items[0]["short_text"] = "简短可见内容"
    items[0]["text"] = "不应进入模型的长版正文和其他经历"
    facts = {
        UUID(ref): {"id": ref, "revision": 1, "statement": "未展示的个人经历"}
        for item in items
        for ref in item["fact_refs"]
    }
    result = visible_materials(
        document,
        {
            "hidden_item_ids": [i["item_id"] for i in items[1:]],
            "compact_item_ids": [items[0]["item_id"]],
        },
        facts,
        {"projects": []},
    )
    encoded = json.dumps(result, ensure_ascii=False)
    assert "简短可见内容" in encoded
    assert "未展示的个人经历" not in encoded
    assert "不应进入模型" not in encoded
    assert "short_text" not in encoded
    assert document["sections"][0]["items"][0]["text"].startswith("不应进入模型")


def test_visible_materials_reject_unknown_evidence():
    document = json.loads(Path("tests/fixtures/resumes/normal_one_page.json").read_text())[
        "document"
    ]
    with pytest.raises(DomainError, match="grounding_failed"):
        visible_materials(document, {}, {}, {"projects": []})
