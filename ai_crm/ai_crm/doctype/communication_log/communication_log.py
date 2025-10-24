from typing import Dict
from finbyzai.ai.agent.agent_service import AgentService
import frappe
from frappe.model.document import Document, Optional
from frappe.utils import now_datetime, add_days, get_datetime
import json
import re

def get_followup_settings():
    return frappe.get_single("Followup Settings")

class CommunicationLog(Document):
    
    def validate(self):
        if self.party_type and self.party:
            if not frappe.db.exists(self.party_type, self.party):
                frappe.throw(f"{self.party_type} {self.party} does not exist")
        
        if self.sender_mail:
            if "@" in self.sender_mail:
                account_name = frappe.db.get_value("Email Account", {"email_id": self.sender_mail}, "name")
                if account_name:
                    self.sender_mail = account_name
                else:
                    frappe.throw(f"Email Account with email {self.sender_mail} does not exist")
            
            if not frappe.db.get_value("Email Account", self.sender_mail, "enable_outgoing"):
                frappe.throw(f"Email Account {self.sender_mail} is not enabled for outgoing emails")
class EmailAccountManager:
    @staticmethod
    def get_next_account_for_party(party_type, party):
        """Get next email account using round-robin logic - Returns Email Account NAME"""
        existing_log = frappe.db.get_value(
            "Communication Log",
            {"party_type": party_type, "party": party},
            "sender_mail"
        )
        
        if existing_log:
            if "@" in existing_log:
                account_name = frappe.db.get_value("Email Account", {"email_id": existing_log}, "name")
                return account_name if account_name else existing_log
            return existing_log
        
        settings = get_followup_settings()
        if not settings.enable_check: 
            frappe.throw("Follow-up automation is disabled in Followup Setting")
        
        if not settings.email_sending_schedule:
            frappe.throw("No email accounts configured in Followup Setting")
        
        available_accounts = []
        for row in settings.email_sending_schedule:
            if frappe.db.get_value("Email Account", row.email_account, "enable_outgoing"):
                available_accounts.append(row.email_account)
        
        if not available_accounts:
            frappe.throw("No enabled email accounts found in Followup Setting")
        
        last_log = frappe.get_all(
            "Communication Log",
            fields=["sender_mail"],
            order_by="creation desc",
            limit=1
        )
        
        if last_log and last_log[0].sender_mail:
            sender = last_log[0].sender_mail
            
            if "@" in sender:
                sender = frappe.db.get_value("Email Account", {"email_id": sender}, "name") or sender
            
            if sender in available_accounts:
                current_index = available_accounts.index(sender)
                next_index = (current_index + 1) % len(available_accounts)
                return available_accounts[next_index]
        
        return available_accounts[0]
