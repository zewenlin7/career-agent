"""Install pinned font dependencies into an operator cache, never system font directories."""

import argparse
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from career_agent.config import Settings
from career_agent.resume.fonts import (
    FONT_BASE_URL,
    FONT_HASHES,
    LICENSE_HASH,
    FontDependencyError,
    verified_fonts,
)
from career_agent.resume.renderer import CompileError, TypstRenderer


def setup(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    resources = {
        name: (f"Sans/OTF/SimplifiedChinese/{name}", digest) for name, digest in FONT_HASHES.items()
    }
    resources["LICENSE"] = ("LICENSE", LICENSE_HASH)
    for filename, (relative, expected) in resources.items():
        target = directory / filename
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise FontDependencyError("font_hash_mismatch")
            continue
        with urlopen(f"{FONT_BASE_URL}/{relative}", timeout=240) as response:
            content = response.read(25_000_001)
        if len(content) > 25_000_000 or hashlib.sha256(content).hexdigest() != expected:
            raise FontDependencyError("font_hash_mismatch")
        # Atomic publish only after hash verification; no partially downloaded dependency.
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    verified_fonts(directory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Offline hash and CLI preflight only")
    args = parser.parse_args()
    settings = Settings()
    try:
        if not args.check:
            setup(settings.font_dir)
        with tempfile.TemporaryDirectory(prefix="career-font-check-") as temporary:
            version = TypstRenderer(settings.typst_bin, font_dir=settings.font_dir).preflight(
                Path(temporary)
            )
    except (OSError, URLError, FontDependencyError, CompileError):
        raise SystemExit("font_dependency_setup_failed") from None
    print(f"Font hashes verified; Typst {version}; controlled zh-CN fonts ready")


if __name__ == "__main__":
    main()
