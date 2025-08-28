// Copyright (c) 2025, sandeep and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Agent", {
	refresh(frm) {

	},
    llm_provider: function(frm) {
        frm.set_value('llm', '');

        frm.set_query('llm', function() {
            return {
                filters: {
                    provider: frm.doc.llm_provider
                }
            };
        });
    }
});
