// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('YouTube Videos', {
    refresh(frm) {
        if(frm.is_new()) return;

        set_dashboard_headline(frm);

        // --- Button 1: Fetch channel videos ---
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


function set_dashboard_headline(frm) {
    if (!frm.doc.videos || frm.doc.videos.length === 0) {
        if (frm.doc.workflow_status === 'Completed') {
            const raw_msg = frm.doc.workflow_message || '';
            const match = raw_msg.match(/YT-VID-\d+-\d+/);
            let prev_link = '';
            if (match) {
                const prev_id = match[0];
                prev_link = ` View recent fetch record: <a href="/app/youtube-videos/${prev_id}" style="font-weight: 600; text-decoration: underline; color: #172b4d;">${prev_id}</a>`;
            }
            frm.dashboard.set_headline(
                `ℹ️ <strong>Completed:</strong> 0 new videos added (videos already imported).${prev_link}`,
                'yellow'
            );
        } else if (frm.doc.workflow_status === 'Running') {
            const msg = frappe.utils.escape_html(frm.doc.workflow_message || __('Fetching videos from YouTube...'));
            frm.dashboard.set_headline(
                `⏳ <strong>Running:</strong> ${msg}`,
                'blue'
            );
        } else {
            frm.dashboard.clear_headline();
        }
        return;
    }

    const total = frm.doc.videos.length;
    const processed = frm.doc.videos.filter(row => row.last_analyzed_on || (row.analysis_reasoning && row.analysis_reasoning.length > 0));
    const related = frm.doc.videos.filter(row => row.is_related);
    const not_related = frm.doc.videos.filter(row => row.last_analyzed_on && !row.is_related);

    if (total === 1) {
        const v = frm.doc.videos[0];
        if (v.is_related) {
            const ch_link = v.content_hub ? `<a href="/app/content-hub/${v.content_hub}" style="font-weight: 600; text-decoration: underline;">${v.content_hub}</a>` : '';
            frm.dashboard.set_headline(
                `✅ <strong>Video is Relevant for Content Creation</strong> — Content Hub ${ch_link} created successfully.`,
                'green'
            );
        } else if (v.last_analyzed_on || v.analysis_reasoning) {
            const reason = frappe.utils.escape_html(v.analysis_reasoning || __('Content criteria did not match.'));
            frm.dashboard.set_headline(
                `⚠️ <strong>Video Not Relevant</strong> — Content Hub creation skipped.<br><div style="margin-top: 4px; font-size: 13px; font-weight: normal; opacity: 0.95;"><strong>Reason:</strong> ${reason}</div>`,
                'red'
            );
        } else {
            frm.dashboard.set_headline(
                `⏳ <strong>Video Analysis Queued...</strong> Please wait while AI evaluates the video transcript.`,
                'blue'
            );
        }
    } else {
        // Multi-row handling
        if (processed.length === total) {
            if (related.length > 0) {
                frm.dashboard.set_headline(
                    `✅ <strong>Analysis Completed:</strong> ${related.length} of ${total} video(s) processed into Content Hub (${not_related.length} skipped as not relevant).`,
                    'green'
                );
            } else {
                frm.dashboard.set_headline(
                    `⚠️ <strong>Analysis Completed:</strong> All ${total} video(s) analyzed, 0 marked relevant (Content Hub creation skipped).`,
                    'red'
                );
            }
        } else if (processed.length > 0) {
            frm.dashboard.set_headline(
                `⏳ <strong>Analysis In Progress:</strong> ${processed.length} of ${total} video(s) completed...`,
                'blue'
            );
        } else {
            frm.dashboard.set_headline(
                `⏳ <strong>Analysis Queued:</strong> Waiting to process ${total} video(s)...`,
                'blue'
            );
        }
    }
}

