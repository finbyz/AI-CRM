"""Create development tasks for NextJS Pages.

Called from the *Assign to Developer* dialog on the NextJS Page form.
"""

import frappe
import frappe.share
from frappe import _
from frappe.desk.form.assign_to import add as assign_to
from frappe.utils import today, add_days

SUBJECT_LENGTH = 140
# Page development work is tracked under this Task Type unless the dialog picks another.
DEFAULT_TASK_TYPE = "Development"


@frappe.whitelist(methods=["POST"])
def create_page_task(
    page_name,
    employee,
    description,
    project,
    exp_start_date=None,
    exp_end_date=None,
    subject=None,
    task_type=None,
):
    """Create a Task and assign it to *employee* for the given NextJS Page.

    Args:
        page_name: Name (ID) of the NextJS Page document.
        employee: Employee ID (e.g. ``HR-EMP-00042``).
        description: Free-text task description entered by the user.
        project: Project the task belongs to.
        exp_start_date: Expected start date (default: today).
        exp_end_date: Expected end date (default: tomorrow).
        subject: Task subject (default: "Develop and deploy page: <title>"), cut to 140 characters.
        task_type: Task Type (default: "Development").

    Returns:
        dict with ``name`` and ``subject`` of the newly created Task.

    Raises:
        frappe.ValidationError: If the employee has no linked User, or the project or task type is unknown.
    """
    frappe.has_permission("Task", "create", throw=True)

    project = (project or "").strip()
    if not project:
        frappe.throw(_("Select a Project for the development task"))
    if not frappe.db.exists("Project", project):
        frappe.throw(_("Project {0} does not exist").format(project))

    task_type = (task_type or "").strip() or DEFAULT_TASK_TYPE
    if not frappe.db.exists("Task Type", task_type):
        frappe.throw(_("Task Type {0} does not exist. Create it or pick another type.").format(task_type))

    page = frappe.get_doc("NextJS Page", page_name)
    page.check_permission("read")
    emp = frappe.get_doc("Employee", employee)

    if emp.status != "Active":
        frappe.throw(_("Employee {0} is not active").format(emp.employee_name))

    if not emp.user_id:
        frappe.throw(
            _("Employee {0} does not have a linked User ID. Please set one before assigning tasks.").format(
                emp.employee_name
            )
        )

    ensure_developer_page_access(page, emp.user_id)

    exp_start_date = exp_start_date or today()
    exp_end_date = exp_end_date or add_days(exp_start_date, 1)

    # Task.subject holds 140 characters; long page titles stay whole in the description.
    subject = ((subject or "").strip() or f"Develop and deploy page: {page.title}")[:SUBJECT_LENGTH]

    # Build an HTML description that includes the user's notes and a link
    # back to the NextJS Page for quick navigation.
    page_link = frappe.utils.get_link_to_form("NextJS Page", page_name)
    notes = frappe.utils.escape_html(description or "").replace("\n", "<br>")
    full_description = f"<p>{notes}</p>" if notes else ""
    full_description += f"<p><strong>Page title:</strong> {frappe.utils.escape_html(page.title or '')}</p>"
    full_description += f"<p><strong>Source page:</strong> {page_link}</p>"

    task = frappe.get_doc(
        {
            "doctype": "Task",
            "subject": subject,
            "description": full_description,
            "project": project,
            "type": task_type,
            "exp_start_date": exp_start_date,
            "exp_end_date": exp_end_date,
            "assignee": emp.user_id,
            # Whoever assigns the page reviews the work.
            "approver": [{"user": frappe.session.user}],
            "status": "Open",
        }
    )
    task.insert(ignore_permissions=True)

    # productivity_next assigns the Task to its assignee on insert; assign here only when it did not,
    # since assigning twice shows an "already assigned" message.
    if not frappe.db.exists(
        "ToDo", {"reference_type": "Task", "reference_name": task.name, "allocated_to": emp.user_id, "status": "Open"}
    ):
        assign_to({"doctype": "Task", "name": task.name, "assign_to": [emp.user_id], "description": subject})

    return {"name": task.name, "subject": task.subject}


def ensure_developer_page_access(page, user):
    """Grant source-page read access using the assigning user's share permission."""
    if frappe.has_permission(doc=page, ptype="read", user=user):
        return

    if frappe.get_system_settings("disable_document_sharing"):
        frappe.throw(
            _("Developer {0} cannot read page {1}, and document sharing is disabled. Grant page access before assigning.").format(
                user, page.name
            ),
            frappe.PermissionError,
        )

    if not page.has_permission("share"):
        frappe.throw(
            _("Developer {0} cannot read page {1}. You need permission to share this page before assigning it.").format(
                user, page.name
            ),
            frappe.PermissionError,
        )

    frappe.share.add(page.doctype, page.name, user=user, read=1)
