from urllib.parse import urlencode

from finbyzai.ai.utils.knowledge_base_utils import extract_text_from_source

import frappe
import re
from frappe import _


RESUME_SHARE_TTL_SECONDS = 10 * 60
RESUME_SHARE_CACHE_PREFIX = "resume_share"

def get_agent(fieldname, label):
    """Return the AI Agent configured for the given Content Hub Setting field."""
    agent_name = frappe.db.get_single_value("Content Hub Setting", fieldname)
    if not agent_name:
        frappe.throw(_("Please set {0} in Content Hub Setting.").format(_(label)))

    try:
        return frappe.get_doc("AI Agent", agent_name)
    except frappe.DoesNotExistError:
        frappe.throw(
            _("AI Agent {0} (set as {1} in Content Hub Setting) does not exist.").format(
                agent_name, _(label)
            )
        )


@frappe.whitelist(methods=["POST"])
def extract_skills_from_job_opening(job_opening_name: str):
    """Extract skills from Job Opening using AI Agent.

    Raises on all errors so Frappe's standard error handler returns a proper
    HTTP error response to the frontend instead of a {success: false} dict
    that callers might not check.
    """
    # check before invoking: this writes to the opening and spends AI credits,
    # so it must not be reachable by any authenticated user via GET.
    frappe.has_permission("Job Opening", "write", doc=job_opening_name, throw=True)

    agent = get_agent("job_skills_extractor_agent", "Job Skills Extractor Agent")
    ai_service = agent.agent_service
    job_opening = frappe.get_doc("Job Opening", job_opening_name)

    ai_input = {
        "designation": job_opening.designation or "",
        "small_description": job_opening.small_description or "",
        "description": job_opening.description or "",
        "skills": job_opening.skills or ""
    }

    result = ai_service.invoke(**ai_input)
    required_skills = result.skills
    job_opening.required_skills = []
    for skill in required_skills:
        job_opening.append("required_skills", {"skill": skill})

    job_opening.save()

    return {
        "success": True,
        "message": f"Successfully extracted {len(required_skills)} skills",
        "skills": required_skills
    }


def exponential_weighted_score(
    skill_scores,
    required_skills_order,
    decay: float = 0.95,
):
    """Weighted average over EVERY required skill, not just the ones the AI returned.

    Iterating the AI's response instead of the requirement list let a model that
    replied about one skill out of ten score 100. The requirement list is the
    denominator, so an unanswered skill counts as zero. Unknown (hallucinated)
    skills are ignored, duplicates keep the first response, and scores are
    clamped to 0-100 because the schema's bounds are advisory to the model.

    Skill names are compared case-insensitively so "Python" from the AI and
    "python" in the Job Opening are treated as the same skill.

    decay=0.95 means each subsequent required skill contributes ~5 % less
    than the previous one, prioritising the most important skills.
    """
    by_skill: dict[str, float] = {}
    for skill_data in skill_scores or []:
        skill_name = getattr(skill_data, "skill_name", None)
        score = getattr(skill_data, "score", None)

        if skill_name is None or score is None:
            continue

        # Normalise to lowercase so "Python" and "python" are the same key.
        skill_key = skill_name.strip().lower()

        # First response for a skill wins; later duplicates cannot inflate it.
        if skill_key in by_skill:
            continue

        try:
            score = float(score)
        except (TypeError, ValueError):
            continue

        by_skill[skill_key] = min(max(score, 0.0), 100.0)

    total_weighted_score = 0.0
    total_weight = 0.0

    for position, skill_name in enumerate(required_skills_order):
        weight = decay ** position
        skill_key = skill_name.strip().lower()
        total_weighted_score += by_skill.get(skill_key, 0.0) * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return total_weighted_score / total_weight


def _join_lines(value):
    """Join a list of values into a newline-separated string, or return None."""
    return "\n".join(str(v) for v in value) if value else None


