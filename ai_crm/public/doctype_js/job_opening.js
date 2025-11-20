frappe.ui.form.on("Job Opening", {
    refresh: function (frm) {
        // Add AI Skills Extraction Button
        if (!frm.is_new()) {
            frm.add_custom_button(__('Extract Skills with AI'), function () {
                frappe.confirm(
                    __('This will extract skills from the job description using AI. Continue?'),
                    function () {
                        // Show loading indicator
                        frappe.show_alert({
                            message: __('🤖 AI is analyzing the job description...'),
                            indicator: 'blue'
                        }, 10);

                        frappe.call({
                            method: 'ai_crm.resume_ranker.api.extract_skills_from_job_opening',
                            args: {
                                job_opening_name: frm.doc.name
                            },
                            freeze: true,
                            freeze_message: __('🔍 Extracting skills with AI...'),
                            callback: function (r) {
                                console.log('AI Response:', r);

                                if (r.message && r.message.success) {
                                    // Success
                                    frappe.show_alert({
                                        message: __('✅ {0}', [r.message.message]),
                                        indicator: 'green'
                                    }, 7);
                                    frm.reload_doc();
                                } else {
                                    // Failure
                                    let error_msg = r.message && r.message.message
                                        ? r.message.message
                                        : 'Skill extraction failed. Check Error Log.';

                                    frappe.msgprint({
                                        title: __('❌ Extraction Failed'),
                                        message: error_msg,
                                        indicator: 'red'
                                    });

                                    console.error('Extraction Error:', r.message);
                                }
                            },
                            error: function (r) {
                                console.error('API Error:', r);
                                frappe.msgprint({
                                    title: __('❌ Error'),
                                    message: __('Failed to connect to AI service. Check console and Error Log.'),
                                    indicator: 'red'
                                });
                            }
                        });
                    }
                );
            });
        }
    }
});