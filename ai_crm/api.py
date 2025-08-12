import frappe
import json
from frappe import _


def get_customer_or_lead_by_email(email):
    contact = frappe.get_all(
        "Contact Email",
        filters={"email_id": email},
        fields=["parent"],
        limit=1
    )

    if not contact:
        return None

    contact_doc = frappe.get_doc("Contact", contact[0].parent)

    customer_link = None
    lead_link = None

    for link in contact_doc.links:
        if link.link_doctype == "Customer":
            customer_link = link
        elif link.link_doctype == "Lead":
            lead_link = link

    if customer_link:
        return {
            "type": "Customer",
            "party": customer_link.link_name,
            "contact": contact_doc.name
        }

    if lead_link:
        return {
            "type": "Lead",
            "party": lead_link.link_name,
            "contact": contact_doc.name
        }
    return None


@frappe.whitelist()
def get_contact(contact_data):
    if isinstance(contact_data, str):
        data = json.loads(contact_data)
    else:
        data = contact_data
    primary_email = None
    for email in data.get("email_ids", []):
        if email.get("is_primary") == 1 and email.get("email_id"):
            primary_email = email["email_id"]
            break

    if not primary_email:
        primary_email = data["email_ids"][0]["email_id"]
    
    existing_contact = frappe.db.get_value(
        "Contact", 
        {"email_id": primary_email}, 
        ["name"]
    ) if primary_email else None
    contact = None
    if existing_contact:
        contact = frappe.get_doc("Contact", existing_contact)
        links = contact.links[0].as_dict() if contact.links else {}
        customer_link = next((l for l in contact.links if l.link_doctype == "Customer"), None)
        lead_link = next((l for l in contact.links if l.link_doctype == "Lead"), None)
        link = {}
        if customer_link:
            link = {
                "party_type": customer_link.link_doctype,
                "party": customer_link.link_name,
            }
        elif lead_link:
            link = {
                "party_type": lead_link.link_doctype,
                "party": lead_link.link_name,
            }
            
        if link.get("party_type") or links.get("party_name"):
            return {
                "status": "success",
                "message": f"Contact already exists with email {primary_email}",
                "contact_name": existing_contact,
                **link
            }
    
    # Second check: Look for contacts with the same company domain
    company_domain = data.get("company_domain")
    
    if company_domain:
        domain_contacts = frappe.get_all(
            "Contact", 
            filters=[
                ["Contact", "email_id", "like", f"%{company_domain}"],
                ["Dynamic Link", "link_doctype", "in", ['Customer','Lead']]
            ],
            fields=["name", "email_id"]
        )
        if domain_contacts:
            domain_contact = domain_contacts[0]
            contact_name = domain_contact.name
            contact = frappe.get_doc("Contact", contact_name)

            # Prioritize Customer, then Lead
            customer_link = next((l for l in contact.links if l.link_doctype == "Customer"), None)
            lead_link = next((l for l in contact.links if l.link_doctype == "Lead"), None)

            if customer_link:
                link = {
                    "party_type": customer_link.link_doctype,
                    "party": customer_link.link_name,
                }
            elif lead_link:
                link = {
                    "party_type": lead_link.link_doctype,
                    "party": lead_link.link_name,
                }
            else:
                link = {
                    "party_type": "Lead",
                    "party": None
                }

            return {
                "status": "success",
                "message": f"Contact found with same company domain {company_domain}",
                "contact_name": contact_name,
                "with_domain": True,
                **link
            }
    if contact:
        return {
                "status": "success",
                "message": f"Contact found with same company {company_domain}",
                "contact_name": contact.name,
                "with_domain": False,
            }
    return {
        "status": "failed",
        "message": "Contact does not exist"
    }


@frappe.whitelist()
def create_contact(contact_data,party_type,party):
    try:
        if isinstance(contact_data, str):
            data = json.loads(contact_data)
        else:
            data = contact_data
            
        if not data.get("email_ids") or not data["email_ids"][0].get("email_id"):
            frappe.throw(_("Email address is required"))
            
        primary_email = None
        for email in data.get("email_ids", []):
            if email.get("is_primary") == 1 and email.get("email_id"):
                primary_email = email["email_id"]
                break

        if not primary_email:
            primary_email = data["email_ids"][0]["email_id"]
        
        existing_contact = frappe.db.get_value(
            "Contact", 
            {"email_id": primary_email}, 
            ["name"]
        )
        
        if existing_contact:
            return {
                "status": "error",
                "message": f"Contact already exists with email {primary_email}",
                "contact_name": existing_contact
            }
            
        contact = frappe.new_doc("Contact")
        
        contact.first_name = data.get("first_name", "")
        contact.last_name = data.get("last_name", "")
        contact.salutation = data.get("salutation")
        contact.designation = data.get("designation")
        contact.gender = data.get("gender")
        contact.company_name = data.get("company_name")
        contact.auto_created = True
        
        for email in data.get("email_ids", []):
            contact.append("email_ids", {
                "email_id": email.get("email_id"),
                "is_primary": email.get("is_primary", 0)
            })
            
        for phone in data.get("phone_nos", []):
            contact.append("phone_nos", {
                "phone": phone.get("phone"),
                "is_primary_mobile_no": phone.get("is_primary_mobile_no", 0),
                "is_primary_phone": phone.get("is_primary_phone", 0)
            })
            
        contact.append("links", {
            "link_doctype": party_type,
            "link_name": party
        })
        
        contact.insert(ignore_permissions=True)
        frappe.db.commit()
        
        address_data = data.get("address")
        address_name = None
        
        if address_data and address_data.get('state') and address_data.get("country") and address_data.get("address_line1"):
            address = frappe.new_doc("Address")
            address.address_title = f"{data.get('first_name') or ''} {data.get('last_name') or '' }".strip() or data.get('company_name', 'Address')
            address.address_type = address_data.get("address_type", "Billing")
            address.address_line1 = address_data.get("address_line1")
            address.address_line2 = address_data.get("address_line2")
            address.city = address_data.get("city")
            address.state = address_data.get("state")
            address.pincode = address_data.get("pincode")
            address.country = address_data.get("country")
            address.phone = next((phone.get("phone") for phone in data.get("phone_nos", []) if phone.get("is_primary_phone", 0) == 1), None)
            address.email_id = primary_email
            address.auto_created = True
            
            address.append("links", {
                "link_doctype": party_type,
                "link_name": party
            })
            
            address.insert(ignore_permissions=True)
            address_name = address.name
            frappe.db.commit()
            
        return {
            "status": "success",
            "message": "Contact created successfully",
            "contact_name": contact.name,
            "address_name": address_name
        }
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Error creating contact", message=str(e))
        return {
            "status": "error",
            "message": f"Failed to create contact: {str(e)}"
        }

def create_address(address_data, contact_name):
    
    address_doc = frappe.get_doc({
        "doctype": "Address",
        "address_title": address_data.get("address_title") or f"Address of {contact_name}",
        "address_line1": address_data.get("address_line1", ""),
        "city": address_data.get("city", ""),
        "state": address_data.get("state", ""),
        "pincode": address_data.get("pincode", ""),
        "country": address_data.get("country", ""),
        "links": [{
            "link_doctype": "Contact",
            "link_name": contact_name
        }]
    })
    
    address_doc.insert(ignore_permissions=True)
    return address_doc
