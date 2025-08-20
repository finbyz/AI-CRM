import frappe

PERMISSIONS_MAP = {
    "Bot Access": ["read", "write","create","delete"],
    "Customer":["read", "write","create"],
    "Lead":["read", "write","create"],
    "Contact":["read", "write","create"],
    "Address":["read", "write","create"],
    "Voice Recording":["read", "write","create","delete"]
}
    
def before_uninstall():
    remove_permission(PERMISSIONS_MAP)




def remove_permission(permissions_map):
    role_name = "AI Automation"
    
    frappe.db.delete("Custom DocPerm", {"role": role_name})
    frappe.db.delete("Has Role", {"role": role_name})

    if frappe.db.exists("Role", role_name):
        frappe.delete_doc("Role", role_name, ignore_permissions=True, force=1)

    frappe.db.commit()
