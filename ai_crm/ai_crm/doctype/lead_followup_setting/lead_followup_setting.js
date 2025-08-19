// Copyright (c) 2025, sandeep and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lead Followup Setting", {
    provider: function(frm) {
        frm.set_value('llm', '');

        frm.set_query('llm', function() {
            return {
                filters: {
                    provider: frm.doc.provider
                }
            };
        });
    },
    research_provider: function(frm) {
        frm.set_value('research_llm', '');

        frm.set_query('research_llm', function() {
            return {
                filters: {
                    provider: frm.doc.research_llm
                }
            };
        });
    },

    onload: function(frm) {
        frm.set_query('llm', function() {
            if (frm.doc.provider) {
                return {
                    filters: {
                        provider: frm.doc.provider
                    }
                };
            }
        });
        frm.set_query('research_llm', function() {
            if (frm.doc.research_provider) {
                return {
                    filters: {
                        provider: frm.doc.research_provider
                    }
                };
            }
        });
    }
});
