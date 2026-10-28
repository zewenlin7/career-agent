from uuid import uuid4

from test_product_drafts import draft
from test_resume_presentation import source


async def test_compression_proposal_does_not_create_resume(client):
    _, work = await source(client)
    before = (await client.get("/api/v1/resume-workspaces")).json()
    result = await draft(client, "resume_library_compression", source_workspace_id=work["id"])
    adopted = await client.post(f"/api/v1/product-drafts/{result['id']}/adopt", json={})
    assert adopted.status_code == 200, adopted.text
    assert (await client.get("/api/v1/resume-workspaces")).json() == before
    proposal = adopted.json()["adopted"]["resume_edit"]
    assert proposal["source_workspace_id"] == work["id"]
    original = {i["item_id"]: i["text"] for s in work["document"]["sections"] for i in s["items"]}
    assert {
        i["item_id"]: i["text"] for s in proposal["document"]["sections"] for i in s["items"]
    } == original


async def test_two_resumes_same_profile_compress_their_own_text(client):
    _, first = await source(client)
    second = (
        await client.post(
            "/api/v1/resume-workspaces",
            json={"profile_id": first["profile_id"], "request_id": str(uuid4())},
        )
    ).json()
    document = second["document"]
    document["sections"][0]["items"][0]["text"] += "\n用户补充的不同表达。"
    second = (
        await client.post(
            f"/api/v1/resume-workspaces/{second['id']}/editions",
            json={
                "request_id": str(uuid4()),
                "expected_revision": second["revision"],
                "name": second["name"],
                "document": document,
            },
        )
    ).json()
    a = await draft(client, "resume_library_compression", source_workspace_id=first["id"])
    b = await draft(client, "resume_library_compression", source_workspace_id=second["id"])
    assert a["output"] != b["output"]


async def test_only_independent_roots_take_numbers_and_deleted_numbers_can_be_reused(client):
    _, first = await source(client)
    assert first["name"] == "简历 1"
    refinement = await draft(
        client, "resume_refinement", source_workspace_id=first["id"], feedback="保持事实。"
    )
    await client.post(f"/api/v1/product-drafts/{refinement['id']}/adopt", json={})
    second = (
        await client.post(
            "/api/v1/resume-workspaces",
            json={"profile_id": first["profile_id"], "request_id": str(uuid4())},
        )
    ).json()
    assert second["name"] == "简历 2"
    deleted = await client.request(
        "DELETE",
        f"/api/v1/resume-workspaces/{second['id']}",
        json={"expected_revision": second["revision"]},
    )
    assert deleted.status_code == 200, deleted.text
    third = (
        await client.post(
            "/api/v1/resume-workspaces",
            json={"profile_id": first["profile_id"], "request_id": str(uuid4())},
        )
    ).json()
    assert third["name"] == "简历 2" and third["id"] != second["id"]


