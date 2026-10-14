import re

import frappe
import requests
from frappe import _
from frappe.utils import now_datetime

from ai_crm.social_media.doctype.youtube_settings.youtube_settings import is_own_channel

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
WEB_RESULTS = 8
TRANSCRIPT_LIMIT = 12000

# Used when the Research Agent has no human message of its own.
DEFAULT_BRIEF = """Topic: {title}
Target audience: {target_audience}
Source: {source_type}
Channel: {channel_name}

Transcript:
{transcript}"""


def start_research_for_video(row_name):
    """Create (or reuse) the Content Hub for a relevant video row and queue its research."""
    video = frappe.get_doc("YouTube Video", row_name)
    if video.parenttype != "YouTube Videos":
        frappe.throw(_("Invalid video row"))
    frappe.get_doc("YouTube Videos", video.parent).check_permission("read")

    if video.content_hub and frappe.db.exists("Content Hub", video.content_hub):
        hub = frappe.get_doc("Content Hub", video.content_hub)
    else:
        hub = frappe.get_doc({
            "doctype": "Content Hub",
            "title": video.title,
            "source_type": "YouTube Video",
            "channel_name": video.channel_name or "",
            "source_url": video.video_link,
        })
        hub.insert()
        frappe.db.set_value("YouTube Video", video.name, "content_hub", hub.name)

    if hub.research_status not in ("Completed", "Queued", "Researching"):
        queue_research(hub)
    return {"content_hub": hub.name, "research_status": hub.research_status}


def queue_research(hub):
    hub.check_permission("write")
    if hub.research_status in ("Queued", "Researching"):
        frappe.throw(_("Research is already running for {0}").format(hub.name))
    if not frappe.db.get_single_value("Content Hub Setting", "research_agent"):
        frappe.throw(_("Set a Research Agent in Content Hub Setting first"))

    hub.db_set({"research_status": "Queued", "research_error": None})
    frappe.enqueue(
        run_research,
        queue="long",
        timeout=900,
        enqueue_after_commit=True,
        job_id=f"content-hub-research:{hub.name}",
        deduplicate=True,
        hub_name=hub.name,
        user=frappe.session.user,
    )


def run_research(hub_name, user=None):
    hub = frappe.get_doc("Content Hub", hub_name)
    hub.db_set("research_status", "Researching")
    frappe.db.commit()
    link = frappe.utils.get_link_to_form("Content Hub", hub_name, frappe.utils.escape_html(hub.title))
    try:
        # db_set, so a user editing the hub meanwhile does not hit a save conflict.
        hub.db_set({
            "research": _research(hub),
            "research_status": "Completed",
            "research_error": None,
            "researched_on": now_datetime(),
        })
        message = _("Research is ready for {0}. Click Generate to create posts.").format(link)
        indicator = "green"
    except Exception as error:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"Content Hub research failed: {hub_name}")
        frappe.db.set_value(
            "Content Hub", hub_name, {"research_status": "Failed", "research_error": str(error)[:500]}
        )
        message = _("Research failed for {0}: {1}").format(link, frappe.utils.escape_html(str(error)[:200]))
        indicator = "red"
    frappe.db.commit()

    if user:
        frappe.publish_realtime(
            "msgprint",
            {"message": message, "indicator": indicator, "title": _("Content Hub Research")},
            user=user,
        )


def _research(hub):
    agent = frappe.get_doc("AI Agent", frappe.db.get_single_value("Content Hub Setting", "research_agent"))
    llm = frappe.get_doc("LLM", agent.llm)
    if llm.provider != "OpenRouter":
        frappe.throw(_("The Research Agent must use an OpenRouter model, because web search runs through OpenRouter"))

    provider = frappe.get_doc("LLM Provider", llm.provider)
    api_base = (provider.api_base or OPENROUTER_API_BASE).rstrip("/")
    payload = {
        "model": llm.name.removeprefix("openrouter/"),
        "messages": _build_messages(agent, _get_brief_values(hub)),
        "plugins": [{"id": "web", "max_results": WEB_RESULTS}],
        "temperature": agent.temperature if agent.temperature is not None else 0.2,
    }
    if agent.max_tokens:
        payload["max_tokens"] = agent.max_tokens

    response = requests.post(
        f"{api_base}/chat/completions",
        headers={"Authorization": f"Bearer {provider.get_password('api_key')}"},
        json=payload,
        timeout=600,
    )
    if response.status_code != 200:
        frappe.throw(_("Research request failed ({0}): {1}").format(response.status_code, response.text[:300]))

    message = ((response.json().get("choices") or [{}])[0].get("message")) or {}
    notes = (message.get("content") or "").strip()
    if not notes:
        frappe.throw(_("The Research Agent returned no research"))
    return notes + _format_sources(message.get("annotations"))


def _get_brief_values(hub):
    values = {
        "title": hub.title,
        "target_audience": hub.target_audience or "Business owners, finance and operations leaders, and tech teams",
        "source_type": hub.source_type or "Manual Topic",
        "channel_name": hub.channel_name or "None",
        "video_ownership": "None",
        "transcript": "None",
    }
    if hub.source_type == "YouTube Video":
        video = frappe.db.get_value(
            "YouTube Video", {"content_hub": hub.name}, ["channel_id", "transcript"], as_dict=True
        ) or frappe._dict()
        transcript = (video.transcript or "").strip()
        values["transcript"] = transcript[:TRANSCRIPT_LIMIT] or "None"
        values["video_ownership"] = "Our own video" if is_own_channel(video.channel_id) else "Third-party video"
    return values


def _build_messages(agent, values):
    """Render the agent's own prompt (system and human messages) with the topic's values."""
    from langchain_core.prompts import ChatPromptTemplate

    rows = [(row.type, row.content) for row in agent.messages if row.content and row.content_type in (None, "", "text")]
    if not any(role == "human" for role, _content in rows):
        rows.append(("human", DEFAULT_BRIEF))
    prompt = ChatPromptTemplate.from_messages(rows)
    messages = prompt.format_messages(**{name: values.get(name, "None") for name in prompt.input_variables})
    roles = {"system": "system", "human": "user", "ai": "assistant"}
    return [{"role": roles[m.type], "content": m.content} for m in messages]


def _format_sources(annotations):
    sources = {}
    for item in annotations or []:
        citation = item.get("url_citation") if item.get("type") == "url_citation" else None
        if citation and citation.get("url"):
            title = re.sub(r"<[^>]*>|[\[\]]", "", citation.get("title") or "").strip()
            sources.setdefault(citation["url"], title or citation["url"])
    if not sources:
        return ""
    lines = [f"{i}. [{title}]({url})" for i, (url, title) in enumerate(sources.items(), 1)]
    return "\n\n## Sources\n" + "\n".join(lines)
