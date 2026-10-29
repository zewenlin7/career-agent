import io

import pytest
from PIL import Image

pytestmark = pytest.mark.integration


async def work(client):
    r = await client.get("/api/v1/profile-workspace")
    assert r.status_code == 200, r.text
    return r.json()


async def section(client, w, name, value):
    r = await client.patch(
        "/api/v1/profile-workspace/sections/" + name,
        json={"expected_revision": w["section_revisions"][name], "value": value},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_sections_publish_noop_history_and_partial_inputs(client):
    w = await work(client)
    w = await section(
        client,
        w,
        "personal",
        {"display_name": "合成用户", "email": "demo@example.test", "city": "上海"},
    )
    w = await section(
        client,
        w,
        "education",
        [
            {
                "organization": "合成大学",
                "degree": "本科",
                "major": "",
                "role": "",
                "start_date": "",
                "description": "",
            }
        ],
    )
    w = await section(
        client,
        w,
        "projects",
        [{"organization": "离线项目", "technology_stack": "Python", "role": ""}],
    )
    skills = "语言：Python、SQL\n\nAI 应用：RAG、Agent\n"
    w = await section(client, w, "skills", skills)
    w = await section(
        client, w, "preferences", {"expected_role": "后端开发", "expected_city": "上海"}
    )
    assert (await client.get("/api/v1/profile")).status_code == 404
    unchanged = await section(client, w, "skills", skills)
    assert unchanged["revision"] == w["revision"]
    assert (await work(client))["data"]["skills_text"] == skills
    r = await client.post(
        "/api/v1/profile-workspace/publish", json={"expected_revision": w["revision"]}
    )
    assert r.status_code == 200, r.text
    first = r.json()
    w = await work(client)
    r = await client.post(
        "/api/v1/profile-workspace/publish", json={"expected_revision": w["revision"]}
    )
    assert r.json()["id"] == first["id"]
    # Independent section versions: saving skills doesn't conflict with personal edit.
    w2 = await section(client, w, "skills", "SQL")
    w2 = await section(client, w, "personal", {"display_name": "合成用户", "city": "北京"})
    bad = await client.patch(
        "/api/v1/profile-workspace/sections/personal",
        json={
            "expected_revision": w2["section_revisions"]["personal"],
            "value": {"display_name": "   "},
        },
    )
    assert bad.status_code == 422
    assert (await work(client))["data"]["skills_text"] == "SQL"
    r = await client.post(
        "/api/v1/profile-workspace/publish", json={"expected_revision": w2["revision"]}
    )
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["id"] != first["id"]
    restored = await client.post(
        "/api/v1/profile-workspace/restore",
        json={"expected_revision": (await work(client))["revision"], "profile_id": first["id"]},
    )
    assert restored.status_code == 200
    assert (await client.get("/api/v1/profile")).json()["id"] == second["id"]
    assert (await client.get("/api/v1/profile/revisions/" + first["id"])).json()["data"][
        "personal"
    ]["city"] == "上海"
    assert (await client.delete("/api/v1/profile/revisions/" + first["id"])).status_code == 200
    assert (await client.get("/api/v1/profile/revisions/" + first["id"])).status_code == 200


async def test_photos_normalize_replace_remove_and_freeze(client):
    image = Image.new("RGB", (30, 40), "white")
    data = io.BytesIO()
    image.save(data, format="PNG")
    r = await client.post(
        "/api/v1/profile-photos", content=data.getvalue(), headers={"content-type": "image/png"}
    )
    assert r.status_code == 201, r.text
    photo = r.json()
    fetched = await client.get(photo["url"])
    assert fetched.headers["content-type"] == "image/jpeg"
    assert fetched.content.startswith(b"\xff\xd8")
    w = await section(
        client,
        await work(client),
        "personal",
        {"display_name": "合成用户", "photo_id": photo["id"]},
    )
    p = (
        await client.post(
            "/api/v1/profile-workspace/publish", json={"expected_revision": w["revision"]}
        )
    ).json()
    replacement = (
        await client.post(
            "/api/v1/profile-photos", content=data.getvalue(), headers={"content-type": "image/png"}
        )
    ).json()
    w = await section(
        client,
        await work(client),
        "personal",
        {"display_name": "合成用户", "photo_id": replacement["id"]},
    )
    await section(client, w, "personal", {"display_name": "合成用户", "photo_id": None})
    assert (await client.get("/api/v1/profile/revisions/" + p["id"])).json()["data"]["personal"][
        "photo_id"
    ] == photo["id"]
    assert (await client.get(photo["url"])).status_code == 200
    assert (
        await client.post(
            "/api/v1/profile-photos", content=b"<svg/>", headers={"content-type": "image/png"}
        )
    ).status_code == 422


async def test_resume_resolve_names_and_archive_without_manual_facts(client):
    w = await section(client, await work(client), "personal", {"display_name": "合成用户"})
    await section(
        client,
        w,
        "projects",
        [{"organization": "合成项目", "role": "", "description": "实现测试工具"}],
    )
    d = (await client.post("/api/v1/resume-workspaces", json={})).json()
    assert d["document"]["sections"][0]["items"][0]["fact_refs"] == []
    saved = await resolve_document(client, d)
    # Saving a resume from a working draft doesn't publish it as the current personal profile.
    assert (await client.get("/api/v1/profile")).status_code == 404
    version = (await client.get("/api/v1/resume-library/versions")).json()["items"][0]
    assert version["name"].startswith("简历 ")
    rename = await client.patch(
        "/api/v1/resume-library/versions/" + version["id"],
        json={"expected_revision": 1, "name": "求职简历"},
    )
    assert rename.status_code == 200
    assert (
        await client.request(
            "DELETE",
            "/api/v1/resume-library/versions/" + version["id"],
            json={"expected_revision": 2},
        )
    ).status_code == 200
    assert (await client.get("/api/v1/resume-library/versions")).json()["items"] == []
    assert (
        await client.get(
            "/api/v1/resume-variants/" + saved["id"], params={"revision": saved["revision"]}
        )
    ).status_code == 200


async def test_profile_binding_deletion_protection(client):
    w = await section(client, await work(client), "personal", {"display_name": "合成用户"})
    p = (
        await client.post(
            "/api/v1/profile-workspace/publish", json={"expected_revision": w["revision"]}
        )
    ).json()
    j = await client.post(
        "/api/v1/jobs", json={"company_name": "合成公司", "title": "开发", "jd_text": "开发系统"}
    )
    assert j.status_code == 201, j.text
    bound = await client.put(
        f"/api/v1/applications/{j.json()['application_id']}/context",
        json={
            "expected_revision": 1,
            "profile_id": p["id"],
            "job_revision_id": j.json()["job_revision_id"],
            "resume_revision_id": None,
        },
    )
    assert bound.status_code == 200, bound.text
    assert (await client.delete("/api/v1/profile/revisions/" + p["id"])).status_code == 409


async def test_resume_bound_archive_block_and_formal_snapshot_immutable(client, sessions):
    from uuid import UUID

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    w = await section(client, await work(client), "personal", {"display_name": "合成用户"})
    w = await section(
        client, w, "projects", [{"organization": "离线项目", "description": "开发测试服务"}]
    )
    p = (
        await client.post(
            "/api/v1/profile-workspace/publish", json={"expected_revision": w["revision"]}
        )
    ).json()
    d = (await client.post("/api/v1/resume-workspaces", json={})).json()
    saved = await resolve_document(client, d)
    assert saved["document"]["profile_id"] != p["id"]  # new verified scope, old snapshot unchanged
    j = (
        await client.post(
            "/api/v1/jobs",
            json={"company_name": "合成企业", "title": "开发工程师", "jd_text": "开发工具"},
        )
    ).json()
    path = f"/api/v1/applications/{j['application_id']}/context"
    binding = (await client.get(path)).json()
    bind = await client.put(
        path,
        json={
            "expected_revision": binding["revision"],
            "profile_id": saved["document"]["profile_id"],
            "resume_revision_id": saved["resume_revision_id"],
            "job_revision_id": j["job_revision_id"],
        },
    )
    assert bind.status_code == 200, bind.text
    archive = await client.request(
        "DELETE",
        f"/api/v1/resume-library/versions/{saved['resume_revision_id']}",
        json={"expected_revision": 1},
    )
    assert archive.status_code == 409 and archive.json()["error"]["code"] == "resume_in_use"
    async with sessions.begin() as session:
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    text("UPDATE resume_variant_revisions SET document='{}'::jsonb WHERE id=:id"),
                    {"id": UUID(saved["resume_revision_id"])},
                )


