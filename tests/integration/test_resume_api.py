import asyncio
import copy
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from career_agent.infrastructure import entities as e
from career_agent.resume.schemas import RenderReport

pytestmark = [pytest.mark.integration, pytest.mark.typst]


@pytest.fixture
async def resume_input(sessions):
    f = json.loads(
        await asyncio.to_thread(Path("tests/fixtures/resumes/normal_one_page.json").read_text)
    )
    async with sessions.begin() as session:
        for fact in f["facts"]:
            session.add(
                e.PersonalFact(
                    id=UUID(fact["id"]),
                    statement=fact["statement"],
                    category="synthetic",
                    status=e.FactStatus.VERIFIED,
                    verified_at=e.utcnow(),
                )
            )
        await session.flush()
        session.add(
            e.PersonalProfile(
                id=UUID(f["document"]["profile_id"]),
                revision=1,
                data={
                    "display_name": f["name"],
                    "projects": [
                        {
                            "organization": "Example",
                            "role": "Fixture",
                            "fact_ids": [fact["id"] for fact in f["facts"]],
                        }
                    ],
                },
            )
        )
    return f["document"]


async def test_variant_revisions_render_download(client, sessions, resume_input):
    response = await client.post("/api/v1/resume-variants", json=resume_input)
    assert response.status_code == 201, response.text
    variant = response.json()
    url = "/api/v1/resume-variants/" + variant["id"]
    assert (await client.get(url)).json() == variant
    changed = copy.deepcopy(resume_input)
    changed["sections"][0]["items"][0]["text"] = (
        "Backend engineer focused on reliable Python services."
    )
    response = await client.post(
        url + "/revisions", json={"expected_revision": 1, "document": changed}
    )
    assert response.status_code == 201 and response.json()["revision"] == 2
    assert (await client.get(url + "?revision=1")).json() == variant
    assert (
        await client.post(url + "/revisions", json={"expected_revision": 1, "document": changed})
    ).status_code == 409
    response = await client.post(url + "/render", json={"revision": 1})
    assert response.status_code == 201, response.text
    artifact = response.json()
    assert artifact["resume_variant_revision"] == 1
    report = artifact["report"]
    assert report["render_status"] == "accepted", report
    assert report["page_count"] == 1 and report["validation_status"] == "passed"
    assert report["versions"]["compiler_version"] == "0.15.1"
    assert report["versions"]["resume_variant_schema_version"] == "resume-v2"
    assert report["versions"]["resume_template_version"] == "resume_zh_cn_a4_single_v1"
    assert report["versions"]["layout_policy_version"] == "content-v1"
    artifact_url = "/api/v1/artifacts/" + artifact["id"]
    assert (await client.get(artifact_url)).json() == artifact
    pdf = await client.get(artifact_url + "/download")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert hashlib.sha256(pdf.content).hexdigest() == artifact["file_hash"]
    assert pdf.headers["cache-control"] == "no-store"
    async with sessions() as session:
        row = await session.get(e.RenderArtifact, UUID(artifact["id"]))
        assert row.report["versions"]["compiler_version"] == "0.15.1"
        with pytest.raises(DBAPIError):
            await session.execute(text("UPDATE resume_variant_revisions SET revision=99"))
        await session.rollback()
        session.add(
            e.RenderArtifact(
                resume_variant_id=UUID(variant["id"]),
                resume_variant_revision=999,
                report=RenderReport(render_status="failed", validation_status="not_run").model_dump(
                    mode="json"
                ),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.parametrize("status", ["proposed", "rejected", "superseded"])
async def test_render_rechecks_fact_status(client, sessions, resume_input, status):
    variant = (await client.post("/api/v1/resume-variants", json=resume_input)).json()
    async with sessions.begin() as session:
        fact = await session.get(
            e.PersonalFact, UUID(resume_input["sections"][0]["items"][0]["fact_refs"][0])
        )
        fact.status = e.FactStatus(status)
    response = await client.post(
        f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1}
    )
    artifact = response.json()
    assert artifact["report"]["error_code"] == "grounding_failed", artifact
    assert artifact["report"]["findings"][0]["code"] == "missing_verified_fact"
    assert artifact["artifact_ref"] is None and artifact["file_hash"] is None
    assert artifact["report"]["attempts"] == []
    assert (await client.get(f"/api/v1/artifacts/{artifact['id']}/download")).status_code == 409


async def test_wrong_profile_requirement_and_hard_field(client, sessions, resume_input):
    doc = copy.deepcopy(resume_input)
    doc["sections"][0]["items"][0]["requirement_refs"] = [str(uuid4())]
    variant = (await client.post("/api/v1/resume-variants", json=doc)).json()
    artifact = (
        await client.post(f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1})
    ).json()
    assert "invalid_requirement_reference" in {f["code"] for f in artifact["report"]["findings"]}
    async with sessions.begin() as session:
        profile = e.PersonalProfile(revision=2, data={"display_name": "Other Snapshot"})
        session.add(profile)
        await session.flush()
        doc["profile_id"] = str(profile.id)
    doc["profile_revision"] = 2
    variant = (await client.post("/api/v1/resume-variants", json=doc)).json()
    artifact = (
        await client.post(f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1})
    ).json()
    assert "snapshot_mismatch" in {f["code"] for f in artifact["report"]["findings"]}
    doc["profile_revision"] = 99
    assert (await client.post("/api/v1/resume-variants", json=doc)).json()["error"][
        "code"
    ] == "invalid_variant"


