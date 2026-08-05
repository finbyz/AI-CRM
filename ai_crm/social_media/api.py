# Copyright (c) 2026, finbyz and contributors
# For license information, please see license.txt
#
# Backend API for the "Postato" single-page Social Command Center.
# This module ONLY orchestrates the existing whitelisted pipeline methods on
# `Content Hub` and `Social Media Post` -- it does not duplicate any business
# logic. The data of record stays in the same DocTypes.

import re
import requests
import frappe
from frappe import _
from frappe.utils import now_datetime

from ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services.background_jobs import (
    enqueue_youtube_workflow,
)
from ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services.video_processor import (
    enqueue_video_processing,
)


# credential DocType -> Social Media Post / Content Hub platform label
PLATFORM_BY_CREDENTIAL = {
    "Twitter Integration": "X (Twitter)",
    "LinkedIn Integration": "LinkedIn",
    "Reddit Integration": "Reddit",
}

# per-integration field that holds a human-friendly account label
ACCOUNT_LABEL_FIELD = {
    "Twitter Integration": ["username", "full_name"],
    "LinkedIn Integration": ["full_name", "email"],
    "Reddit Integration": ["account_name", "username"],
}

POST_FIELDS = [
    "name", "title", "content", "platform", "status", "image_attachment",
    "post_on", "created_on", "post_link", "content_hub", "credential_type",
    "credential", "modified",
]


# --------------------------------------------------------------------------- #
# Read: everything the page needs in a single round-trip
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def get_dashboard_data():
    accounts = list_connected_accounts()
    posts = _recent_posts(limit=200)
    return {
        "accounts": accounts,
        "stats": _stats(accounts),
        "posts": posts,
        "hubs": _hubs_with_counts(limit=12),
        "queue": _queue(posts),
        "activity": _activity(posts),
        "youtube_videos": _recent_youtube_videos(limit=20),
    }

def _recent_youtube_videos(limit=20):
    return frappe.get_all(
        "YouTube Video",
        fields=["name", "title", "channel_id", "video_id", "published_on"],
        order_by="published_on desc",
        limit=limit,
    )


def _stats(accounts):
    from frappe.utils import get_first_day, nowdate
    connected = len([a for a in accounts if a.get("connected")])
    scheduled = frappe.db.count("Social Media Post", {"status": "Scheduled"})
    posted = frappe.db.count("Social Media Post", {"status": "Posted"})
    failed = frappe.db.count("Social Media Post", {"status": "Failed"})
    posted_month = frappe.db.count("Social Media Post", {
        "status": "Posted",
        "modified": [">=", get_first_day(nowdate())],
    })
    denom = posted + failed
    success = round((posted / denom) * 100) if denom else 100
    return {
        "connected": connected,
        "total": len(accounts),
        "scheduled": scheduled,
        "posted_month": posted_month,
        "success_rate": success,
    }


def _hubs_with_counts(limit=12):
    hubs = frappe.get_all(
        "Content Hub",
        fields=["name", "title", "target_audience", "platform", "modified"],
        order_by="modified desc",
        limit=limit,
    )
    if not hubs:
        return []
    counts = {}
    for r in frappe.get_all("Content Hub Idea", fields=["parent", "count(name) as c"],
                            group_by="parent"):
        counts[r.get("parent")] = r.get("c")
    for h in hubs:
        h["idea_count"] = counts.get(h["name"], 0)
    return hubs


def _queue(posts, limit=10):
    scheduled = [p for p in posts if p.get("status") == "Scheduled" and p.get("post_on")]
    scheduled.sort(key=lambda p: str(p.get("post_on")))
    return scheduled[:limit]


def _activity(posts, limit=6):
    acts = []
    for p in posts:
        st = p.get("status")
        if st == "Posted":
            acts.append({"icon": "published", "text": f"Post published to {p.get('platform')}",
                         "when": p.get("modified")})
        elif st == "Scheduled":
            acts.append({"icon": "scheduled", "text": f"Post scheduled for {p.get('platform')}",
                         "when": p.get("post_on") or p.get("modified")})
        elif p.get("image_attachment"):
            acts.append({"icon": "image", "text": f"Image generated for {p.get('platform')} post",
                         "when": p.get("modified")})
        else:
            acts.append({"icon": "draft", "text": f"Draft created for {p.get('platform')}",
                         "when": p.get("modified")})
        if len(acts) >= limit:
            break
    return acts


