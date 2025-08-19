import frappe
from ai_crm.utils.perplexity import research_company, research_person
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from frappe.core.doctype.communication.email import make

class EmailOutput(BaseModel):
    subject: str = Field(description="Subject line of the email")
    body: str = Field(description="Email body text")

def run_followup_job():
    """Background job to analyze opportunity-related activities and draft follow-up emails"""
    setting = frappe.get_single("Lead Followup Setting")
    if not setting.is_enable:
        return

    followups = get_opportunity_followups(setting.days_since_last_activity) or []

    for row in followups:
        party = {
            "party_type": row.get("party_type"),
            "name": row.get("party_name"),
            "lead_name": row.get("customer_name"),
            "email_id": row.get("email"),
            "company_name": row.get("company"),
            "status": row.get("opportunity_status"),
            "custom_person_research": row.get("custom_person_research"),
            "customer_details": row.get("customer_details"),
            "contact_name": row.get("contact_name"),
            "country":row.get("country"),
            "city":row.get("city"),
            "state":row.get("state"),
        }

        if not party.get("custom_person_research"):
            research_summary = research_person(party.get("party_type"),party.get("name"),party.get("contact_name"))
            party["custom_person_research"] = research_summary
            
        if not party.get("customer_details"):
            research_summary = research_company(
                party.get("party_type"),
                party.get("name"),
                country=party.get("country"),
                city=party.get("city"),
                state=party.get("state")
            )
            party["customer_details"] = research_summary

        activities = get_party_activities(party.get("party_type"), party.get("name"))

        activity_summary = "\n".join(
            [f"- {a.get('type')}: {a.get('subject')} on {a.get('date')}" for a in activities]
        )

        email_draft = draft_email(party, activity_summary)
        # Save draft in Communication or custom doctype
        send_email_draft(party, email_draft)

    
def get_opportunity_followups(days_since_last_activity=5):
    """Fetch parties with active Opportunity and no recent communication within the given days"""
    lead_opportunity  = frappe.db.sql("""
        SELECT DISTINCT
            l.name AS party_name,
            "Lead" as party_type,
            l.lead_name AS customer_name,
            COALESCE(ct.email_id, l.email_id) AS email,
            l.company_name AS company,
            l.custom_company_research AS customer_details,
            o.name AS opportunity_id,
            o.status AS opportunity_status,
            o.country,
            o.city,
            o.state,
            comm.last_activity,
            ct.custom_person_research AS custom_person_research,
            ct.name AS contact_name
        FROM `tabLead` l
        INNER JOIN `tabOpportunity` o 
            ON o.opportunity_from = 'Lead' AND o.party_name = l.name
        LEFT JOIN `tabContact` ct
            ON ct.name = o.contact_person
        LEFT JOIN (
            SELECT reference_name, MAX(communication_date) AS last_activity
            FROM `tabCommunication`
            WHERE reference_doctype = 'Lead'
            GROUP BY reference_name
        ) comm ON comm.reference_name = l.name
        WHERE o.status IN ('Open','Quotation','Replied')
            AND (comm.last_activity IS NULL OR comm.last_activity < DATE_SUB(CURDATE(), INTERVAL %s DAY))
            AND l.status NOT IN ('Converted', 'Do Not Contact')
        LIMIT 50
        """, (days_since_last_activity,), as_dict=True)
        
    customers_opportunity = frappe.db.sql("""
        SELECT DISTINCT
            c.name AS party_name,
            "Customer" as party_type,
            c.customer_name AS customer_name,
            COALESCE(ct.email_id, c.email_id) AS email,
            c.customer_group AS company,
            o.name AS opportunity_id,
            o.status AS opportunity_status,
            o.country,
            o.city,
            o.state,
            comm.last_activity,
            ct.custom_person_research AS custom_person_research,
            c.customer_details AS customer_details,
            ct.name AS contact_name
        FROM `tabCustomer` c
        INNER JOIN `tabOpportunity` o 
            ON o.opportunity_from = 'Customer' AND o.party_name = c.name
        LEFT JOIN `tabContact` ct
            ON ct.name = o.contact_person
        LEFT JOIN (
            SELECT reference_name, MAX(communication_date) AS last_activity
            FROM `tabCommunication`
            WHERE reference_doctype = 'Customer'
            GROUP BY reference_name
        ) comm ON comm.reference_name = c.name
        WHERE o.status IN ('Open','Quotation','Replied')
            AND (comm.last_activity IS NULL OR comm.last_activity < DATE_SUB(CURDATE(), INTERVAL %s DAY))
        LIMIT 50
    """, (days_since_last_activity,), as_dict=True)
    result = [*customers_opportunity,*lead_opportunity]
    return result