async def test_compiler_failure_persisted_and_errors_private(
    client, resume_input, monkeypatch, caplog
):
    from career_agent.resume.renderer import CompileError, TypstRenderer

    def missing(*args):
        raise CompileError("compiler_unavailable")

    monkeypatch.setattr(TypstRenderer, "preflight", missing)
    variant = (await client.post("/api/v1/resume-variants", json=resume_input)).json()
    result = (
        await client.post(f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1})
    ).json()
    assert result["report"]["error_code"] == "compiler_unavailable"
    assert result["artifact_ref"] is None
    malicious = {**resume_input, "template": "/private/synthetic-person/resume.typ"}
    response = await client.post("/api/v1/resume-variants", json=malicious)
    assert response.status_code == 422
    assert "/private/synthetic-person" not in response.text + caplog.text
    assert (await client.get("/api/v1/artifacts/not-a-uuid/download")).status_code == 422


async def test_artifact_write_failure_and_download_tamper(client, resume_input, monkeypatch):
    from career_agent.resume.renderer import CompileError
    from career_agent.resume.store import ArtifactStore

    variant = (await client.post("/api/v1/resume-variants", json=resume_input)).json()

    def fail(*args):
        raise CompileError("artifact_write_failed")

    monkeypatch.setattr(ArtifactStore, "write", fail)
    result = (
        await client.post(f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1})
    ).json()
    assert result["report"]["render_status"] == "failed"
    assert result["report"]["error_code"] == "artifact_write_failed"
    assert result["artifact_ref"] is None


async def test_valid_requirement_and_other_revision_rejected(client, sessions, resume_input):
    job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "company_name": "Synthetic",
                "title": "Engineer",
                "jd_text": "Python",
                "requirements": [{"text": "Python"}],
            },
        )
    ).json()
    async with sessions() as session:
        revision = await session.scalar(
            select(e.JobRevision).where(e.JobRevision.job_id == UUID(job["id"]))
        )
        resume_input["job_revision_id"] = str(revision.id)
    resume_input["sections"][0]["items"][0]["requirement_refs"] = [job["requirements"][0]["id"]]
    variant = (await client.post("/api/v1/resume-variants", json=resume_input)).json()
    artifact = (
        await client.post(f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1})
    ).json()
    assert artifact["report"]["render_status"] == "accepted"
    await client.post(
        f"/api/v1/jobs/{job['id']}/revisions",
        json={"expected_revision": 1, "title": "New", "jd_text": "Different requirement"},
    )
    async with sessions() as session:
        revision = await session.scalar(
            select(e.JobRevision).where(
                e.JobRevision.job_id == UUID(job["id"]), e.JobRevision.revision == 2
            )
        )
        resume_input["job_revision_id"] = str(revision.id)
    variant = (await client.post("/api/v1/resume-variants", json=resume_input)).json()
    artifact = (
        await client.post(f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1})
    ).json()
    assert "invalid_requirement_reference" in {f["code"] for f in artifact["report"]["findings"]}


