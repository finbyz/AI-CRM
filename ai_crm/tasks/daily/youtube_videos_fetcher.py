import frappe



def bg_fetch_yt_videos():
    yt = frappe.new_doc("YouTube Tracker")
    yt.fetch_channel_videos_by_frequency()


