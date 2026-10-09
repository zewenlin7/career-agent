import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from career_agent.config import Settings
from career_agent.resume.fonts import FONT_FAMILY, FontDependencyError, verified_fonts
from career_agent.resume.policy import canonical_json
from career_agent.resume.schemas import COMPILER_VERSION, HEADINGS, Selection

TEMPLATE = Path(__file__).parent / "templates" / "resume_zh_cn_a4_single_v1.typ"


class CompileError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def discover_typst(configured: str) -> str:
    resolved = shutil.which(configured)
    if resolved:
        return resolved
    if configured == "typst" and Path("/opt/homebrew/bin/typst").is_file():
        return "/opt/homebrew/bin/typst"
    raise CompileError("compiler_unavailable")


class TypstRenderer:
    def __init__(
        self, binary: str = "typst", timeout: float = 15, font_dir: Path | None = None
    ) -> None:
        self.font_dir = font_dir if font_dir is not None else Settings().font_dir
        self._fonts: dict[str, bytes] | None = None
        self.binary = binary
        self.timeout = timeout
        self._template_bytes: bytes | None = None

    def prepare_fonts(self, directory: Path) -> Path:
        # Freeze verified bytes for this render; later cache changes cannot alter a round.
        if self._fonts is None:
            try:
                self._fonts = verified_fonts(self.font_dir)
            except FontDependencyError as exc:
                raise CompileError(str(exc)) from None
        target = directory / "fonts"
        try:
            target.mkdir(exist_ok=True)
            for name, content in self._fonts.items():
                (target / name).write_bytes(content)
        except OSError:
            raise CompileError("artifact_write_failed") from None
        return target

    def template_bytes(self) -> bytes:
        if self._template_bytes is None:
            try:
                self._template_bytes = TEMPLATE.read_bytes()
            except OSError:
                raise CompileError("template_error") from None
        return self._template_bytes

    def template_hash(self) -> str:
        return hashlib.sha256(self.template_bytes()).hexdigest()

    def _run(self, arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                [discover_typst(self.binary), *arguments],
                cwd=cwd,
                capture_output=True,
                timeout=self.timeout,
                check=False,
                env={"PATH": os.defpath, "HOME": str(cwd)},
            )
        except subprocess.TimeoutExpired:
            raise CompileError("compile_timeout") from None
        except OSError:
            raise CompileError("compiler_unavailable") from None

    def preflight(self, directory: Path) -> str:
        result = self._run(["--version"], directory)
        match = re.fullmatch(rb"typst ([0-9]+\.[0-9]+\.[0-9]+)(?: [^\r\n]*)?\s*", result.stdout)
        if result.returncode or not match:
            raise CompileError("compiler_unavailable")
        version = match[1].decode()
        if version != COMPILER_VERSION:
            raise CompileError("template_error")
        font_path = self.prepare_fonts(directory)
        fonts = self._run(
            [
                "fonts",
                "--ignore-system-fonts",
                "--ignore-embedded-fonts",
                "--font-path",
                str(font_path),
            ],
            directory,
        )
        if fonts.returncode or FONT_FAMILY.encode() not in fonts.stdout.splitlines():
            raise CompileError("template_error")
        return version

    def compile(self, selection: Selection, name: str, directory: Path) -> Path:
        font_path = self.prepare_fonts(directory)
        try:
            (directory / "main.typ").write_bytes(self.template_bytes())
            data = {
                "name": name,
                "sections": [
                    {
                        "heading": HEADINGS[s.name],
                        "items": [{"kind": i.kind, "text": i.text} for i in s.items],
                    }
                    for s in selection.sections
                ],
            }
            (directory / "data.json").write_bytes(canonical_json(data))
        except OSError:
            raise CompileError("artifact_write_failed") from None
        output = directory / "resume.pdf"
        output.unlink(missing_ok=True)
        result = self._run(
            [
                "compile",
                "--root",
                str(directory),
                "--ignore-system-fonts",
                "--ignore-embedded-fonts",
                "--font-path",
                str(font_path),
                "--creation-timestamp",
                "0",
                "--jobs",
                "1",
                "main.typ",
                "resume.pdf",
            ],
            directory,
        )
        if result.returncode:
            # Never expose raw diagnostics; only stable categories are retained.
            code = "template_error" if b"error:" in result.stderr else "compile_failed"
            raise CompileError(code)
        if result.stderr or not output.is_file():
            # Includes missing glyph/font warnings; no silent fallback is accepted.
            raise CompileError("compile_failed")
        return output
