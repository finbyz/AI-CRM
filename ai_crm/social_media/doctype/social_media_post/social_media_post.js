// Copyright (c) 2025, sandeep and contributors
// For license information, please see license.txt

frappe.ui.form.on("Social Media Post", {
	refresh(frm) {
		render_preview(frm);
		add_workflow_buttons(frm);
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
	if (status === "Pending Approval" && is_manager) {
		frm.add_custom_button(__("Approve"), () => run_action(frm, "approve"));
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
