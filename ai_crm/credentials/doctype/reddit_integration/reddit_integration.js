// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Reddit Integration', {
    refresh: function(frm) {
        // Add Connect Reddit button
        if (frm.doc.connection_status !== "Connected") {
            frm.add_custom_button('Connect Reddit', () => {
                // Clear any existing tokens before starting
                frm.set_value('access_token', '');
                frm.set_value('refresh_token', '');
                frm.set_value('state', '');
                frm.set_value('connection_status', 'Not Connected');
                
                frm.save().then(() => {
                    frappe.call({
                        method: 'get_authorization_url',
                        doc: frm.doc,
                        callback: function(r) {
                            if (r.message && r.message.status === 'success') {
                                const authUrl = r.message.auth_url;
                                
                                frappe.msgprint({
                                    title: 'Redirecting to Reddit',
                                    message: 'You will be redirected to Reddit for authorization. Please complete the process and return.',
                                    indicator: 'blue'
                                });
                                
                                // Open Reddit OAuth in a new popup window
                                const width = 800;
                                const height = 700;
                                const left = (window.innerWidth / 2) - (width / 2);
                                const top = (window.innerHeight / 2) - (height / 2);
                                
                                const popup = window.open(
                                    authUrl, 
                                    'RedditAuth', 
                                    `width=${width},height=${height},top=${top},left=${left},scrollbars=yes,resizable=yes,status=yes,location=yes`
                                );
                                
                                // Check if popup is closed
                                const checkClosed = setInterval(() => {
                                    if (popup.closed) {
                                        clearInterval(checkClosed);
                                        
                                        // Show loading message
                                        frappe.show_alert({
                                            message: 'Processing authorization...',
                                            indicator: 'blue'
                                        });
                                        
                                        // Refresh the form to see updated connection status
                                        setTimeout(() => {
                                            frm.reload_doc();
                                        }, 2000);
                                    }
                                }, 1000);
                                
                                // Optional: Handle popup blocked
                                if (!popup || popup.closed || typeof popup.closed == 'undefined') {
                                    frappe.msgprint({
                                        title: 'Popup Blocked',
                                        message: 'Popup was blocked by browser. Please allow popups and try again, or manually open this URL:<br><br><a href="' + authUrl + '" target="_blank">' + authUrl + '</a>',
                                        indicator: 'red'
                                    });
                                }
                                
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
            });
        } else {
            // Add Test Connection button for connected accounts
            frm.add_custom_button('Test Connection', () => {
                frappe.show_alert({
                    message: 'Testing Reddit connection...',
                    indicator: 'blue'
                });
                
                frappe.call({
                    method: 'test_connection',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            frappe.msgprint({
                                title: 'Success',
                                message: `Connection successful! Username: u/${r.message.username || 'N/A'}`,
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        } else {
                            frappe.msgprint({
                                title: 'Connection Error',
                                message: r.message?.message || 'Connection test failed',
                                indicator: 'red'
                            });
                        }
                    }
                });
            });
            
            // Add Refresh Token button
            frm.add_custom_button('Refresh Token', () => {
                frappe.show_alert({
                    message: 'Refreshing access token...',
                    indicator: 'blue'
                });
                
                frappe.call({
                    method: 'refresh_access_token',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            frappe.show_alert({
                                message: 'Token refreshed successfully',
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        } else {
                            frappe.msgprint({
                                title: 'Token Refresh Failed',
                                message: r.message?.message || 'Failed to refresh token. You may need to re-authorize.',
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
                    { fieldname: 'content', fieldtype: 'Small Text', label: 'Post Content (optional)', default: 'This is a test post from Frappe Reddit Integration' }
                ],
                function(values) {
                    frappe.show_alert({
                        message: 'Creating post...',
                        indicator: 'blue'
                    });
                    
                    frappe.call({
                        method: 'post_to_reddit',
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
                                    message: 'Post created successfully!<br><a href="' + (r.message.url || '#') + '" target="_blank">View Post</a>',
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

            // Add Test Image Post button
            frm.add_custom_button('Test Image Post', () => {
                frappe.prompt([
                    { fieldname: 'subreddit', fieldtype: 'Data', label: 'Subreddit', reqd: 1, default: 'test' },
                    { fieldname: 'title', fieldtype: 'Data', label: 'Post Title', reqd: 1, default: 'Test Image Post from Frappe' },
                    { fieldname: 'image_file', fieldtype: 'Attach Image', label: 'Select Image', reqd: 1 },
                    { fieldname: 'content', fieldtype: 'Small Text', label: 'Additional Text (optional)', default: '' }
                ],
                function(values) {
                    frappe.show_alert({
                        message: 'Creating image post...',
                        indicator: 'blue'
                    });
                    
                    frappe.call({
                        method: 'post_to_reddit',
                        doc: frm.doc,
                        args: {
                            subreddit: values.subreddit,
                            title: values.title,
                            content: values.content,
                            image_attachment: values.image_file
                        },
                        callback: function(r) {
                            if (r.message && r.message.status === 'success') {
                                frappe.msgprint({
                                    title: 'Success',
                                    message: 'Image post created successfully!<br><a href="' + (r.message.url || '#') + '" target="_blank">View Post</a>',
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: 'Error',
                                    message: r.message?.message || 'Failed to create image post',
                                    indicator: 'red'
                                });
                            }
                        }
                    });
                },
                'Create Test Image Post',
                'Submit');
            });

            // Add Test Link Post button
            frm.add_custom_button('Test Link Post', () => {
                frappe.prompt([
                    { fieldname: 'subreddit', fieldtype: 'Data', label: 'Subreddit', reqd: 1, default: 'test' },
                    { fieldname: 'title', fieldtype: 'Data', label: 'Post Title', reqd: 1, default: 'Test Link Post from Frappe' },
                    { fieldname: 'url', fieldtype: 'Data', label: 'Link URL', reqd: 1, default: 'https://frappe.io' }
                ],
                function(values) {
                    frappe.show_alert({
                        message: 'Creating link post...',
                        indicator: 'blue'
                    });
                    
                    frappe.call({
                        method: 'post_to_reddit',
                        doc: frm.doc,
                        args: {
                            subreddit: values.subreddit,
                            title: values.title,
                            url: values.url
                        },
                        callback: function(r) {
                            if (r.message && r.message.status === 'success') {
                                frappe.msgprint({
                                    title: 'Success',
                                    message: 'Link post created successfully!<br><a href="' + (r.message.url || '#') + '" target="_blank">View Post</a>',
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: 'Error',
                                    message: r.message?.message || 'Failed to create link post',
                                    indicator: 'red'
                                });
                            }
                        }
                    });
                },
                'Create Test Link Post',
                'Submit');
            });

            // Add Test Comment button
            frm.add_custom_button('Test Comment', () => {
                frappe.prompt([
                    { fieldname: 'post_id', fieldtype: 'Data', label: 'Post ID (e.g. abc123)', reqd: 1 },
                    { fieldname: 'comment_text', fieldtype: 'Small Text', label: 'Comment Text', reqd: 1, default: 'This is a test comment from Frappe Reddit Integration' }
                ],
                function(values) {
                    frappe.show_alert({
                        message: 'Posting comment...',
                        indicator: 'blue'
                    });
                    
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
            
            // Add Disconnect button
            frm.add_custom_button('Disconnect', () => {
                frappe.confirm(
                    'Are you sure you want to disconnect this Reddit account?',
                    () => {
                        // Clear all OAuth tokens and data
                        frm.set_value('access_token', '');
                        frm.set_value('refresh_token', '');
                        frm.set_value('state', '');
                        frm.set_value('token_type', '');
                        frm.set_value('connection_status', 'Not Connected');
                        frm.set_value('username', '');
                        frm.set_value('user_id', '');
                        frm.set_value('connected_at', '');
                        frm.set_value('expires_at', '');
                        
                        frm.save().then(() => {
                            frappe.msgprint({
                                title: 'Disconnected',
                                message: 'Reddit account has been disconnected successfully',
                                indicator: 'orange'
                            });
                        });
                    }
                );
            });
        }
        
        // Show connection status indicators
        if (frm.doc.connection_status === 'Connected') {
            frm.dashboard.add_indicator('Connected', 'green');
            
            // Show account info if available
            if (frm.doc.username) {
                frm.dashboard.add_comment(
                    `Connected as u/${frm.doc.username}`,
                    'blue', 
                    true
                );
            }
            
            // Show token expiry info
            if (frm.doc.expires_at) {
                const expiryDate = new Date(frm.doc.expires_at);
                const now = new Date();
                const hoursLeft = Math.round((expiryDate - now) / (1000 * 60 * 60));
                
                if (hoursLeft > 0) {
                    frm.dashboard.add_comment(
                        `Token expires in ${hoursLeft} hour(s)`,
                        hoursLeft < 24 ? 'orange' : 'blue',
                        true
                    );
                } else {
                    frm.dashboard.add_comment(
                        'Token expired - refresh needed',
                        'red',
                        true
                    );
                }
            }
            
        } else if (frm.doc.connection_status === 'Error') {
            frm.dashboard.add_indicator('Connection Error', 'red');
        } else if (frm.doc.connection_status === 'Pending Authorization') {
            frm.dashboard.add_indicator('Pending Authorization', 'orange');
            frm.dashboard.add_comment(
                'Complete the OAuth authorization process to connect',
                'orange',
                true
            );
        } else {
            frm.dashboard.add_indicator('Not Connected', 'grey');
        }
        
        // Add helpful information section
        if (!frm.doc.client_id || !frm.get_field('client_secret').value) {
            frm.dashboard.add_comment(
                'Configure your Client ID and Client Secret from Reddit App Preferences',
                'blue',
                true
            );
        }
    },
    
    onload: function(frm) {
        // Set default redirect URI for new records
        if (frm.is_new() && !frm.doc.redirect_uri) {
            const callback_url = `${window.location.origin}/api/method/ai_crm.credentials.doctype.reddit_integration.reddit_integration.reddit_callback`;
            frm.set_value('redirect_uri', callback_url);
        }
        
        // Set default user agent for new records
        if (frm.is_new() && !frm.doc.user_agent) {
            frm.set_value('user_agent', 'FrappeSocialBot:1.0:web (by /u/YourUsername)');
        }
        
        // Add field descriptions
        frm.set_df_property('client_id', 'description', 'App ID from Reddit App Preferences (https://www.reddit.com/prefs/apps)');
        frm.set_df_property('client_secret', 'description', 'Secret from Reddit App Preferences (for script/web app type)');
        frm.set_df_property('redirect_uri', 'description', 'Must match exactly with what is configured in Reddit App Preferences');
        frm.set_df_property('user_agent', 'description', 'Unique identifier for your app (format: platform:appname:version (by /u/username))');
    },
    
    client_id: function(frm) {
        // Clear connection status when client ID changes
        if (frm.doc.connection_status === 'Connected') {
            frappe.msgprint({
                title: 'Client ID Changed',
                message: 'Connection status reset. Please reconnect with the new Client ID.',
                indicator: 'orange'
            });
            frm.set_value('connection_status', 'Not Connected');
        }
    },
    
    client_secret: function(frm) {
        // Clear connection status when client secret changes
        if (frm.doc.connection_status === 'Connected') {
            frappe.msgprint({
                title: 'Client Secret Changed',
                message: 'Connection status reset. Please reconnect with the new Client Secret.',
                indicator: 'orange'
            });
            frm.set_value('connection_status', 'Not Connected');
        }
    },
    
    validate: function(frm) {
        // Basic validation
        if (!frm.doc.client_id) {
            frappe.msgprint({
                title: 'Client ID Required',
                message: 'Please enter your Client ID from Reddit App Preferences',
                indicator: 'red'
            });
            frappe.validated = false;
        }
        
        if (!frm.get_field('client_secret').value) {
            frappe.msgprint({
                title: 'Client Secret Required',
                message: 'Please enter your Client Secret from Reddit App Preferences',
                indicator: 'red'
            });
            frappe.validated = false;
        }
        
        if (!frm.doc.user_agent) {
            frappe.msgprint({
                title: 'User Agent Required',
                message: 'Please enter a unique User Agent string for your app',
                indicator: 'red'
            });
            frappe.validated = false;
        }
        
        // Validate redirect URI format
        if (frm.doc.redirect_uri && !frm.doc.redirect_uri.startsWith('http')) {
            frappe.msgprint({
                title: 'Invalid Redirect URI',
                message: 'Redirect URI must be a valid HTTP/HTTPS URL',
                indicator: 'red'
            });
            frappe.validated = false;
        }
    }
});