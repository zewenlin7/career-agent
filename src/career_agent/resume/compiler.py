import hashlib
import tempfile
from pathlib import Path

from career_agent.resume.fonts import FONT_FAMILY, FONT_HASHES
from career_agent.resume.pdf import validate_pdf
from career_agent.resume.policy import compress, initial_selection, selection_hash
from career_agent.resume.renderer import CompileError, TypstRenderer
from career_agent.resume.schemas import (
    MAX_ROUNDS,
    Attempt,
    Finding,
    PDFValidation,
    RenderReport,
    RenderVersions,
    ResumeDocument,
)


def compile_resume(
    document: ResumeDocument,
    name: str,
    renderer: TypstRenderer,
) -> tuple[RenderReport, bytes | None]:
    versions = RenderVersions()
    report = RenderReport(render_status="failed", validation_status="not_run", versions=versions)
    selection = initial_selection(document)
    try:
        versions.template_sha256 = renderer.template_hash()
        with tempfile.TemporaryDirectory(prefix="career-render-") as temp:
            directory = Path(temp)
            versions.compiler_version = renderer.preflight(directory)
            versions.font_family = FONT_FAMILY
            versions.font_file_hashes = dict(FONT_HASHES)
            for number in range(1, MAX_ROUNDS + 1):
                try:
                    path = renderer.compile(selection, name, directory)
                except CompileError as exc:
                    report.attempts.append(
                        Attempt(
                            number=number,
                            selection_hash=selection_hash(selection),
                            selected_item_ids=[
                                i.item_id for s in selection.sections for i in s.items
                            ],
                            decisions=selection.decisions,
                            validation=PDFValidation(
                                status="failed", findings=[Finding(code=exc.code)]
                            ),
                        )
                    )
                    raise
                validation = validate_pdf(path, selection, name)
                report.attempts.append(
                    Attempt(
                        number=number,
                        selection_hash=selection_hash(selection),
                        selected_item_ids=[i.item_id for s in selection.sections for i in s.items],
                        decisions=selection.decisions,
                        validation=validation,
                    )
                )
                report.page_count = validation.page_count
                report.findings = validation.findings
                report.validation_status = validation.status
                if validation.status == "passed":
                    content = path.read_bytes()
                    report.file_hash = hashlib.sha256(content).hexdigest()
                    report.render_status = "accepted"
                    return report, content
                codes = {f.code for f in validation.findings}
                if codes != {"layout_overflow"}:
                    report.error_code = (
                        "pdf_invalid" if "pdf_invalid" in codes else "text_validation_failed"
                    )
                    return report, None
                next_selection = compress(selection)
                if next_selection is None:
                    break
                if number == MAX_ROUNDS - 1:
                    # The final round always tests the required-content floor.
                    while (smaller := compress(next_selection)) is not None:
                        next_selection = smaller
                selection = next_selection
            report.error_code = "layout_failed"
    except CompileError as exc:
        report.error_code = exc.code
        report.findings = [Finding(code=exc.code)]
    except (OSError, ValueError):
        report.error_code = "artifact_write_failed"
        report.findings = [Finding(code="artifact_write_failed")]
    report.render_status = "failed"
    report.file_hash = None
    return report, None
