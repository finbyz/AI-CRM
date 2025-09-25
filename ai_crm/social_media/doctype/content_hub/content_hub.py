import frappe
from frappe.model.document import Document
from frappe.utils import nowdate

class ContentHub(Document):

    @frappe.whitelist()
    def generate_linkedin_ideas(self):
        # Check credential
        if not self.credential:
            frappe.throw("No credential selected in Content Hub")
        
        credential_doc = frappe.get_doc(self.credential_type, self.credential)
        content_hub_setting = frappe.get_single("Content Hub Setting")

        # Determine which AI agent to use with fallback
        if credential_doc.use_default_ai_agents == 1:
            idea_agent = content_hub_setting.idea_agent
        else:
            idea_agent_name = credential_doc.idea_generator_agent
            if idea_agent_name:
                ai_agent_doc = frappe.get_doc("AI Agent", idea_agent_name)
                idea_agent = ai_agent_doc.agent_service
            else:
                # Fallback to content hub setting agent if credential agent is empty
                idea_agent = content_hub_setting.idea_agent

        # Keep the original working AI invocation
        ai_input_data = {
            "title": self.title,
            "target_audience": self.target_audience,
            "social_media": self.platform
        }
        result = idea_agent.invoke(**ai_input_data)
        ideas = result.ideas  # This worked in your original code
        
        # Append ideas to child table
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
        # Get the credential record
        if not self.credential:
            frappe.throw("No credential selected in Content Hub")
            
        credential_doc = frappe.get_doc(self.credential_type, self.credential)
        content_hub_setting = frappe.get_single("Content Hub Setting")

        # Determine which AI agent to use with fallback
        if credential_doc.use_default_ai_agents == 1:
            post_agent = content_hub_setting.post_agent
        else:
            post_agent_name = credential_doc.post_generator_agent
            if post_agent_name:
                ai_agent_doc = frappe.get_doc("AI Agent", post_agent_name)
                post_agent = ai_agent_doc.agent_service
            else:
                # Fallback to content hub setting agent if credential agent is empty
                post_agent = content_hub_setting.post_agent

        # Prepare AI input data
        ai_input_data = {
            "title": self.title,
            "target_audience": self.target_audience,
            "social_media": self.platform,
            "idea_title": idea_title,
            "idea_description": idea_description,
            "content_hub_name": self.name,
        }

        # Invoke AI agent
        result = post_agent.invoke(**ai_input_data)
        post_content = getattr(result, "content", None)
        if not post_content:
            frappe.throw("AI agent did not return post content")

        # Create new Social Media Post
        new_post = frappe.new_doc("Social Media Post")
        new_post.title = self.title
        new_post.status = "Draft"
        new_post.platform = self.platform
        new_post.content_hub = self.name
        new_post.reference_content_idea = idea_title
        new_post.content = post_content
        new_post.created_on = nowdate()
        new_post.insert()
        
        return {"status": "success", "post_name": new_post.name}
