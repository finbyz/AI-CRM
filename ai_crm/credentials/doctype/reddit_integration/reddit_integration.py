import base64
import secrets
import traceback
from urllib.parse import urlencode
import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime
from ai_crm.credentials.doctype.reddit_integration.reddit_client import RedditClient

class RedditIntegration(Document):
    def before_save(self):
        """Generate state for OAuth flow"""
        if not self.state:
            self.state = secrets.token_urlsafe(32)

        if not self.redirect_uri:
            self.redirect_uri = f"https://{frappe.conf.hostname}/api/method/ai_crm.credentials.doctype.reddit_integration.reddit_integration.callback"

        if not self.user_agent:
            self.user_agent = self.get_user_agent()

    def get_user_agent(self):
        version = "v1.0"
        username = self.username or self.name  
        app_id = "ai_crm_reddit_bot"  
        return f"web:{app_id}:{version} (by /u/{username})"
    
    @frappe.whitelist()
    def test_connection(self):
        try:
            if not self.access_token:
                return {
                    "status": "error",
                    "message": _("Access token not available. Please connect your Reddit account."),
                }
            expires_in = (
                frappe.utils.time_diff(self.expires_at, frappe.utils.now()).total_seconds()
                if self.expires_at else 0
            )
            reddit_client = RedditClient(
                user_agent=self.get_user_agent(),
                access_token=self.get_password("access_token"),
                refresh_token=self.get_password("refresh_token"),
                expires_in=expires_in,
                client_id=self.client_id,
                client_secret=self.get_password("client_secret"),
                redirect_uri=self.redirect_uri,
            )
            user_data = reddit_client.get_me()
            self.username = user_data.get("name", "")
            self.user_id = user_data.get("id", "")
            self.connection_status = "Connected"
            self.connected_at = frappe.utils.now()
            
            return {
                "status": "success",
                "message": _("Reddit connection successful"),
                "username": self.username,
            }
        except Exception as e:
            self.connection_status = "Error"
            frappe.log_error(
                title="Reddit Connection Test Failed",
                message=frappe.get_traceback()
            )
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def get_authorization_url(self):
        
        try:
           
            params = {
                "client_id": self.client_id,
                "response_type": "code",
                "state": self.state,
                "redirect_uri": self.redirect_uri,
                "duration": "permanent",  
                "scope": "identity submit read edit", 
            }

            auth_url = "https://www.reddit.com/api/v1/authorize?" + urlencode(params)

            self.connection_status = "Pending Authorization"
            self.save(ignore_permissions=True)

            return {"status": "success", "auth_url": auth_url, "state": self.state}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_access_token(self, code):
        """Step 2: Exchange authorization code for access token"""
        try:
            url = "https://www.reddit.com/api/v1/access_token"
            client_secret = self.get_password("client_secret") or ""
            auth_string = f"{self.client_id}:{client_secret}"
            auth_encoded = base64.b64encode(auth_string.encode()).decode()

            headers = {
                "Authorization": f"Basic {auth_encoded}",
                "User-Agent": self.get_user_agent(),
                "Content-Type": "application/x-www-form-urlencoded",
            }

            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            }

            response = requests.post(url, headers=headers, data=data, timeout=30)

            if response.status_code == 200:
                token_data = response.json()

                self.set_value("access_token", token_data.get("access_token"))
                self.set_value("refresh_token", token_data.get("refresh_token"))
                self.token_type = token_data.get("token_type", "bearer")

                expires_in = token_data.get("expires_in", 3600)  
                self.expires_at = frappe.utils.add_to_date(
                    frappe.utils.now(), seconds=expires_in
                )

                self.connection_status = "Connected"
                self.connected_at = frappe.utils.now()

                return {
                    "status": "success",
                    "message": "Access token obtained successfully",
                }
            else:
                self.connection_status = "Error"
                return {
                    "status": "error",
                    "message": f"Reddit Token Error: {response.status_code}",
                }

        except Exception as e:
            self.connection_status = "Error"
            return {"status": "error", "message": str(e)}

    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        try:
            if not self.refresh_token:
                return {"status": "error", "message": "No refresh token available"}

            url = "https://www.reddit.com/api/v1/access_token"

            client_secret = self.get_password("client_secret") or ""
            auth_string = f"{self.client_id}:{client_secret}"
            auth_encoded = base64.b64encode(auth_string.encode()).decode()

            headers = {
                "Authorization": f"Basic {auth_encoded}",
                "User-Agent": self.get_user_agent(),
                "Content-Type": "application/x-www-form-urlencoded",
            }

            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.get_password("refresh_token"),
            }

            response = requests.post(url, headers=headers, data=data, timeout=30)

            if response.status_code == 200:
                token_data = response.json()

                self.set_value("access_token", token_data.get("access_token"))
                
                if token_data.get("refresh_token"):
                    self.set_value("refresh_token", token_data.get("refresh_token"))

                expires_in = token_data.get("expires_in", 3600)
                self.expires_at = frappe.utils.add_to_date(
                    frappe.utils.now(), seconds=expires_in
                )

                self.save(ignore_permissions=True)

                return {"status": "success", "message": "Token refreshed successfully"}
            else:
                return {
                    "status": "error",
                    "message": f"Token refresh failed: {response.status_code}",
                }

        except Exception as e:
            return {"status": "error", "message": str(e)}
    def ensure_valid_token(self):
        """Ensure we have a valid access token, refresh if needed"""
        try:
            if not self.expires_at:
                frappe.logger().warning(f"No expiry date set for token in {self.name}")
                return True
            
            expires_at = get_datetime(self.expires_at)
            current_time = get_datetime()
            time_until_expiry = (expires_at - current_time).total_seconds()
            
            if time_until_expiry < 300:
                frappe.logger().info(
                    f"Token for {self.name} expiring in {time_until_expiry} seconds, refreshing..."
                )
                
                result = self.refresh_access_token()
                
                if result.get('status') != 'success':
                    error_msg = result.get('message', 'Unknown error')
                    frappe.log_error(
                        f"Failed to refresh token for {self.name}: {error_msg}",
                        "Reddit Token Refresh Failed"
                    )
                    return False
                
                frappe.logger().info(f"Token for {self.name} refreshed successfully")
                return True
            else:
                frappe.logger().info(f"Token for {self.name} valid for {int(time_until_expiry)} more seconds")
                return True
                
        except Exception as e:
            frappe.log_error(
                f"Error in ensure_valid_token for {self.name}: {str(e)}\n{traceback.format_exc()}",
                "Token Validation Error"
            )
            return False
    def get_valid_access_token(self):
        
        if self.ensure_valid_token():
            return self.get_password("access_token")
        return None

