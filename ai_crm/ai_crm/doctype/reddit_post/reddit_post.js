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
            frm.add_custom_button(__('Generate Comment'), function() {
                frappe.call({
                    method: 'ai_crm.reddit_api.generate_ai_comment',
                    args: {
                        post_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint(__('Generated Comment successfully!<br><br><strong>Generated Comment:</strong><br><em>"{0}"</em>', [r.message.comment]));
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Failed to generate AI comment: {0}', [r.message.error || 'Unknown error']));
                        }
                    },
                    freeze: true,
                    freeze_message: __('Generating comment...')
                });
            }, __('AI Actions'));
        }
        
        if (frm.doc.ai_generated_comment && frm.doc.comment_status !== 'Commented') {
            frm.add_custom_button(__('Revise Comment'), function() {
                frappe.call({
                    method: 'ai_crm.reddit_api.call_ai_agent_revise',
                    args: {
                        doc_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint(__('Comment revised successfully!<br><br><strong>Revised Comment:</strong><br><em>"{0}"</em>', [r.message.revised_comment]));
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Failed to revise comment: {0}', [r.message.error || 'Unknown error']));
                        }
                    },
                    freeze: true,
                    freeze_message: __('Revising comment...')
                });
            }, __('AI Actions'));
        }
        if (frm.doc.revise_comment && frm.doc.comment_status !== 'Commented') {
            frm.add_custom_button(__('Post Revised Comment'), function() {
                frappe.call({
                    method: 'ai_crm.reddit_api.post_revised_comment_to_reddit',
                    args: {
                        post_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint(__('Revised comment posted successfully!'));
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Failed: {0}', [r.message.error || 'Unknown error']));
                        }
                    },
                    freeze: true,
                    freeze_message: __('Posting revised comment to Reddit...')
                });
            }, __('AI Actions'));
        }
        if (frm.doc.comment_status === 'Ready' && frm.doc.ai_generated_comment) {
            frm.add_custom_button(__('Post to Reddit'), function() {
                frappe.call({
                    method: 'ai_crm.reddit_api.post_comment_to_reddit',
                    args: { post_name: frm.doc.name },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint(__('Comment posted successfully!'));
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Failed: {0}', [r.message.error]));
                        }
                    },
                    freeze: true,
                    freeze_message: __('Posting to Reddit...')
                });
            }, __('AI Actions'));
        }
    },

     onload: function(frm) {
       
        if (frm.doc.num_comments) {
            let fetchedCommentsCount = 0;
            if (frm.doc.existing_comments && frm.doc.existing_comments.includes('--- Comment #')) {
                fetchedCommentsCount = frm.doc.existing_comments.split('--- Comment #').length - 1;
            }
            
        }
        if (frm.doc.existing_comments) {
            const commentCount = frm.doc.existing_comments.split('--- Comment #').length - 1;
            frm.set_df_property('existing_comments', 'description', 
                __('Automatically fetched {0} comments from Reddit', [commentCount]));
        }
    }
});