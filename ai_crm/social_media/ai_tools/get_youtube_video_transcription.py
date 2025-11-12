# Auto-generated LangChain tool for: get_youtube_video_transcription
# Module: Social Media

from typing import Any, Dict
import frappe
from langchain.tools import tool
import requests
import re


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

def fetch_transcript(video_id: str, api_token: str) -> Dict[str, Any]:
    """Fetch transcript from YouTube Transcript API."""
    try:
        transcript_url = "https://www.youtube-transcript.io/api/transcripts"
        tr_res = requests.post(
            transcript_url,
            headers={
                "Authorization": f"Basic {api_token}",
                "Content-Type": "application/json"
            },
            json={"ids": [video_id]},
            timeout=30
        )
       
        if tr_res.status_code == 200:
            tr_data = tr_res.json()
            if tr_data and isinstance(tr_data, list) and len(tr_data) > 0:
                if "tracks" in tr_data[0] and len(tr_data[0]["tracks"]) > 0:
                    chunks = [
                        seg.get("text", "") 
                        for seg in tr_data[0]["tracks"][0].get("transcript", [])
                    ]
                    cleaned_transcript = " ".join(chunks)
                    if cleaned_transcript:
                        return {
                            "success": True,
                            "transcript": "\n\n--- Transcript ---\n" + cleaned_transcript,
                            "status_code": 200
                        }
            return {
                "success": True,
                "transcript": "\n\n[No transcript available]",
                "status_code": 200
            }
       
        else:
            return {
                "success": False,
                "transcript": f"\n\n[Transcript API returned status: {tr_res.status_code}]",
                "status_code": tr_res.status_code
            }
                   
    except Exception as e:
        return {
            "success": False,
            "transcript": f"\n\n[Transcript unavailable: {str(e)}]",
            "status_code": 0
        }

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
    YOUTUBE_TRANSCRIPT_API_TOKEN = frappe.get_doc("YouTube Settings").get_password("api_key")
    
    try:
        # Extract video ID from URL or use direct ID
        video_id = extract_video_id(video_url_or_id)
        
        # Fetch transcript
        result = fetch_transcript(video_id, YOUTUBE_TRANSCRIPT_API_TOKEN)
        
        return result["transcript"]
        
    except ValueError as e:
        return f"\n\n[Error: {str(e)}]"
    except Exception as e:
        return f"\n\n[Unexpected error: {str(e)}]"
