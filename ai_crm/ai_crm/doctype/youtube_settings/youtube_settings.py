
import frappe
import requests
import re
from frappe.model.document import Document

class YouTubeSettings(Document):
    def validate(self):
        # Only for child table entries
        if hasattr(self, "channels"):
            for row in self.channels:
                if row.channel_name and not row.channel_id:
                    row.channel_id = get_channel_id_from_name(row.channel_name)


def get_channel_id_from_name(channel_name):
    """
    Fetch the YouTube channel ID from a channel name or @handle.
    """
    url = f"https://www.youtube.com/{channel_name}"
    try:
        html = requests.get(url, timeout=10).text
        match = re.search(r'/channel/(UC[\w-]{22})', html)
        if match:
            return match.group(1)
    except Exception as e:
        frappe.log_error(f"Error fetching channel ID for {channel_name}: {str(e)}")
    return None