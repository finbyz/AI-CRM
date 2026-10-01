// Copyright (c) 2025, sandeep and contributors
// For license information, please see license.txt

const CREDENTIAL_TYPES = ["LinkedIn Integration", "Twitter Integration", "Reddit Integration"];

frappe.ui.form.on("Social Media Post", {
	setup(frm) {
		frm.set_query("credential_type", () => ({ filters: { name: ["in", CREDENTIAL_TYPES] } }));
		frappe.realtime.on("ai_crm_creative_update", (data) => {
			if (data?.name === frm.doc.name) frm.reload_doc();
		});
	},
	refresh(frm) {
		render_preview(frm);
		render_creative_gallery(frm);
		add_workflow_buttons(frm);
		add_creative_buttons(frm);
		add_copy_button(frm);
		add_post_link(frm);
	},
	content(frm) {
		render_preview(frm);
	},
});

function add_workflow_buttons(frm) {
	const is_manager = frappe.user.has_role("Social Media Manager") || frappe.user.has_role("System Manager");
	const { status, generation_status } = frm.doc;

	if (status === "Draft" && generation_status === "Ready" && !frm.is_new()) {
		frm.add_custom_button(__("Submit for Approval"), () => run_action(frm, "submit_for_approval"));
		frm.add_custom_button(__("Revise Post"), () => revise_post(frm), __("Actions"));
		frm.add_custom_button(__("Generate Image"), () => generate_image(frm), __("Actions"));
	}
	if (status === "Pending Approval" && frm.doc.__onload?.can_approve) {
		frm.add_custom_button(__("Approve"), () => approve_post(frm)).addClass("btn-primary");
		frm.add_custom_button(__("Reject"), () => reject_post(frm), __("Actions"));
	}
	if (status === "Approved" && is_manager) {
		frm.add_custom_button(__("Publish Now"), () => publish_post(frm));
		frm.add_custom_button(__("Schedule"), () => schedule_post(frm), __("Actions"));
	}
	if (status === "Scheduled" && is_manager) {
		frm.add_custom_button(__("Unschedule"), () => run_action(frm, "unschedule"));
	}
	if (status === "Failed" && generation_status === "Failed") {
		frm.add_custom_button(__("Retry Generation"), () => run_action(frm, "retry_generation"));
	}
	if (status === "Failed" && generation_status === "Ready" && is_manager) {
		frm.add_custom_button(__("Retry Publish"), () => run_action(frm, "retry_publish"));
	}
}

function platform_from_credential(credential_type) {
	return {
		"LinkedIn Integration": "LinkedIn",
		"Twitter Integration": "X (Twitter)",
		"Reddit Integration": "Reddit",
	}[credential_type] || __("Post preview");
}

function render_preview(frm) {
	const field = frm.fields_dict?.preview_html;
	if (!field?.$wrapper) return;
	const content = frappe.utils.escape_html(frm.doc.content || "").replace(/\n/g, "<br>");
	const platform = platform_from_credential(frm.doc.credential_type);
	field.$wrapper.html(`<div class="social-media-preview"><strong>${frappe.utils.escape_html(platform)}</strong><div>${content}</div></div>`);
}

function run_action(frm, method, args = {}) {
	return frm.call({ method, doc: frm.doc, args, freeze: true }).then(() => frm.reload_doc());
}

function reject_post(frm) {
	frappe.prompt(
		{ fieldname: "reason", fieldtype: "Small Text", label: __("Rejection Reason"), reqd: 1 },
		(values) => run_action(frm, "reject", values),
		__("Reject Post"),
		__("Return to Draft"),
	);
}

function schedule_post(frm) {
	frappe.prompt(
		{ fieldname: "post_on", fieldtype: "Datetime", label: __("Publish On"), reqd: 1 },
		(values) => run_action(frm, "schedule", values),
		__("Schedule Post"),
		__("Schedule"),
	);
}

function publish_post(frm) {
	frappe.confirm(__("Publish this post on {0}?", [platform_from_credential(frm.doc.credential_type)]), () => run_action(frm, "post"));
}

function revise_post(frm) {
	frappe.prompt(
		{ fieldname: "instruction", fieldtype: "Small Text", label: __("Revision instruction"), reqd: 1 },
		(values) => run_action(frm, "revise_post", values),
		__("Revise Post"),
		__("Revise"),
	);
}

function generate_image(frm) {
	frappe.prompt(
		{ fieldname: "instruction", fieldtype: "Small Text", label: __("Image instruction") },
		(values) => run_action(frm, "generate_image", values),
		__("Generate Image"),
		__("Generate"),
	);
}

function add_creative_buttons(frm) {
	if (frm.is_new() || frm.doc.status !== "Draft") return;
	const busy = ["Queued", "Generating"].includes(frm.doc.creative_status);
	if (busy) return;

	frm.add_custom_button(__("Generate Creative"), () => generate_creative(frm), __("Creative"));
	if ((frm.doc.slides || []).length) {
		frm.add_custom_button(__("Re-render Slides"), () => rerender_creative(frm), __("Creative"));
	}
}

