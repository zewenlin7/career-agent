import logging
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from career_agent.api.app import create_app
from career_agent.security.logging import SafeCode, SafeEvent, redact, safe_log


def test_safe_logging_and_redaction(caplog, synthetic):
    logger = logging.getLogger("career_agent.test")
    with caplog.at_level(logging.WARNING):
        safe_log(logger, SafeEvent.REQUEST_FAILED, code=SafeCode.INTERNAL_ERROR, run_id=uuid4())
    for value in synthetic["pii"]:
        assert value not in caplog.text
        assert value not in redact(value)
    assert "secret-value" not in redact("api_key=secret-value")
    assert "[PATH]" in redact(r"C:\private\resume.txt")
    with pytest.raises(ValueError):
        safe_log(logger, synthetic["pii"][0], code=SafeCode.INTERNAL_ERROR)
    with pytest.raises(TypeError):
        safe_log(logger, SafeEvent.REQUEST_FAILED, code=SafeCode.INTERNAL_ERROR, prompt="private")


async def test_api_does_not_reflect_validation_or_provider_errors(caplog, synthetic):
    app = create_app()
    raw = "provider body " + " ".join(synthetic["pii"])

    @app.get("/synthetic-error")
    async def synthetic_error():
        raise RuntimeError(raw)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with caplog.at_level(logging.WARNING):
                response = await client.get("/synthetic-error")
            assert response.status_code == 500
            assert response.json() == {"error": {"code": "internal_error"}}
            # Invalid UUID fails before any DB operation.
            invalid = await client.get("/api/v1/jobs/" + synthetic["pii"][0])
            assert invalid.status_code == 422
            for value in synthetic["pii"]:
                assert value not in response.text + invalid.text + caplog.text


def test_gitignore_boundaries():
    private = [
        ".env",
        ".env.local",
        ".private/resume.txt",
        "artifacts/resume.pdf",
        "backups/database.dump",
        "pgdata/data",
        "db.sql",
        "debug.log",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(private),
        text=True,
        capture_output=True,
        check=True,
    )
    assert set(result.stdout.splitlines()) == set(private)
    public = [".env.example", "tests/fixtures/synthetic.json"]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"], input="\n".join(public), text=True, capture_output=True
    )
    assert result.stdout == ""


def test_business_layer_has_no_provider_names():
    for directory in ["application", "domain"]:
        for path in (Path("src/career_agent") / directory).glob("*.py"):
            assert "openai" not in path.read_text().lower()
            assert "anthropic" not in path.read_text().lower()
