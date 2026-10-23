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
					"Creates a NextJS Page from the full research under a fresh title of our own (saved in Page Title), then fills its SEO, FAQs, related links and schema. It stays unpublished until you click Generate Page there."
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
		dialog.hide();
		if (frm.is_dirty()) await frm.save();
		build_web_page(frm, values.output_type);
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

const NEXTJS_API = "finbyzweb.nextjs_web.doctype.nextjs_page.nextjs_page.";
// Order matters: Related Links reads the SEO fields, and the FAQ schema syncs when FAQs are saved.
// Related Links is ours: finbyzweb's agent has no list of real pages, so it guesses routes.
const PAGE_STEPS = [
	{ label: __("SEO title, description and keywords"), method: "generate_seo" },
	{ label: __("FAQs"), method: "generate_faqs" },
	{ label: __("Related links"), method: "ai_crm.social_media.doctype.content_hub.content_hub.find_related_pages", arg: "page_name" },
	{ label: __("Schema (JSON-LD)"), method: "generate_schema" },
];

async function build_web_page(frm, output_type) {
	const steps = [{ label: __("Create page with a fresh title and the research") }, ...PAGE_STEPS];
	const states = steps.map(() => ({ status: "pending" }));
	let page = null;

	const dialog = new frappe.ui.Dialog({
		title: __("Building {0}", [output_type]),
		fields: [{ fieldname: "progress", fieldtype: "HTML" }],
		primary_action_label: __("Open Page"),
		primary_action: () => {
			dialog.hide();
			frappe.set_route("Form", "NextJS Page", page.name);
		},
	});
	dialog.get_close_btn().hide();
	dialog.get_primary_btn().hide();
	dialog.show();

	const render = () => {
		dialog.fields_dict.progress.$wrapper.html(`
			<div class="content-hub-steps">
				${steps.map((step, i) => render_step(step, states[i])).join("")}
			</div>
			${page ? `<p class="text-muted small mt-3">${__(
				"Review the page, then click Generate Page there to publish it on the website."
			)}</p>` : ""}`);
	};

	const run = async (i, call) => {
		states[i] = { status: "running" };
		render();
		try {
			const response = await call();
			const failed = response && response.success === false;
			states[i] = { status: failed ? "skipped" : "done", message: failed ? response.message : "" };
			return response;
		} catch (error) {
			states[i] = { status: "failed", message: __("Failed. You can run it again from the page.") };
		} finally {
			render();
		}
	};

	page = await run(0, () =>
		frm.call({ doc: frm.doc, method: "create_web_page", args: { output_type } }).then((r) => r.message)
	);

	if (!page) {
		steps.slice(1).forEach((_step, i) => (states[i + 1] = { status: "skipped", message: __("Page was not created") }));
		render();
		dialog.get_close_btn().show();
		return;
	}
	states[0].message = page.title;

	for (const [i, step] of PAGE_STEPS.entries()) {
		const method = step.method.includes(".") ? step.method : NEXTJS_API + step.method;
		await run(i + 1, () => frappe.xcall(method, { [step.arg || "doc_name"]: page.name }));
	}

	frm.reload_doc();
	dialog.set_title(__("{0} ready", [output_type]));
	dialog.get_close_btn().show();
	dialog.get_primary_btn().show();
}

function render_step(step, state) {
	const icons = {
		pending: `<span class="text-muted">○</span>`,
		running: `<span class="spinner-border spinner-border-sm text-primary" role="status"></span>`,
		done: `<span class="text-success">✓</span>`,
		skipped: `<span class="text-warning">!</span>`,
		failed: `<span class="text-danger">✕</span>`,
	};
	const message = state.message
		? `<div class="text-muted small">${frappe.utils.escape_html(state.message)}</div>`
		: "";
	return `
		<div class="d-flex align-items-start mb-3">
			<div style="width: 24px">${icons[state.status]}</div>
			<div class="${state.status === "pending" ? "text-muted" : ""}">${step.label}${message}</div>
		</div>`;
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