def set_ai_summary(applicant, result):
    """Store the summary fields the agent already returns alongside skill_scores.

    These come back on every invoke at no extra cost, so they are simply mapped
    onto the applicant instead of being discarded. Each is optional in the
    output schema, so missing values fall back to None rather than failing.
    """
    applicant.ai_feedback = getattr(result, "feedback", None)
    applicant.ai_strengths = _join_lines(getattr(result, "strengths", None))
    applicant.ai_missing_skills = _join_lines(getattr(result, "missing_skills", None))
    applicant.ai_overall_score = getattr(result, "overall_score", None)
    applicant.skill_match_percentage = getattr(result, "skill_match_percentage", None)
    applicant.matched_skills_count = getattr(result, "matched_skills_count", None)
    applicant.total_required_skills = getattr(result, "total_required_skills", None)

    # ERPNext/Frappe experience is treated as distinct from generic ERP experience:
    # a candidate who only knows SAP is not an ERPNext hire, and vice versa.
    applicant.erpnext_experiance = 1 if getattr(result, "has_erpnext_experience", False) else 0
    applicant.erp_experiance = 1 if getattr(result, "has_erp_experience", False) else 0


def get_verified_resume_file(applicant):
    """Return the File name only when that File is attached to this applicant.

    The worker runs as Administrator, so an arbitrary path in resume_attachment
    would otherwise be read and shipped to the AI provider. The portal endpoints
    that set this field are Guest-callable, so the value is untrusted input.

    Two url shapes exist. Local storage stores '/private/files/<name>', while
    DFP External Storage (S3) rewrites file_url to '/file/<File name>/<filename>'.
    Matching only on file_url therefore fails on S3 sites, so the File name is
    also read out of the DFP url. Either way the attachment is still verified,
    which is what actually makes this safe.
    """
    resume_url = applicant.resume_attachment
    if not resume_url:
        return None

    candidates = frappe.get_all(
        "File",
        filters={"file_url": resume_url},
        pluck="name",
    )

    # DFP external storage: /file/<File name>/<filename>
    dfp_match = re.match(r"^/file/([^/]+)/", resume_url)
    if dfp_match:
        candidates.append(dfp_match.group(1))

    for file_name in candidates:
        attached = frappe.db.get_value(
            "File", file_name, ["attached_to_doctype", "attached_to_name"], as_dict=True
        )
        if (
            attached
            and attached.attached_to_doctype == "Job Applicant"
            and attached.attached_to_name == applicant.name
        ):
            return file_name

    frappe.log_error(
        "Resume Ranker: resume not attached to this applicant",
        f"{applicant.name} points at {resume_url}, which is not attached to it. Refusing to read.",
    )
    return None


def create_resume_share_url(applicant, file_name):
    """Create a short-lived, one-use URL for an applicant's resume."""
    if not file_name:
        frappe.throw(_("The resume is not attached to this Job Applicant."))

    token = frappe.generate_hash(length=40)
    cache_key = _get_resume_share_cache_key(token)
    payload = frappe.as_json({"file_name": file_name, "applicant_name": applicant.name})
    frappe.cache.set(cache_key, payload, ex=RESUME_SHARE_TTL_SECONDS)

    endpoint = frappe.utils.get_url(
        "/api/method/ai_crm.resume_ranker.api.download_shared_resume"
    )
    return f"{endpoint}?{urlencode({'token': token})}"


@frappe.whitelist(allow_guest=True, methods=["GET"])
def download_shared_resume(token: str):
    """Download a resume through a short-lived, one-use share token."""
    payload = _consume_resume_share_token(token)
    if not payload:
        frappe.throw(_("This resume link is invalid or has expired."), frappe.PermissionError)

    file_doc = frappe.get_doc("File", payload["file_name"])
    if (
        file_doc.attached_to_doctype != "Job Applicant"
        or file_doc.attached_to_name != payload["applicant_name"]
    ):
        frappe.throw(_("This resume link is invalid or has expired."), frappe.PermissionError)

    frappe.local.response.filename = file_doc.file_name
    frappe.local.response.filecontent = file_doc.get_content()
    frappe.local.response.type = "download"


