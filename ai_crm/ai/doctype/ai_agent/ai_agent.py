import json
import frappe
from frappe.model.document import Document
from langchain_litellm.chat_models import ChatLiteLLM
from langchain_core.output_parsers import PydanticOutputParser
from langchain.schema import StrOutputParser
from langchain.prompts import ChatPromptTemplate
from json_schema_to_pydantic import create_model


class AIAgent(Document):
    
    def validate(self):
        if self.agent_type == "Gemini Cache Agent":
            if any(map(lambda x:x.type == 'system', self.messages)):
                frappe.throw("You can not set system message for Gemini Cache Agent")
        if not self.output_schema:
            self.output_schema = None

    @property
    def chat_messages(self):
        messages = []
        for msg in self.messages:
            messages.append((msg.type, msg.content))
        if self.output_schema:
            message_type = 'system' if self.agent_type != "Gemini Cache Agent" else "human"
            messages.append((message_type, "{format_instructions}"))
        return messages
    
    
    def invoke(self, query=None,**kwargs):
        """
        Invoke the AI agent with optional structured output schema
        
        Args:
            query (str): The user query
            kwargs (str, optional): Additional context
        """
        if self.agent_type == "Gemini Cache Agent":
            cache_doc = frappe.get_doc("Gemini Cache",self.gemini_cache)
            llm: ChatLiteLLM = cache_doc._llm
        else:
            llm_doc = frappe.get_doc("LLM",self.llm)
            llm: ChatLiteLLM = llm_doc.llm
        
        messages = self.chat_messages
        if query:
            messages.append(("human", "{query}"))

        prompt = ChatPromptTemplate.from_messages([
            *messages,
        ])
        dynamic_model = None
        if self.output_schema:
            dynamic_model = create_model(schema=json.loads(self.output_schema))
        format_instructions = ''
        if dynamic_model:
            output_parser = PydanticOutputParser(pydantic_object=dynamic_model)
            format_instructions = output_parser.get_format_instructions()
        else:
            output_parser = StrOutputParser()

        chain = prompt | llm | output_parser
        
        input_vars = {
            "format_instructions": format_instructions,
            "query": query,
            **kwargs
        }
        
        try:
            response = chain.invoke(input_vars)
            return response
        except Exception as e:
            frappe.log_error(f"Query: {query}\nError: {str(e)}", "AIAgent Invoke Error")
            return {"error": f"Error invoking AI agent: {str(e)}"}

