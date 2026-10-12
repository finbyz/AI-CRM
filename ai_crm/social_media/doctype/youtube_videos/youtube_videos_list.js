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
            frappe.call('ai_crm.social_media.api.get_configured_youtube_channels').then(r => {
                open_youtube_fetch_dialog(listview, r.message || []);
            });
        });
    }
}

function open_youtube_fetch_dialog(listview, channels) {
    const dialog = new frappe.ui.Dialog({
        title: __('Fetch & Import YouTube Videos'),
        size: 'large',
        fields: [
            {
                fieldname: 'fetch_type',
                fieldtype: 'Select',
                label: __('Fetch Mode'),
                options: ['Configured Channels', 'Single Video URL'],
                default: channels.length ? 'Configured Channels' : 'Single Video URL'
            },
            {
                fieldname: 'video_url',
                fieldtype: 'Data',
                label: __('YouTube Video URL'),
                placeholder: 'https://www.youtube.com/watch?v=...',
                depends_on: 'eval:doc.fetch_type=="Single Video URL"',
                mandatory_depends_on: 'eval:doc.fetch_type=="Single Video URL"'
            },
            {
                fieldname: 'channels',
                fieldtype: 'Table',
                label: __('Channels'),
                description: __('Tick the channels to fetch; with none ticked, all channels are fetched. Add channels in YouTube Settings.'),
                depends_on: 'eval:doc.fetch_type=="Configured Channels"',
                cannot_add_rows: true,
                cannot_delete_rows: true,
                in_place_edit: false,
                data: channels,
                fields: [
                    { fieldname: 'channel_title', fieldtype: 'Data', label: __('Channel'), in_list_view: 1, read_only: 1, columns: 4 },
                    { fieldname: 'channel_id', fieldtype: 'Data', label: __('Channel ID'), in_list_view: 1, read_only: 1, columns: 4 },
                    { fieldname: 'last_fetched_on', fieldtype: 'Datetime', label: __('Last Fetched'), in_list_view: 1, read_only: 1, columns: 2 }
                ]
            },
            {
                fieldname: 'max_results',
                fieldtype: 'Int',
                label: __('Latest Videos per Channel'),
                default: 3,
                description: __('Up to 10. Already imported videos are skipped, and the hourly fetch is not affected.'),
                depends_on: 'eval:doc.fetch_type=="Configured Channels"'
            }
        ],
        primary_action_label: __('Fetch & Import'),
        primary_action: function (values) {
            const call = values.fetch_type === 'Single Video URL'
                ? {
                    method: 'ai_crm.social_media.api.fetch_youtube_url',
                    args: { url: values.video_url },
                    freeze_message: __('Fetching video details...')
                }
                : {
                    method: 'ai_crm.social_media.api.fetch_youtube_channel_videos',
                    args: {
                        channel_ids: dialog.fields_dict.channels.grid.get_selected_children().map(row => row.channel_id),
                        max_results: values.max_results
                    },
                    freeze_message: __('Queuing channel fetch...')
                };

            frappe.call({ ...call, freeze: true }).then(r => {
                const res = r.message || {};
                dialog.hide();
                listview.refresh();

                let msg;
                if (res.already_exists) {
                    msg = __('This video was already imported.');
                } else if (res.channels) {
                    msg = __('Fetching the latest videos from {0} channel(s). Transcript, analysis and ideas run in the background.', [res.channels]);
                } else {
                    msg = __('Imported {0}. Transcript, analysis and ideas run in the background.', [frappe.utils.escape_html(res.title || '')]);
                }
                frappe.show_alert({ message: msg, indicator: res.already_exists ? 'orange' : 'green' }, 7);
                frappe.set_route('Form', 'YouTube Videos', res.tracker_name);
            });
        }
    });

    dialog.show();
}
