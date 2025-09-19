import frappe
from frappe.model.document import Document
import requests
from uuid import uuid4
from datetime import datetime, timedelta

class LinkedInIntegration(Document):
    def before_save(self):
        self.state = str(uuid4())

    def __init__(self, linkedin_doc):
        self.linkedin_doc = linkedin_doc
        self.access_token = linkedin_doc.access_token
        self.organization_support = linkedin_doc.organization_support
        self.organization_id = linkedin_doc.organization_id
        self.person_id = linkedin_doc.person_id

    def validate_linkedin_content(self, content):
        """Validate LinkedIn specific content requirements"""
        if not content:
            frappe.throw(_("Content is required for LinkedIn posts"))

        # LinkedIn has a character limit for posts
        if len(content) > 3000:
            frappe.throw(_("LinkedIn post content cannot exceed 3000 characters"))

    def _upload_linkedin_image(self, author_urn, image_attachment) -> str:
        """
        Upload a Frappe File to LinkedIn and return the image URN.
        """
        register_url = "https://api.linkedin.com/v2/images?action=initializeUpload"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        register_payload = {"initializeUploadRequest": {"owner": author_urn}}
        reg_res = requests.post(register_url, headers=headers, json=register_payload)
        reg_res.raise_for_status()
        reg_data = reg_res.json()["value"]

        upload_url = reg_data["uploadUrl"]
        image_urn = reg_data["image"]

        file_doc = frappe.get_doc("File", {"file_url": image_attachment})
        file_path = file_doc.get_full_path()
        mime_type = frappe.utils.file_manager.mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        with open(file_path, "rb") as f:
            file_content = f.read()

        upload_headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": mime_type}
        up_res = requests.post(upload_url, headers=upload_headers, data=file_content)
        up_res.raise_for_status()

        return image_urn

    def _prepare_linkedin_post_data(self, content, image_attachment=None):
        """Prepare the post data according to LinkedIn Posts API schema.
        If an image is attached, you must first register & upload it to LinkedIn,
        then pass the returned URN (image_urn) here.
        """

        # Pick correct author URN
        if self.organization_support:
            author_urn = f"urn:li:organization:{self.organization_id}"
        else:
            author_urn = f"urn:li:person:{self.person_id}"

        post_data = {
            "author": author_urn,
            "commentary": content,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        
        if image_attachment:
            image_urn = self._upload_linkedin_image(author_urn, image_attachment)
            post_data["content"] = {
                "media": {
                    "title": "Optional title",
                    "id": image_urn
                }
            }
        return post_data

    def _make_linkedin_api_request(self, post_data):
        """Make the actual API request to LinkedIn Posts API"""
        url = "https://api.linkedin.com/rest/posts"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202408",  # Using latest version as per documentation
            "X-Restli-Protocol-Version": "2.0.0"
        }

        response = requests.post(url, headers=headers, json=post_data, timeout=60)
        if response.status_code == 201:
            post_id = response.headers.get('x-restli-id')
            post_link = f"https://www.linkedin.com/feed/update/{post_id}"
            return {
                "status": "success",
                "post_id": post_id,
                "post_link": post_link
            }
        else:
            error_message = f"LinkedIn API Error: {response.status_code} - {response.text}"
            frappe.log_error(error_message, "LinkedIn Post API")
            return {
                "status": "error",
                "error": error_message
            }

    def post_to_linkedin(self, content, image_attachment=None):
        """Post content to LinkedIn using the Posts API"""
        if not content:
            frappe.throw(_("Content is required for posting"))

        if not self.access_token:
            frappe.throw(_("LinkedIn access token not found. Please reconnect your LinkedIn account."))

        if self.linkedin_doc.connection_status != "Connected":
            frappe.throw(_("LinkedIn account is not connected. Please reconnect your account."))

        # Validate content
        self.validate_linkedin_content(content)

        post_data = self._prepare_linkedin_post_data(content, image_attachment)
        response = self._make_linkedin_api_request(post_data)
        
        return response

    def update_linkedin_post(self, post_id, content):
        """Update an existing LinkedIn post"""
        try:
            if not post_id:
                frappe.throw(_("Post ID is required for updating"))

            if not self.access_token:
                frappe.throw(_("LinkedIn access token not found"))

            # Prepare update data
            update_data = {
                "patch": {
                    "$set": {
                        "commentary": content
                    }
                }
            }

            # Make API request
            url = f"https://api.linkedin.com/rest/posts/{post_id}"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202408",
                "X-Restli-Protocol-Version": "2.0.0",
                "X-RestLi-Method": "PARTIAL_UPDATE"
            }

            response = requests.post(url, headers=headers, json=update_data, timeout=30)

            if response.status_code == 204:
                return {
                    "status": "success",
                    "message": _("Post updated successfully on LinkedIn")
                }
            else:
                error_message = f"LinkedIn API Error: {response.status_code} - {response.text}"
                frappe.log_error(error_message, "LinkedIn Update API")
                return {
                    "status": "error",
                    "message": error_message
                }

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "LinkedIn Update Error")
            return {
                "status": "error",
                "message": str(e)
            }

    def delete_linkedin_post(self, post_id):
        """Delete a LinkedIn post"""
        try:
            if not post_id:
                frappe.throw(_("Post ID is required for deletion"))

            if not self.access_token:
                frappe.throw(_("LinkedIn access token not found"))

            # Make API request
            url = f"https://api.linkedin.com/rest/posts/{post_id}"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "LinkedIn-Version": "202408",
                "X-Restli-Protocol-Version": "2.0.0",
                "X-RestLi-Method": "DELETE"
            }

            response = requests.delete(url, headers=headers, timeout=30)

            if response.status_code == 204:
                return {
                    "status": "success",
                    "message": _("Post deleted successfully from LinkedIn")
                }
            else:
                error_message = f"LinkedIn API Error: {response.status_code} - {response.text}"
                frappe.log_error(error_message, "LinkedIn Delete API")
                return {
                    "status": "error",
                    "message": error_message
                }

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "LinkedIn Delete Error")
            return {
                "status": "error",
                "message": str(e)
            }


