"""Pinned external font dependency. No binaries or operator paths in contracts."""

import hashlib
from pathlib import Path

FONT_FAMILY = "Noto Sans CJK SC"
FONT_RELEASE = "Sans2.004"
FONT_COMMIT = "523d033d6cb47f4a80c58a35753646f5c3608a78"
FONT_POLICY_VERSION = "noto-sans-cjk-sc-2.004-regular-bold-v1"
FONT_BASE_URL = f"https://raw.githubusercontent.com/notofonts/noto-cjk/{FONT_COMMIT}"
FONT_HASHES = {
    "NotoSansCJKsc-Regular.otf": "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
    "NotoSansCJKsc-Bold.otf": "b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a",
}
LICENSE_HASH = "6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2"
PDF_FONT_NAMES = frozenset({"NotoSansCJKsc-Regular", "NotoSansCJKsc-Bold"})


class FontDependencyError(Exception):
    """Safe code only; never propagate filesystem or network diagnostics."""


def verified_fonts(directory: Path) -> dict[str, bytes]:
    result = {}
    for filename, expected in FONT_HASHES.items():
        try:
            content = (directory / filename).read_bytes()
        except OSError:
            raise FontDependencyError("font_dependency_missing") from None
        if hashlib.sha256(content).hexdigest() != expected:
            raise FontDependencyError("font_hash_mismatch")
        result[filename] = content
    return result
