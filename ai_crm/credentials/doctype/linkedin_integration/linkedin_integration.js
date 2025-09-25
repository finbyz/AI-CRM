// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt
// your_app/public/js/linkedin_integration.js

frappe.ui.form.on('LinkedIn Integration', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Connect to LinkedIn'), () => {
                if (!frm.doc.client_id || !frm.doc.redirect_uri) {
                    frappe.msgprint(__("Please set Client ID and Redirect URI before connecting."));
                    return;
                }

                frappe.call({
                    method: 'frappe.client.save',
                    args: {
                        doc: frm.doc
                    },
                    callback: function(r) {
                        if (!r.message) {
                            return;
                        }
                        const clientId = frm.doc.client_id;
                        const redirectUri = encodeURIComponent(frm.doc.redirect_uri);
                        const state = frm.doc.state;

                        // Using modern OpenID Connect scopes for user info, plus social posting scopes
                        let scopes = "openid profile email w_member_social";
                        if (frm.doc.organization_support) {
                            scopes += " w_organization_social";
                        }
                        const scope = encodeURIComponent(scopes);
                        
                        const authUrl = `https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=${clientId}&redirect_uri=${redirectUri}&scope=${scope}&state=${state}`;

                        // Open LinkedIn OAuth in a new popup window
                        const width = 600, height = 700;
                        const left = (window.innerWidth / 2) - (width / 2);
                        const top = (window.innerHeight / 2) - (height / 2);

                        const authWindow = window.open(authUrl, 'LinkedInAuth', `width=${width},height=${height},top=${top},left=${left}`);
                        
                        // Optional: Add a listener to refresh the form when the popup is closed
                        const timer = setInterval(() => {
                            if (authWindow.closed) {
                                clearInterval(timer);
                                frm.reload_doc();
                            }
                        }, 1000);
                    }
                });
            });
        }
    }
});