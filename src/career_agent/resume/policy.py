import hashlib
import json
from typing import Any

from career_agent.resume.schemas import ResumeDocument, Selection


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def selection_hash(selection: Selection) -> str:
    return hashlib.sha256(canonical_json(selection.model_dump(mode="json"))).hexdigest()


def initial_selection(document: ResumeDocument) -> Selection:
    sections = sorted(
        document.model_copy(deep=True).sections, key=lambda s: (s.ordering, str(s.section_id))
    )
    for section in sections:
        section.items.sort(key=lambda i: (i.ordering, str(i.item_id)))
    return Selection(sections=sections)
