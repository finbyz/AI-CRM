frappe.ui.form.on("Content Hub", {
    refresh: function (frm) {
        frm.add_custom_button("Generate Ideas", function () {
            console.log("🚀 Calling generate_linkedin_ideas for doc:", frm.doc.name);

            frm.call({
                doc: frm.doc,
                method: "generate_linkedin_ideas",
                freeze: true,
                freeze_message: "Generating ideas...",
                callback: function (r) {
                    console.log("📩 Response from generate_linkedin_ideas:", r);

                    if (r.message?.status === "success") {
                        frappe.show_alert({
                            message: `✅ Ideas generated for ${r.message.docname}`,
                            indicator: "green"
                        });
                        frm.reload_doc();
                    } else {
                        frappe.show_alert({
                            message: `❌ Error: ${r.message?.error || "Unknown error"}`,
                            indicator: "red"
                        });
                    }
                }
            });
        });
    }
});

frappe.ui.form.on("ContentHubIdea", {
    form_render: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let $wrapper = frm.fields_dict["ideas_child_table"]
            .grid.grid_rows_by_docname[cdn]
            .grid_form.fields_dict.description.$wrapper;

        // Avoid duplicate button
        if ($wrapper.find(".btn-generate-idea-" + cdn).length) return;

        let btn = $(`
            <button class="btn btn-xs btn-primary btn-generate-idea-${cdn}" style="margin-top:5px;">
                <i class="fa fa-magic"></i> Generate From This Idea
            </button>
        `);
        $wrapper.append(btn);

        btn.on("click", function () {
            console.log("✨ Generating post from idea:", row);

            (frm.is_dirty() ? frm.save() : Promise.resolve()).then(() => {
                frm.call({
                    doc: frm.doc,
                    method: "generate_post_from_idea",
                    args: {
                        idea_title: row.idea_title,
                        idea_description: row.description
                    },
                    freeze: true,
                    freeze_message: "Generating post content...",
                    callback: function (r) {
                        console.log("📩 Response from generate_post_from_idea:", r);

                        if (r.message?.status === "success") {
                            frappe.show_alert({
                                message: `✅ Post created: ${r.message.post_name}`,
                                indicator: "green"
                            });
                            frm.reload_doc();
                        } else {
                            frappe.show_alert({
                                message: `❌ Error: ${r.message?.error || "Unknown error"}`,
                                indicator: "red"
                            });
                        }
                    }
                });
            });
        });
    }
});
