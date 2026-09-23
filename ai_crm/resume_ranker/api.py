import os
import re
import tempfile

import frappe
from frappe import _

from finbyzai.ai.utils.knowledge_base_utils import (
    extract_csv_to_text,
    extract_docx_to_text,
    extract_excel_to_text,
    extract_pdf_to_text,
    extract_text_from_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_agent(fieldname, label):
    """Return the AI Agent configured in Content Hub Setting for *fieldname*."""
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


def get_verified_resume_file(applicant):
    """Return the File name only when that File is confirmed attached to this applicant.

    The worker runs as Administrator, so an arbitrary path in resume_attachment
    would otherwise be read and shipped to the AI provider — the portal endpoints
    that set this field are Guest-callable, making it untrusted input.

    Two URL shapes exist:
      Local storage:         /private/files/<filename>
      DFP External Storage:  /file/<File name>/<filename>
    """
    resume_url = applicant.resume_attachment
    if not resume_url:
        return None

    candidates = frappe.get_all("File", filters={"file_url": resume_url}, pluck="name")

    # DFP / S3 external storage rewrites file_url to /file/<File name>/<filename>
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
        f"{applicant.name} points at {resume_url!r}, which is not attached to it.",
    )
    return None


def _read_resume_text(file_doc):
    """Extract plain text from a resume File doc.

    Uses file_doc.get_content() so that private local files and S3/DFP
    external-storage files are both resolved correctly, then writes the
    bytes to a temporary file for the matching format extractor.
    """
    try:
        content_bytes = file_doc.get_content()
    except Exception as exc:
        frappe.log_error(
            "Resume Ranker: could not read resume bytes",
            f"{file_doc.name} ({file_doc.file_name}): {exc}",
        )
        return None

    suffix = os.path.splitext(file_doc.file_name)[-1] or ".pdf"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content_bytes)
            tmp_path = tmp.name
        success, content, error = _extract_text_from_local_file(tmp_path, suffix)
        result = {"success": success, "content": content, "error": error}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not result.get("success"):
        frappe.log_error(
            "Resume Ranker: could not extract text from resume",
            f"{file_doc.name} ({file_doc.file_name}): {result.get('error')}",
        )
        return None

    return result.get("content")


def _extract_text_from_local_file(file_path, suffix):
    extractors = {
        ".csv": extract_csv_to_text,
        ".docx": extract_docx_to_text,
        ".pdf": extract_pdf_to_text,
        ".txt": extract_text_from_file,
        ".xls": extract_excel_to_text,
        ".xlsx": extract_excel_to_text,
    }
    extractor = extractors.get(suffix.lower())
    if not extractor:
        return False, None, f"Unsupported file type: {suffix.lower()}"

    return extractor(file_path)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def exponential_weighted_score(skill_scores, required_skills_order, decay: float = 0.95):
    """Weighted average over every required skill.

    The requirement list is the denominator, so an unanswered or hallucinated
    skill counts as zero. Duplicates keep the first response. Scores are clamped
    to [0, 100]. decay=0.95 gives each subsequent required skill ~5 % less
    weight, prioritising the most important skills at the top of the list.
    """
    by_skill: dict[str, float] = {}
    for item in skill_scores or []:
        name = getattr(item, "skill_name", None)
        score = getattr(item, "score", None)
        if name is None or score is None:
            continue
        key = name.strip().lower()
        if key in by_skill:
            continue  # first response wins; duplicates cannot inflate score
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        by_skill[key] = min(max(score, 0.0), 100.0)

    total_score = total_weight = 0.0
    for position, skill_name in enumerate(required_skills_order):
        weight = decay ** position
        total_score += by_skill.get(skill_name.strip().lower(), 0.0) * weight
        total_weight += weight

    return (total_score / total_weight) if total_weight else 0.0



def set_ai_summary(applicant, result):
    """Map all summary fields from the agent result onto the applicant doc."""
    applicant.ai_feedback            = getattr(result, "feedback", None)
    applicant.ai_overall_score       = getattr(result, "overall_score", None)
    applicant.skill_match_percentage = getattr(result, "skill_match_percentage", None)
    applicant.matched_skills_count   = getattr(result, "matched_skills_count", None)
    applicant.total_required_skills  = getattr(result, "total_required_skills", None)
    # ERPNext experience is distinct from generic ERP (SAP ≠ ERPNext hire)
    applicant.erpnext_experiance = 1 if getattr(result, "has_erpnext_experience", False) else 0
    applicant.erp_experiance     = 1 if getattr(result, "has_erp_experience", False) else 0


