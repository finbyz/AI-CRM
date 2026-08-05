import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class ContentHub(Document):

    @frappe.whitelist()
    def generate_ideas(self):
        return self.generate_linkedin_ideas()

    @frappe.whitelist()
    def generate_linkedin_ideas(self):
        content_hub_setting = frappe.get_single("Content Hub Setting")

        # Determine AI Agent
        agent_name = None
        if self.credential and self.credential_type:
            cred_doc = frappe.get_doc(self.credential_type, self.credential)
            if not cred_doc.use_default_ai_agents:
                agent_name = cred_doc.idea_generator_agent

        is_youtube = (getattr(self, "source_type", None) == "YouTube Video")

        if not agent_name and is_youtube:
            agent_name = getattr(content_hub_setting, "youtube_idea_generator_agent", None) or getattr(content_hub_setting, "youtube_fetch_agent", None)

        if not agent_name:
            agent_name = content_hub_setting.idea_generator_agent

        if not agent_name:
            frappe.throw("No Idea Generator Agent configured in Content Hub Setting")

        idea_agent = frappe.get_doc("AI Agent", agent_name).agent_service

        # Prepare YouTube transcript & context
        youtube_context = ""
        transcript_text = (getattr(self, "youtube_transcript", "") or "")[:12000]
        youtube_video_link = getattr(self, "youtube_video_link", "") or ""
        youtube_views = getattr(self, "youtube_views", 0) or 0
        channel_name = getattr(self, "channel_name", "") or ""

        if is_youtube and getattr(self, "youtube_video", None):
            try:
                yt_doc = frappe.get_doc("YouTube Video", self.youtube_video)
                raw_transcript = (yt_doc.transcript or "").strip()
                transcript_text = raw_transcript[:12000] + ("..." if len(raw_transcript) > 12000 else "")
                youtube_video_link = yt_doc.video_link or f"https://www.youtube.com/watch?v={yt_doc.video_id}"
                if yt_doc.views and not youtube_views:
                    youtube_views = yt_doc.views
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
            "social_media": self.platform or "LinkedIn",
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

        self.save()
        self.reload()
        return {"status": "success", "docname": self.name}

    @frappe.whitelist()
    def generate_post_from_idea(self, idea_title: str, idea_description: str):
        content_hub_setting = frappe.get_single("Content Hub Setting")

        # Determine AI Agent
        agent_name = None
        if self.credential and self.credential_type:
            cred_doc = frappe.get_doc(self.credential_type, self.credential)
            if not cred_doc.use_default_ai_agents:
                agent_name = cred_doc.post_generator_agent

        is_youtube = (getattr(self, "source_type", None) == "YouTube Video")

        if not agent_name and is_youtube:
            agent_name = getattr(content_hub_setting, "youtube_post_generator_agent", None)

        if not agent_name:
            agent_name = content_hub_setting.post_generator_agent

        if not agent_name:
            frappe.throw("No Post Generator Agent configured in Content Hub Setting")

        post_agent = frappe.get_doc("AI Agent", agent_name).agent_service

        brand_voice = content_hub_setting.brand_voice or ""
        instruction = f"Brand Voice / Tone: {brand_voice}" if brand_voice else "None"

        # Fetch YouTube transcript and metrics if YouTube source
        transcript_text = (getattr(self, "youtube_transcript", "") or "")[:12000]
        youtube_video_link = getattr(self, "youtube_video_link", "") or ""
        youtube_views = getattr(self, "youtube_views", 0) or 0
        channel_name = getattr(self, "channel_name", "") or ""

        if is_youtube and getattr(self, "youtube_video", None):
            try:
                yt_doc = frappe.get_doc("YouTube Video", self.youtube_video)
                raw_transcript = (yt_doc.transcript or "").strip()
                transcript_text = raw_transcript[:12000] + ("..." if len(raw_transcript) > 12000 else "")
                youtube_video_link = yt_doc.video_link or f"https://www.youtube.com/watch?v={yt_doc.video_id}"
                if yt_doc.views and not youtube_views:
                    youtube_views = yt_doc.views
                if yt_doc.channel_name and not channel_name:
                    channel_name = yt_doc.channel_name
            except Exception as e:
                frappe.log_error(f"Error fetching YouTube Video context for post generation: {str(e)}")

        ai_input_data = {
            "action": "generate",
            "title": self.title,
            "target_audience": self.target_audience or "",
            "social_media": self.platform or "LinkedIn",
            "idea_title": idea_title,
            "idea_description": idea_description,
            "previous_post": "None",
            "instruction": instruction,
            "source_type": getattr(self, "source_type", "Manual Topic"),
            "channel_name": channel_name,
            "youtube_views": youtube_views,
            "youtube_video_link": youtube_video_link,
            "transcript": transcript_text
        }

        result = post_agent.invoke(**ai_input_data)
        post_content = getattr(result, "content", None) or (result.get("content") if isinstance(result, dict) else str(result))

        if not post_content:
            frappe.throw("AI agent did not return post content")

        # Save to Social Media Post
        new_post = frappe.new_doc("Social Media Post")
        new_post.title = idea_title or self.title
        new_post.status = "Draft"
        new_post.platform = self.platform
        new_post.content_hub = self.name
        new_post.reference_content_idea = idea_title
        new_post.content = str(post_content)
        new_post.created_on = nowdate()
        if self.credential_type and self.credential:
            new_post.credential_type = self.credential_type
            new_post.credential = self.credential
        new_post.insert(ignore_permissions=True)

        return {"status": "success", "post_name": new_post.name}
