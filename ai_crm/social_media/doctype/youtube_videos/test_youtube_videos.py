# Copyright (c) 2025, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services.ai_service import (
    analyze_video,
)


class AnalysisAgent:
    def __init__(self):
        self.input_data = None

    def invoke(self, **input_data):
        self.input_data = input_data
        return {"is_related": 1, "reasoning": "Matches a configured topic"}


class TestYouTubeVideos(FrappeTestCase):
    def test_analysis_receives_user_relevance_settings(self):
        agent = AnalysisAgent()

        result = analyze_video(
            agent,
            "Frappe tutorial",
            "Video transcript",
            relevance_topics="Frappe\nERPNext",
            relevance_prompt="Only include implementation tutorials",
        )

        self.assertEqual(result["is_related"], 1)
        self.assertEqual(agent.input_data["relevance_topics"], "Frappe\nERPNext")
        self.assertEqual(
            agent.input_data["relevance_prompt"],
            "Only include implementation tutorials",
        )
