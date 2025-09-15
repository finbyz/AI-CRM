// Copyright (c) 2025, sandeep and contributors
// For license information, please see license.txt

frappe.ui.form.on('Social Media Post', {
	refresh: function(frm) {
		// Render preview for supported platforms
		if (frm.doc.content && ['LinkedIn', 'Twitter', 'Reddit'].includes(frm.doc.platform)) {
			frm.trigger('render_preview');
		}
		// Add Post button when document is saved and platform is selected
		if (frm.doc.platform && frm.doc.content && frm.doc.status !== 'Posted') {
			frm.add_custom_button(__('Post to Social Media'), function() {
				post_to_social_media(frm);
			});
		}
		if (frm.doc.platform && frm.doc.content && frm.doc.status === 'Draft') {
			frm.add_custom_button(__('Revise Post'), function() {
				revise_post(frm);
			}, __('Actions'));
		}
		if (frm.doc.platform && frm.doc.content && frm.doc.status !== "Posted") {
			frm.add_custom_button(__('Generate Image'), function() {
				generate_image(frm);
			});
		}

		// Add Update button if post is already posted and has post ID
		if (frm.doc.status === 'Posted' && frm.doc.platform === 'LinkedIn' && frm.doc.social_media_post_id) {
			frm.add_custom_button(__('Update Post'), function() {
				update_social_media_post(frm);
			}, __('Actions'));
		}
		if (frm.doc.status === 'Posted' && frm.doc.platform === 'LinkedIn' && frm.doc.social_media_post_id) {
			frm.add_custom_button(__('Delete Post'), function() {
				delete_social_media_post(frm);
			}, __('Actions'));
		}

	},

	// Re-render preview on content change
	content: function(frm) {
		if (['LinkedIn', 'Twitter', 'Reddit'].includes(frm.doc.platform)) {
			frm.trigger('render_preview');
		}
	},

	render_preview: function(frm) {
		let content = frm.doc.content || '';
		const platform = frm.doc.platform || 'LinkedIn';

		function getPlatformTheme(p) {
			const themeByPlatform = {
				'LinkedIn': {
					title: 'LinkedIn Post Preview',
					brandColor: '#0a66c2',
					accentText: '#0a66c2',
					buttonBg: '#000000',
					icon: '🔗'
				},
				'Twitter': {
					title: 'Twitter Post Preview',
					brandColor: '#1d9bf0',
					accentText: '#1d9bf0',
					buttonBg: '#0f1419',
					icon: '🐦'
				},
				'Reddit': {
					title: 'Reddit Post Preview',
					brandColor: '#ff4500',
					accentText: '#ff4500',
					buttonBg: '#1a1a1b',
					icon: '👽'
				}
			};
			return themeByPlatform[p] || themeByPlatform['LinkedIn'];
		}

		const theme = getPlatformTheme(platform);

		function escapeHtml(str) {
			return (str || '')
				.replace(/&/g, '&amp;')
				.replace(/</g, '&lt;')
				.replace(/>/g, '&gt;');
		}

		let html = escapeHtml(content);
		html = html.replace(/\*{1,2}([^\*]+)\*{1,2}/g, '<b>$1<\/b>');
		html = html.replace(/^\s*\*\s+(.+)$/gm, `<div style="margin:6px 0; padding-left:18px; position:relative;"><span style="position:absolute; left:0; color:${theme.brandColor}; font-weight:bold;">•<\/span>$1<\/div>`);
		html = html.replace(/(^|\s)#([\w_]+)/g, `$1<span style=\"color:${theme.accentText}; font-weight:bold;\">#$2<\/span>`);
		html = html.replace(/(https?:\/\/[^\s<>"]+)/g, `<a href=\"$1\" target=\"_blank\" style=\"color:${theme.accentText}; text-decoration:none;\">$1<\/a>`);
		html = html.replace(/\n\s*\n/g, '<br><br>');
		html = html.replace(/\n/g, '<br>');

		const styledHtml = `
			<div style="
				font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
				background: #ffffff; 
				border-radius: 12px; 
				border: 1px solid #e0e0e0;
				max-width: 100%;
				overflow: hidden;
				box-shadow: 0 2px 8px rgba(0,0,0,0.1);
			">
				<div style="
					background: white;
					color: black;
					padding: 14px 20px;
					font-weight: 600;
					font-size: 15px;
					display: flex;
					align-items: center;
					justify-content: space-between;
					border-bottom: 1px solid #e0e0e0;
				">
					<div style="display:flex; align-items:center; gap:10px;">
						<span style="font-size: 18px;">${theme.icon}</span>
						${theme.title}
					</div>
					<button class="btn btn-xs btn-revise-post" 
						style="background-color: ${theme.buttonBg}; color: white; border: none; border-radius:5px;">
						✨ Revise Post
					</button>
				</div>

				<div style="
					padding: 18px;
					line-height: 1.6; 
					color: #000000e6; 
					word-wrap: break-word;
				">
					${html}
				</div>
			</div>
		`;

		const field = frm.fields_dict && frm.fields_dict.preview_html;
		if (field && field.$wrapper) {
			field.$wrapper.html(styledHtml);
		} else {
			frm.set_df_property('preview_html', 'options', styledHtml);
		}

		setTimeout(() => {
			frm.$wrapper.find('.btn-revise-post').off('click').on('click', function() {
				frm.trigger('open_review_dialog');
			});
		}, 50);
	},

	open_review_dialog: function(frm) {
		let dialog = new frappe.ui.Dialog({
			title: __('Revise Your Post'),
			fields: [
				{
					label: __('What changes would you like?'),
					fieldname: 'review_feedback',
					fieldtype: 'Small Text',
					reqd: 1
				}
			],
			primary_action_label: __('Send Revision'),
			primary_action: function(values) {
				if (!values.review_feedback) {
					frappe.msgprint(__('Please provide revision feedback.'));
					return;
				}
				dialog.hide();
				frappe.show_alert({ message: __('Revising post...'), indicator: 'blue' });
				frm.call('revise_post', { instruction: values.review_feedback })
					.then(r => {
						if (r.message && r.message.status === 'success') {
							frappe.msgprint({ title: __('Success'), message: __('Post revised successfully.'), indicator: 'green' });
							frm.reload_doc();
						} else {
							frappe.msgprint({
								title: __('Error'),
								message: (r.message && (r.message.message || r.message.error)) || __('Failed to revise post'),
								indicator: 'red'
							});
						}
					})
					.catch(err => {
						frappe.msgprint({
							title: __('Error'),
							message: __('An error occurred while revising: {0}', [err.message || err]),
							indicator: 'red'
						});
					});
			}
		});
		dialog.show();
	}
});

function post_to_social_media(frm) {

	if (!frm.doc.content) {
		frappe.msgprint(__('Please enter content for the post'));
		return;
	}

	// Show loading message
	frappe.show_alert({
		message: __('Posting to {0}...', [frm.doc.platform]),
		indicator: 'blue'
	});

	// Call the generic post method
	frm.call({
		method: 'post',
		doc: frm.doc,
		freeze: true,
		freeze_message: __('Posting to {0}...', [frm.doc.platform])
	}).then(r => {
		if (r.message) {
			if (r.message.status === 'success') {
				let success_message = __('Post published successfully on {0}!', [frm.doc.platform]);
				
				if (r.message.post_link) {					
                    const linkedin_url = r.message.post_link;
                    success_message += '<br><br>' + __(`<a href="${linkedin_url}" target="_blank">View Post on ${frm.doc.platform}</a>`);
				}

				frappe.msgprint({
					title: __('Success'),
					message: success_message,
					indicator: 'green'
				});

				frm.reload_doc();
			} else {
				frappe.msgprint({
					title: __('Error'),
					message: r.message.message || __('Failed to post on {0}', [frm.doc.platform]),
					indicator: 'red'
				});
			}
		}
	}).catch(err => {
		frappe.msgprint({
			title: __('Error'),
			message: __('An error occurred while posting: {0}', [err.message || err]),
			indicator: 'red'
		});
	});
}

function view_linkedin_post(frm) {
	// Open LinkedIn post in new tab
	const post_id = frm.doc.social_media_post_id;
	
	if (!post_id) {
		frappe.msgprint(__('No post ID found. Cannot view post.'));
		return;
	}

	// Convert LinkedIn post ID to URL
	const linkedin_post_id = post_id.replace('urn:li:share:', '');
	const linkedin_url = `https://www.linkedin.com/feed/update/${linkedin_post_id}`;
	
	// Open in new tab
	window.open(linkedin_url, '_blank');
}

function update_social_media_post(frm) {
	// Use the stored post ID
	const post_id = frm.doc.social_media_post_id;
	
	if (!post_id) {
		frappe.msgprint(__('No post ID found. Cannot update post.'));
		return;
	}

	frappe.show_alert({
		message: __('Updating post...'),
		indicator: 'blue'
	});

	frm.call({
		method: 'update_linkedin_post',
		doc: frm.doc,
		freeze: true,
		freeze_message: __('Updating post...')
	}).then(r => {
		if (r.message && r.message.status === 'success') {
			frappe.msgprint({
				title: __('Success'),
				message: __('Post updated successfully!'),
				indicator: 'green'
			});
			frm.reload_doc();
		} else {
			frappe.msgprint({
				title: __('Error'),
				message: r.message.message || __('Failed to update post'),
				indicator: 'red'
			});
		}
	});
}

function delete_social_media_post(frm) {
	frappe.confirm(
		__('Are you sure you want to delete this post from {0}?', [frm.doc.platform]),
		function() {
			frappe.show_alert({
				message: __('Deleting post...'),
				indicator: 'blue'
			});

			frm.call({
				method: 'delete_linkedin_post',
				doc: frm.doc,
				freeze: true,
				freeze_message: __('Deleting post...')
			}).then(r => {
				if (r.message && r.message.status === 'success') {
					frappe.msgprint({
						title: __('Success'),
						message: __('Post deleted successfully!'),
						indicator: 'green'
					});
					frm.reload_doc();
				} else {
					frappe.msgprint({
						title: __('Error'),
						message: r.message.message || __('Failed to delete post'),
						indicator: 'red'
					});
				}
			});
		}
	);
}

function generate_image(frm){
	frappe.prompt([
		{
			fieldname: 'instruction',
			label: __('Instruction'),
			fieldtype: 'Small Text',
			reqd: false,
			description: __('Describe how you want to generate this image')
		}
	], (values) => {
		frappe.show_alert({
			message: __('Generating image for your post...'),
			indicator: 'blue'
		});

		frm.call({ method: 'generate_image', doc: frm.doc, args: { instruction: values.instruction }, freeze: true, freeze_message: __('Generating image for your post...') })
			.then(r => {
				if (r.message && r.message.status === 'success') {
					frappe.msgprint({
						title: __('Success'),
						message: __('Image for your post generated successfully.'),
						indicator: 'green'
					});
					frm.reload_doc();
				} else {
					frappe.msgprint({
						title: __('Error'),
						message: (r.message && (r.message.message || r.message.error)) || __('Failed to image generation'),
						indicator: 'red'
					});
				}
			})
			.catch(err => {
				frappe.msgprint({
					title: __('Error'),
					message: __('An error occurred while revising: {0}', [err.message || err]),
					indicator: 'red'
				});
			});
	});
}

function revise_post(frm){
	frappe.prompt([
		{
			fieldname: 'instruction',
			label: __('Instruction'),
			fieldtype: 'Small Text',
			reqd: true,
			description: __('Describe how you want to revise this post')
		}
	], (values) => {
		frappe.show_alert({
			message: __('Revising post...'),
			indicator: 'blue'
		});

		frm.call({ method: 'revise_post', doc: frm.doc, args: { instruction: values.instruction }, freeze: true, freeze_message: __('Revising post...') })
			.then(r => {
				if (r.message && r.message.status === 'success') {
					frappe.msgprint({
						title: __('Success'),
						message: __('Post revised successfully.'),
						indicator: 'green'
					});
					frm.reload_doc();
				} else {
					frappe.msgprint({
						title: __('Error'),
						message: (r.message && (r.message.message || r.message.error)) || __('Failed to revise post'),
						indicator: 'red'
					});
				}
			})
			.catch(err => {
				frappe.msgprint({
					title: __('Error'),
					message: __('An error occurred while revising: {0}', [err.message || err]),
					indicator: 'red'
				});
			});
	});
}