def get_lead_activities(lead_name):
    """Fetch recent activities (Communication/Activity/Notes) linked to Lead"""
    activities = []

    comms = frappe.get_all(
        "Communication",
        filters={"reference_doctype": "Lead", "reference_name": lead_name},
        fields=["subject", "content", "communication_date as date", "'Email' as type"],
        order_by="communication_date desc",
        limit=5,
    )
    activities.extend(comms)

    notes = frappe.get_all(
        "CRM Note",
        filters={"parent": lead_name},
        fields=["note as subject", "creation as date", "'Note' as type"],
        order_by="creation desc",
        limit=5,
    )
    activities.extend(notes)

    return activities

def get_party_activities(party_type, party_name):
    """Fetch recent activities for a given party type (Lead/Customer) and name"""
    activities = []

    comms = frappe.get_all(
        "Communication",
        filters={"reference_doctype": party_type, "reference_name": party_name},
        fields=["subject", "content", "communication_date as date", "'Email' as type"],
        order_by="communication_date desc",
        limit=5,
    )
    activities.extend(comms)

    notes = frappe.get_all(
        "CRM Note",
        filters={"parent": party_name},
        fields=["note as subject", "creation as date", "'Note' as type"],
        order_by="creation desc",
        limit=5,
    )
    activities.extend(notes)

    return activities

def draft_email(lead, activity_summary):
    setting = frappe.get_single("Lead Followup Setting")
    draft_prompt = setting.get("email_creation_prompt")
    system_instruction = setting.email_system_instruction or "You are a helpful assistant drafting business follow-up emails."
    research_text = f"\nAdditional Research:\n{lead.get('custom_person_research')}" if lead.get("custom_person_research") else ""

    query = draft_prompt.format(
        lead_name=lead.get("lead_name", ""),
        company_name=lead.get("company_name", ""),
        title=lead.get("title", ""),
        website=lead.get("website", ""),
        country=lead.get("country", ""),
        status=lead.get("status", ""),
        email=lead.get("email_id", ""),
        custom_company_research=lead.get("custom_company_research"),
        custom_person_research=lead.get("custom_person_research"),
        activity_summary=activity_summary or "No recent activities.",
        research_text=research_text
    )
    
    llm_doc = frappe.get_doc("LLM",setting.get('llm'))
    llm = llm_doc.llm
    output_parser = PydanticOutputParser(pydantic_object=EmailOutput)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "{system_instruction}\n\n{format_instructions}"),
        ("human", "{query}\n")
    ])

    chain = prompt | llm | output_parser

    result = chain.invoke({
        "system_instruction": system_instruction,
        "query": query,
        "format_instructions": output_parser.get_format_instructions(),
    })
    if result:    
        return {
            "subject": result.subject,
            "body": result.body
        }
    return None

def send_email_draft(party, email_draft):
    """Save draft in Communication as Draft type"""
    if not email_draft:
        return
    try:
        make(
            recipients=party.get("email_id"),
            subject=email_draft.get('subject'),
            content=email_draft.get('body'),
            doctype=party.get("party_type", "Lead"),
            name=party.get("name"),
            send_email=True
        )
    except frappe.OutgoingEmailError as e:
        frappe.log_error('Lead Auto Followup error',e)