@frappe.whitelist(allow_guest=True)
def callback(code=None, state=None, error=None,*args, **kwargs):
    """Handle LinkedIn OAuth callback"""
    ACCESS_TOKEN_ENDPOINT = "https://www.linkedin.com/oauth/v2/accessToken"
    USER_INFO_ENDPOINT = "https://api.linkedin.com/v2/userinfo"
    try:
        integrations = frappe.get_list("LinkedIn Integration",filters={"state":state},pluck='name')
        if not len(integrations):
            frappe.throw(f"Not Found with {state}")    
        integration = frappe.get_doc("LinkedIn Integration",integrations[0])
        client_id = integration.client_id
        client_secret = integration.get_password("client_secret")
        redirect_uri = integration.redirect_uri

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        res = requests.post(ACCESS_TOKEN_ENDPOINT, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        res.raise_for_status()
        token_data = res.json()
        now = datetime.now()
        expiry_time = now + timedelta(seconds=token_data.get("expires_in"))

        integration.access_token = token_data.get("access_token")
        integration.expires_in = expiry_time.strftime("%Y-%m-%d %H:%M:%S")
        integration.connection_status = "Connected"
        headers = {
            'Authorization': f'Bearer {integration.access_token}',
        }
        user_info_response = requests.request("GET", USER_INFO_ENDPOINT, headers=headers, data={})
        user_info = user_info_response.json()
        integration.full_name = user_info.get("name")
        integration.email = user_info.get("email")
        integration.person_id = user_info.get("sub")
        integration.organization = user_info.get("sub")
        integration.save(ignore_permissions=True)

        

        return "success"

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "LinkedIn OAuth Callback Error")
        frappe.local.response["http_status_code"] = 500
        return {"error": f"Error getting access token: {str(e)}"}