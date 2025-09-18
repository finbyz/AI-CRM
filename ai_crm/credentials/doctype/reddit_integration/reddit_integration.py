# Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
import requests
import json
import base64
import secrets
import os
import mimetypes
import time
from uuid import uuid4
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode, parse_qs
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime
from frappe import _


class RedditIntegration(Document):
    def before_save(self):
        """Generate state for OAuth flow"""
        if not self.state:
            self.state = secrets.token_urlsafe(32)
        
        # Set default redirect URI if not provided
        if not self.redirect_uri:
            site_url = frappe.utils.get_url()
            self.redirect_uri = f"{site_url}/api/method/ai_crm.credentials.doctype.reddit_integration.reddit_integration.reddit_callback"

        # Set default user agent if not provided
        if not self.user_agent:
            self.user_agent = "FrappeSocialBot:1.0:web (by /u/Future_Sprinkles_492)"

    def validate(self):
        """Validate Reddit credentials when they are provided"""
        if self.access_token and self.connection_status == "Connected":
            # Test existing connection
            self.test_connection()
    
    @frappe.whitelist()
    def test_connection(self):
        """Test Reddit API connection"""
        try:
            if not self.get_password('access_token'):
                return {
                    "status": "error",
                    "message": _("Access token not available. Please connect your Reddit account.")
                }
            
            # Test with a simple API call to get user info
            url = "https://oauth.reddit.com/api/v1/me"
            
            headers = {
                "Authorization": f"Bearer {self.get_password('access_token')}",
                "User-Agent": self.user_agent
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                user_data = response.json()
                self.username = user_data.get("name", "")
                self.user_id = user_data.get("id", "")
                self.connection_status = "Connected"
                self.connected_at = frappe.utils.now()
                self.save(ignore_permissions=True)
                frappe.db.commit()
                
                return {
                    "status": "success",
                    "message": _("Reddit connection successful"),
                    "username": self.username
                }
            else:
                self.connection_status = "Error"
                self.save(ignore_permissions=True)
                frappe.db.commit()
                return {
                    "status": "error",
                    "message": f"Reddit API Error: {response.status_code} - {response.text}"
                }
                
        except Exception as e:
            self.connection_status = "Error"
            self.save(ignore_permissions=True)
            frappe.db.commit()
            return {
                "status": "error",
                "message": str(e)
            }
    
    @frappe.whitelist()
    def get_authorization_url(self):
        """Step 1: Generate Reddit OAuth authorization URL"""
        try:
            if not self.client_id:
                frappe.throw("Client ID is required.")
            
            # Reddit OAuth2 parameters
            params = {
                "client_id": self.client_id,
                "response_type": "code",
                "state": self.state,
                "redirect_uri": self.redirect_uri,
                "duration": "permanent",  # Request permanent access
                "scope": "identity submit read edit history"  # Required scopes including history for better access
            }
            
            auth_url = "https://www.reddit.com/api/v1/authorize?" + urlencode(params)
            
            # Update status to pending
            self.connection_status = "Pending Authorization"
            self.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "status": "success",
                "auth_url": auth_url,
                "state": self.state
            }
                
        except Exception as e:
            frappe.log_error(
                title="Reddit Authorization URL Error", 
                message=frappe.get_traceback()
            )
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _get_access_token(self, code):
        """Step 2: Exchange authorization code for access token"""
        try:
            url = "https://www.reddit.com/api/v1/access_token"
            
            # Prepare auth header (Basic Auth with client credentials)
            client_secret = self.get_password("client_secret") or ""
            auth_string = f"{self.client_id}:{client_secret}"
            auth_encoded = base64.b64encode(auth_string.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {auth_encoded}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri
            }
            
            response = requests.post(url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                
                self.access_token = token_data.get("access_token")
                self.refresh_token = token_data.get("refresh_token")
                self.token_type = token_data.get("token_type", "bearer")
                
                # Set expiry time - use token_expires_at field
                expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
                self.token_expires_at = now_datetime() + timedelta(seconds=expires_in)
                
                self.connection_status = "Connected"
                self.connected_at = frappe.utils.now()
                
                return {
                    "status": "success",
                    "message": "Access token obtained successfully"
                }
            else:
                self.connection_status = "Error"
                frappe.log_error(
                    title="Reddit Token Exchange Error",
                    message=f"Status: {response.status_code}, Response: {response.text}"
                )
                return {
                    "status": "error",
                    "message": f"Reddit Token Error: {response.status_code} - {response.text}"
                }
                
        except Exception as e:
            self.connection_status = "Error"
            frappe.log_error(
                title="Reddit Token Exchange Exception",
                message=frappe.get_traceback()
            )
            return {
                "status": "error",
                "message": str(e)
            }
    
    @frappe.whitelist()
    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        try:
            if not self.get_password('refresh_token'):
                return {
                    "status": "error",
                    "message": "No refresh token available"
                }
            
            url = "https://www.reddit.com/api/v1/access_token"
            
            client_secret = self.get_password("client_secret") or ""
            auth_string = f"{self.client_id}:{client_secret}"
            auth_encoded = base64.b64encode(auth_string.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {auth_encoded}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.get_password("refresh_token")
            }
            
            response = requests.post(url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                
                self.access_token = token_data.get("access_token")
                # Note: Reddit may not provide a new refresh token
                if token_data.get("refresh_token"):
                    self.refresh_token = token_data.get("refresh_token")
                
                expires_in = token_data.get("expires_in", 3600)
                self.token_expires_at = now_datetime() + timedelta(seconds=expires_in)
                
                self.save(ignore_permissions=True)
                frappe.db.commit()
                
                return {
                    "status": "success",
                    "message": "Token refreshed successfully"
                }
            else:
                frappe.log_error(
                    title="Reddit Token Refresh Error",
                    message=f"Status: {response.status_code}, Response: {response.text}"
                )
                return {
                    "status": "error",
                    "message": f"Token refresh failed: {response.status_code} - {response.text}"
                }
                
        except Exception as e:
            frappe.log_error(
                title="Reddit Token Refresh Exception",
                message=frappe.get_traceback()
            )
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _get_valid_token(self):
        """Get a valid access token, refresh if needed"""
        if not self.get_password('access_token'):
            return None
        
        # Check if token is expired (with 10 minute buffer)
        if self.token_expires_at:
            token_expiry = (
                get_datetime(self.token_expires_at)
                if isinstance(self.token_expires_at, str)
                else self.token_expires_at
            )
            
            buffer_time = now_datetime() + timedelta(minutes=10)
            
            if buffer_time >= token_expiry:
                frappe.log_error(
                    message="Reddit token expiring soon, attempting refresh",
                    title="Reddit Token Refresh"
                )
                refresh_result = self.refresh_access_token()
                if refresh_result.get("status") != "success":
                    return None
        
        return self.get_password("access_token")
    
    def _get_reddit_headers(self):
        """Get headers for Reddit API calls with valid token"""
        token = self._get_valid_token()
        if not token:
            raise Exception("No valid access token available. Please re-authorize.")
        
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": self.user_agent,
            "Content-Type": "application/json"
        }
    
    def upload_media(self, media_path):
        """Upload media to Reddit and return asset_id"""
        try:
            if not os.path.exists(media_path):
                raise FileNotFoundError(f"Media file not found: {media_path}")
            
            # Get file info
            filename = os.path.basename(media_path)
            file_size = os.path.getsize(media_path)
            mimetype, _ = mimetypes.guess_type(media_path)
            
            if not mimetype:
                # Default mimetype based on extension
                ext = os.path.splitext(filename)[1].lower()
                mimetype_map = {
                    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                    '.gif': 'image/gif', '.webp': 'image/webp', '.mp4': 'video/mp4',
                    '.mov': 'video/quicktime', '.avi': 'video/x-msvideo'
                }
                mimetype = mimetype_map.get(ext, 'image/jpeg')
            
            frappe.log_error(
                message=f"Uploading media: {filename}, Size: {file_size}, Type: {mimetype}",
                title="Reddit Media Upload"
            )
            
            # Step 1: Request upload lease
            url = "https://oauth.reddit.com/api/media/asset.json"
            headers = self._get_reddit_headers()
            
            data = {
                "filepath": filename, 
                "mimetype": mimetype
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code != 200:
                frappe.log_error(
                    message=f"Asset request failed: {response.status_code} - {response.text}",
                    title="Reddit Media Upload Error"
                )
                return None
            
            response_data = response.json()
            asset_info = response_data.get("asset", {})
            upload_lease = response_data.get("args", {})
            
            asset_id = asset_info.get("asset_id")
            upload_url = upload_lease.get("action")
            fields = upload_lease.get("fields", {})
            
            if not upload_url or not asset_id:
                frappe.log_error(
                    message="Upload URL or asset_id missing from Reddit response",
                    title="Reddit Media Upload Error"
                )
                return None
            
            # Step 2: Upload to S3
            with open(media_path, "rb") as file_obj:
                form_data = fields if isinstance(fields, dict) else {}
                files = {"file": (filename, file_obj, mimetype)}
                
                upload_response = requests.post(
                    upload_url, 
                    data=form_data, 
                    files=files, 
                    timeout=120
                )
            
            if upload_response.status_code not in [200, 201, 204]:
                frappe.log_error(
                    message=f"S3 upload failed: {upload_response.status_code} - {upload_response.text}",
                    title="Reddit Media Upload Error"
                )
                return None
            
            frappe.log_error(
                message=f"Media uploaded successfully. Asset ID: {asset_id}",
                title="Reddit Media Upload Success"
            )
            
            return asset_id
            
        except Exception as e:
            frappe.log_error(
                message=f"Media upload exception: {str(e)}",
                title="Reddit Media Upload Error"
            )
            return None
    
    @frappe.whitelist()
    def post_to_reddit(self, subreddit, title, content=None, image_attachment=None, url=None):
        """Post to Reddit with optional media - FIXED WITH WHITELIST DECORATOR"""
        try:
            if not subreddit:
                return {"status": "error", "message": "Subreddit is required"}
            
            if not title:
                return {"status": "error", "message": "Title is required"}
            
            # If external URL is provided, create link post
            if url and not image_attachment:
                return self._create_link_post(subreddit, title, url)
            
            # If image attachment is provided, create image post
            if image_attachment:
                try:
                    # Get file path from Frappe
                    file_doc = (
                        frappe.get_doc("File", image_attachment)
                        if frappe.db.exists("File", image_attachment)
                        else frappe.get_doc("File", {"file_url": image_attachment})
                    )
                    file_path = file_doc.get_full_path()
                    
                    # Upload media first
                    asset_id = self.upload_media(file_path)
                    if not asset_id:
                        return {"status": "error", "message": "Failed to upload media"}
                    
                    # Create image post
                    return self._create_image_post(subreddit, title, asset_id, content)
                    
                except Exception as e:
                    return {"status": "error", "message": f"Image processing failed: {str(e)}"}
            
            # Create text post
            return self._create_text_post(subreddit, title, content)
            
        except Exception as e:
            return {"status": "error", "message": f"General error: {str(e)}"}
    
    def _create_text_post(self, subreddit, title, content=None):
        """Create a text post"""
        try:
            api_url = "https://oauth.reddit.com/api/submit"
            headers = {
                "Authorization": f"Bearer {self._get_valid_token()}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "sr": subreddit,
                "title": title,
                "kind": "self",
                "api_type": "json"
            }
            
            if content:
                data["text"] = content
            
            response = requests.post(api_url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("json", {}).get("errors"):
                    errors = result["json"]["errors"]
                    error_msg = "; ".join([str(error) for error in errors])
                    return {
                        "status": "error",
                        "message": f"Reddit API Error: {error_msg}"
                    }
                
                post_data = result.get("json", {}).get("data", {})
                api_url_value = post_data.get("url", "")
                
                if api_url_value.startswith("http"):
                    post_url = api_url_value
                else:
                    post_url = f"https://www.reddit.com{api_url_value}"
                
                return {
                    "status": "success",
                    "message": "Text post created successfully",
                    "url": post_url,
                    "id": post_data.get("id")
                }
            else:
                return {
                    "status": "error",
                    "message": f"Text post creation failed: {response.status_code} - {response.text}"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Text post error: {str(e)}"
            }
    
    def _create_link_post(self, subreddit, title, url):
        """Create a link post with external URL"""
        try:
            api_url = "https://oauth.reddit.com/api/submit"
            headers = {
                "Authorization": f"Bearer {self._get_valid_token()}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
             
            data = {
                "sr": subreddit,
                "title": title,
                "kind": "link",
                "url": url,
                "api_type": "json"
            }

            response = requests.post(api_url, headers=headers, data=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get("json", {}).get("errors"):
                    errors = result["json"]["errors"]
                    error_msg = "; ".join([str(error) for error in errors])
                    return {"status": "error", "message": f"Reddit API Error: {error_msg}"}

                post_data = result.get("json", {}).get("data", {})
                api_url_value = post_data.get("url", "")
                
                if api_url_value.startswith("http"):
                    post_url = api_url_value
                else:
                    post_url = f"https://www.reddit.com{api_url_value}"
                    
                return {
                    "status": "success", 
                    "message": "Link post created successfully", 
                    "url": post_url, 
                    "id": post_data.get("id")
                }
            else:
                return {
                    "status": "error", 
                    "message": f"Link post failed: {response.status_code} - {response.text}"
                }
                
        except Exception as e:
            return {"status": "error", "message": f"Link post error: {str(e)}"}
    
    def _create_image_post(self, subreddit, title, asset_id, content=None):
        """Create an image post using uploaded asset_id"""
        try:
            # Method 1: Try gallery post first (most reliable for single images)
            result = self._try_gallery_post(subreddit, title, asset_id)
            if result.get("status") == "success":
                return result
            
            # Method 2: Try richtext format
            result = self._try_richtext_post(subreddit, title, asset_id, content)
            if result.get("status") == "success":
                return result
            
            # Method 3: Try inline media format
            result = self._try_inline_media_post(subreddit, title, asset_id)
            if result.get("status") == "success":
                return result
            
            return {
                "status": "error",
                "message": "All image post methods failed"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Image post error: {str(e)}"
            }
    
    def _try_gallery_post(self, subreddit, title, asset_id):
        """Try creating a gallery post"""
        try:
            api_url = "https://oauth.reddit.com/api/submit_gallery_post.json"
            headers = self._get_reddit_headers()
            
            data = {
                "sr": subreddit,
                "title": title,
                "items": [{"media_id": asset_id}],
                "api_type": "json"
            }
            
            response = requests.post(api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if not result.get("json", {}).get("errors"):
                    post_data = result.get("json", {}).get("data", {})
                    post_url = f"https://www.reddit.com{post_data.get('url', '')}"
                    return {
                        "status": "success", 
                        "message": "Gallery image post created successfully", 
                        "url": post_url,
                        "id": post_data.get("id")
                    }
            
            return {"status": "error", "message": "Gallery post failed"}
            
        except Exception:
            return {"status": "error", "message": "Gallery post exception"}
    
    def _try_richtext_post(self, subreddit, title, asset_id, content=None):
        """Try creating a richtext post with embedded image"""
        try:
            api_url = "https://oauth.reddit.com/api/submit"
            headers = {
                "Authorization": f"Bearer {self._get_valid_token()}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # Create richtext JSON structure
            richtext_document = [{"c": [{"e": "img", "id": asset_id}], "e": "par"}]
            
            # Add text content if provided
            if content:
                richtext_document.append({
                    "c": [{"e": "text", "t": content}],
                    "e": "par"
                })
            
            richtext_json = {"document": richtext_document}
            
            data = {
                "sr": subreddit,
                "title": title,
                "kind": "self",
                "richtext_json": json.dumps(richtext_json),
                "api_type": "json"
            }
            
            response = requests.post(api_url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if not result.get("json", {}).get("errors"):
                    post_data = result.get("json", {}).get("data", {})
                    post_url = f"https://www.reddit.com{post_data.get('url', '')}"
                    return {
                        "status": "success", 
                        "message": "Richtext image post created successfully", 
                        "url": post_url,
                        "id": post_data.get("id")
                    }
            
            return {"status": "error", "message": "Richtext post failed"}
            
        except Exception:
            return {"status": "error", "message": "Richtext post exception"}
    
    def _try_inline_media_post(self, subreddit, title, asset_id):
        """Try creating an inline media post"""
        try:
            api_url = "https://oauth.reddit.com/api/submit"
            headers = {
                "Authorization": f"Bearer {self._get_valid_token()}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "sr": subreddit,
                "title": title,
                "kind": "image",
                "media_id": asset_id,
                "api_type": "json"
            }
            
            response = requests.post(api_url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if not result.get("json", {}).get("errors"):
                    post_data = result.get("json", {}).get("data", {})
                    post_url = f"https://www.reddit.com{post_data.get('url', '')}"
                    return {
                        "status": "success", 
                        "message": "Inline media post created successfully", 
                        "url": post_url,
                        "id": post_data.get("id")
                    }
            
            return {"status": "error", "message": "Inline media post failed"}
            
        except Exception:
            return {"status": "error", "message": "Inline media post exception"}
    
    # Legacy methods for backward compatibility - ALL WHITELISTED
    @frappe.whitelist()
    def create_post(self, subreddit, title, content=None, url=None, is_self=True):
        """Legacy method - redirects to post_to_reddit"""
        if url and not is_self:
            return self.post_to_reddit(subreddit, title, url=url)
        else:
            return self.post_to_reddit(subreddit, title, content=content)
    
    @frappe.whitelist()
    def create_media_post(self, subreddit, title, media_url=None, filepath=None, mimetype="image/jpeg", kind="image"):
        """Legacy method - redirects to post_to_reddit"""
        if media_url:
            return self.post_to_reddit(subreddit, title, url=media_url)
        elif filepath:
            return self.post_to_reddit(subreddit, title, image_attachment=filepath)
        else:
            return {"status": "error", "message": "Either media_url or filepath is required"}
    
    @frappe.whitelist()
    def create_image_post_simple(self, subreddit, title, image_path):
        """Legacy method - redirects to post_to_reddit"""
        return self.post_to_reddit(subreddit, title, image_attachment=image_path)
            
    @frappe.whitelist()
    def create_comment(self, post_id, comment_text):
        """Create a comment on a Reddit post"""
        try:
            api_url = "https://oauth.reddit.com/api/comment"
            headers = {
                "Authorization": f"Bearer {self._get_valid_token()}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            thing_id = f"t3_{post_id}"   

            data = {
                "thing_id": thing_id,   
                "text": comment_text,
                "api_type": "json"
            }
            
            response = requests.post(api_url, headers=headers, data=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get("json", {}).get("errors"):
                    errors = result["json"]["errors"]
                    error_msg = "; ".join([str(error) for error in errors])
                    return {"status": "error", "message": f"Reddit API Error: {error_msg}"}

                return {"status": "success", "message": "Comment created successfully"}
            else:
                return {"status": "error", "message": f"Comment failed: {response.status_code} - {response.text}"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def test_post(self):
        """Create a test post in r/test subreddit"""
        return self.post_to_reddit(
            subreddit='test',
            title=f'Test Post from Frappe Integration - {frappe.utils.now()}',
            content=f'This is a test post created at {frappe.utils.now()}'
        )

    @frappe.whitelist()
    def test_image_post(self, image_path=None):
        """Test image posting in r/test subreddit"""
        if not image_path:
            return {"status": "error", "message": "Image path is required"}
            
        return self.post_to_reddit(
            subreddit='test',
            title=f'Test Image Post from Frappe - {frappe.utils.now()}',
            image_attachment=image_path
        )


# Callback function
@frappe.whitelist(allow_guest=True)
def reddit_callback(state=None, code=None, error=None, *args, **kwargs):
    """Handle Reddit OAuth callback"""
    try:
        if error:
            frappe.respond_as_web_page(
                "Reddit Authorization Error", 
                f"Reddit returned an error: {error}",
                indicator_color="red"
            )
            return
        
        if not code:
            frappe.respond_as_web_page(
                "Reddit Authorization Error",
                "No authorization code received from Reddit.",
                indicator_color="red"
            )
            return
        
        # Find Reddit Integration record
        reddit_integration = None
        
        # Try to find by state if provided
        if state and state not in ["None", "null", ""]:
            try:
                integration_doc_name = frappe.db.get_value(
                    "Reddit Integration", {"state": state}
                )
                if integration_doc_name:
                    reddit_integration = frappe.get_doc("Reddit Integration", integration_doc_name)
            except Exception:
                pass
        
        # If state method fails, find the most recent pending record
        if not reddit_integration:
            try:
                records = frappe.get_all(
                    "Reddit Integration", 
                    filters={"connection_status": ["in", ["Pending Authorization", "Not Connected"]]},
                    order_by="creation desc",
                    limit=1
                )
                
                if records:
                    reddit_integration = frappe.get_doc("Reddit Integration", records[0].name)
                    
            except Exception:
                pass
        
        # If still not found, find any Reddit Integration record
        if not reddit_integration:
            try:
                records = frappe.get_all(
                    "Reddit Integration", 
                    order_by="modified desc",
                    limit=1
                )
                if records:
                    reddit_integration = frappe.get_doc("Reddit Integration", records[0].name)
                    
            except Exception:
                pass
        
        if not reddit_integration:
            frappe.respond_as_web_page(
                "Reddit Authorization Error",
                "No Reddit Integration record found. Please create a Reddit Integration record first.",
                indicator_color="red"
            )
            return
        
        # Exchange code for access token
        result = reddit_integration._get_access_token(code)
        
        if result["status"] == "success":
            # Test the connection to get user info
            test_result = reddit_integration.test_connection()
            
            if test_result.get("status") == "success":
                frappe.respond_as_web_page(
                    "Reddit Authorization Successful!",
                    f"Your Reddit account (@{test_result.get('username', 'N/A')}) has been connected successfully. You can now close this window.",
                    indicator_color="green"
                )
            else:
                frappe.respond_as_web_page(
                    "Connection Test Failed",
                    f"Authorization completed but connection test failed: {test_result.get('message', 'Unknown error')}",
                    indicator_color="orange"
                )
        else:
            frappe.respond_as_web_page(
                "Token Exchange Failed",
                f"Failed to exchange authorization code for access token: {result.get('message', 'Unknown error')}",
                indicator_color="red"
            )
            
    except Exception as e:
        frappe.log_error(
            title="Reddit OAuth Callback Error", 
            message=frappe.get_traceback()
        )
        frappe.respond_as_web_page(
            "Authorization Error",
            "An unexpected error occurred during the authorization process. Please try again.",
            indicator_color="red"
        )


# Keep the old callback function name for backward compatibility
@frappe.whitelist(allow_guest=True)
def callback(state=None, code=None, error=None, *args, **kwargs):
    """Backward compatibility - redirect to reddit_callback"""
    return reddit_callback(state, code, error, *args, **kwargs)