async def test_photo_and_contacts_render_from_exact_snapshot(client):
    import pdfplumber

    image = Image.new("RGB", (30, 40), "white")
    data = io.BytesIO()
    image.save(data, format="PNG")
    photo = (
        await client.post(
            "/api/v1/profile-photos", content=data.getvalue(), headers={"content-type": "image/png"}
        )
    ).json()
    w = await section(
        client,
        await work(client),
        "personal",
        {
            "display_name": "合成用户",
            "email": "synthetic@example.test",
            "city": "上海",
            "photo_id": photo["id"],
        },
    )
    await section(
        client, w, "projects", [{"organization": "合成项目", "description": "开发离线工具"}]
    )
    draft = (await client.post("/api/v1/resume-workspaces", json={})).json()
    saved = await resolve_document(client, draft)
    w = await work(client)
    await section(client, w, "personal", {"display_name": "改后的资料", "photo_id": None})
    response = await client.post(
        f"/api/v1/resume-variants/{saved['id']}/render", json={"revision": 1}
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["report"]["render_status"] == "accepted", str(result["report"])
    assert result["report"]["versions"]["render_wrapper_version"] == "resume-render-wrapper-v5"
    content = (await client.get(f"/api/v1/artifacts/{result['id']}/download")).content
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = pdf.pages[0].extract_text()
        assert "合成用户" in text and "synthetic@example.test" in text
        assert "改后的资料" not in text
        assert pdf.pages[0].images


async def test_workspace_upgrade_preserves_old_document_and_mutability_boundary(
    client, sessions, migrated_url
):
    import asyncio
    import json
    from uuid import uuid4

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = migrated_url
    await asyncio.to_thread(command.downgrade, cfg, "b105c0402601")
    pid, vid, rid = uuid4(), uuid4(), uuid4()
    from career_agent.resume.schemas import ResumeDocument

    fid = uuid4()
    document = ResumeDocument.model_validate(
        {
            "profile_id": str(pid),
            "profile_revision": 1,
            "sections": [
                {
                    "section_id": str(uuid4()),
                    "name": "education",
                    "ordering": 0,
                    "priority": 50,
                    "items": [
                        {
                            "item_id": str(uuid4()),
                            "kind": "entry",
                            "text": "历史学校 本科",
                            "fact_refs": [str(fid)],
                            "ordering": 0,
                            "priority": 50,
                        }
                    ],
                }
            ],
        }
    ).model_dump(mode="json")
    async with sessions.begin() as session:
        await session.execute(
            text(
                "INSERT INTO personal_profiles (id,created_at,revision,data) VALUES "
                "(:id,now(),1,CAST(:data AS jsonb))"
            ),
            {
                "id": pid,
                "data": json.dumps(
                    {
                        "display_name": "历史资料",
                        "education": [
                            {
                                "organization": "历史学校",
                                "role": "本科",
                                "description": "",
                                "fact_ids": [str(fid)],
                            }
                        ],
                    }
                ),
            },
        )
        await session.execute(
            text(
                "INSERT INTO personal_facts "
                "(id,created_at,lineage_id,revision,statement,category,status,verified_at) "
                "VALUES (:id,now(),:id,1,'历史学校 本科','education','verified',now())"
            ),
            {"id": fid},
        )
        await session.execute(
            text(
                "INSERT INTO resume_variants (id,created_at,current_revision,library_visible) "
                "VALUES (:id,now(),1,true)"
            ),
            {"id": vid},
        )
        await session.execute(
            text(
                "INSERT INTO resume_variant_revisions "
                "(id,created_at,resume_variant_id,revision,profile_id,document,input_snapshot) "
                "VALUES (:id,now(),:variant,1,:profile,CAST(:doc AS jsonb),CAST(:snapshot AS "
                "jsonb))"
            ),
            {
                "id": rid,
                "variant": vid,
                "profile": pid,
                "doc": json.dumps(document),
                "snapshot": json.dumps(
                    {"display_name": "历史资料", "facts": [{"fact_id": str(fid), "revision": 1}]}
                ),
            },
        )
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.check, cfg)
    async with sessions.begin() as session:
        row = (
            await session.execute(
                text(
                    "SELECT display_name,library_number,document "
                    "FROM resume_variant_revisions WHERE "
                    "id=:id"
                ),
                {"id": rid},
            )
        ).one()
        assert row.display_name == "简历 1" and row.document == document
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    text("UPDATE resume_variant_revisions SET revision=2 WHERE id=:id"), {"id": rid}
                )
    p = (await client.get(f"/api/v1/profile/revisions/{pid}")).json()
    assert p["data"]["education"][0]["organization"] == "历史学校"
    assert p["data"]["personal"]["photo_id"] is None

    old = await client.get(f"/api/v1/resume-variants/{vid}?revision=1")
    assert old.status_code == 200, old.text
    rendered = await client.post(f"/api/v1/resume-variants/{vid}/render", json={"revision": 1})
    assert rendered.json()["report"]["render_status"] == "accepted", rendered.text


