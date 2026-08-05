# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
Transcript Service
Handles fetching transcripts from YouTube videos
"""

import frappe
import requests


def fetch_transcript_single_attempt(video_id, api_token=None):
    """
    Fetch transcript with transcript.io primary and youtube_transcript_api fallback.

    Args:
        video_id: YouTube video ID
        api_token: Optional Transcript.io API token

    Returns:
        dict: {
            'success': bool,
            'transcript': str,
            'status_code': int,
            'source': str
        }
    """
    errors = []

    # 1. Primary: Try Transcript.io API if token is provided
    if api_token:
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
                result = _process_transcript_response(response)
                if result.get("success") and result.get("transcript"):
                    result["source"] = "transcript.io"
                    return result
            elif response.status_code == 429:
                errors.append("Transcript.io rate limit reached")
                frappe.log_error(f"Transcript.io rate limited for video {video_id}", "YouTube Transcript Rate Limit")
            else:
                errors.append(f"Transcript.io returned HTTP {response.status_code}")
        except Exception as e:
            errors.append(f"Transcript.io: {e}")
            frappe.log_error(
                f"Transcript.io API error ({video_id}): {str(e)}",
                "YouTube Transcript API Error"
            )

    # 2. Fallback: youtube_transcript_api Python library
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        yt = YouTubeTranscriptApi()
        fetched = None

        # 1. Try listing tracks with strict English priority
        try:
            t_list = yt.list(video_id)
            if t_list:
                chosen_t = None
                # Priority 1: Manual English track
                for t in t_list:
                    if not getattr(t, 'is_generated', True) and getattr(t, 'language_code', '').startswith('en'):
                        chosen_t = t
                        break
                # Priority 2: Auto-generated English track
                if not chosen_t:
                    for t in t_list:
                        if getattr(t, 'language_code', '').startswith('en'):
                            chosen_t = t
                            break
                # Priority 3: Manual track in any language
                if not chosen_t:
                    for t in t_list:
                        if not getattr(t, 'is_generated', True):
                            chosen_t = t
                            break
                # Priority 4: First available track in any language
                if not chosen_t:
                    chosen_t = next(iter(t_list))

                fetched = chosen_t.fetch()
        except Exception as e:
            errors.append(f"YouTube track list: {e}")

        # 2. Fallback to direct fetch()
        if not fetched:
            try:
                fetched = yt.fetch(video_id)
            except Exception as e:
                errors.append(f"YouTube transcript fetch: {e}")
                fetched = None

        if fetched:
            chunks = []
            for item in fetched:
                if isinstance(item, dict):
                    t = item.get("text")
                else:
                    t = getattr(item, "text", None)
                if t:
                    chunks.append(str(t).strip())

            transcript_text = " ".join(chunks).strip()
            if transcript_text:
                return {
                    "success": True,
                    "transcript": transcript_text,
                    "status_code": 200,
                    "source": "youtube_transcript_api"
                }
    except Exception as e:
        errors.append(f"YouTube transcript fallback: {e}")
        frappe.log_error(
            f"youtube_transcript_api fallback failed for {video_id}: {str(e)}",
            "YouTube Transcript Fallback Error"
        )

    return {
        "success": False,
        "transcript": "",
        "status_code": 404,
        "error": "; ".join(errors) or "No captions are available for this video"
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
