# Copyright (c) 2025, finbyz and contributors
# For license information, please see license.txt

import base64
from ai_crm.ai.agent.agent_service import AgentService
import frappe
import requests
from frappe.model.document import Document
from frappe.utils import get_url
from frappe import _
from urllib.parse import urlencode 
from frappe.utils import now_datetime 


class SocialMediaPost(Document):

    def get_credentials(self):
        """Fetch credential document from either Content Hub or direct fields"""
        if self.content_hub:
            content_hub_doc = frappe.get_doc("Content Hub", self.content_hub)
            if not content_hub_doc.credential:
                frappe.throw("No credential selected in Content Hub")
            return frappe.get_doc(content_hub_doc.credential_type, content_hub_doc.credential)
        else:
            if not self.credential_type or not self.credential:
                frappe.throw("Either Content Hub or direct Credential fields are required")
            return frappe.get_doc(self.credential_type, self.credential)

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
            
    def validate_reddit_content(self):
        """Validate Reddit specific content requirements"""
        if not self.content and not self.image_attachment:
           frappe.throw(_("Content or image is required for Reddit posts"))
    
        if self.title and len(self.title) > 300:
           frappe.throw(_("Reddit post title cannot exceed 300 characters"))

    @frappe.whitelist()
    def post(self):
        try:
            if not self.platform:
                frappe.throw(_("Social Media Platform is required"))

            if not self.content:
                frappe.throw(_("Content is required for posting"))

            platform_lower = self.platform.lower()
            result = None

            if platform_lower == "linkedin":
                result = self.post_to_linkedin()
            elif platform_lower in ["twitter", "x", "x (twitter)"]:
                result = self.post_to_twitter()
            # Removed post_to_facebook from here as it's not implemented
            elif platform_lower == "instagram":
                result = self.post_to_instagram()
                
            elif platform_lower == "reddit":  
                result = self.post_to_reddit() 
            else:
                frappe.throw(_("Unsupported social media platform: {0}").format(self.platform))
            
            return result

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
    def revise_post(self, instruction: str):
        content_hub_setting = frappe.get_single("Content Hub Setting")

        # Step 1: Get credential from Content Hub or fallback to this record
        if self.content_hub:
            hub_doc = frappe.get_doc("Content Hub", self.content_hub)
            if hub_doc.credential:
                credential_doc = frappe.get_doc(hub_doc.credential_type, hub_doc.credential)
            else:
                frappe.throw("No credential selected in linked Content Hub")
        else:
            if not self.credential:
                frappe.throw("No credential selected in this document or linked Content Hub")
            credential_doc = frappe.get_doc(self.credential_type, self.credential)

        # Step 2: Decide which AI agent to use
        if credential_doc.use_default_ai_agents == 1:
            revise_agent = content_hub_setting.revise_agent
        else:
            if getattr(credential_doc, "revise_generator_agent", None):
                ai_agent_doc = frappe.get_doc("AI Agent", credential_doc.revise_generator_agent)
                revise_agent = ai_agent_doc.agent_service
            else:
                revise_agent = content_hub_setting.revise_agent

        # Step 3: Prepare input for AI
        ai_input_data = {
            "title": self.title,
            "social_media": self.platform,
            "prevois_post": self.content,
            "query": instruction,
            "content_hub_name": self.content_hub or self.name,
        }

        # Step 4: Call AI agent
        result = revise_agent.invoke(**ai_input_data)
        revised_content = getattr(result, "content", None)

        if not revised_content:
            frappe.throw("AI agent did not return revised content")

        # Step 5: Save result back
        self.content = revised_content
        self.save()
        self.reload()

        return {"status": "success", "revised_content": revised_content}


    @frappe.whitelist()
    def post_to_linkedin(self):
        """Bridge method to post content to LinkedIn using LinkedInIntegration"""
        try:
            if not self.content:
                frappe.throw(_("Content is required for posting"))

            linkedin_doc = self.get_credentials()

            if not linkedin_doc.access_token:
                frappe.throw(_("LinkedIn OAuth 2.0 access token not found. Please reconnect your LinkedIn account."))

            if linkedin_doc.connection_status != "Connected":
                frappe.throw(_("LinkedIn account is not connected. Please reconnect your account."))

            result = linkedin_doc.post_to_linkedin(self.content, self.image_attachment)
            
            if result.get("status") == "success":
                self.status = "Posted"
                self.social_media_post_id = result.get("post_id")
                self.social_media_post_link = result.get("post_link")
                self.post_link = result.get("post_link")
                self.save()
                frappe.db.commit()
                return result
            else:
                self.status = "Failed"
                self.save()
                frappe.db.commit()
                error_msg = result.get("error", "Unknown error occurred")
                frappe.log_error(f"LinkedIn Post Failed: {error_msg}", "LinkedIn Post Error")
                return {
                    "status": "error",
                    "message": error_msg
                }

        except Exception as e:
            frappe.log_error(f"LinkedIn Post Exception: {str(e)}", "LinkedIn Post Exception")
            self.status = "Failed"
            self.save()
            frappe.db.commit()
            return {
                "status": "error",
                "message": str(e)
            }

    @frappe.whitelist()
    def update_linkedin_post(self, post_id=None):
        """Bridge method to update an existing LinkedIn post"""
        try:
            if not self.social_media_post_id:
                frappe.throw(_("No LinkedIn post ID found to update"))

            linkedin_doc = self.get_credentials()

            result = linkedin_doc.update_linkedin_post(self.social_media_post_id, self.content)

            if result.get("status") == "success":
                self.status = "Updated"
                self.save()
                frappe.db.commit()
                return result
            else:
                self.status = "Failed"
                self.save()
                frappe.db.commit()
                error_msg = result.get("message", "Unknown error occurred")
                frappe.log_error(f"LinkedIn Update Failed: {error_msg}", "LinkedIn Update Error")
                return {"status": "error", "message": error_msg}

        except Exception as e:
            frappe.log_error(f"LinkedIn Update Exception: {str(e)}", "LinkedIn Update Exception")
            self.status = "Failed"
            self.save()
            frappe.db.commit()
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def delete_linkedin_post(self, post_id=None):
        """Bridge method to delete a LinkedIn post"""
        try:
            if not self.social_media_post_id:
                frappe.throw(_("No LinkedIn post ID found to delete"))

            linkedin_doc = self.get_credentials()

            result = linkedin_doc.delete_linkedin_post(self.social_media_post_id)

            if result.get("status") == "success":
                self.status = "Deleted"
                self.social_media_post_id = None
                self.social_media_post_link = None
                self.save()
                frappe.db.commit()
                return result
            else:
                self.status = "Failed"
                self.save()
                frappe.db.commit()
                error_msg = result.get("message", "Unknown error occurred")
                frappe.log_error(f"LinkedIn Delete Failed: {error_msg}", "LinkedIn Delete Error")
                return {"status": "error", "message": error_msg}

        except Exception as e:
            frappe.log_error(f"LinkedIn Delete Exception: {str(e)}", "LinkedIn Delete Exception")
            self.status = "Failed"
            self.save()
            frappe.db.commit()
            return {"status": "error", "message": str(e)}

    @frappe.whitelist()
    def post_to_twitter(self):
        """Post content to Twitter using OAuth 2.0"""
        try: 
            if not self.content:
                frappe.throw(_("Content is required for posting"))

            twitter_doc = self.get_credentials()
            
            # OAuth 2.0 validation
            if not twitter_doc.access_token:
                frappe.throw(_("Twitter OAuth 2.0 access token not found. Please reconnect your Twitter account."))

            if twitter_doc.connection_status != "Connected":
                frappe.throw(_("Twitter account is not connected. Please reconnect your account."))

            # Call Twitter integration's post method
            result = twitter_doc.post_to_twitter(self.content, self.image_attachment)
            
            if result.get("status") == "success":
                self.status = "Posted"
                self.social_media_post_id = result.get("tweet_id")
                self.social_media_post_link = result.get("tweet_url")
                self.post_link = result.get("tweet_url")
                self.save()
                frappe.db.commit()
                return result
            else:
                self.status = "Failed"
                self.save()
                frappe.db.commit()
                error_msg = result.get("message", "Unknown error occurred")
                frappe.log_error(f"Twitter Post Failed: {error_msg}", "Twitter Post Error")
                return {
                    "status": "error",
                    "message": error_msg
                }

        except Exception as e:
            frappe.log_error(f"Twitter Post Exception: {str(e)}", "Twitter Post Exception")
            self.status = "Failed"
            self.save()
            frappe.db.commit()
            return {
                "status": "error",
                "message": str(e)
            }

            
    @frappe.whitelist()
    def post_to_reddit(self):
        """Post content to Reddit"""
        try:
            reddit_doc = self.get_credentials()

            if not reddit_doc.access_token:
                frappe.throw(_("Reddit access token not found. Please reconnect your Reddit account."))

            if reddit_doc.connection_status != "Connected":
                frappe.throw(_("Reddit account is not connected. Please reconnect your account."))
        
            subreddit = getattr(self, 'subreddit', None) or "test"
            post_title = self.title or (self.content[:100] + "..." if len(self.content) > 100 else self.content)

            # Handle image vs text posts properly
            if self.image_attachment:
                try:
                    file_doc = frappe.get_doc("File", {"file_url": self.image_attachment})
                    image_path = file_doc.get_full_path()
                
                    # Call create_image_post_simple method 
                    result = reddit_doc.create_image_post_simple(
                        subreddit=subreddit,
                        title=post_title,
                        image_path=image_path
                    )
                except Exception as img_error:
                    frappe.log_error(f"Image processing error: {str(img_error)}", "Reddit Image Error")
                    return {
                        "status": "error",
                        "message": f"Failed to process image: {str(img_error)}"
                    }
            else:
                # Call create_post method for text posts
                result = reddit_doc.create_post(
                    subreddit=subreddit,
                    title=post_title,
                    content=self.content,
                    is_self=True
                )
        
            # Validate result structure
            if not isinstance(result, dict):
                frappe.log_error(f"Invalid result type from Reddit API: {type(result)}", "Reddit API Error")
                return {
                    "status": "error",
                    "message": "Invalid response from Reddit API"
                }
        
            if result.get("status") == "success":
                self.status = "Posted"
                self.social_media_post_id = result.get("id", "")
                self.social_media_post_link = result.get("url", "")
                self.post_link = result.get("url", "")
                self.save()
                return result
            else:
                self.status = "Failed"
                self.save()
                return result
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Reddit Post Error")
            self.status = "Failed"
            self.save()
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
    def generate_image(self, instruction=''):
        setting = frappe.get_single("Content Hub Setting")

        credential_doc = self.get_credentials()

        if instruction:
            self.user_instructions = instruction
            self.save(ignore_permissions=True)

        # Determine which image agent to use
        if credential_doc.use_default_ai_agents == 1:
            image_agent = setting.image_agent
            meta_prompt = setting.image_generation_meta_prompt
        else:
            image_agent_name = getattr(credential_doc, "image_generation_agent", None)
            meta_prompt_cred = getattr(credential_doc, "image_generation_meta_prompt", None)
            if image_agent_name:
                ai_agent_doc = frappe.get_doc("AI Agent", image_agent_name)
                image_agent = ai_agent_doc.agent_service
            else:
                image_agent = setting.image_agent  # fallback

            # Meta prompt fallback
            meta_prompt = meta_prompt_cred or setting.image_generation_meta_prompt

        if not self.image_generation_prompt:
            helper_agent = AgentService(setting.helper_agent)
            generation_prompt = f"{meta_prompt}\n\nPost Content:\n{self.content}\n{instruction}"
            image_generation_response = helper_agent.invoke(query=generation_prompt)

            # ✅ Extract the actual usable string
            if isinstance(image_generation_response, dict) and "output" in image_generation_response:
                image_generation_prompt = image_generation_response["output"]
            elif hasattr(image_generation_response, 'content'):
                image_generation_prompt = str(image_generation_response.content)
            elif hasattr(image_generation_response, 'text'):
                image_generation_prompt = str(image_generation_response.text)
            else:
                image_generation_prompt = str(image_generation_response)
        else:
            image_generation_prompt = str(self.image_generation_prompt)

        try:
            prompt_text = str(image_generation_prompt)[:900]
            image_response = image_agent.invoke(query=prompt_text, size=setting.image_size)
        except Exception as e:
            frappe.log_error("Image generation failed", frappe.get_traceback())
            return {
                "status": "error",
                "error": str(e)
            }

        # Handle the image response safely
        try:
            b64_image = image_response.images[0]
            image_bytes = base64.b64decode(b64_image)

            file_name = f"{frappe.scrub(self.title or 'social_post')}_{self.platform.lower()}.png"
            file_doc = frappe.new_doc("File")
            file_doc.content = image_bytes
            file_doc.file_name = file_name
            file_doc.is_private = True
            file_doc.save()

            self.image_attachment = file_doc.file_url
            self.image_generation_prompt = prompt_text
            self.save()
            self.reload()

            return {"status": "success"}

        except Exception as e:
            frappe.log_error("Image download/save failed", frappe.get_traceback())
            return {
                "status": "error",
                "error": str(e)
            }

@frappe.whitelist()
def schedule_social_media_posts():
    """
    This function is intended to be run by the Frappe scheduler.
    It fetches all 'Scheduled' social media posts where the 'post_on' datetime
    is in the past and attempts to publish them.
    """
    current_time = now_datetime()

    posts_to_publish = frappe.get_all(
        "Social Media Post",
        filters={
            "status": "Scheduled",
            "post_on": ["<=", current_time]
        },
        fields=["name"]
    )

    # --- Start of new debugging code ---
    if not posts_to_publish:
        # If no posts are found, return a clear message.
        return "No posts found with 'Scheduled' status and a past 'post_on' time."
    # --- End of new debugging code ---

    processed_posts = [] # Keep track of what we process
    for post_meta in posts_to_publish:
        try:
            post_doc = frappe.get_doc("Social Media Post", post_meta.name)
            post_doc.post()
            processed_posts.append(post_meta.name) # Add to our list
        except Exception:
            frappe.log_error(
                f"Failed to publish scheduled post: {post_meta.name}\n{frappe.get_traceback()}",
                "Scheduled Social Media Post Error"
            )

    # Return the list of posts that the loop attempted to process.
    return f"Attempted to process the following posts: {processed_posts}"