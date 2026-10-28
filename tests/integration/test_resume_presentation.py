"""Presentation changes never destroy factual revisions or historical PDFs."""

from uuid import uuid4

import pytest
from test_profile_area import section, work

pytestmark = pytest.mark.integration


async def source(client):
    w = await section(client, await work(client), "personal", {"display_name": "合成用户"})
    for key in ["education", "experiences", "projects"]:
        w = await section(
            client, w, key, [{"organization": f"合成{key}", "description": "实现离线测试。"}]
        )
    w = await section(client, w, "skills", "Python")
    p = (
        await client.post(
            "/api/v1/profile-workspace/publish", json={"expected_revision": w["revision"]}
        )
    ).json()
    d = (await client.post("/api/v1/resume-workspaces", json={"profile_id": p["id"]})).json()
    return p, d


async def test_presentation_no_new_resume_and_frozen_pdf(client):
    _, d = await source(client)
    original = d["document"]
    path = f"/api/v1/resume-workspaces/{d['id']}/presentation"
    result = await client.put(
        path,
        json={
            "expected_revision": d["revision"],
            "hidden_sections": ["education"],
            "experience_order": "projects_first",
        },
    )
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["document"] == original and saved["id"] == d["id"]
    assert saved["saved_at"]
    assert len((await client.get("/api/v1/resume-workspaces")).json()) == 1
    assert (
        await client.put(path, json={"expected_revision": d["revision"], "hidden_sections": []})
    ).status_code == 409
    rendered = await client.post(
        f"/api/v1/resume-workspaces/{d['id']}/render", json={"expected_revision": saved["revision"]}
    )
    assert rendered.status_code == 200, rendered.text
    data = rendered.json()
    assert data["artifact"]["report"]["render_status"] == "accepted", data
    assert data["artifact"]["report"]["presentation"]["hidden_sections"] == ["education"]
    import io

    import pdfplumber

    content = (await client.get(f"/api/v1/artifacts/{data['artifact']['id']}/download")).content
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = pdf.pages[0].extract_text()
        assert "合成education" not in text
        assert text.index("合成projects") < text.index("合成experiences")
    version = (await client.get("/api/v1/resume-library/versions")).json()["items"][0]
    changed = await client.put(
        f"/api/v1/resume-library/versions/{version['id']}/presentation",
        json={
            "expected_revision": version["metadata_revision"],
            "hidden_sections": [],
            "experience_order": "work_first",
        },
    )
    assert changed.status_code == 200, changed.text
    old = (await client.get(f"/api/v1/artifacts/{data['artifact']['id']}")).json()
    assert old["report"]["presentation"]["hidden_sections"] == ["education"]
    assert len((await client.get("/api/v1/resume-library/versions")).json()["items"]) == 1


async def test_ai_content_only_schema_materializes_canonical_order(client):
    profile, _ = await source(client)
    created = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "base_resume_drafting",
            "profile_id": profile["id"],
            "mode": "fixture",
        },
    )
    assert created.status_code == 201, created.text
    path = f"/api/v1/product-drafts/{created.json()['id']}"
    output = await client.post(path + "/execute")
    assert output.json()["status"] == "completed", output.text
    assert "items" in output.json()["output"] and "sections" not in output.json()["output"]
    saved = await client.post(path + "/adopt", json={})
    assert saved.status_code == 200, saved.text
    workspace = (
        await client.get(
            f"/api/v1/resume-workspaces/{saved.json()['adopted']['resume_workspace_id']}"
        )
    ).json()
    assert [s["name"] for s in workspace["document"]["sections"]] == [
        "education",
        "experience",
        "projects",
        "skills",
    ]
    rendered = await client.post(
        f"/api/v1/resume-workspaces/{workspace['id']}/render",
        json={"expected_revision": workspace["revision"]},
    )
    assert rendered.status_code == 200, rendered.text
    assert rendered.json()["claim_issues"] == []
    assert rendered.json()["artifact"]["report"]["render_status"] == "accepted"


