# Copyright (c) 2025, finbyz and contributors
# For license information, please see license.txt

import base64

import frappe
from finbyzai.ai.agent.agent_service import AgentService
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from ai_crm.social_media.platforms import PLATFORM_BY_CREDENTIAL, get_platform


class SocialMediaPost(Document):
    APPROVAL_FIELDS = {
        "title", "content", "image_attachment", "creative_pdf",
        "credential_type", "credential", "subreddit", "post_on",
    }
    SOURCE_FIELDS = {
        "content_hub", "reference_content_idea", "source_idea_row",
    }
    WORKFLOW_FIELDS = {
        "status", "generation_status", "submitted_by", "submitted_on",
        "approved_by", "approved_on", "rejection_reason", "failure_reason",
    }

    @property
    def platform(self):
        return get_platform(self.credential_type)

    def validate(self):
        if self.is_new():
            self._prepare_manual_post()
        previous = self.get_doc_before_save()
        if not previous:
            return

        # Schedule/unschedule legitimately move post_on without touching the content.
        protected = self.APPROVAL_FIELDS - {"post_on"} if self.flags.scheduling else self.APPROVAL_FIELDS
        protected_content_changed = any(
            previous.get(field) != self.get(field) for field in protected
        )
        source_context_changed = any(
            previous.get(field) != self.get(field) for field in self.SOURCE_FIELDS
        )
        if source_context_changed:
            frappe.throw(_("The original source context cannot be changed"))
        if protected_content_changed and previous.status in {"Pending Approval", "Publishing", "Posted"}:
            frappe.throw(_("Return the post to Draft before changing approved content"))
        if protected_content_changed and previous.status in {"Approved", "Scheduled"}:
            if not self._is_manager():
                frappe.throw(_("Only a Social Media Manager can change an approved post"))
            self._return_to_draft()
            self.flags.skip_approval_reset = True
        if protected_content_changed and previous.status == "Failed" and previous.generation_status == "Ready":
            if not self._is_manager():
                frappe.throw(_("Only a Social Media Manager can change a failed publish"))
            self._return_to_draft()
            self.failure_reason = None
            self.flags.skip_approval_reset = True

        workflow_changed = any(
            previous.get(field) != self.get(field) for field in self.WORKFLOW_FIELDS
        )
        if workflow_changed and not self.flags.skip_approval_reset:
            frappe.throw(_("Use a Content Studio workflow action to change workflow fields"))

    def _prepare_manual_post(self):
        """Posts written by hand (no Content Hub) skip AI generation."""
        if self.content_hub:
            return
        if not self.credential_type or not self.credential:
            frappe.throw(_("Select the Credential Type and Credential to post from"))
        if self.credential_type not in PLATFORM_BY_CREDENTIAL:
            frappe.throw(_("Credential Type must be one of {0}").format(", ".join(PLATFORM_BY_CREDENTIAL)))
        if not (self.title or "").strip():
            frappe.throw(_("Title is required"))
        if not (self.content or "").strip():
            frappe.throw(_("Content is required"))
        self.status = "Draft"
        self.generation_status = "Ready"

    def get_group_names(self):
        """Drafts generated from the same Content Hub idea, used to share a creative."""
        if not (self.content_hub and self.source_idea_row):
            return [self.name]
        return frappe.get_all(
            self.doctype,
            filters={"content_hub": self.content_hub, "source_idea_row": self.source_idea_row},
            order_by="creation asc",
            pluck="name",
        )

    @frappe.whitelist(methods=["POST"])
    def copy_to_account(self, credential_type: str, credential: str):
        """Create a new Draft of this post for another account. It is not submitted."""
        self.check_permission("read")
        frappe.has_permission(self.doctype, "create", throw=True)
        if credential_type not in PLATFORM_BY_CREDENTIAL:
            frappe.throw(_("Credential Type must be one of {0}").format(", ".join(PLATFORM_BY_CREDENTIAL)))
        if not frappe.db.exists(credential_type, credential):
            frappe.throw(_("{0} {1} does not exist").format(credential_type, credential))
        if (credential_type, credential) == (self.credential_type, self.credential):
            frappe.throw(_("This post already uses that account"))

        from ai_crm.social_media.creative.generation import copy_creative

        copy = frappe.get_doc({
            "doctype": self.doctype,
            "title": self.title,
            "content": self.content,
            "image_attachment": self.image_attachment,
            "image_generation_prompt": self.image_generation_prompt,
            "credential_type": credential_type,
            "credential": credential,
            "subreddit": self.subreddit if credential_type == self.credential_type else None,
            "content_hub": self.content_hub,
            "reference_content_idea": self.reference_content_idea,
            "source_idea_row": self.source_idea_row,
            "status": "Draft",
            "generation_status": "Ready",
        })
        copy.insert()
        if self.creative_status == "Ready":
            copy_creative(self, copy)
        return copy.name

    def get_credentials(self):
        """Return the connected account selected when this draft was created."""
        if not self.credential_type or not self.credential:
            frappe.throw("Select a social media account before publishing")
        return frappe.get_doc(self.credential_type, self.credential)

    @frappe.whitelist(methods=["POST"])
    def update_draft(self, title: str, content: str):
        self.check_permission("write")
        if self.status not in {"Draft", "Approved", "Scheduled"}:
            frappe.throw(_("Only draft or approved posts can be edited"))
        if self.status != "Draft":
            self._require_manager()
        self.title = title
        self.content = content
        self.flags.skip_approval_reset = True
        self._return_to_draft()
        self.save()
        return self.as_studio_dict()

    @frappe.whitelist(methods=["POST"])
    def submit_for_approval(self):
        # Anyone who can see the post may send it for approval.
        self.check_permission("read")
        if self.generation_status != "Ready":
            frappe.throw("Wait for content generation to finish")
        if self.status != "Draft":
            frappe.throw("Only draft posts can be submitted")
        if not self.content or not self.credential or not self.platform:
            frappe.throw("Content, platform, and account are required")
        if self.platform == "Reddit" and not self.subreddit:
            frappe.throw("Subreddit is required for Reddit posts")
        self.status = "Pending Approval"
        self.submitted_by = frappe.session.user
        self.submitted_on = now_datetime()
        self.rejection_reason = None
        self.flags.skip_approval_reset = True
        self.save(ignore_permissions=True)
        return self.as_studio_dict()

    @frappe.whitelist(methods=["POST"])
    def approve(self):
        """Approve, then publish now (no Post On, or it has passed) or schedule for Post On."""
        self._require_approver()
        if self.status != "Pending Approval":
            frappe.throw("Only pending posts can be approved")
        self.approved_by = frappe.session.user
        self.approved_on = now_datetime()
        self.rejection_reason = None
        self.flags.skip_approval_reset = True
        publish_now = not self.post_on or get_datetime(self.post_on) <= now_datetime()
        if publish_now:
            self.status = "Approved"
            self.post_on = None
        else:
            self.status = "Scheduled"
        self.flags.scheduling = True
        self.save(ignore_permissions=True)
        account = f"{self.platform} ({self.credential})"
        if publish_now:
            frappe.msgprint(_("Approved. Posting to {0} now.").format(account), title=_("Approved"), indicator="green")
        else:
            frappe.msgprint(
                _("Approved. Will be posted to {0} on {1}.").format(account, frappe.utils.format_datetime(self.post_on)),
                title=_("Scheduled"),
                indicator="blue",
            )
        if publish_now:
            frappe.enqueue(
                publish_approved_post,
                queue="long",
                timeout=900,
                enqueue_after_commit=True,
                job_id=f"publish:{self.name}",
                deduplicate=True,
                post_name=self.name,
            )
        return self.as_studio_dict()

    @frappe.whitelist(methods=["POST"])
    def reject(self, reason: str):
        self._require_approver()
        reason = (reason or "").strip()
        if self.status != "Pending Approval":
            frappe.throw("Only pending posts can be rejected")
        if not reason:
            frappe.throw("Enter a rejection reason")
        self._return_to_draft()
        self.rejection_reason = reason
        self.flags.skip_approval_reset = True
        self.save()
        return self.as_studio_dict()

    @frappe.whitelist(methods=["POST"])
    def schedule(self, post_on: str):
        self._require_manager()
        if self.status != "Approved":
            frappe.throw("Approve the post before scheduling it")
        scheduled_for = get_datetime(post_on)
        if scheduled_for <= now_datetime():
            frappe.throw("Schedule time must be in the future")
        self.status = "Scheduled"
        self.post_on = scheduled_for
        self.flags.skip_approval_reset = True
        self.flags.scheduling = True
        self.save()
        return self.as_studio_dict()

    @frappe.whitelist(methods=["POST"])
    def unschedule(self):
        self._require_manager()
        if self.status != "Scheduled":
            frappe.throw("Only scheduled posts can be unscheduled")
        self.status = "Approved"
        self.post_on = None
        self.flags.skip_approval_reset = True
        self.flags.scheduling = True
        self.save()
        return self.as_studio_dict()

    @frappe.whitelist(methods=["POST"])
    def retry_generation(self):
        self.check_permission("write")
        if self.status != "Failed" or self.generation_status != "Failed":
            frappe.throw(_("Only failed generation jobs can be retried"))
        if not self.content_hub or not self.source_idea_row:
            frappe.throw(_("The original source idea is unavailable"))

        from ai_crm.social_media.doctype.content_hub.generation import generate_post_content

        self.status = "Draft"
        self.generation_status = "Queued"
        self.failure_reason = None
        self.flags.skip_approval_reset = True
        self.save()
        frappe.enqueue(
            generate_post_content,
            queue="long",
            timeout=900,
            enqueue_after_commit=True,
            job_id=f"content-studio:{self.name}",
            deduplicate=True,
            post_name=self.name,
            content_hub_name=self.content_hub,
            idea_name=self.source_idea_row,
        )
        return self.as_studio_dict()

    @frappe.whitelist(methods=["POST"])
    def generate_creative(self, template: str, brief: str = "", llm: str | None = None, share_with_siblings: int = 1):
        self._require_editable_draft()
        from ai_crm.social_media.creative.generation import queue_creative

        return queue_creative(self, template, brief, llm, frappe.utils.cint(share_with_siblings))

    @frappe.whitelist(methods=["POST"])
    def rerender_creative(self):
        self._require_editable_draft()
        if self.creative_status in {"Queued", "Generating"}:
            frappe.throw(_("The creative is still being generated"))
        from ai_crm.social_media.creative.generation import rerender_creative

        rerender_creative(self)
        return {"status": "success"}

    def _require_editable_draft(self):
        self.check_permission("write")
        if self.status != "Draft":
            frappe.throw(_("Return the post to Draft before changing its creative"))

    @frappe.whitelist(methods=["POST"])
    def retry_publish(self):
        self._require_manager()
        if self.status != "Failed" or self.generation_status != "Ready":
            frappe.throw("Only failed publish attempts can be retried")
        self.status = "Approved"
        self.failure_reason = None
        self.flags.skip_approval_reset = True
        self.save()
        return self.post()

    def _return_to_draft(self):
        self.status = "Draft"
        self.post_on = None
        self.approved_by = None
        self.approved_on = None

    def _require_manager(self):
        if not self._is_manager():
            frappe.throw("Social Media Manager role is required", frappe.PermissionError)
        self.check_permission("write")

    def _is_manager(self):
        return self._is_approver() or bool(
            {"System Manager", "Social Media Manager"}.intersection(frappe.get_roles())
        )

    def _is_approver(self):
        if frappe.session.user == "Administrator":
            return True
        roles = frappe.get_all(
            "Has Role",
            filters={"parent": "Content Hub Setting", "parenttype": "Content Hub Setting", "parentfield": "approver_roles"},
            pluck="role",
        ) or ["System Manager"]
        return bool(set(roles).intersection(frappe.get_roles()))

    def _require_approver(self):
        if not self._is_approver():
            frappe.throw(_("You are not allowed to approve or reject social media posts"), frappe.PermissionError)

    def onload(self):
        self.set_onload("can_approve", self._is_approver())

    def as_studio_dict(self):
        fields = (
            "name", "title", "content", "credential_type", "credential",
            "status", "generation_status", "post_on", "posted_on", "post_link",
            "remote_post_id", "subreddit", "image_attachment", "content_hub",
            "reference_content_idea", "owner", "submitted_by", "submitted_on",
            "approved_by", "approved_on", "rejection_reason", "failure_reason", "modified",
        )
        data = {field: self.get(field) for field in fields}
        data["platform"] = self.platform
        return data

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

    def validate_reddit_content(self):
        """Validate Reddit specific content requirements"""
        if not self.content and not self.image_attachment:
           frappe.throw(_("Content or image is required for Reddit posts"))
    
        if self.title and len(self.title) > 300:
           frappe.throw(_("Reddit post title cannot exceed 300 characters"))

    @frappe.whitelist(methods=["POST"])
    def post(self):
        self._require_manager()
        self._claim_for_publishing()

        try:
            if not self.platform:
                frappe.throw(_("Social Media Platform is required"))
            platform = self.platform.lower()
            if not self.content and not (platform == "reddit" and self.image_attachment):
                frappe.throw(_("Content is required for posting"))

            if platform == "linkedin":
                result = self.post_to_linkedin()
            elif platform in {"twitter", "x", "x (twitter)"}:
                result = self.post_to_twitter()
            elif platform == "reddit":
                result = self.post_to_reddit()
            else:
                frappe.throw(_("Unsupported social media platform: {0}").format(self.platform))

            if not result or result.get("status") != "success":
                self.reload()
                self.status = "Failed"
                self.failure_reason = (
                    (result or {}).get("message")
                    or (result or {}).get("error")
                    or _("Publishing failed")
                )
                self.flags.skip_approval_reset = True
                self.save(ignore_permissions=True)
            return result
        except Exception as error:
            frappe.log_error(frappe.get_traceback(), "Social Media Post Error")
            self.reload()
            self.status = "Failed"
            self.failure_reason = str(error)
            self.flags.skip_approval_reset = True
            self.save(ignore_permissions=True)
            return {"status": "error", "message": str(error)}

    def _claim_for_publishing(self):
        rows = frappe.db.sql(
            """
            select status, post_on
            from `tabSocial Media Post`
            where name = %s
            for update
            """,
            self.name,
            as_dict=True,
        )
        if not rows or rows[0].status not in {"Approved", "Scheduled"}:
            frappe.throw(_("This post is not available for publishing"))
        if rows[0].status == "Scheduled" and get_datetime(rows[0].post_on) > now_datetime():
            frappe.throw(_("This post is scheduled for a future time"))

        self.reload()
        self.status = "Publishing"
        self.failure_reason = None
        self.flags.skip_approval_reset = True
        self.save()
        # Commit the claim before the external API call so another worker cannot publish it.
        frappe.db.commit()

    @frappe.whitelist(methods=["POST"])
    def revise_post(self, instruction: str):
        self.check_permission("write")
        if self.status not in {"Draft", "Approved", "Scheduled"}:
            frappe.throw(_("Only draft or approved posts can be revised"))
        if self.status != "Draft":
            self._require_manager()
        content_hub_setting = frappe.get_single("Content Hub Setting")

        credential_doc = self.get_credentials()

        # Step 2: Decide which AI agent to use
        agent_name = None
        if credential_doc and not getattr(credential_doc, "use_default_ai_agents", False):
            agent_name = getattr(credential_doc, "post_generator_agent", None)

        if not agent_name:
            agent_name = content_hub_setting.revise_post_agent or content_hub_setting.post_generator_agent

        if not agent_name:
            frappe.throw("No revision agent configured in Content Hub Setting")

        revise_agent = frappe.get_doc("AI Agent", agent_name).agent_service

        # Step 3: Prepare unified AI input
        ai_input_data = {
            "action": "revise",
            "title": self.title,
            "social_media": self.platform,
            "previous_post": self.content,
            "instruction": instruction,
            "target_audience": "None",
            "idea_title": "None",
            "idea_description": "None",
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


    def post_to_linkedin(self):
        """Bridge method to post content to LinkedIn using LinkedInIntegration"""
        try:
            self.validate_linkedin_content()

            linkedin_doc = self.get_credentials()

            if not linkedin_doc.access_token:
                frappe.throw(_("LinkedIn OAuth 2.0 access token not found. Please reconnect your LinkedIn account."))

            if linkedin_doc.connection_status != "Connected":
                frappe.throw(_("LinkedIn account is not connected. Please reconnect your account."))

            document = self.get_linkedin_document()
            result = linkedin_doc.post_to_linkedin(
                self.content,
                None if document else self.image_attachment,
                document=document,
                document_title=self.title,
            )
            
            if result.get("status") == "success":
                self.status = "Posted"
                self.posted_on = frappe.utils.now_datetime()
                self.remote_post_id = result.get("post_id")
                self.post_link = result.get("post_link")
                self.save()
                return result
            else:
                self.status = "Failed"
                self.save()
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
            return {
                "status": "error",
                "message": str(e)
            }

    def get_linkedin_document(self):
        """PDF to post as a LinkedIn document (carousel), or None to post the image."""
        if not self.creative_pdf or self.creative_status != "Ready":
            return None
        fmt = frappe.db.get_value("Creative Template", self.creative_template, "format")
        return self.creative_pdf if fmt in {"Carousel", "One Pager"} else None

    def post_to_twitter(self):
        """Post content to Twitter using OAuth 2.0"""
        try: 
            self.validate_twitter_content()

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
                self.posted_on = frappe.utils.now_datetime()
                self.remote_post_id = result.get("tweet_id")
                self.post_link = result.get("tweet_url")
                self.save()
                return result
            else:
                self.status = "Failed"
                self.save()
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
            return {
                "status": "error",
                "message": str(e)
            }

            
    def post_to_reddit(self):
        """Post content to Reddit."""
        try:
            self.validate_reddit_content()
            reddit_doc = self.get_credentials()

            if not reddit_doc.access_token:
                frappe.throw(_("Reddit access token not found. Please reconnect your Reddit account."))

            if reddit_doc.connection_status != "Connected":
                frappe.throw(_("Reddit account is not connected. Please reconnect your account."))
        
            subreddit = self.subreddit
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
                self.posted_on = frappe.utils.now_datetime()
                self.remote_post_id = result.get("id", "")
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

    @frappe.whitelist(methods=["POST"])
    def generate_image(self, instruction: str = ''):
        self.check_permission("write")
        if self.status not in {"Draft", "Approved", "Scheduled"}:
            frappe.throw(_("Only draft or approved posts can be changed"))
        if self.status != "Draft":
            self._require_manager()
        setting = frappe.get_single("Content Hub Setting")

        credential_doc = self.get_credentials()

        # Determine which image agent to use
        agent_name = None
        meta_prompt = setting.image_generation_meta_prompt or ""

        if credential_doc and not getattr(credential_doc, "use_default_ai_agents", False):
            agent_name = getattr(credential_doc, "image_generation_agent", None)
            account_prompt = getattr(credential_doc, "image_generation_meta_prompt", None)
            if account_prompt:
                meta_prompt = account_prompt

        if not agent_name:
            agent_name = setting.image_generation_agent

        if not agent_name:
            frappe.throw("No Image Generation Agent configured in Content Hub Setting")

        image_agent = frappe.get_doc("AI Agent", agent_name).agent_service

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


def publish_approved_post(post_name):
    """Background publish right after approval; post() records success or failure on the post."""
    doc = frappe.get_doc("Social Media Post", post_name)
    if doc.status == "Approved":
        doc.post()
