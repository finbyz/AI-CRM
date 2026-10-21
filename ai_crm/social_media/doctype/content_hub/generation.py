import frappe
from frappe import _

from ai_crm.social_media.platforms import PLATFORM_BY_CREDENTIAL, get_platform, to_platform_text
from ai_crm.social_media.doctype.youtube_settings.youtube_settings import is_own_channel


# Posts generated together from research share this key in source_idea_row, so they can share a creative.
RESEARCH_BATCH_PREFIX = "research-"
RESEARCH_LIMIT = 20000
# What the account already said, so a new post never repeats it.
HISTORY_STATUSES = ("Pending Approval", "Approved", "Scheduled", "Publishing", "Posted")
HISTORY_POSTS = 20
HISTORY_POST_CHARS = 700
SKIP_PREFIX = "SKIP:"


def queue_posts_for_idea(content_hub, idea_name, targets):
    idea = next((row for row in content_hub.ideas_child_table if row.name == idea_name), None)
    if not idea:
        frappe.throw(_("The selected idea does not belong to this Content Hub"))
    return queue_posts(content_hub, targets, idea=idea)


def queue_posts(content_hub, targets, idea=None, instruction=None):
    """Create one draft per account and generate each in the background, from an idea or from the research."""
    targets = frappe.parse_json(targets) if isinstance(targets, str) else targets
    if not isinstance(targets, list) or not targets:
        frappe.throw(_("Select at least one social media account"))

    batch_key = idea.name if idea else f"{RESEARCH_BATCH_PREFIX}{frappe.generate_hash(length=10)}"
    instruction = (instruction or "").strip()
    post_names = []
    seen_targets = set()
    for target in targets:
        credential_type, credential, subreddit = _validate_target(target)
        target_key = (credential_type, credential)
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)

        post = frappe.new_doc("Social Media Post")
        post.title = (idea.idea_title if idea else None) or content_hub.title
        post.status = "Draft"
        post.generation_status = "Queued"
        post.credential_type = credential_type
        post.credential = credential
        post.subreddit = subreddit
        post.content_hub = content_hub.name
        post.reference_content_idea = idea.idea_title if idea else None
        post.source_idea_row = batch_key
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
            idea_name=batch_key,
            instruction=instruction,
        )

    return {"status": "queued", "posts": post_names}


def generate_post_content(post_name, content_hub_name, idea_name, instruction=None):
    post = frappe.get_doc("Social Media Post", post_name)
    hub = frappe.get_doc("Content Hub", content_hub_name)
    idea = None
    if not (idea_name or "").startswith(RESEARCH_BATCH_PREFIX):
        idea = next((row for row in hub.ideas_child_table if row.name == idea_name), None)
        if not idea:
            _mark_generation_failed(post, "The source idea no longer exists")
            return

    try:
        post.db_set("generation_status", "Generating", update_modified=False)
        agent = _get_post_agent(hub, post)
        query = _build_research_message(hub, instruction) + _build_history_message(post)
        result = agent.invoke(query=query, **_build_agent_input(hub, post, idea))
        content = getattr(result, "content", None)
        if content is None and isinstance(result, dict):
            content = result.get("content")
        if not content:
            frappe.throw(_("The post agent returned empty content"))
        if str(content).strip().upper().startswith(SKIP_PREFIX):
            reason = str(content).strip()[len(SKIP_PREFIX):].strip()
            _mark_generation_failed(post, _("Skipped: this account already covered this topic. {0}").format(reason))
            return

        post.reload()
        post.content = to_platform_text(post.credential_type, str(content))
        post.generation_status = "Ready"
        post.failure_reason = None
        post.flags.skip_approval_reset = True
        post.save(ignore_permissions=True)
    except Exception as error:
        _mark_generation_failed(post, str(error))
        frappe.log_error(frappe.get_traceback(), f"Content Studio generation failed: {post.name}")


def _build_research_message(hub, instruction=None):
    """Sent as the final message, so the research reaches any post agent prompt."""
    parts = []
    if (hub.research or "").strip():
        parts.append(
            "Research notes on this topic (gathered from the web). Use their facts and numbers where they "
            "strengthen the post, never invent beyond them, and do not add their source links to the post.\n\n"
            + hub.research.strip()[:RESEARCH_LIMIT]
        )
    if instruction:
        parts.append(f"Extra instructions for this post: {instruction}")
    return "\n\n".join(parts) or "Write the post."


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


