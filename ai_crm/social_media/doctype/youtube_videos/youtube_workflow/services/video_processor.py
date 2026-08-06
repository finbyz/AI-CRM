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
                    ch_doc.source_url = video.video_link
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
        check_and_update_tracker_completion(tracker_name)

    except Exception as e:
        frappe.log_error(
            f"Error processing video {video_id}: {str(e)}",
            "YouTube Video Workflow"
        )
        check_and_update_tracker_completion(tracker_name)


def check_and_update_tracker_completion(tracker_name):
    """
    Check if all videos in the tracker document have completed processing,
    and update parent YouTube Videos workflow_status and workflow_message accordingly.
    """
    if not tracker_name or not frappe.db.exists("YouTube Videos", tracker_name):
        return

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
    if unprocessed:
        # Still some videos pending
        return

    # All videos processed!
    related_videos = [v for v in tracker.videos if v.is_related]
    failed_videos = [v for v in tracker.videos if not v.is_related and ("unavailable" in (v.analysis_reasoning or "").lower() or "failed" in (v.analysis_reasoning or "").lower())]
    not_related_videos = [v for v in tracker.videos if not v.is_related and v not in failed_videos]
    total_videos = len(tracker.videos)

    if total_videos == 1:
        single_video = tracker.videos[0]
        if single_video.is_related:
            status = "Completed"
            message = "Completed: Video is relevant. Content Hub created successfully."
        elif single_video in failed_videos:
            status = "Completed"
            message = f"Completed: Video processing failed. Reason: {single_video.analysis_reasoning}"
        else:
            reason = single_video.analysis_reasoning or "Not relevant to criteria"
            status = "Completed"
            message = f"Completed: Video analyzed but not relevant (Content Hub skipped). Reason: {reason}"
    else:
        status = "Completed"
        parts = []
        if related_videos:
            parts.append(f"{len(related_videos)} relevant")
        if not_related_videos:
            parts.append(f"{len(not_related_videos)} not relevant")
        if failed_videos:
            parts.append(f"{len(failed_videos)} failed")
        
        summary = ", ".join(parts) if parts else "0 videos processed"
        message = f"Completed: {total_videos} video(s) analyzed ({summary})."

    frappe.db.set_value(
        "YouTube Videos",
        tracker_name,
        {
            "workflow_status": status,
            "workflow_message": str(message)[:500]
        }
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