async def test_render_layout_failure_persisted(client, sessions, resume_input):
    fixture = json.loads(
        await asyncio.to_thread(Path("tests/fixtures/resumes/impossible_one_page.json").read_text)
    )
    source = fixture["facts"][0]
    async with sessions.begin() as session:
        session.add(
            e.PersonalFact(
                id=UUID(source["id"]),
                statement=source["statement"],
                category="synthetic",
                status=e.FactStatus.VERIFIED,
                verified_at=e.utcnow(),
            )
        )
        await session.flush()
        profile = e.PersonalProfile(
            revision=2,
            data={
                "display_name": fixture["name"],
                "projects": [
                    {"organization": "Example", "role": "Example", "fact_ids": [source["id"]]}
                ],
            },
        )
        session.add(profile)
        await session.flush()
        fixture["document"]["profile_id"] = str(profile.id)
        fixture["document"]["profile_revision"] = 2
    variant = (await client.post("/api/v1/resume-variants", json=fixture["document"])).json()
    artifact = (
        await client.post(f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1})
    ).json()
    assert artifact["report"]["error_code"] == "layout_failed"
    assert artifact["report"]["page_count"] > 1
    assert artifact["artifact_ref"] is None and artifact["file_hash"] is None
    assert (await client.get(f"/api/v1/artifacts/{artifact['id']}/download")).status_code == 409


async def test_artifact_removed_on_transaction_rollback(
    client, sessions, resume_input, monkeypatch, tmp_path
):
    from career_agent.application import resumes
    from career_agent.resume.store import ArtifactStore

    # Force an application exception AFTER file creation/flush, before commit.
    original = resumes.render_variant
    stores = []

    async def fail_after_write(session, row, settings):
        result = await original(session, row, settings)
        stores.append(ArtifactStore(settings.data_dir))
        assert result.artifact_ref is not None
        raise RuntimeError("/private/synthetic-error.txt")

    monkeypatch.setattr(resumes, "render_variant", fail_after_write)
    variant = (await client.post("/api/v1/resume-variants", json=resume_input)).json()
    response = await client.post(
        f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1}
    )
    assert response.status_code == 500 and "/private" not in response.text
    assert list(stores[0].root.glob("*.pdf")) == []
    async with sessions() as session:
        assert list(await session.scalars(select(e.RenderArtifact))) == []


async def test_download_rejects_corrupted_file(client, sessions, resume_input, monkeypatch):
    from career_agent.resume.store import ArtifactStore

    variant = (await client.post("/api/v1/resume-variants", json=resume_input)).json()
    artifact = (
        await client.post(f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1})
    ).json()
    assert artifact["report"]["render_status"] == "accepted"
    original = ArtifactStore.read

    def tamper_then_read(store, ref, digest):
        (store.root / f"{ref}.pdf").write_bytes(b"corrupt")
        return original(store, ref, digest)

    monkeypatch.setattr(ArtifactStore, "read", tamper_then_read)
    response = await client.get(f"/api/v1/artifacts/{artifact['id']}/download")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pdf_invalid"


@pytest.mark.parametrize("failure", ["read", "hash", "store_hash"])
async def test_post_validation_failure_persists_failed_report(
    client, sessions, resume_input, monkeypatch, failure, tmp_path
):
    from career_agent.resume import compiler

    variant = (await client.post("/api/v1/resume-variants", json=resume_input)).json()
    if failure == "read":
        original = Path.read_bytes

        def fail_pdf(path):
            if path.name == "resume.pdf":
                raise OSError("/private/synthetic-path")
            return original(path)

        monkeypatch.setattr(Path, "read_bytes", fail_pdf)
    else:
        original = compiler.hashlib.sha256
        calls = 0

        def fail_hash(content=b""):
            nonlocal calls
            if content.startswith(b"%PDF"):
                calls += 1
                if failure == "hash" or calls == 2:
                    raise ValueError("/private/synthetic-digest")
            return original(content)

        monkeypatch.setattr(compiler.hashlib, "sha256", fail_hash)
    response = await client.post(
        f"/api/v1/resume-variants/{variant['id']}/render", json={"revision": 1}
    )
    assert response.status_code == 201, response.text
    artifact = response.json()
    assert artifact["report"]["render_status"] == "failed"
    assert artifact["report"]["error_code"] == "artifact_write_failed"
    assert artifact["report"]["file_hash"] is None
    assert artifact["artifact_ref"] is None and artifact["file_hash"] is None
    url = f"/api/v1/artifacts/{artifact['id']}"
    assert (await client.get(url)).json() == artifact
    assert (await client.get(url + "/download")).status_code == 409
    assert "/private" not in response.text
    assert list((tmp_path / "artifacts").glob("*.pdf")) == []
    async with sessions() as session:
        row = await session.get(e.RenderArtifact, UUID(artifact["id"]))
        assert row.report["render_status"] == "failed"
