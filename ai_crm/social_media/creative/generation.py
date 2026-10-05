# Copyright (c) 2026, finbyz and contributors
# For license information, please see license.txt
#
# Creative generation: the model writes structured text, the renderer draws it.
# Flow: brief -> LLM (JSON) -> strict validation (one self-correction retry)
#       -> render PNG/PDF -> attach to the post and any sibling drafts.

import json
import re
from pathlib import Path

import frappe
from frappe import _

from ai_crm.social_media.creative.renderer import render_document, render_slides
from ai_crm.social_media.creative.schema import (
    CreativeValidationError,
    describe_document_for_prompt,
    describe_slides_for_prompt,
    validate_document,
    validate_slides,
)

SAMPLES = Path(__file__).parent / "samples"
BUILTIN_EXAMPLES = {
    "Carousel": "carousel_month_end_close.json",
    "Single Image": "single_stat.json",
    "One Pager": "one_pager_ai_erp.json",
}
SINGLE_IMAGE_LAYOUTS = ("cover", "stats", "quote", "points", "compare")
MAX_ATTEMPTS = 2


# --------------------------------------------------------------------------- #
# Pure helpers (no database access)
# --------------------------------------------------------------------------- #
def build_messages(fmt, brief, title="", post_text="", instructions="", brand_voice="",
                   example=None, min_slides=5, max_slides=8, skill=""):
    """Return (system, user) prompts for the writing model."""
    if fmt == "One Pager":
        shape = '{"eyebrow": ..., "title": ..., "title_emphasis": ..., "lede": ..., "blocks": [...]}'
        contract = describe_document_for_prompt()
        format_rules = "Write a single A4 one-page document with 3 to 5 blocks. Mix block types."
    elif fmt == "Single Image":
        shape = '{"slides": [ { "layout": ..., ... } ]}'
        contract = describe_slides_for_prompt(SINGLE_IMAGE_LAYOUTS)
        format_rules = "Write exactly ONE slide. It is a standalone image, so it must make sense on its own."
    else:
        shape = '{"slides": [ { "layout": ..., ... }, ... ]}'
        contract = describe_slides_for_prompt()
        format_rules = (
            f"Write a carousel of {min_slides} to {max_slides} slides. The first slide must use the cover "
            "layout and the last the cta layout. Vary the layouts in between, one idea per slide, and make "
            "every slide pull the reader to the next."
        )

    system = f"""You write the words for FinByz Tech social media creatives. The visual design is fixed \
by our brand templates; you only choose layouts and write the text.

Return ONLY one JSON object shaped like {shape}. No markdown fences, no commentary.

{format_rules}

{contract}

Writing rules:
- title and title_emphasis form one headline; title_emphasis is the closing clause and is set in an \
italic accent colour, e.g. title "Close your books in", title_emphasis "3 days, not 3 weeks."
- Stay within every character limit. Fewer words is better: less to read, more to see.
- Use commas as connectors, never em-dashes.
- Never invent statistics, percentages, client names or quotes. Use a number or quote only if it \
appears in the brief or the post text; otherwise prefer points, steps or compare layouts.
- icon values must come from the icon list."""

    if skill:
        system += (
            "\n\nFinByz creative skill. Layout, colours, fonts and logo are already implemented by the "
            "templates; apply its tone, messaging and writing rules to your text:\n" + skill.strip()
        )
    if brand_voice:
        system += f"\n\nBrand voice:\n{brand_voice.strip()}"
    if instructions:
        system += f"\n\nTemplate instructions (follow these closely):\n{instructions.strip()}"
    if example:
        system += (
            "\n\nExample of the expected structure. Its facts and numbers are fictional; "
            f"never reuse them:\n{json.dumps(example, ensure_ascii=False)}"
        )

    user = f"Brief:\n{(brief or '').strip() or 'Create a creative for the post below.'}"
    if title:
        user += f"\n\nPost title: {title}"
    if post_text:
        user += f"\n\nPost text this creative accompanies:\n{post_text.strip()[:4000]}"
    return system, user


def parse_json_response(text):
    """Pull the JSON object out of a model reply."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise CreativeValidationError(["the reply did not contain a JSON object"])
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise CreativeValidationError([f"the reply was not valid JSON ({error.msg} at line {error.lineno})"])


def check_content(fmt, data, strict, min_slides=5, max_slides=8):
    """Validate against the schema plus the template's format rules."""
    if fmt == "One Pager":
        return validate_document(data, strict=strict)

    clean = validate_slides(data, strict=strict)
    slides = clean["slides"]
    problems = []
    if fmt == "Single Image":
        if len(slides) != 1:
            problems.append(f"write exactly 1 slide, got {len(slides)}")
            clean["slides"] = slides[:1]
        elif slides[0]["layout"] not in SINGLE_IMAGE_LAYOUTS:
            problems.append(f"a single image must use one of: {', '.join(SINGLE_IMAGE_LAYOUTS)}")
    else:
        if not min_slides <= len(slides) <= max_slides:
            problems.append(f"write {min_slides} to {max_slides} slides, got {len(slides)}")
        if slides[0]["layout"] != "cover":
            problems.append("the first slide must use the cover layout")
        if slides[-1]["layout"] != "cta":
            problems.append("the last slide must use the cta layout")
    if problems and strict:
        raise CreativeValidationError(problems)
    clean["warnings"].extend(problems)
    return clean


