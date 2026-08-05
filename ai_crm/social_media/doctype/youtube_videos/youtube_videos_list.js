// Copyright (c) 2026, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings['YouTube Videos'] = {
    onload: function (listview) {
        add_fetch_button(listview);
    },
    refresh: function (listview) {
        add_fetch_button(listview);
    }
};

function add_fetch_button(listview) {
    if (!listview.page) return;

    if (!listview.page.has_youtube_fetch_button) {
        listview.page.has_youtube_fetch_button = true;
        listview.page.add_inner_button(__('Fetch YouTube Videos'), function () {
            open_youtube_fetch_dialog(listview);
        });
    }
}

function open_youtube_fetch_dialog(listview) {
    const dialog = new frappe.ui.Dialog({
        title: __('Fetch & Import YouTube Videos'),
        fields: [
            {
                fieldname: 'fetch_type',
                fieldtype: 'Select',
                label: __('Fetch Mode'),
                options: ['Single Video URL', 'Configured YouTube Channel'],
                default: 'Single Video URL'
            },
            {
                fieldname: 'video_url',
                fieldtype: 'Data',
                label: __('YouTube Video URL'),
                placeholder: 'https://www.youtube.com/watch?v=vX_892kL1aM',
                depends_on: 'eval:doc.fetch_type=="Single Video URL"'
            },
            {
                fieldname: 'configured_channel',
                fieldtype: 'Select',
                label: __('Select Configured Channel'),
                options: [],
                depends_on: 'eval:doc.fetch_type=="Configured YouTube Channel"'
            },
            {
                fieldname: 'max_results',
                fieldtype: 'Select',
                label: __('Max Videos to Fetch'),
                options: ['3', '5', '10', '20'],
                default: '5',
                depends_on: 'eval:doc.fetch_type!="Single Video URL"'
            },
            {
                fieldname: 'auto_content_hub',
                fieldtype: 'Check',
                label: __('Auto-create Content Hub & generate post ideas'),
                default: 1
            }
        ],
        primary_action_label: __('Fetch & Import'),
        primary_action: function (values) {
            const btn = dialog.get_primary_btn();
            btn.prop('disabled', true);

            if (values.fetch_type === 'Single Video URL') {
                if (!values.video_url) {
                    frappe.msgprint(__('Please enter a YouTube video URL'));
                    btn.prop('disabled', false);
                    return;
                }

                frappe.dom.freeze(__('Fetching video details & captions...'));
                frappe.call({
                    method: 'ai_crm.social_media.api.fetch_youtube_url',
                    args: {
                        url: values.video_url,
                        auto_create_content_hub: values.auto_content_hub
                    },
                    callback: function (r) {
                        frappe.dom.unfreeze();
                        btn.prop('disabled', false);
                        if (r.message && ['success', 'queued'].includes(r.message.status)) {
                            dialog.hide();
                            const msg = r.message.already_exists
                                ? __('ℹ️ Video already imported in {0}', [r.message.tracker_name])
                                : __('✅ Imported video: {0}', [r.message.title || r.message.video_name]);
                            frappe.show_alert({
                                message: msg,
                                indicator: r.message.already_exists ? 'orange' : 'green'
                            });
                            listview.refresh();
                        }
                    },
                    error: function () {
                        frappe.dom.unfreeze();
                        btn.prop('disabled', false);
                    }
                });

            } else {
                const channel = values.configured_channel;

                if (!channel) {
                    frappe.msgprint(__('Please select or enter a YouTube channel'));
                    btn.prop('disabled', false);
                    return;
                }

                frappe.dom.freeze(__('Fetching videos from YouTube channel...'));
                frappe.call({
                    method: 'ai_crm.social_media.api.fetch_youtube_channel_videos',
                    args: {
                        channel_name_or_id: channel,
                        max_results: values.max_results,
                        auto_create_content_hub: values.auto_content_hub
                    },
                    callback: function (r) {
                        frappe.dom.unfreeze();
                        btn.prop('disabled', false);
                        if (r.message && ['success', 'queued'].includes(r.message.status)) {
                            dialog.hide();
                            const msg = __('Queued new-video processing for {0}', [r.message.channel_title]);
                            frappe.show_alert({
                                message: msg,
                                indicator: 'green'
                            });
                            listview.refresh();
                        }
                    },
                    error: function () {
                        frappe.dom.unfreeze();
                        btn.prop('disabled', false);
                    }
                });
            }
        }
    });

    // Populate configured channels dynamically
    frappe.call({
        method: 'ai_crm.social_media.api.get_configured_youtube_channels',
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                const options = r.message.map(c => c.channel_name || c.channel_id);
                dialog.set_df_property('configured_channel', 'options', options);
            } else {
                dialog.set_df_property('configured_channel', 'options', ['No channels configured in YouTube Settings']);
            }
        }
    });

    dialog.show();
}
