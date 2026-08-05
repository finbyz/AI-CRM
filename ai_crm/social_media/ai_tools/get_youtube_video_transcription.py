# Auto-generated LangChain tool for: get_youtube_video_transcription
# Module: Social Media

import frappe
from langchain.tools import tool
import re

from ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services.transcript_service import (
    fetch_transcript_single_attempt,
)


def extract_video_id(url_or_id: str) -> str:
    """
    Extract YouTube video ID from various URL formats or return the ID itself.
    
    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - VIDEO_ID (direct ID)
    """
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'  # Direct video ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    
    raise ValueError(f"Could not extract video ID from: {url_or_id}")

@tool("get_youtube_video_transcription", return_direct=False)
def get_youtube_video_transcription_tool(video_url_or_id: str) -> str:
    """
    Get the transcription/captions of a YouTube video.
    
    This tool fetches the transcript (captions) from a YouTube video using the
    YouTube Transcript API.

    Args:
        video_url_or_id (str): YouTube video URL or video ID. Accepts formats like:
            - https://www.youtube.com/watch?v=VIDEO_ID
            - https://youtu.be/VIDEO_ID
            - VIDEO_ID (11-character video ID)

    Returns:
        str: The transcript text with status information, or an error message.
        
    Examples:
        >>> get_youtube_video_transcription_tool("dQw4w9WgXcQ")
        >>> get_youtube_video_transcription_tool("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    """
    api_token = frappe.get_single("YouTube Settings").get_password(
        "transcript_io_api_token",
        raise_exception=False,
    )

    try:
        # Extract video ID from URL or use direct ID
        video_id = extract_video_id(video_url_or_id)
        
        # Fetch transcript
        result = fetch_transcript_single_attempt(video_id, api_token)
        if not result.get("success"):
            return f"[Transcript unavailable: {result.get('error', 'Unknown error')}]"
        return result["transcript"]
        
    except ValueError as e:
        return f"\n\n[Error: {str(e)}]"
    except Exception as e:
        return f"\n\n[Unexpected error: {str(e)}]"