def write_content(invoke, fmt, system, user, min_slides=5, max_slides=8):
    """Ask the model, and once more with the problems listed if the first reply is off.

    `invoke(messages)` takes [(role, text), ...] and returns the reply text.
    Returns (content, warnings).
    """
    messages = [("system", system), ("user", user)]
    reply = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        reply = invoke(messages)
        try:
            data = parse_json_response(reply)
            clean = check_content(fmt, data, True, min_slides, max_slides)
            return clean, clean.pop("warnings", [])
        except CreativeValidationError as error:
            if attempt == MAX_ATTEMPTS:
                break
            messages += [
                ("assistant", reply),
                ("user", "Fix these problems and return the complete JSON object again, nothing else:\n- "
                 + "\n- ".join(error.errors)),
            ]

    # Last resort: trim to fit rather than fail the whole job.
    clean = check_content(fmt, parse_json_response(reply), False, min_slides, max_slides)
    return clean, clean.pop("warnings", [])


def render_content(fmt, content, size, theme="Mixed"):
    if fmt == "One Pager":
        return render_document(content)
    return render_slides(content, size=size or "portrait", theme=theme or "Mixed")


# --------------------------------------------------------------------------- #
# Frappe glue
# --------------------------------------------------------------------------- #
def queue_creative(post, template, brief, llm=None, share_with_siblings=True):
    template_doc = frappe.get_doc("Creative Template", template)
    if not template_doc.enabled:
        frappe.throw(_("Creative Template {0} is disabled").format(template))
    if not (llm or template_doc.llm):
        frappe.throw(_("Select a model, or set a Default Model on the Creative Template"))

    post.creative_template = template
    post.creative_prompt = brief
    post.creative_llm = llm or template_doc.llm
    post.creative_status = "Queued"
    post.creative_error = None
    post.save()

    frappe.enqueue(
        run_creative_job,
        queue="long",
        timeout=900,
        enqueue_after_commit=True,
        job_id=f"creative:{post.name}",
        deduplicate=True,
        post_name=post.name,
        share_with_siblings=bool(share_with_siblings),
    )
    return {"status": "queued"}


def run_creative_job(post_name, share_with_siblings=True):
    post = frappe.get_doc("Social Media Post", post_name)
    try:
        post.db_set("creative_status", "Generating", update_modified=False)
        _notify(post)
        template = frappe.get_doc("Creative Template", post.creative_template)
        settings = frappe.get_single("Content Hub Setting")
        min_slides, max_slides = template.min_slides or 5, template.max_slides or 8

        system, user = build_messages(
            template.format,
            post.creative_prompt,
            title=post.title,
            post_text=post.content,
            instructions=template.instructions,
            brand_voice=settings.brand_voice,
            example=_example(template),
            min_slides=min_slides,
            max_slides=max_slides,
            skill=settings.get("creative_skill"),
        )
        chat = frappe.get_doc("LLM", post.creative_llm).llm
        content, warnings = write_content(
            lambda messages: _reply_text(chat.invoke(messages)),
            template.format, system, user, min_slides, max_slides,
        )
        result = render_content(template.format, content, template.size, template.get("theme"))
        _apply_render(post, template.format, content, result, warnings + result.warnings)

        if share_with_siblings:
            for sibling in _sibling_drafts(post):
                copy_creative(post, sibling)
    except Exception as error:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"Creative generation failed: {post_name}")
        post = frappe.get_doc("Social Media Post", post_name)
        post.db_set({"creative_status": "Failed", "creative_error": str(error)[-2000:]}, update_modified=False)
    _notify(post)