class AIFollowupGenerator:
    def __init__(self, party_type, party_name):
        self.party_type = party_type
        self.party_name = party_name
        self.party_doc = frappe.get_doc(party_type, party_name)
        self.settings = get_followup_settings()
    
    def generate_emails(self):
        if not self.settings.enable_check:  
            frappe.throw("Follow-up automation is disabled")
        
        if not self.settings.dynamic_followup_generator:
            frappe.throw("Dynamic Follow-Up Generator not configured in Followup Setting")
        
        party_email = self.party_doc.get("email_id")
        if not party_email:
            frappe.msgprint(f"No email found for {self.party_type} {self.party_name}", indicator="orange")
            return []
        
        party_data = self._prepare_party_data()
        research_data = self._get_research_data()
        
        self._save_research_to_party(research_data)
        
        emails = self._generate_email_content(party_data, research_data)
        scheduled_emails = self._schedule_emails(emails)
        return scheduled_emails

    def _prepare_party_data(self):
        """Prepare party data from Lead/Customer document"""
        try:
            party_data = {
                'name': '',
                'company_name': '',
                'title': '',
                'website': '',
                'country': '',
                'status': '',
                'email': '',
                'mobile': '',
                'activity_summary': ''
            }
            
            if self.party_type == "Lead":
                doc = self.party_doc
                party_data = {
                    'name': f"{doc.get('salutation') or ''} {doc.get('first_name') or ''} {doc.get('last_name') or ''}".strip(),
                    'company_name': doc.get('company_name') or '',
                    'title': doc.get('job_title') or '',
                    'website': doc.get('website') or '',
                    'country': doc.get('country') or '',
                    'status': doc.get('status') or 'Lead',
                    'email': doc.get('email_id') or '',
                    'mobile': doc.get('mobile_no') or '',
                }
            elif self.party_type == "Customer":
                doc = self.party_doc
                party_data = {
                    'name': doc.get('customer_name') or '',
                    'company_name': doc.get('customer_name') or '',
                    'title': '',
                    'website': doc.get('website') or '',
                    'country': doc.get('country') or '',
                    'status': 'Customer',
                    'email': doc.get('email_id') or '',
                    'mobile': doc.get('mobile_no') or '',
                }
            
            party_data['activity_summary'] = self._get_activity_summary()
            return party_data
            
        except Exception as e:
            frappe.log_error(f"Error preparing party data: {str(e)}", "Prepare Party Data Error")
            return party_data

    def _get_activity_summary(self):
        """Get recent activities summary"""
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
            frappe.log_error(f"Error getting activity summary: {str(e)}", "Activity Summary Error")
            return "No recent activities"

    def _get_research_data(self):
        """Get research data from AI agents"""
        research_data = {
            "person": None,
            "company": None
        }
        
        # Get party information
        if self.party_type == "Lead":
            person_name = self.party_doc.get("first_name", "") + " " + (self.party_doc.get("last_name", "") or "")
            person_name = person_name.strip() or self.party_doc.get("lead_name") or self.party_name
            job_title = self.party_doc.get("job_title") or ""
        else:
            person_name = self.party_doc.get("customer_name") or self.party_name
            job_title = self.party_doc.get("designation") or ""
        
        company_name = self.party_doc.get("company_name") or ""
        
        # Person Research
        if self.settings.person_research and person_name and company_name:
            try:
                person_query = f"{person_name}"
                if job_title:
                    person_query += f", {job_title}"
                if company_name:
                    person_query += f" at {company_name}"
                
                frappe.logger().info(f"Starting Person Research for: {person_query}")
                
                person_research = self._call_ai_agent(
                    self.settings.person_research, 
                    person_query
                )
                
                if person_research:
                    research_data["person"] = person_research
                    frappe.logger().info(f"Person research completed successfully")
                    
            except Exception as e:
                error_msg = str(e)
                frappe.log_error(
                    f"Person research failed for {person_name}:\n{error_msg}\n{frappe.get_traceback()}", 
                    "Person Research Error"
                )
        
        # Company Research  
        if self.settings.company_research and company_name:
            try:
                company_query = company_name
                industry = self.party_doc.get("industry")
                if industry:
                    company_query += f" - {industry} industry"
                
                frappe.logger().info(f"Starting Company Research for: {company_query}")
                
                company_research = self._call_ai_agent(
                    self.settings.company_research,
                    company_query
                )
                
                if company_research:
                    research_data["company"] = company_research
                    frappe.logger().info(f"Company research completed successfully")
                    
            except Exception as e:
                error_msg = str(e)
                frappe.log_error(
                    f"Company research failed for {company_name}:\n{error_msg}\n{frappe.get_traceback()}", 
                    "Company Research Error"
                )
        
        frappe.logger().info(f"Research Data Summary: Person={'✓' if research_data['person'] else '✗'}, Company={'✓' if research_data['company'] else '✗'}")
        
        return research_data

    def _call_ai_agent(self, agent_name, query):
        """Call AI Agent - preserve Pydantic objects"""
        try:
            frappe.logger().info(f"Calling AI Agent: {agent_name}")
            
            if not frappe.db.exists("AI Agent", agent_name):
                frappe.logger().error(f"AI Agent '{agent_name}' does not exist!")
                return None
            
            agent_doc = frappe.get_doc("AI Agent", agent_name)
            
            response = None
            methods_to_try = ['test_agent', 'run_agent', 'execute']
            
            for method_name in methods_to_try:
                if hasattr(agent_doc, method_name):
                    try:
                        frappe.logger().info(f"Trying method: {method_name}")
                        method = getattr(agent_doc, method_name)
                        response = method(input=query)
                        frappe.logger().info(f"Method {method_name} succeeded")
                        break
                    except Exception as e:
                        frappe.logger().error(f"Method {method_name} failed: {str(e)}")
                        continue
            
            if not response:
                try:
                    frappe.logger().info("Trying frappe.call method")
                    response = frappe.call('raven.api.agent.run', agent=agent_name, prompt=query)
                except Exception as e:
                    frappe.logger().error(f"frappe.call failed: {str(e)}")
            
            if response:
                frappe.logger().info(f"Raw response type: {type(response)}")
                frappe.logger().info(f"Raw response has 'emails': {hasattr(response, 'emails')}")
                
                # FOR EMAIL GENERATION AGENT: Don't parse, return as-is to preserve Pydantic structure
                if agent_name == self.settings.dynamic_followup_generator:
                    frappe.logger().info("Email generation agent - returning raw response")
                    return response
                else:
                    # For research agents, parse normally
                    frappe.logger().info("Research agent - parsing response")
                    return self._parse_agent_response(response)
            else:
                frappe.logger().error("No response from any method")
                return None
                
        except Exception as e:
            frappe.log_error(f"AI Agent call failed: {str(e)}\n{frappe.get_traceback()}", "AI Agent Call Error")
            return None
    def _parse_agent_response(self, response):
        """Parse AI agent response"""
        try:
            if not response:
                return None
            
            if isinstance(response, dict):
                if 'response' in response:
                    response = response['response']
                
                if hasattr(response, '__dict__'):
                    return response.__dict__
                
                return response
            
            if isinstance(response, str):
                response = response.strip()
                
                if '```json' in response:
                    response = response.split('```json')[1].split('```')[0].strip()
                elif '```' in response:
                    response = response.split('```')[1].split('```')[0].strip()
                
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    return response
            
            if hasattr(response, '__dict__'):
                return response.__dict__
            
            return response
            
        except Exception as e:
            frappe.logger().error(f"Error parsing agent response: {str(e)}")
            return None

    def _save_research_to_party(self, research_data):
        """Save research data back to the Lead/Customer record as plain text"""
        try:
            doc_updated = False
            
            if research_data.get("company"):
                company_data = research_data["company"]
                
                if isinstance(company_data, dict):
                    company_text = self._format_company_research_text(company_data)
                else:
                    company_text = str(company_data)
                
                if hasattr(self.party_doc, 'company_research'):
                    self.party_doc.company_research = company_text
                    doc_updated = True
                    frappe.logger().info("Company research saved as text to company_research field")
                else:
                    frappe.logger().warning("company_research field not found")
            
            if research_data.get("person"):
                person_data = research_data["person"]
                
                if isinstance(person_data, dict):
                    person_text = self._format_person_research_text(person_data)
                else:
                    person_text = str(person_data)
                
                if hasattr(self.party_doc, 'person_research'):
                    self.party_doc.person_research = person_text
                    doc_updated = True
                    frappe.logger().info("Person research saved as text to person_research field")
                else:
                    alternative_fields = ['person_research', 'personal_research', 'research_data', 'notes']
                    field_found = False
                    
                    for field_name in alternative_fields:
                        if hasattr(self.party_doc, field_name):
                            setattr(self.party_doc, field_name, person_text)
                            doc_updated = True
                            frappe.logger().info(f"Person research saved as text to {field_name} field")
                            field_found = True
                            break
                    
                    if not field_found:
                        frappe.logger().warning("No person research field found")
            
            if doc_updated:
                self.party_doc.save()
                frappe.db.commit()
                frappe.logger().info("Research data saved successfully as text")
                frappe.msgprint(f"Research data saved for {self.party_doc.get('lead_name') or self.party_doc.get('customer_name')}", alert=True)
            else:
                frappe.logger().warning("No research data was saved")
                
        except Exception as e:
            error_msg = f"Error saving research data: {str(e)}"
            frappe.log_error(error_msg, "Research Save Error")
            frappe.msgprint(error_msg, alert=True)

    def _format_company_research_text(self, company_data):
        """Format company research data as plain text"""
        text_lines = []
        text_lines.append("COMPANY RESEARCH SUMMARY")
        text_lines.append("=" * 50)
        
        if company_data.get('company_overview') and company_data['company_overview'] != 'N/A':
            text_lines.append(f"Overview: {company_data['company_overview']}")
        
        if company_data.get('industry') and company_data['industry'] != 'N/A':
            text_lines.append(f"Industry: {company_data['industry']}")
        
        if company_data.get('headquarters') and company_data['headquarters'] != 'N/A':
            text_lines.append(f"Headquarters: {company_data['headquarters']}")
        
        if company_data.get('website_url') and company_data['website_url'] != 'N/A':
            text_lines.append(f"Website: {company_data['website_url']}")
        
        if company_data.get('company_size') and company_data['company_size'] != 'N/A':
            text_lines.append(f"Company Size: {company_data['company_size']}")
        
        if company_data.get('founded_year') and company_data['founded_year'] != 'N/A':
            text_lines.append(f"Founded: {company_data['founded_year']}")
        
        for key, value in company_data.items():
            if key not in ['company_overview', 'industry', 'headquarters', 'website_url', 'company_size', 'founded_year']:
                if value and value != 'N/A':
                    formatted_key = key.replace('_', ' ').title()
                    text_lines.append(f"{formatted_key}: {value}")
        
        text_lines.append(f"\nResearch Date: {now_datetime().strftime('%Y-%m-%d %H:%M')}")
        
        return "\n".join(text_lines)

    def _format_person_research_text(self, person_data):
        """Format person research data as plain text"""
        text_lines = []
        text_lines.append("PERSON RESEARCH SUMMARY")
        text_lines.append("=" * 50)
        
        if person_data.get('linkedin_profile') and person_data['linkedin_profile'] != 'N/A':
            text_lines.append(f"LinkedIn: {person_data['linkedin_profile']}")
        
        if person_data.get('research_summary') and person_data['research_summary'] != 'N/A':
            text_lines.append(f"Summary: {person_data['research_summary']}")
        
        if person_data.get('current_position') and person_data['current_position'] != 'N/A':
            text_lines.append(f"Current Position: {person_data['current_position']}")
        
        if person_data.get('experience') and person_data['experience'] != 'N/A':
            text_lines.append(f"Experience: {person_data['experience']}")
        
        if person_data.get('education') and person_data['education'] != 'N/A':
            text_lines.append(f"Education: {person_data['education']}")
        
        for key, value in person_data.items():
            if key not in ['linkedin_profile', 'research_summary', 'current_position', 'experience', 'education']:
                if value and value != 'N/A':
                    formatted_key = key.replace('_', ' ').title()
                    text_lines.append(f"{formatted_key}: {value}")
        
        text_lines.append(f"\nResearch Date: {now_datetime().strftime('%Y-%m-%d %H:%M')}")
        
        return "\n".join(text_lines)

    def _get_email_signature(self):
        """Get email signature"""
        try:
            sender_mail = EmailAccountManager.get_next_account_for_party(self.party_type, self.party_name)
            
            if sender_mail:
                email_account = frappe.get_doc("Email Account", sender_mail)
                
                if hasattr(email_account, 'signature') and email_account.signature:
                    return email_account.signature
                
                if hasattr(email_account, 'add_signature') and email_account.add_signature:
                    user_signature = frappe.db.get_value("User", frappe.session.user, "email_signature")
                    if user_signature:
                        return user_signature
            
            user_signature = frappe.db.get_value("User", frappe.session.user, "email_signature")
            return user_signature
            
        except Exception as e:
            frappe.log_error(f"Error getting email signature: {str(e)}", "Signature Error")
            return None

    def _append_signature_to_email(self, email_content, signature):
        """Append signature to email"""
        try:
            if not signature:
                return email_content
            
            email_content = str(email_content).strip()
            signature = str(signature).strip()
            
            if not ('<p>' in signature or '<div>' in signature or '<br>' in signature):
                signature = f"<p>{signature}</p>"
            
            signature_html = f"<br><br>{signature}"
            return email_content + signature_html
            
        except Exception as e:
            frappe.log_error(f"Error appending signature: {str(e)}", "Signature Error")
            return email_content

    def _generate_email_content(self, party_data, research_data):
        """Generate email content using AI"""
        try:
            agent_name = self.settings.dynamic_followup_generator
            agent_doc = frappe.get_doc("AI Agent", agent_name)
            research_context = self._build_research_context(research_data)
            
            query = f"""Generate exactly 3 professional follow-up emails in valid JSON format.

PROSPECT DETAILS:
Name: {party_data['name']}
Company: {party_data['company_name']}
Title: {party_data['title']}
Website: {party_data['website']}
Country: {party_data['country']}
Status: {party_data['status']}
Email: {party_data['email']}
Mobile: {party_data['mobile']}

RECENT ACTIVITIES:
{party_data['activity_summary']}

{research_context}

REQUIREMENTS:
Create 3 personalized, professional follow-up emails:
1. First follow-up (introduction/initial outreach)
2. Second follow-up (gentle reminder with value add)  
3. Third follow-up (final nudge with call-to-action)

Each email must:
- Be professional and polite
- Use proper HTML formatting with <p> tags
- Include a personalized greeting
- Be tailored to the prospect's information
- NOT include a signature

RETURN ONLY THIS EXACT JSON FORMAT (no markdown, no extra text):
{{"emails": [{{"subject": "Subject Line 1", "body": "<p>Email body with HTML tags...</p>"}}, {{"subject": "Subject Line 2", "body": "<p>Email body with HTML tags...</p>"}}, {{"subject": "Subject Line 3", "body": "<p>Email body with HTML tags...</p>"}}]}}"""
            
            response = None
            if hasattr(agent_doc, 'test_agent'):
                response = agent_doc.test_agent(input=query)
            elif hasattr(agent_doc, 'run_agent'):
                response = agent_doc.run_agent(input=query)
            elif hasattr(agent_doc, 'execute'):
                response = agent_doc.execute(input=query)
            else:
                response = frappe.call('raven.api.agent.run', agent=agent_name, prompt=query)
            
            emails = self._parse_email_response(response)
            
            if emails and len(emails) >= 3:
                return emails[:3]
            elif emails and len(emails) > 0:
                return emails
            else:
                return self._get_fallback_emails(party_data)
            
        except Exception as e:
            error_msg = str(e)
            frappe.log_error(f"AI Agent Error: {error_msg}", "AI Agent Exception")
            return self._get_fallback_emails(party_data)
    
    def _build_research_context(self, research_data):
        """Build research context"""
        context = ""
        
        if research_data.get("person"):
            person_info = research_data["person"]
            context += "\nPERSON RESEARCH:\n"
            if isinstance(person_info, dict):
                context += f"  • LinkedIn: {person_info.get('linkedin_profile', 'N/A')}\n"
                summary = person_info.get('research_summary', 'N/A')
                if summary and summary != 'N/A':
                    summary_short = summary[:500] + "..." if len(summary) > 500 else summary
                    context += f"  • Summary: {summary_short}\n"
            else:
                context += f"  {person_info}\n"
        
        if research_data.get("company"):
            company_info = research_data["company"]
            context += "\nCOMPANY RESEARCH:\n"
            if isinstance(company_info, dict):
                context += f"  • Overview: {company_info.get('company_overview', 'N/A')}\n"
                context += f"  • Industry: {company_info.get('industry', 'N/A')}\n"
                context += f"  • Headquarters: {company_info.get('headquarters', 'N/A')}\n"
                context += f"  • Website: {company_info.get('website_url', 'N/A')}\n"
            else:
                context += f"  {company_info}\n"
        
        return context if context else "No research data available."

    def _parse_email_response(self, response):
        """Parse email response"""
        try:
            if isinstance(response, dict) and 'response' in response:
                response_data = response['response']
                if hasattr(response_data, 'emails'):
                    return self._extract_pydantic_emails(response_data.emails)
                if isinstance(response_data, dict) and 'emails' in response_data:
                    return self._extract_emails(response_data['emails'])
            
            if isinstance(response, dict):
                if 'output' in response:
                    response = response['output']
                if isinstance(response, dict) and 'emails' in response:
                    return self._extract_emails(response['emails'])
            
            if hasattr(response, 'emails'):
                return self._extract_pydantic_emails(response.emails)
            
            response_str = json.dumps(response) if isinstance(response, dict) else str(response).strip()
            
            if not response_str:
                return []
            
            if '```json' in response_str:
                response_str = response_str.split('```json')[1].split('```')[0].strip()
            elif '```' in response_str:
                response_str = response_str.split('```')[1].split('```')[0].strip()
            
            json_match = re.search(r'\{[\s\S]*?"emails"[\s\S]*?\][\s\S]*?\}', response_str)
            if json_match:
                response_str = json_match.group(0)
            
            data = json.loads(response_str)
            
            if 'emails' in data and isinstance(data['emails'], list):
                return self._extract_emails(data['emails'])
            
            return []
            
        except Exception as e:
            frappe.log_error(f"Email parse error: {str(e)}", "Email Parse Error")
            return []

    def _extract_pydantic_emails(self, emails_list):
        """Extract emails from Pydantic objects"""
        formatted_emails = []
        try:
            for email_obj in emails_list:
                subject = getattr(email_obj, 'subject', 'Follow-up')
                body = getattr(email_obj, 'body', '') or getattr(email_obj, 'content', '')
                
                if body:
                    body = body.strip()
                    if not ('<p>' in body or '<div>' in body or '<html>' in body):
                        body = body.replace('\n', '<br>')
                        body = f"<p>{body}</p>"
                    
                    formatted_emails.append({
                        "subject": str(subject).strip(),
                        "content": body
                    })
            
            return formatted_emails
        except Exception as e:
            frappe.log_error(f"Pydantic email extraction error: {str(e)}", "Pydantic Email Error")
            return []

    def _extract_emails(self, emails_list):
        formatted_emails = []
        try:
            for email in emails_list:
                if isinstance(email, dict):
                    subject = email.get('subject', 'Follow-up')
                    body = email.get('body', '') or email.get('content', '')
                    
                    if body:
                        if not ('<p>' in body or '<div>' in body):
                            body = f"<p>{body}</p>"
                        
                        formatted_emails.append({
                            "subject": subject,
                            "content": body
                        })
            
            return formatted_emails
        except Exception as e:
            frappe.log_error(f"Email extraction error: {str(e)}", "Email Extraction Error")
            return []
    def _schedule_emails(self, emails):
        """Schedule emails with proper timing"""
        try:
            if not emails:
                return []
            
            scheduled_emails = []
            current_time = now_datetime()
            
            for i, email in enumerate(emails):
                if i == 0:
                    schedule_time = current_time
                elif i == 1:
                    schedule_time = add_days(current_time, 1)
                else:
                    schedule_time = add_days(current_time, 3)
                scheduled_email = {
                    "subject": email.get("subject", "Follow-up"),
                    "content": email.get("content", ""),
                    "scheduled_time": schedule_time,
                    "status": "Scheduled" if i > 0 else "Pending"
                }
                scheduled_emails.append(scheduled_email)
            
            return scheduled_emails
            
        except Exception as e:
            frappe.log_error(f"Error scheduling emails: {str(e)}", "Email Scheduling Error")

    def _get_fallback_emails(self, party_data):
        name = party_data.get('name', 'there')
        company = party_data.get('company_name', 'your company')
        
        return [
            {
                "subject": f"Introduction - {company}",
                "content": f"<p>Hi {name},</p><p>I hope this email finds you well. I wanted to reach out regarding {company}.</p><p>Best regards</p>"
            },
            {
                "subject": f"Following up - {company}",
                "content": f"<p>Hi {name},</p><p>I wanted to follow up on my previous email regarding {company}.</p><p>Best regards</p>"
            },
            {
                "subject": f"Final follow-up - {company}",
                "content": f"<p>Hi {name},</p><p>This is my final attempt to connect with you regarding {company}.</p><p>Best regards</p>"
            }
        ]
