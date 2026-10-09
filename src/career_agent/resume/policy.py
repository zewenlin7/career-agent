import hashlib
import json
from typing import Any

from career_agent.resume.schemas import Decision, ResumeDocument, Selection


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


def compress(selection: Selection) -> Selection | None:
    """Short forms once, then one optional item per round. Never drop required items."""
    result = selection.model_copy(deep=True)
    short_items = sorted(
        [i for s in result.sections for i in s.items if i.short_text],
        key=lambda i: (i.priority, i.ordering, str(i.item_id)),
    )
    if short_items:
        for item in short_items:
            assert item.short_text is not None
            item.text, item.short_text = item.short_text, None
            result.decisions.append(Decision(action="short_text", target_id=item.item_id))
        return result
    optional = sorted(
        [(s, i) for s in result.sections for i in s.items if not i.required],
        key=lambda pair: (
            pair[1].kind != "bullet",
            pair[1].priority,
            pair[0].priority,
            pair[0].ordering,
            pair[1].ordering,
            str(pair[1].item_id),
        ),
    )
    if not optional:
        return None
    section, item = optional[0]
    section.items.remove(item)
    result.decisions.append(Decision(action="remove_item", target_id=item.item_id))
    if not section.items and not section.required:
        result.sections.remove(section)
        result.decisions.append(Decision(action="remove_section", target_id=section.section_id))
    return result
