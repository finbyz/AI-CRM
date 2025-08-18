import frappe
import otto.lib as otto
import frappe
from ai_crm.utils.perplexity import research_lead


def format_section(items, fields):
    """Helper to format dict list into readable string for LLM"""
    if not items:
        return "None"
    lines = []
    for i, item in enumerate(items, 1):
        details = ", ".join([f"{f}: {item.get(f)}" for f in fields if f in item])
        lines.append(f"{i}. {details}")
    return "\n".join(lines)


def run_followup_job():
    """Background job to analyze lead activities and draft follow-up emails"""
    setting = frappe.get_single("Lead Followup Setting")
    if not setting.is_enable: return
    leads = get_leads_for_followup(setting.days_since_last_activity)

    for lead in leads:
        if not lead.custom_additional_info:
            research_summary = research_lead(lead.name)
            lead.custom_additional_info = research_summary
            
        activities = get_lead_activities(lead.name)

        activity_summary = "\n".join(
            [f"- {a.get('type')}: {a.get('subject')} on {a.get('date')}" for a in activities]
        )

        email_draft = draft_email(lead, activity_summary)
        # Save draft in Communication or custom doctype
        save_email_draft(lead, email_draft)


def get_leads_for_followup(days_since_last_activity):
    """Fetch leads that have no communication in last 3 days"""
    return frappe.db.sql("""
        SELECT l.name, l.lead_name, l.email_id, l.company_name, l.status, l.custom_additional_info
        FROM `tabLead` l
        LEFT JOIN (
            SELECT reference_name, MAX(communication_date) as last_activity
            FROM `tabCommunication`
            WHERE reference_doctype = 'Lead'
            GROUP BY reference_name
        ) c ON c.reference_name = l.name
        WHERE l.status NOT IN ('Converted', 'Do Not Contact', 'Opportunity')
          AND (c.last_activity IS NULL OR c.last_activity < DATE_SUB(CURDATE(), INTERVAL %s DAY))
        LIMIT 50
    """,(days_since_last_activity,), as_dict=True)


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

def draft_email(lead, activity_summary):
    """Use otto + research context to generate a follow-up email draft"""
    setting = frappe.get_single("Lead Followup Setting")
    
    draft_prompt = setting.get("email_creation_prompt") or """
    Lead Name: {lead_name}
    Company: {company_name}
    Title: {title}
    Website: {website}
    Country: {country}
    Status: {status}
    Email: {email}

    Recent Activities:
    {activity_summary}

    {research_text}

    Please draft a polite, professional, and personalized follow-up email 
    that acknowledges the lead's context and encourages next steps.
    """
    email_system_instruction = setting.email_system_instruction or "You are a helpful assistant drafting business follow-up emails."
    email_system_instruction += """Always return the output strictly as a JSON object in the following format:

    {
        "subject": "<a clear, concise subject line>",
        "body": "<a well-formatted, polite, and professional email body with paragraphs. Do not include markdown or escape characters.>"
    }

    Do not include any text outside the JSON object.
    """
    research_text = f"\nAdditional Research:\n{lead.get('custom_additional_info')}" if lead.get("custom_additional_info") else ""

    query = draft_prompt.format(
        lead_name=lead.get("lead_name", ""),
        company_name=lead.get("company_name", ""),
        title=lead.get("title", ""),
        website=lead.get("website", ""),
        country=lead.get("country", ""),
        status=lead.get("status", ""),
        email=lead.get("email_id", ""),
        activity_summary=activity_summary or "No recent activities.",
        research_text=research_text
    )
    response = otto.quick_query(
        model=otto.get_model(provider="OpenAI",size="Small"),
        instruction=email_system_instruction,
        query=query,
        stream=False,
    )
    if response:
        response = frappe.parse_json(response[0].get('text'))
        if response.get("subject") and response.get('body'):
            return {
                "subject":response.get("subject"),
                "body":response.get("body")
            }
    return None


def save_email_draft(lead, email_draft):
    """Save draft in Communication as Draft type"""
    if not email_draft:
        return

    comm = frappe.get_doc({
        "doctype": "Communication",
        "communication_type": "Communication",
        "communication_medium": "Email",
        "subject": email_draft.get('subject'),
        "content": email_draft.get('body'),
        "status": "Draft",
        "sent_or_received": "Sent",
        "recipients": lead.get("email_id"),
        "reference_doctype": "Lead",
        "reference_name": lead.get("name"),
    })
    comm.insert(ignore_permissions=True)
    frappe.db.commit()

