# Copyright (c) 2025, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services.ai_service import (
    analyze_video,
)
from ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services.background_jobs import (
    run_youtube_workflow,
)


class AnalysisAgent:
    def __init__(self):
        self.input_data = None

    def invoke(self, **input_data):
        self.input_data = input_data
        return {"is_related": 1, "reasoning": "Matches a configured topic"}


class TestYouTubeVideos(FrappeTestCase):
    def test_tracker_schema_owns_read_only_video_rows(self):
        """Verify that the tracker owns imported rows and exposes workflow progress."""
        meta = frappe.get_meta("YouTube Videos")

        self.assertEqual(meta.get_field("videos").options, "YouTube Video")
        self.assertEqual(meta.get_field("videos").read_only, 1)
        self.assertEqual(meta.get_field("workflow_status").default, "Queued")

    def test_analysis_receives_user_relevance_settings(self):
        """Verify that video analysis receives the configured relevance instructions."""
        agent = AnalysisAgent()

        result = analyze_video(
            agent,
            "Frappe tutorial",
            "Video transcript",
            relevance_prompt="Only include implementation tutorials",
        )

        self.assertEqual(result["is_related"], 1)
        self.assertEqual(
            agent.input_data["relevance_prompt"],
            "Only include implementation tutorials",
        )


class TestYouTubeImportStatus(FrappeTestCase):
    def test_empty_import_marks_tracker_completed(self):
        """Verify that an import completes when no new or pending videos exist."""
        with (
            patch(
                "ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services."
                "background_jobs.fetch_videos_from_channels",
                return_value=[],
            ),
            patch(
                "ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services."
                "background_jobs.enqueue_video_processing",
                return_value=0,
            ),
            patch(
                "ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services."
                "background_jobs._set_tracker_status"
            ) as set_tracker_status,
        ):
            result = run_youtube_workflow("YT-VID-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["videos_enqueued"], 0)
        set_tracker_status.assert_any_call("YT-VID-1", "Running", "Fetching videos")
        set_tracker_status.assert_any_call("YT-VID-1", "Completed", "No new videos found")

    def test_fetch_failure_marks_tracker_failed(self):
        """Verify that a fetch error marks the tracker as failed and returns the error."""
        with (
            patch(
                "ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services."
                "background_jobs.fetch_videos_from_channels",
                side_effect=RuntimeError("YouTube unavailable"),
            ),
            patch(
                "ai_crm.social_media.doctype.youtube_videos.youtube_workflow.services."
                "background_jobs._set_tracker_status"
            ) as set_tracker_status,
            patch.object(frappe, "log_error"),
        ):
            result = run_youtube_workflow("YT-VID-1")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "YouTube unavailable")
        set_tracker_status.assert_any_call("YT-VID-1", "Failed", "YouTube unavailable")