# ---------------------------------------------------------------------------
# Core ranking
# ---------------------------------------------------------------------------

def _rank_applicant(applicant_name):
    applicant = frappe.get_doc("Job Applicant", applicant_name)

    if not applicant.job_title:
        frappe.log_error(
            "Resume Ranker: no job opening",
            f"Job Applicant {applicant_name} has no job_title.",
        )
        return

    resume_file_name = get_verified_resume_file(applicant)
    if not resume_file_name:
        return

    job_opening = frappe.get_doc("Job Opening", applicant.job_title)
    skills = [row.skill for row in job_opening.required_skills]

    if not skills:
        frappe.log_error(
            "Resume Ranker: no required skills",
            f"Job Opening {job_opening.name} has no required_skills. "
            "Run skill extraction on the opening before ranking applicants.",
        )
        return

    resume_text = _read_resume_text(frappe.get_doc("File", resume_file_name))
    if not resume_text:
        return

    agent = get_agent("resume_ranker_agent", "Resume Ranker Agent")
    result = agent.agent_service.invoke(
        resume_text=resume_text,
        skills=",".join(skills),
    )

    if not result:
        frappe.log_error(
            "Resume Ranker: empty AI response",
            f"Job Applicant {applicant_name} — agent returned no result.",
        )
        return

    set_ai_summary(applicant, result)

    applicant.skill_score = []
    for skill in result.skill_scores or []:
        applicant.append("skill_score", {
            "skill":  skill.skill_name,
            "score":  skill.score,
            "reason": skill.reason,
        })

    applicant.score = exponential_weighted_score(result.skill_scores, skills)
    applicant.save(ignore_permissions=True)


def process_applicant_background(applicant_name):
    """Background-worker entry point. Elevates to Administrator for the run."""
    original_user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        _rank_applicant(applicant_name)
    finally:
        frappe.set_user(original_user)


def _enqueue_ranking(applicant_name):
    frappe.enqueue(
        "ai_crm.resume_ranker.api.process_applicant_background",
        queue="long",
        timeout=1200,
        applicant_name=applicant_name,
        enqueue_after_commit=True,
    )


# ---------------------------------------------------------------------------
# Document hooks
# ---------------------------------------------------------------------------

def on_update_enqueue_if_resume_added(doc, method=None):
    """Enqueue ranking when a resume is first added to a Job Applicant."""
    if not doc.resume_attachment or not doc.job_title:
        return

    before = doc.get_doc_before_save()
    if before and before.resume_attachment:
        return

    _enqueue_ranking(doc.name)


# ---------------------------------------------------------------------------
# Whitelisted API
# ---------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def extract_skills_from_job_opening(job_opening_name: str):
    """Extract required skills from a Job Opening using the configured AI agent."""
    frappe.has_permission("Job Opening", "write", doc=job_opening_name, throw=True)

    agent = get_agent("job_skills_extractor_agent", "Job Skills Extractor Agent")
    job_opening = frappe.get_doc("Job Opening", job_opening_name)

    result = agent.agent_service.invoke(
        designation=job_opening.designation or "",
        small_description=job_opening.small_description or "",
        description=job_opening.description or "",
        skills=job_opening.skills or "",
    )

    required_skills = result.skills
    job_opening.required_skills = []
    for skill in required_skills:
        job_opening.append("required_skills", {"skill": skill})
    job_opening.save()

    return {
        "success": True,
        "message": f"Successfully extracted {len(required_skills)} skills",
        "skills": required_skills,
    }


@frappe.whitelist(methods=["POST"])
def analyze_candidate(applicant_name: str, job_title: str = None):
    """Manually trigger resume ranking for a Job Applicant.

    job_title is accepted but intentionally ignored — the opening is always
    derived from the applicant to prevent scoring against a different (easier)
    set of requirements.
    """
    frappe.has_permission("Job Applicant", "write", doc=applicant_name, throw=True)
    process_applicant_background(applicant_name)
    return {"success": True}
