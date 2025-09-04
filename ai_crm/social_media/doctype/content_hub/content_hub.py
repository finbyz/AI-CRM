import frappe
from frappe.model.document import Document

class ContentHub(Document):

    @frappe.whitelist()
    def generate_linkedin_ideas(self):
        content_hub_setting = frappe.get_single("Content Hub Setting")
        idea_agent = content_hub_setting.idea_agent

        ai_input_data = {
            "title": self.title,
            "target_audience": self.target_audience,
            "social_media": self.platform
        }
        result = idea_agent.invoke(**ai_input_data)
        ideas = result.ideas
        
        for idea in ideas:
            self.append("ideas_child_table", {
                "idea_title": getattr(idea, "idea_title", ""),
                "description": getattr(idea, "description", "")
            })
        self.save()
        self.reload()
        return {"status": "success", "docname": self.name}

    @frappe.whitelist()
    def generate_post_from_idea(self, idea_title: str, idea_description: str):
        content_hub_setting = frappe.get_single("Content Hub Setting")
        post_agent = content_hub_setting.post_agent

        ai_input_data = {
            "title": self.title,
            "target_audience": self.target_audience,
            "social_media": "LinkedIn",
            "idea_title": idea_title,
            "idea_description": idea_description,
            "content_hub_name": self.name,
        }

        result = post_agent.invoke(**ai_input_data)
        post_content = result.post_content
        
        if not post_content:
            frappe.throw("AI agent did not return post content")

        new_post = frappe.new_doc("Social Media Post")
        new_post.title = self.title
        new_post.status = "Draft"
        new_post.platform = self.platform
        new_post.content_hub = self.name
        new_post.reference_content_idea = idea_title
        new_post.content = post_content
        new_post.insert()
        return {"status": "success", "post_name": new_post.name}
    