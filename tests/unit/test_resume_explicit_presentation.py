"""Product presentation never silently edits the source document."""

import json
from pathlib import Path

import pytest

from career_agent.resume.presentation import apply_presentation
from career_agent.resume.schemas import ResumeDocument


def document():
    value = json.loads(Path("tests/fixtures/resumes/normal_one_page.json").read_text())
    return ResumeDocument.model_validate(value["document"])


def test_short_expression_is_explicit_and_source_is_immutable():
    source = document()
    item = source.sections[0].items[0]
    item.short_text = item.text[:4]
    original = source.model_dump()
    normal = apply_presentation(source, {})
    assert normal.sections[0].items[0].text == item.text
    compact = apply_presentation(source, {"compact_item_ids": [str(item.item_id)]})
    assert compact.sections[0].items[0].text == item.short_text
    assert source.model_dump() == original


def test_hiding_all_items_omits_section_without_deleting_source():
    source = document()
    section = source.sections[0]
    original = source.model_dump()
    visible = apply_presentation(
        source, {"hidden_item_ids": [str(i.item_id) for i in section.items]}
    )
    assert section.section_id not in {s.section_id for s in visible.sections}
    assert source.model_dump() == original


def test_compact_requires_an_existing_short_expression():
    source = document()
    item = source.sections[0].items[0]
    item.short_text = None
    with pytest.raises(ValueError, match="compact_expression_unavailable"):
        apply_presentation(source, {"compact_item_ids": [str(item.item_id)]})


def test_compression_preserves_full_text_and_returns_all_short_forms():
    from career_agent.product.draft_contracts import ResumeExpressions
    from career_agent.product.drafts import expressions_document, validate_output

    source = {"sections": document().model_dump(mode="json")["sections"]}
    items = [i for s in source["sections"] for i in s["items"]]
    for item in items:
        item["text"] = "设计检索流程。维护检索流程。"
        item["short_text"] = None
    context = {"source_document": source, "compression": True, "facts": []}
    output = ResumeExpressions.model_validate(
        {
            "items": [
                {"source_item_id": i["item_id"], "text": i["text"], "short_text": "设计检索流程。"}
                for i in items
            ]
        }
    )
    validate_output(output, context)
    result = expressions_document(output, context)
    assert [i.text for s in result.sections for i in s.items] == [i["text"] for i in items]
    assert all(i.short_text == "设计检索流程。" for s in result.sections for i in s.items)
