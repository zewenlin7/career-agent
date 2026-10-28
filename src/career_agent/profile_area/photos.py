import io
import warnings
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError

from career_agent.domain.rules import DomainError
from career_agent.resume.renderer import CompileError
from career_agent.resume.store import ArtifactStore


class PhotoStore(ArtifactStore):
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "profile-photos"

    def _path(self, ref: UUID) -> Path:
        # Same opaque-ID, no symlink, owner-only storage rules as PDF artifacts.
        path = super()._path(ref).with_suffix(".jpg")
        if path.is_symlink():
            raise CompileError("artifact_write_failed")
        return path


def normalize(content: bytes) -> tuple[bytes, int, int]:
    if not content or len(content) > 5_000_000:
        raise DomainError("photo_too_large", 422)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if (
                    image.format not in {"JPEG", "PNG", "WEBP"}
                    or image.width * image.height > 16_000_000
                ):
                    raise ValueError()
                image.load()
                clean = ImageOps.exif_transpose(image).convert("RGB")
                clean.thumbnail((1200, 1200))
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=90)  # no EXIF/GPS/comment payload
                return output.getvalue(), clean.width, clean.height
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise DomainError("invalid_photo", 422) from None
