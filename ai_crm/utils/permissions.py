import frappe


def require_permission(doctype, ptype="read", name=None):
	"""Throw PermissionError unless the session user has `ptype` access.

	Checks the record when `name` is an existing record, otherwise the DocType.
	Used at the top of whitelisted endpoints that skip permission checks in their body.
	"""
	if name and frappe.db.exists(doctype, name):
		frappe.has_permission(doctype, ptype, name, throw=True)
	else:
		frappe.has_permission(doctype, ptype, throw=True)
