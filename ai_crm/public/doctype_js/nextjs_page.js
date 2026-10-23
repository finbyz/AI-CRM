/**
 * Extends the NextJS Page form with an "Assign to Developer" button.
 *
 * Opens a dialog pre-filled with the default developer from Content Hub Setting,
 * today as expected start, and tomorrow as expected end. Creates a Task on Send.
 */

frappe.ui.form.on("NextJS Page", {
	refresh(frm) {
		if (frm.is_new() || !frappe.model.can_create("Task")) return;

		frm.add_custom_button(
			__("Assign to Developer"),
			() => open_assign_dialog(frm),
			__("Actions")
		);
	},
});

/**
 * Open the Assign-to-Developer dialog.
 *
 * Pre-fills the employee from Content Hub Setting → Default Page Developer,
 * expected start = today, expected end = tomorrow.
 */
async function open_assign_dialog(frm) {
	// Fetch the default employee from Content Hub Setting
	let default_employee = "";
	try {
		const res = await frappe.db.get_single_value(
			"Content Hub Setting",
			"default_page_developer"
		);
		default_employee = res || "";
	} catch (e) {
		// Setting not configured yet — user can still pick manually
		console.warn("Could not fetch default page developer:", e);
	}

	const today = frappe.datetime.get_today();
	const tomorrow = frappe.datetime.add_days(today, 1);

	const dialog = new frappe.ui.Dialog({
		title: __("Assign to Developer"),
		fields: [
			{
				label: __("Assign To"),
				fieldname: "employee",
				fieldtype: "Link",
				options: "Employee",
				default: default_employee,
				reqd: 1,
				get_query() {
					return {
						filters: {
							status: "Active",
							user_id: ["is", "set"],
						},
					};
				},
			},
			{ fieldtype: "Column Break" },
			{
				label: __("Expected Start Date"),
				fieldname: "exp_start_date",
				fieldtype: "Date",
				default: today,
				reqd: 1,
			},
			{
				label: __("Expected End Date"),
				fieldname: "exp_end_date",
				fieldtype: "Date",
				default: tomorrow,
				reqd: 1,
			},
			{ fieldtype: "Section Break" },
			{
				label: __("Description"),
				fieldname: "description",
				fieldtype: "Small Text",
				description: __(
					"Add instructions or context for the developer, e.g. design notes, urgency, special requirements."
				),
			},
		],
		size: "large",
		primary_action_label: __("Send"),
		primary_action(values) {
			dialog.disable_primary_action();

			frappe.call({
				method: "ai_crm.social_media.page_task.create_page_task",
				args: {
					page_name: frm.doc.name,
					employee: values.employee,
					description: values.description || "",
					exp_start_date: values.exp_start_date,
					exp_end_date: values.exp_end_date,
				},
				freeze: true,
				freeze_message: __("Creating task…"),
				callback(r) {
					dialog.hide();
					if (r.message) {
						const task_link = frappe.utils.get_form_link(
							"Task",
							r.message.name,
							true
						);
						frappe.show_alert(
							{
								message: __("Task created: {0}", [task_link]),
								indicator: "green",
							},
							10
						);
					}
				},
				error() {
					dialog.enable_primary_action();
				},
			});
		},
	});

	dialog.show();
}
