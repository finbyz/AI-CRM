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
            frm.add_custom_button(__('Post Comment Now'), function() {
                frappe.call({
                    method: 'ai_crm.reddit_api.post_comment_manually',
                    args: {
                        post_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint(__('Comment posted successfully!'));
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Failed to post comment: {0}', [r.message.error || 'Unknown error']));
                        }
                    }
                });
            }, __('Actions'));
        }
        
        // Add status indicators
        if (frm.doc.comment_status === 'Commented') {
            frm.dashboard.add_indicator(__('Commented'), 'green');
        } else if (frm.doc.comment_status === 'Failed') {
            frm.dashboard.add_indicator(__('Comment Failed'), 'red');
        } else if (frm.doc.comment_status === 'Pending') {
            frm.dashboard.add_indicator(__('Comment Pending'), 'orange');
        }
    }
});