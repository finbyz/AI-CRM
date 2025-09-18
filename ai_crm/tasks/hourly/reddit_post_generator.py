# scheduler_tasks.py (Updated for automatic AI comments)
import frappe
from frappe.utils import now, add_to_date, get_datetime
from ai_crm.reddit_api import RedditAPI, store_posts_in_db, generate_ai_comment_internal

def fetch_and_store_posts():
    """Scheduler task to fetch posts from all active subreddits"""
    try:
        frappe.logger().info("Starting scheduled task: fetch_and_store_posts")
        
        # Get all active subreddits that need monitoring
        subreddits = frappe.get_all(
            'Subreddit',
            filters={
                'is_active': 1,
                'docstatus': ['!=', 2]
            },
            fields=['name', 'subreddit_name', 'monitor_frequency', 'last_monitored']
        )
        
        if not subreddits:
            frappe.logger().info("No active subreddits found for monitoring")
            return
        
        reddit_api = RedditAPI()
        current_time = get_datetime()
        processed_count = 0
        
        for subreddit in subreddits:
            try:
                # Check if it's time to monitor this subreddit
                if subreddit.last_monitored:
                    next_monitor_time = add_to_date(
                        subreddit.last_monitored, 
                        minutes=subreddit.monitor_frequency
                    )
                    
                    if current_time < next_monitor_time:
                        frappe.logger().debug(
                            f"Skipping r/{subreddit.subreddit_name} - not time yet"
                        )
                        continue
                
                frappe.logger().info(f"Fetching posts from r/{subreddit.subreddit_name}")
                
                # Fetch posts
                posts = reddit_api.fetch_reddit_posts(subreddit.subreddit_name)
                
                if not posts:
                    frappe.logger().info(f"No new posts found in r/{subreddit.subreddit_name}")
                    continue
                
                # Store posts in database
                stored_count = store_posts_in_db(subreddit.subreddit_name, posts)
                
                # Update subreddit statistics
                subreddit_doc = frappe.get_doc('Subreddit', subreddit.name)
                subreddit_doc.last_monitored = current_time
                subreddit_doc.posts_fetched_today = (subreddit_doc.posts_fetched_today or 0) + stored_count
                subreddit_doc.total_posts_monitored = (subreddit_doc.total_posts_monitored or 0) + stored_count
                subreddit_doc.last_error = ''
                subreddit_doc.save()
                
                processed_count += 1
                frappe.logger().info(f"Stored {stored_count} new posts from r/{subreddit.subreddit_name}")
                
                # Auto-queue AI comments for new posts if enabled
                if subreddit_doc.auto_comment and subreddit_doc.use_ai_comments and subreddit_doc.ai_comment_agent:
                    # Get newly created posts
                    new_posts = frappe.get_all(
                        'Reddit Post',
                        filters={
                            'subreddit': subreddit.name,
                            'comment_status': 'Pending',
                            'creation': ['>=', add_to_date(current_time, minutes=-5)]  # Posts created in last 5 minutes
                        },
                        fields=['name', 'post_id']
                    )
                    
                    for post in new_posts:
                        frappe.enqueue(
                            'ai_crm.reddit_api.queue_ai_comment',
                            post_name=post.name,
                            queue='short',
                            timeout=300
                        )
                        frappe.logger().info(f"Queued AI comment for post {post.post_id}")
                
            except Exception as e:
                # Log error to subreddit
                try:
                    subreddit_doc = frappe.get_doc('Subreddit', subreddit.name)
                    subreddit_doc.last_error = str(e)[:500]
                    subreddit_doc.save()
                except Exception as save_error:
                    frappe.logger().error(f"Failed to save error to subreddit: {str(save_error)}")
                
                frappe.log_error(
                    message=str(e), 
                    title=f"Error processing subreddit {subreddit.subreddit_name}"
                )
        
        # Commit all changes
        frappe.db.commit()
        frappe.logger().info(f"Completed fetch_and_store_posts - processed {processed_count} subreddits")
        
    except Exception as e:
        frappe.log_error(
            message=str(e), 
            title="Error in fetch_and_store_posts scheduler task"
        )
        frappe.logger().error(f"Critical error in fetch_and_store_posts: {str(e)}")

