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
    },

    // Auto-update platform when credential_type changes
    credential_type: function(frm) {
        if (frm.doc.credential_type === "Twitter Integration") {
            frm.set_value("platform", "X (Twitter)");
        } 
        else if (frm.doc.credential_type === "LinkedIn Integration") {
            frm.set_value("platform", "LinkedIn");
        } 
        else if (frm.doc.credential_type === "Reddit Integration") {
            frm.set_value("platform", "Reddit");
        }
    }
});

frappe.ui.form.on("Content Hub Idea", {
    form_render: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let $wrapper = frm.fields_dict["ideas_child_table"]
            .grid.grid_rows_by_docname[cdn]
            .grid_form.fields_dict.description.$wrapper;

        // Avoid duplicate button
        if ($wrapper.find(".btn-generate-idea-" + cdn).length) return;

        let btn = $(`<button class="btn btn-xs btn-primary btn-generate-idea-${cdn}" style="margin-top:5px;">
            <i class="fa fa-magic"></i> Generate Post From This Idea
        </button>`);

        $wrapper.append(btn);

        btn.on("click", function () {
            if (btn.data("running")) return;
            btn.data("running", true);
            btn.prop("disabled", true);

            const $icon = btn.find("i.fa");
            $icon.addClass("fa-spinner fa-pulse");

            const freeze_message = row.idea_title
                ? `Generating post from: ${row.idea_title}...`
                : "Generating post content...";
            frappe.dom.freeze(freeze_message);

            const savePromise = frm.is_dirty() ? frm.save() : Promise.resolve();

            savePromise.then(() => {
                return frm.call({
                    doc: frm.doc,
                    method: "generate_post_from_idea",
                    args: {
                        idea_title: row.idea_title,
                        idea_description: row.description
                    }
                });
            }).then((r) => {
                if (r && r.message && r.message.status === "success") {
                    const post_name = r.message.post_name;
                    frappe.msgprint({
                        title: __("Success"),
                        message: __(`<a href="/app/social-media-post/${post_name}" target="_blank">✅ Post created: ${post_name}</a>`),
                        indicator: "green"
                    });
                    frm.reload_doc();
                } else {
                    frappe.show_alert({
                        message: `❌ Error: ${r?.message?.error || "Unknown error"}`,
                        indicator: "red"
                    });
                }
            }).catch((err) => {
                console.error("generate_post_from_idea error:", err);
                frappe.show_alert({
                    message: "❌ Something went wrong. Check browser console for details.",
                    indicator: "red"
                });
            }).finally(() => {
                frappe.dom.unfreeze();
                btn.data("running", false);
                btn.prop("disabled", false);
                $icon.removeClass("fa-spinner fa-pulse");
            });
        });
    }
});