class CommunicationLogManager:
        @staticmethod
        def create_or_update_log(party_type, party_name, sender_mail, emails):
            if not emails:
                frappe.msgprint("No emails to schedule", indicator="orange")
                return None
            
            existing_log = frappe.db.get_value(
                "Communication Log",
                {"party_type": party_type, "party": party_name}
            )
            
            current_time = now_datetime()
            
            formatted_emails = []
            for i, email in enumerate(emails):
                if i == 0:
                    scheduled_time = current_time
                elif i == 1:
                    scheduled_time = add_days(current_time, 1)
                else:
                    scheduled_time = add_days(current_time, 3)
                
                formatted_email = {
                    "subject": email.get("subject", "Follow-up"),
                    "status": "Unsent",
                    "content": email.get("content", ""),
                    "time": scheduled_time 
                }
                formatted_emails.append(formatted_email)
            
            if existing_log:
                doc = frappe.get_doc("Communication Log", existing_log)
                doc.communication_email = [e for e in doc.communication_email if e.status != "Unsent"]
                for email in formatted_emails:
                    doc.append("communication_email", email)
                doc.save()
                frappe.msgprint(f"Updated Communication Log: {doc.name}", indicator="green")
            else:
                doc = frappe.get_doc({
                    "doctype": "Communication Log",
                    "party_type": party_type,
                    "party": party_name,
                    "sender_mail": sender_mail,
                    "creation_source": "Auto Generated",
                    "communication_email": formatted_emails
                })
                doc.insert()
                frappe.msgprint(f"Created Communication Log: {doc.name}", indicator="green")
            return doc.name