def process_pending_ai_comments():
    """Scheduler task to process pending AI comments after delay period"""
    try:
        frappe.logger().info("Starting scheduled task: process_pending_ai_comments")
        
        current_time = get_datetime()
        total_processed = 0
        
        # Get all subreddits with AI commenting enabled
        ai_subreddits = frappe.get_all(
            'Subreddit',
            filters={
                'auto_comment': 1,
                'use_ai_comments': 1,
                'is_active': 1
            },
            fields=['name', 'subreddit_name', 'comment_delay_minutes', 'ai_comment_agent']
        )
        
        if not ai_subreddits:
            frappe.logger().info("No subreddits with AI commenting enabled")
            return
        
        for subreddit in ai_subreddits:
            if not subreddit.ai_comment_agent:
                continue
                
            try:
                # Calculate delay time
                delay_minutes = subreddit.comment_delay_minutes or 5
                delay_time = add_to_date(current_time, minutes=-delay_minutes)
                
                # Get posts ready for AI commenting
                pending_posts = frappe.get_all(
                    'Reddit Post',
                    filters={
                        'subreddit': subreddit.name,
                        'comment_status': 'Pending',
                        'created_utc': ['<=', delay_time]
                    },
                    fields=['name', 'post_id', 'title'],
                    limit=5  # Process 5 posts at a time to avoid rate limits
                )
                
                if not pending_posts:
                    continue
                
                frappe.logger().info(f"Processing {len(pending_posts)} AI comments for r/{subreddit.subreddit_name}")
                
                for post in pending_posts:
                    try:
                        # Generate AI comment
                        result = generate_ai_comment_internal(post.name, subreddit.ai_comment_agent)
                        
                        if result.get('success'):
                            total_processed += 1
                            frappe.logger().info(f"AI comment posted for post {post.post_id}")
                        else:
                            frappe.logger().error(f"AI comment failed for post {post.post_id}: {result.get('error')}")
                        
                        # Add delay between comments to avoid rate limiting
                        import time
                        time.sleep(3)
                        
                    except Exception as e:
                        frappe.log_error(
                            message=str(e),
                            title=f"Error processing AI comment for post {post.post_id}"
                        )
                
            except Exception as e:
                frappe.log_error(
                    message=str(e),
                    title=f"Error processing AI comments for subreddit {subreddit.subreddit_name}"
                )
        
        # Commit all changes
        frappe.db.commit()
        frappe.logger().info(f"Completed process_pending_ai_comments - processed {total_processed} comments")
        
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Error in process_pending_ai_comments scheduler task"
        )
        frappe.logger().error(f"Critical error in process_pending_ai_comments: {str(e)}")

def cleanup_old_posts():
    """Clean up old Reddit posts to prevent database bloat"""
    try:
        frappe.logger().info("Starting scheduled task: cleanup_old_posts")
        
        # Delete posts older than 30 days that are already commented or failed
        cutoff_date = add_to_date(get_datetime(), days=-30)
        
        old_posts = frappe.get_all(
            'Reddit Post',
            filters={
                'created_utc': ['<', cutoff_date],
                'comment_status': ['in', ['Commented', 'Failed', 'Skipped']]
            },
            fields=['name']
        )
        
        deleted_count = 0
        for post in old_posts:
            try:
                frappe.delete_doc('Reddit Post', post.name)
                deleted_count += 1
            except Exception as e:
                frappe.logger().error(f"Error deleting old post {post.name}: {str(e)}")
        
        frappe.db.commit()
        frappe.logger().info(f"Cleaned up {deleted_count} old posts")
        
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Error in cleanup_old_posts scheduler task"
        )

def reset_daily_counters():
    """Reset daily post counters at midnight"""
    try:
        frappe.logger().info("Starting scheduled task: reset_daily_counters")
        
        frappe.db.sql("UPDATE `tabSubreddit` SET posts_fetched_today = 0")
        frappe.db.commit()
        
        frappe.logger().info("Successfully reset daily counters")
        
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Error in reset_daily_counters scheduler task"
        )

# Test functions
@frappe.whitelist()
def test_fetch_and_store():
    """Test function to manually trigger fetch_and_store_posts"""
    try:
        fetch_and_store_posts()
        return {"status": "success", "message": "fetch_and_store_posts completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@frappe.whitelist() 
def test_ai_comments():
    """Test function to manually trigger process_pending_ai_comments"""
    try:
        process_pending_ai_comments()
        return {"status": "success", "message": "process_pending_ai_comments completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def test_cleanup():
    """Test function to manually trigger cleanup_old_posts"""
    try:
        cleanup_old_posts()
        return {"status": "success", "message": "cleanup_old_posts completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}