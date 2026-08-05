import frappe
from frappe import _

from ai_crm.social_media.platforms import PLATFORM_BY_CREDENTIAL, get_platform


def queue_posts_for_idea(content_hub, idea_name, targets):
    targets = frappe.parse_json(targets) if isinstance(targets, str) else targets
    if not isinstance(targets, list) or not targets:
        frappe.throw(_("Select at least one social media account"))

    idea = next((row for row in content_hub.ideas_child_table if row.name == idea_name), None)
    if not idea:
        frappe.throw(_("The selected idea does not belong to this Content Hub"))

    post_names = []
    seen_targets = set()
    for target in targets:
        credential_type, credential, subreddit = _validate_target(target)
        target_key = (credential_type, credential)
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)

        post = frappe.new_doc("Social Media Post")
        post.title = idea.idea_title or content_hub.title
        post.status = "Draft"
        post.generation_status = "Queued"
        post.credential_type = credential_type
        post.credential = credential
        post.subreddit = subreddit
        post.content_hub = content_hub.name
        post.reference_content_idea = idea.idea_title
        post.source_idea_row = idea.name
        post.insert()
        post_names.append(post.name)

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
    account = frappe.db.get_value(
        credential_type,
        credential,
        ["name", "connection_status"],
        as_dict=True,
    )
    if not account:
        frappe.throw(_("Social media account {0} does not exist").format(credential))
    subreddit = (target.get("subreddit") or "").strip()
    if credential_type == "Reddit Integration" and not subreddit:
        frappe.throw(_("Select a subreddit for Reddit posts"))
    return credential_type, credential, subreddit


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
    settings = frappe.get_single("Content Hub Setting")
    source = _get_source_context(hub)
    brand_voice = settings.brand_voice or ""
    return {
        "action": "generate",
        "title": hub.title,
        "target_audience": hub.target_audience or "",
        "social_media": get_platform(post.credential_type),
        "idea_title": idea.idea_title,
        "idea_description": idea.description or "",
        "previous_post": "None",
        "instruction": f"Brand Voice / Tone: {brand_voice}" if brand_voice else "None",
        "source_type": hub.source_type or "Manual Topic",
        "channel_name": source.get("channel_name") or hub.channel_name or "",
        "youtube_views": source.get("views") or 0,
        "youtube_video_link": source.get("video_link") or hub.source_url or "",
        "transcript": (source.get("transcript") or "")[:12000],
    }


def _get_source_context(hub):
    if hub.source_type != "YouTube Video":
        return frappe._dict()
    return frappe.db.get_value(
        "YouTube Video",
        {"content_hub": hub.name},
        ["channel_name", "views", "video_link", "transcript"],
        as_dict=True,
    ) or frappe._dict()


def _mark_generation_failed(post, reason):
    post.reload()
    post.status = "Failed"
    post.generation_status = "Failed"
    post.failure_reason = str(reason)[-2000:]
    post.flags.skip_approval_reset = True
    post.save(ignore_permissions=True)
