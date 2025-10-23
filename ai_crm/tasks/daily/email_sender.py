import frappe
from frappe.utils import now_datetime, get_datetime

class EmailSender:
    @staticmethod
    def send_scheduled_emails():
        """Main function to send all scheduled emails"""
        frappe.logger().info("Starting scheduled email send job")
        
        try:
            logs = frappe.get_all(
                "Communication Log",
                filters={"docstatus": ["!=", 2]},
                fields=["name", "party_type", "party", "sender_mail"]
            )
            
            frappe.logger().info(f"Found {len(logs)} communication logs to process")
            
            sent_count = 0
            failed_count = 0
            
            for log in logs:
                try:
                    frappe.logger().info(f"Processing log: {log.name}")
                    log_doc = frappe.get_doc("Communication Log", log.name)
                    
                    if not log_doc.communication_email:
                        continue
                    
                    for email_row in log_doc.communication_email:
                        if email_row.status == "Unsent":
                            try:
                                scheduled_time = get_datetime(email_row.time)
                                current_time = now_datetime()
                                
                                if scheduled_time <= current_time:
                                    frappe.logger().info(
                                        f"Time check passed: {scheduled_time} <= {current_time}"
                                    )
                                    EmailSender.send_single_email(email_row, log_doc)
                                    sent_count += 1
                                else:
                                    frappe.logger().info(
                                        f"Email not ready yet. Scheduled: {scheduled_time}, Current: {current_time}"
                                    )
                            except Exception as e:
                                failed_count += 1
                                frappe.log_error(
                                    f"Failed to send email: {str(e)}\n{frappe.get_traceback()}",
                                    f"Email Send Failed - {log_doc.name}"
                                )
                                frappe.logger().error(f" Email send error: {str(e)}")
                
                except Exception as e:
                    frappe.log_error(
                        f"Error processing log {log.get('name')}: {str(e)}\n{frappe.get_traceback()}",
                        "Email Sender - Log Processing Error"
                    )
                    frappe.logger().error(f" Log processing error: {str(e)}")
            
            result_msg = f" Email send job completed. Sent: {sent_count}, Failed: {failed_count}"
            frappe.logger().info(result_msg)
            return {"sent": sent_count, "failed": failed_count}
            
        except Exception as e:
            frappe.log_error(
                f"Critical error in send_scheduled_emails: {str(e)}\n{frappe.get_traceback()}",
                "Email Sender - Critical Error"
            )
            frappe.logger().error(f" Critical error: {str(e)}")
            return {"sent": 0, "failed": 0, "error": str(e)}

    @staticmethod
    def send_single_email(email_row, log_doc):
        """Send a single email"""
        try:
            # Validate sender account
            if not log_doc.sender_mail:
                email_row.status = "Failed"
                email_row.error_message = "No sender email account configured"
                log_doc.save()
                raise Exception("Sender account not configured")
            
            try:
                sender_account = frappe.get_doc("Email Account", log_doc.sender_mail)
            except frappe.DoesNotExistError:
                email_row.status = "Failed"
                email_row.error_message = f"Email account {log_doc.sender_mail} not found"
                log_doc.save()
                frappe.db.commit()
                raise Exception(f"Email account not found: {log_doc.sender_mail}")
            
            if not sender_account.enable_outgoing:
                email_row.status = "Failed"
                email_row.error_message = "Email account not enabled for outgoing"
                log_doc.save()
                frappe.db.commit()
                raise Exception("Email account not enabled for outgoing")
            
            # Get recipient email
            party_doc = frappe.get_doc(log_doc.party_type, log_doc.party)
            recipient_email = party_doc.get("email_id") or party_doc.get("email")
            
            if not recipient_email:
                email_row.status = "Failed"
                email_row.error_message = "No email address found for party"
                log_doc.save()
                frappe.db.commit()
                raise Exception("No recipient email found")
            
            frappe.logger().info(f"Sending email to {recipient_email}")
            
            # Send email
            frappe.sendmail(
                recipients=[recipient_email],
                sender=sender_account.email_id,
                subject=email_row.subject,
                message=email_row.content,
                reference_doctype=log_doc.party_type,
                reference_name=log_doc.party,
                delayed=False
            )
            
            # Update status
            email_row.status = "Sent"
            email_row.sent_at = now_datetime()
            email_row.error_message = None
            
            log_doc.flags.ignore_version_mismatch = True
            log_doc.save(ignore_version=True)
            frappe.db.commit()
            
            frappe.logger().info(f"Email sent to {recipient_email}: {email_row.subject}")
            
        except Exception as e:
            # Mark as failed
            email_row.status = "Failed"
            email_row.error_message = str(e)[:200]
            
            try:
                log_doc.flags.ignore_version_mismatch = True
                log_doc.save(ignore_version=True)
                frappe.db.commit()
            except:
                pass
            
            frappe.logger().error(f" Email failed: {str(e)}")
            raise e


def enqueue_scheduled_emails():
    """Queue the email sending job (called by scheduler)"""
    frappe.logger().info(" Enqueueing scheduled email job")
    try:
        frappe.enqueue(
            method="ai_crm.tasks.daily.email_sender.EmailSender.send_scheduled_emails",
            queue="long",
            timeout=600,
            is_async=True
        )
    except Exception as e:
        frappe.logger().error(f"Failed to enqueue email job: {str(e)}")