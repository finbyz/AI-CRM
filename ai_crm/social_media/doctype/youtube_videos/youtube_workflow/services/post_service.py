# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
Post Service
Handles creation of Social Media Post documents
"""

import frappe


def create_social_media_post(video_title, video_id, video_link, post_content):
    """
    Create a Social Media Post document.
    
    Args:
        video_title: Video title
        video_id: YouTube video ID
        video_link: Full video URL
        post_content: Generated post content
        
    Returns:
        str: Name of created post document, or None if failed
    """
    try:
        if not post_content or not post_content.strip():
            frappe.log_error(
                f"Empty post content for video {video_id}",
                "YouTube Post Creation"
            )
            return None
        
        # Create new Social Media Post
        new_post = frappe.new_doc("Social Media Post")
        new_post.title = video_title[:140]
        new_post.status = "Draft"
        new_post.content = post_content
        new_post.source_video_id = video_id
        new_post.source_video_link = video_link
        
        new_post.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return new_post.name
        
    except Exception as e:
        frappe.log_error(
            f"Failed to create post for video {video_id}: {str(e)}",
            "YouTube Post Creation"
        )
        return None
