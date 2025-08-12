# your_app/api/lead_dashboard.py

import frappe
import json
from frappe import _

@frappe.whitelist()
def get_dashboard_data(filters: str | None = None):
    """
    Main API endpoint for the Lead Dashboard.
    Fetches leads, calculates analytics, and returns a comprehensive data object.
    """
    if not frappe.has_permission("Lead", "read"):
        frappe.throw(_("You do not have permission to read Leads"), frappe.PermissionError)

    try:
        parsed_filters = json.loads(filters) if filters else {}
        
        leads = _fetch_filtered_leads(parsed_filters)
        analytics = _calculate_lead_analytics(leads)

        return {
            "leads": leads,
            "analytics": analytics,
        }
    except Exception as e:
        frappe.log_error(f"Lead Dashboard API Error: {str(e)}", "Lead Dashboard Error")
        frappe.throw(_("An error occurred while fetching dashboard data: {0}").format(str(e)))


def _fetch_filtered_leads(filters: dict) -> list[dict]:
    """
    Fetches and returns a list of leads based on the provided filters.
    """
    fields = [
        "name", "status", "lead_owner", "company_name", "source", 
        "industry", "creation", "email_id", "mobile_no", "territory", 
        "first_name", "last_name", "lead_name", "phone", "website"
    ]
    
    query_filters = {}

    # Date range
    from_date = filters.get('fromDate')
    to_date = filters.get('toDate')
    if from_date and to_date:
        query_filters['creation'] = ["between", [from_date, to_date]]
    elif from_date:
        query_filters['creation'] = [">=", from_date]
    elif to_date:
        query_filters['creation'] = ["<=", to_date]

    # Multi-select filters
    for field in ['status', 'source']:
        values = filters.get(f'{field}Filter')
        if values and f"All {field.title()}es" not in values:
            query_filters[field] = ["in", values]
    
    # Single-select filters
    if filters.get('ownerFilter') and filters.get('ownerFilter') != 'All Owners':
        query_filters['lead_owner'] = filters['ownerFilter']
    
    if filters.get('industryFilter') and filters.get('industryFilter') != 'All Industries':
        query_filters['industry'] = filters['industryFilter']

    leads = frappe.get_all(
        "Lead",
        filters=query_filters,
        fields=fields,
        order_by="creation desc",
        limit_page_length=5000  # Set a reasonable limit
    )
    
    # Add a full_name field for easier display
    for lead in leads:
        lead['full_name'] = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or lead.get('lead_name')

    return leads

def _calculate_lead_analytics(leads: list[dict]) -> dict:
    """
    Calculates and returns an analytics object from a list of leads.
    """
    total_leads = len(leads)
    status_counts = {}
    source_counts = {}
    owner_stats = {}

    open_statuses = {"Lead", "Open", "Replied", "Interested"}
    lost_statuses = {"Do Not Contact", "Lost Quotation"}

    # Initialize counts
    summary = {
        "total": total_leads,
        "open": 0,
        "converted": 0,
        "lost": 0,
    }

    if not leads:
        return { "summary": summary, "by_status": {}, "by_source": {}, "by_owner": [] }

    # Process each lead
    for lead in leads:
        status = lead.get('status') or "Uncategorized"
        source = lead.get('source') or "Unknown"
        owner = lead.get('lead_owner') or "Unassigned"

        # Tally summary counts
        if status == "Converted":
            summary['converted'] += 1
        elif status in open_statuses:
            summary['open'] += 1
        elif status in lost_statuses:
            summary['lost'] += 1

        # Tally breakdowns
        status_counts[status] = status_counts.get(status, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

        # Tally owner stats
        if owner not in owner_stats:
            owner_stats[owner] = {"total": 0, "converted": 0, "lost": 0}
        
        owner_stats[owner]['total'] += 1
        if status == "Converted":
            owner_stats[owner]['converted'] += 1
        elif status in lost_statuses:
            owner_stats[owner]['lost'] += 1

    # Format owner stats for the grid
    owner_list = [
        {"owner": owner, **stats}
        for owner, stats in owner_stats.items()
    ]

    return {
        "summary": summary,
        "by_status": dict(sorted(status_counts.items(), key=lambda item: item[1], reverse=True)),
        "by_source": dict(sorted(source_counts.items(), key=lambda item: item[1], reverse=True)),
        "by_owner": sorted(owner_list, key=lambda item: item['total'], reverse=True),
    }

@frappe.whitelist()
def get_filter_options():
    """
    Fetches unique values for filter dropdowns to ensure they are based on actual data.
    """
    try:
        # Fetch unique values using SQL for performance
        statuses = [r[0] for r in frappe.db.sql("SELECT DISTINCT status FROM `tabLead` WHERE status IS NOT NULL AND status != '' ORDER BY status")]
        sources = [r[0] for r in frappe.db.sql("SELECT DISTINCT source FROM `tabLead` WHERE source IS NOT NULL AND source != '' ORDER BY source")]
        industries = [r[0] for r in frappe.db.sql("SELECT DISTINCT industry FROM `tabLead` WHERE industry IS NOT NULL AND industry != '' ORDER BY industry")]
        
        # Fetch active users for the 'owner' dropdown
        owners = frappe.get_all(
            "User",
            filters={"enabled": 1},
            fields=["name as value", "full_name as label"],
            order_by="full_name"
        )

        return {
            "status": statuses,
            "source": sources,
            "industry": industries,
            "owner": owners,
        }
    except Exception as e:
        frappe.log_error(f"Filter Options API Error: {str(e)}", "Lead Dashboard Error")
        frappe.throw(_("An error occurred while fetching filter options."))