def rerender_creative(post):
    """Render again from the slide JSON the user edited; no model call."""
    template = frappe.get_doc("Creative Template", post.creative_template)
    rows = sorted(post.slides, key=lambda row: row.slide_no or 0)
    if not rows:
        frappe.throw(_("There are no slides to render"))
    try:
        if template.format == "One Pager":
            content = frappe.parse_json(rows[0].slide_json)
        else:
            content = {"slides": [frappe.parse_json(row.slide_json) for row in rows]}
    except Exception:
        frappe.throw(_("Slide content must be valid JSON"))

    try:
        content = check_content(template.format, content, False, template.min_slides or 1, template.max_slides or 12)
    except CreativeValidationError as error:
        frappe.throw("<br>".join(frappe.utils.escape_html(e) for e in error.errors), title=_("Invalid slide content"))
    warnings = content.pop("warnings", [])
    result = render_content(template.format, content, template.size, template.get("theme"))
    _apply_render(post, template.format, content, result, warnings + result.warnings)


def _apply_render(post, fmt, content, result, warnings):
    old_files = _creative_file_names(post)
    stem = frappe.scrub(post.name)

    images = [_save_file(post, f"{stem}-{i:02d}.png", png) for i, png in enumerate(result.images, 1)]
    pdf_url = _save_file(post, f"{stem}.pdf", result.pdf)

    post.reload()
    post.set("slides", [])
    parts = [content] if fmt == "One Pager" else content["slides"]
    for i, (part, image) in enumerate(zip(parts, images), 1):
        post.append("slides", {
            "slide_no": i,
            "layout": part.get("layout") or "document",
            "image": image,
            "slide_json": json.dumps(part, indent=1, ensure_ascii=False),
        })
    post.creative_pdf = pdf_url
    # LinkedIn posts carousels and one-pagers as the PDF; other platforms use this first image.
    post.image_attachment = images[0] if images else None
    post.creative_status = "Ready"
    post.creative_error = None
    post.creative_warnings = "\n".join(warnings) or None
    post.save()

    in_use = {row.image for row in post.slides} | {post.creative_pdf}
    for name in old_files:
        if frappe.db.get_value("File", name, "file_url") not in in_use:
            frappe.delete_doc("File", name, ignore_permissions=True)


def copy_creative(source, target, save=True):
    target.creative_template = source.creative_template
    target.creative_llm = source.creative_llm
    target.creative_prompt = source.creative_prompt
    target.creative_status = "Ready"
    target.creative_error = None
    target.creative_warnings = source.creative_warnings
    target.creative_pdf = _share_file(source.creative_pdf, target)
    target.set("slides", [])
    for row in source.slides:
        target.append("slides", {
            "slide_no": row.slide_no,
            "layout": row.layout,
            "slide_json": row.slide_json,
            "image": _share_file(row.image, target),
        })
    target.image_attachment = target.slides[0].image if target.slides else None
    if save:
        target.save()


def _sibling_drafts(post):
    names = [name for name in post.get_group_names() if name != post.name]
    docs = [frappe.get_doc("Social Media Post", name) for name in names]
    return [doc for doc in docs if doc.status == "Draft"]


def _save_file(post, file_name, content):
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "attached_to_doctype": post.doctype,
        "attached_to_name": post.name,
        "is_private": 1,
        "content": content,
    })
    file_doc.save(ignore_permissions=True)
    return file_doc.file_url


def _share_file(file_url, target):
    """Attach an existing file to another post without copying it on disk."""
    if not file_url:
        return None
    # Only share creatives of posts the user can already read, never an arbitrary private file.
    sources = frappe.get_all(
        "File",
        filters={"file_url": file_url, "attached_to_doctype": target.doctype},
        pluck="attached_to_name",
    )
    if not any(frappe.has_permission(target.doctype, "read", doc=name) for name in sources):
        frappe.throw(_("You do not have access to {0}").format(file_url), frappe.PermissionError)
    if not frappe.db.exists("File", {"file_url": file_url, "attached_to_name": target.name}):
        frappe.get_doc({
            "doctype": "File",
            "file_url": file_url,
            "file_name": file_url.rsplit("/", 1)[-1],
            "attached_to_doctype": target.doctype,
            "attached_to_name": target.name,
            "is_private": 1,
        }).insert(ignore_permissions=True)
    return file_url


def _creative_file_names(post):
    urls = {row.image for row in post.slides if row.image} | ({post.creative_pdf} if post.creative_pdf else set())
    if not urls:
        return []
    return frappe.get_all(
        "File",
        filters={"attached_to_doctype": post.doctype, "attached_to_name": post.name, "file_url": ("in", list(urls))},
        pluck="name",
    )


def _example(template):
    if template.example_json:
        return frappe.parse_json(template.example_json)
    return json.loads((SAMPLES / BUILTIN_EXAMPLES[template.format]).read_text())


def _reply_text(reply):
    content = getattr(reply, "content", reply)
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def _notify(post):
    frappe.publish_realtime(
        "ai_crm_creative_update",
        {"name": post.name, "status": post.creative_status},
        doctype=post.doctype,
        docname=post.name,
        after_commit=True,
    )
