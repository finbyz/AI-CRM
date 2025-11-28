# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ai_crm.ai_crm.doctype.youtube_videos.youtube_workflow.services.background_jobs import enqueue_youtube_workflow


class YouTubeVideos(Document):

    @frappe.whitelist()
    def fetch_videos_workflow(self):
        """
        Trigger the complete YouTube workflow:
        1. Fetch videos from channels
        2. Save to tracker
        3. Process each video (transcript → analysis → post generation)
        
        Returns:
            str: Status message
        """
        try:
            enqueue_youtube_workflow(self.name)
            return "✅ YouTube workflow enqueued. Videos will be fetched and processed in the background."
            
        except Exception as e:
            frappe.log_error(
                f"Fetch workflow error: {str(e)}",
                "YouTube Videos Workflow"
            )
            frappe.throw(f"Error in fetch workflow: {str(e)}")

