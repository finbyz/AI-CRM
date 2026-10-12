// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("YouTube Channel", {
	channel_name(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, { channel_id: "", channel_title: "" });
		if (!row.channel_name) return;

		frappe
			.call({
				method: "ai_crm.social_media.doctype.youtube_settings.youtube_settings.lookup_channel",
				args: { channel_name: row.channel_name },
			})
			.then((r) => {
				frappe.model.set_value(cdt, cdn, {
					channel_id: r.message.channel_id,
					channel_title: r.message.title,
				});
				frappe.show_alert({ message: __("Found: {0}", [r.message.title]), indicator: "green" });
			});
	},
});
