// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('YouTube Videos', {
    refresh(frm) {
        // --- Button 1: Fetch channel videos ---
        if(frm.is_new()) return;
        frm.add_custom_button('Fetch', function () {
            frm.call('fetch_videos_workflow').then(r => {
                if (r.message) {
                    frappe.msgprint(r.message);
                    frm.reload_doc();
                }
            });
        });

        // --- Button 2: View generated Content Hubs ---
        frm.add_custom_button('View Content Hubs', function () {
            if (frm.doc.videos && frm.doc.videos.length > 0) {
                const hubIds = frm.doc.videos
                    .map(row => row.content_hub)
                    .filter(Boolean);

                if (hubIds.length === 0) {
                    frappe.msgprint(__('No related Content Hubs found.'));
                    return;
                }

                frappe.route_options = {
                    "name": ["in", hubIds]
                };
                frappe.set_route("List", "Content Hub");
            } else {
                frappe.msgprint(__('No videos found in this tracker.'));
            }
        });
    }
});
