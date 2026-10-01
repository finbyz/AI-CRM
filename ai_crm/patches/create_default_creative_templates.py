import frappe

MODEL = "openrouter/anthropic/claude-sonnet-5.5"

SHARED = """Audience: business owners, CFOs and operations heads evaluating or running ERPNext.
FinByz Tech: ERPNext and Frappe implementation partner with genuine accounting depth and AI built into the core.
Voice: confident, practical and specific. Speak to one business problem and its fix; no hype, no buzzwords.
Prefer concrete ERPNext features, workflows and outcomes over generic claims.
Only use numbers, client names or quotes that appear in the brief or the post text."""

TEMPLATES = [
    {
        "template_name": "LinkedIn Carousel",
        "format": "Carousel",
        "size": "portrait",
        "min_slides": 6,
        "max_slides": 8,
        "instructions": SHARED + """

Structure: a cover with a sharp promise, one slide naming the problem (compare works well),
2 to 4 slides with the fix (points or steps), proof only if the brief gives real numbers,
and a cta slide inviting a free consultation.""",
    },
    {
        "template_name": "LinkedIn Single Image",
        "format": "Single Image",
        "size": "portrait",
        "instructions": SHARED + """

One strong message a reader gets in three seconds. Use stats only with real numbers from the brief,
otherwise a cover headline, a quote from the brief, or a short points list.""",
    },
    {
        "template_name": "One Pager PDF",
        "format": "One Pager",
        "size": "portrait",
        "instructions": SHARED + """

A one-page capability or solution brief: a clear headline, a lede of two sentences,
cards for what we do, steps for how it starts, and a band with the closing message.""",
    },
]


def execute():
    frappe.reload_doc("social_media", "doctype", "creative_template")
    model = _ensure_model()
    for values in TEMPLATES:
        if frappe.db.exists("Creative Template", values["template_name"]):
            continue
        frappe.get_doc({"doctype": "Creative Template", "enabled": 1, "llm": model, **values}).insert(
            ignore_permissions=True
        )


def _ensure_model():
    if frappe.db.exists("LLM", MODEL):
        return MODEL
    if not frappe.db.exists("LLM Provider", "OpenRouter"):
        return None
    frappe.get_doc({
        "doctype": "LLM",
        "__newname": MODEL,
        "provider": "OpenRouter",
        "title": "Claude Sonnet 5.5 (OpenRouter)",
        "enabled": 1,
        "size": "Large",
        "supports_vision": 1,
    }).insert(ignore_permissions=True)
    return MODEL
