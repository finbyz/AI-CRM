// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('YouTube Tracker', {
    refresh(frm) {
        // --- Button 1: Fetch channel videos ---
        frm.add_custom_button('Fetch', function () {
            frm.call('fetch_channel_videos_by_frequency').then(r => {
                if (r.message) {
                    frappe.msgprint(r.message);
                    frm.reload_doc();
                }
            });
        });

        // --- Button 2: View Social Media Posts ---
        frm.add_custom_button('View Generated Posts', function () {
            if (frm.doc.videos && frm.doc.videos.length > 0) {
                const postIds = frm.doc.videos
                    .map(row => row.social_media_post)
                    .filter(Boolean);

                if (postIds.length === 0) {
                    frappe.msgprint(__('No related Social Media Posts found.'));
                    return;
                }

                frappe.route_options = {
                    "name": ["in", postIds]
                };
                frappe.set_route("List", "Social Media Post");
            } else {
                frappe.msgprint(__('No videos found in this tracker.'));
            }
        });
    }
});