@frappe.whitelist()
def list_connected_accounts():
    accounts = []
    for doctype, platform in PLATFORM_BY_CREDENTIAL.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        label_fields = ACCOUNT_LABEL_FIELD.get(doctype, [])
        fields = ["name", "connection_status"] + [f for f in label_fields]
        try:
            rows = frappe.get_all(doctype, fields=fields, order_by="modified desc")
        except Exception:
            rows = frappe.get_all(doctype, fields=["name", "connection_status"])
        for row in rows:
            label = next((row.get(f) for f in label_fields if row.get(f)), None)
            accounts.append({
                "credential_type": doctype,
                "credential": row.get("name"),
                "platform": platform,
                "label": label or row.get("name"),
                "status": row.get("connection_status") or "Unknown",
                "connected": (row.get("connection_status") == "Connected"),
            })
    return accounts


def _recent_posts(limit=100):
    return frappe.get_all(
        "Social Media Post",
        fields=POST_FIELDS,
        order_by="modified desc",
        limit=limit,
    )


@frappe.whitelist()
def get_all_hub_ideas(limit=30):
    """Aggregate ideas across all Content Hubs for the Ideas Library browser."""
    hubs = frappe.get_all(
        "Content Hub",
        fields=["name", "title", "target_audience", "platform",
                "credential_type", "credential", "modified"],
        order_by="modified desc",
        limit=limit,
    )
    ideas_by_parent = {}
    for r in frappe.get_all("Content Hub Idea",
                            fields=["parent", "idea_title", "description"],
                            order_by="idx asc"):
        ideas_by_parent.setdefault(r.get("parent"), []).append(
            {"idea_title": r.get("idea_title"), "description": r.get("description")})
    for h in hubs:
        h["ideas"] = ideas_by_parent.get(h["name"], [])
    return {"hubs": hubs}


@frappe.whitelist()
def get_hub_ideas(hub):
    """Load an existing Content Hub's ideas back into the page."""
    doc = frappe.get_doc("Content Hub", hub)
    return {
        "hub": doc.name,
        "title": doc.title,
        "target_audience": doc.target_audience,
        "platform": doc.platform,
        "ideas": [
            {"idea_title": r.idea_title, "description": r.description}
            for r in doc.ideas_child_table
        ],
    }


@frappe.whitelist()
def get_post(post):
    """Return a single post as a plain dict for the composer."""
    doc = frappe.get_doc("Social Media Post", post)
    return {f: doc.get(f) for f in POST_FIELDS if hasattr(doc, f)}


# --------------------------------------------------------------------------- #
# Generate: ideas + posts (reuse Content Hub controller methods)
# --------------------------------------------------------------------------- #
def _ensure_hub(title, target_audience, platform, credential_type, credential, source_type="Manual Topic", youtube_video=None):
    """Find a matching Content Hub or create one. Content Hub is single-platform,
    so we keep one hub per (title, platform, credential)."""
    existing = frappe.get_all(
        "Content Hub",
        filters={"title": title, "platform": platform, "credential": credential},
        limit=1,
    )
    if existing:
        if source_type == "YouTube Video" and youtube_video:
            frappe.db.set_value("Content Hub", existing[0].name, {
                "source_type": source_type,
                "youtube_video": youtube_video
            })
        return existing[0].name

    doc = frappe.new_doc("Content Hub")
    doc.title = title
    doc.target_audience = target_audience or ""
    doc.platform = platform
    doc.credential_type = credential_type
    doc.credential = credential
    doc.source_type = source_type
    if source_type == "YouTube Video":
        doc.youtube_video = youtube_video
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def generate_ideas(title, target_audience, credential_type, credential, source_type="Manual Topic", youtube_video=None):
    """Create/reuse a Content Hub and run the existing idea generator."""
    if not title:
        frappe.throw(_("A topic/title is required to generate ideas"))

    platform = PLATFORM_BY_CREDENTIAL.get(credential_type)
    if not platform:
        frappe.throw(_("Unknown credential type: {0}").format(credential_type))

    hub = _ensure_hub(title, target_audience, platform, credential_type, credential, source_type, youtube_video)
    hub_doc = frappe.get_doc("Content Hub", hub)

    # regenerate cleanly instead of appending on top of old ideas
    hub_doc.set("ideas_child_table", [])
    hub_doc.save(ignore_permissions=True)

    hub_doc.generate_linkedin_ideas()  # existing whitelisted controller method
    hub_doc.reload()

    ideas = [
        {"idea_title": r.idea_title, "description": r.description}
        for r in hub_doc.ideas_child_table
    ]
    return {"hub": hub, "platform": platform, "ideas": ideas}