@frappe.whitelist(allow_guest=True)
def callback(state=None, code=None, error=None, *args, **kwargs):
    """Handle Reddit OAuth callback with improved error handling"""
    try:
        if error:
            error_description = kwargs.get('error_description', 'Unknown OAuth error')
            frappe.log_error(
                f"Reddit OAuth Error: {error} - {error_description}",
                "Reddit OAuth Error"
            )
            return {
                "status": "error",
                "message": f"OAuth Error: {error} - {error_description}"
            }

        if not code or code in ["None", "null", ""]:
            frappe.log_error("No authorization code received in callback", "Reddit OAuth Error")
            return {
                "status": "error",
                "message": "No authorization code received from Reddit"
            }

        reddit_integration = frappe.get_doc("Reddit Integration", {"state": state}) if state else None
        
        if not reddit_integration:
            frappe.log_error(
                f"No Reddit Integration found for state: {state}",
                "Reddit OAuth Error"
            )
            return {
                "status": "error",
                "message": "No Reddit Integration record found. Please try reconnecting."
            }
        client_id = reddit_integration.client_id
        client_secret = reddit_integration.get_password("client_secret")
        auth_str = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_str}',
            'User-Agent': reddit_integration.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': reddit_integration.redirect_uri,
        }
        token_resp = requests.post("https://www.reddit.com/api/v1/access_token", data=data, headers=headers)
        if token_resp.status_code != 200:
            frappe.log_error(
                f"Token exchange failed: {token_resp.status_code} - {token_resp.text}",
                "Reddit OAuth Error"
            )
            return {
                "status": "error",
                "message": _("Failed to exchange authorization code for tokens"),
            }
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token") 
        expires_in = token_data.get("expires_in")
        
        reddit_integration.access_token = access_token
        reddit_integration.refresh_token = refresh_token
        reddit_integration.expires_at = add_to_date(frappe.utils.now(), seconds=expires_in)
                
        reddit_client = RedditClient(
            user_agent=reddit_integration.user_agent,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=reddit_integration.redirect_uri,
        )
        
        user_details = reddit_client.get_me()
        reddit_integration.username = user_details.get("name", "")
        reddit_integration.user_id = user_details.get("id", "")
        reddit_integration.user_agent = reddit_integration.get_user_agent()  
        reddit_integration.connected_at = frappe.utils.now()
        reddit_integration.connection_status = "Connected"
        reddit_integration.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            "status": "success",
            "message": f"Reddit account u/{reddit_integration.username} connected successfully",
            "username": reddit_integration.username,
            "integration_name": reddit_integration.name
        }

    except Exception as e:
       
        frappe.log_error(
            title="Reddit OAuth Callback Exception",
            message=frappe.get_traceback()
        )
        
        return {
            "status": "error",
            "message": f"An unexpected error occurred: {str(e)}"
        }
