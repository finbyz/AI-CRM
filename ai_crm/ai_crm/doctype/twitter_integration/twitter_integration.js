frappe.ui.form.on('Twitter Integration', {
    refresh: function(frm) {
        // Add Connect Twitter button
        if (frm.doc.connection_status !== "Connected") {
            frm.add_custom_button('Connect Twitter', () => {
                // Clear any existing OAuth tokens before starting
                frm.set_value('access_token', '');
                frm.set_value('refresh_token', '');
                frm.set_value('state', '');
                frm.set_value('code_verifier', '');
                frm.set_value('connection_status', 'Not Connected');
                
                frm.save().then(() => {
                    // Get OAuth 2.0 authorization URL
                    frappe.call({
                        method: 'get_authorization_url',
                        doc: frm.doc,
                        callback: function(r) {
                            if (r.message && r.message.status === 'success') {
                                const authUrl = r.message.auth_url;
                                
                                frappe.msgprint({
                                    title: 'Redirecting to Twitter',
                                    message: 'You will be redirected to Twitter for authorization. Please complete the process and return.',
                                    indicator: 'blue'
                                });
                                
                                // Open Twitter OAuth in a new popup window
                                const width = 800;
                                const height = 700;
                                const left = (window.innerWidth / 2) - (width / 2);
                                const top = (window.innerHeight / 2) - (height / 2);
                                
                                const popup = window.open(
                                    authUrl, 
                                    'TwitterAuth', 
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
                    message: 'Testing Twitter connection...',
                    indicator: 'blue'
                });
                
                frappe.call({
                    method: 'test_connection',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            const username = r.message.data?.data?.username || 'N/A';
                            frappe.msgprint({
                                title: 'Success',
                                message: `Connection successful! Username: @${username}`,
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
            
            // Add Refresh Token button (for OAuth 2.0) - Fixed method name
            frm.add_custom_button('Refresh Token', () => {
                frappe.show_alert({
                    message: 'Refreshing access token...',
                    indicator: 'blue'
                });
                
                frappe.call({
                    method: 'refresh_access_token',  // This is now whitelisted
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
            
            // Add Disconnect button
            frm.add_custom_button('Disconnect', () => {
                frappe.confirm(
                    'Are you sure you want to disconnect this Twitter account?',
                    () => {
                        // Clear all OAuth 2.0 tokens and data
                        frm.set_value('access_token', '');
                        frm.set_value('refresh_token', '');
                        frm.set_value('state', '');
                        frm.set_value('code_verifier', '');
                        frm.set_value('token_type', '');
                        frm.set_value('token_expires_at', '');
                        frm.set_value('connection_status', 'Not Connected');
                        frm.set_value('username', '');
                        frm.set_value('user_id', '');
                        frm.set_value('full_name', '');
                        frm.set_value('profile_image_url', '');
                        frm.set_value('connected_at', '');
                        
                        frm.save().then(() => {
                            frappe.msgprint({
                                title: 'Disconnected',
                                message: 'Twitter account has been disconnected successfully',
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
                    `Connected as @${frm.doc.username}${frm.doc.full_name ? ` (${frm.doc.full_name})` : ''}`,
                    'blue', 
                    true
                );
            }
            
            // Show token expiry info
            if (frm.doc.token_expires_at) {
                const expiryDate = new Date(frm.doc.token_expires_at);
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
            
                    
        } else if (frm.doc.connection_status === 'Not Connected') {
            frm.dashboard.add_indicator('Not Connected', 'red');
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
                'Configure your OAuth 2.0 Client ID and Client Secret from Twitter Developer Portal',
                'blue',
                true
            );
        }
    },
    
    onload: function(frm) {
        // Set default redirect URI for new records
        if (frm.is_new() && !frm.doc.redirect_uri) {
            const callback_url = `${window.location.origin}/api/method/ai_crm.ai_crm.doctype.twitter_integration.twitter_integration.callback`;
            frm.set_value('redirect_uri', callback_url);
        }
        
        // Add field descriptions
        frm.set_df_property('client_id', 'description', 'OAuth 2.0 Client ID from Twitter Developer Portal (not API Key)');
        frm.set_df_property('client_secret', 'description', 'OAuth 2.0 Client Secret from Twitter Developer Portal (not API Secret)');
        frm.set_df_property('redirect_uri', 'description', 'Must match exactly with what is configured in Twitter Developer Portal');
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
                message: 'Please enter your OAuth 2.0 Client ID from Twitter Developer Portal',
                indicator: 'red'
            });
            frappe.validated = false;
        }
        
        if (!frm.get_field('client_secret').value) {
            frappe.msgprint({
                title: 'Client Secret Required',
                message: 'Please enter your OAuth 2.0 Client Secret from Twitter Developer Portal',
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