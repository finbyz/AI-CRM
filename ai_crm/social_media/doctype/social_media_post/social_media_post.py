# Copyright (c) 2025, sandeep and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.file_manager import save_file
import requests
import json
from frappe.model.document import Document
from frappe.utils import get_url, cstr
from frappe import _


class SocialMediaPost(Document):
	# def validate(self):
	# 	"""Validate the social media post before saving"""
	# 	if self.platform == "LinkedIn" and not self.linkedin_account:
	# 		frappe.throw(_("LinkedIn Account is required for LinkedIn posts"))
		
	# 	if self.platform == "LinkedIn" and self.status == "Posted":
	# 		self.validate_linkedin_content()
		
	# 	# Add validation for other platforms as needed
	# 	if self.platform == "Twitter" and self.status == "Posted":
	# 		self.validate_twitter_content()
		
	# 	if self.platform == "Facebook" and self.status == "Posted":
	# 		self.validate_facebook_content()

	def validate_linkedin_content(self):
		"""Validate LinkedIn specific content requirements"""
		if not self.content:
			frappe.throw(_("Content is required for LinkedIn posts"))
		
		# LinkedIn has a character limit for posts
		if len(self.content) > 3000:
			frappe.throw(_("LinkedIn post content cannot exceed 3000 characters"))

	def validate_twitter_content(self):
		"""Validate Twitter specific content requirements"""
		if not self.content:
			frappe.throw(_("Content is required for Twitter posts"))
		
		# Twitter has a character limit for posts
		if len(self.content) > 280:
			frappe.throw(_("Twitter post content cannot exceed 280 characters"))

	def validate_facebook_content(self):
		"""Validate Facebook specific content requirements"""
		if not self.content:
			frappe.throw(_("Content is required for Facebook posts"))
		
		# Facebook has a character limit for posts
		if len(self.content) > 63206:
			frappe.throw(_("Facebook post content cannot exceed 63,206 characters"))

	@frappe.whitelist()
	def post(self):
		"""
		Generic method to post content to the selected social media platform.
		This method automatically routes to the appropriate platform-specific posting method.
		"""
		try:
			if not self.platform:
				frappe.throw(_("Social Media Platform is required"))
			
			if not self.content:
				frappe.throw(_("Content is required for posting"))

			if self.platform.lower() == "linkedin":
				return self.post_to_linkedin()
			elif self.platform.lower() == "twitter":
				return self.post_to_twitter()
			elif self.platform.lower() == "facebook":
				return self.post_to_facebook()
			elif self.platform.lower() == "instagram":
				return self.post_to_instagram()
			else:
				frappe.throw(_("Unsupported social media platform: {0}").format(self.platform))
				
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Social Media Post Error")
			self.status = "Failed"
			self.save(ignore_permissions=True)
			frappe.db.commit()
			
			return {
				"status": "error",
				"message": str(e)
			}

	@frappe.whitelist()
	def revise_post(self,instruction:str):
		content_hub_setting = frappe.get_single("Content Hub Setting")
		revise_agent = content_hub_setting.revise_agent
		ai_input_data = {
			"title": self.title,
			"social_media": self.platform,
			"prevois_post": self.content,
			"query": instruction,
		}
		result = revise_agent.invoke(**ai_input_data)
		self.content = result.content
		self.save()
		self.reload()
		return {"status": "success"}

	def _upload_linkedin_image(self, author_urn,access_token) -> str:
		"""
		Upload a Frappe File to LinkedIn and return the image URN.
		"""
		register_url = "https://api.linkedin.com/v2/images?action=initializeUpload"
		headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
		register_payload = {"initializeUploadRequest": {"owner": author_urn}}
		reg_res = requests.post(register_url, headers=headers, json=register_payload)
		reg_res.raise_for_status()
		reg_data = reg_res.json()["value"]

		upload_url = reg_data["uploadUrl"]
		image_urn = reg_data["image"]

		file_doc = frappe.get_doc("File", {"file_url":self.image_attachment})
		file_path = file_doc.get_full_path()
		mime_type = frappe.utils.file_manager.mimetypes.guess_type(file_path)[0] or "application/octet-stream"
		with open(file_path, "rb") as f:
			file_content = f.read()

		upload_headers = {"Authorization": f"Bearer {access_token}", "Content-Type": mime_type}
		up_res = requests.post(upload_url, headers=upload_headers, data=file_content)
		up_res.raise_for_status()

		return image_urn
	
	@frappe.whitelist()
	def post_to_linkedin(self):
		"""Post content to LinkedIn using the Posts API"""
		# if not self.linkedin_account:
		# 	frappe.throw(_("LinkedIn Account is required"))
		
		if not self.content:
			frappe.throw(_("Content is required for posting"))
		content_hub = frappe.get_doc("Content Hub",self.content_hub)
		linkedin_doc = frappe.get_doc(content_hub.credential_type,content_hub.credential)

		if not linkedin_doc.access_token:
			frappe.throw(_("LinkedIn access token not found. Please reconnect your LinkedIn account."))
		
		if linkedin_doc.connection_status != "Connected":
			frappe.throw(_("LinkedIn account is not connected. Please reconnect your account."))

		post_data = self._prepare_linkedin_post_data(linkedin_doc)
		
		response = self._make_linkedin_api_request(post_data, linkedin_doc.access_token)
		if response.get('status') == 'success':
			self.status = "Posted"
		else:
			self.status = "Failed"
		self.save()
		return response

	def _prepare_linkedin_post_data(self, linkedin_doc):
		"""Prepare the post data according to LinkedIn Posts API schema.
		If an image is attached, you must first register & upload it to LinkedIn,
		then pass the returned URN (image_urn) here.
		"""
		
		# Pick correct author URN
		if linkedin_doc.organization_support:
			author_urn = f"urn:li:organization:{linkedin_doc.organization_id}"
		else:
			author_urn = f"urn:li:person:{linkedin_doc.person_id}"
		
		post_data = {
			"author": author_urn,
			"commentary": self.content,
			"visibility": "PUBLIC",
			"distribution": {
				"feedDistribution": "MAIN_FEED",
				"targetEntities": [],
				"thirdPartyDistributionChannels": [],
			},
			"lifecycleState": "PUBLISHED",
			"isReshareDisabledByAuthor": False,
		}
		if self.image_attachment:
			image_urn =  self._upload_linkedin_image(author_urn,linkedin_doc.access_token)
			post_data["content"] = {
				"media": {
				"title": "Optional title",
				"id": image_urn
				}
			}		
		return post_data


	def _get_image_url(self):
		"""Get the full URL for the attached image"""
		if self.image_attachment:
			return get_url(self.image_attachment)
		return None



	def _make_linkedin_api_request(self, post_data, access_token):
		"""Make the actual API request to LinkedIn Posts API"""
		url = "https://api.linkedin.com/rest/posts"
		
		headers = {
			"Authorization": f"Bearer {access_token}",
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

	@frappe.whitelist()
	def update_linkedin_post(self, post_id=None):
		"""Update an existing LinkedIn post"""
		try:
			if not self.linkedin_account:
				frappe.throw(_("LinkedIn Account is required"))
			
			# Use post_id parameter or stored post ID
			if not post_id:
				post_id = self.social_media_post_id
			
			if not post_id:
				frappe.throw(_("Post ID is required for updating"))
			
			linkedin_doc = frappe.get_doc("LinkedIn Integration", self.linkedin_account)
			
			if not linkedin_doc.access_token:
				frappe.throw(_("LinkedIn access token not found"))
			
			# Prepare update data
			update_data = {
				"patch": {
					"$set": {
						"commentary": self.content
					}
				}
			}
			
			# Make API request
			url = f"https://api.linkedin.com/rest/posts/{post_id}"
			headers = {
				"Authorization": f"Bearer {linkedin_doc.access_token}",
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

	@frappe.whitelist()
	def delete_linkedin_post(self, post_id=None):
		"""Delete a LinkedIn post"""
		try:
			if not self.linkedin_account:
				frappe.throw(_("LinkedIn Account is required"))
			
			# Use post_id parameter or stored post ID
			if not post_id:
				post_id = self.social_media_post_id
			
			if not post_id:
				frappe.throw(_("Post ID is required for deletion"))
			
			linkedin_doc = frappe.get_doc("LinkedIn Integration", self.linkedin_account)
			
			if not linkedin_doc.access_token:
				frappe.throw(_("LinkedIn access token not found"))
			
			# Make API request
			url = f"https://api.linkedin.com/rest/posts/{post_id}"
			headers = {
				"Authorization": f"Bearer {linkedin_doc.access_token}",
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

	@frappe.whitelist()
	def post_to_twitter(self):
		"""Post content to Twitter"""
		try:
			# TODO: Implement Twitter API integration
			# This is a placeholder for future Twitter implementation
			frappe.throw(_("Twitter posting is not yet implemented. Please use LinkedIn for now."))
			
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Twitter Post Error")
			self.status = "Failed"
			self.save(ignore_permissions=True)
			frappe.db.commit()
			
			return {
				"status": "error",
				"message": str(e)
			}

	@frappe.whitelist()
	def post_to_facebook(self):
		"""Post content to Facebook"""
		try:
			# TODO: Implement Facebook API integration
			# This is a placeholder for future Facebook implementation
			frappe.throw(_("Facebook posting is not yet implemented. Please use LinkedIn for now."))
			
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Facebook Post Error")
			self.status = "Failed"
			self.save(ignore_permissions=True)
			frappe.db.commit()
			
			return {
				"status": "error",
				"message": str(e)
			}

	@frappe.whitelist()
	def post_to_instagram(self):
		"""Post content to Instagram"""
		try:
			# TODO: Implement Instagram API integration
			# This is a placeholder for future Instagram implementation
			frappe.throw(_("Instagram posting is not yet implemented. Please use LinkedIn for now."))
			
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Instagram Post Error")
			self.status = "Failed"
			self.save(ignore_permissions=True)
			frappe.db.commit()
			
			return {
				"status": "error",
				"message": str(e)
			}

	@frappe.whitelist()
	def generate_image(self,instruction=''):
		setting = frappe.get_single("Content Hub Setting")
		if not self.image_generation_prompt:
			meta_prompt = setting.image_generation_meta_prompt
			helper_agent = frappe.get_doc("AI Agent", setting.helper_agent)
			generation_prompt = f"{meta_prompt}\n\nPost Content:\n{self.content}\n{instruction}"
			image_generation_prompt = helper_agent.invoke(query=generation_prompt)
		else:
			image_generation_prompt = self.image_generation_prompt

		frappe.log_error("prompt",image_generation_prompt)

		agent = setting.image_agent
		try:
			image_response = agent.invoke(query=image_generation_prompt[:900],size=setting.image_size)
		except Exception as e:
			frappe.log_error("Image genration failed",frappe.get_traceback())
			return {
				"status":"error",
				"error": e
			}
		url = image_response.data[0].url
		response = requests.get(url, stream=True)
		response.raise_for_status()

		image_bytes = response.content
		file_name = f"{frappe.scrub(self.title)}_{self.platform.lower()}.png"
		file_doc = frappe.new_doc("File")
		file_doc.content = image_bytes
		file_doc.file_name = file_name
		file_doc.is_private = True
		file_doc.save()
		self.image_attachment = file_doc.file_url
		self.image_generation_prompt = image_generation_prompt
		self.save()
		self.reload()
		return {
			"status":"success"
		}
