import hashlib
import os
from pathlib import Path
from uuid import UUID

from career_agent.resume.renderer import CompileError


class ArtifactStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "artifacts"

    def _path(self, ref: UUID) -> Path:
        if not isinstance(ref, UUID):
            raise CompileError("artifact_write_failed")
        if self.root.is_symlink():
            raise CompileError("artifact_write_failed")
        path = self.root / f"{ref}.pdf"
        if path.is_symlink() or path.resolve().parent != self.root.resolve():
            raise CompileError("artifact_write_failed")
        return path

    def write(self, ref: UUID, content: bytes) -> str:
        path = self._path(ref)
        try:
            digest = hashlib.sha256(content).hexdigest()
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        except (OSError, ValueError):
            raise CompileError("artifact_write_failed") from None
        return digest

    def read(self, ref: UUID, expected_hash: str) -> bytes:
        try:
            path = self._path(ref)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                content = stream.read(10_000_001)
            if len(content) > 10_000_000 or hashlib.sha256(content).hexdigest() != expected_hash:
                raise CompileError("pdf_invalid")
            return content
        except OSError:
            raise CompileError("pdf_invalid") from None

    def remove(self, ref: UUID) -> None:
        self._path(ref).unlink(missing_ok=True)
