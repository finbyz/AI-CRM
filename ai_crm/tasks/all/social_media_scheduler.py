# Copyright (c) 2025, finbyz and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime


def schedule_social_media_posts():
    """
    This function is intended to be run by the Frappe scheduler.
    It fetches all 'Scheduled' social media posts where the 'post_on' datetime
    is in the past and attempts to publish them.
    """
    current_time = now_datetime()

    posts_to_publish = frappe.get_all(
        "Social Media Post",
        filters={
            "status": "Scheduled",
            "post_on": ["<=", current_time],
        },
        fields=["name"],
    )

    # If no posts are found, return early
    if not posts_to_publish:
        frappe.logger().info("No scheduled social media posts found to publish")
        return "No posts found with 'Scheduled' status and a past 'post_on' time."

    processed_posts = []
    failed_posts = []

    for post_meta in posts_to_publish:
        try:
            post_doc = frappe.get_doc("Social Media Post", post_meta.name)
            result = post_doc.post()

            if result and result.get("status") == "success":
                processed_posts.append(post_meta.name)
                frappe.logger().info(f"Successfully published scheduled post: {post_meta.name}")
            else:
                failed_posts.append(post_meta.name)
                frappe.logger().error(f"Failed to publish post {post_meta.name}: {result}")

        except Exception:
            failed_posts.append(post_meta.name)
            frappe.log_error(
                f"Failed to publish scheduled post: {post_meta.name}\n{frappe.get_traceback()}",
                "Scheduled Social Media Post Error",
            )

    # Return summary
    summary = f"Processed: {len(processed_posts)} posts successfully"
    if failed_posts:
        summary += f", Failed: {len(failed_posts)} posts"

    return summary
