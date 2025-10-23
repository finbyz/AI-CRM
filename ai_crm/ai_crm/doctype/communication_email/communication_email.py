import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

class CommunicationEmail(Document):
    def send(self):
        """Send this specific email"""
        try:
            # Get parent Communication Log
            parent = frappe.get_doc("Communication Log", self.parent)
            
            # Get recipient email
            party_doc = frappe.get_doc(parent.party_type, parent.party)
            recipient = party_doc.get("email_id")
            
            if not recipient:
                self._mark_failed("No recipient email address found")
                return False
            
            # Get sender email account
            sender_account_name = parent.sender_mail
            if not sender_account_name:
                # Try to get default outgoing account
                sender_account_name = frappe.db.get_value("Email Account", {"default_outgoing": 1}, "name")
            
            if not sender_account_name:
                self._mark_failed("No sender email account configured")
                return False
            
            # Get email account details
            email_account = frappe.get_doc("Email Account", sender_account_name)
            
            if not email_account.get("enable_outgoing"):
                self._mark_failed(f"Email account {sender_account_name} is not enabled for outgoing emails")
                return False
            
            sender_email_id = email_account.get("email_id")
            if not sender_email_id:
                self._mark_failed("Sender email ID is empty")
                return False
            
            # Send email using Frappe's sendmail - REMOVED sender_name parameter
            frappe.sendmail(
                recipients=[recipient],
                sender=sender_email_id,
                subject=self.subject,
                content=self.content,
                reference_doctype=parent.party_type,
                reference_name=parent.party,
                now=True
            )
            
            # Mark as sent
            self.status = "Sent"
            self.sent_at = now_datetime()
            self.error_message = ""  # Clear previous errors
            self.save()
            frappe.db.commit()
            
            frappe.logger().info(f"Email sent successfully: {self.subject}")
            return True
            
        except Exception as e:
            error_msg = f"Email send failed: {str(e)}"
            self._mark_failed(error_msg)
            frappe.log_error(error_msg, "CommunicationEmail Send Error")
            return False
    
    def _mark_failed(self, error_message):
        """Helper method to mark email as failed"""
        self.status = "Failed"
        self.error_message = error_message
        self.save()
        frappe.db.commit()