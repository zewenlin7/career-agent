from uuid import uuid4

import pytest
from test_preparation import prep_input as prep_fixture

prep_input = prep_fixture
pytestmark = pytest.mark.integration


async def test_actual_draft_edit_numbers_and_snapshot(client, prep_input):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    bound = await client.put(
        f"/api/v1/applications/{app['id']}/context", json={"expected_revision": 1, **prep_input}
    )
    assert bound.status_code == 200, bound.text
    created = await client.post(
        "/api/v1/interviews",
        json={
            "application_id": app["id"],
            "round_name": "技术一面",
            "status": "draft",
            "round_number": 1,
            "interview_type": "technical",
        },
    )
    assert created.status_code == 201, created.text
    row = created.json()
    path = f"/api/v1/interviews/{row['id']}"
    assert row["context_binding"]["profile_id"] == prep_input["profile_id"]
    assert not (await client.get("/api/v1/interviews", params={"application_id": app["id"]})).json()
    assert (
        len(
            (
                await client.get(
                    "/api/v1/interviews", params={"application_id": app["id"], "status": "draft"}
                )
            ).json()
        )
        == 1
    )
    bad = await client.patch(path, json={"expected_revision": 1, "status": "completed"})
    assert bad.status_code == 422
    first, follow, second = [str(uuid4()) for _ in range(3)]
    entries = [
        {
            "entry_id": first,
            "order": 1,
            "kind": "primary",
            "question": "事务是什么？",
            "answer": "原子提交。",
        },
        {
            "entry_id": follow,
            "order": 2,
            "kind": "follow_up",
            "primary_entry_id": first,
            "question": "如何回滚？",
        },
        {"entry_id": second, "order": 3, "kind": "primary", "question": "如何测试？"},
    ]
    saved = await client.patch(
        path,
        json={
            "expected_revision": 1,
            "entries": entries,
            "notes_text": "待复习",
            "status": "completed",
        },
    )
    assert saved.status_code == 200, saved.text
    numbered = saved.json()["entries"]
    assert [(x["main_question_number"], x["followup_index"]) for x in numbered] == [
        (1, None),
        (1, 1),
        (2, None),
    ]
    # Delete a group, preserve the identity/number of the surviving question.
    again = await client.patch(
        path, json={"expected_revision": 2, "entries": [numbered[2]], "notes_text": ""}
    )
    assert again.status_code == 200, again.text
    assert again.json()["entries"][0]["main_question_number"] == 2
    assert again.json()["notes"] == []
    stale = await client.patch(path, json={"expected_revision": 2, "entries": entries})
    assert stale.status_code == 409


async def test_knowledge_edit_delete_with_cas(client, prep_input):
    app = (await client.get("/api/v1/applications")).json()["items"][0]
    note = (
        await client.post(
            "/api/v1/knowledge-notes",
            json={"application_id": app["id"], "title": "复习", "content": "事务"},
        )
    ).json()
    path = f"/api/v1/knowledge-notes/{note['id']}"
    edited = await client.patch(
        path, json={"expected_revision": 1, "title": "复习计划", "content": "复习回滚"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 2
    assert (await client.delete(path, params={"expected_revision": 1})).status_code == 409
    assert (await client.delete(path, params={"expected_revision": 2})).status_code == 200
    assert (await client.delete(path, params={"expected_revision": 2})).status_code == 200
    listing = await client.get(f"/api/v1/applications/{app['id']}/knowledge-notes")
    assert listing.json()["items"] == []
    assert (await client.get("/api/v1/knowledge-notes")).json() == []