function generate_creative(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Generate Creative"),
		fields: [
			{
				fieldname: "template",
				fieldtype: "Link",
				label: __("Creative Template"),
				options: "Creative Template",
				reqd: 1,
				default: frm.doc.creative_template,
				get_query: () => ({ filters: { enabled: 1 } }),
				onchange: async () => {
					const template = dialog.get_value("template");
					if (!template || dialog.get_value("llm")) return;
					const { message } = await frappe.db.get_value("Creative Template", template, "llm");
					if (message?.llm) dialog.set_value("llm", message.llm);
				},
			},
			{
				fieldname: "llm",
				fieldtype: "Link",
				label: __("Model"),
				options: "LLM",
				default: frm.doc.creative_llm,
				description: __("Leave empty to use the template's default model."),
				get_query: () => ({
					filters: { enabled: 1, is_embedding_model: 0, supports_image_generation: 0 },
				}),
			},
			{
				fieldname: "brief",
				fieldtype: "Small Text",
				label: __("Brief"),
				default: frm.doc.creative_prompt,
				description: __(
					"What the creative should say: angle, audience, key facts or numbers to use. The post text is included automatically.",
				),
			},
			{
				fieldname: "share_with_siblings",
				fieldtype: "Check",
				label: __("Use for all draft posts from this idea"),
				default: 1,
				hidden: !frm.doc.content_hub,
				description: __("Attaches the same creative to this idea's drafts for your other accounts."),
			},
		],
		primary_action_label: __("Generate"),
		primary_action: async (values) => {
			dialog.hide();
			if (frm.is_dirty()) await frm.save();
			await frm.call({ method: "generate_creative", doc: frm.doc, args: values, freeze: true });
			frappe.show_alert({ message: __("Creative queued. This page refreshes when it is ready."), indicator: "blue" });
			frm.reload_doc();
		},
	});
	dialog.show();
}

function rerender_creative(frm) {
	frm.call({
		method: "rerender_creative",
		doc: frm.doc,
		freeze: true,
		freeze_message: __("Rendering slides..."),
	}).then(() => frm.reload_doc());
}

function render_creative_gallery(frm) {
	const field = frm.fields_dict?.creative_gallery;
	if (!field?.$wrapper) return;
	const status = frm.doc.creative_status;
	const slides = frm.doc.slides || [];
	const esc = frappe.utils.escape_html;

	if (["Queued", "Generating"].includes(status)) {
		field.$wrapper.html(`<div class="text-muted">${esc(__("Generating the creative, this usually takes under a minute..."))}</div>`);
		return;
	}
	if (!slides.length) {
		field.$wrapper.html(`<div class="text-muted">${esc(__("No creative yet. Use Creative > Generate Creative."))}</div>`);
		return;
	}
	const tiles = slides
		.map(
			(row) => `<a href="${esc(row.image)}" target="_blank" style="display:block;width:180px;">
				<img src="${esc(row.image)}" style="width:100%;border-radius:8px;border:1px solid var(--border-color);">
				<div class="text-muted small" style="margin-top:4px;">${esc(String(row.slide_no))} &middot; ${esc(row.layout || "")}</div>
			</a>`,
		)
		.join("");
	const pdf = frm.doc.creative_pdf
		? `<a class="btn btn-xs btn-default" href="${esc(frm.doc.creative_pdf)}" target="_blank">${esc(__("Open PDF"))}</a>`
		: "";
	field.$wrapper.html(`<div style="margin-bottom:10px;">${pdf}</div><div style="display:flex;flex-wrap:wrap;gap:12px;">${tiles}</div>`);
}

function add_copy_button(frm) {
	if (frm.is_new() || frm.doc.status === "Draft") return;
	frm.add_custom_button(__("Post to Another Account"), () => copy_to_account(frm), __("Actions"));
}

function copy_to_account(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Post to Another Account"),
		fields: [
			{
				fieldname: "credential_type",
				fieldtype: "Link",
				label: __("Credential Type"),
				options: "DocType",
				reqd: 1,
				default: frm.doc.credential_type,
				get_query: () => ({ filters: { name: ["in", CREDENTIAL_TYPES] } }),
				onchange: () => dialog.set_value("credential", ""),
			},
			{
				fieldname: "credential",
				fieldtype: "Dynamic Link",
				label: __("Credential"),
				options: "credential_type",
				reqd: 1,
			},
		],
		primary_action_label: __("Create Draft"),
		primary_action: async (values) => {
			const { message: name } = await frm.call({ method: "copy_to_account", doc: frm.doc, args: values, freeze: true });
			dialog.hide();
			frappe.show_alert({ message: __("Draft {0} created. Review it and submit when ready.", [name]), indicator: "green" });
			frappe.set_route("Form", frm.doctype, name);
		},
	});
	dialog.show();
}

function approve_post(frm) {
	const account = `${platform_from_credential(frm.doc.credential_type)} (${frappe.utils.escape_html(frm.doc.credential || "")})`;
	const post_on = frm.doc.post_on && frappe.datetime.str_to_obj(frm.doc.post_on) > new Date() ? frm.doc.post_on : null;
	const message = post_on
		? __("Post to {0} on {1}?", [account, frappe.datetime.str_to_user(post_on)])
		: __("Post to {0} now?", [account]);

	frappe.confirm(message, async () => {
		await frm.call({ method: "approve", doc: frm.doc, freeze: true });
		frm.reload_doc();
		if (!post_on) setTimeout(() => frm.reload_doc(), 20000);
	});
}

// Sidebar link to the published post, like Frappe's "See on Website".
function add_post_link(frm) {
	frm.web_link && frm.web_link.remove();
	if (frm.doc.post_link) {
		frm.add_web_link(frm.doc.post_link, __("View on {0}", [platform_from_credential(frm.doc.credential_type)]));
	}
}
