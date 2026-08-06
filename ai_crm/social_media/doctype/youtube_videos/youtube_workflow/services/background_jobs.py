# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
Background Jobs
Orchestrates the complete YouTube workflow
"""

import frappe
from .video_fetcher import fetch_videos_from_channels, save_videos_to_tracker
from .video_processor import enqueue_video_processing


def run_youtube_workflow(
    tracker_name=None,
    channel_id=None,
    force=False,
    max_results=None,
):
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
        _set_tracker_status(tracker_name, "Running", "Fetching videos")
        # Step 1: Fetch videos from YouTube
        videos_list = fetch_videos_from_channels(
            channel_id=channel_id,
            force=force,
            max_results=max_results,
        )
        
        if not videos_list:
            videos_enqueued = enqueue_video_processing(tracker_name) if tracker_name else 0
            _set_tracker_status(
                tracker_name,
                "Running" if videos_enqueued else "Completed",
                f"Processing {videos_enqueued} pending videos" if videos_enqueued else "No new videos found",
            )
            return {
                "success": True,
                "videos_fetched": 0,
                "videos_added": 0,
                "videos_enqueued": videos_enqueued,
                "message": (
                    "No new videos; retried pending videos"
                    if videos_enqueued
                    else "No new videos based on frequency"
                ),
            }
        if tracker_name is None:
            tracker = frappe.new_doc("YouTube Videos")
            tracker.workflow_status = "Running"
            tracker.workflow_message = "Processing fetched videos"
            tracker.save(ignore_permissions=True)
            tracker_name = tracker.name
        # Step 2: Save videos to tracker
        videos_added = save_videos_to_tracker(tracker_name, videos_list)
        
        if videos_added == 0:
            videos_enqueued = enqueue_video_processing(tracker_name)
            _set_tracker_status(
                tracker_name,
                "Running" if videos_enqueued else "Completed",
                f"Processing {videos_enqueued} pending videos" if videos_enqueued else "No pending videos",
            )
            return {
                "success": True,
                "videos_fetched": len(videos_list),
                "videos_added": 0,
                "videos_enqueued": videos_enqueued,
                "message": "Existing pending videos queued for retry",
            }
        
        # Step 3: Enqueue processing jobs
        videos_enqueued = enqueue_video_processing(tracker_name)
        _set_tracker_status(
            tracker_name,
            "Running" if videos_enqueued else "Completed",
            f"Processing {videos_enqueued} videos" if videos_enqueued else "Import completed",
        )
        
        return {
            "success": True,
            "videos_fetched": len(videos_list),
            "videos_added": videos_added,
            "videos_enqueued": videos_enqueued,
            "message": (
                f"Successfully fetched {len(videos_list)} videos, added {videos_added} new videos, "
                f"enqueued {videos_enqueued} for processing"
            ),
        }
        
    except Exception as e:
        _set_tracker_status(tracker_name, "Failed", str(e))
        frappe.log_error(
            f"YouTube workflow error: {str(e)}",
            "YouTube Workflow"
        )
        return {
            "success": False,
            "error": str(e),
            "message": f"Workflow failed: {str(e)}"
        }


def enqueue_youtube_workflow(
    tracker_name=None,
    channel_id=None,
    force=False,
    max_results=None,
):
    """
    Enqueue the complete YouTube workflow as a background job.
    
    Args:
        tracker_name: Name of the YouTube Videos document
    """
    frappe.enqueue(
        method=(
            "ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services."
            "background_jobs.run_youtube_workflow"
        ),
        queue='long',
        timeout=3600,
        is_async=True,
        tracker_name=tracker_name,
        channel_id=channel_id,
        force=force,
        max_results=max_results,
        enqueue_after_commit=True
    )


def _set_tracker_status(tracker_name, status, message):
    if tracker_name and frappe.db.exists("YouTube Videos", tracker_name):
        frappe.db.set_value(
            "YouTube Videos",
            tracker_name,
            {"workflow_status": status, "workflow_message": str(message)[:500]},
        )
