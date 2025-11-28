# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
Transcript Service
Handles fetching transcripts from YouTube videos
"""

import frappe
import requests
import time


def fetch_transcript_single_attempt(video_id, api_token):
    """
    Fetch transcript without retry logic (for background processing).
    
    Args:
        video_id: YouTube video ID
        api_token: Transcript.io API token
        
    Returns:
        dict: {
            'success': bool,
            'transcript': str,
            'status_code': int,
            'rate_limited': bool (optional)
        }
    """
    try:
        response = requests.post(
            "https://www.youtube-transcript.io/api/transcripts",
            headers={
                "Authorization": f"Basic {api_token}",
                "Content-Type": "application/json"
            },
            json={"ids": [video_id]},
            timeout=30
        )
        
        if response.status_code == 200:
            return _process_transcript_response(response)
        
        elif response.status_code == 429:
            return {
                "success": False,
                "transcript": "",
                "status_code": 429,
                "rate_limited": True
            }
        
        else:
            return {
                "success": False,
                "transcript": "",
                "status_code": response.status_code
            }
            
    except Exception as e:
        frappe.log_error(
            f"Transcript single attempt error ({video_id}): {str(e)}",
            "YouTube Transcript Error"
        )
        return {
            "success": False,
            "transcript": "",
            "status_code": 0,
            "error": str(e)
        }


def _process_transcript_response(response):
    """Process the transcript API response and extract text."""
    try:
        data = response.json()
        
        if not data or not isinstance(data, list) or len(data) == 0:
            return {
                "success": True,
                "transcript": "",
                "status_code": 200,
                "no_transcript": True
            }
        
        tracks = data[0].get("tracks", [])
        
        if not tracks or "transcript" not in tracks[0]:
            return {
                "success": True,
                "transcript": "",
                "status_code": 200,
                "no_transcript": True
            }
        
        segments = tracks[0]["transcript"]
        chunks = [seg.get("text", "") for seg in segments]
        transcript_text = " ".join(chunks)
        
        return {
            "success": True,
            "transcript": transcript_text,
            "status_code": 200
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error processing transcript response: {str(e)}",
            "YouTube Transcript Processing"
        )
        return {
            "success": False,
            "transcript": "",
            "status_code": 200,
            "error": str(e)
        }
