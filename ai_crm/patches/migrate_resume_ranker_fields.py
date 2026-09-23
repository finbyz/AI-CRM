import frappe
from frappe.model.utils.rename_field import rename_field


DOCTYPE = "Job Applicant"

REMOVED_FIELDS = (
    "ai_overall_score",
    "skill_match_percentage"
	"ai_strengths",
	"ai_missing_skills",
	"ai_gap_section",
	"ai_gap_cb",
)


def execute():
	for fieldname in REMOVED_FIELDS:
		delete_custom_field(fieldname)

	frappe.clear_cache(doctype=DOCTYPE)



def delete_custom_field(fieldname):
	field_name = get_custom_field_name(fieldname)
	if frappe.db.exists("Custom Field", field_name):
		frappe.delete_doc("Custom Field", field_name, delete_permanently=True, force=True)


def get_custom_field_name(fieldname):
	return f"{DOCTYPE}-{fieldname}"
