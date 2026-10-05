import re
import time
from urllib.parse import quote

import frappe
from frappe.apps import _
from frappe.model.document import Document
import requests
from uuid import uuid4
from datetime import datetime, timedelta

class LinkedInIntegration(Document):
    def before_save(self):
        if not self.state:
            self.state = str(uuid4())

    def get_linkedin_helper(self):
        """Get a helper instance with current document data"""
        return LinkedInHelper(self)

    def validate_linkedin_content(self, content):
        """Validate LinkedIn specific content requirements"""
        if not content:
            frappe.throw(_("Content is required for LinkedIn posts"))

        # LinkedIn has a character limit for posts
        if len(content) > 3000:
            frappe.throw(_("LinkedIn post content cannot exceed 3000 characters"))

    def post_to_linkedin(self, content, image_attachment=None, document=None, document_title=None):
        """Post content to LinkedIn using the Posts API"""
        self.validate_linkedin_content(content)
        helper = self.get_linkedin_helper()
        return helper.post_to_linkedin(content, image_attachment, document, document_title)

    def update_linkedin_post(self, post_id, content):
        """Update an existing LinkedIn post"""
        self.validate_linkedin_content(content)
        helper = self.get_linkedin_helper()
        return helper.update_linkedin_post(post_id, content)

    def delete_linkedin_post(self, post_id):
        """Delete a LinkedIn post"""
        helper = self.get_linkedin_helper()
        return helper.delete_linkedin_post(post_id)


