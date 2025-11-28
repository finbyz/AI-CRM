# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
Background Jobs
Orchestrates the complete YouTube workflow
"""

import frappe
from .video_fetcher import fetch_videos_from_channels, save_videos_to_tracker
from .video_processor import enqueue_video_processing


def run_youtube_workflow(tracker_name = None):
    """
    Complete YouTube workflow:
    1. Fetch videos from all channels
    2. Save videos to tracker
    3. Enqueue processing for each video
    
    This function should be called as a background job.
    
    Args:
        tracker_name: Name of the YouTube Videos document
    """
    try:
        # Step 1: Fetch videos from YouTube
        videos_list = fetch_videos_from_channels()
        
        if not videos_list:
            frappe.log_error(
                f"No videos fetched for tracker {tracker_name}",
                "YouTube Workflow"
            )
            return {
                "success": True,
                "videos_fetched": 0,
                "videos_added": 0,
                "videos_enqueued": 0,
                "message": "No new videos based on frequency"
            }
        if tracker_name is None:
            tracker = frappe.get_doc("YouTube Videos")
            tracker.save(ignore_permissions=True)
            tracker_name = tracker.name
        # Step 2: Save videos to tracker
        videos_added = save_videos_to_tracker(tracker_name, videos_list)
        
        if videos_added == 0:
            return {
                "success": True,
                "videos_fetched": len(videos_list),
                "videos_added": 0,
                "videos_enqueued": 0,
                "message": "All fetched videos already exist in tracker"
            }
        
        # Step 3: Enqueue processing jobs
        videos_enqueued = enqueue_video_processing(tracker_name)
        
        return {
            "success": True,
            "videos_fetched": len(videos_list),
            "videos_added": videos_added,
            "videos_enqueued": videos_enqueued,
            "message": f"Successfully fetched {len(videos_list)} videos, added {videos_added} new videos, enqueued {videos_enqueued} for processing"
        }
        
    except Exception as e:
        frappe.log_error(
            f"YouTube workflow error: {str(e)}",
            "YouTube Workflow"
        )
        return {
            "success": False,
            "error": str(e),
            "message": f"Workflow failed: {str(e)}"
        }


def enqueue_youtube_workflow(tracker_name):
    """
    Enqueue the complete YouTube workflow as a background job.
    
    Args:
        tracker_name: Name of the YouTube Videos document
    """
    frappe.enqueue(
        method='ai_crm.ai_crm.doctype.youtube_videos.youtube_workflow.services.background_jobs.run_youtube_workflow',
        queue='long',
        timeout=3600,
        is_async=True,
        tracker_name=tracker_name,
        enqueue_after_commit=True
    )
# ai_crm.ai_crm.doctype.youtube_videos.youtube_workflow.services.background_jobs.run_youtube_workflow
# ai_crm.ai_crm.doctype.youtube_tracker.youtube_workflow.services.background_jobs.run_youtube_workflow
