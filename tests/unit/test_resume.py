import copy
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from career_agent.domain.rules import FactStatus
from career_agent.resume.grounding import FactEvidence, validate_grounding
from career_agent.resume.policy import compress, initial_selection, selection_hash
from career_agent.resume.renderer import CompileError
from career_agent.resume.schemas import FactSnapshot, InputSnapshot, ResumeDocument
from career_agent.resume.store import ArtifactStore


@pytest.fixture
def resume_fixture():
    return json.loads(Path("tests/fixtures/resumes/normal_one_page.json").read_text())


def grounding_args(fixture):
    document = ResumeDocument.model_validate(fixture["document"])
    facts = {
        UUID(f["id"]): FactEvidence(
            UUID(f["id"]), f["revision"], FactStatus(f["status"]), f["statement"]
        )
        for f in fixture["facts"]
    }
    snapshot = InputSnapshot(
        display_name=fixture["name"],
        facts=[FactSnapshot(fact_id=f.id, revision=f.revision) for f in facts.values()],
    )
    return document, snapshot, set(facts), facts, set()


def test_valid_grounding(resume_fixture):
    assert validate_grounding(*grounding_args(resume_fixture)) == []


@pytest.mark.parametrize("state", ["proposed", "superseded", "rejected"])
def test_nonverified_facts_fail(resume_fixture, state):
    resume_fixture["facts"][0]["status"] = state
    assert "missing_verified_fact" in {
        f.code for f in validate_grounding(*grounding_args(resume_fixture))
    }


def test_missing_wrong_snapshot_and_requirement(resume_fixture):
    doc, snapshot, members, facts, requirements = grounding_args(resume_fixture)
    first = doc.sections[0].items[0]
    assert (
        validate_grounding(doc, snapshot, members, {}, requirements)[0].code
        == "missing_verified_fact"
    )
    assert (
        validate_grounding(doc, snapshot, set(), facts, requirements)[0].code == "snapshot_mismatch"
    )
    snapshot.facts[0].revision = 99
    assert (
        validate_grounding(doc, snapshot, members, facts, requirements)[0].code
        == "snapshot_mismatch"
    )
    first.requirement_refs = [uuid4()]
    assert "invalid_requirement_reference" in {
        f.code for f in validate_grounding(doc, snapshot, members, facts, set())
    }


def test_hard_fields_and_short_text(resume_fixture):
    doc, snapshot, members, facts, requirements = grounding_args(resume_fixture)
    doc.sections[0].items[0].short_text = "Improved performance by 99%"
    assert "hard_field_mismatch" in {
        f.code for f in validate_grounding(doc, snapshot, members, facts, requirements)
    }
    item = resume_fixture["document"]["sections"][0]["items"][0]
    item["hard_claims"] = [
        {"kind": "organization", "value": "Invented Company", "fact_ref": item["fact_refs"][0]}
    ]
    assert "hard_field_mismatch" in {
        f.code for f in validate_grounding(*grounding_args(resume_fixture))
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "priority",
        "revision",
        "no_facts",
        "template",
        "output_path",
        "section",
        "control",
    ],
)
def test_invalid_variant(resume_fixture, mutation):
    doc = resume_fixture["document"]
    item = doc["sections"][0]["items"][0]
    if mutation == "duplicate":
        doc["sections"][0]["items"].append(copy.deepcopy(item))
    elif mutation == "priority":
        item["priority"] = -1
    elif mutation == "revision":
        doc["profile_revision"] = 0
    elif mutation == "no_facts":
        item["fact_refs"] = []
    elif mutation == "template":
        doc["template"] = "../../private.typ"
    elif mutation == "output_path":
        doc["output_path"] = "/private/example.pdf"
    elif mutation == "section":
        doc["sections"][0]["name"] = "arbitrary heading"
    elif mutation == "control":
        item["text"] = "Hidden\x00text"
    with pytest.raises(ValidationError):
        ResumeDocument.model_validate(doc)


def test_deterministic_policy_and_required(resume_fixture):
    doc = ResumeDocument.model_validate(resume_fixture["document"])
    item = doc.sections[0].items[0]
    item.short_text = "Backend engineer."
    optional = doc.sections[1].items[-1]
    optional.required = False
    original = initial_selection(doc)
    shorter = compress(original)
    assert shorter.decisions[0].action == "short_text"
    assert original.sections[0].items[0].text != shorter.sections[0].items[0].text
    selected = compress(shorter)
    assert selected.decisions[-1].target_id == optional.item_id
    required = {i.item_id for s in doc.sections for i in s.items if i.required}
    assert required <= {i.item_id for s in selected.sections for i in s.items}
    assert compress(selected) is None
    assert selection_hash(compress(compress(initial_selection(doc)))) == selection_hash(selected)


