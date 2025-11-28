# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
Video Fetcher Service
Handles fetching videos from YouTube channels
"""

import frappe
import requests
from datetime import timedelta
from frappe.utils import now_datetime


def fetch_videos_from_channels():
    """
    Fetch videos from all configured YouTube channels.
    Returns list of video data dictionaries.
    
    Returns:
        list: List of video dicts with channel info
    """
    settings = frappe.get_single("YouTube Settings")
    
    api_key = settings.get_password("api_key")
    if not api_key:
        frappe.throw("YouTube API key missing in YouTube Settings")
    
    channels = settings.get("channels")
    if not channels:
        return []
    
    all_videos = []
    now = now_datetime()
    
    for channel in channels:
        try:
            if not _should_fetch_channel(channel, now):
                continue
            
            channel_videos = _fetch_channel_videos(channel, api_key, now)
            all_videos.extend(channel_videos)
            
            channel.last_fetched_on = now
            
        except Exception as e:
            frappe.log_error(
                f"Fetch error ({getattr(channel, 'channel_name', 'unknown')}): {str(e)}",
                "YouTube Video Fetcher"
            )
            continue
    
    if all_videos:
        settings.save(ignore_permissions=True)
        frappe.db.commit()
    
    return all_videos


def _should_fetch_channel(channel, current_time):
    """Check if channel should be fetched based on frequency."""
    frequency_days = max(int(channel.fetch_frequency or 5), 1)
    last_fetched_on = channel.last_fetched_on
    
    if not last_fetched_on:
        return True
    
    return current_time >= last_fetched_on + timedelta(days=frequency_days)


def _fetch_channel_videos(channel, api_key, now):
    """Fetch videos from a specific YouTube channel."""
    frequency_days = max(int(channel.fetch_frequency or 5), 1)
    is_weekly = frequency_days == 7
    
    last_fetched_on = channel.last_fetched_on
    published_after = (last_fetched_on or (now - timedelta(days=7))).isoformat("T") + "Z"
    
    all_videos = []
    next_page_token = None
    
    while True:
        params = {
            "key": api_key,
            "channelId": channel.channel_id,
            "part": "snippet",
            "publishedAfter": published_after,
            "order": "viewCount" if is_weekly else "date",
            "type": "video",
            "maxResults": 50
        }
        
        if next_page_token:
            params["pageToken"] = next_page_token
        
        try:
            res = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params,
                timeout=30
            ).json()
        except Exception as e:
            frappe.log_error(
                f"YouTube API request failed for {channel.channel_name}: {str(e)}",
                "YouTube API Error"
            )
            break
        
        if "error" in res:
            frappe.log_error(
                f"YouTube API Error ({channel.channel_name}): {res['error'].get('message', 'Unknown')}",
                "YouTube Fetch Error"
            )
            break
        
        page_videos = _process_api_response(res, api_key, channel)
        all_videos.extend(page_videos)
        
        next_page_token = res.get("nextPageToken")
        if is_weekly or not next_page_token:
            break
    
    if is_weekly and all_videos:
        all_videos.sort(key=lambda x: x["views"], reverse=True)
        all_videos = all_videos[:3]
    
    return all_videos


def _process_api_response(response, api_key, channel):
    """Process YouTube API response and extract video information."""
    videos = []
    
    for item in response.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        
        snippet = item.get("snippet", {})
        
        video_data = {
            "channel_id": channel.channel_id,
            "channel_name": channel.channel_name,
            "video_id": video_id,
            "title": (snippet.get("title") or "")[:140],
            "description": (snippet.get("description") or "").strip(),
            "published_on": snippet.get("publishedAt"),
            "views": _fetch_video_views(video_id, api_key),
            "video_link": f"https://www.youtube.com/watch?v={video_id}"
        }
        
        videos.append(video_data)
    
    return videos


def _fetch_video_views(video_id, api_key):
    """Fetch view count for a specific video."""
    try:
        res = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "key": api_key,
                "id": video_id,
                "part": "statistics"
            },
            timeout=30
        ).json()
        
        if res.get("items"):
            return int(res["items"][0]["statistics"].get("viewCount", 0))
    except Exception as e:
        frappe.log_error(
            f"View fetch failed ({video_id}): {str(e)}",
            "YouTube Stats Error"
        )
    
    return 0


def save_videos_to_tracker(tracker_name, videos_list):
    """
    Save fetched videos to tracker child table.
    
    Args:
        tracker_name: Name of YouTube Videos document
        videos_list: List of video dicts from fetch_videos_from_channels
        
    Returns:
        int: Number of videos added
    """
    tracker = frappe.get_doc("YouTube Videos", tracker_name)
    count = 0
    
    for video_data in videos_list:
        if any(v.video_id == video_data["video_id"] for v in tracker.videos):
            continue
        
        tracker.append("videos", {
            "channel_id": video_data["channel_id"],
            "video_id": video_data["video_id"],
            "title": video_data["title"],
            "published_on": video_data["published_on"],
            "views": video_data.get("views", 0),
            "video_link": video_data["video_link"],
            "transcript": video_data.get("description", ""),
            "is_related": 0,
            "analysis_reasoning": "",
            "social_media_post": None,
            "last_analyzed_on": None
        })
        
        count += 1
    
    if count > 0:
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
    
    return count
