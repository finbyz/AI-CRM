frappe.ui.form.on('Subreddit', {
    refresh: function(frm) {
        // Add custom buttons
        frm.add_custom_button(__('Fetch Posts Now'), function() {
            frappe.call({
                method: 'ai_crm.reddit_api.fetch_posts_manually',
                args: {
                    subreddit_name: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
                        frappe.msgprint(__('Fetched {0} new posts', [r.message.count]));
                        frm.reload_doc();
                    }
                },
                freeze: true,
                freeze_message: __('Fetching posts...')
            });
        }, __('Actions'));
        
        frm.add_custom_button(__('View Posts'), function() {
            frappe.route_options = {
                'subreddit': frm.doc.name
            };
            frappe.set_route('List', 'Reddit Post');
        }, __('Actions'));
        
        frm.add_custom_button(__('Post Statistics'), function() {
            frappe.call({
                method: 'ai_crm.reddit_api.get_post_statistics',
                args: {
                    subreddit_name: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
                        let stats = r.message;
                        let msg = `
                            <div class="reddit-stats">
                                <h4>Post Statistics for r/${frm.doc.subreddit_name}</h4>
                                <table class="table table-bordered">
                                    <tr><td><strong>Total Posts:</strong></td><td>${stats.total_posts}</td></tr>
                                    <tr><td><strong>Posts Today:</strong></td><td>${stats.posts_today}</td></tr>
                                    <tr><td><strong>Commented:</strong></td><td>${stats.commented}</td></tr>
                                    <tr><td><strong>Pending:</strong></td><td>${stats.pending}</td></tr>
                                    <tr><td><strong>Failed:</strong></td><td>${stats.failed}</td></tr>
                                    <tr><td><strong>Average Score:</strong></td><td>${stats.avg_score}</td></tr>
                                </table>
                            </div>
                        `;
                        frappe.msgprint(msg);
                    }
                }
            });
        }, __('Reports'));
        
        // Add indicator for active status
        if (frm.doc.is_active) {
            frm.dashboard.add_indicator(__('Active'), 'green');
        } else {
            frm.dashboard.add_indicator(__('Inactive'), 'red');
        }
        
        // Show last error if exists
        if (frm.doc.last_error) {
            frm.dashboard.add_comment(frm.doc.last_error, 'red', true);
        }
    },
    
    subreddit_name: function(frm) {
        // Auto-remove r/ prefix
        if (frm.doc.subreddit_name && frm.doc.subreddit_name.startsWith('r/')) {
            frm.set_value('subreddit_name', frm.doc.subreddit_name.substring(2));
        }
    }
});