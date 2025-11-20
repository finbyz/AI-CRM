from finbyzai.ai.utils.knowledge_base_utils import extract_text_from_source
import frappe
from frappe import _
import os

@frappe.whitelist()
def extract_skills_from_job_opening(job_opening_name):
    """Extract skills from Job Opening using AI Agent"""
    try:  
        agent = frappe.get_doc("AI Agent", "Job Skills Extractor")
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
     
    except Exception as e:
        frappe.log_error(f"Skill Extraction Error: {str(e)}", "extract_skills_from_job_opening")
        return {
            "success": False,
            "message": f"Skill extraction failed: {str(e)}"
        }


def process_applicant_background(applicant_name, job_title, resume_path):
    job_opening = frappe.get_doc("Job Opening", job_title)
    skills = [required_skill.skill for required_skill in job_opening.required_skills]
    agent = frappe.get_doc("AI Agent", "AI Resume Ranker")
    ai_service = agent.agent_service
    applicant = frappe.get_doc("Job Applicant", applicant_name)

    extraction_result = extract_text_from_source(applicant.resume_attachment, 'file')
    if not extraction_result.get("success"):
        frappe.log_error("Resume Text extraction error",f"Not able to extract text from {applicant.resume_attachment}")
        return
    
    ai_input = {
        "resume_text": extraction_result.get("content"),
        "skills": ','.join(skills)
    }
    
    result = ai_service.invoke(**ai_input)

    if not result:
        frappe.throw("AI Agent returned empty response")
    
    skill_scores = result.skill_scores
    applicant.skill_score = []  
    total_score = 0 
    valid_scores = 0 
    
    for skill in skill_scores:
        score_value = skill.score 
        
        applicant.append("skill_score", {  
            'reason': skill.reason,
            'score': score_value,  
            'skill': skill.skill_name
        })
        total_score += score_value  
        valid_scores += 1  
    
    if valid_scores > 0:  
        applicant.score = total_score / valid_scores  
    else:  
        applicant.score = 0 
        
    applicant.save()

def process_new_applicant(doc, method=None):
    if not doc.resume_attachment or not doc.job_title:
        return
    
    frappe.enqueue(
        'ai_crm.resume_ranker.api.process_applicant_background',
        queue='default',
        timeout=300,
        applicant_name=doc.name,
        job_title=doc.job_title,
        resume_path=doc.resume_attachment,
        enqueue_after_commit=True
    )

def get_file_path(file_path):
    """Find resume file in different locations"""
    filename = os.path.basename(file_path)

    possible_paths = [
        frappe.get_site_path('private', 'files', filename),
        frappe.get_site_path('public', 'files', filename),
        frappe.get_site_path('private', file_path.lstrip(
            '/').replace('private/', '')),
        frappe.get_site_path('public', file_path.lstrip('/')),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    frappe.logger().error(f" Resume not found")
    return None

@frappe.whitelist(methods=["POST"])
def analyze_candidate(applicant_name, job_title, resume_path):
    process_applicant_background(applicant_name, job_title, resume_path)
    return {
        "success": True
    }