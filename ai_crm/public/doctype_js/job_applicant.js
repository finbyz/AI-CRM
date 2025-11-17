frappe.ui.form.on("Job Applicant", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__('Analyze'), () => {
            frappe.confirm(
                __('This will analyze applicant resume and provide score for each skill. Continue?'),
                () => {
                    frappe.call({
                        method: 'ai_crm.resume_ranker.api.analyze_candidate',
                        args: {
                            applicant_name: frm.doc.name,
                            job_title: frm.doc.job_title,
                            resume_path: frm.doc.resume_attachment
                        },
                        freeze: true,
                        freeze_message: __('🔍 Extracting skills with AI...'),

                        callback(r) {
                            if (r.message?.success) {
                                frappe.show_alert({
                                    message: __('✅ Analysis completed successfully'),
                                    indicator: 'green'
                                }, 10);

                                frm.reload_doc();
                            } else {
                                frappe.msgprint({
                                    title: __('❌ Extraction Failed'),
                                    message: r.message?.message || 'Skill extraction failed.',
                                    indicator: 'red'
                                });
                            }
                        },

                        error() {
                            frappe.msgprint({
                                title: __('❌ Error'),
                                message: __('Failed to connect to AI service.'),
                                indicator: 'red'
                            });
                        }
                    });
                }
            );
        });
    }
});
