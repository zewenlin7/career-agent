import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pdfplumber
import pytest

from career_agent.resume import renderer as renderer_module
from career_agent.resume.compiler import compile_resume
from career_agent.resume.fonts import FONT_FAMILY, FONT_HASHES, FONT_POLICY_VERSION, PDF_FONT_NAMES
from career_agent.resume.pdf import validate_pdf
from career_agent.resume.policy import initial_selection
from career_agent.resume.renderer import CompileError, TypstRenderer
from career_agent.resume.schemas import MAX_ROUNDS, Finding, PDFValidation, ResumeDocument

pytestmark = pytest.mark.typst


def fixture(name):
    f = json.loads(Path(f"tests/fixtures/resumes/{name}.json").read_text())
    return f, ResumeDocument.model_validate(f["document"])


@pytest.mark.parametrize(
    "name,expected,attempts",
    [
        ("normal_one_page_zh_cn", "accepted", 1),
        ("compressible_overflow_zh_cn", "accepted", 3),
        ("impossible_one_page_zh_cn", "failed", 1),
        ("mixed_script_font_regression", "accepted", 1),
    ],
)
def test_real_acceptance_and_repeatability(name, expected, attempts, tmp_path):
    f, doc = fixture(name)
    report, pdf = compile_resume(doc, f["name"], TypstRenderer())
    assert report.render_status == expected, report.model_dump_json()
    assert len(report.attempts) == attempts
    assert report.versions.compiler_version == "0.15.1"
    assert report.versions.locale == "zh-CN"
    assert report.versions.font_family == FONT_FAMILY
    assert report.versions.font_policy_version == FONT_POLICY_VERSION
    assert report.versions.font_file_hashes == FONT_HASHES
    assert report.versions.template_sha256
    again, _ = compile_resume(doc, f["name"], TypstRenderer())
    assert report.model_dump(exclude={"file_hash"}) == again.model_dump(exclude={"file_hash"})
    # Compare decisions, validation and versions; byte-identical PDF metadata is not required.
    required = {i.item_id for s in doc.sections for i in s.items if i.required}
    for attempt in report.attempts:
        assert required <= set(attempt.selected_item_ids)
    if pdf:
        path = tmp_path / "accepted.pdf"
        path.write_bytes(pdf)
        with pdfplumber.open(path) as parsed:
            assert len(parsed.pages) == 1
            text = parsed.pages[0].extract_text()
            assert f["name"] in text
            assert "(cid:" not in text and "\ufffd" not in text
            assert all(
                c["fontname"].split("+")[-1] in PDF_FONT_NAMES for c in parsed.pages[0].chars
            )
            assert "项目经历" in text and "Python" in text

        assert report.validation_status == "passed"
        import hashlib

        assert report.file_hash == hashlib.sha256(pdf).hexdigest()
    else:
        assert report.error_code == "layout_failed"
        assert report.page_count > 1
    if name == "compressible_overflow_zh_cn":
        assert report.attempts[0].validation.page_count > 1
        assert [d.action for d in report.attempts[-1].decisions] == ["short_text", "remove_item"]
        short, removed = report.attempts[-1].decisions
        assert short.target_id == next(
            i.item_id for s in doc.sections for i in s.items if i.short_text
        )
        assert removed.target_id not in report.attempts[-1].selected_item_ids
        assert removed.target_id not in required


def test_typst_text_is_not_executable(tmp_path):
    f, doc = fixture("normal_one_page")
    text = '#read("/private/synthetic-secret.txt") #panic("not executable")'
    doc.sections[0].items[0].text = text
    report, pdf = compile_resume(doc, f["name"], TypstRenderer())
    assert report.render_status == "accepted"
    path = tmp_path / "inert.pdf"
    path.write_bytes(pdf)
    with pdfplumber.open(path) as parsed:
        assert "#read(" in parsed.pages[0].extract_text()


def test_compiler_unavailable_timeout_and_template_errors(tmp_path, monkeypatch):
    f, doc = fixture("normal_one_page")
    report, pdf = compile_resume(doc, f["name"], TypstRenderer("/nonexistent/synthetic/typst"))
    assert report.error_code == "compiler_unavailable" and pdf is None
    bad = tmp_path / "broken.typ"
    bad.write_text("#let x = (")
    monkeypatch.setattr(renderer_module, "TEMPLATE", bad)
    report, _ = compile_resume(doc, f["name"], TypstRenderer())
    assert report.error_code == "template_error"
    assert len(report.attempts) == 1
    monkeypatch.undo()
    # Real CLI is launched; tiny timeout forces bounded subprocess termination.
    report, _ = compile_resume(doc, f["name"], TypstRenderer(timeout=0.000001))
    assert report.error_code == "compile_timeout"


def test_missing_glyph_is_not_silent():
    f, doc = fixture("normal_one_page")
    doc.sections[0].items[0].text = "Unsupported glyph \U0001fae8"
    report, pdf = compile_resume(doc, f["name"], TypstRenderer())
    assert report.render_status == "failed" and pdf is None


def test_pdf_corrupt_empty_and_missing_text(tmp_path):
    f, doc = fixture("normal_one_page")
    selection = initial_selection(doc)
    path = tmp_path / "corrupt.pdf"
    for content in [b"", b"not a PDF"]:
        path.write_bytes(content)
        assert validate_pdf(path, selection, f["name"]).findings[0].code == "pdf_invalid"
    renderer = TypstRenderer()
    renderer.compile(selection, f["name"], tmp_path)
    selection.sections[0].items[0].text = "This retained text was silently lost."
    result = validate_pdf(tmp_path / "resume.pdf", selection, f["name"])
    assert "text_validation_failed" in {f.code for f in result.findings}


