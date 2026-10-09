"""Offline compiler examples. No database writes, model calls or private data reads."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from career_agent.config import Settings
from career_agent.domain.rules import FactStatus
from career_agent.resume.compiler import compile_resume
from career_agent.resume.grounding import FactEvidence, validate_grounding
from career_agent.resume.renderer import TypstRenderer
from career_agent.resume.schemas import FactSnapshot, InputSnapshot, ResumeDocument


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Settings().data_dir / "synthetic-examples"
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "resumes"
    for name in [
        "normal_one_page_zh_cn",
        "compressible_overflow_zh_cn",
        "impossible_one_page_zh_cn",
        "mixed_script_font_regression",
    ]:
        fixture = json.loads((fixtures / f"{name}.json").read_text())
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
        if validate_grounding(document, snapshot, set(facts), facts, set()):
            raise SystemExit("synthetic_grounding_failed")
        report, pdf = compile_resume(
            document,
            fixture["name"],
            TypstRenderer(Settings().typst_bin, font_dir=Settings().font_dir),
        )
        (args.output_dir / f"{name}.report.json").write_text(report.model_dump_json(indent=2))
        output = args.output_dir / f"{name}.pdf"
        output.unlink(missing_ok=True)  # A prior success must not mask a new failure.
        if pdf:
            output.write_bytes(pdf)
            output.chmod(0o600)
        print(
            f"{name}: {report.render_status}; pages={report.page_count}; "
            f"attempts={len(report.attempts)}; error={report.error_code}"
        )
        expected = "failed" if name == "impossible_one_page_zh_cn" else "accepted"
        if report.render_status != expected:
            raise SystemExit("synthetic_acceptance_failed")


if __name__ == "__main__":
    main()
