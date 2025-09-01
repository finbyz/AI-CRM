// Copyright (c) 2025, sandeep and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Agent", {
	refresh(frm) {

	},
    agent_type(frm){
        if(frm.doc.agent_type == "Gemini Cache Agent"){
            frm.doc.llm_provider = null
            frm.doc.llm = null
            frm.refresh_fields()
        }
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