def _get_resume_share_cache_key(token):
    return frappe.cache.make_key(f"{RESUME_SHARE_CACHE_PREFIX}:{token}")


def _consume_resume_share_token(token):
    if not token:
        return None

    cached_payload = frappe.cache.getdel(_get_resume_share_cache_key(token))
    if not cached_payload:
        return None

    return frappe.parse_json(frappe.safe_decode(cached_payload))


def process_applicant_background(applicant_name, job_title=None):
    """Score an applicant's resume. Restores the original session user on exit.

    Applications from the public job portal are owned by Guest, and frappe.enqueue
    runs the job as whoever enqueued it. The worker must verify the attached File
    and create its temporary share URL, so it is elevated only for the duration of
    the run. analyze_candidate can call this inside a web request, hence the restore.
    """
    original_user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        _rank_applicant(applicant_name)
    finally:
        frappe.set_user(original_user)


def _rank_applicant(applicant_name):
    # the opening is read off the applicant, never taken from the caller, so a
    # candidate cannot be scored against an easier set of requirements.
    applicant = frappe.get_doc("Job Applicant", applicant_name)

    if not applicant.job_title:
        frappe.log_error("Resume Ranker: no job opening", f"Job Applicant {applicant_name} has no job_title")
        return

    resume_file_name = get_verified_resume_file(applicant)
    if not resume_file_name:
        return

    job_opening = frappe.get_doc("Job Opening", applicant.job_title)
    skills = [required_skill.skill for required_skill in job_opening.required_skills]
    agent = get_agent("resume_ranker_agent", "Resume Ranker Agent")
    ai_service = agent.agent_service

    # The agent is a plain chain with no fetch tool, so it must be given the
    # resume text itself. Handing it only a URL makes it fabricate a candidate.
    file_doc = frappe.get_doc("File", resume_file_name)
    extraction_result = extract_text_from_source(file_doc.file_url, 'file')
    if not extraction_result.get("success"):
        frappe.log_error(
            "Resume Ranker: could not read resume",
            f"{applicant.name}: {file_doc.file_name} could not be read ({extraction_result.get('error')}).",
        )
        return

    ai_input = {
        "resume_text": extraction_result.get("content"),
        "skills": ','.join(skills)
    }
    
    result = ai_service.invoke(**ai_input)

    if not result:
        frappe.log_error(
            "Resume Ranker: AI Agent returned empty response",
            f"Job Applicant {applicant_name} — agent returned no result.",
        )
        return

    skill_scores = result.skill_scores
    applicant.skill_score = []

    set_ai_summary(applicant, result)

    for skill in skill_scores:
        applicant.append("skill_score", {
            "reason": skill.reason,
            "score": skill.score,
            "skill": skill.skill_name,
        })

    applicant.score = exponential_weighted_score(skill_scores, skills)
    applicant.save(ignore_permissions=True)


def after_insert(doc, method=None):
    # Do NOT guard on doc.resume_attachment here: the careers portal inserts the
    # applicant first and only then saves the resume, so it is still empty at this
    # point. enqueue_after_commit=True means the worker re-reads the applicant
    # after commit, by which time the resume is present; the missing-resume case
    # is handled there.
    if not doc.job_title:
        return

    frappe.enqueue(
        "ai_crm.resume_ranker.api.process_applicant_background",
        queue="long",
        timeout=1200,
        applicant_name=doc.name,
        enqueue_after_commit=True,
    )

@frappe.whitelist(methods=["POST"])
def analyze_candidate(applicant_name: str, job_title: str = None):
    # job_title is accepted but ignored: the opening is derived from the
    # applicant. Kept in the signature so older cached JS keeps working.
    # process_applicant_background elevates to Administrator, so gate the
    # whitelisted entry point on the caller's own permissions.
    frappe.has_permission("Job Applicant", "write", doc=applicant_name, throw=True)
    process_applicant_background(applicant_name)
    return {
        "success": True
    }