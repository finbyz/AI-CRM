/**
 * Extends the NextJS Page form with an "Assign to Developer" button.
 *
 * Opens a dialog pre-filled with the task subject, the developer this user last assigned
 * in this browser, today as expected start, and tomorrow as expected end. Creates a Task on Send.
 */

// Task.subject is a Data field.
const SUBJECT_LENGTH = 140;

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

// Per browser, site and user, so it survives restarts without a server-side setting.
const DEVELOPER_KEY = `ai_crm:last_page_developer:${frappe.boot.sitename}:${frappe.session.user}`;

/**
 * Open the Assign-to-Developer dialog.
 *
 * Pre-fills the employee last assigned from this browser, expected start = today,
 * expected end = tomorrow.
 */
async function open_assign_dialog(frm) {
	const default_employee = await get_saved_developer();

	const today = frappe.datetime.get_today();
	const tomorrow = frappe.datetime.add_days(today, 1);

	const dialog = new frappe.ui.Dialog({
		title: __("Assign to Developer"),
		fields: [
			{
				label: __("Subject"),
				fieldname: "subject",
				fieldtype: "Data",
				length: SUBJECT_LENGTH,
				default: __("Develop and deploy page: {0}", [frm.doc.title || frm.doc.name]).slice(0, SUBJECT_LENGTH),
				reqd: 1,
			},
			{ fieldtype: "Section Break" },
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
				default: __("Source page: Open NextJS Page: {0}", [frm.doc.title || frm.doc.name]) +
					"\n" + frappe.urllib.get_full_url(frappe.utils.get_form_link("NextJS Page", frm.doc.name)) + "\n\n",
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
					subject: values.subject,
					description: values.description || "",
					exp_start_date: values.exp_start_date,
					exp_end_date: values.exp_end_date,
				},
				freeze: true,
				freeze_message: __("Creating task…"),
				callback(r) {
					dialog.hide();
					if (r.message) {
						save_developer(values.employee);
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

/** Return the saved developer, clearing it if they are no longer active or have no user. */
async function get_saved_developer() {
	let employee = "";
	try {
		employee = localStorage.getItem(DEVELOPER_KEY) || "";
	} catch (e) {
		return "";
	}
	if (!employee) return "";

	let message;
	try {
		({ message } = await frappe.db.get_value("Employee", employee, ["status", "user_id"]));
	} catch (e) {
		// Cannot check right now; leave Assign To empty but keep the saved choice.
		return "";
	}
	if (message?.status === "Active" && message.user_id) return employee;

	save_developer("");
	return "";
}

function save_developer(employee) {
	try {
		if (employee) localStorage.setItem(DEVELOPER_KEY, employee);
		else localStorage.removeItem(DEVELOPER_KEY);
	} catch (e) {
		// Storage blocked (private window); the user just picks again next time.
	}
}
