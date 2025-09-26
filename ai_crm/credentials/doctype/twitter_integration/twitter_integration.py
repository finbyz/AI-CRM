# Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
import requests
import json
import base64
import secrets
import hashlib
import mimetypes
import os
import time
from uuid import uuid4
from datetime import timedelta
from urllib.parse import urlencode
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime
from requests_oauthlib import OAuth1Session, OAuth1


class TwitterIntegration(Document):
    """
    Handles Twitter API integration using OAuth 2.0 with PKCE for authentication
    and OAuth 1.0a for media uploads.
    """

    def before_save(self):
        """Generate state and code verifier for OAuth 2.0 PKCE flow on first save."""
        if not self.state:
            self.state = str(uuid4())

        if not self.code_verifier:
            # Generate a secure random string for the code verifier (43-128 characters)
            self.code_verifier = (
                base64.urlsafe_b64encode(secrets.token_bytes(32))
                .decode("utf-8")
                .rstrip("=")
            )

        # Set a default redirect URI if one is not provided.
        if not self.redirect_uri:
            site_url = frappe.utils.get_url()
            self.redirect_uri = f"{site_url}/api/method/ai_crm.ai_crm.doctype.twitter_integration.twitter_integration.callback"

    def _generate_code_challenge(self):
        """Generates a code challenge from the code verifier for the PKCE flow."""
        code_sha = hashlib.sha256(self.code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(code_sha).decode("utf-8").rstrip("=")
        return code_challenge

    @frappe.whitelist()
    def get_authorization_url(self):
        """Generate and return the OAuth 2.0 authorization URL for the user to visit."""
        try:
            if not self.client_id:
                frappe.throw("Client ID is a required field.")

            code_challenge = self._generate_code_challenge()

            scopes = [
                "tweet.read",
                "users.read",
                "tweet.write",
                "tweet.moderate.write",
                "follows.read",
                "follows.write",
                "offline.access",
                "like.read",
                "like.write",
                "dm.write",
                "dm.read",
                "list.read",
                "list.write",
                "media.write",
            ]

            auth_params = {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": " ".join(scopes),
                "state": self.state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }

            base_url = "https://twitter.com/i/oauth2/authorize"
            auth_url = f"{base_url}?{urlencode(auth_params)}"

            self.connection_status = "Pending Authorization"
            self.save(ignore_permissions=True)
            frappe.db.commit()

            return {"status": "success", "auth_url": auth_url}
        except Exception as e:
            frappe.log_error(
                title="Authorization URL Error", message=frappe.get_traceback()
            )
            return {"status": "error", "message": str(e)}

    def _exchange_code_for_token(self, authorization_code):
        """Exchange the authorization code for an access token."""
        try:
            url = "https://api.twitter.com/2/oauth2/token"

            client_secret = self.get_password("client_secret")
            if not client_secret:
                raise Exception("Client Secret is required for token exchange.")

            token_data = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": self.code_verifier,
            }

            auth_string = f"{self.client_id}:{client_secret}"
            auth_b64 = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            }

            response = requests.post(url, headers=headers, data=token_data, timeout=30)
            response.raise_for_status()

            token_response = response.json()
            self.access_token = token_response.get("access_token")
            self.refresh_token = token_response.get("refresh_token")
            self.token_type = token_response.get("token_type", "bearer")

            expires_in = token_response.get("expires_in", 7200)
            self.token_expires_at = now_datetime() + timedelta(seconds=expires_in)

            return {
                "status": "success",
                "message": "Access token obtained successfully.",
            }

        except requests.exceptions.HTTPError as he:
            error_message = (
                f"Token exchange failed: {he.response.status_code} - {he.response.text}"
            )
            frappe.log_error(
                title="Twitter Token Exchange HTTPError", message=error_message
            )
            return {"status": "error", "message": error_message}
        except Exception as e:
            frappe.log_error(
                title="Twitter Token Exchange Error", message=frappe.get_traceback()
            )
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def _refresh_access_token(self):
        """Refresh access token with better error handling"""
        try:
            if not self.refresh_token:
                raise Exception("No refresh token available")

            url = "https://api.twitter.com/2/oauth2/token"

            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }

            client_secret = self.get_password("client_secret")
            if not client_secret:
                raise Exception("Client Secret is required")

            auth_string = f"{self.client_id}:{client_secret}"
            auth_b64 = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            }

            response = requests.post(url, headers=headers, data=token_data, timeout=30)

            frappe.log_error(
                message=f"Token refresh response: {response.status_code} - {response.text}",
                title="Twitter Token Refresh",
            )

            if response.status_code == 200:
                token_response = response.json()
                self.access_token = token_response.get("access_token")

                # Update refresh token if provided
                if token_response.get("refresh_token"):
                    self.refresh_token = token_response.get("refresh_token")

                expires_in = token_response.get("expires_in", 7200)
                self.token_expires_at = now_datetime() + timedelta(seconds=expires_in)

                self.save(ignore_permissions=True)
                frappe.db.commit()

                frappe.log_error(
                    message="Token refreshed successfully", title="Twitter Token Refresh"
                )
                return True
            else:
                frappe.log_error(
                    message=f"Token refresh failed: {response.status_code} - {response.text}",
                    title="Twitter Token Refresh Error",
                )
                return False
        except Exception as e:
            frappe.log_error(f"Token refresh failed: {str(e)}", "Twitter OAuth2")
            return False

    def _get_bearer_headers(self):

        # Always check token validity before any API call
        if not self.access_token:
            raise Exception("No access token available. Please re-authorize.")

        if self.token_expires_at:
            token_expiry = (
                get_datetime(self.token_expires_at)
                if isinstance(self.token_expires_at, str)
                else self.token_expires_at
            )

            # Check if token expires in next 10 minutes (increased buffer)
            buffer_time = now_datetime() + timedelta(minutes=10)

            frappe.log_error(
                message=f"Current time: {now_datetime()}, Token expires: {token_expiry}, Buffer time: {buffer_time}",
                title="Twitter Token Check",
            )

            if buffer_time >= token_expiry:
                frappe.log_error(
                    message="Token expiring soon, attempting refresh",
                    title="Twitter Token Refresh",
                )
                refresh_success = self._refresh_access_token()
                if not refresh_success:
                    # Clear the tokens to force re-authorization
                    self.access_token = None
                    self.refresh_token = None
                    self.token_expires_at = None
                    self.connection_status = "Token Expired"
                    self.save(ignore_permissions=True)
                    frappe.db.commit()
                    raise Exception(
                        "Failed to refresh access token. Please re-authorize."
                    )

        return {"Authorization": f"Bearer {self.access_token}"}
    
    @frappe.whitelist()
    def test_connection(self):
        """
        Tests the connection to the Twitter API by fetching the authenticated user's info.
        """
        try:
            headers = self._get_bearer_headers()
            url = "https://api.twitter.com/2/users/me"
            
            # Fetch user data to verify the connection
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            user_data = response.json().get("data")
            if user_data:
                self.username = user_data.get("username")
                self.twitter_user_id = user_data.get("id")
                self.connection_status = "Connected"
                self.save(ignore_permissions=True)
                frappe.db.commit()
                
                return {
                    "status": "success",
                    "message": f"Successfully connected to Twitter as @{self.username}",
                }
            else:
                return {
                    "status": "error", 
                    "message": "Could not retrieve user data from Twitter."
                }

        except requests.exceptions.HTTPError as he:
            error_message = f"Connection test failed: {he.response.status_code} - {he.response.text}"
            frappe.log_error(title="Twitter Connection Test HTTPError", message=error_message)
            self.connection_status = "Error"
            self.save(ignore_permissions=True)
            frappe.db.commit()
            return {"status": "error", "message": error_message}
            
        except Exception as e:
            frappe.log_error(title="Twitter Connection Test Error", message=frappe.get_traceback())
            self.connection_status = "Error"
            self.save(ignore_permissions=True)
            frappe.db.commit()
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def _refresh_access_token(self):
        """Refresh access token with better error handling"""
        try:
            if not self.refresh_token:
                frappe.log_error("No refresh token available", "Twitter Token Refresh")
                return False

            url = "https://api.twitter.com/2/oauth2/token"
            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            }

            client_secret = self.get_password("client_secret")
            if not client_secret:
                frappe.log_error("Client Secret not found", "Twitter Token Refresh")
                return False

            auth_string = f"{self.client_id}:{client_secret}"
            auth_b64 = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            }

            response = requests.post(url, headers=headers, data=token_data, timeout=30)

            frappe.log_error(
                message=f"Refresh attempt - Status: {response.status_code}, Response: {response.text}",
                title="Twitter Token Refresh",
            )

            if response.status_code == 200:
                token_response = response.json()

                # Update tokens
                old_access_token = self.access_token
                self.access_token = token_response.get("access_token")

                # Twitter may or may not provide a new refresh token
                if token_response.get("refresh_token"):
                    self.refresh_token = token_response.get("refresh_token")

                # Update expiry time
                expires_in = token_response.get("expires_in", 7200)
                self.token_expires_at = now_datetime() + timedelta(seconds=expires_in)

                # Save the updated tokens
                self.save(ignore_permissions=True)
                frappe.db.commit()

                frappe.log_error(
                    message=f"Token refreshed successfully. New expires at: {self.token_expires_at}",
                    title="Twitter Token Refresh Success",
                )
                return True
            else:
                frappe.log_error(
                    message=f"Token refresh failed: {response.status_code} - {response.text}",
                    title="Twitter Token Refresh Error",
                )
                return False

        except Exception as e:
            frappe.log_error(
                f"Token refresh exception: {str(e)}", "Twitter Token Refresh Error"
            )
            return False

    def _get_oauth1_session(self):
        """Create OAuth1Session for API calls"""
        # Get OAuth 1.0a secrets from password fields
        consumer_secret = self.get_password("consumer_secret")
        access_token_secret = self.get_password("access_token_secret")

        if not all(
            [
                self.consumer_key,
                consumer_secret,
                self.access_token_key,
                access_token_secret,
            ]
        ):
            raise Exception(
                "OAuth 1.0a credentials required. Please add Consumer Key, Consumer Secret, Access Token Key, and Access Token Secret."
            )

        return OAuth1Session(
            self.consumer_key,
            client_secret=consumer_secret,
            resource_owner_key=self.access_token_key,
            resource_owner_secret=access_token_secret,
        )

    def _upload_media_simple(self, media_path, media_category="tweet_image"):
        """Upload media in a single request (for files < 5MB) - from working code"""
        try:
            oauth_session = self._get_oauth1_session()

            with open(media_path, "rb") as media_file:
                files = {"media": media_file}
                data = {"media_category": media_category}

                response = oauth_session.post(
                    "https://upload.twitter.com/1.1/media/upload.json",
                    files=files,
                    data=data,
                )

                if response.status_code == 200:
                    result = response.json()
                    return str(result["media_id"])
                else:
                    frappe.log_error(
                        message=f"Media upload failed: {response.status_code} - {response.text}",
                        title="Twitter Media Upload Error",
                    )
                    return None

        except Exception as e:
            frappe.log_error(
                f"Error uploading media: {str(e)}", "Twitter Media Upload Error"
            )
            return None

    def _upload_media_chunked(self, media_path, media_category="tweet_image"):
        """Upload media using chunked upload for large files - from working code"""
        try:
            oauth_session = self._get_oauth1_session()
            file_size = os.path.getsize(media_path)
            mime_type, _ = mimetypes.guess_type(media_path)

            # Step 1: Initialize upload
            init_data = {
                "command": "INIT",
                "total_bytes": file_size,
                "media_type": mime_type,
                "media_category": media_category,
            }

            response = oauth_session.post(
                "https://upload.twitter.com/1.1/media/upload.json", data=init_data
            )
            if response.status_code != 202:
                frappe.log_error(
                    f"Upload initialization failed: {response.status_code}",
                    "Twitter Upload Error",
                )
                return None

            media_id = response.json()["media_id"]

            # Step 2: Upload chunks
            chunk_size = 1024 * 1024  # 1MB chunks
            segment_index = 0

            with open(media_path, "rb") as media_file:
                while True:
                    chunk = media_file.read(chunk_size)
                    if not chunk:
                        break

                    append_data = {
                        "command": "APPEND",
                        "media_id": media_id,
                        "segment_index": segment_index,
                    }

                    files = {"media": chunk}

                    response = oauth_session.post(
                        "https://upload.twitter.com/1.1/media/upload.json",
                        data=append_data,
                        files=files,
                    )

                    if response.status_code != 204:
                        frappe.log_error(
                            f"Chunk upload failed: {response.status_code}",
                            "Twitter Upload Error",
                        )
                        return None

                    segment_index += 1

            # Step 3: Finalize upload
            finalize_data = {"command": "FINALIZE", "media_id": media_id}

            response = oauth_session.post(
                "https://upload.twitter.com/1.1/media/upload.json", data=finalize_data
            )
            if response.status_code != 201:
                frappe.log_error(
                    f"Upload finalization failed: {response.status_code}",
                    "Twitter Upload Error",
                )
                return None

            return str(media_id)

        except Exception as e:
            frappe.log_error(
                f"Error in chunked upload: {str(e)}", "Twitter Upload Error"
            )
            return None

    def upload_media(self, media_path, media_category="tweet_image"):
        """Upload media to Twitter and return media ID - from working code"""
        if not os.path.exists(media_path):
            raise FileNotFoundError(f"Media file not found: {media_path}")

        # Get file info
        file_size = os.path.getsize(media_path)

        # For large files (>5MB), use chunked upload
        if file_size > 5 * 1024 * 1024:  # 5MB
            return self._upload_media_chunked(media_path, media_category)
        else:
            return self._upload_media_simple(media_path, media_category)

    def post_to_twitter(self, content, image_attachment=None):
        """Post a tweet with optional image attachment - using working posting logic"""
        try:
            # Prepare tweet data
            payload = {"text": content}

            # Upload media if provided
            if image_attachment:
                try:
                    # Get file path from Frappe
                    file_doc = (
                        frappe.get_doc("File", image_attachment)
                        if frappe.db.exists("File", image_attachment)
                        else frappe.get_doc("File", {"file_url": image_attachment})
                    )
                    file_path = file_doc.get_full_path()

                    # Determine media category based on file extension
                    _, ext = os.path.splitext(file_path.lower())
                    if ext in [".mp4", ".mov", ".avi"]:
                        media_category = "tweet_video"
                    elif ext in [".gif"]:
                        media_category = "tweet_gif"
                    else:
                        media_category = "tweet_image"

                    media_id = self.upload_media(file_path, media_category)
                    if media_id:
                        payload["media"] = {"media_ids": [media_id]}
                    else:
                        return {"status": "error", "message": "Failed to upload media"}

                except Exception as e:
                    return {"status": "error", "message": f"Image upload failed: {str(e)}"}

            # Post tweet using OAuth 1.0a (from working code)
            try:
                oauth_session = self._get_oauth1_session()

                response = oauth_session.post(
                    "https://api.twitter.com/2/tweets",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 201:
                    data = response.json()
                    tweet_id = data.get("data", {}).get("id")
                    tweet_url = None
                    if tweet_id and self.username:
                        tweet_url = (
                            f"https://twitter.com/{self.username}/status/{tweet_id}"
                        )

                    return {
                        "status": "success",
                        "message": "Tweet posted successfully",
                        "post_link": tweet_url,
                        "data": data,
                    }
                else:
                    frappe.log_error(
                        message=f"Tweet posting failed: {response.status_code} - {response.text}",
                        title="Twitter Tweet Post Error",
                    )
                    return {
                        "status": "error",
                        "message": f"Tweet failed: {response.status_code} - {response.text}",
                    }

            except Exception as e:
                frappe.log_error(
                    f"Tweet posting exception: {str(e)}", "Twitter Post Error"
                )
                return {"status": "error", "message": f"Tweet posting failed: {str(e)}"}

        except Exception as e:
            return {"status": "error", "message": f"General error: {str(e)}"}


@frappe.whitelist(allow_guest=True)
def callback(code=None, state=None, error=None):
		"""Handles the OAuth 2.0 callback from Twitter after user authorization."""
		try:
			if error:
				frappe.respond_as_web_page(
					"Authorization Error", f"Twitter returned an error: {error}"
				)
				return

			if not code or not state:
				frappe.respond_as_web_page(
					"Authorization Error",
					"Invalid callback request: code or state parameter is missing.",
				)
				return

			integration_doc_name = frappe.db.get_value(
				"Twitter Integration", {"state": state}
			)
			if not integration_doc_name:
				frappe.respond_as_web_page(
					"Error", "No matching Twitter integration found for the provided state."
				)
				return

			integration = frappe.get_doc("Twitter Integration", integration_doc_name)

			token_response = integration._exchange_code_for_token(code)

			if token_response.get("status") == "success":
				test_response = integration.test_connection()
				if test_response.get("status") == "success":
					frappe.respond_as_web_page(
						"Success!",
						"Twitter authorization was successful. You can now close this window.",
						indicator_color="green",
					)
				else:
					frappe.respond_as_web_page(
						"Connection Test Failed",
						f"Could not verify the connection with Twitter. Please try again. Error: {test_response.get('message')}",
						indicator_color="red",
					)
			else:
				frappe.respond_as_web_page(
					"Token Exchange Failed",
					f"Failed to get access token from Twitter. Error: {token_response.get('message')}",
					indicator_color="red",
				)

		except Exception as e:
			frappe.log_error(
				title="Twitter OAuth2 Callback Error", message=frappe.get_traceback()
			)
			frappe.respond_as_web_page(
				"Server Error",
				"An unexpected error occurred during the authorization process.",
				indicator_color="red",
			)