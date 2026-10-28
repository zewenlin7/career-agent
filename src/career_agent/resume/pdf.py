import unicodedata
from pathlib import Path

import pdfplumber

from career_agent.resume.fonts import PDF_FONT_NAMES
from career_agent.resume.renderer import item_view
from career_agent.resume.schemas import HEADINGS, Finding, PDFValidation, Selection


def normalized(text: str) -> str:
    # Noto CJK maps U+2022 to the U+00B7 glyph in PDF ToUnicode extraction.
    # Fold only these list markers; never remove or reorder factual text.
    return "".join(unicodedata.normalize("NFKC", text).replace("\u2022", "\u00b7").split())


def retained_text_present(extracted: str, expected: list[str]) -> bool:
    """Match ordered, disjoint ranges in ONE immutable normalized text.

    Normalization only folds compatibility characters and layout whitespace. Never
    delete matched text: that could join unrelated characters into a false match.
    """
    source = normalized(extracted)
    cursor = 0
    for text in expected:
        token = normalized(text)
        start = source.find(token, cursor)
        if not token or start < 0:
            return False
        cursor = start + len(token)
    return True


def validate_pdf(
    path: Path, selection: Selection, name: str, *, contacts: str = "", photo_required: bool = False
) -> PDFValidation:
    try:
        with pdfplumber.open(path) as pdf:
            pages = pdf.pages
            if not pages:
                return PDFValidation(status="failed", findings=[Finding(code="pdf_invalid")])
            findings: list[Finding] = []
            # Validate all pages and all retained text BEFORE considering compression.
            extracted = normalized("\n".join(p.extract_text() or "" for p in pages))
            if not extracted:
                findings.append(Finding(code="pdf_invalid"))
            expected = [name]
            if contacts:
                expected.extend(contacts.split(" · "))
            if photo_required and not any(page.images for page in pages):
                findings.append(Finding(code="pdf_invalid"))
            for section in selection.sections:
                expected.append(HEADINGS[section.name])
                for item in section.items:
                    view = item_view(item)
                    if view.get("structured"):
                        expected.extend(
                            str(view[key]) for key in ["title", "subtitle", "period"] if view[key]
                        )
                        body = view["body"]
                        assert isinstance(body, list)
                        expected.extend(str(line) for line in body)
                    else:
                        expected.append(item.text)
            if not retained_text_present(extracted, expected):
                findings.append(Finding(code="text_validation_failed"))
            for page in pages:
                if abs(page.width - 595.276) > 1 or abs(page.height - 841.89) > 1:
                    findings.append(Finding(code="pdf_invalid"))
                for char in page.chars:
                    if (
                        char["x0"] < 18 * 72 / 25.4 - 1
                        or char["x1"] > page.width - 18 * 72 / 25.4 + 1
                        or char["top"] < 16 * 72 / 25.4 - 2
                        or char["bottom"] > page.height - 16 * 72 / 25.4 + 2
                    ):
                        findings.append(Finding(code="layout_overflow"))
                        break
                    if (
                        float(char["size"]) < 10.4
                        or char["fontname"].split("+")[-1] not in PDF_FONT_NAMES
                        or "\ufffd" in char["text"]
                        or "(cid:" in char["text"]
                    ):
                        findings.append(Finding(code="text_validation_failed"))
                        break
            if len(pages) != 1:
                findings.append(Finding(code="layout_overflow"))
            unique = [Finding(code=code) for code in sorted({f.code for f in findings})]
            return PDFValidation(
                status="failed" if unique else "passed", page_count=len(pages), findings=unique
            )
    except Exception:
        # PDF parser diagnostics can contain paths/content; never forward them.
        return PDFValidation(status="failed", findings=[Finding(code="pdf_invalid")])