def generate_followups_on_party_activity(doc, method):
    try:
        settings = get_followup_settings()
        if not settings.enable_check:
            frappe.logger().info(f"Follow-up automation disabled")
            return
        if method != "after_insert":
            return
        
        if not doc.get("email_id"):
            frappe.msgprint("No email found, skipping follow-up generation", indicator="orange")
            return
        
        sender_mail = EmailAccountManager.get_next_account_for_party(doc.doctype, doc.name)
        generator = AIFollowupGenerator(doc.doctype, doc.name)
        emails = generator.generate_emails()
        
        if not emails:
            frappe.msgprint("No emails generated", indicator="orange")
            return
        
        log_name = CommunicationLogManager.create_or_update_log(
            doc.doctype,
            doc.name,
            sender_mail,
            emails
        )
        
        if log_name:
            frappe.msgprint(
                f"✓ {len(emails)} follow-up emails scheduled!",
                indicator="green",
                title="Follow-ups Scheduled"
            )
        
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"Follow-up generation error: {error_msg}\n{frappe.get_traceback()}", "Follow-up Error")
        frappe.msgprint(f"Error: {error_msg}", indicator="red")

@frappe.whitelist()
def regenerate_emails_for_log(log_name):
    try:
        log = frappe.get_doc("Communication Log", log_name)
        log.reload()
        
        existing_emails = []
        for email in log.communication_email:
            if email.status != "Unsent":
                existing_emails.append(email)
        
        log.communication_email = []
        for email in existing_emails:
            log.append("communication_email", email)
        
        generator = AIFollowupGenerator(log.party_type, log.party)
        new_emails = generator.generate_emails()  
        for email in new_emails:
            log.append("communication_email", email)
        
        log.flags.ignore_version_mismatch = True
        log.save(ignore_version=True)
        frappe.db.commit()
        
        frappe.msgprint(f"Regenerated {len(new_emails)} emails and updated research data", indicator="green")
        
        return {"count": len(new_emails), "log_name": log.name}
        
    except frappe.exceptions.TimestampMismatchError:
        frappe.db.rollback()
        frappe.throw("Document was modified by another user. Please refresh and try again.")
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Regenerate Error")
        frappe.throw(str(e))