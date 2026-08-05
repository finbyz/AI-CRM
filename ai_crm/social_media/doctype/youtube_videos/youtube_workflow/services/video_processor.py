# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
Video Processor
Main workflow orchestration for processing individual videos
"""

import frappe
from frappe.utils import now_datetime
from .transcript_service import fetch_transcript_single_attempt
from .ai_service import get_analysis_agent, analyze_video


def process_video_workflow(tracker_name, video_id):
    """
    Complete workflow for processing a single video:
    1. Fetch transcript
    2. Analyze video for relevance
    3. If related, create a Content Hub and generate ideas
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
        transcript_api_token = settings.get_password("transcript_io_api_token", raise_exception=False)

        # Step 1: Fetch transcript (uses primary transcript.io or fallback youtube_transcript_api)
        transcript_result = fetch_transcript_single_attempt(video_id, transcript_api_token)

        if transcript_result.get("success") and transcript_result.get("transcript"):
            video.transcript = transcript_result["transcript"]
            frappe.db.set_value("YouTube Video", video.name, "transcript", video.transcript)
        else:
            error = transcript_result.get("error") or "No captions are available"
            _update_video_status(video, f"Transcript unavailable: {error}", mark_processed=False)
            return

        # Step 2: Analyze video
        analysis_result = _analyze_video_step(video, settings)

        if not analysis_result.get("success"):
            _update_video_status(video, "Analysis failed", mark_processed=True)
            return

        video.is_related = analysis_result.get("is_related", 0)
        video.analysis_reasoning = analysis_result.get("reasoning", "")
        video.last_analyzed_on = now_datetime()

        # Step 3: Create Content Hub & generate ideas/posts if video is related
        if video.is_related:
            try:
                # Find or create Content Hub for this video
                if video.content_hub and frappe.db.exists("Content Hub", video.content_hub):
                    pass # Keep existing link
                else:
                    ch_doc = frappe.new_doc("Content Hub")
                    ch_doc.title = video.title
                    ch_doc.source_type = "YouTube Video"
                    ch_doc.channel_name = getattr(video, "channel_name", "") or ""
                    ch_doc.insert(ignore_permissions=True)
                    video.content_hub = ch_doc.name

                    # Try generating ideas for the Content Hub
                    try:
                        ch_doc.generate_ideas()
                    except Exception as ch_err:
                        frappe.log_error(f"Error generating ideas for auto-created Content Hub {ch_doc.name}: {str(ch_err)}")
            except Exception as ch_e:
                frappe.log_error(f"Error creating Content Hub for video {video_id}: {str(ch_e)}")

        _save_video_result(video)

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
            method='ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services.video_processor.process_video_workflow',
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


def _update_video_status(video, reasoning, mark_processed):
    values = {
        "analysis_reasoning": reasoning,
        "last_analyzed_on": now_datetime() if mark_processed else None,
    }
    frappe.db.set_value("YouTube Video", video.name, values)


def _save_video_result(video):
    frappe.db.set_value("YouTube Video", video.name, {
        "transcript": video.transcript,
        "is_related": video.is_related,
        "analysis_reasoning": video.analysis_reasoning,
        "last_analyzed_on": video.last_analyzed_on,
        "content_hub": video.content_hub,
    })


def _analyze_video_step(video, settings):
    """Step 2: Analyze video for relevance."""
    try:
        analysis_agent = get_analysis_agent()
        return analyze_video(
            agent_service=analysis_agent,
            video_title=video.title,
            video_transcript=video.transcript,
            relevance_prompt=settings.relevance_prompt,
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
