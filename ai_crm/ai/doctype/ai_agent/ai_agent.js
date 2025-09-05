// Copyright (c) 2025, sandeep and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Agent", {
    refresh(frm) {
        
    },
    onload(frm){
        frm.trigger('agent_type')
        frm.trigger('llm_provider')
    },
    agent_type(frm) {
        if (frm.doc.agent_type == "Gemini Cache Agent") {
            frm.doc.llm_provider = null
            frm.doc.llm = null
            frm.refresh_fields()
        }
        let fields_to_hide_and_clear = ['output_schema', 'lc_agent_type', 'tools'];

        let hide_fields = ["Image Generation Agent"].includes(frm.doc.agent_type);

        fields_to_hide_and_clear.forEach(field => {
            frm.toggle_display(field, !hide_fields); 
            if (hide_fields) {
                frm.set_value(field, '');
            }
        });

    },
    llm_provider: function (frm) {
        frm.set_query('llm', function () {
            return {
                filters: {
                    provider: frm.doc.llm_provider,
                    supports_image_generation: frm.doc.agent_type === "Image Generation Agent"
                }
            };
        });
    }
});
