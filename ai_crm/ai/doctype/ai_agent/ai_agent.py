from ai_crm.ai.agent.agent_service import AgentService
import frappe
from frappe.model.document import Document
import os



class AIAgent(Document):
    """
    Enhanced AI Agent with capabilities:
    - Multiple agent types with specialized behaviors
    - Advanced memory management
    - Tool integration and workflow capabilities
    - Conversation context and state management
    - Structured output and response formatting
    """
    
    def __init__(self, *args, **kwargs):
        self._agent_service = None
        super().__init__(*args, **kwargs)
    
    def validate(self):
        if self.agent_type == "Gemini Cache Agent":
            if any(map(lambda x:x.type == 'system', self.messages)):
                frappe.throw("You can not set system message for Gemini Cache Agent")
        if not self.output_schema:
            self.output_schema = None

        if self.enable_memory and not self.memory_type:
            frappe.throw("Memory type is required when memory is enabled")
        
    @property
    def agent_service(self):
        if self._agent_service:
            return self._agent_service
        self._agent_service = AgentService(self)
        return self._agent_service

