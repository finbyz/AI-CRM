import frappe

PERMISSIONS_MAP = {
    "Bot Access": ["read", "write"],
}

def after_install():
    create_ai_automation_role()
    set_permissions(PERMISSIONS_MAP)
    
def before_uninstall():
    remove_permission(PERMISSIONS_MAP)

def create_ai_automation_role():
    if not frappe.db.exists("Role", "AI Automation"):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": "AI Automation",
            "desk_access": 0
        }).insert(ignore_permissions=True)
        frappe.db.commit()

def set_permissions(permissions_map):
    role_name = "AI Automation"

    for doctype, actions in permissions_map.items():
        if not frappe.db.exists("DocType", doctype):
            frappe.log_error(f"DocType '{doctype}' not found. Skipping permission assignment.")
            continue

        frappe.db.delete("Custom DocPerm", {
            "role": role_name,
            "parent": doctype
        })

        perm_flags = {
            "read": 0, "write": 0, "create": 0,
            "submit": 0, "cancel": 0, "amend": 0,
            "delete": 0, "print": 0, "email": 0, "export": 0
        }
        for action in actions:
            if action in perm_flags:
                perm_flags[action] = 1

        frappe.get_doc({
            "doctype": "Custom DocPerm",
            "parent": doctype,
            "parenttype": "DocType",
            "role": role_name,
            **perm_flags
        }).insert(ignore_permissions=True)

    frappe.db.commit()


def remove_permission(permissions_map):
    role_name = "AI Automation"
    
    frappe.db.delete("Custom DocPerm", {"role": role_name})
    frappe.db.delete("Has Role", {"role": role_name})

    if frappe.db.exists("Role", role_name):
        frappe.delete_doc("Role", role_name, ignore_permissions=True, force=1)

    frappe.db.commit()
