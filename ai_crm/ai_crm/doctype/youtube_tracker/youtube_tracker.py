# Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
import requests
from datetime import datetime, timedelta
from frappe.model.document import Document
from frappe.utils import now_datetime
import json
import time

class YouTubeTracker(Document):

    @frappe.whitelist()
    def fetch_channel_videos_by_frequency(self):
        settings = frappe.get_single("YouTube Settings")
        api_key = settings.get_password("api_key")
        transcript_api_token = settings.get_password("transcript_io_api_token")

        if not api_key:
            frappe.throw("YouTube API key is missing in YouTube Settings")
        if not transcript_api_token:
            frappe.throw("Transcript.io API token is missing in YouTube Settings")

        channels = settings.get("channels")
        if not channels:
            frappe.msgprint("No channels found in YouTube Settings. Please add channels first.")
            return "No channels found to fetch videos from."

        total_videos = 0
        now = frappe.utils.now_datetime()

        for channel in channels:
            try:
                frequency_days = int(channel.fetch_frequency or 1)
                if frequency_days < 1:
                    frequency_days = 1

                last_fetched_on = channel.last_fetched_on
                should_fetch = not last_fetched_on or (now >= last_fetched_on + timedelta(days=frequency_days))
                if not should_fetch:
                    continue

                # For weekly channels (frequency=7), fetch popular videos of the week
                is_weekly = (frequency_days == 7)
                
                if is_weekly:
                    # Fetch popular videos from the last 7 days
                    published_after = (now - timedelta(days=7)).isoformat("T") + "Z"
                else:
                    # Normal behavior: fetch new videos since last fetch
                    published_after = (last_fetched_on or (now - timedelta(days=7))).isoformat("T") + "Z"

                next_page_token = None

                while True:
                    search_url = "https://www.googleapis.com/youtube/v3/search"
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

                    res = requests.get(search_url, params=params, timeout=30).json()
                    if "error" in res:
                        frappe.log_error(
                            f"YouTube API Error for channel {channel.channel_name}: {res['error'].get('message','Unknown error')}",
                            "YouTube Fetch Error"
                        )
                        break

                    videos_list = []
                    for item in res.get("items", []):
                        video_id = item["id"]["videoId"]
                        snippet = item["snippet"]
                        title = snippet["title"][:140]
                        published_on = snippet["publishedAt"]
                        description = (snippet.get("description") or "").strip()

                        # Fetch views
                        views = 0
                        try:
                            stats_url = "https://www.googleapis.com/youtube/v3/videos"
                            stats_params = {"key": api_key, "id": video_id, "part": "statistics"}
                            stats_res = requests.get(stats_url, params=stats_params, timeout=30).json()
                            if stats_res.get("items"):
                                views = int(stats_res["items"][0]["statistics"].get("viewCount", 0))
                        except Exception as e:
                            frappe.log_error(f"Stats fetch failed for video {video_id}: {str(e)}", "YouTube Stats Error")

                        videos_list.append({
                            "video_id": video_id,
                            "title": title,
                            "published_on": published_on,
                            "views": views,
                            "description": description,
                        })

                    # For weekly channels, sort by views and limit to top 3
                    if is_weekly and videos_list:
                        videos_list.sort(key=lambda x: x["views"], reverse=True)
                        videos_list = videos_list[:3]

                    # Append videos to child table with transcript fetching
                    for vid in videos_list:
                        video_id = vid["video_id"]
                        title = vid["title"]
                        published_on = vid["published_on"]
                        video_link = f"https://www.youtube.com/watch?v={video_id}"
                        description = vid["description"]
                        transcript_text = description if description else ""

                        # Fetch transcript with rate limit handling
                        transcript_result = self._fetch_transcript_with_retry(
                            video_id,
                            transcript_api_token,
                            max_retries=2,
                            initial_delay=2
                        )
                        
                        if transcript_result["success"]:
                            transcript_text += transcript_result["transcript"]
                        elif transcript_result["status_code"] == 429:
                            transcript_text += "\n\n[Transcript pending - rate limited]"
                        else:
                            transcript_text += transcript_result["transcript"]

                        if any(v.video_id == video_id for v in self.videos):
                            continue

                        # Append child row
                        self.append("videos", {
                            "channel_id": channel.channel_id,
                            "video_id": video_id,
                            "title": title,
                            "published_on": published_on,
                            "views": vid["views"],
                            "video_link": video_link,
                            "transcript": transcript_text,
                            "is_related": 0,
                            "analysis_reasoning": "",
                            "social_media_post": None,
                            "last_analyzed_on": None
                        })
                        total_videos += 1

                    next_page_token = res.get("nextPageToken")
                    
                    # For weekly channels, we only need one page of top results
                    if is_weekly or not next_page_token:
                        break

                channel.last_fetched_on = now

            except Exception as e:
                frappe.log_error(f"Error fetching videos for channel {channel.channel_name}: {str(e)}", "YouTube Tracker Error")
                continue

        if total_videos > 0:
            self.save(ignore_permissions=True)
            settings.save(ignore_permissions=True)
            frappe.db.commit()

            # Check if there are pending transcripts
            pending_count = sum(1 for v in self.videos if v.transcript and "[Transcript pending - rate limited]" in v.transcript)
            
            if pending_count > 0:
                frappe.enqueue(
                    method='ai_crm.ai_crm.doctype.youtube_tracker.youtube_tracker.retry_failed_transcripts',
                    queue='long',
                    timeout=3600,
                    is_async=True,
                    job_name=f"retry_transcripts_{self.name}",
                    tracker_name=self.name,
                    enqueue_after_commit=True
                )
                return f"✅ Successfully fetched {total_videos} videos. {pending_count} transcripts will be retried, then AI analysis will start."
            else:
                frappe.enqueue(
                    method='ai_crm.ai_crm.doctype.youtube_tracker.youtube_tracker.run_ai_workflow_background',
                    queue='long',
                    timeout=7200,
                    is_async=True,
                    job_name=f"ai_workflow_youtube_{self.name}",
                    tracker_name=self.name,
                    enqueue_after_commit=True
                )
                return f"✅ Successfully fetched {total_videos} videos. AI analysis started in background."
        else:
            return "ℹ️ No new videos found based on the set frequencies."


    def _fetch_transcript_with_retry(self, video_id, api_token, max_retries=2, initial_delay=2):
        """Fetch transcript with exponential backoff retry logic."""
        for attempt in range(max_retries + 1):
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
                            chunks = [seg.get("text", "") for seg in tr_data[0]["tracks"][0].get("transcript", [])]
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
                
                elif tr_res.status_code == 429:
                    if attempt < max_retries:
                        delay = initial_delay * (2 ** attempt)
                        frappe.log_error(
                            f"Rate limit hit for video {video_id}. Retrying in {delay}s",
                            "YouTube Transcript Rate Limit"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        return {
                            "success": False,
                            "transcript": f"\n\n[Transcript API returned status: 429]",
                            "status_code": 429
                        }
                else:
                    return {
                        "success": False,
                        "transcript": f"\n\n[Transcript API returned status: {tr_res.status_code}]",
                        "status_code": tr_res.status_code
                    }
                    
            except Exception as e:
                if attempt < max_retries:
                    delay = initial_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                else:
                    frappe.log_error(
                        f"Transcript fetch error for video {video_id}: {str(e)}",
                        "YouTube Transcript Error"
                    )
                    return {
                        "success": False,
                        "transcript": f"\n\n[Transcript unavailable: {str(e)}]",
                        "status_code": 0
                    }
        
        return {
            "success": False,
            "transcript": "\n\n[Transcript fetch failed after retries]",
            "status_code": 0
        }


    @frappe.whitelist()
    def retry_pending_transcripts(self):
        """Retry fetching pending transcripts."""
        self.reload()
        
        settings = frappe.get_single("YouTube Settings")
        transcript_api_token = settings.get_password("transcript_io_api_token")
        
        if not transcript_api_token:
            frappe.throw("Transcript.io API token is missing in YouTube Settings")
        
        pending_videos = [v for v in self.videos if v.transcript and "[Transcript pending - rate limited]" in v.transcript]
        
        if not pending_videos:
            return "No pending transcripts to retry."
        
        success_count = 0
        
        for video in pending_videos:
            transcript_result = self._fetch_transcript_with_retry(
                video.video_id,
                transcript_api_token,
                max_retries=3,
                initial_delay=5
            )
            
            if transcript_result["success"]:
                current_transcript = video.transcript or ""
                current_transcript = current_transcript.replace("[Transcript pending - rate limited]", "")
                video.transcript = current_transcript + transcript_result["transcript"]
                success_count += 1
            
            time.sleep(60)
        
        self.save(ignore_permissions=True)
        frappe.db.commit()
        
        return f"✅ Successfully fetched {success_count} transcripts."


    @frappe.whitelist()
    def rerun_ai_workflow(self):
        """Manually re-run AI workflow on all videos."""
        for video in self.videos:
            video.last_analyzed_on = None
        
        self.save(ignore_permissions=True)
        frappe.db.commit()
        
        result = self.run_ai_workflow()
        
        if result.get("success"):
            return f"✅ AI Workflow completed: {result.get('processed', 0)} processed, {result.get('related', 0)} related"
        else:
            return f"❌ AI Workflow failed: {result.get('error', 'Unknown error')}"


    def run_ai_workflow(self):
        """Run Analysis Agent and Post Generation Agent on new videos."""
        self.reload()
        
        try:
            settings = frappe.get_single("YouTube Settings")

            if not settings.analysis_ai_agent:
                frappe.log_error("Analysis AI Agent not set", "YouTube AI Workflow")
                return {"success": False, "error": "Analysis AI Agent not configured"}

            if not settings.post_generation_ai_agent:
                frappe.log_error("Post Generation AI Agent not set", "YouTube AI Workflow")
                return {"success": False, "error": "Post Generation AI Agent not configured"}

            try:
                analysis_agent_doc = frappe.get_doc("AI Agent", settings.analysis_ai_agent)
                post_agent_doc = frappe.get_doc("AI Agent", settings.post_generation_ai_agent)
            except frappe.DoesNotExistError as e:
                frappe.log_error(f"AI Agent not found: {str(e)}", "YouTube AI Workflow")
                return {"success": False, "error": "AI Agent not found"}

            if not hasattr(analysis_agent_doc, 'agent_service') or not hasattr(post_agent_doc, 'agent_service'):
                frappe.log_error("Agent service not available", "YouTube AI Workflow")
                return {"success": False, "error": "Agent service not available"}

            analysis_agent = analysis_agent_doc.agent_service
            post_agent = post_agent_doc.agent_service

            processed_count = 0
            related_count = 0
            error_count = 0
            skipped_pending = 0

            # Process each unanalyzed video
            for idx, video in enumerate(self.videos):
                if video.last_analyzed_on:
                    continue
                
                if video.transcript and "[Transcript pending - rate limited]" in video.transcript:
                    skipped_pending += 1
                    continue

                try:
                    frappe.publish_realtime(
                        'ai_workflow_progress',
                        {'current': idx + 1, 'total': len(self.videos), 'video_title': video.title},
                        user=frappe.session.user
                    )

                    # Run Analysis Agent
                    analysis_result = self._run_analysis_agent(analysis_agent, video)
                    
                    if analysis_result is None:
                        error_count += 1
                        continue

                    video.is_related = analysis_result.get('is_related', 0)
                    video.analysis_reasoning = analysis_result.get('reasoning', 'No reasoning provided')
                    video.last_analyzed_on = now_datetime()
                    
                    self.save(ignore_permissions=True)
                    frappe.db.commit()
                    processed_count += 1

                    # Run Post Generation if related
                    if video.is_related:
                        post_result = self._run_post_generation_agent(post_agent, video)
                        
                        if post_result:
                            new_post = self._create_social_media_post(video, post_result)
                            
                            if new_post:
                                video.social_media_post = new_post.name
                                self.save(ignore_permissions=True)
                                frappe.db.commit()
                                related_count += 1

                except Exception as e:
                    error_count += 1
                    frappe.log_error(
                        f"AI workflow error for video {video.video_id}: {str(e)}\n{frappe.get_traceback()}",
                        "YouTube AI Workflow"
                    )
                    continue

            summary = f"Processed: {processed_count}, Related: {related_count}, Errors: {error_count}"
            if skipped_pending > 0:
                summary += f", Skipped: {skipped_pending}"
            
            frappe.publish_realtime(
                'ai_workflow_complete',
                {'message': summary},
                user=frappe.session.user
            )
            
            return {
                "success": True,
                "processed": processed_count,
                "related": related_count,
                "errors": error_count,
                "skipped_pending": skipped_pending
            }

        except Exception as e:
            error_msg = f"AI workflow error: {str(e)}\n{frappe.get_traceback()}"
            frappe.log_error(error_msg, "YouTube AI Workflow")
            return {"success": False, "error": str(e)}


    def _run_analysis_agent(self, agent, video):
        """Run analysis agent on a video."""
        try:
            input_data = {
                "title": video.title or "",
                "transcript": video.transcript or ""
            }

            result = agent.invoke(**input_data)

            if hasattr(result, 'is_related') and hasattr(result, 'reasoning'):
                return {
                    'is_related': int(result.is_related),
                    'reasoning': str(result.reasoning)
                }
            elif isinstance(result, dict):
                return {
                    'is_related': int(result.get('is_related', 0)),
                    'reasoning': str(result.get('reasoning', ''))
                }
            else:
                try:
                    parsed = json.loads(str(result))
                    return {
                        'is_related': int(parsed.get('is_related', 0)),
                        'reasoning': str(parsed.get('reasoning', ''))
                    }
                except:
                    frappe.log_error(
                        f"Unexpected analysis format: {type(result)}\n{str(result)}",
                        "YouTube Analysis"
                    )
                    return None

        except Exception as e:
            frappe.log_error(
                f"Analysis error for {video.video_id}: {str(e)}\n{frappe.get_traceback()}",
                "YouTube Analysis"
            )
            return None


    def _run_post_generation_agent(self, agent, video):
        """Run post generation agent on a video."""
        try:
            input_data = {
                "title": video.title or "",
                "transcript": video.transcript or ""
            }

            result = agent.invoke(**input_data)

            if hasattr(result, 'linkedin_post'):
                return {'linkedin_post': str(result.linkedin_post)}
            elif isinstance(result, dict):
                return {'linkedin_post': str(result.get('linkedin_post', ''))}
            else:
                try:
                    parsed = json.loads(str(result))
                    return {'linkedin_post': str(parsed.get('linkedin_post', ''))}
                except:
                    return {'linkedin_post': str(result)}

        except Exception as e:
            frappe.log_error(
                f"Post generation error for {video.video_id}: {str(e)}\n{frappe.get_traceback()}",
                "YouTube Post Gen"
            )
            return None


    def _create_social_media_post(self, video, post_result):
        """Create a Social Media Post document."""
        try:
            post_content = post_result.get('linkedin_post', '')
            
            if not post_content or post_content.strip() == '':
                frappe.log_error(
                    f"Empty post content for {video.video_id}",
                    "YouTube Post Creation"
                )
                return None

            new_post = frappe.new_doc("Social Media Post")
            new_post.title = video.title[:140]
            new_post.status = "Draft"
            new_post.content = post_content
            new_post.source_video_id = video.video_id
            new_post.source_video_link = video.video_link
            
            new_post.insert(ignore_permissions=True)
            frappe.db.commit()
            
            return new_post

        except Exception as e:
            frappe.log_error(
                f"Failed to create post for {video.video_id}: {str(e)}\n{frappe.get_traceback()}",
                "YouTube Post Creation"
            )
            return None


# Background jobs
def run_ai_workflow_background(tracker_name):
    """Background job to run AI workflow."""
    try:
        tracker = frappe.get_doc("YouTube Tracker", tracker_name)
        result = tracker.run_ai_workflow()
        
        frappe.publish_realtime(
            'ai_workflow_finished',
            result,
            user=frappe.session.user
        )
        
        return result
        
    except Exception as e:
        error_msg = f"Background AI error: {str(e)}\n{frappe.get_traceback()}"
        frappe.log_error(error_msg, "YouTube Workflow")
        return {"success": False, "error": str(e)}


def retry_failed_transcripts(tracker_name):
    """Background job to retry failed transcripts."""
    try:
        time.sleep(300)
        
        tracker = frappe.get_doc("YouTube Tracker", tracker_name)
        result = tracker.retry_pending_transcripts()
        
        if isinstance(result, str):
            frappe.log_error(f"Retry result: {result}", "Transcript Retry")
        
        # Run AI workflow after transcript retry
        frappe.enqueue(
            method='ai_crm.ai_crm.doctype.youtube_tracker.youtube_tracker.run_ai_workflow_background',
            queue='long',
            timeout=7200,
            is_async=True,
            job_name=f"ai_workflow_youtube_{tracker_name}",
            tracker_name=tracker_name
        )
        
        return result
        
    except Exception as e:
        error_msg = f"Transcript retry error: {str(e)}\n{frappe.get_traceback()}"
        frappe.log_error(error_msg, "Transcript Retry")
        return {"success": False, "error": str(e)}