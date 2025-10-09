
frappe.ui.form.on('Subreddit', {
    refresh: function(frm) {
        
        if (!frm.doc.__islocal) {
          
            frm.add_custom_button(__('Fetch Posts'), function() {
                fetch_posts_manually(frm);
            }, __('Actions'));
            
            if (frm.doc.auto_comment && frm.doc.use_ai_comments && frm.doc.ai_comment_agent) {
                frm.add_custom_button(__('Generate AI Comments'), function() {
                    generate_ai_comments_manually(frm);
                }, __('Actions'));
            }
           
            if (frm.doc.auto_comment && frm.doc.use_ai_comments && frm.doc.comment_revise_agent) {
                frm.add_custom_button(__('Revise AI Comments'), function() {
                    revise_ai_comments_manually(frm);
                }, __('Actions'));
            }
           
            frm.add_custom_button(__('View Posts'), function() {
                frappe.set_route('List', 'Reddit Post', {'subreddit': frm.doc.name});
            }, __('Actions'));
            
          
            frm.add_custom_button(__('Test Workflow'), function() {
                test_complete_workflow(frm);
            }, __('Debug'));
            
         
        }
    },
    
    auto_comment: function(frm) {
        frm.toggle_display(['use_ai_comments', 'comment_template', 'comment_delay_minutes'], frm.doc.auto_comment);
    },
    
    use_ai_comments: function(frm) {
        frm.toggle_display('ai_comment_agent', frm.doc.use_ai_comments);
        frm.toggle_display('comment_revise_agent', frm.doc.use_ai_comments);
        frm.toggle_display('comment_template', !frm.doc.use_ai_comments);
    }
});

function fetch_posts_manually(frm) {
    frappe.call({
        method: 'ai_crm.tasks.hourly.reddit_post_generator.trigger_fetch_manually',
        args: {
            subreddit_name: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Fetching posts from Reddit...'),
        callback: function(r) {
            if (r.message && r.message.count !== undefined) {
                frappe.msgprint(__('Fetched {0} new posts', [r.message.count]));
                frm.reload_doc();
            } else {
                frappe.msgprint(__('No new posts found or error occurred'));
            }
        }
    });
}

function generate_ai_comments_manually(frm) {
    frappe.call({
        method: 'ai_crm.tasks.hourly.reddit_post_generator.trigger_ai_comments_manually',
        args: {
            subreddit_name: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Generating AI comments...'),
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.msgprint(__('Generated AI comments for {0} posts', [r.message.processed]));
                frm.reload_doc();
            } else {
                frappe.msgprint(__('Error: {0}', [r.message.error || 'Unknown error']));
            }
        }
    });
}

function revise_ai_comments_manually(frm) {
    frappe.call({
        method: 'ai_crm.reddit_api.revise_ai_comments_bulk',
        args: {
            subreddit_name: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Revising AI comments...'),
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.msgprint(__('Revised {0} AI comments successfully', [r.message.revised_count]));
                frm.reload_doc();
            } else {
                frappe.msgprint(__('Error: {0}', [r.message.error || 'Unknown error']));
            }
        }
    });
}