async def test_editing_body_invalidates_unchanged_old_short_text(client):
    _, work = await source(client)
    document = work["document"]
    item = document["sections"][0]["items"][0]
    item["short_text"] = item["text"].split("\n")[0]
    saved = (
        await client.post(
            f"/api/v1/resume-workspaces/{work['id']}/editions",
            json={
                "request_id": str(uuid4()),
                "expected_revision": work["revision"],
                "name": work["name"],
                "document": document,
            },
        )
    ).json()
    document = saved["document"]
    document["sections"][0]["items"][0]["text"] += "\n新的正文表达。"
    edited = await client.post(
        f"/api/v1/resume-workspaces/{saved['id']}/editions",
        json={
            "request_id": str(uuid4()),
            "expected_revision": saved["revision"],
            "name": saved["name"],
            "document": document,
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["document"]["sections"][0]["items"][0]["short_text"] is None


async def test_compression_restores_exact_private_body_not_model_view(client):
    _, work = await source(client)
    document = work["document"]
    item = document["sections"][0]["items"][0]
    item["text"] += "\n合成用户负责实现离线测试。"
    work = (
        await client.post(
            f"/api/v1/resume-workspaces/{work['id']}/editions",
            json={
                "request_id": str(uuid4()),
                "expected_revision": work["revision"],
                "name": work["name"],
                "document": document,
            },
        )
    ).json()
    result = await draft(client, "resume_library_compression", source_workspace_id=work["id"])
    adopted = await client.post(f"/api/v1/product-drafts/{result['id']}/adopt", json={})
    assert adopted.status_code == 200, adopted.text
    proposal = adopted.json()["adopted"]["resume_edit"]["document"]
    assert [i["text"] for s in proposal["sections"] for i in s["items"]] == [
        i["text"] for s in document["sections"] for i in s["items"]
    ]


async def test_refinement_rename_forks_persistent_naming_branch(client):
    _, work = await source(client)

    async def optimize(**source_args):
        result = await draft(client, "resume_refinement", feedback="保持事实。", **source_args)
        response = await client.post(f"/api/v1/product-drafts/{result['id']}/adopt", json={})
        assert response.status_code == 200, response.text
        return response.json()["adopted"]["resume_revision_id"]

    first = await optimize(source_workspace_id=work["id"])
    versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    old = next(v for v in versions if v["id"] == first)
    root = next(v for v in versions if v["name"] == "简历 1")
    second = await optimize(source_resume_revision_id=root["id"])
    renamed = await client.patch(
        f"/api/v1/resume-library/versions/{first}",
        json={"expected_revision": old["metadata_revision"], "name": "上海外企版"},
    )
    assert renamed.status_code == 200
    branch_first = await optimize(source_resume_revision_id=first)
    branch_second = await optimize(source_resume_revision_id=branch_first)
    third = await optimize(source_resume_revision_id=second)
    names = {
        v["id"]: v["name"]
        for v in (await client.get("/api/v1/resume-library/versions")).json()["items"]
    }
    assert names[second] == "简历 1 · AI优化版2"
    assert names[third] == "简历 1 · AI优化版3"
    assert names[branch_first] == "上海外企版 · AI优化版1"
    assert names[branch_second] == "上海外企版 · AI优化版2"


async def test_compression_only_generates_visible_missing_expressions(client):
    _, work = await source(client)
    document = work["document"]
    existing = document["sections"][0]["items"][0]
    existing["short_text"] = existing["text"].split("\n")[0]
    hidden = document["sections"][1]["items"][0]
    work = (
        await client.post(
            f"/api/v1/resume-workspaces/{work['id']}/editions",
            json={
                "request_id": str(uuid4()),
                "expected_revision": work["revision"],
                "name": work["name"],
                "document": document,
                "presentation": {
                    "hidden_item_ids": [hidden["item_id"]],
                    "hidden_sections": ["skills"],
                },
            },
        )
    ).json()
    result = await draft(client, "resume_library_compression", source_workspace_id=work["id"])
    ids = {i["source_item_id"] for i in result["output"]["items"]}
    assert existing["item_id"] not in ids
    assert hidden["item_id"] not in ids
    assert document["sections"][-1]["items"][0]["item_id"] not in ids
    adopted = (await client.post(f"/api/v1/product-drafts/{result['id']}/adopt", json={})).json()[
        "adopted"
    ]["resume_edit"]
    items = {i["item_id"]: i for s in adopted["document"]["sections"] for i in s["items"]}
    assert items[existing["item_id"]]["short_text"] == existing["short_text"]
    assert items[hidden["item_id"]]["short_text"] is None


async def test_ordinary_edits_replace_one_library_entry_and_preserve_history(client):
    _, work = await source(client)
    original_doc = work["document"]
    original_id = work["id"]
    entry_id = work.get("entry_id", original_id)
    import copy

    for kind in ("body", "hide", "short"):
        document = copy.deepcopy(work["document"])
        presentation = work["presentation"]
        item = document["sections"][0]["items"][0]
        if kind == "body":
            item["text"] += "\n用户补充表达。"
        elif kind == "hide":
            presentation = {**presentation, "hidden_item_ids": [item["item_id"]]}
        else:
            item["short_text"] = item["text"].split("\n")[0]
        response = await client.post(
            f"/api/v1/resume-workspaces/{work['id']}/editions",
            json={
                "request_id": str(uuid4()),
                "expected_revision": work["revision"],
                "document": document,
                "name": work["name"],
                "presentation": presentation,
            },
        )
        assert response.status_code == 200, response.text
        work = response.json()
        visible = (await client.get("/api/v1/resume-workspaces")).json()
        assert len(visible) == 1
        assert visible[0]["entry_id"] == entry_id
    assert (await client.get(f"/api/v1/resume-workspaces/{original_id}")).json()[
        "document"
    ] == original_doc


async def test_short_text_validation_reports_safe_item_locations(client):
    _, work = await source(client)
    document = work["document"]
    for sec in document["sections"][:2]:
        sec["items"][0]["short_text"] = sec["items"][0]["text"]
    response = await client.post(
        f"/api/v1/resume-workspaces/{work['id']}/editions",
        json={
            "request_id": str(uuid4()),
            "expected_revision": work["revision"],
            "document": document,
            "name": work["name"],
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "resume_field_validation"
    assert error["fields"] == [
        {"section": n, "item": 0, "field": "short_text", "code": "short_text_not_shorter"}
        for n in (0, 1)
    ]
    assert "实现离线测试" not in response.text


async def test_formal_edit_keeps_entry_through_workspace_and_materialization(client):
    _, work = await source(client)
    resolved = (
        await client.post(
            f"/api/v1/resume-workspaces/{work['id']}/resolve",
            json={"expected_revision": work["revision"]},
        )
    ).json()
    original = (await client.get("/api/v1/resume-library/versions")).json()["items"][0]
    exact = (
        await client.get(
            f"/api/v1/resume-variants/{original['variant_id']}?revision={original['revision']}"
        )
    ).json()
    import copy

    document = copy.deepcopy(exact["document"])
    document["sections"][0]["items"][0]["text"] += "\n用户补充表达。"
    saved = await client.post(
        f"/api/v1/resume-library/versions/{resolved['resume_revision_id']}/expression",
        json={
            "request_id": str(uuid4()),
            "expected_revision": original["revision"],
            "expected_metadata_revision": original["metadata_revision"],
            "name": original["name"],
            "document": document,
            "presentation": original["presentation"],
        },
    )
    assert saved.status_code == 200, saved.text
    editing = saved.json()["workspace"]
    assert editing["entry_id"] == original["entry_id"]
    assert (await client.get("/api/v1/resume-library/versions")).json()["items"] == []
    assert len((await client.get("/api/v1/resume-workspaces")).json()) == 1
    next_result = await client.post(
        f"/api/v1/resume-workspaces/{editing['id']}/resolve",
        json={"expected_revision": editing["revision"]},
    )
    assert next_result.status_code == 200, next_result.text
    assert next_result.json()["resume_revision_id"]
    versions = (await client.get("/api/v1/resume-library/versions")).json()["items"]
    assert len(versions) == 1
    assert versions[0]["entry_id"] == original["entry_id"]
    assert versions[0]["variant_id"] == original["variant_id"]
    assert versions[0]["created_at"] == original["created_at"]
    assert (
        await client.get(
            f"/api/v1/resume-variants/{original['variant_id']}?revision={original['revision']}"
        )
    ).json()["document"] == exact["document"]