def _build_history_message(post):
    """The account's earlier posts, so the agent changes the angle or skips a topic it already covered."""
    history = frappe.get_all(
        "Social Media Post",
        filters={
            "credential_type": post.credential_type,
            "credential": post.credential,
            "status": ["in", HISTORY_STATUSES],
            "name": ["!=", post.name],
            "content": ["is", "set"],
        },
        fields=["content", "status", "posted_on", "modified"],
        order_by="coalesce(posted_on, modified) desc",
        limit=HISTORY_POSTS,
    )
    if not history:
        return ""

    entries = []
    for i, row in enumerate(history, 1):
        when = frappe.utils.formatdate(row.posted_on or row.modified, "dd MMM yyyy")
        text = row.content.strip()
        if len(text) > HISTORY_POST_CHARS:
            text = text[:HISTORY_POST_CHARS] + "..."
        entries.append(f"[{i}] {row.status}, {when}:\n{text}")

    return (
        "\n\nPosts this account has already published or queued (newest first):\n\n"
        + "\n\n".join(entries)
        + "\n\nBefore writing, check these posts. Never repeat their hook, main point, examples or closing "
        "question. If one of them already covers this topic, write only from a clearly different angle with "
        "facts it did not use. If there is no genuinely new angle left, do not write a post; reply with "
        f'{{"content": "{SKIP_PREFIX} <one sentence naming the earlier post and why>"}} instead.'
    )


def _build_agent_input(hub, post, idea):
    settings = frappe.get_single("Content Hub Setting")
    source = _get_source_context(hub)
    brand_voice = settings.brand_voice or ""
    own = is_own_channel(source.get("channel_id"))
    return {
        "action": "generate",
        "title": hub.title,
        "target_audience": hub.target_audience or "",
        "social_media": get_platform(post.credential_type),
        "idea_title": idea.idea_title if idea else hub.title,
        "idea_description": (idea.description or "") if idea else (
            "No idea was pre-selected. Choose the single strongest, most useful angle from the research notes "
            "and the source material."
        ),
        "previous_post": "None",
        "instruction": f"Brand Voice / Tone: {brand_voice}" if brand_voice else "None",
        "source_type": hub.source_type or "Manual Topic",
        "channel_name": source.get("channel_name") or hub.channel_name or "",
        "youtube_views": source.get("views") or 0,
        # Only our own videos are linked; other channels are used as background, never cited.
        "youtube_video_link": (source.get("video_link") or hub.source_url or "None") if own else "None",
        "video_ownership": "Our own video" if own else "Third-party video",
        "transcript": (source.get("transcript") or "")[:12000],
    }


def _get_source_context(hub):
    if hub.source_type != "YouTube Video":
        return frappe._dict()
    return frappe.db.get_value(
        "YouTube Video",
        {"content_hub": hub.name},
        ["channel_id", "channel_name", "views", "video_link", "transcript"],
        as_dict=True,
    ) or frappe._dict()


def _mark_generation_failed(post, reason):
    post.reload()
    post.status = "Failed"
    post.generation_status = "Failed"
    post.failure_reason = str(reason)[-2000:]
    post.flags.skip_approval_reset = True
    post.save(ignore_permissions=True)


NEXTJS_PAGE_TYPES = {"Web Page": "Web page", "Blog Post": "Blog Post"}


def draft_nextjs_page(hub, output_type):
    """Draft an unsaved NextJS Page holding the hub's full research, for the user to review and save."""
    if "finbyzweb" not in frappe.get_installed_apps():
        frappe.throw(_("Web pages need the finbyzweb app"))
    if output_type not in NEXTJS_PAGE_TYPES:
        frappe.throw(_("Choose Web Page or Blog Post"))
    if not (hub.research or "").strip():
        frappe.throw(_("Click Do Research first. The page is created from the research notes."))
    frappe.has_permission("NextJS Page", "create", throw=True)

    from finbyzweb.nextjs_web.doctype.nextjs_page.nextjs_page import slugify

    title = _get_page_title(hub, output_type)
    route = "/" + slugify(title)
    return frappe.get_doc({
        "doctype": "NextJS Page",
        "title": title,
        "page_type": NEXTJS_PAGE_TYPES[output_type],
        "content_type": "Markdown",
        "content_md": hub.research.strip(),
        "is_published": 0,
        "route": route,
        "actual_route": route,
    })


def _get_page_title(hub, output_type):
    """Reuse the hub's page title, or write a fresh one so the page never copies the source's title."""
    source_title = _get_source_title(hub)
    if hub.page_title and _normalize_title(hub.page_title) != _normalize_title(source_title):
        return hub.page_title

    from ai_crm.social_media.doctype.content_hub.research import generate_page_title

    title = generate_page_title(hub, source_title, output_type)
    if hub.name:
        hub.db_set("page_title", title)
    return title


def _get_source_title(hub):
    if hub.source_type == "YouTube Video" and hub.name:
        return frappe.db.get_value("YouTube Video", {"content_hub": hub.name}, "title") or hub.title
    return hub.title


def _normalize_title(title):
    return " ".join("".join(ch for ch in (title or "").casefold() if ch.isalnum() or ch.isspace()).split())
