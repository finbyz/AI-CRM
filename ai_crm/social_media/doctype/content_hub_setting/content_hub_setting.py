# Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

from finbyzai.ai.agent.agent_service import AgentService
from frappe.model.document import Document


class ContentHubSetting(Document):
	@property
	def idea_agent(self):
		ai_agent = AgentService(self.idea_generator_agent)
		return ai_agent
	
	@property
	def post_agent(self):
		ai_agent = AgentService(self.post_generator_agent)
		return ai_agent
	
	@property
	def revise_agent(self):
		ai_agent = AgentService(self.revise_post_agent)
		return ai_agent

	@property
	def image_agent(self):
		ai_agent = AgentService(self.image_generation_agent)
		return ai_agent
