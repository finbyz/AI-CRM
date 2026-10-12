// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("YouTube Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Channels"), () => save_then(frm, () => test_channels_dialog(frm)));
		frm.add_custom_button(__("Import Video"), () => import_video_dialog());
	},
});

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

function save_then(frm, callback) {
	if (frm.is_dirty()) {
		frm.save().then(callback);
	} else {
		callback();
	}
}

function test_channels_dialog(frm) {
	const channels = (frm.doc.channels || [])
		.filter((row) => row.channel_id)
		.map((row) => ({
			channel_title: row.channel_title || row.channel_name,
			channel_id: row.channel_id,
			last_fetched_on: row.last_fetched_on,
		}));
	if (!channels.length) {
		frappe.msgprint(__("Add a channel first."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Test Channels"),
		size: "large",
		fields: [
			{
				fieldname: "channels",
				fieldtype: "Table",
				label: __("Select the channels to test"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: false,
				data: channels,
				fields: [
					{ fieldname: "channel_title", fieldtype: "Data", label: __("Channel"), in_list_view: 1, read_only: 1, columns: 4 },
					{ fieldname: "channel_id", fieldtype: "Data", label: __("Channel ID"), in_list_view: 1, read_only: 1, columns: 4 },
					{ fieldname: "last_fetched_on", fieldtype: "Datetime", label: __("Last Fetched"), in_list_view: 1, read_only: 1, columns: 2 },
				],
			},
			{
				fieldname: "max_results",
				fieldtype: "Int",
				label: __("Latest videos per channel"),
				default: 3,
				description: __("Up to 10. Already imported videos are skipped. Scheduled fetching is not affected."),
			},
		],
		primary_action_label: __("Fetch & Process"),
		primary_action(values) {
			const selected = dialog.fields_dict.channels.grid.get_selected_children();
			const rows = selected.length ? selected : values.channels;
			frappe
				.call({
					method: "ai_crm.social_media.doctype.youtube_settings.youtube_settings.test_channels",
					args: { channel_ids: rows.map((row) => row.channel_id), max_results: values.max_results },
					freeze: true,
				})
				.then((r) => {
					dialog.hide();
					frappe.msgprint({
						title: __("Test Started"),
						indicator: "green",
						message: __("Fetching {0} channel(s) in the background. Track progress in {1}.", [
							rows.length,
							`<a href="/app/youtube-videos/${r.message}">${r.message}</a>`,
						]),
					});
				});
		},
	});
	dialog.show();
	dialog.$wrapper.find(".modal-body").prepend(
		`<p class="text-muted small">${__("Tick rows to test only those channels; with none ticked, all are tested.")}</p>`
	);
}

function import_video_dialog() {
	frappe.prompt(
		{
			fieldname: "url",
			fieldtype: "Data",
			label: __("YouTube Video URL"),
			reqd: 1,
			placeholder: "https://www.youtube.com/watch?v=...",
		},
		(values) => {
			frappe
				.call({
					method: "ai_crm.social_media.api.fetch_youtube_url",
					args: { url: values.url },
					freeze: true,
					freeze_message: __("Fetching video details..."),
				})
				.then((r) => {
					const link = `<a href="/app/youtube-videos/${r.message.tracker_name}">${r.message.tracker_name}</a>`;
					frappe.msgprint(
						r.message.already_exists
							? __("This video was already imported in {0}.", [link])
							: __("Imported {0}. Transcript, analysis and ideas run in the background; see {1}.", [
									frappe.utils.escape_html(r.message.title),
									link,
							  ])
					);
				});
		},
		__("Import Video"),
		__("Import")
	);
}
