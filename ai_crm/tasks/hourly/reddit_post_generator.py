from frappe import _
from ai_crm.reddit_api import generate_ai_comment_internal
import frappe
from frappe.utils import get_datetime, add_to_date
import time
from ai_crm.reddit_api import (
    RedditAPI, 
    store_posts_in_db, 
    extract_comment_from_ai_result
)

def fetch_reddit_posts():
    
    try:
        subreddits = frappe.get_all(
            'Subreddit',
            filters={'is_active': 1},
            fields=['name', 'subreddit_name', 'sort_type', 'fetch_limit', 'reddit_integration']
        )
        
        if not subreddits:
            frappe.logger().info("No active subreddits found")
            return
        
        processed_count = 0
        
        for subreddit in subreddits:
            try:
                integration_name = subreddit.reddit_integration
                if not integration_name:
                    frappe.logger().warning(
                        f"No Reddit Integration for r/{subreddit.subreddit_name}, skipping"
                    )
                    continue
                if not frappe.db.exists('Reddit Integration', integration_name):
                    frappe.logger().error(
                        f"Integration '{integration_name}' not found for r/{subreddit.subreddit_name}"
                    )
                    continue
                
                integration_doc = frappe.get_doc('Reddit Integration', integration_name)
                if integration_doc.connection_status != 'Connected':
                    frappe.logger().warning(
                        f"Integration '{integration_name}' not connected, skipping r/{subreddit.subreddit_name}"
                    )
                    continue
                
                reddit_api = RedditAPI(integration_name)
                
                posts = reddit_api.fetch_reddit_posts(
                    subreddit.subreddit_name,
                    sort_type=subreddit.sort_type or 'new',
                    limit=subreddit.fetch_limit or 10
                )
                
                if not posts:
                    frappe.logger().info(
                        f"No new posts found for r/{subreddit.subreddit_name}"
                    )
                    continue
                
                frappe.logger().info(
                    f"Fetched {len(posts)} posts from r/{subreddit.subreddit_name}"
                )
               
                stored_count = store_posts_in_db(subreddit.subreddit_name, posts)
                
                subreddit_doc = frappe.get_doc('Subreddit', subreddit.name)
                subreddit_doc.last_monitored = frappe.utils.now()
                subreddit_doc.posts_fetched_today = (subreddit_doc.posts_fetched_today or 0) + stored_count
                subreddit_doc.total_posts_monitored = (subreddit_doc.total_posts_monitored or 0) + stored_count
                subreddit_doc.last_error = ''
                subreddit_doc.save(ignore_permissions=True)
                
                processed_count += 1
                frappe.logger().info(
                    f"✓ Stored {stored_count} new posts for r/{subreddit.subreddit_name}"
                )
                
                # Rate limiting
                time.sleep(2)
                
            except Exception as e:
                error_msg = f"Error fetching posts from r/{subreddit.subreddit_name}: {str(e)}"
                frappe.log_error(message=error_msg, title="Reddit Fetch Error")
                
                try:
                    subreddit_doc = frappe.get_doc('Subreddit', subreddit.name)
                    subreddit_doc.last_error = str(e)[:500]
                    subreddit_doc.save(ignore_permissions=True)
                except Exception as save_error:
                    frappe.logger().error(f"Failed to save error: {str(save_error)}")
        
        frappe.logger().info(f"✓ Completed fetch_reddit_posts - processed {processed_count} subreddits")
        
    except Exception as e:
        frappe.log_error(f"Error in fetch_reddit_posts scheduler: {str(e)}")

