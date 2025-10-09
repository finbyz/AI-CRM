// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Reddit Integration', {
    refresh: function(frm) {
        // Add Connect Reddit button
        if (frm.doc.connection_status !== "Connected") {
            frm.add_custom_button('Connect Reddit', () => {
                frappe.call({
                    method: 'get_authorization_url',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            const authUrl = r.message.auth_url;
                            const width = 800;
                            const height = 600;
                            const left = (window.innerWidth / 2) - (width / 2);
                            const top = (window.innerHeight / 2) - (height / 2);

                            const popup = window.open(
                                authUrl, 
                                'RedditAuth', 
                                `width=${width},height=${height},top=${top},left=${left},scrollbars=yes,resizable=yes`
                            );

                            const checkClosed = setInterval(() => {
                                if (popup.closed) {
                                    clearInterval(checkClosed);
                                    setTimeout(() => {
                                        frm.reload_doc();
                                    }, 1000);
                                }
                            }, 1000);
                        } else {
                            frappe.msgprint({
                                title: 'Error',
                                message: r.message?.message || 'Failed to get authorization URL',
                                indicator: 'red'
                            });
                        }
                    }
                });
            });
        } else {
            // Add Test Connection button
            frm.add_custom_button('Test Connection', () => {
                frappe.call({
                    method: 'test_connection',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            frappe.msgprint({
                                title: 'Success',
                                message: r.message.message + '<br>Username: u/' + (r.message.username || 'N/A'),
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        } else {
                            frappe.msgprint({
                                title: 'Error',
                                message: r.message?.message || 'Connection test failed',
                                indicator: 'red'
                            });
                        }
                    }
                });
            });

            // Add Disconnect button
            frm.add_custom_button('Disconnect', () => {
                frappe.confirm('Are you sure you want to disconnect this Reddit account?', () => {
                    frm.set_value('access_token', '');
                    frm.set_value('refresh_token', '');
                    frm.set_value('state', '');
                    frm.set_value('connection_status', 'Not Connected');
                    frm.set_value('username', '');
                    frm.set_value('user_id', '');
                    frm.set_value('connected_at', '');
                    frm.set_value('expires_at', '');
                    frm.save();
                    frappe.msgprint({
                        title: 'Disconnected',
                        message: 'Reddit account has been disconnected',
                        indicator: 'orange'
                    });
                });
            });
        }
        
        // Connection status indicators
        if (frm.doc.connection_status === 'Connected') {
            frm.dashboard.add_indicator('Connected', 'green');
        } else if (frm.doc.connection_status === 'Error') {
            frm.dashboard.add_indicator('Connection Error', 'red');
        } else if (frm.doc.connection_status === 'Pending Authorization') {
            frm.dashboard.add_indicator('Pending Authorization', 'orange');
        } else {
            frm.dashboard.add_indicator('Not Connected', 'grey');
        }
    },
    
    onload: function(frm) {
        if (frm.is_new() && !frm.doc.redirect_uri) {
            const callback_url = `${window.location.origin}/api/method/ai_crm.credentials.doctype.reddit_integration.reddit_integration.reddit_callback`;
            frm.set_value('redirect_uri', callback_url);
        }
        if (frm.is_new() && !frm.doc.user_agent) {
            frm.set_value('user_agent', 'Frappe:RedditBot:v1.0');
        }
    }
});
