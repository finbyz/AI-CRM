from finbyzai.ai.agent.agent_service import AgentService
import frappe
from pydantic import BaseModel,Field

def research_company(party_type: str,party_name: str,**kwargs) -> str:
    """Research about a lead or customer using internal data or fallback to Perplexity."""
    doc = frappe.get_doc(party_type, {"name": party_name})
    
    lead_info = {}
    if party_type == "Lead":
        lead_info = {
            "full_name" : f"{doc.salutation or ''} {doc.first_name or ''} {doc.last_name or ''}".strip(),
            "company" : doc.company_name or "",
            "website" : doc.website or "",
            "country" : doc.country or kwargs.get("country"),
            "city" : doc.city or kwargs.get("city"),
            "state" : doc.state or kwargs.get("state"),
            "territory" : doc.territory or kwargs.get("territory"),
        }
    else:  # Customer
        lead_info = {
            "full_name" : doc.customer_name or "",
            "company" : doc.customer_name or "",
            "website": doc.website or kwargs.get('website'),
            "country" : kwargs.get("country"),
            "city" : kwargs.get("city"),
            "state" : kwargs.get("state"),
            "territory" : doc.territory or kwargs.get("territory"),
        }
        
    # get prompt template from settings
    setting = frappe.get_single("Lead Followup Setting")
    company_research_service = AgentService(setting.company_research_agent)

    result = company_research_service.invoke(**lead_info)

    if party_type == "Lead":
        doc.company_research = result
    elif party_type == "Customer":
        doc.customer_details = result
    doc.save()
    return result

def research_person(party_type:str,party_name:str,contact_name:str) -> str:
    """Research about a person using internal data or fallback to Perplexity."""
    contact = frappe.get_doc("Contact", {"name": contact_name})
    doc = frappe.get_doc(party_type, {"name": party_name})
    lead_info = {}
    if party_type == "Lead":
        lead_info = {
            "website" : doc.website or "",
            "country" : doc.country or "",
            "city" : doc.city or "",
            "territory" : doc.territory or "",
        }
    else:  # Customer
        lead_info = {
            "website" : doc.website or "",
            "country" : getattr(doc, "country", "") or "",
            "city" : getattr(doc, "city", "") or "",
            "territory" : getattr(doc, "territory", "") or "",
        }
    lead_info.update({
        "company" : contact.company_name or "",
        "full_name": f"{contact.first_name} {contact.middle_name} {contact.last_name}"
    })
    
    setting = frappe.get_single("Lead Followup Setting")
    person_research_service = AgentService(setting.person_research_agent)
    result = person_research_service.invoke(**lead_info)
    
    contact.person_research = result.research_summary
    contact.linkedin_profile = result.linkedin_profile if result.linkedin_profile.startswith("http") else None
    contact.save()
    
    return result