@frappe.whitelist()
def create_posts_for_idea(idea_title, idea_description, targets, title,
                          target_audience=None, generate_image_flag=False, image_prompt=None):
    """Fan one idea out into a Draft Social Media Post per selected account.
    Reuses Content Hub.generate_post_from_idea -- no duplicated AI logic."""
    targets = frappe.parse_json(targets) if isinstance(targets, str) else targets
    if isinstance(generate_image_flag, str):
        generate_image_flag = frappe.parse_json(generate_image_flag)

    if not targets:
        frappe.throw(_("Select at least one account to create posts for"))

    created, errors = [], []
    for t in targets:
        credential_type = t.get("credential_type")
        credential = t.get("credential")
        platform = t.get("platform") or PLATFORM_BY_CREDENTIAL.get(credential_type)
        try:
            hub = _ensure_hub(title, target_audience, platform,
                              credential_type, credential)
            hub_doc = frappe.get_doc("Content Hub", hub)
            res = hub_doc.generate_post_from_idea(idea_title, idea_description)
            post_name = res.get("post_name")

            if generate_image_flag:
                try:
                    frappe.get_doc("Social Media Post", post_name).generate_image(image_prompt or "")
                except Exception as img_e:
                    frappe.log_error(f"Image Gen Error: {str(img_e)}", "Postato create_posts_for_idea")

            created.append(get_post(post_name))
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Postato create_posts_for_idea")
            errors.append({"platform": platform, "error": str(e)})

    return {"posts": created, "errors": errors}


# --------------------------------------------------------------------------- #
# Compose actions: thin wrappers so the page has ONE clean API surface
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def save_post_content(post, content, title=None):
    doc = frappe.get_doc("Social Media Post", post)
    doc.content = content
    if title is not None:
        doc.title = title
    doc.save(ignore_permissions=True)
    return {"status": "success"}


@frappe.whitelist()
def revise_post(post, instruction):
    doc = frappe.get_doc("Social Media Post", post)
    return doc.revise_post(instruction)


@frappe.whitelist()
def generate_image(post, instruction=""):
    doc = frappe.get_doc("Social Media Post", post)
    return doc.generate_image(instruction)


@frappe.whitelist()
def schedule_post(post, post_on):
    doc = frappe.get_doc("Social Media Post", post)
    doc.post_on = post_on
    doc.status = "Scheduled"
    doc.save(ignore_permissions=True)
    return {"status": "success", "post_on": doc.post_on}


@frappe.whitelist()
def publish_post(post):
    """Publish now via the existing per-platform posting pipeline."""
    doc = frappe.get_doc("Social Media Post", post)
    return doc.post()


@frappe.whitelist()
def unschedule_post(post):
    doc = frappe.get_doc("Social Media Post", post)
    doc.post_on = None
    doc.status = "Draft"
    doc.save(ignore_permissions=True)
    return {"status": "success"}


@frappe.whitelist()
def delete_post(post):
    frappe.delete_doc("Social Media Post", post, ignore_permissions=True)
    return {"status": "success"}


# --------------------------------------------------------------------------- #
# Phase 3 — AI tools, brand voice, analytics
# --------------------------------------------------------------------------- #
TOOL_INSTRUCTIONS = {
    "shorten": ("Rewrite this post to be significantly more concise and punchy while preserving "
                "the core message and call-to-action. Keep it within the platform's ideal length."),
    "expand": ("Expand this post with more depth: add a concrete example or supporting detail plus "
               "a stronger hook and closing. Keep the same tone and platform style."),
    "translate": ("Translate this post into {language}. Preserve the tone, hashtags, formatting and "
                  "intent. Return only the translated post."),
}


@frappe.whitelist()
def apply_tool(post, tool, language=None):
    """One-click AI tools. Reuse Social Media Post.revise_post with a preset instruction."""
    instr = TOOL_INSTRUCTIONS.get(tool)
    if not instr:
        frappe.throw(_("Unknown tool: {0}").format(tool))
    if tool == "translate":
        instr = instr.format(language=language or "Spanish")
    doc = frappe.get_doc("Social Media Post", post)
    return doc.revise_post(instr)


@frappe.whitelist()
def get_brand_voice():
    return {"brand_voice": frappe.db.get_single_value("Content Hub Setting", "brand_voice") or ""}


@frappe.whitelist()
def set_brand_voice(brand_voice):
    frappe.db.set_single_value("Content Hub Setting", "brand_voice", brand_voice or "")
    return {"status": "success"}


@frappe.whitelist()
def apply_brand_voice(post):
    voice = frappe.db.get_single_value("Content Hub Setting", "brand_voice")
    if not voice:
        frappe.throw(_("No brand voice defined yet. Set it first."))
    instr = (f"Rewrite this post to match our brand voice and persona described below, "
             f"keeping the platform style and length.\n\nBrand voice:\n{voice}")
    doc = frappe.get_doc("Social Media Post", post)
    return doc.revise_post(instr)


