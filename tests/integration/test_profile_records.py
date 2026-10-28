import pytest

pytestmark = pytest.mark.integration


async def test_named_profiles_independent_save_and_noop(client):
    a = (await client.post("/api/v1/profile-library")).json()
    b = (await client.post("/api/v1/profile-library")).json()
    assert a["id"] != b["id"] and a["name"] != b["name"]
    r = await client.patch(
        f"/api/v1/profile-library/{a['id']}",
        json={"expected_revision": a["revision"], "name": "上海求职资料"},
    )
    assert r.status_code == 200, r.text
    a = r.json()
    payload = {"expected_revision": 1, "value": {"display_name": "合成用户", "city": "上海"}}
    r = await client.patch(f"/api/v1/profile-library/{a['id']}/sections/personal", json=payload)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["name"] == "上海求职资料" and a["profile_id"]
    payload["expected_revision"] = a["section_revisions"]["personal"]
    same = (
        await client.patch(f"/api/v1/profile-library/{a['id']}/sections/personal", json=payload)
    ).json()
    assert same["revision"] == a["revision"] and same["profile_id"] == a["profile_id"]
    assert (await client.get(f"/api/v1/profile-library/{b['id']}")).json()["profile_id"] is None
    assert (
        await client.request(
            "DELETE",
            f"/api/v1/profile-library/{b['id']}",
            json={"expected_revision": b["revision"]},
        )
    ).status_code == 200
    assert len((await client.get("/api/v1/profile-library")).json()["items"]) == 1


async def test_mixed_fact_batch_and_updated_time(client):
    ids = []
    for text in ["编写 Python 服务", "使用 SQL 分析"]:
        r = await client.post("/api/v1/facts", json={"statement": text, "category": "skill"})
        ids.append(r.json()["id"])
    await client.post("/api/v1/facts/" + ids[0] + "/verify")
    r = await client.post("/api/v1/fact-library/actions", json={"ids": ids, "action": "verify"})
    assert r.status_code == 200, r.text
    rows = (await client.get("/api/v1/fact-library")).json()["items"]
    assert all(f["status"] == "verified" and f["updated_at"] for f in rows)


async def named_source(client):
    row = (await client.post("/api/v1/profile-library")).json()
    for section, value in [
        (
            "personal",
            {"display_name": "合成用户", "email": "synthetic@example.test", "city": "上海"},
        ),
        (
            "projects",
            [
                {
                    "organization": "离线项目",
                    "description": "实现事务回滚测试。",
                    "technology_stack": "Python",
                }
            ],
        ),
    ]:
        response = await client.patch(
            f"/api/v1/profile-library/{row['id']}/sections/{section}",
            json={"expected_revision": row["section_revisions"][section], "value": value},
        )
        assert response.status_code == 200, response.text
        row = response.json()
    return row


async def test_resume_source_idempotency_editions_and_no_fact_gate(client):
    import asyncio
    from uuid import uuid4

    source = await named_source(client)
    request = {"request_id": str(uuid4()), "profile_id": source["profile_id"]}
    responses = await asyncio.gather(
        *(client.post("/api/v1/resume-workspaces", json=request) for _ in range(2))
    )
    assert all(r.status_code == 201 for r in responses)
    original = responses[0].json()
    assert original["id"] == responses[1].json()["id"]
    assert original["personal"]["email"] == "synthetic@example.test"
    assert "Python" in original["document"]["sections"][0]["items"][0]["text"]
    assert (await client.get("/api/v1/facts")).json() == []
    body = {
        "request_id": str(uuid4()),
        "expected_revision": original["revision"],
        "name": original["name"],
        "document": original["document"],
    }
    assert (
        await client.post(f"/api/v1/resume-workspaces/{original['id']}/editions", json=body)
    ).json()["id"] == original["id"]
    body["document"]["sections"][0]["items"][0]["text"] = "离线项目\n实现回滚测试。"
    body["request_id"] = str(uuid4())
    edited = await client.post(f"/api/v1/resume-workspaces/{original['id']}/editions", json=body)
    assert edited.status_code == 200, edited.text
    assert edited.json()["id"] != original["id"]
    assert (await client.get("/api/v1/resume-workspaces/" + original["id"])).json()[
        "document"
    ] != edited.json()["document"]
    assert (await client.get("/api/v1/facts")).json() == []


