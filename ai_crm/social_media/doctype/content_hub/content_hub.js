const RESEARCH_RUNNING = ["Queued", "Researching"];

frappe.ui.form.on("Content Hub", {
	refresh(frm) {
		if (frm.is_new()) return;

		const running = RESEARCH_RUNNING.includes(frm.doc.research_status);
		const researched = frm.doc.research_status === "Completed";

		const research_button = frm.add_custom_button(
			researched ? __("Redo Research") : __("Do Research"),
			() => start_research(frm)
		);
		research_button.prop("disabled", running);
		research_button.toggleClass("btn-primary", !researched && !running);

		const generate_button = frm.add_custom_button(__("Generate"), () => open_generate_dialog(frm));
		generate_button.toggleClass("btn-primary", researched);

		if (running) {
			frm.dashboard.set_headline(
				__("Researching this topic on the web. You will get a message when it is ready."),
				"blue"
			);
		}
	},
});

async function start_research(frm) {
	if (frm.doc.research_status === "Completed") {
		const confirmed = await new Promise((resolve) =>
			frappe.confirm(__("Replace the current research notes with a fresh web research?"), () =>
				resolve(true), () => resolve(false))
		);
		if (!confirmed) return;
	}
	if (frm.is_dirty()) await frm.save();

	await frm.call({ doc: frm.doc, method: "start_research", freeze: true });
	await frm.reload_doc();
	frappe.show_alert({ message: __("Research started"), indicator: "blue" });
}

function open_generate_dialog(frm) {
	const is_social = "eval:doc.output_type=='Social Media Post'";
	const dialog = new frappe.ui.Dialog({
		title: __("Generate"),
		fields: [
			{
				fieldname: "output_type",
				fieldtype: "Select",
				label: __("What to generate"),
				options: frappe.boot.versions?.finbyzweb
					? ["Social Media Post", "Web Page", "Blog Post"]
					: ["Social Media Post"],
				default: "Social Media Post",
				reqd: 1,
			},
			{
				fieldname: "coming_soon",
				fieldtype: "HTML",
				depends_on: "eval:doc.output_type!='Social Media Post'",
				options: `<p class="text-muted">${__(
					"Opens a new NextJS Page with the full research notes as its content, under a fresh title of our own (saved in Page Title, never the YouTube title). Review and save it, then use Generate SEO, Generate FAQs and Generate Page there."
				)}</p>`,
			},
			{
				fieldname: "research_note",
				fieldtype: "HTML",
				options: frm.doc.research
					? ""
					: `<p class="text-warning">${__(
							"No research yet. Click Do Research first. Posts can still be written from the source, but web pages need the research."
					  )}</p>`,
			},
			{
				fieldname: "linkedin_account",
				fieldtype: "Link",
				label: __("LinkedIn Account"),
				options: "LinkedIn Integration",
				depends_on: is_social,
			},
			{
				fieldname: "twitter_account",
				fieldtype: "Link",
				label: __("X (Twitter) Account"),
				options: "Twitter Integration",
				depends_on: is_social,
			},
			{
				fieldname: "reddit_account",
				fieldtype: "Link",
				label: __("Reddit Account"),
				options: "Reddit Integration",
				depends_on: is_social,
			},
			{
				fieldname: "subreddit",
				fieldtype: "Data",
				label: __("Subreddit"),
				depends_on: "eval:doc.output_type=='Social Media Post' && doc.reddit_account",
				mandatory_depends_on: "eval:doc.output_type=='Social Media Post' && doc.reddit_account",
			},
			{
				fieldname: "instruction",
				fieldtype: "Small Text",
				label: __("Angle or Instructions (optional)"),
				depends_on: is_social,
			},
		],
		primary_action_label: __("Generate"),
		primary_action: (values) => generate(frm, dialog, values),
	});
	dialog.show();
}

async function generate(frm, dialog, values) {
	if (values.output_type !== "Social Media Post") {
		const response = await frm.call({
			doc: frm.doc,
			method: "draft_web_page",
			args: { output_type: values.output_type },
			freeze: true,
			freeze_message: __("Writing a fresh title..."),
		});
		if (!response.message) return;
		dialog.hide();
		frappe.new_doc("NextJS Page", response.message);
		return;
	}

	const targets = get_selected_targets(values);
	if (!targets.length) {
		frappe.msgprint(__("Select at least one social media account."));
		return;
	}

	dialog.disable_primary_action();
	try {
		const response = await frm.call({
			doc: frm.doc,
			method: "generate_social_posts",
			args: { targets, instruction: values.instruction },
			freeze: true,
			freeze_message: __("Queueing post generation..."),
		});
		dialog.hide();
		const posts = response.message?.posts || [];
		const url =
			posts.length === 1
				? frappe.utils.get_form_link("Social Media Post", posts[0])
				: `/app/social-media-post?content_hub=${encodeURIComponent(frm.doc.name)}`;
		frappe.show_alert(
			{
				message: __("{0} post(s) queued. {1}", [
					posts.length,
					`<a href="${url}">${posts.length === 1 ? __("Open post") : __("View posts")}</a>`,
				]),
				indicator: "green",
			},
			10
		);
	} finally {
		dialog.enable_primary_action();
	}
}

function get_selected_targets(values) {
	return [
		{ credential_type: "LinkedIn Integration", credential: values.linkedin_account },
		{ credential_type: "Twitter Integration", credential: values.twitter_account },
		{
			credential_type: "Reddit Integration",
			credential: values.reddit_account,
			subreddit: values.subreddit?.trim(),
		},
	].filter((target) => target.credential);
}
