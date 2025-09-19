# Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
import requests
import json
import base64
import secrets
import os
from uuid import uuid4
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode, parse_qs
from frappe.model.document import Document
from frappe import _


class RedditIntegration(Document):
    def before_save(self):
        """Generate state for OAuth flow"""
        if not self.state:
            self.state = secrets.token_urlsafe(32)
        
        # Set default redirect URI if not provided
        if not self.redirect_uri:
            self.redirect_uri = f"https://aicrm.finbyz.tech/api/method/ai_crm.credentials.doctype.reddit_integration.reddit_integration.reddit_callback"

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
            if not self.access_token:
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
                
                return {
                    "status": "success",
                    "message": _("Reddit connection successful"),
                    "username": self.username
                }
            else:
                self.connection_status = "Error"
                return {
                    "status": "error",
                    "message": f"Reddit API Error: {response.status_code}"
                }
                
        except Exception as e:
            self.connection_status = "Error"
            return {
                "status": "error",
                "message": str(e)
            }
    
    @frappe.whitelist()
    def get_authorization_url(self):
        """Step 1: Generate Reddit OAuth authorization URL"""
        try:
            # Reddit OAuth2 parameters
            params = {
                "client_id": self.client_id,
                "response_type": "code",
                "state": self.state,
                "redirect_uri": self.redirect_uri,
                "duration": "permanent",  # Request permanent access
                "scope": "identity submit read edit"  # Required scopes
            }
            
            auth_url = "https://www.reddit.com/api/v1/authorize?" + urlencode(params)
            
            # Update status to pending
            self.connection_status = "Pending Authorization"
            self.save(ignore_permissions=True)
            
            return {
                "status": "success",
                "auth_url": auth_url,
                "state": self.state
            }
                
        except Exception as e:
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
                
                # Set expiry time
                expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
                self.expires_at = frappe.utils.add_to_date(
                    frappe.utils.now(), 
                    seconds=expires_in
                )
                
                self.connection_status = "Connected"
                self.connected_at = frappe.utils.now()
                
                return {
                    "status": "success",
                    "message": "Access token obtained successfully"
                }
            else:
                self.connection_status = "Error"
                return {
                    "status": "error",
                    "message": f"Reddit Token Error: {response.status_code}"
                }
                
        except Exception as e:
            self.connection_status = "Error"
            return {
                "status": "error",
                "message": str(e)
            }
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        try:
            if not self.refresh_token:
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
                self.expires_at = frappe.utils.add_to_date(
                    frappe.utils.now(), 
                    seconds=expires_in
                )
                
                self.save(ignore_permissions=True)
                
                return {
                    "status": "success",
                    "message": "Token refreshed successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": f"Token refresh failed: {response.status_code}"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _get_valid_token(self):
        """Get a valid access token, refresh if needed"""
        if not self.access_token:
            return None
        
        # Check if token is expired
        if self.expires_at and frappe.utils.now_datetime() >= frappe.utils.get_datetime(self.expires_at):
            refresh_result = self.refresh_access_token()
            if refresh_result.get("status") != "success":
                return None
        
        return self.get_password("access_token")
    
    @frappe.whitelist()
    def create_post(self, subreddit, title, content=None, url=None, is_self=True):
        """Create a post on Reddit"""
        try:
            token = self._get_valid_token()
            if not token:
                return {
                    "status": "error",
                    "message": "No valid access token available"
                }
            
            api_url = "https://oauth.reddit.com/api/submit"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "sr": subreddit,
                "title": title,
                "kind": "self" if is_self else "link",
                "api_type": "json"
            }
            
            if is_self and content:
                data["text"] = content
            elif not is_self and url:
                data["url"] = url
            
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
                    "message": "Post created successfully",
                    "url": post_url,
                    "id": post_data.get("id")
                }
            else:
                return {
                    "status": "error",
                    "message": f"Post creation failed: {response.status_code}"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
            
    @frappe.whitelist()
    def create_comment(self, post_id, comment_text):
        """Create a comment on a Reddit post"""
        try:
            token = self._get_valid_token()
            if not token:
                return {"status": "error", "message": "No valid access token available"}

            api_url = "https://oauth.reddit.com/api/comment"
            headers = {
                "Authorization": f"Bearer {token}",
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
                return {"status": "error", "message": f"Comment failed: {response.status_code}"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def upload_media(self, filepath, mimetype):
        """Upload image/video to Reddit and return asset_id"""
        try:
            # Validate inputs
            if not filepath:
                return {"status": "error", "message": "Filepath is required"}
            if not mimetype:
                return {"status": "error", "message": "Mimetype is required"}
            if not os.path.exists(str(filepath)):
                return {"status": "error", "message": f"File not found: {filepath}"}
            
            token = self._get_valid_token()
            if not token:
                return {"status": "error", "message": "No valid access token"}

            filename = os.path.basename(str(filepath))
            if not filename:
                return {"status": "error", "message": "Invalid filepath"}
                
            file_size = os.path.getsize(str(filepath))
            
            # Step 1: Request upload lease
            url = "https://oauth.reddit.com/api/media/asset.json"
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/json"
            }
            
            data = {"filepath": filename, "mimetype": mimetype}
            response = requests.post(url, headers=headers, json=data, timeout=30)

            if response.status_code != 200:
                return {"status": "error", "message": f"Asset request failed: {response.status_code}"}

            response_data = response.json()
            asset_info = response_data.get("asset", {})
            upload_lease = response_data.get("args", {})
            
            asset_id = asset_info.get("asset_id")
            upload_url = upload_lease.get("action")
            fields = upload_lease.get("fields", {})
            websocket_url = asset_info.get("websocket_url")

            if not upload_url or not asset_id:
                return {"status": "error", "message": "Upload URL or asset_id missing"}

            # Step 2: Upload to S3
            with open(str(filepath), "rb") as file_obj:
                form_data = fields if isinstance(fields, dict) else {}
                files = {"file": (filename, file_obj, mimetype)}
                upload_response = requests.post(upload_url, data=form_data, files=files, timeout=120)

            if upload_response.status_code not in [200, 201, 204]:
                return {"status": "error", "message": f"Upload failed: {upload_response.status_code}"}

            return {"status": "success", "asset_id": asset_id, "websocket_url": websocket_url}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def create_media_post(self, subreddit, title, media_url=None, filepath=None, mimetype="image/jpeg", kind="image"):
        """Create a Reddit post with image or video"""
        try:
            # Validate required parameters
            if not subreddit:
                return {"status": "error", "message": "Subreddit is required"}
            
            if not title:
                return {"status": "error", "message": "Title is required"}
            
            token = self._get_valid_token()
            if not token:
                return {"status": "error", "message": "No valid access token"}

            # If external media URL is provided, create link post
            if media_url and not filepath:
                return self._create_link_post(subreddit, title, media_url, token)
            
            # If filepath is provided, upload and create image post
            if filepath:
                return self._create_image_post(subreddit, title, filepath, mimetype, token)
            
            return {"status": "error", "message": "Either media_url or filepath is required"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _create_link_post(self, subreddit, title, url, token):
        """Create a link post with external URL"""
        try:
            api_url = "https://oauth.reddit.com/api/submit"
            headers = {
                "Authorization": f"Bearer {token}",
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
                    
                return {"status": "success", "message": "Link post created", "url": post_url, "id": post_data.get("id")}
            else:
                return {"status": "error", "message": f"Link post failed: {response.text}"}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _create_image_post(self, subreddit, title, filepath, mimetype, token):
        """Create an image post using Reddit's media upload"""
        try:
            # Step 1: Upload media and get asset_id
            upload_result = self.upload_media(filepath, mimetype)
            if upload_result.get("status") != "success":
                return upload_result

            asset_id = upload_result["asset_id"]
            websocket_url = upload_result.get("websocket_url")
            
            # Step 2: Submit gallery post (most reliable for images)
            api_url = "https://oauth.reddit.com/api/submit_gallery_post.json"
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/json"
            }
            
            data = {
                "sr": subreddit,
                "title": title,
                "items": [{"media_id": asset_id}],
                "api_type": "json"
            }
            
            response = requests.post(api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("json", {}).get("errors"):
                    errors = result["json"]["errors"]
                    error_msg = "; ".join([str(error) for error in errors])
                    # Try alternative if gallery fails
                    return self._submit_with_richtext(subreddit, title, asset_id, token)

                post_data = result.get("json", {}).get("data", {})
                post_url = f"https://www.reddit.com{post_data.get('url', '')}"
                    
                return {"status": "success", "message": "Image post created", "url": post_url, "id": post_data.get("id")}
            else:
                # Try richtext editor format
                return self._submit_with_richtext(subreddit, title, asset_id, token)
                
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _submit_with_richtext(self, subreddit, title, asset_id, token):
        """Submit using richtext editor format"""
        try:
            api_url = "https://oauth.reddit.com/api/submit"
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            # Richtext JSON format for embedded media
            richtext_json = {
                "document": [
                    {
                        "c": [{"e": "img", "id": asset_id}],
                        "e": "par"
                    }
                ]
            }
            
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
                if result.get("json", {}).get("errors"):
                    errors = result["json"]["errors"]
                    error_msg = "; ".join([str(error) for error in errors])
                    return {"status": "error", "message": f"Richtext API Error: {error_msg}"}

                post_data = result.get("json", {}).get("data", {})
                post_url = f"https://www.reddit.com{post_data.get('url', '')}"
                
                return {"status": "success", "message": "Richtext image post created", "url": post_url, "id": post_data.get("id")}
            else:
                return {"status": "error", "message": f"All image post methods failed: {response.text}"}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _create_gallery_post(self, subreddit, title, asset_id, token):
        """Alternative method: Create gallery post"""
        try:
            api_url = "https://oauth.reddit.com/api/submit_gallery_post.json"
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/json"
            }
            
            data = {
                "sr": subreddit,
                "title": title,
                "items": [{"media_id": asset_id}],  # Gallery format
                "api_type": "json"
            }
            
            response = requests.post(api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("json", {}).get("errors"):
                    errors = result["json"]["errors"]
                    error_msg = "; ".join([str(error) for error in errors])
                    return {"status": "error", "message": f"Reddit Gallery API Error: {error_msg}"}

                post_data = result.get("json", {}).get("data", {})
                api_url_value = post_data.get("url", "")
                
                if api_url_value.startswith("http"):
                    post_url = api_url_value
                else:
                    post_url = f"https://www.reddit.com{api_url_value}"
                    
                return {"status": "success", "message": "Gallery post created", "url": post_url, "id": post_data.get("id")}
            else:
                return {"status": "error", "message": f"Gallery post failed: {response.text}"}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def create_image_post_simple(self, subreddit, title, image_path):
        """Direct image post - most reliable method"""
        try:
            # Validate inputs
            if not image_path:
                return {"status": "error", "message": "Image path is required"}
            if not subreddit:
                return {"status": "error", "message": "Subreddit is required"}
            if not title:
                return {"status": "error", "message": "Title is required"}
                
            # Auto-detect mimetype
            file_ext = os.path.splitext(str(image_path))[1].lower()
            mimetype_map = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                '.gif': 'image/gif', '.webp': 'image/webp'
            }
            mimetype = mimetype_map.get(file_ext, 'image/jpeg')
            
            # Upload first
            upload_result = self.upload_media(image_path, mimetype)
            if upload_result.get("status") != "success":
                return upload_result

            asset_id = upload_result["asset_id"]
            token = self._get_valid_token()
            
            # Try gallery post first (most reliable for images)
            try:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": self.user_agent,
                    "Content-Type": "application/json"
                }
                
                data = {
                    "sr": subreddit,
                    "title": title,
                    "items": [{"media_id": asset_id}]
                }
                
                response = requests.post(
                    "https://oauth.reddit.com/api/submit_gallery_post.json",
                    headers=headers, json=data, timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if not result.get("json", {}).get("errors"):
                        post_data = result.get("json", {}).get("data", {})
                        post_url = f"https://www.reddit.com{post_data.get('url', '')}"
                        return {"status": "success", "message": "Gallery image post created", "url": post_url}
            except:
                pass
            
            # Fallback: richtext format
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            richtext_json = {
                "document": [{"c": [{"e": "img", "id": asset_id}], "e": "par"}]
            }
            
            data = {
                "sr": subreddit,
                "title": title,
                "kind": "self",
                "richtext_json": json.dumps(richtext_json),
                "api_type": "json"
            }
            
            response = requests.post(
                "https://oauth.reddit.com/api/submit",
                headers=headers, data=data, timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if not result.get("json", {}).get("errors"):
                    post_data = result.get("json", {}).get("data", {})
                    post_url = f"https://www.reddit.com{post_data.get('url', '')}"
                    return {"status": "success", "message": "Richtext image post created", "url": post_url}
                else:
                    errors = result["json"]["errors"]
                    return {"status": "error", "message": f"Reddit errors: {errors}"}
            
            return {"status": "error", "message": "All image post methods failed"}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def test_image_post(self, image_path=None):
        """Test image posting in r/test subreddit"""
        if not image_path:
            return {"status": "error", "message": "Image path is required"}
            
        return self.create_image_post_simple(
            subreddit='test',
            title=f'Test Image Post from Frappe - {frappe.utils.now()}',
            image_path=image_path
        )

    @frappe.whitelist()
    def test_post(self):
        """Create a test post in r/test subreddit"""
        return self.create_post(
            subreddit='test',
            title='Test Post from Frappe Integration',
            content=f'This is a test post created at {frappe.utils.now()}'
        )


# Simplified callback function - removed excessive logging
@frappe.whitelist(allow_guest=True)
def reddit_callback(state=None, code=None, error=None, *args, **kwargs):
    """Handle Reddit OAuth callback"""
    try:
        if error:
            return f"""
            <html>
            <body>
                <h2>Reddit Authorization Failed</h2>
                <p>Error: {error}</p>
                <script>
                    setTimeout(function() {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
            </html>
            """
        
        if not code:
            return """
            <html>
            <body>
                <h2>Reddit Authorization Failed</h2>
                <p>Error: No authorization code received</p>
                <script>
                    setTimeout(function() {
                        window.close();
                    }, 5000);
                </script>
            </body>
            </html>
            """
        
        # Find Reddit Integration record
        reddit_integration = None
        
        # Try to find by state if provided
        if state and state not in ["None", "null"]:
            try:
                integrations = frappe.get_list(
                    "Reddit Integration",
                    filters={"state": state},
                    pluck='name'
                )
                
                if integrations:
                    reddit_integration = frappe.get_doc("Reddit Integration", integrations[0])
                    
            except Exception:
                pass
        
        # If state method fails, find the most recent pending record
        if not reddit_integration:
            try:
                records = frappe.get_all("Reddit Integration", 
                                        filters={"connection_status": ["in", ["Pending Authorization", "Not Connected"]]},
                                        order_by="creation desc",
                                        limit=1)
                
                if records:
                    reddit_integration = frappe.get_doc("Reddit Integration", records[0].name)
                    
            except Exception:
                pass
        
        # If still not found, find any Reddit Integration record
        if not reddit_integration:
            try:
                records = frappe.get_all("Reddit Integration", 
                                        order_by="modified desc",
                                        limit=1)
                if records:
                    reddit_integration = frappe.get_doc("Reddit Integration", records[0].name)
                    
            except Exception:
                pass
        
        if not reddit_integration:
            return """
            <html>
            <body>
                <h2>Reddit Authorization Failed</h2>
                <p>Error: No Reddit Integration record found</p>
                <script>
                    setTimeout(function() {
                        window.close();
                    }, 5000);
                </script>
            </body>
            </html>
            """
        
        # Exchange code for access token
        result = reddit_integration._get_access_token(code)
        
        if result["status"] == "success":
            # Test the connection to get user info
            test_result = reddit_integration.test_connection()
            
            if test_result.get("status") == "success":
                # Save the updated integration
                reddit_integration.save(ignore_permissions=True)
                
                
                return """
                <html>
                <body>
                    <h2>Reddit Authorization Successful!</h2>
                    <p>Your Reddit account has been connected successfully.</p>
                    <p>You can now close this window and return to the application.</p>
                    <script>
                        setTimeout(function() {
                            window.close();
                        }, 3000);
                    </script>
                </body>
                </html>
                """
            else:
                return f"""
                <html>
                <body>
                    <h2>Reddit Authorization Failed</h2>
                    <p>Error: Connection test failed</p>
                    <script>
                        setTimeout(function() {{
                            window.close();
                        }}, 5000);
                    </script>
                </body>
                </html>
                """
        else:
            return f"""
            <html>
            <body>
                <h2>Reddit Authorization Failed</h2>
                <p>Error: {result.get('message', 'Failed to get access token')}</p>
                <script>
                    setTimeout(function() {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
            </html>
            """
            
    except Exception as e:
        return f"""
        <html>
        <body>
            <h2>Reddit Authorization Error</h2>
            <p>Error: {str(e)}</p>
            <script>
                setTimeout(function() {{
                    window.close();
                }}, 5000);
            </script>
        </body>
        </html>
        """

# Keep the old callback function name for backward compatibility
@frappe.whitelist(allow_guest=True)
def callback(state=None, code=None, error=None, *args, **kwargs):
    """Backward compatibility - redirect to reddit_callback"""
    return reddit_callback(state, code, error, *args, **kwargs)