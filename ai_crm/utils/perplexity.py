import frappe
from litellm import completion


def research_lead(lead_name: str) -> str:
    """Research about a lead using internal data or fallback to Perplexity."""

    lead = frappe.get_doc("Lead", {"name": lead_name})
    if not lead:
        raise frappe.DoesNotExistError(f'Lead does not exist {lead_name}')

    lead_info = {
        "name": lead.lead_name or "",
        "full_name": f"{lead.salutation or ''} {lead.first_name or ''} {lead.last_name or ''}".strip(),
        "email": lead.email_id or "",
        "company": lead.company_name or "",
        "website": lead.website or "",
        "title": lead.title or "",
        "country": lead.country or "",
        "city": lead.city or "",
        "territory": lead.territory or "",
        "status": lead.status or "",
    }

    # get prompt template from settings
    setting = frappe.get_single("Lead Followup Setting")
    research_prompt = setting.lead_research_prompt or """
    Research about the company "{company}" (website: {website}), 
    and the lead "{full_name}" from {country} with email {email}.
    Provide sales-relevant insights, recent news, and potential opportunities.
    """
    perplexity_api_key =  setting.get_password("perplexity_api_key")
    query = research_prompt.format(**lead_info)

    response = completion(
        model="perplexity/sonar",
        api_key=perplexity_api_key,
        messages=[
            {"role": "system", "content": "You are a B2B sales research assistant."},
            {"role": "user", "content": query}
        ],
    )
    research_summery = response["choices"][0]["message"]["content"]
    lead.custom_additional_info = research_summery
    lead.save()
    return research_summery
