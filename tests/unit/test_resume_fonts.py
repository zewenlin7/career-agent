import io
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from career_agent.resume.fonts import FONT_HASHES, FontDependencyError, verified_fonts
from career_agent.resume.renderer import CompileError, TypstRenderer
from career_agent.resume.schemas import ResumeDocument


def test_missing_and_corrupt_dependency_fail_closed(tmp_path):
    with pytest.raises(FontDependencyError, match="font_dependency_missing"):
        verified_fonts(tmp_path)
    (tmp_path / next(iter(FONT_HASHES))).write_bytes(b"corrupt font")
    with pytest.raises(FontDependencyError, match="font_hash_mismatch"):
        verified_fonts(tmp_path)
    renderer = TypstRenderer(font_dir=tmp_path)
    with pytest.raises(CompileError, match="font_hash_mismatch"):
        renderer.prepare_fonts(tmp_path)


def test_font_setup_rejects_bad_download_without_publishing(tmp_path):
    module = runpy.run_path("scripts/setup_resume_fonts.py")
    with patch("urllib.request.urlopen", return_value=io.BytesIO(b"not an official font")):
        # run_path imported urlopen before patch; replace that function's globals directly.
        module["setup"].__globals__["urlopen"] = lambda *a, **kw: io.BytesIO(b"bad font")
        with pytest.raises(FontDependencyError, match="font_hash_mismatch"):
            module["setup"](tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("field,value", [("font_path", "/private/font"), ("locale", "en-US")])
def test_font_path_and_other_locale_not_client_controls(field, value):
    import json

    doc = json.loads(Path("tests/fixtures/resumes/normal_one_page_zh_cn.json").read_text())[
        "document"
    ]
    doc[field] = value
    with pytest.raises(ValidationError):
        ResumeDocument.model_validate(doc)
