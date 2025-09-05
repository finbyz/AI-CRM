# Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ContentHubSetting(Document):
	@property
	def idea_agent(self):
		ai_agent = frappe.get_doc("AI Agent", self.idea_generator_agent)
		return ai_agent
	
	@property
	def post_agent(self):
		ai_agent = frappe.get_doc("AI Agent", self.post_generator_agent)
		return ai_agent
	
	@property
	def revise_agent(self):
		ai_agent = frappe.get_doc("AI Agent", self.revise_post_agent)
		return ai_agent

	@property
	def image_agent(self):
		ai_agent = frappe.get_doc("AI Agent", self.image_generation_agent)
		return ai_agent
