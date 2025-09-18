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
                                    <tr><td><strong>AI Commented:</strong></td><td>${stats.ai_commented || 0}</td></tr>
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

        // Test AI Agent button
        if (frm.doc.use_ai_comments && frm.doc.ai_comment_agent) {
            frm.add_custom_button(__('Test AI Agent'), function() {
                // Get a random pending post to test
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Reddit Post',
                        filters: {
                            subreddit: frm.doc.name,
                            comment_status: 'Pending'
                        },
                        limit_page_length: 1,
                        fields: ['name', 'title']
                    },
                    callback: function(r) {
                        if (r.message && r.message.length > 0) {
                            let post = r.message[0];
                            frappe.call({
                                method: 'ai_crm.reddit_api.generate_ai_comment',
                                args: {
                                    post_name: post.name,
                                    agent_name: frm.doc.ai_comment_agent
                                },
                                callback: function(ai_r) {
                                    if (ai_r.message && ai_r.message.success) {
                                        frappe.msgprint(__('AI Test Successful! Generated comment: <br><br><em>"{0}"</em>', [ai_r.message.comment]));
                                    } else {
                                        frappe.msgprint(__('AI Test Failed: {0}', [ai_r.message.error || 'Unknown error']));
                                    }
                                }
                            });
                        } else {
                            frappe.msgprint(__('No pending posts found to test AI agent'));
                        }
                    }
                });
            }, __('AI Actions'));
        }

        // Add indicator for active status
        if (frm.doc.is_active) {
            frm.dashboard.add_indicator(__('Active'), 'green');
        } else {
            frm.dashboard.add_indicator(__('Inactive'), 'red');
        }

        // Add AI indicator
        if (frm.doc.use_ai_comments && frm.doc.ai_comment_agent) {
            frm.dashboard.add_indicator(__('AI Enabled'), 'blue');
        }

        // Show last error if exists
        if (frm.doc.last_error) {
            frm.dashboard.add_comment(frm.doc.last_error, 'red', true);
        }

        // Load AI Agents dropdown
        if (frm.doc.use_ai_comments) {
            frm.set_query('ai_comment_agent', function() {
                return {
                    filters: {
                        'agent_type': 'Structured Chat Agent'
                    }
                };
            });
        }
    },

    subreddit_name: function(frm) {
        // Auto-remove r/ prefix
        if (frm.doc.subreddit_name && frm.doc.subreddit_name.startsWith('r/')) {
            frm.set_value('subreddit_name', frm.doc.subreddit_name.substring(2));
        }
    },

    use_ai_comments: function(frm) {
        // Clear AI agent if AI comments disabled
        if (!frm.doc.use_ai_comments) {
            frm.set_value('ai_comment_agent', '');
        }
        
        // Refresh to show/hide AI agent field
        frm.refresh_fields();
    },

    ai_comment_agent: function(frm) {
        // Validate AI agent when selected
        if (frm.doc.ai_comment_agent) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'AI Agent',
                    name: frm.doc.ai_comment_agent
                },
                callback: function(r) {
                    if (r.message) {
                        let agent = r.message;
                        if (!agent.structured_output) {
                            frappe.msgprint(__('Warning: Selected AI Agent does not have structured output configured. It may not work properly for Reddit comments.'));
                        }
                    }
                }
            });
        }
    },

    auto_comment: function(frm) {
        // Show warning about AI vs Template
        if (frm.doc.auto_comment) {
            frappe.msgprint({
                title: __('Auto Comment Settings'),
                message: __('You can use either AI Generated Comments or Template Comments. AI comments will be used if enabled, with template as fallback.'),
                indicator: 'blue'
            });
        }
    }
});