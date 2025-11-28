# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
Video Processor
Main workflow orchestration for processing individual videos
"""

import frappe
from frappe.utils import now_datetime
from .transcript_service import fetch_transcript_single_attempt
from .ai_service import get_analysis_agent, get_post_generation_agent, analyze_video, generate_social_post
from .post_service import create_social_media_post


def process_video_workflow(tracker_name, video_id):
    """
    Complete workflow for processing a single video:
    1. Fetch transcript
    2. Analyze video for relevance
    3. If related, generate social media post
    4. Update video record with results
    
    Args:
        tracker_name: Name of the YouTube Videos document
        video_id: YouTube video ID to process
    """
    try:
        tracker = frappe.get_doc("YouTube Videos", tracker_name)
        video = _get_video_from_tracker(tracker, video_id)
        
        if not video:
            frappe.log_error(
                f"Video {video_id} not found in tracker {tracker_name}",
                "YouTube Video Workflow"
            )
            return
        
        settings = frappe.get_single("YouTube Settings")
        transcript_api_token = settings.get_password("transcript_io_api_token")
        
        if not transcript_api_token:
            _update_video_status(tracker, video, "Transcript API token missing")
            return
        
        # Step 1: Fetch transcript
        transcript_result = fetch_transcript_single_attempt(video_id, transcript_api_token)
        
        if not transcript_result.get("success"):
            if transcript_result.get("rate_limited"):
                _update_video_status(tracker, video, "Transcript rate-limited")
            else:
                _update_video_status(tracker, video, "Transcript unavailable")
            return
        
        video.transcript = (video.transcript or "") + "\n\n--- Transcript ---\n" + transcript_result.get("transcript", "")
        
        # Step 2: Analyze video
        analysis_result = _analyze_video_step(video)
        
        if not analysis_result.get("success"):
            _update_video_status(tracker, video, "Analysis failed")
            return
        
        video.is_related = analysis_result.get("is_related", 0)
        video.analysis_reasoning = analysis_result.get("reasoning", "")
        video.last_analyzed_on = now_datetime()
        
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Step 3: Generate social media post if video is related
        if video.is_related:
            post_result = _generate_post_step(video)
            
            if post_result.get("success"):
                post_name = create_social_media_post(
                    video_title=video.title,
                    video_id=video.video_id,
                    video_link=video.video_link,
                    post_content=post_result.get("content", "")
                )
                
                if post_name:
                    video.social_media_post = post_name
                    tracker.save(ignore_permissions=True)
                    frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(
            f"Error processing video {video_id}: {str(e)}",
            "YouTube Video Workflow"
        )


def enqueue_video_processing(tracker_name):
    """
    Enqueue background jobs for all unprocessed videos in a tracker.
    
    Args:
        tracker_name: Name of the YouTube Videos document
        
    Returns:
        int: Number of videos enqueued
    """
    tracker = frappe.get_doc("YouTube Videos", tracker_name)
    
    unprocessed_videos = [v for v in tracker.videos if not v.last_analyzed_on]
    
    for video in unprocessed_videos:
        frappe.enqueue(
            method='ai_crm.ai_crm.doctype.youtube_videos.youtube_workflow.services.video_processor.process_video_workflow',
            queue='long',
            timeout=1800,
            is_async=True,
            tracker_name=tracker_name,
            video_id=video.video_id,
            enqueue_after_commit=True
        )
    
    return len(unprocessed_videos)


def _get_video_from_tracker(tracker, video_id):
    """Find a video in the tracker's child table."""
    for video in tracker.videos:
        if video.video_id == video_id:
            return video
    return None


def _update_video_status(tracker, video, reasoning):
    """Update video with error status and save."""
    video.analysis_reasoning = reasoning
    video.last_analyzed_on = now_datetime()
    tracker.save(ignore_permissions=True)
    frappe.db.commit()


def _analyze_video_step(video):
    """Step 2: Analyze video for relevance."""
    try:
        analysis_agent = get_analysis_agent()
        return analyze_video(
            agent_service=analysis_agent,
            video_title=video.title,
            video_transcript=video.transcript
        )
    except Exception as e:
        frappe.log_error(
            f"Analysis step error for {video.video_id}: {str(e)}",
            "YouTube Analysis Step"
        )
        return {
            "success": False,
            "is_related": 0,
            "reasoning": f"Analysis error: {str(e)}"
        }


def _generate_post_step(video):
    """Step 3: Generate social media post."""
    try:
        post_agent = get_post_generation_agent()
        return generate_social_post(
            agent_service=post_agent,
            video_title=video.title,
            video_transcript=video.transcript
        )
    except Exception as e:
        frappe.log_error(
            f"Post generation step error for {video.video_id}: {str(e)}",
            "YouTube Post Generation Step"
        )
        return {
            "success": False,
            "linkedin_post": ""
        }
