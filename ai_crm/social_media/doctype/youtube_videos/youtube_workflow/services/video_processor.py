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
    3. Update video record with results (users then pick relevant videos to research)

    Args:
        tracker_name: Name of the YouTube Videos document
        video_id: YouTube video ID to process
    """
    try:
        tracker = frappe.get_doc("YouTube Videos", tracker_name)
        video = _get_video_from_tracker(tracker, video_id)

        if not video:
            frappe.log_error("YouTube Video Workflow", f"Video {video_id} not found in tracker {tracker_name}")
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
            _update_video_status(video, f"Transcript unavailable: {error}", mark_processed=True)
            check_and_update_tracker_completion(tracker_name)
            return

        # Step 2: Analyze video
        analysis_result = _analyze_video_step(video, settings)

        if not analysis_result.get("success"):
            _update_video_status(video, "Analysis failed", mark_processed=True)
            check_and_update_tracker_completion(tracker_name)
            return

        video.is_related = analysis_result.get("is_related", 0)
        video.analysis_reasoning = analysis_result.get("reasoning", "")
        video.last_analyzed_on = now_datetime()

        # Research and post generation are started by the user from the row ("Do Research").
        _save_video_result(video)
        check_and_update_tracker_completion(tracker_name)

    except Exception as e:
        frappe.log_error("YouTube Video Workflow", f"Error processing video {video_id}: {str(e)}")
        check_and_update_tracker_completion(tracker_name)


def check_and_update_tracker_completion(tracker_name):
    """
    Mark the tracker Completed once every video is analysed. It is saved (not db-updated)
    so the "relevant videos" email notification fires exactly once.
    """
    if not tracker_name or not frappe.db.exists("YouTube Videos", tracker_name):
        return

    # Video jobs run in parallel: commit this job's results, then let one job at a time decide.
    frappe.db.commit()
    frappe.db.sql("SELECT name FROM `tabYouTube Videos` WHERE name = %s FOR UPDATE", tracker_name)

    tracker = frappe.get_doc("YouTube Videos", tracker_name)
    if not tracker.videos:
        # Find most recent previous tracker record with videos
        prev = frappe.db.sql("""
            SELECT t.name 
            FROM `tabYouTube Videos` t
            JOIN `tabYouTube Video` v ON v.parent = t.name
            WHERE t.name != %s
            ORDER BY t.creation DESC
            LIMIT 1
        """, (tracker_name,), as_dict=True)

        prev_id = prev[0].name if prev else ""
        if prev_id:
            msg = f"Completed: No new videos found. Previously fetched in {prev_id}"
        else:
            msg = "Completed: No new videos found (channel already fetched recently or videos already imported)"

        frappe.db.set_value(
            "YouTube Videos",
            tracker_name,
            {"workflow_status": "Completed", "workflow_message": str(msg)[:500]}
        )
        return

    # Check if all videos have been analyzed / processed
    unprocessed = [
        v for v in tracker.videos
        if not v.last_analyzed_on and not (v.analysis_reasoning and len((v.analysis_reasoning or "").strip()) > 0)
    ]
    if unprocessed or tracker.workflow_status == "Completed":
        return

    related_videos = [v for v in tracker.videos if v.is_related]
    failed_videos = [v for v in tracker.videos if not v.is_related and ("unavailable" in (v.analysis_reasoning or "").lower() or "failed" in (v.analysis_reasoning or "").lower())]
    not_related_videos = [v for v in tracker.videos if not v.is_related and v not in failed_videos]
    total_videos = len(tracker.videos)

    if total_videos == 1:
        single_video = tracker.videos[0]
        if single_video.is_related:
            message = "Completed: Video is relevant. Open the row and click Do Research."
        elif single_video in failed_videos:
            message = f"Completed: Video processing failed. Reason: {single_video.analysis_reasoning}"
        else:
            reason = single_video.analysis_reasoning or "Not relevant to criteria"
            message = f"Completed: Video analyzed but not relevant. Reason: {reason}"
    else:
        parts = []
        if related_videos:
            parts.append(f"{len(related_videos)} relevant")
        if not_related_videos:
            parts.append(f"{len(not_related_videos)} not relevant")
        if failed_videos:
            parts.append(f"{len(failed_videos)} failed")
        
        summary = ", ".join(parts) if parts else "0 videos processed"
        message = f"Completed: {total_videos} video(s) analyzed ({summary})."

    tracker.workflow_status = "Completed"
    tracker.workflow_message = message[:500]
    tracker.relevant_videos = len(related_videos)
    tracker.save(ignore_permissions=True)
    frappe.db.commit()


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

    if not unprocessed_videos:
        check_and_update_tracker_completion(tracker_name)
        return 0

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
        frappe.log_error("YouTube Analysis Step", f"Analysis step error for {video.video_id}: {str(e)}")
        return {
            "success": False,
            "is_related": 0,
            "reasoning": f"Analysis error: {str(e)}"
        }