def test_store_no_traversal_symlink_or_tamper(tmp_path):
    store = ArtifactStore(tmp_path)
    ref = uuid4()
    digest = store.write(ref, b"%PDF-synthetic")
    assert store.read(ref, digest) == b"%PDF-synthetic"
    with pytest.raises(CompileError):
        store.write("../escape", b"x")
    with pytest.raises(CompileError):
        store.write(ref, b"overwrite")
    (store.root / f"{ref}.pdf").write_bytes(b"tamper")
    with pytest.raises(CompileError):
        store.read(ref, digest)
    other = uuid4()
    (store.root / f"{other}.pdf").symlink_to(tmp_path / "outside")
    with pytest.raises(CompileError):
        store.write(other, b"x")


def test_optional_sections_and_priority_order(resume_fixture):
    doc = ResumeDocument.model_validate(resume_fixture["document"])
    section = doc.sections[-1]
    section.required = False
    for item in section.items:
        item.required = False
        item.priority = 0
    selected = compress(initial_selection(doc))
    assert [d.action for d in selected.decisions] == ["remove_item", "remove_section"]
    assert section.section_id not in [s.section_id for s in selected.sections]


def test_positive_declared_hard_claim(resume_fixture):
    item = resume_fixture["document"]["sections"][1]["items"][0]
    item["hard_claims"] = [
        {"kind": "organization", "value": "Example Systems", "fact_ref": item["fact_refs"][0]}
    ]
    assert validate_grounding(*grounding_args(resume_fixture)) == []


def test_short_forms_are_applied_one_at_a_time_in_priority_order(resume_fixture):
    doc = ResumeDocument.model_validate(resume_fixture["document"])
    for index, section in enumerate(doc.sections):
        section.priority = 90 - index
        for item in section.items:
            item.short_text = "Short expression."
    original = initial_selection(doc)
    expected = sorted(
        [(s, i) for s in original.sections for i in s.items],
        key=lambda pair: (
            pair[0].priority,
            pair[1].priority,
            pair[0].ordering,
            pair[1].ordering,
            str(pair[1].item_id),
        ),
    )
    assert len(expected) > 1
    first = compress(original)
    assert first is not None and len(first.decisions) == 1
    assert first.decisions[0].target_id == expected[0][1].item_id
    assert sum(i.short_text is None for s in first.sections for i in s.items) == 1
    second = compress(first)
    assert second is not None and len(second.decisions) == 2
    assert second.decisions[-1].target_id == expected[1][1].item_id
    assert all(i.short_text for s in original.sections for i in s.items)


def test_structured_layout_is_text_bound_and_retains_every_line():
    from hashlib import sha256

    from career_agent.resume.renderer import item_view
    from career_agent.resume.schemas import EntryLayout, ResumeItem

    text = "合成大学\n硕士\n计算机\n2023-09\n2026-06\n课程项目"
    item = ResumeItem(
        item_id=uuid4(),
        kind="entry",
        text=text,
        fact_refs=[uuid4()],
        priority=50,
        ordering=0,
        layout=EntryLayout(
            text_sha256=sha256(text.encode()).hexdigest(), date_lines=[3, 4], subtitle_lines=[2, 1]
        ),
    )
    view = item_view(item)
    assert view["title"] == "合成大学"
    assert view["period"] == "2023.09 – 2026.06"
    assert view["subtitle"] == "计算机 · 硕士"
    assert view["body"] == ["课程项目"]
    item.text = "用户修改的表达"
    assert "structured" not in item_view(item)
    item.text = text
    item.layout.date_lines = [0, 99]
    assert "structured" not in item_view(item)


def test_pdf_bullet_glyph_equivalence_does_not_remove_content():
    from career_agent.resume.pdf import retained_text_present

    assert retained_text_present("·实现测试", ["•实现测试"])
    assert not retained_text_present("·实现", ["•实现测试"])


def test_model_expression_schema_never_accepts_model_owned_order_or_refs():
    from uuid import uuid4

    import pytest
    from pydantic import ValidationError

    from career_agent.product.draft_contracts import ResumeExpressions

    with pytest.raises(ValidationError):
        ResumeExpressions.model_validate(
            {"items": [{"source_item_id": str(uuid4()), "text": "内容", "ordering": 9}]}
        )
