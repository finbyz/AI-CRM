# Copyright (c) 2026, finbyz and contributors
# For license information, please see license.txt
#
# Validation for the structured content an AI agent produces for a creative.
# Strict mode returns every problem so the agent can be asked to fix them;
# lenient mode trims and defaults so a render never fails on copy length.

import re

from ai_crm.social_media.creative.brand import DEFAULT_ICON, ICONS


class CreativeValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


SLIDE_LAYOUTS = {
    "cover": {
        "fields": {"eyebrow": 40, "title": 60, "title_emphasis": 40, "subtitle": 170},
        "required": ["title"],
    },
    "points": {
        "fields": {"eyebrow": 40, "title": 50, "title_emphasis": 36},
        "required": ["title"],
        "list": ("items", 2, 4, {"icon": None, "title": 42, "text": 130}),
    },
    "stats": {
        "fields": {"eyebrow": 40, "title": 50, "title_emphasis": 36, "caption": 150},
        "required": ["title"],
        "list": ("items", 2, 4, {"value": 7, "suffix": 3, "label": 40}),
    },
    "quote": {
        "fields": {"eyebrow": 40, "quote": 170, "quote_emphasis": 70, "attribution": 60},
        "required": ["quote"],
    },
    "steps": {
        "fields": {"eyebrow": 40, "title": 50, "title_emphasis": 36},
        "required": ["title"],
        "list": ("items", 2, 5, {"title": 34, "text": 100}),
    },
    "compare": {
        "fields": {"eyebrow": 40, "title": 50, "title_emphasis": 36, "left_label": 24, "right_label": 24},
        "required": ["title", "left_label", "right_label"],
        "list": ("rows", 2, 5, {"left": 60, "right": 60}),
    },
    "cta": {
        "fields": {"eyebrow": 40, "title": 50, "title_emphasis": 36, "text": 150, "button": 28},
        "required": ["title"],
    },
}

DEFAULT_TONE = {
    "cover": "dark",
    "points": "light",
    "stats": "dark",
    "quote": "dark",
    "steps": "light",
    "compare": "light",
    "cta": "dark",
}

MAX_SLIDES = 12

DOCUMENT_BLOCKS = {
    "cards": {"fields": {"label": 40}, "list": ("items", 2, 6, {"icon": None, "title": 40, "text": 150})},
    "stats": {"fields": {"label": 40}, "list": ("items", 2, 4, {"value": 7, "suffix": 3, "label": 40})},
    "steps": {"fields": {"label": 40}, "list": ("items", 2, 5, {"title": 34, "text": 110})},
    "band": {"fields": {"eyebrow": 40, "text": 90, "emphasis": 50}, "required": ["text"]},
    "callout": {"fields": {"text": 220}, "required": ["text"]},
}
DOCUMENT_FIELDS = {"eyebrow": 50, "title": 60, "title_emphasis": 40, "lede": 260}
MAX_DOCUMENT_BLOCKS = 5


def validate_slides(data, strict=True):
    """Validate {"slides": [...]} and return a normalised copy."""
    errors, warnings = [], []
    slides = (data or {}).get("slides") if isinstance(data, dict) else None
    if not isinstance(slides, list) or not slides:
        raise CreativeValidationError(['"slides" must be a non-empty list'])
    if len(slides) > MAX_SLIDES:
        _problem(errors, warnings, strict, f"at most {MAX_SLIDES} slides are allowed, got {len(slides)}")
        slides = slides[:MAX_SLIDES]

    out = []
    for i, slide in enumerate(slides, 1):
        where = f"slide {i}"
        if not isinstance(slide, dict):
            errors.append(f"{where}: must be an object")
            continue
        layout = slide.get("layout")
        spec = SLIDE_LAYOUTS.get(layout)
        if not spec:
            errors.append(f"{where}: unknown layout {layout!r}, use one of {', '.join(SLIDE_LAYOUTS)}")
            continue
        clean = _validate_block(slide, spec, where, strict, errors, warnings)
        clean["layout"] = layout
        tone = slide.get("tone")
        clean["tone"] = tone if tone in ("dark", "light") else DEFAULT_TONE[layout]
        clean["icon"] = _icon(slide.get("icon"), where, strict, errors, warnings, required=False)
        out.append(clean)

    if errors:
        raise CreativeValidationError(errors)
    return {"slides": out, "warnings": warnings}


