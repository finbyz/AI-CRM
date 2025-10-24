app_name = "ai_crm"
app_title = "Ai CRM"
app_publisher = "Finbyz Tech Pvt Ltd"
app_description = "this is ai powered crm system"
app_email = "info@finbyz.tech"
app_license = "MIT"

# Installation / Uninstallation
before_uninstall = "ai_crm.install.before_uninstall"

# Uninstallation
# ------------

# before_uninstall = "ai_crm.uninstall.before_uninstall"
# after_uninstall = "ai_crm.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "ai_crm.utils.before_app_install"
# after_app_install = "ai_crm.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "ai_crm.utils.before_app_uninstall"
# after_app_uninstall = "ai_crm.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ai_crm.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------
doc_events = {
    "Lead": {
        "after_insert": "ai_crm.ai_crm.doctype.communication_log.communication_log.generate_followups_on_party_activity"
    },
    "Customer": {
        "after_insert": "ai_crm.ai_crm.doctype.communication_log.communication_log.generate_followups_on_party_activity"
    }
}

scheduler_events = {
	# "all": [
	# ],
      
	"daily": [
		"ai_crm.tasks.daily.smart_followup.run_followup_job",
        "ai_crm.tasks.hourly.reddit_post_generator.reset_daily_counters"
    ],
     "hourly": [
        "ai_crm.tasks.hourly.reddit_post_generator.fetch_reddit_posts",
        "ai_crm.tasks.hourly.reddit_post_generator.process_pending_ai_comments"
    ],
    "cron": {
        # Every 1 minute → check social media scheduled posts
        "*/10 * * * *": [
            "ai_crm.tasks.all.social_media_scheduler.schedule_social_media_posts",
            "ai_crm.tasks.daily.email_sender.enqueue_scheduled_emails",
            "ai_crm.scheduler_task.auto_comment_on_posts"
        ]
    }
}
# ------------------------------------------------------------------ #

# Fixtures to export
fixtures = [
    "LLM",
    "Lead Followup Setting",
    "Content Hub Setting",
    "AI Agent",
    {
        "doctype": "Role",
        "filters": {"name": ["in", ["AI Automation","Social Media Manager"]]}
    },
    {
        "doctype": "Custom DocPerm", 
        "filters": {"role": ["in", ["AI Automation"]]}
    },
    {
        "doctype": "Custom Field",
        "filters": [
            ["module", "=", "Ai CRM"]
        ]
    }
]