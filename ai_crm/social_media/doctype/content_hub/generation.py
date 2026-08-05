import frappe
from frappe import _
from frappe.utils import nowdate


PLATFORM_BY_CREDENTIAL = {
    "Twitter Integration": "X (Twitter)",
    "LinkedIn Integration": "LinkedIn",
    "Reddit Integration": "Reddit",
}


def queue_posts_for_idea(content_hub, idea_name, targets):
    targets = frappe.parse_json(targets) if isinstance(targets, str) else targets
    if not isinstance(targets, list) or not targets:
        frappe.throw(_("Select at least one social media account"))

    idea = next((row for row in content_hub.ideas_child_table if row.name == idea_name), None)
    if not idea:
        frappe.throw(_("The selected idea does not belong to this Content Hub"))

    settings = frappe.get_single("Content Hub Setting")
    post_names = []
    seen_targets = set()
    for target in targets:
        credential_type, credential, platform = _validate_target(target)
        target_key = (credential_type, credential)
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)

        post = frappe.new_doc("Social Media Post")
        post.title = idea.idea_title or content_hub.title
        post.status = "Draft"
        post.generation_status = "Queued"
        post.platform = platform
        post.credential_type = credential_type
        post.credential = credential
        post.content_hub = content_hub.name
        post.reference_content_idea = idea.idea_title
        post.source_idea_row = idea.name
        post.source_type = content_hub.source_type or "Manual Topic"
        post.source_title = content_hub.title
        post.source_channel = content_hub.channel_name
        yt_doc = None
        if content_hub.source_type == "YouTube Video":
            yt_video_name = frappe.db.get_value("YouTube Video", {"content_hub": content_hub.name}, "name")
            if yt_video_name:
                yt_doc = frappe.get_doc("YouTube Video", yt_video_name)
                
        post.source_video_link = yt_doc.video_link if yt_doc else ""
        post.source_views = yt_doc.views if yt_doc else 0
        post.source_transcript = yt_doc.transcript if yt_doc else ""
        post.target_audience = content_hub.target_audience
        post.source_idea_description = idea.description
        post.brand_voice_snapshot = settings.brand_voice
        post.created_on = nowdate()
        post.insert()
        post_names.append(post.name)

        # Update Content Hub with the generated post link
        frappe.db.set_value("Content Hub", content_hub.name, "social_media_post", post.name)
        
        # Update YouTube Video child table with the generated post link
        if yt_doc:
            frappe.db.set_value("YouTube Video", yt_doc.name, "social_media_post", post.name)

        frappe.enqueue(
            generate_post_content,
            queue="long",
            timeout=900,
            enqueue_after_commit=True,
            job_id=f"content-studio:{post.name}",
            deduplicate=True,
            post_name=post.name,
            content_hub_name=content_hub.name,
            idea_name=idea.name,
        )

    return {"status": "queued", "posts": post_names}


def generate_post_content(post_name, content_hub_name, idea_name):
    post = frappe.get_doc("Social Media Post", post_name)
    hub = frappe.get_doc("Content Hub", content_hub_name)
    idea = next((row for row in hub.ideas_child_table if row.name == idea_name), None)
    if not idea:
        _mark_generation_failed(post, "The source idea no longer exists")
        return

    try:
        post.db_set("generation_status", "Generating", update_modified=False)
        agent = _get_post_agent(hub, post)
        result = agent.invoke(**_build_agent_input(hub, post, idea))
        content = getattr(result, "content", None)
        if content is None and isinstance(result, dict):
            content = result.get("content")
        if not content:
            frappe.throw(_("The post agent returned empty content"))

        post.reload()
        post.content = str(content)
        post.generation_status = "Ready"
        post.failure_reason = None
        post.flags.skip_approval_reset = True
        post.save(ignore_permissions=True)
    except Exception as error:
        _mark_generation_failed(post, str(error))
        frappe.log_error(frappe.get_traceback(), f"Content Studio generation failed: {post.name}")


def _validate_target(target):
    if not isinstance(target, dict):
        frappe.throw(_("Each account target must be an object"))
    credential_type = target.get("credential_type")
    credential = target.get("credential")
    if credential_type not in PLATFORM_BY_CREDENTIAL or not isinstance(credential, str):
        frappe.throw(_("Invalid social media account"))
    if not frappe.db.exists(credential_type, credential):
        frappe.throw(_("Social media account {0} does not exist").format(credential))
    return credential_type, credential, PLATFORM_BY_CREDENTIAL[credential_type]


def _get_post_agent(hub, post):
    settings = frappe.get_single("Content Hub Setting")
    credential = frappe.get_doc(post.credential_type, post.credential)
    agent_name = None
    if not getattr(credential, "use_default_ai_agents", False):
        agent_name = getattr(credential, "post_generator_agent", None)
    if not agent_name and hub.source_type == "YouTube Video":
        agent_name = settings.youtube_post_generator_agent
    agent_name = agent_name or settings.post_generator_agent
    if not agent_name:
        frappe.throw(_("No Post Generator Agent is configured"))
    return frappe.get_doc("AI Agent", agent_name).agent_service


def _build_agent_input(hub, post, idea):
    brand_voice = post.brand_voice_snapshot or ""
    return {
        "action": "generate",
        "title": post.source_title or hub.title,
        "target_audience": post.target_audience or "",
        "social_media": post.platform,
        "idea_title": post.reference_content_idea or idea.idea_title,
        "idea_description": post.source_idea_description or "",
        "previous_post": "None",
        "instruction": f"Brand Voice / Tone: {brand_voice}" if brand_voice else "None",
        "source_type": post.source_type or "Manual Topic",
        "channel_name": post.source_channel or "",
        "youtube_views": post.source_views or 0,
        "youtube_video_link": post.source_video_link or "",
        "transcript": (post.source_transcript or "")[:12000],
    }


def _mark_generation_failed(post, reason):
    post.reload()
    post.status = "Failed"
    post.generation_status = "Failed"
    post.failure_reason = str(reason)[-2000:]
    post.flags.skip_approval_reset = True
    post.save(ignore_permissions=True)