def validate_document(data, strict=True):
    """Validate a one-page document: header fields plus up to five blocks."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        raise CreativeValidationError(["document must be an object"])

    clean = _validate_block(data, {"fields": DOCUMENT_FIELDS, "required": ["title"]}, "document", strict, errors, warnings)
    blocks = data.get("blocks") or []
    if not isinstance(blocks, list) or not blocks:
        errors.append('"blocks" must be a non-empty list')
        blocks = []
    if len(blocks) > MAX_DOCUMENT_BLOCKS:
        _problem(errors, warnings, strict, f"at most {MAX_DOCUMENT_BLOCKS} blocks are allowed, got {len(blocks)}")
        blocks = blocks[:MAX_DOCUMENT_BLOCKS]

    clean["blocks"] = []
    for i, block in enumerate(blocks, 1):
        where = f"block {i}"
        spec = DOCUMENT_BLOCKS.get(block.get("type")) if isinstance(block, dict) else None
        if not spec:
            errors.append(f"{where}: type must be one of {', '.join(DOCUMENT_BLOCKS)}")
            continue
        cb = _validate_block(block, spec, where, strict, errors, warnings)
        cb["type"] = block["type"]
        clean["blocks"].append(cb)

    if errors:
        raise CreativeValidationError(errors)
    clean["warnings"] = warnings
    return clean


def _validate_block(src, spec, where, strict, errors, warnings):
    clean = {}
    for field, limit in spec["fields"].items():
        clean[field] = _text(src.get(field), limit, f"{where}.{field}", strict, errors, warnings)
    for field in spec.get("required", []):
        if not clean.get(field):
            errors.append(f"{where}: {field} is required")

    if "list" in spec:
        key, low, high, item_spec = spec["list"]
        items = src.get(key)
        if not isinstance(items, list):
            errors.append(f"{where}: {key} must be a list of {low} to {high} entries")
            items = []
        elif not low <= len(items) <= high:
            _problem(errors, warnings, strict, f"{where}: {key} needs {low} to {high} entries, got {len(items)}")
            items = items[:high]
        clean[key] = []
        for j, item in enumerate(items, 1):
            item_where = f"{where}.{key}[{j}]"
            if not isinstance(item, dict):
                errors.append(f"{item_where}: must be an object")
                continue
            row = {}
            for field, limit in item_spec.items():
                if limit is None:
                    row[field] = _icon(item.get(field), item_where, strict, errors, warnings, required=True)
                else:
                    row[field] = _text(item.get(field), limit, f"{item_where}.{field}", strict, errors, warnings)
            clean[key].append(row)
    return clean


def _text(value, limit, where, strict, errors, warnings):
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        errors.append(f"{where}: must be text")
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    # House style: commas, not dashes, as connectors.
    text = re.sub(r"\s*—\s*|\s+–\s+|\s+-\s+", ", ", text)
    if len(text) > limit:
        _problem(errors, warnings, strict, f"{where}: {len(text)} characters, the limit is {limit}")
        text = text[: limit - 1].rstrip(" ,.;:") + "…"
    return text


def _icon(value, where, strict, errors, warnings, required):
    if value in ICONS:
        return value
    if value or required:
        _problem(errors, warnings, strict, f"{where}: icon {value!r} is not in the icon list")
    return DEFAULT_ICON


def _problem(errors, warnings, strict, message):
    (errors if strict else warnings).append(message)


def describe_slides_for_prompt(layouts=None):
    """Plain-text contract for slide content, given to the writing model."""
    lines = ["Slide layouts (character limits in brackets, optional fields may be omitted):"]
    for name, spec in SLIDE_LAYOUTS.items():
        if layouts and name not in layouts:
            continue
        lines.append(f"- {name}: " + _describe_spec(spec) + f"; required: {', '.join(spec.get('required', []))}")
    lines.append("Every slide may also set icon (the faint background motif) and tone (dark or light).")
    lines.append("Icons: " + ", ".join(ICONS))
    return "\n".join(lines)


def describe_document_for_prompt():
    """Plain-text contract for a one-page document."""
    lines = [
        "Document fields: " + ", ".join(f"{f}[{n}]" for f, n in DOCUMENT_FIELDS.items()) + "; required: title",
        f"blocks: 2 to {MAX_DOCUMENT_BLOCKS} entries, each with a type:",
    ]
    for name, spec in DOCUMENT_BLOCKS.items():
        lines.append(f"- {name}: " + _describe_spec(spec))
    lines.append("Icons: " + ", ".join(ICONS))
    return "\n".join(lines)


def _describe_spec(spec):
    text = ", ".join(f"{f}[{n}]" for f, n in spec["fields"].items())
    if "list" in spec:
        key, low, high, item = spec["list"]
        item_fields = ", ".join(f if n is None else f"{f}[{n}]" for f, n in item.items())
        text += f"; {key}: {low} to {high} x {{{item_fields}}}"
    return text