async def test_ai_create_refine_overflow_compress_pdf_same_lineage(client):
    w = await section(client, await work(client), "personal", {"display_name": "合成用户"})
    w = await section(
        client,
        w,
        "projects",
        [{"organization": "合成项目", "description": "实现离线回归测试。\n" * 70}],
    )
    profile = (
        await client.post(
            "/api/v1/profile-workspace/publish", json={"expected_revision": w["revision"]}
        )
    ).json()

    async def generate(task, **kwargs):
        c = await client.post(
            "/api/v1/product-drafts",
            json={"request_id": str(uuid4()), "task": task, "mode": "fixture", **kwargs},
        )
        assert c.status_code == 201, c.text
        path = f"/api/v1/product-drafts/{c.json()['id']}"
        r = await client.post(path + "/execute")
        assert r.json()["status"] == "completed", r.text
        a = await client.post(path + "/adopt", json={})
        assert a.status_code == 200, a.text
        return a.json()["adopted"]

    base = await generate("base_resume_drafting", profile_id=profile["id"])
    refined = await generate(
        "resume_refinement",
        source_workspace_id=base["resume_workspace_id"],
        feedback="保持事实，整理表达。",
    )
    versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    original = next(v for v in versions if v["id"] == refined["resume_revision_id"])
    overflow = await client.post(
        f"/api/v1/resume-variants/{original['variant_id']}/render",
        json={"revision": original["revision"]},
    )
    assert overflow.json()["report"]["error_code"] == "layout_failed", overflow.text
    doc = (
        await client.get(
            f"/api/v1/resume-variants/{original['variant_id']}?revision={original['revision']}"
        )
    ).json()["document"]
    compressed = await generate(
        "resume_library_compression",
        source_resume_revision_id=original["id"],
    )
    proposal = compressed["resume_edit"]
    before_count = len((await client.get("/api/v1/resume-workspaces")).json())
    edited = {**doc, "sections": proposal["document"]["sections"]}
    chosen_ids = [
        i["item_id"] for sec in edited["sections"] for i in sec["items"] if i.get("short_text")
    ]
    save = await client.post(
        f"/api/v1/resume-library/versions/{original['id']}/expression",
        json={
            "request_id": str(uuid4()),
            "expected_revision": original["revision"],
            "expected_metadata_revision": original["metadata_revision"],
            "name": original["name"],
            "generation_id": proposal["generation_id"],
            "document": edited,
            "presentation": {"compact_item_ids": chosen_ids},
        },
    )
    assert save.status_code == 200, save.text
    new_id = save.json()["resume_revision_id"]
    versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    saved = next(v for v in versions if v["id"] == new_id)
    assert saved["variant_id"] == original["variant_id"]
    assert saved["entry_id"] == original["entry_id"]
    assert saved["name"] == original["name"]
    assert all(v["id"] != original["id"] for v in versions)
    assert len(versions) == 2  # root + optimized entry, no extra compression entry
    assert len((await client.get("/api/v1/resume-workspaces")).json()) == before_count
    final = await client.post(
        f"/api/v1/resume-variants/{saved['variant_id']}/render",
        json={"revision": saved["revision"]},
    )
    assert final.json()["report"]["render_status"] == "accepted", final.text
    old = (
        await client.get(
            f"/api/v1/resume-variants/{original['variant_id']}?revision={original['revision']}"
        )
    ).json()
    assert old["document"] == doc


async def test_legacy_workspace_presentation_is_normalized_on_read(client):
    _, row = await source(client)
    view = (await client.get(f"/api/v1/resume-workspaces/{row['id']}")).json()
    assert view["presentation"]["hidden_sections"] == []
    assert view["presentation"]["hidden_item_ids"] == []
    assert view["presentation"]["compact_item_ids"] == []
    assert view["presentation"]["item_order"] == []