class LinkedInHelper:
    """Helper class for LinkedIn API operations"""
    
    # LinkedIn sunsets each monthly version after about a year; keep this current.
    API_VERSION = "202609"
    DOCUMENT_READY_TIMEOUT = 90  # seconds to wait for LinkedIn to process an uploaded PDF

    def __init__(self, linkedin_doc):
        self.linkedin_doc = linkedin_doc
        self.access_token = linkedin_doc.get_password("access_token")
        self.organization_support = linkedin_doc.organization_support
        self.organization_id = linkedin_doc.organization_id
        self.person_id = linkedin_doc.person_id

    def _get_headers(self):
        """Constructs the default headers for LinkedIn API requests."""
        if not self.access_token:
            frappe.throw(_("LinkedIn access token not found. Please reconnect your LinkedIn account."))
        
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": self.API_VERSION,  # Using the latest API version format
            "X-Restli-Protocol-Version": "2.0.0"
        }
        
    def _extract_urls_from_content(self, content):
        """Extract URLs from content text"""
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, content)
        return urls if urls else None
    
    def _extract_youtube_video_id(self, url):
        """Extract YouTube video ID from URL"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\?\/\s]+)',
            r'youtube\.com\/embed\/([^&\?\/\s]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _upload_linkedin_image(self, author_urn, image_attachment) -> str:
        """
        Upload a Frappe File to LinkedIn and return the image URN.
        """
        register_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
        headers = self._get_headers()
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

    def _upload_linkedin_document(self, author_urn, file_url) -> str:
        """Upload a PDF to LinkedIn, wait until it is processed, and return its document URN."""
        reg_res = requests.post(
            "https://api.linkedin.com/rest/documents?action=initializeUpload",
            headers=self._get_headers(),
            json={"initializeUploadRequest": {"owner": author_urn}},
            timeout=60,
        )
        reg_res.raise_for_status()
        reg_data = reg_res.json()["value"]
        document_urn = reg_data["document"]

        file_path = frappe.get_doc("File", {"file_url": file_url}).get_full_path()
        with open(file_path, "rb") as f:
            up_res = requests.put(
                reg_data["uploadUrl"],
                headers={"Authorization": f"Bearer {self.access_token}"},
                data=f.read(),
                timeout=120,
            )
        up_res.raise_for_status()

        status_url = f"https://api.linkedin.com/rest/documents/{quote(document_urn, safe='')}"
        deadline = time.monotonic() + self.DOCUMENT_READY_TIMEOUT
        status = None
        while time.monotonic() < deadline:
            res = requests.get(status_url, headers=self._get_headers(), timeout=30)
            res.raise_for_status()
            status = res.json().get("status")
            if status == "AVAILABLE":
                return document_urn
            if status == "PROCESSING_FAILED":
                frappe.throw(_("LinkedIn could not process the PDF"))
            time.sleep(3)
        frappe.throw(_("LinkedIn is still processing the PDF (status {0}); retry the publish shortly").format(status))

    def _prepare_linkedin_post_data(self, content, image_attachment=None, document=None, document_title=None):
        """Prepare the post data according to LinkedIn Posts API schema."""
        if self.organization_support and self.organization_id:
            author_urn = f"urn:li:organization:{self.organization_id}"
        else:
            author_urn = f"urn:li:person:{self.person_id}"

        # Extract URLs from content
        urls = self._extract_urls_from_content(content)

        # A PDF becomes a swipeable document (carousel) post and takes priority.
        if document:
            document_urn = self._upload_linkedin_document(author_urn, document)
            post_data = {
                "author": author_urn,
                "commentary": content,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "content": {
                    "media": {
                        "title": (document_title or "Document")[:200],
                        "id": document_urn,
                    }
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }
            return post_data, "posts"

        # If image exists, use current Posts API (image priority)
        if image_attachment:
            image_urn = self._upload_linkedin_image(author_urn, image_attachment)
            post_data = {
                "author": author_urn,
                "commentary": content,  # URLs in commentary will be clickable
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
                "content": {
                    "media": {
                        "title": "Image from Frappe",
                        "id": image_urn
                    }
                }
            }
            return post_data, "posts"  # Return API type
        
        # If URL exists but no image, use UGC Posts API for URL preview
        elif urls:
            first_url = urls[0]  # Use first URL for preview
            
            # Prepare UGC Post data structure
            ugc_post_data = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": content
                        },
                        "shareMediaCategory": "ARTICLE",
                        "media": [
                            {
                                "status": "READY",
                                "originalUrl": first_url,
                            }
                        ]
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                }
            }
            return ugc_post_data, "ugcPosts"  # Return API type
        
        # Text-only post, use current Posts API
        else:
            post_data = {
                "author": author_urn,
                "commentary": content,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }
            return post_data, "posts"  # Return API type

    def _make_linkedin_api_request(self, method, url, **kwargs):
        """A centralized method for making API requests."""
        try:
            response = requests.request(method, url, timeout=60, **kwargs)
            response.raise_for_status()
            
            if response.status_code == 201:  # Created
                # For Posts API
                if '/rest/posts' in url:
                    post_id = response.headers.get('x-restli-id')
                    post_link = f"https://www.linkedin.com/feed/update/{post_id}"
                # For UGC Posts API
                else:
                    post_id = response.headers.get('x-restli-id')
                    if not post_id:
                        # Sometimes UGC Posts returns ID in response body
                        response_data = response.json()
                        post_id = response_data.get('id', '')
                    post_link = f"https://www.linkedin.com/feed/update/{post_id}"
                
                return {"status": "success", "post_id": post_id, "post_link": post_link}
                
            elif response.status_code == 204:  # No Content (for update/delete)
                return {"status": "success"}
                
            return response.json()

        except requests.exceptions.RequestException as e:
            if e.response is not None:
                error_message = f"LinkedIn API Error: {e.response.status_code} - {e.response.text}"
            else:
                error_message = f"LinkedIn API Error: {e}"
            frappe.log_error(error_message, "LinkedIn API Request")
            return {"status": "error", "error": error_message}

    def post_to_linkedin(self, content, image_attachment=None, document=None, document_title=None):
        """Post content to LinkedIn using the appropriate API."""
        if self.linkedin_doc.connection_status != "Connected":
            frappe.throw(_("LinkedIn account is not connected. Please reconnect your account."))

        post_data, api_type = self._prepare_linkedin_post_data(content, image_attachment, document, document_title)
        
        # Choose the right API endpoint
        if api_type == "ugcPosts":
            url = "https://api.linkedin.com/v2/ugcPosts"
            headers = self._get_headers()
            # Remove LinkedIn-Version header for UGC Posts (it uses older format)
            if "LinkedIn-Version" in headers:
                del headers["LinkedIn-Version"]
        else:
            url = "https://api.linkedin.com/rest/posts"
            headers = self._get_headers()
        
        return self._make_linkedin_api_request("POST", url, headers=headers, json=post_data)

    def update_linkedin_post(self, post_id, content):
        """Update an existing LinkedIn post."""
        if not post_id:
            frappe.throw(_("Post ID is required for updating"))

        url = f"https://api.linkedin.com/rest/posts/{post_id}"
        headers = self._get_headers()
        
        update_data = { "patch": { "$set": { "commentary": content } } }
        
        # Using a PATCH request is more semantic for partial updates
        response = self._make_linkedin_api_request("PATCH", url, headers=headers, json=update_data)
        if response.get("status") == "success":
            response["message"] = _("Post updated successfully on LinkedIn")
        return response

    def delete_linkedin_post(self, post_id):
        """Delete a LinkedIn post."""
        if not post_id:
            frappe.throw(_("Post ID is required for deletion"))

        url = f"https://api.linkedin.com/rest/posts/{post_id}"
        headers = self._get_headers()
        
        response = self._make_linkedin_api_request("DELETE", url, headers=headers)
        if response.get("status") == "success":
            response["message"] = _("Post deleted successfully from LinkedIn")
        return response
    

@frappe.whitelist(allow_guest=True)
def callback(code=None, state=None, error=None, *args, **kwargs):
    """Handle LinkedIn OAuth callback"""
    if error:
        frappe.log_error(f"LinkedIn OAuth Error: {kwargs.get('error_description')}", "LinkedIn OAuth Callback")
        return {"error": f"LinkedIn login failed: {kwargs.get('error_description')}"}

    try:
        integrations = frappe.get_all("LinkedIn Integration", filters={"state": state}, fields=['name'])
        if not integrations:
            frappe.throw(f"No LinkedIn Integration found with state: {state}")
        
        integration = frappe.get_doc("LinkedIn Integration", integrations[0].name)
        client_id = integration.client_id
        client_secret = integration.get_password("client_secret")
        redirect_uri = integration.redirect_uri

        token_payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        res = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data=token_payload)
        res.raise_for_status()
        token_data = res.json()

        access_token = token_data.get("access_token")
        expiry_seconds = token_data.get("expires_in")
        
        integration.access_token = access_token
        if expiry_seconds:
            integration.expires_in = (datetime.now() + timedelta(seconds=expiry_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        integration.connection_status = "Connected"
        integration.full_name, integration.email, integration.person_id = _fetch_member_profile(
            access_token, integration.organization_support
        )
        
        integration.save(ignore_permissions=True)
        frappe.db.commit()

        frappe.respond_as_web_page("Success", "LinkedIn connection successful! You can close this window.", http_status_code=200)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "LinkedIn OAuth Callback Error")
        frappe.respond_as_web_page("Error", f"An error occurred: {str(e)}", http_status_code=500)

def _fetch_member_profile(access_token, organization_support):
    """Return (full name, email, person id) of the member who authorised the app."""
    headers = {"Authorization": f"Bearer {access_token}"}
    if not organization_support:
        res = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=30)
        res.raise_for_status()
        info = res.json()
        return info.get("name"), info.get("email"), info.get("sub")

    # Community Management API apps have no OpenID Connect; r_basicprofile serves /v2/me and no email.
    res = requests.get("https://api.linkedin.com/v2/me", headers=headers, timeout=30)
    res.raise_for_status()
    info = res.json()
    full_name = " ".join(filter(None, [info.get("localizedFirstName"), info.get("localizedLastName")]))
    return full_name or None, None, info.get("id")
