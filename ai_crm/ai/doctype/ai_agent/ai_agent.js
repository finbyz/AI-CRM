// Copyright (c) 2025, sandeep and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Agent", {
    refresh(frm) {
        if (frm.doc.name) {
            frm.add_custom_button(__("Test Agent"), function() {
                frm.trigger("show_test_dialog");
            }, __("Actions"));
        }
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
    },
    
    show_test_dialog(frm) {
        let dialog = new frappe.ui.Dialog({
            title: __("Test AI Agent"),
            fields: [
                {
                    fieldtype: "Small Text",
                    fieldname: "query",
                    label: __("Query"),
                    reqd: 1,
                    placeholder: __("Enter your test query here...")
                },
                {
                    fieldtype: "Section Break",
                    fieldname: "variables_section",
                    label: __("Variables (Optional)")
                },
                {
                    fieldtype: "HTML",
                    fieldname: "variables_container",
                    options: `
                        <div id="variables-container">
                            <div class="variable-row" style="margin-bottom: 10px;">
                                <div class="row">
                                    <div class="col-md-5">
                                        <input type="text" class="form-control var-key" placeholder="Variable Name (e.g., name, age, topic)" />
                                    </div>
                                    <div class="col-md-6">
                                        <input type="text" class="form-control var-value" placeholder="Value for this variable" />
                                    </div>
                                    <div class="col-md-1">
                                        <button type="button" class="btn btn-sm btn-danger remove-var" style="display: none;">
                                            <i class="fa fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div style="margin-top: 10px;">
                            <button type="button" class="btn btn-sm btn-secondary" id="add-variable-btn">
                                <i class="fa fa-plus"></i> Add Variable
                            </button>
                        </div>
                    `
                }
            ],
            primary_action_label: __("Test"),
            primary_action: function(values) {
                frm.trigger("test_agent", values, dialog);
                dialog.hide();
            }
        });
        
        dialog.show();
        
        // Add event listeners
        dialog.fields_dict.variables_container.$wrapper.find("#add-variable-btn").on("click", function() {
            add_variable_row(dialog);
        });
        
        dialog.fields_dict.variables_container.$wrapper.on("click", ".remove-var", function() {
            $(this).closest(".variable-row").remove();
            update_remove_buttons(dialog);
        });
        
        // Initial setup
        update_remove_buttons(dialog);
    },
    
    add_variable_row(dialog) {
        let container = dialog.fields_dict.variables_container.$wrapper.find("#variables-container");
        let new_row = $(`
            <div class="variable-row" style="margin-bottom: 10px;">
                <div class="row">
                    <div class="col-md-5">
                        <input type="text" class="form-control var-key" placeholder="Variable Name (e.g., name, age, topic)" />
                    </div>
                    <div class="col-md-6">
                        <input type="text" class="form-control var-value" placeholder="Value for this variable" />
                    </div>
                    <div class="col-md-1">
                        <button type="button" class="btn btn-sm btn-danger remove-var">
                            <i class="fa fa-times"></i>
                        </button>
                    </div>
                </div>
            </div>
        `);
        
        container.append(new_row);
        update_remove_buttons(dialog);
    },
    
    update_remove_buttons(dialog) {
        let rows = dialog.fields_dict.variables_container.$wrapper.find(".variable-row");
        rows.find(".remove-var").toggle(rows.length > 1);
    },
    
    test_agent(frm, values, dialog) {
        // Build variables object from dynamic fields
        let variables = {};
        dialog.fields_dict.variables_container.$wrapper.find(".variable-row").each(function() {
            let key = $(this).find(".var-key").val();
            let value = $(this).find(".var-value").val();
            
            if (key && value) {
                variables[key] = value;
            }
        });
        
        frappe.call({
            method: "ai_crm.ai_crm.ai.doctype.ai_agent.ai_agent.test_agent",
            args: {
                docname: frm.doc.name,
                query: values.query,
                variables: variables
            },
            callback: function(r) {
                if (r.message) {
                    frm.trigger("show_test_result", r.message);
                }
            },
            error: function(err) {
                frappe.msgprint(__("Error testing agent: ") + err.message);
            }
        });
    },
    
    show_test_result(frm, result) {
        let dialog = new frappe.ui.Dialog({
            title: __("Test Result"),
            fields: [
                {
                    fieldtype: "HTML",
                    fieldname: "result_html",
                    options: frm.trigger("format_test_result", result)
                }
            ],
            primary_action_label: __("Close"),
            primary_action: function() {
                dialog.hide();
            }
        });
        
        dialog.fields_dict.result_html.$wrapper.html(frm.trigger("format_test_result", result));
        dialog.show();
    },
    
    format_test_result(frm, result) {
        let html = `
            <div class="test-result-container" style="padding: 15px;">
                <div class="test-status" style="margin-bottom: 15px;">
                    <h4 style="color: ${result.success ? 'green' : 'red'};">
                        ${result.success ? '✓ Test Successful' : '✗ Test Failed'}
                    </h4>
                </div>
                
                <div class="test-details" style="margin-bottom: 15px;">
                    <strong>Query:</strong> ${result.query}<br>
                    <strong>Agent Type:</strong> ${result.agent_type}<br>
                    <strong>LLM:</strong> ${result.llm}<br>
                    ${result.variables && Object.keys(result.variables).length > 0 ? 
                        `<strong>Variables:</strong> <pre style="background: #f5f5f5; padding: 5px; border-radius: 3px;">${JSON.stringify(result.variables, null, 2)}</pre>` : 
                        ''
                    }
                </div>
                
                <div class="test-response" style="margin-bottom: 15px;">
                    <strong>Response:</strong>
                    <div style="background: #f9f9f9; padding: 10px; border-radius: 5px; margin-top: 5px; max-height: 300px; overflow-y: auto;">
                        ${result.success ? 
                            (typeof result.response === 'object' ? 
                                `<pre>${JSON.stringify(result.response, null, 2)}</pre>` : 
                                result.response
                            ) : 
                            `<span style="color: red;">${result.error}</span>`
                        }
                    </div>
                </div>
            </div>
        `;
        return html;
    }
});