@pytest.mark.parametrize("with_photo", [False, True])
async def test_new_profile_fields_reach_structured_single_page_pdf(client, with_photo):
    import pdfplumber

    personal = {
        "display_name": "合成求职者",
        "phone": "13800000000",
        "email": "synthetic@example.test",
        "city": "上海",
        "github": "github.com/synthetic",
        "website": "https://example.test/portfolio",
    }
    if with_photo:
        image = Image.new("RGB", (60, 80), "white")
        content = io.BytesIO()
        image.save(content, format="PNG")
        uploaded = await client.post(
            "/api/v1/profile-photos",
            content=content.getvalue(),
            headers={"content-type": "image/png"},
        )
        personal["photo_id"] = uploaded.json()["id"]
    w = await section(client, await work(client), "personal", personal)
    w = await section(
        client,
        w,
        "education",
        [
            {
                "organization": "合成科技大学",
                "degree": "硕士",
                "major": "计算机科学",
                "start_date": "2023-09",
                "end_date": "2026-06",
                "description": "研究信息检索与分布式系统。",
            }
        ],
    )
    w = await section(
        client,
        w,
        "experiences",
        [
            {
                "organization": "合成智能公司",
                "role": "研发实习生",
                "start_date": "2025-03",
                "end_date": "2025-08",
                "description": "开发知识助手接口。",
                "achievements": "完成回滚测试。",
            }
        ],
    )
    w = await section(
        client,
        w,
        "projects",
        [
            {
                "organization": "求职工具",
                "role": "独立开发",
                "start_date": "2026-07",
                "end_date": "2026-10",
                "technology_stack": "Python · PostgreSQL",
                "description": "实现岗位匹配与评测。",
                "achievements": "完成离线验收。",
            }
        ],
    )
    await section(client, w, "skills", "语言：Python、SQL\n工程：Docker")
    draft = (await client.post("/api/v1/resume-workspaces", json={})).json()
    rendered = await client.post(
        f"/api/v1/resume-workspaces/{draft['id']}/render",
        json={"expected_revision": draft["revision"]},
    )
    assert rendered.status_code == 200, rendered.text
    result = rendered.json()
    assert result["claim_issues"] == []
    artifact = result["artifact"]
    assert artifact["report"]["render_status"] == "accepted", artifact["report"]
    pdf_bytes = (await client.get(f"/api/v1/artifacts/{artifact['id']}/download")).content
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        assert len(pdf.pages) == 1
        page = pdf.pages[0]
        text = page.extract_text()
        for value in [
            "13800000000",
            "synthetic@example.test",
            "上海",
            "github.com/synthetic",
            "example.test/portfolio",
            "硕士",
            "计算机科学",
            "2023.09",
            "2026.06",
            "2025.03",
            "2025.08",
            "完成回滚测试",
            "2026.07",
            "2026.10",
            "独立开发",
            "PostgreSQL",
            "完成离线验收",
            "Docker",
        ]:
            assert value in "".join(text.split()), (value, text)
        assert bool(page.images) is with_photo
        words = page.extract_words()
        heading = next(word for word in words if "合成科技大学" in word["text"])
        date = next(word for word in words if "2023.09" in word["text"])
        assert abs(heading["top"] - date["top"]) < 3
        assert date["x0"] > heading["x1"]


