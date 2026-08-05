import frappe
from frappe.model.document import Document

from ai_crm.social_media.doctype.content_hub.generation import queue_posts_for_idea


class ContentHub(Document):

    @frappe.whitelist(methods=["POST"])
    def generate_ideas(self):
        self.check_permission("write")
        return self.generate_linkedin_ideas()

    @frappe.whitelist(methods=["POST"])
    def generate_linkedin_ideas(self):
        self.check_permission("write")
        self.db_set({"generation_status": "Generating", "generation_error": None})
        try:
            return self._generate_linkedin_ideas()
        except Exception as error:
            frappe.log_error(frappe.get_traceback(), f"Content Hub idea generation failed: {self.name}")
            self.db_set({"generation_status": "Failed", "generation_error": str(error)[:500]})
            return {"status": "error", "error": str(error)}

    def _generate_linkedin_ideas(self):
        content_hub_setting = frappe.get_single("Content Hub Setting")

        # Determine AI Agent
        agent_name = None
        if self.credential and self.credential_type:
            cred_doc = frappe.get_doc(self.credential_type, self.credential)
            if not getattr(cred_doc, "use_default_ai_agents", False):
                agent_name = getattr(cred_doc, "idea_generator_agent", None)

        is_youtube = (getattr(self, "source_type", None) == "YouTube Video")

        if not agent_name and is_youtube:
            agent_name = (
                getattr(content_hub_setting, "youtube_idea_generator_agent", None)
                or getattr(content_hub_setting, "youtube_fetch_agent", None)
            )

        if not agent_name:
            agent_name = content_hub_setting.idea_generator_agent

        if not agent_name:
            frappe.throw("No Idea Generator Agent configured in Content Hub Setting")

        idea_agent = frappe.get_doc("AI Agent", agent_name).agent_service

        # Prepare YouTube transcript & context
        youtube_context = ""
        transcript_text = ""
        youtube_video_link = ""
        youtube_views = 0
        channel_name = getattr(self, "channel_name", "") or ""

        if is_youtube:
            try:
                # Find the linked YouTube Video child table record
                yt_video_name = frappe.db.get_value("YouTube Video", {"content_hub": self.name}, "name")
                if yt_video_name:
                    yt_doc = frappe.get_doc("YouTube Video", yt_video_name)
                    raw_transcript = (yt_doc.transcript or "").strip()
                    transcript_text = raw_transcript[:12000] + ("..." if len(raw_transcript) > 12000 else "")
                    youtube_video_link = yt_doc.video_link or f"https://www.youtube.com/watch?v={yt_doc.video_id}"
                    youtube_views = yt_doc.views or 0
                    if yt_doc.channel_name and not channel_name:
                        channel_name = yt_doc.channel_name
    
                    youtube_context = (
                        f"\n\nYouTube Video Context:\n"
                        f"Title: {yt_doc.title}\n"
                        f"Channel Name: {channel_name}\n"
                        f"Views: {youtube_views}\n"
                        f"Video Link: {youtube_video_link}\n"
                        f"Transcript: {transcript_text}"
                    )
            except Exception as e:
                frappe.log_error(f"Error fetching YouTube Video for Content Hub: {str(e)}")

        brand_voice = content_hub_setting.brand_voice or ""
        brand_voice_prompt = f"\nBrand Voice / Tone: {brand_voice}" if brand_voice else ""

        ai_input_data = {
            "title": f"{self.title}{youtube_context}{brand_voice_prompt}",
            "target_audience": self.target_audience or "",
            "social_media": self.platform or "Source Neutral",
            "youtube_views": youtube_views,
            "channel_name": channel_name,
            "youtube_video_link": youtube_video_link,
            "transcript": transcript_text
        }

        result = idea_agent.invoke(**ai_input_data)
        ideas = getattr(result, "ideas", []) if hasattr(result, "ideas") else result.get("ideas", [])

        # Append ideas to child table
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

        self.generation_status = "Ready"
        self.generation_error = None
        self.save()
        self.reload()
        return {"status": "success", "docname": self.name}

    @frappe.whitelist(methods=["POST"])
    def generate_posts_from_idea(self, idea_name: str, targets: str | list):
        self.check_permission("read")
        return queue_posts_for_idea(self, idea_name, targets)

    @frappe.whitelist(methods=["POST"])
    def generate_post_from_idea(self, idea_title: str, idea_description: str):
        """Compatibility wrapper for the existing Content Hub form."""
        self.check_permission("read")
        if not self.credential_type or not self.credential or not self.platform:
            frappe.throw("Select an account before generating a post")
        idea = next(
            (
                row for row in self.ideas_child_table
                if row.idea_title == idea_title and row.description == idea_description
            ),
            None,
        )
        if not idea:
            frappe.throw("The selected idea does not belong to this Content Hub")
        result = queue_posts_for_idea(self, idea.name, [{
            "credential_type": self.credential_type,
            "credential": self.credential,
            "platform": self.platform,
        }])
        return {"status": "queued", "post_name": result["posts"][0]}
