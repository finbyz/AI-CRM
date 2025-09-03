import json
import frappe
from frappe.model.document import Document
from langchain_litellm.chat_models import ChatLiteLLM
from langchain_core.output_parsers import PydanticOutputParser
from langchain.schema import StrOutputParser
from langchain.prompts import ChatPromptTemplate
from json_schema_to_pydantic import create_model
from langchain.agents import initialize_agent, AgentType


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
    
    def get_tools(self):
        """
        Return a list of LangChain Tool objects for all tools linked to this agent.
        Assumes self.tools is a child table or MultiSelect linking to AIAgentTool DocType.
        """
        tools_list = []
        if self.tools:
            for ai_agent_tool in self.tools:
                tool = frappe.get_doc("AI Tool",ai_agent_tool.tool)
                tools_list.append(tool.get_tool())
        return tools_list

    @property
    def agent(self):
        """
        Initialize and return a LangChain agent using the tools linked to this agent.
        """
        tools = self.get_tools()
        llm = self.get_llm()
        agent = initialize_agent(
            tools,
            llm,
            agent=self._resolve_agent_type()
        )
        return agent

    def _resolve_agent_type(self) -> AgentType:
        desired = self.lc_agent_type
        if not desired:
            return AgentType.ZERO_SHOT_REACT_DESCRIPTION
        for at in AgentType:
            if desired.upper() == at.name.upper() or desired.lower() == at.value.lower():
                return at
        return AgentType.ZERO_SHOT_REACT_DESCRIPTION
    
    def get_llm(self) -> ChatLiteLLM:
        if self.agent_type == "Gemini Cache Agent":
            cache_doc = frappe.get_doc("Gemini Cache",self.gemini_cache)
            llm = cache_doc._llm
        else:
            llm_doc = frappe.get_doc("LLM",self.llm)
            llm = llm_doc.llm
        return llm
    
    def invoke(self, query=None,**kwargs):
        """
        Invoke the AI agent with optional structured output schema
        
        Args:
            query (str): The user query
            kwargs (str, optional): Additional context
        """
        
        llm = self.get_llm()
        
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
        response = chain.invoke(input_vars)
        return response