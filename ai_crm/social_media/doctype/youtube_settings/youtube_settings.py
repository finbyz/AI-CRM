import re

import frappe
import requests
from frappe import _
from frappe.model.document import Document

CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")


class YouTubeSettings(Document):
    def validate(self):
        before = self.get_doc_before_save()
        old_names = {row.name: row.channel_name for row in (before.channels if before else [])}
        api_key = self.get_password("api_key", raise_exception=False) if self.api_key else None

        for row in self.channels:
            row.channel_name = (row.channel_name or "").strip()
            name_changed = old_names.get(row.name) != row.channel_name
            if row.channel_id and row.channel_title and not name_changed:
                continue

            info = get_channel_info(row.channel_name, api_key)
            if not info:
                frappe.throw(
                    _("Row {0}: YouTube channel {1} not found. Use the @handle or channel URL.").format(
                        row.idx, frappe.bold(row.channel_name)
                    )
                )
            row.channel_id = info["channel_id"]
            row.channel_title = info["title"]


def get_channel_info(value, api_key=None):
    """Resolve an @handle, channel URL or channel ID to {channel_id, title}."""
    value = (value or "").strip().rstrip("/")
    if not value:
        return None

    match = re.search(r"youtube\.com/(channel/UC[\w-]{22}|@[\w.-]+)", value)
    if match:
        value = match.group(1).removeprefix("channel/")
    elif not CHANNEL_ID_RE.match(value) and not value.startswith("@"):
        value = "@" + value

    if api_key:
        params = {"key": api_key, "part": "snippet"}
        params["id" if CHANNEL_ID_RE.match(value) else "forHandle"] = value
        try:
            res = requests.get("https://www.googleapis.com/youtube/v3/channels", params=params, timeout=15)
            items = res.json().get("items") or []
        except Exception:
            frappe.log_error(f"Channel lookup failed for {value}", "YouTube Settings")
            items = []
        if items:
            return {"channel_id": items[0]["id"], "title": items[0]["snippet"]["title"]}
        return None

    return _scrape_channel_info(value)


def _scrape_channel_info(value):
    """Fallback when no API key is set: read the channel page's canonical link."""
    path = f"channel/{value}" if CHANNEL_ID_RE.match(value) else value
    try:
        page = requests.get(f"https://www.youtube.com/{path}", timeout=15).text
    except Exception:
        return None
    channel = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"', page)
    if not channel:
        return None
    title = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    return {"channel_id": channel.group(1), "title": title.group(1) if title else ""}


@frappe.whitelist()
def lookup_channel(channel_name):
    frappe.only_for(("System Manager", "Social Media Manager"))
    settings = frappe.get_single("YouTube Settings")
    info = get_channel_info(channel_name, settings.get_password("api_key", raise_exception=False))
    if not info:
        frappe.throw(_("YouTube channel {0} not found").format(frappe.bold(channel_name)))
    return info


@frappe.whitelist()
def test_channels(channel_ids, max_results=3):
    """Fetch the latest videos of the given channels now and process them in the background."""
    from ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services.background_jobs import (
        enqueue_youtube_workflow,
    )

    frappe.only_for(("System Manager", "Social Media Manager"))
    channel_ids = frappe.parse_json(channel_ids) if isinstance(channel_ids, str) else channel_ids
    configured = {row.channel_id for row in frappe.get_single("YouTube Settings").channels}
    channel_ids = [c for c in channel_ids or [] if c in configured]
    if not channel_ids:
        frappe.throw(_("Select at least one saved channel"))

    tracker = frappe.new_doc("YouTube Videos")
    tracker.workflow_status = "Queued"
    tracker.workflow_message = f"Test fetch for {len(channel_ids)} channel(s)"
    tracker.insert()
    enqueue_youtube_workflow(
        tracker_name=tracker.name,
        channel_id=channel_ids,
        force=True,
        max_results=max(1, min(int(max_results or 3), 10)),
    )
    return tracker.name
