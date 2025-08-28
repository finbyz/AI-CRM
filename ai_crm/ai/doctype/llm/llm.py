# Copyright (c) 2025, sandeep and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from langchain_litellm import ChatLiteLLM

class LLM(Document):
	@property
	def llm(self):
		provider = frappe.get_doc("LLM Provider", self.provider)
		return ChatLiteLLM(
			api_key = provider.get_password("api_key"),
			model = self.name,
		)