async def test_ai_resume_without_facts_and_selected_extraction(client):
    from test_product_drafts import draft

    source = await named_source(client)
    ai = await draft(client, "base_resume_drafting", profile_id=source["profile_id"])
    adopted = await client.post(f"/api/v1/product-drafts/{ai['id']}/adopt", json={})
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["adopted"]["resume_workspace_id"]
    assert (await client.get("/api/v1/facts")).json() == []
    for _ in range(2):
        extraction = await draft(client, "profile_fact_extraction", profile_id=source["profile_id"])
        r = await client.post(
            f"/api/v1/product-drafts/{extraction['id']}/adopt", json={"selected_indices": [0]}
        )
        assert r.status_code == 200, r.text
    facts = (await client.get("/api/v1/fact-library")).json()["items"]
    assert len(facts) == 1 and facts[0]["status"] == "proposed"
    assert facts[0]["source_label"] == "个人资料提取"
    assert (await client.get("/api/v1/profile-library/" + source["id"])).json()[
        "profile_id"
    ] == source["profile_id"]


async def test_cancel_interrupts_running_generation(client, monkeypatch):
    import asyncio
    from uuid import uuid4

    from career_agent.interview.calls import InterviewCalls

    entered, stopped = asyncio.Event(), asyncio.Event()

    async def blocked(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(InterviewCalls, "generate", blocked)
    source = await named_source(client)
    created = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "profile_fact_extraction",
            "profile_id": source["profile_id"],
        },
    )
    id = created.json()["id"]
    running = asyncio.create_task(client.post(f"/api/v1/product-drafts/{id}/execute"))
    await asyncio.wait_for(entered.wait(), 5)
    cancelled = await client.post(f"/api/v1/product-drafts/{id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled" and stopped.is_set()
    result = await asyncio.wait_for(running, 5)
    assert result.json()["status"] == "cancelled" and result.json()["output"] is None
    assert (await client.get("/api/v1/facts")).json() == []


async def test_pdf_confirmation_and_resume_extraction_provenance(client):
    from uuid import uuid4

    from test_product_drafts import draft

    source = await named_source(client)
    row = (
        await client.post(
            "/api/v1/resume-workspaces",
            json={"request_id": str(uuid4()), "profile_id": source["profile_id"]},
        )
    ).json()
    r = await client.post(
        f"/api/v1/resume-workspaces/{row['id']}/render", json={"expected_revision": row["revision"]}
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["claim_issues"] == []
    assert result["artifact"]["report"]["render_status"] == "accepted", result
    resume_id = result["resume_revision_id"]
    proposal = await draft(client, "profile_fact_extraction", source_resume_revision_id=resume_id)
    adopted = await client.post(
        f"/api/v1/product-drafts/{proposal['id']}/adopt", json={"selected_indices": [0]}
    )
    assert adopted.status_code == 200, adopted.text
    assert len(adopted.json()["adopted"]["existing_fact_ids"]) == 1
    assert len((await client.get("/api/v1/facts")).json()) == 1


async def test_ai_compression_skips_existing_short_expression_without_model_call(client):
    from uuid import uuid4

    source = await named_source(client)
    row = (
        await client.post(
            "/api/v1/resume-workspaces",
            json={"request_id": str(uuid4()), "profile_id": source["profile_id"]},
        )
    ).json()
    item = row["document"]["sections"][0]["items"][0]
    item["short_text"] = "离线项目\n实现回滚测试。"
    saved = (
        await client.post(
            f"/api/v1/resume-workspaces/{row['id']}/editions",
            json={
                "expected_revision": row["revision"],
                "request_id": str(uuid4()),
                "name": row["name"],
                "document": row["document"],
            },
        )
    ).json()
    response = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "resume_library_compression",
            "source_workspace_id": saved["id"],
            "mode": "fixture",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "compression_not_needed"
    assert (await client.get("/api/v1/resume-workspaces/" + saved["id"])).json()[
        "document"
    ] == saved["document"]


async def test_unrendered_resume_extraction_freezes_source_and_proposes_only(client):
    from uuid import uuid4

    source = await named_source(client)
    resume = (
        await client.post(
            "/api/v1/resume-workspaces",
            json={"request_id": str(uuid4()), "profile_id": source["profile_id"]},
        )
    ).json()
    created = await client.post(
        "/api/v1/product-drafts",
        json={
            "request_id": str(uuid4()),
            "task": "profile_fact_extraction",
            "source_workspace_id": resume["id"],
        },
    )
    assert created.status_code == 201, created.text
    id = created.json()["id"]
    completed = await client.post(f"/api/v1/product-drafts/{id}/execute")
    assert completed.json()["status"] == "completed", completed.text
    adopted = await client.post(
        f"/api/v1/product-drafts/{id}/adopt", json={"selected_indices": [0]}
    )
    assert adopted.status_code == 200, adopted.text
    rows = (await client.get("/api/v1/fact-library")).json()["items"]
    assert len(rows) == 1 and rows[0]["status"] == "proposed"
    assert rows[0]["source_label"] == "简历提取"
    assert rows[0]["source_locator"].startswith(
        f"resume-draft:{resume['id']}:{resume['revision']}:"
    )


async def test_saved_resume_discovery_has_stable_pagination(client):
    from uuid import uuid4

    source = await named_source(client)
    ids = []
    for _ in range(3):
        row = (
            await client.post(
                "/api/v1/resume-workspaces",
                json={"request_id": str(uuid4()), "profile_id": source["profile_id"]},
            )
        ).json()
        ids.append(row["id"])
    pages = [
        (await client.get(f"/api/v1/resume-workspaces?limit=1&offset={i}")).json() for i in range(4)
    ]
    assert [page[0]["id"] for page in pages[:3]] == list(reversed(ids))
    assert pages[3] == []


async def test_profile_create_intent_is_idempotent_and_name_edits_are_atomic(client):
    import asyncio
    from uuid import uuid4

    body = {"request_id": str(uuid4())}
    results = await asyncio.gather(
        *(client.post("/api/v1/profile-library", json=body) for _ in range(2))
    )
    a, b = [r.json() for r in results]
    assert a["id"] == b["id"]
    saved = await client.patch(
        f"/api/v1/profile-library/{a['id']}/sections/personal",
        json={
            "expected_revision": 1,
            "expected_record_revision": 1,
            "record_name": "我的资料",
            "value": {"display_name": "合成用户"},
        },
    )
    assert saved.status_code == 200, saved.text
    row = saved.json()
    assert row["name"] == "我的资料"
    same = await client.patch(
        f"/api/v1/profile-library/{a['id']}/sections/personal",
        json={
            "expected_revision": row["section_revisions"]["personal"],
            "expected_record_revision": row["revision"],
            "record_name": "我的资料",
            "value": {"display_name": "合成用户"},
        },
    )
    assert same.json()["profile_id"] == row["profile_id"]


async def test_unsupported_ai_claim_is_specific_and_never_verified(client, sessions):
    from uuid import UUID, uuid4

    from career_agent.profile_area.entities import ResumeWorkspace

    source = await named_source(client)
    row = (
        await client.post(
            "/api/v1/resume-workspaces",
            json={"request_id": str(uuid4()), "profile_id": source["profile_id"]},
        )
    ).json()
    async with sessions.begin() as session:
        saved = await session.get(ResumeWorkspace, UUID(row["id"]))
        import copy

        document = copy.deepcopy(saved.document)
        document["sections"][0]["items"][0]["text"] = "提升效率 99%"
        saved.document = document
    result = await client.post(
        f"/api/v1/resume-workspaces/{row['id']}/render", json={"expected_revision": row["revision"]}
    )
    assert result.status_code == 200, result.text
    assert result.json()["artifact"] is None
    assert result.json()["claim_issues"][0]["text"] == "提升效率 99%"
    assert not any(
        f["statement"] == "提升效率 99%" for f in (await client.get("/api/v1/facts")).json()
    )
    from test_product_drafts import draft

    correction = await draft(
        client,
        "resume_claim_refinement",
        source_workspace_id=row["id"],
        selected_item_ids=[row["document"]["sections"][0]["items"][0]["item_id"]],
        feedback="仅保留原始资料支持的描述",
    )
    adopted = await client.post(f"/api/v1/product-drafts/{correction['id']}/adopt", json={})
    assert adopted.status_code == 200, adopted.text
    repaired = (
        await client.get(
            "/api/v1/resume-workspaces/" + adopted.json()["adopted"]["resume_workspace_id"]
        )
    ).json()
    assert repaired["id"] != row["id"]
    assert "99%" not in str(repaired["document"])
    old = (await client.get("/api/v1/resume-workspaces/" + row["id"])).json()
    assert "99%" in str(old["document"])


async def test_profile_global_edit_isolated_local_save_cancel_commit_and_conflict(client):
    row = await named_source(client)
    path = f"/api/v1/profile-library/{row['id']}"
    original = (await client.get(path)).json()
    edit = (
        await client.post(path + "/editing", json={"expected_revision": original["revision"]})
    ).json()
    data = {**edit["data"], "skills_text": "语言：Python\n工程：PostgreSQL"}
    saved = await client.put(
        path + "/editing",
        json={"edit_id": edit["id"], "expected_revision": edit["revision"], "data": data},
    )
    assert saved.status_code == 200, saved.text
    edit = saved.json()
    assert (await client.get(path)).json() == original
    # Reopening recovers locally saved work, not a new committed snapshot.
    assert (
        await client.post(path + "/editing", json={"expected_revision": original["revision"]})
    ).json() == edit
    cancelled = await client.post(
        path + "/editing/cancel",
        json={"edit_id": edit["id"], "expected_revision": edit["revision"]},
    )
    assert cancelled.status_code == 200
    assert cancelled.json() == original
    assert (
        await client.post(
            path + "/editing/commit",
            json={"edit_id": edit["id"], "expected_revision": edit["revision"]},
        )
    ).status_code == 409
    edit = (
        await client.post(path + "/editing", json={"expected_revision": original["revision"]})
    ).json()
    unchanged = await client.post(
        path + "/editing/commit",
        json={"edit_id": edit["id"], "expected_revision": edit["revision"]},
    )
    assert unchanged.json() == original
    edit = (
        await client.post(path + "/editing", json={"expected_revision": original["revision"]})
    ).json()
    edit = (
        await client.put(
            path + "/editing",
            json={"edit_id": edit["id"], "expected_revision": edit["revision"], "data": data},
        )
    ).json()
    committed = await client.post(
        path + "/editing/commit",
        json={"edit_id": edit["id"], "expected_revision": edit["revision"]},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["profile_id"] != original["profile_id"]
    assert committed.json()["data"]["skills_text"] == data["skills_text"]


async def test_library_refinement_reuses_task_and_records_exact_feedback(client):
    from uuid import uuid4

    from test_product_drafts import draft

    source = await named_source(client)
    work = (
        await client.post(
            "/api/v1/resume-workspaces",
            json={"request_id": str(uuid4()), "profile_id": source["profile_id"]},
        )
    ).json()
    generated = await draft(
        client, "resume_refinement", source_workspace_id=work["id"], feedback="突出离线测试。"
    )
    assert generated["lineage"]["source_workspace_id"] == work["id"]
    source_revision = generated["lineage"]["source_resume_revision_id"]
    assert source_revision
    result = await client.post(f"/api/v1/product-drafts/{generated['id']}/adopt", json={})
    assert result.status_code == 200, result.text
    result = result.json()
    revised_id = result["adopted"]["resume_revision_id"]
    assert revised_id != source_revision
    library = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    assert {source_revision, revised_id} <= {row["id"] for row in library}
    subject = (await client.get(f"/api/v1/resume-library/subjects/{revised_id}")).json()[
        "feedback_target"
    ]
    assert subject["task_type"] == "resume_refinement"
    assert subject["accepted_model_call_id"] == generated["accepted_model_call_id"]
    feedback = await client.post(
        "/api/v1/evaluation/feedback",
        json={"subject": subject, "vote": "thumbs_up", "comment": "表达更清晰"},
    )
    assert feedback.status_code == 201, feedback.text
    second = await draft(
        client,
        "resume_refinement",
        source_resume_revision_id=revised_id,
        feedback="继续精简表达。",
        feedback_id=feedback.json()["id"],
    )
    assert second["lineage"]["source_resume_revision_id"] == revised_id
    assert second["lineage"]["feedback_id"] == feedback.json()["id"]
