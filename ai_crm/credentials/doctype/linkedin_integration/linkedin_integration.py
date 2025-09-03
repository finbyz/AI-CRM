# your_app/your_app/doctype/linkedin_integration/linkedin_integration.py

import frappe
from frappe.model.document import Document
import requests
from uuid import uuid4
from datetime import datetime, timedelta

class LinkedInIntegration(Document):
    def before_save(self):
        self.state = str(uuid4())

@frappe.whitelist(allow_guest=True)
def callback(code=None, state=None, error=None,*args, **kwargs):
    """Handle LinkedIn OAuth callback"""
    try:
        integrations = frappe.get_list("LinkedIn Integration",filters={"state":state},pluck='name')
        if not len(integrations):
            frappe.throw(f"Not Found with {state}")    
        integration = frappe.get_doc("LinkedIn Integration",integrations[0])
        client_id = integration.client_id
        client_secret = integration.get_password("client_secret")
        redirect_uri = integration.redirect_uri

        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        res = requests.post(token_url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        res.raise_for_status()
        token_data = res.json()
        frappe.log_error("response data",str(token_data))
        now = datetime.now()
        expiry_time = now + timedelta(seconds=token_data.get("expires_in"))

        integration.access_token = token_data.get("access_token")
        integration.expires_in = expiry_time.strftime("%Y-%m-%d %H:%M:%S")
        integration.connection_status = "Connected"
        headers = {
            'Authorization': f'Bearer {integration.access_token}',
        }
        user_info_response = requests.request("GET", "https://api.linkedin.com/v2/userinfo", headers=headers, data={})
        user_info = user_info_response.json()
        integration.full_name = user_info.get("name")
        integration.email = user_info.get("email")
        integration.person_id = user_info.get("sub")
        integration.organization = user_info.get("sub")
        integration.save(ignore_permissions=True)

        frappe.db.commit()

        return "success"

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "LinkedIn OAuth Callback Error")
        frappe.local.response["http_status_code"] = 500
        return {"error": f"Error getting access token: {str(e)}"}
