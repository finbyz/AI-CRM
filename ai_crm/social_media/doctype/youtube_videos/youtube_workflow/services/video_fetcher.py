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


def fetch_videos_from_channels(channel_id=None, force=False, max_results=None):
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
    settings_changed = False
    now = now_datetime()

    for channel in channels:
        if channel_id and channel.channel_id != channel_id:
            continue

        try:
            if not force and not _should_fetch_channel(channel, now):
                continue
            
            channel_videos = _fetch_channel_videos(channel, api_key, now, max_results)
            all_videos.extend(channel_videos)
            
            channel.last_fetched_on = now
            settings_changed = True

        except Exception as e:
            frappe.log_error(
                f"Fetch error ({getattr(channel, 'channel_name', 'unknown')}): {str(e)}",
                "YouTube Video Fetcher"
            )
            continue
    
    if settings_changed:
        settings.save(ignore_permissions=True)

    return all_videos


def _should_fetch_channel(channel, current_time):
    """Check if channel should be fetched based on frequency."""
    frequency_days = max(int(channel.fetch_frequency or 5), 1)
    last_fetched_on = channel.last_fetched_on
    
    if not last_fetched_on:
        return True
    
    return current_time >= last_fetched_on + timedelta(days=frequency_days)


def _fetch_channel_videos(channel, api_key, now, max_results=None):
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
            "maxResults": max(1, min(int(max_results), 50)) if max_results else 50,
        }
        
        if next_page_token:
            params["pageToken"] = next_page_token
        
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        res = response.json()
        if "error" in res:
            message = res["error"].get("message", "Unknown YouTube API error")
            raise RuntimeError(message)
        
        page_videos = _process_api_response(res, api_key, channel)
        all_videos.extend(page_videos)

        if max_results and len(all_videos) >= int(max_results):
            all_videos = all_videos[:int(max_results)]
            break

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
    incoming_ids = {row["video_id"] for row in videos_list}
    existing_ids = set(frappe.get_all(
        "YouTube Video",
        filters={"video_id": ["in", list(incoming_ids)]},
        pluck="video_id",
    )) if incoming_ids else set()
    count = 0

    for video_data in videos_list:
        if video_data["video_id"] in existing_ids:
            continue
        
        tracker.append("videos", {
            "channel_id": video_data["channel_id"],
            "channel_name": video_data.get("channel_name"),
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
        
        existing_ids.add(video_data["video_id"])
        count += 1
    
    if count > 0:
        tracker.save(ignore_permissions=True)
    
    return count