async def test_unrendered_resume_resolves_idempotently_without_manual_facts(client, evidence_rows):
    w = await section(client, await work(client), "personal", {"display_name": "合成用户"})
    await section(
        client, w, "projects", [{"organization": "合成项目", "description": "实现测试工具"}]
    )
    d = (await client.post("/api/v1/resume-workspaces", json={})).json()
    assert (await evidence_rows()) == []
    path = f"/api/v1/resume-workspaces/{d['id']}/resolve"
    first = await client.post(path, json={"expected_revision": d["revision"]})
    assert first.status_code == 200, first.text
    assert first.json()["claim_issues"] == []
    assert first.json()["resume_revision_id"]
    second = await client.post(path, json={"expected_revision": d["revision"]})
    assert second.json() == first.json()
    versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    assert len(versions) == 1
    renders = await client.get(f"/api/v1/resume-revisions/{versions[0]['id']}/renders")
    assert renders.json() == []


async def resolve_document(client, row):
    resolved = await client.post(
        f"/api/v1/resume-workspaces/{row['id']}/resolve",
        json={"expected_revision": row["revision"]},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["claim_issues"] == []
    versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    version = next(v for v in versions if v["id"] == resolved.json()["resume_revision_id"])
    return (
        await client.get(
            f"/api/v1/resume-variants/{version['variant_id']}",
            params={"revision": version["revision"]},
        )
    ).json()
