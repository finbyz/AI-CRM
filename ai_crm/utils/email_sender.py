import frappe
from frappe.utils import now_datetime, get_datetime

class EmailSender:
    @staticmethod
    def send_scheduled_emails():
        frappe.logger().info(" Starting scheduled email sending job...")
        
        logs = frappe.get_all(
            "Communication Log",
            fields=["name", "party_type", "party", "sender_mail"]
        )
        sent_count = 0
        failed_count = 0
        
        for log in logs:
            try:
                log_doc = frappe.get_doc("Communication Log", log.name)
                
                for email in log_doc.communication_email:
                    if email.status == "Unsent" and get_datetime(email.time) <= now_datetime():
                        try:
                            party_doc = frappe.get_doc(log.party_type, log.party)
                            recipient = party_doc.get("email_id")
                            
                            if not recipient:
                                email.status = "Failed"
                                email.error_message = "No email address found"
                                frappe.logger().error(f" No recipient email for {log.party}")
                                continue
                            
                            sender_account = frappe.get_doc("Email Account", log.sender_mail)
                            sender_name = sender_account.sender_name or "Sales Team"
                            
                            frappe.logger().info(f"Sending email to {recipient}: {email.subject}")
                            
                            frappe.sendmail(
                                recipients=[recipient],
                                sender=log.sender_mail,
                                sender_name=sender_name,
                                subject=email.subject,
                                message=email.content,
                                reference_doctype=log.party_type,
                                reference_name=log.party
                            )
                            
                            email.status = "Sent"
                            email.sent_at = now_datetime()
                            sent_count += 1
                            
                            frappe.logger().info(f" Email sent to {recipient}: {email.subject}")
                            
                        except Exception as e:
                            email.status = "Failed"
                            email.error_message = str(e)
                            failed_count += 1
                            frappe.log_error(f"Failed to send email: {str(e)}", "Email Sender Error")
                            frappe.logger().error(f" Failed to send: {str(e)}")
                
                log_doc.save(ignore_permissions=True)
                
            except Exception as e:
                frappe.log_error(f"Error processing log {log.name}: {str(e)}", "Email Sender Error")
                failed_count += 1

        frappe.db.commit()
        
        if sent_count > 0 or failed_count > 0:
            frappe.logger().info(f"Email Sender Summary:  Sent {sent_count},  Failed {failed_count}")
        else:
            frappe.logger().info(f"No emails due for sending")
        
        return {"sent": sent_count, "failed": failed_count}
def send_scheduled_emails():
    
    return EmailSender.send_scheduled_emails()