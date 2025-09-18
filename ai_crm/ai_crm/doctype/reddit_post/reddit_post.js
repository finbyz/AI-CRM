frappe.ui.form.on('Reddit Post', {
    refresh: function(frm) {
        if (frm.doc.url) {
            frm.add_custom_button(__('Open Reddit Post'), function() {
                window.open(frm.doc.url, '_blank');
            }, __('Actions'));
        }

        if (frm.doc.external_url) {
            frm.add_custom_button(__('Open External Link'), function() {
                window.open(frm.doc.external_url, '_blank');
            }, __('Actions'));
        }

        if (frm.doc.comment_status === 'Pending') {
            // AI Comment button
            frm.add_custom_button(__('Generate AI Comment'), function() {
                frappe.call({
                    method: 'ai_crm.reddit_api.generate_ai_comment',
                    args: {
                        post_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint(__('AI Comment posted successfully!<br><br><strong>Generated Comment:</strong><br><em>"{0}"</em>', [r.message.comment]));
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Failed to generate AI comment: {0}', [r.message.error || 'Unknown error']));
                        }
                    },
                    freeze: true,
                    freeze_message: __('Generating AI comment...')
                });
            }, __('AI Actions'));

            // Template Comment button
            frm.add_custom_button(__('Post Template Comment'), function() {
                frappe.call({
                    method: 'ai_crm.reddit_api.post_comment_manually',
                    args: {
                        post_name: frm.doc.name,
                        use_ai: false
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint(__('Template comment posted successfully!'));
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Failed to post template comment: {0}', [r.message.error || 'Unknown error']));
                        }
                    }
                });
            }, __('Actions'));

            // Test AI Comment (without posting)
            frm.add_custom_button(__('Preview AI Comment'), function() {
                frappe.call({
                    method: 'ai_crm.reddit_api.call_ai_agent',
                    args: {
                        agent_name: 'Reddit Comment Generator', // Default agent name
                        input_data: {
                            post_title: frm.doc.title,
                            post_content: frm.doc.selftext || '',
                            subreddit: frm.doc.subreddit,
                            post_type: frm.doc.post_type,
                            score: frm.doc.score,
                            author: frm.doc.author
                        }
                    },
                    callback: function(r) {
                        if (r.message && !r.message.error) {
                            let comment = r.message.comment || JSON.stringify(r.message, null, 2);
                            frappe.msgprint({
                                title: __('AI Generated Comment Preview'),
                                message: `<div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-top: 10px;">
                                    <strong>Generated Comment:</strong><br><br>
                                    <em>"${comment}"</em>
                                </div>`,
                                wide: true
                            });
                        } else {
                            frappe.msgprint(__('Failed to preview AI comment: {0}', [r.message.error || 'Unknown error']));
                        }
                    },
                    freeze: true,
                    freeze_message: __('Generating preview...')
                });
            }, __('AI Actions'));
        }

        // Add status indicators
        if (frm.doc.comment_status === 'Commented') {
            if (frm.doc.ai_generated_comment) {
                frm.dashboard.add_indicator(__('AI Commented'), 'blue');
            } else {
                frm.dashboard.add_indicator(__('Commented'), 'green');
            }
        } else if (frm.doc.comment_status === 'Failed') {
            frm.dashboard.add_indicator(__('Comment Failed'), 'red');
        } else if (frm.doc.comment_status === 'Pending') {
            frm.dashboard.add_indicator(__('Comment Pending'), 'orange');
        }

        // Show AI comment if exists
        if (frm.doc.ai_generated_comment) {
            frm.dashboard.add_comment(__('AI Generated: "{0}"', [frm.doc.ai_generated_comment]), 'blue', true);
        }

        // Show comment error if exists
        if (frm.doc.comment_error) {
            frm.dashboard.add_comment(frm.doc.comment_error, 'red', true);
        }

        // Add post type indicator
        let type_color = {
            'Text': 'grey',
            'Image': 'green',
            'Video': 'purple',
            'Link': 'orange'
        };
        frm.dashboard.add_indicator(__(frm.doc.post_type || 'Text'), type_color[frm.doc.post_type] || 'grey');

        // Add score indicator if significant
        if (frm.doc.score > 100) {
            frm.dashboard.add_indicator(__('Hot Post ({0} score)', [frm.doc.score]), 'red');
        } else if (frm.doc.score > 10) {
            frm.dashboard.add_indicator(__('Popular ({0} score)', [frm.doc.score]), 'orange');
        }
    },

    onload: function(frm) {
        // Format display fields
        if (frm.doc.score) {
            frm.set_df_property('score', 'description', __('Current Reddit score/upvotes'));
        }
        
        if (frm.doc.num_comments) {
            frm.set_df_property('num_comments', 'description', __('Number of comments on Reddit'));
        }
    }
});