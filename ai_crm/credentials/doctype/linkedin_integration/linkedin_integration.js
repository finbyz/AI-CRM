// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt
// your_app/public/js/linkedin_integration.js

const LINKEDIN_CALLBACK = "/api/method/ai_crm.credentials.doctype.linkedin_integration.linkedin_integration.callback";

frappe.ui.form.on('LinkedIn Integration', {
    refresh: function(frm) {
        check_redirect_uri(frm);
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

                        // Page posting needs a Community Management API app, which cannot also
                        // carry Sign In with LinkedIn, so it reads the profile via r_basicprofile.
                        const scopes = frm.doc.organization_support
                            ? "r_basicprofile w_member_social w_organization_social"
                            : "openid profile email w_member_social";
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

// The Redirect URI must match this site and the URL registered in the LinkedIn developer app.
function check_redirect_uri(frm) {
    const expected = window.location.origin + LINKEDIN_CALLBACK;
    if (frm.is_new() && !frm.doc.redirect_uri) {
        frm.set_value('redirect_uri', expected);
        return;
    }
    if (frm.doc.redirect_uri && frm.doc.redirect_uri !== expected) {
        frm.dashboard.set_headline_alert(
            __("Redirect URI does not match this site. Expected: {0}", [frappe.utils.escape_html(expected)]),
            "orange"
        );
        frm.add_custom_button(__('Use This Site\'s Redirect URI'), () => {
            frm.set_value('redirect_uri', expected);
            frm.save();
        });
    }
}