def test_blank_pdf_and_out_of_bounds(tmp_path):
    # Test-only trusted sources are never accepted by the application API.
    for source, expected in [
        ('#set page(paper: "a4")\n#box(width: 1pt)', "pdf_invalid"),
        (
            '#set page(paper: "a4", margin: 0pt)\n#set text(font: "Libertinus Serif")\nOverflow',
            "layout_overflow",
        ),
    ]:
        (tmp_path / "test.typ").write_text(source)
        result = subprocess.run(
            [
                renderer_module.discover_typst("typst"),
                "compile",
                "--ignore-system-fonts",
                str(tmp_path / "test.typ"),
                str(tmp_path / "test.pdf"),
            ],
            capture_output=True,
            check=True,
        )
        assert result.returncode == 0
        f, doc = fixture("normal_one_page")
        report = validate_pdf(tmp_path / "test.pdf", initial_selection(doc), f["name"])
        assert expected in {x.code for x in report.findings}


def test_bounded_rounds(monkeypatch):
    from career_agent.resume import compiler

    f, doc = fixture("normal_one_page")
    for _ in range(20):
        item = doc.sections[0].items[0].model_copy(deep=True)
        item.item_id, item.required = uuid4(), False
        doc.sections[0].items.append(item)
    monkeypatch.setattr(
        compiler,
        "validate_pdf",
        lambda *args: PDFValidation(
            status="failed", page_count=2, findings=[Finding(code="layout_overflow")]
        ),
    )
    report, pdf = compile_resume(doc, f["name"], TypstRenderer())
    assert report.error_code == "layout_failed" and pdf is None
    assert len(report.attempts) == MAX_ROUNDS


def test_raw_diagnostics_are_not_exposed(monkeypatch, tmp_path):
    f, doc = fixture("normal_one_page")
    renderer = TypstRenderer()
    monkeypatch.setattr(
        renderer,
        "_run",
        lambda *args: subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout=b"",
            stderr=b"/private/person.txt synthetic@example.invalid",
        ),
    )
    with pytest.raises(CompileError) as error:
        renderer.compile(initial_selection(doc), f["name"], tmp_path)
    assert str(error.value) == "compile_failed"


def test_template_snapshot_and_font_preflight(tmp_path, monkeypatch):
    trusted = tmp_path / "trusted.typ"
    trusted.write_bytes(renderer_module.TEMPLATE.read_bytes())
    monkeypatch.setattr(renderer_module, "TEMPLATE", trusted)
    renderer = TypstRenderer()
    digest = renderer.template_hash()
    trusted.write_text('#panic("changed after snapshot")')
    f, doc = fixture("normal_one_page")
    report, pdf = compile_resume(doc, f["name"], renderer)
    assert report.render_status == "accepted" and pdf
    assert report.versions.template_sha256 == digest
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, b"typst 0.15.1\n", b""),
            subprocess.CompletedProcess([], 0, b"Other font\n", b""),
        ]
    )
    monkeypatch.setattr(renderer, "_run", lambda *args: next(responses))
    with pytest.raises(CompileError, match="template_error"):
        renderer.preflight(tmp_path)


def test_compile_timeout_after_preflight(tmp_path, monkeypatch):
    f, doc = fixture("normal_one_page")
    renderer = TypstRenderer(timeout=0.000001)
    monkeypatch.setattr(renderer, "preflight", lambda directory: "0.15.1")
    report, pdf = compile_resume(doc, f["name"], renderer)
    assert report.error_code == "compile_timeout" and pdf is None
    assert len(report.attempts) == 1


def test_final_round_keeps_only_required(monkeypatch):
    from career_agent.resume import compiler

    f, doc = fixture("normal_one_page")
    for n in range(20):
        item = doc.sections[0].items[0].model_copy(deep=True)
        item.item_id, item.required, item.priority = uuid4(), False, n
        doc.sections[0].items.append(item)
    actual = compiler.validate_pdf

    def require_floor(path, selected, name):
        if any(not i.required for s in selected.sections for i in s.items):
            return PDFValidation(
                status="failed", page_count=2, findings=[Finding(code="layout_overflow")]
            )
        return actual(path, selected, name)

    monkeypatch.setattr(compiler, "validate_pdf", require_floor)
    report, pdf = compile_resume(doc, f["name"], TypstRenderer())
    assert report.render_status == "accepted" and pdf
    assert len(report.attempts) == MAX_ROUNDS
    assert len(report.attempts[-1].decisions) == 20


@pytest.mark.parametrize("failure", ["read", "hash"])
def test_artifact_read_hash_failure_never_accepted(monkeypatch, failure):
    from career_agent.resume import compiler

    f, doc = fixture("normal_one_page_zh_cn")
    if failure == "read":
        original = Path.read_bytes

        def fail_pdf(path):
            if path.name == "resume.pdf":
                raise OSError("/private/synthetic-path")
            return original(path)

        monkeypatch.setattr(Path, "read_bytes", fail_pdf)
    else:
        original = compiler.hashlib.sha256

        def fail_hash(content=b""):
            if content.startswith(b"%PDF"):
                raise ValueError("synthetic digest failure")
            return original(content)

        monkeypatch.setattr(compiler.hashlib, "sha256", fail_hash)
    report, content = compile_resume(doc, f["name"], TypstRenderer())
    assert report.render_status == "failed"
    assert report.validation_status == "passed"  # PDF validation itself succeeded.
    assert report.error_code == "artifact_write_failed"
    assert report.file_hash is None and content is None
    assert "/private" not in report.model_dump_json()