async def test_resolved_source_rebinds_hard_claim_without_fact_review(client, sessions):
    from uuid import UUID

    from career_agent.infrastructure import entities as e
    from career_agent.profile_area.entities import ResumeWorkspace

    _, row = await source(client)
    resolved = (
        await client.post(
            f"/api/v1/resume-workspaces/{row['id']}/resolve",
            json={"expected_revision": row["revision"]},
        )
    ).json()
    revision_id = resolved["resume_revision_id"]
    async with sessions.begin() as session:
        original = await session.get(e.ResumeVariantRevision, UUID(revision_id))
        parent = await session.get(ResumeWorkspace, UUID(row["id"]))
        import copy

        doc = {"sections": copy.deepcopy(original.document["sections"])}
        item = doc["sections"][0]["items"][0]
        item["text"] += "\n来源支持的改写。"
        item["hard_claims"] = [
            {
                "kind": "organization",
                "value": item["text"].split("\n")[0],
                "fact_ref": item["fact_refs"][0],
            }
        ]
        evidence = {
            i["item_id"]: {"kind": "ai", "statement": i["text"] + "\n原始来源补充。"}
            for s in doc["sections"]
            for i in s["items"]
        }
        child = ResumeWorkspace(
            name="兼容精简",
            profile_id=parent.profile_id,
            source=parent.source,
            document=doc,
            content_sources=evidence,
            source_resume_revision_id=original.id,
        )
        session.add(child)
        await session.flush()
        child_id, revision = child.id, child.revision
    result = await client.post(
        f"/api/v1/resume-workspaces/{child_id}/resolve", json={"expected_revision": revision}
    )
    assert result.status_code == 200, result.text
    assert result.json()["resume_revision_id"]


async def test_edit_saves_presentation_without_duplicate_and_cas(client):
    _, row = await source(client)
    response = await client.post(
        f"/api/v1/resume-workspaces/{row['id']}/editions",
        json={
            "request_id": str(uuid4()),
            "expected_revision": row["revision"],
            "name": row["name"],
            "document": row["document"],
            "presentation": {
                "hidden_item_ids": [row["document"]["sections"][0]["items"][0]["item_id"]],
                "experience_order": "projects_first",
            },
        },
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["id"] == row["id"] and saved["document"] == row["document"]
    assert saved["presentation"]["experience_order"] == "projects_first"
    assert len((await client.get("/api/v1/resume-workspaces")).json()) == 1
    assert (
        await client.post(
            f"/api/v1/resume-workspaces/{row['id']}/editions",
            json={
                "request_id": str(uuid4()),
                "expected_revision": row["revision"],
                "name": row["name"],
                "document": row["document"],
                "presentation": {},
            },
        )
    ).status_code == 409


async def test_refinement_root_names_and_materialization_order(client):
    from test_product_drafts import draft

    _, row = await source(client)
    first = await draft(
        client, "resume_refinement", source_workspace_id=row["id"], feedback="保持事实。"
    )
    adopted = (await client.post(f"/api/v1/product-drafts/{first['id']}/adopt", json={})).json()[
        "adopted"
    ]
    second = await draft(
        client,
        "resume_refinement",
        source_resume_revision_id=adopted["resume_revision_id"],
        feedback="保持事实。",
    )
    next_result = (
        await client.post(f"/api/v1/product-drafts/{second['id']}/adopt", json={})
    ).json()["adopted"]
    versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    names = {v["id"]: v["name"] for v in versions}
    assert names[adopted["resume_revision_id"]] == row["name"] + " · AI优化版1"
    assert names[next_result["resume_revision_id"]] == row["name"] + " · AI优化版2"
    assert adopted["refinement_root_revision_id"] == next_result["refinement_root_revision_id"]
    root = next(v for v in versions if v["id"] == adopted["refinement_root_revision_id"])
    assert root["created_at"] == row["created_at"]
    assert versions[0]["id"] == next_result["resume_revision_id"]
    before = [v["id"] for v in versions]
    await client.patch(
        f"/api/v1/resume-library/versions/{root['id']}",
        json={"expected_revision": root["metadata_revision"], "name": "改名"},
    )
    assert [
        v["id"] for v in (await client.get("/api/v1/resume-library/versions")).json()["items"]
    ] == before
