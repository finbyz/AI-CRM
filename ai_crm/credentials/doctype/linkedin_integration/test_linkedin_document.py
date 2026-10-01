# Copyright (c) 2026, finbyz and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import MagicMock, patch

from ai_crm.credentials.doctype.linkedin_integration import linkedin_integration as li


def _response(json_data=None, status=200):
    res = MagicMock(status_code=status)
    res.json.return_value = json_data or {}
    res.raise_for_status.return_value = None
    return res


class TestLinkedInDocumentPost(unittest.TestCase):
    def setUp(self):
        doc = MagicMock(organization_support=0, organization_id=None, person_id="abc", connection_status="Connected")
        doc.get_password.return_value = "token"
        self.helper = li.LinkedInHelper(doc)
        self.file_doc = MagicMock()
        self.file_doc.get_full_path.return_value = __file__

    def _run(self, statuses):
        init = _response({"value": {"uploadUrl": "https://upload", "document": "urn:li:document:D1"}})
        with patch.object(li.requests, "post", return_value=init) as post, \
             patch.object(li.requests, "put", return_value=_response()) as put, \
             patch.object(li.requests, "get", side_effect=[_response({"status": s}) for s in statuses]) as get, \
             patch.object(li.frappe, "get_doc", return_value=self.file_doc), \
             patch.object(li.frappe, "throw", side_effect=RuntimeError), \
             patch.object(li, "_", side_effect=lambda text: text), \
             patch.object(li.time, "sleep"):
            data, api = self.helper._prepare_linkedin_post_data(
                "Post text", image_attachment="/private/files/x.png",
                document="/private/files/x.pdf", document_title="ERP Basics",
            )
        return data, api, post, put, get

    def test_pdf_becomes_document_post_after_processing(self):
        data, api, post, put, get = self._run(["PROCESSING", "AVAILABLE"])
        self.assertEqual(api, "posts")
        self.assertEqual(post.call_args.kwargs["json"], {"initializeUploadRequest": {"owner": "urn:li:person:abc"}})
        self.assertEqual(put.call_args.args[0], "https://upload")
        self.assertEqual(get.call_count, 2)
        self.assertIn("urn%3Ali%3Adocument%3AD1", get.call_args.args[0])
        self.assertEqual(data["content"]["media"], {"title": "ERP Basics", "id": "urn:li:document:D1"})
        self.assertEqual(data["author"], "urn:li:person:abc")
        self.assertEqual(data["commentary"], "Post text")

    def test_processing_failure_stops_the_post(self):
        with self.assertRaises(RuntimeError):
            self._run(["PROCESSING_FAILED"])

    def test_headers_use_a_supported_api_version(self):
        self.assertGreaterEqual(int(self.helper._get_headers()["LinkedIn-Version"]), 202510)
