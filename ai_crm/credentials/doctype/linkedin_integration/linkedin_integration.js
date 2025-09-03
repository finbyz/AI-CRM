// Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
// For license information, please see license.txt
// your_app/public/js/linkedin_integration.js

frappe.ui.form.on('LinkedIn Integration', {
    refresh: function(frm) {
        // Add custom button
        frm.add_custom_button('Connect LinkedIn', () => {
            const clientId = frm.doc.client_id;
            const redirectUri = encodeURIComponent(frm.doc.redirect_uri);
            const state = frm.doc.state
            const scope = encodeURIComponent('openid profile email w_member_social');

            const authUrl = `https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=${clientId}&redirect_uri=${redirectUri}&scope=${scope}&state=${state}`;

            // Open LinkedIn OAuth in a new popup window
            const width = 600, height = 600;
            const left = (window.innerWidth / 2) - (width / 2);
            const top = (window.innerHeight / 2) - (height / 2);

            window.open(authUrl, 'LinkedInAuth', `width=${width},height=${height},top=${top},left=${left}`);
        });
    }
});
