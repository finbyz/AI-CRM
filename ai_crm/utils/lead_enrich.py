import frappe
from frappe.utils import now_datetime, add_days
import json
import re

class AIFollowupGenerator:
    """AI-powered follow-up email generator"""
    
    def __init__(self, party_type, party_name):
        self.party_type = party_type
        self.party_name = party_name
        self.party_doc = frappe.get_doc(party_type, party_name)
        self.settings = frappe.get_single("Followup Settings")
    
    def generate_emails(self):
        """Main method to generate follow-up emails"""
        
        if not self.settings.enable:
            frappe.throw("Follow-up automation is disabled")
        
        if not self.settings.dynamic_followup_generator:
            frappe.throw("Dynamic Follow-Up Generator not configured in Followup Settings")
        
        party_email = self.party_doc.get("email_id")
        if not party_email:
            frappe.msgprint(f"No email found for {self.party_type} {self.party_name}", indicator="orange")
            return []
        
        frappe.logger().info(f" Preparing data for {self.party_name}...")
        
        # Prepare data
        party_data = self._prepare_party_data()
        research_text = self._get_research_data()
        
        # Generate emails
        frappe.logger().info(f"Generating emails using AI...")
        emails = self._generate_email_content(party_data, research_text)
        
        # Schedule emails
        frappe.logger().info(f"Scheduling {len(emails)} emails...")
        scheduled_emails = self._schedule_emails(emails)
        
        return scheduled_emails
    
    def _prepare_party_data(self):
        """Prepare party data for AI"""
        data = {
            "name": self.party_doc.get("lead_name") or self.party_doc.get("customer_name") or self.party_name,
            "company_name": self.party_doc.get("company_name") or "",
            "title": self.party_doc.get("designation") or self.party_doc.get("salutation") or "",
            "website": self.party_doc.get("website") or "",
            "country": self.party_doc.get("country") or "",
            "status": self.party_doc.get("status") or "",
            "email": self.party_doc.get("email_id") or "",
            "mobile": self.party_doc.get("mobile_no") or self.party_doc.get("phone") or "",
            "activity_summary": self._get_activity_summary()
        }
        
        return data
    
    def _get_activity_summary(self):
        """Get recent activities for this party"""
        try:
            activities = frappe.get_all(
                "Communication",
                filters={
                    "reference_doctype": self.party_type,
                    "reference_name": self.party_name
                },
                fields=["subject", "content", "creation"],
                order_by="creation desc",
                limit=5
            )
            
            if not activities:
                return "No recent activities"
            
            summary = []
            for act in activities:
                summary.append(f"- {act.subject or 'Activity'} ({act.creation.strftime('%Y-%m-%d')})")
            
            return "\n".join(summary)
        except Exception as e:
            frappe.log_error(f"Error getting activity summary: {str(e)}")
            return "No recent activities"
    
    def _get_research_data(self):
        """Get research data from Person and Company research agents"""
        research_parts = []
        
        if self.settings.person_research:
            try:
                frappe.logger().info(f"Running Person Research...")
                person_research = self._call_ai_agent(
                    self.settings.person_research,
                    f"Research about {self.party_doc.get('lead_name') or self.party_doc.get('customer_name')} from {self.party_doc.get('company_name')}"
                )
                if person_research and person_research != "Research failed":
                    research_parts.append(f"Person Research:\n{person_research}")
                    frappe.logger().info(f" Person research completed")
            except Exception as e:
                frappe.log_error(f"Person research failed: {str(e)}", "Person Research Error")
        
        # Company research
        if self.settings.company_research:
            try:
                frappe.logger().info(f" Running Company Research...")
                company_research = self._call_ai_agent(
                    self.settings.company_research,
                    f"Research about company {self.party_doc.get('company_name')}"
                )
                if company_research and company_research != "Research failed":
                    research_parts.append(f"Company Research:\n{company_research}")
                    frappe.logger().info(f"Company research completed")
            except Exception as e:
                frappe.log_error(f"Company research failed: {str(e)}", "Company Research Error")
        
        return "\n\n".join(research_parts) if research_parts else ""
    
    def _call_ai_agent(self, agent_name, query):
        """Call AI Agent and return response"""
        try:
            agent = frappe.get_doc("AI Agent", agent_name)
            response = agent.run(query)
            return response
        except Exception as e:
            frappe.log_error(f"AI Agent '{agent_name}' failed: {str(e)}", "AI Agent Error")
            return "Research failed"
    
    def _generate_email_content(self, party_data, research_text):
        """Generate email content using Dynamic Follow-Up Generator AI Agent"""
        
        try:
            agent = frappe.get_doc("AI Agent", self.settings.dynamic_followup_generator)
            
            # Construct comprehensive prompt
            query = f"""Generate 3 professional follow-up emails for:

Name: {party_data['name']}
Company: {party_data['company_name']}
Title: {party_data['title']}
Website: {party_data['website']}
Country: {party_data['country']}
Status: {party_data['status']}
Email: {party_data['email']}
Mobile: {party_data['mobile']}
Recent Activities: {party_data['activity_summary']}

{research_text}

Please create 3 personalized, professional follow-up emails:
1. First follow-up (introduction/initial outreach)
2. Second follow-up (gentle reminder with value add)
3. Third follow-up (final nudge with call-to-action)

Each email should be:
- Professional and polite
- Personalized based on the information above
- HTML formatted
- Include proper greeting and signature

Return ONLY valid JSON in this exact format:
{{
  "emails": [
    {{"subject": "...", "body": "..."}},
    {{"subject": "...", "body": "..."}},
    {{"subject": "...", "body": "..."}}
  ]
}}"""
            
            response = agent.run(query)
            
            # Parse JSON response
            emails = self._parse_ai_response(response)
            
            if not emails or len(emails) == 0:
                # Fallback emails
                frappe.log_error("AI Agent did not generate emails, using fallback", "AI Email Generation")
                return self._get_fallback_emails(party_data)
            
            return emails
            
        except Exception as e:
            frappe.log_error(f"AI Agent execution failed: {str(e)}", "AI Agent Execution Error")
            # Return fallback emails instead of throwing error
            return self._get_fallback_emails(party_data)
    
    def _parse_ai_response(self, response):
        """Parse AI response to extract emails"""
        try:
            # Try direct JSON parse
            response_data = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                try:
                    response_data = json.loads(json_match.group(1))
                except:
                    pass
            else:
                # Try to find JSON anywhere in response
                json_match = re.search(r'\{.*"emails".*\}', response, re.DOTALL)
                if json_match:
                    try:
                        response_data = json.loads(json_match.group(0))
                    except:
                        return []
                else:
                    return []
        
        emails = response_data.get("emails", [])
        
        # Format emails
        formatted_emails = []
        for email in emails:
            formatted_emails.append({
                "subject": email.get("subject", "Follow-up"),
                "content": email.get("body", "") or email.get("content", "")
            })
        
        return formatted_emails
    
    def _get_fallback_emails(self, party_data):
        """Generate basic fallback emails if AI fails"""
        return [
            {
                "subject": f"Introduction - {party_data['company_name']}",
                "content": f"<p>Dear {party_data['name']},</p><p>I hope this email finds you well.</p><p>Best regards</p>"
            },
            {
                "subject": f"Following up - {party_data['company_name']}",
                "content": f"<p>Hi {party_data['name']},</p><p>Just following up on my previous email.</p><p>Best regards</p>"
            },
            {
                "subject": f"Quick check-in",
                "content": f"<p>Hello {party_data['name']},</p><p>Wanted to check if you had any questions.</p><p>Best regards</p>"
            }
        ]
    
    def _schedule_emails(self, emails):
        """Schedule emails based on settings"""
        scheduled = []
        
        mail_days = [
            self.settings.mail_1 or 1,
            self.settings.mail_2 or 3,
            self.settings.mail_3 or 5
        ]
        
        for i, email in enumerate(emails):
            days = mail_days[i] if i < len(mail_days) else (i + 1) * 2
            
            scheduled.append({
                "subject": email["subject"],
                "content": email["content"],
                "time": add_days(now_datetime(), days),
                "status": "Unsent"
            })
        
        return scheduled