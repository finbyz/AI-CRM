frappe.ui.form.on("Content Hub", {
	refresh(frm) {
		const button = frm.add_custom_button(__("Generate Ideas"), () => generate_ideas(frm));
		button.toggleClass("btn-primary", frm.doc.generation_status !== "Generating");
		button.prop("disabled", frm.doc.generation_status === "Generating");

		if (!frm.is_new() && frm.doc.ideas_child_table?.length) {
			frm.add_custom_button(__("Generate Posts"), () => open_post_dialog(frm));
		}
	},
});

async function generate_ideas(frm) {
	if (frm.is_new() || frm.is_dirty()) {
		await frm.save();
	}

	const response = await frm.call({
		doc: frm.doc,
		method: "generate_ideas",
		freeze: true,
		freeze_message: __("Generating ideas..."),
	});
	await frm.reload_doc();

	if (response.message?.status === "success") {
		frappe.show_alert({
			message: __("Ideas generated successfully"),
			indicator: "green",
		});
		return;
	}

	frappe.msgprint({
		title: __("Idea Generation Failed"),
		message: response.message?.error || __("Unable to generate ideas."),
		indicator: "red",
	});
}

function open_post_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Generate Posts"),
		fields: get_post_dialog_fields(frm),
		primary_action_label: __("Generate Posts"),
		primary_action: async (values) => generate_posts(frm, dialog, values),
	});
	dialog.show();
}

function get_post_dialog_fields(frm) {
	return [
		{
			fieldname: "idea_names",
			fieldtype: "MultiCheck",
			label: __("Content Ideas"),
			options: frm.doc.ideas_child_table.map((idea) => ({
				label: frappe.utils.escape_html(idea.idea_title),
				value: idea.name,
			})),
			columns: 1,
		},
		{ fieldname: "accounts_section", fieldtype: "Section Break", label: __("Accounts") },
		{
			fieldname: "linkedin_account",
			fieldtype: "Link",
			label: __("LinkedIn Account"),
			options: "LinkedIn Integration",
		},
		{
			fieldname: "twitter_account",
			fieldtype: "Link",
			label: __("X (Twitter) Account"),
			options: "Twitter Integration",
		},
		{
			fieldname: "reddit_account",
			fieldtype: "Link",
			label: __("Reddit Account"),
			options: "Reddit Integration",
		},
		{
			fieldname: "subreddit",
			fieldtype: "Data",
			label: __("Subreddit"),
			depends_on: "eval:doc.reddit_account",
			mandatory_depends_on: "eval:doc.reddit_account",
		},
	];
}

async function generate_posts(frm, dialog, values) {
	if (!values.idea_names?.length) {
		frappe.msgprint(__("Select at least one content idea."));
		return;
	}

	const targets = get_selected_targets(values);
	if (!targets.length) {
		frappe.msgprint(__("Select at least one social media account."));
		return;
	}

	dialog.disable_primary_action();
	frappe.dom.freeze(__("Queueing post generation..."));
	let post_count = 0;
	try {
		for (const idea_name of values.idea_names) {
			const response = await frm.call({
				doc: frm.doc,
				method: "generate_posts_from_idea",
				args: { idea_name, targets },
			});
			post_count += response.message?.posts?.length || 0;
		}
		dialog.hide();
		frappe.show_alert({
			message: __("{0} post(s) queued", [post_count]),
			indicator: "green",
		});
	} finally {
		frappe.dom.unfreeze();
		dialog.enable_primary_action();
	}
}

function get_selected_targets(values) {
	return [
		{ credential_type: "LinkedIn Integration", credential: values.linkedin_account },
		{ credential_type: "Twitter Integration", credential: values.twitter_account },
		{
			credential_type: "Reddit Integration",
			credential: values.reddit_account,
			subreddit: values.subreddit?.trim(),
		},
	].filter((target) => target.credential);
}
