import frappe
from frappe.model.document import Document

from ai_crm.social_media.doctype.content_hub.generation import draft_nextjs_page, queue_posts, queue_posts_for_idea
from ai_crm.social_media.doctype.content_hub.research import queue_research, start_research_for_video
from ai_crm.social_media.doctype.youtube_settings.youtube_settings import is_own_channel


class ContentHub(Document):

    @frappe.whitelist(methods=["POST"])
    def generate_ideas(self):
        self.check_permission("write")
        self.db_set({"generation_status": "Generating", "generation_error": None})
        try:
            return self._generate_ideas()
        except Exception as error:
            frappe.log_error(frappe.get_traceback(), f"Content Hub idea generation failed: {self.name}")
            self.db_set({"generation_status": "Failed", "generation_error": str(error)[:500]})
            return {"status": "error", "error": str(error)}

    def _generate_ideas(self):
        content_hub_setting = frappe.get_single("Content Hub Setting")

        agent_name = None
        is_youtube = (getattr(self, "source_type", None) == "YouTube Video")

        if not agent_name and is_youtube:
            agent_name = content_hub_setting.youtube_idea_generator_agent

        if not agent_name:
            agent_name = content_hub_setting.idea_generator_agent

        if not agent_name:
            frappe.throw("No Idea Generator Agent configured in Content Hub Setting")

        idea_agent = frappe.get_doc("AI Agent", agent_name).agent_service

        # Prepare YouTube transcript & context
        transcript_text = ""
        youtube_video_link = "None"
        youtube_views = 0
        own_video = False
        channel_name = getattr(self, "channel_name", "") or ""

        if is_youtube:
            yt_doc = frappe.db.get_value(
                "YouTube Video",
                {"content_hub": self.name},
                ["channel_id", "channel_name", "video_id", "video_link", "views", "transcript"],
                as_dict=True,
            )
            if yt_doc:
                raw_transcript = (yt_doc.transcript or "").strip()
                transcript_text = raw_transcript[:12000] + ("..." if len(raw_transcript) > 12000 else "")
                youtube_views = yt_doc.views or 0
                channel_name = channel_name or yt_doc.channel_name or ""
                # Only our own videos are linked; other channels are used as background, never cited.
                own_video = is_own_channel(yt_doc.channel_id)
                if own_video:
                    youtube_video_link = yt_doc.video_link or f"https://www.youtube.com/watch?v={yt_doc.video_id}"

        brand_voice = content_hub_setting.brand_voice or ""
        brand_voice_prompt = f"\nBrand Voice / Tone: {brand_voice}" if brand_voice else ""

        ai_input_data = {
            "title": f"{self.title}{brand_voice_prompt}",
            "target_audience": self.target_audience or "",
            "social_media": "Source Neutral",
            "youtube_views": youtube_views,
            "channel_name": channel_name,
            "youtube_video_link": youtube_video_link,
            "video_ownership": "Our own video" if own_video else "Third-party video",
            "transcript": transcript_text
        }

        result = idea_agent.invoke(**ai_input_data)
        ideas = getattr(result, "ideas", []) if hasattr(result, "ideas") else result.get("ideas", [])

        self.set("ideas_child_table", [])
        for idea in (ideas or []):
            if isinstance(idea, dict):
                title = idea.get("idea_title") or idea.get("title") or ""
                desc = idea.get("description") or idea.get("desc") or ""
            else:
                title = getattr(idea, "idea_title", getattr(idea, "title", ""))
                desc = getattr(idea, "description", getattr(idea, "desc", ""))

            if title:
                self.append("ideas_child_table", {
                    "idea_title": title,
                    "description": desc
                })

        self.generation_status = "Completed"
        self.generation_error = None
        self.save()
        self.reload()
        return {"status": "success", "docname": self.name}

    @frappe.whitelist(methods=["POST"])
    def generate_posts_from_idea(self, idea_name: str, targets: str | list):
        self.check_permission("write")
        return queue_posts_for_idea(self, idea_name, targets)

    @frappe.whitelist(methods=["POST"])
    def start_research(self):
        queue_research(self)
        return {"research_status": "Queued"}

    @frappe.whitelist(methods=["POST"])
    def generate_social_posts(self, targets: str | list, instruction: str | None = None):
        self.check_permission("write")
        return queue_posts(self, targets, instruction=instruction)

    @frappe.whitelist(methods=["POST"])
    def draft_web_page(self, output_type: str):
        self.check_permission("read")
        return draft_nextjs_page(self, output_type)


@frappe.whitelist(methods=["POST"])
def start_video_research(video_row: str):
    return start_research_for_video(video_row)
