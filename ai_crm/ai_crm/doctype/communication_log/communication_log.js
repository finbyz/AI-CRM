
frappe.ui.form.on('Communication Log', {
    refresh(frm) {
        
        if (!frm.is_new()) {
            frm.add_custom_button(__('Regenerate Emails'), function() {
                regenerate_emails(frm);
            }, __('Actions'));
        }
    }
});
function regenerate_emails(frm) {
    frappe.confirm(
        'This will clear existing unsent emails and generate new ones. Continue?',
        function() {
            
            frm.doc.communication_email = frm.doc.communication_email.filter(
                e => e.status !== 'Unsent'
            );
            
            frappe.call({
                method: 'ai_crm.ai_crm.doctype.communication_log.communication_log.regenerate_emails_for_log',
                args: {
                    'log_name': frm.doc.name
                },
                freeze: true,
                freeze_message: __('Generating emails...'),
                callback: function(r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: __('Success'),
                            indicator: 'green',
                            message: __('Generated {0} emails successfully!', [r.message.count])
                        });
                        frm.reload_doc();
                    }
                }
            });
        }
    );
}