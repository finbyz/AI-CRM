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
            
            // Add Test Post button
            frm.add_custom_button('Test Post', () => {
                frappe.prompt([
                    { fieldname: 'subreddit', fieldtype: 'Data', label: 'Subreddit', reqd: 1, default: 'test' },
                    { fieldname: 'title', fieldtype: 'Data', label: 'Post Title', reqd: 1, default: 'Test Post from Frappe' },
                    { fieldname: 'content', fieldtype: 'Small Text', label: 'Post Content', reqd: 1, default: 'This is a test post from Frappe Reddit Integration' }
                ],
                function(values) {
                    frappe.call({
                        method: 'create_post',
                        doc: frm.doc,
                        args: {
                            subreddit: values.subreddit,
                            title: values.title,
                            content: values.content
                        },
                        callback: function(r) {
                            if (r.message && r.message.status === 'success') {
                                frappe.msgprint({
                                    title: 'Success',
                                    message: 'Post created successfully!<br>URL: ' + (r.message.url || 'N/A'),
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: 'Error',
                                    message: r.message?.message || 'Failed to create post',
                                    indicator: 'red'
                                });
                            }
                        }
                    });
                },
                'Create Test Post',
                'Submit');
            });

            // Add Test Comment button
            frm.add_custom_button('Test Comment', () => {
                frappe.prompt([
                    { fieldname: 'post_id', fieldtype: 'Data', label: 'Post ID (e.g. abc123)', reqd: 1 },
                    { fieldname: 'comment_text', fieldtype: 'Small Text', label: 'Comment Text', reqd: 1, default: 'This is a test comment from Frappe' }
                ],
                function(values) {
                    frappe.call({
                        method: 'create_comment',
                        doc: frm.doc,
                        args: {
                            post_id: values.post_id,
                            comment_text: values.comment_text
                        },
                        callback: function(r) {
                            if (r.message && r.message.status === 'success') {
                                frappe.msgprint({
                                    title: 'Success',
                                    message: 'Comment posted successfully!',
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: 'Error',
                                    message: r.message?.message || 'Failed to post comment',
                                    indicator: 'red'
                                });
                            }
                        }
                    });
                },
                'Create Test Comment',
                'Submit');
            });

            //  Add Test Media Post button
            frm.add_custom_button('Test Media Post', () => {
                frappe.prompt([
                    { fieldname: 'subreddit', fieldtype: 'Data', label: 'Subreddit', reqd: 1, default: 'test' },
                    { fieldname: 'title', fieldtype: 'Data', label: 'Post Title', reqd: 1 },
                    { fieldname: 'media_url', fieldtype: 'Data', label: 'Media URL (Image/Video)', reqd: 1 }
                ],
                function(values) {
                    frappe.call({
                        method: 'create_media_post',
                        doc: frm.doc,
                        args: {
                            subreddit: values.subreddit,
                            title: values.title,
                            media_url: values.media_url
                        },
                        callback: function(r) {
                            if (r.message && r.message.status === 'success') {
                                frappe.msgprint({
                                    title: 'Success',
                                    message: 'Media post created successfully!<br>URL: ' + (r.message.url || 'N/A'),
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: 'Error',
                                    message: r.message?.message || 'Failed to create media post',
                                    indicator: 'red'
                                });
                            }
                        }
                    });
                },
                'Create Test Media Post',
                'Submit');
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