def process_pending_ai_comments():
    try:
        frappe.logger().info("Starting scheduled task: process_pending_ai_comments")
        
        current_time = get_datetime()
        total_processed = 0
        
        ai_subreddits = frappe.get_all(
            'Subreddit',
            filters={
                'auto_comment_enabled': 1,
                'use_ai_comments': 1,
                'is_active': 1
            },
            fields=[
                'name', 
                'subreddit_name', 
                'comment_delay_minutes', 
                'ai_comment_agent', 
                'reddit_integration'
            ]
        )
        if not ai_subreddits:
            frappe.logger().info("No subreddits with AI commenting enabled")
            return
        
        for subreddit in ai_subreddits:
            if not subreddit.ai_comment_agent:
                frappe.logger().warning(
                    f"No AI agent configured for r/{subreddit.subreddit_name}"
                )
                continue
            
            if not subreddit.reddit_integration:
                frappe.logger().warning(
                    f"No Reddit Integration for r/{subreddit.subreddit_name}"
                )
                continue
            
            try:
                delay_minutes = subreddit.comment_delay_minutes or 5
                delay_time = add_to_date(current_time, minutes=-delay_minutes)
                pending_posts = frappe.get_all(
                    'Reddit Post',
                    filters={
                        'subreddit': subreddit.name,
                        'comment_status': 'Pending',
                        'created_utc': ['<=', delay_time]
                    },
                    fields=['name', 'post_id', 'title'],
                    limit=5
                )
                
                if not pending_posts:
                    continue
                
                frappe.logger().info(
                    f"Processing {len(pending_posts)} AI comments for r/{subreddit.subreddit_name}"
                )
               
                reddit_api = RedditAPI(subreddit.reddit_integration)
                
                for post in pending_posts:
                    try:
                        
                        from ai_crm.reddit_api import generate_ai_comment_internal
                        result = generate_ai_comment_internal(
                            post.name, 
                            subreddit.ai_comment_agent
                        )

                        if result.get('success'):
                            post_doc = frappe.get_doc('Reddit Post', post.name)
                            
                            if post_doc.ai_generated_comment:
                                clean_comment = extract_comment_from_ai_result(
                                    post_doc.ai_generated_comment
                                )
                               
                                success = reddit_api.create_comment(post_doc.post_id, clean_comment)
                                
                                if success:
                                    post_doc.comment_status = 'Commented'
                                    post_doc.comment_posted_at = frappe.utils.now()
                                    post_doc.comment_error = ''
                                    post_doc.save(ignore_permissions=True)
                                    
                                    total_processed += 1
                                    frappe.logger().info(
                                        f" Posted AI comment to r/{subreddit.subreddit_name} - {post.post_id}"
                                    )
                                else:
                                    post_doc.comment_status = 'Failed'
                                    post_doc.comment_error = 'Failed to post comment to Reddit'
                                    post_doc.save(ignore_permissions=True)
                                    frappe.logger().error(
                                        f"Failed to post comment for {post.post_id}"
                                    )
                            else:
                                frappe.logger().error(
                                    f"No AI comment generated for {post.post_id}"
                                )
                        else:
                            frappe.logger().error(
                                f"AI comment generation failed for {post.post_id}: {result.get('error')}"
                            )
                        
                        time.sleep(3)
                        
                    except Exception as e:
                        frappe.log_error(
                            message=str(e),
                            title=f"Error processing AI comment for post {post.post_id}"
                        )
                
            except Exception as e:
                frappe.log_error(
                    message=str(e),
                    title=f"Error processing AI comments for r/{subreddit.subreddit_name}"
                )
        
        frappe.logger().info(
            f"✓ Completed process_pending_ai_comments - processed {total_processed} comments"
        )
        
    except Exception as e:
        frappe.log_error(f"Error in process_pending_ai_comments: {str(e)}")

def cleanup_old_posts():
    
    try:
        frappe.logger().info("Starting scheduled task: cleanup_old_posts")
        
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
                frappe.delete_doc('Reddit Post', post.name, ignore_permissions=True)
                deleted_count += 1
            except Exception as e:
                frappe.logger().error(f"Error deleting old post {post.name}: {str(e)}")
        
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
        
        frappe.logger().info("✓ Successfully reset daily counters")
        
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Error in reset_daily_counters scheduler task"
        )


@frappe.whitelist()
def trigger_fetch_manually(subreddit_name, integration_name=None):
    """Manually trigger post fetching for a specific subreddit"""
    try:
        from ai_crm.reddit_api import fetch_posts_manually
        
        if not integration_name:
            subreddit_doc = frappe.get_doc('Subreddit', subreddit_name)
            integration_name = subreddit_doc.reddit_integration
        
        if not integration_name:
            frappe.throw("No Reddit Integration configured for this subreddit")
        

        if not frappe.db.exists('Reddit Integration', integration_name):
            frappe.throw(f"Reddit Integration '{integration_name}' not found")
            
        integration = frappe.get_doc('Reddit Integration', integration_name)
        if integration.connection_status != 'Connected':
            frappe.throw(f"Reddit Integration '{integration_name}' is not connected")
        
        result = fetch_posts_manually(
            subreddit_name=subreddit_name,
            integration_name=integration_name,
            sort_type=subreddit_doc.sort_type or "hot",
            limit=5,
            time_filter="week"
        )
        
        if result.get('success'):
            posts_count = result.get('count', 0)
            if posts_count > 0:
                frappe.msgprint(
                    f"Successfully fetched {posts_count} new posts from r/{subreddit_name}",
                    indicator='green',
                    alert=True
                )
            else:
                frappe.msgprint(
                    f"No new posts found in r/{subreddit_name}",
                    indicator='blue',
                    alert=True
                )
            return result
        else:
            error_msg = result.get('error', 'Unknown error occurred')
            frappe.throw(f"Failed to fetch posts: {error_msg}")
        
    except Exception as e:
       
        frappe.log_error(
            title=f"Fetch Error - {subreddit_name[:30]}",  
            message=frappe.get_traceback()
        )
        frappe.throw(str(e))


@frappe.whitelist()
def trigger_ai_comments_manually(subreddit_name=None):
    """Manually trigger AI comment generation for pending posts"""
    try:
        from ai_crm.reddit_api import generate_ai_comment_internal
        
        filters = {'comment_status': 'Pending'}
        if subreddit_name:
            filters['subreddit'] = subreddit_name
            
        pending_posts = frappe.get_all(
            'Reddit Post',
            filters=filters,
            fields=['name'],
            limit=10
        )
        
        processed = 0
        errors = 0
        
        for post in pending_posts:
            try:
                result = generate_ai_comment_internal(post.name)
                if result.get('success'):
                    processed += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                frappe.log_error(str(e))
        
        return {
            'success': True,
            'processed': processed,
            'errors': errors
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}