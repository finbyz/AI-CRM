/**
 * Extends the NextJS Page form with an "Assign to Developer" button.
 *
 * Opens a dialog pre-filled with the task subject, the developer, project and task type this user
 * last assigned in this browser, today as expected start, and tomorrow as expected end.
 * Creates a Task on Send.
 */

// Task.subject is a Data field.
const SUBJECT_LENGTH = 140;
// Page development work is tracked under this Task Type unless the dialog picks another.
const DEFAULT_TASK_TYPE = "Development";

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

// Per browser, site and user, so the choices survive restarts without a server-side setting.
const STORAGE_KEYS = {
	employee: `ai_crm:last_page_developer:${frappe.boot.sitename}:${frappe.session.user}`,
	project: `ai_crm:last_page_project:${frappe.boot.sitename}:${frappe.session.user}`,
	task_type: `ai_crm:last_page_task_type:${frappe.boot.sitename}:${frappe.session.user}`,
};

// What a remembered value is checked against before it is pre-filled again.
const REMEMBERED = {
	employee: {
		doctype: "Employee",
		fields: ["name", "status", "user_id"],
		is_valid: (doc) => doc.name && doc.status === "Active" && doc.user_id,
	},
	project: {
		doctype: "Project",
		fields: ["name", "status"],
		is_valid: (doc) => doc.name && doc.status !== "Cancelled",
	},
	task_type: {
		doctype: "Task Type",
		fields: ["name"],
		is_valid: (doc) => doc.name,
	},
};

/**
 * Open the Assign-to-Developer dialog.
 *
 * Pre-fills the employee, project and task type last used from this browser,
 * expected start = today, expected end = tomorrow.
 */
async function open_assign_dialog(frm) {
	const [default_employee, default_project, saved_task_type] = await Promise.all([
		get_saved_choice("employee"),
		get_saved_choice("project"),
		get_saved_choice("task_type"),
	]);

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
			{
				label: __("Project"),
				fieldname: "project",
				fieldtype: "Link",
				options: "Project",
				default: default_project,
				reqd: 1,
				get_query() {
					return {
						filters: {
							status: ["!=", "Cancelled"],
						},
					};
				},
			},
			{
				label: __("Task Type"),
				fieldname: "task_type",
				fieldtype: "Link",
				options: "Task Type",
				default: saved_task_type || DEFAULT_TASK_TYPE,
				reqd: 1,
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
					project: values.project,
					task_type: values.task_type,
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
						save_choice("employee", values.employee);
						save_choice("project", values.project);
						save_choice("task_type", values.task_type);
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

/** Return the saved value for a field, clearing it if the document is gone or no longer usable. */
async function get_saved_choice(fieldname) {
	let value = "";
	try {
		value = localStorage.getItem(STORAGE_KEYS[fieldname]) || "";
	} catch (e) {
		return "";
	}
	if (!value) return "";

	const { doctype, fields, is_valid } = REMEMBERED[fieldname];
	let message;
	try {
		({ message } = await frappe.db.get_value(doctype, value, fields));
	} catch (e) {
		// Cannot check right now; leave the field empty but keep the saved choice.
		return "";
	}
	if (message && is_valid(message)) return value;

	save_choice(fieldname, "");
	return "";
}

function save_choice(fieldname, value) {
	try {
		if (value) localStorage.setItem(STORAGE_KEYS[fieldname], value);
		else localStorage.removeItem(STORAGE_KEYS[fieldname]);
	} catch (e) {
		// Storage blocked (private window); the user just picks again next time.
	}
}