@frappe.whitelist()
def get_analytics():
    """Aggregate dashboard analytics from existing Social Media Post data.
    (Engagement pull-back from platform APIs is a future enhancement.)"""
    from frappe.utils import add_days, getdate, nowdate, get_first_day

    posted_this_month = frappe.db.count("Social Media Post", {
        "status": "Posted",
        "posted_on": [">=", get_first_day(nowdate())],
    })

    rows = frappe.get_all("Social Media Post",
                          fields=["name", "title", "platform", "status", "post_on",
                                  "created_on", "post_link", "modified", "posted_on"])
    totals = {"total": len(rows), "posted": 0, "scheduled": 0, "draft": 0, "failed": 0, "posted_this_month": posted_this_month}
    by_platform, by_status = {}, {}
    for r in rows:
        st = r.get("status") or "Draft"
        key = {"Posted": "posted", "Scheduled": "scheduled",
               "Draft": "draft", "Failed": "failed"}.get(st)
        if key:
            totals[key] += 1
        by_status[st] = by_status.get(st, 0) + 1
        pf = r.get("platform") or "Other"
        by_platform[pf] = by_platform.get(pf, 0) + 1

    denom = totals["posted"] + totals["failed"]
    totals["success_rate"] = round((totals["posted"] / denom) * 100) if denom else 100

    # 14-day timeline by created_on
    timeline = []
    for i in range(13, -1, -1):
        day = add_days(nowdate(), -i)
        c = sum(1 for r in rows if str(r.get("created_on") or "")[:10] == str(day))
        timeline.append({"date": str(day), "count": c})

    recent = sorted(rows, key=lambda r: str(r.get("modified") or ""), reverse=True)[:8]
    return {
        "totals": totals,
        "by_platform": [{"platform": k, "count": v} for k, v in
                        sorted(by_platform.items(), key=lambda x: -x[1])],
        "by_status": [{"status": k, "count": v} for k, v in by_status.items()],
        "timeline": timeline,
        "recent": recent,
    }

@frappe.whitelist()
def get_configured_youtube_channels():
    settings = frappe.get_single("YouTube Settings")
    channels = []
    for c in (settings.channels or []):
        name = c.channel_name or c.channel_id
        if name:
            channels.append({
                "channel_name": c.channel_name or "",
                "channel_id": c.channel_id or "",
                "label": f"{c.channel_name} ({c.channel_id})" if c.channel_id else c.channel_name
            })
    return channels



@frappe.whitelist()
def fetch_youtube_channel_videos(channel_name_or_id: str, max_results: int = 5, auto_create_content_hub: int = 1):
    del auto_create_content_hub
    settings = frappe.get_single("YouTube Settings")
    requested_channel = (channel_name_or_id or "").strip()
    channel = next(
        (row for row in settings.channels or [] if requested_channel in {row.channel_name, row.channel_id}),
        None,
    )
    if not channel or not channel.channel_id:
        frappe.throw(_("Select a configured YouTube channel"))

    tracker = frappe.new_doc("YouTube Videos")
    tracker.insert()
    enqueue_youtube_workflow(
        tracker_name=tracker.name,
        channel_id=channel.channel_id,
        force=True,
        max_results=max_results,
    )
    return {
        "status": "queued",
        "channel_title": channel.channel_name,
        "tracker_name": tracker.name,
    }


@frappe.whitelist()
def fetch_youtube_url(url: str, auto_create_content_hub: int = 1):
    del auto_create_content_hub
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url or "")
    if not match:
        frappe.throw(_("Invalid YouTube URL"))
    video_id = match.group(1)

    existing = frappe.db.get_value("YouTube Video", {"video_id": video_id}, ["parent", "title"], as_dict=True)
    if existing and existing.parent:
        return {"status": "success", "video_name": video_id, "title": existing.title or "", "tracker_name": existing.parent, "already_exists": True}

    settings = frappe.get_single("YouTube Settings")
    api_key = settings.get_password("api_key", raise_exception=False)
    if not api_key:
        frappe.throw(_("YouTube API Key is missing in YouTube Settings"))
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"key": api_key, "id": video_id, "part": "snippet,statistics"},
        timeout=30,
    ).json()
    if not response.get("items"):
        frappe.throw(_("Video not found on YouTube"))

    item = response["items"][0]
    snippet = item.get("snippet", {})
    tracker = frappe.new_doc("YouTube Videos")
    tracker.append("videos", {
        "channel_id": snippet.get("channelId", ""),
        "channel_name": snippet.get("channelTitle", ""),
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "published_on": snippet.get("publishedAt"),
        "views": int(item.get("statistics", {}).get("viewCount", 0)),
        "video_link": f"https://www.youtube.com/watch?v={video_id}",
    })
    tracker.insert()
    enqueue_video_processing(tracker.name)
    return {"status": "queued", "video_name": video_id, "title": snippet.get("title", ""), "tracker_name": tracker.name}
