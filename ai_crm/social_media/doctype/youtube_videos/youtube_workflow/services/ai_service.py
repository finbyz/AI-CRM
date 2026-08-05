# Copyright (c) 2025, Finbyz Tech Pvt Ltd
# For license information, please see license.txt

"""
AI Service
Handles AI agent interactions for video analysis and post generation
"""

import frappe
import json


def analyze_video(
    agent_service,
    video_title,
    video_transcript,
    relevance_prompt="",
):
    """
    Analyze a video using the AI agent to determine if it's related.
    
    Args:
        agent_service: AI Agent Service instance
        video_title: Video title
        video_transcript: Video transcript text
        
    Returns:
        dict: {
            'success': bool,
            'is_related': int (0 or 1),
            'reasoning': str
        }
    """
    try:
        input_data = {
            "title": video_title or "",
            "transcript": video_transcript or "",
            "relevance_prompt": relevance_prompt or "",
        }
        
        result = agent_service.invoke(**input_data)
        
        # Handle different result formats
        if hasattr(result, 'is_related') and hasattr(result, 'reasoning'):
            # Object with attributes
            return {
                'success': True,
                'is_related': int(result.is_related),
                'reasoning': str(result.reasoning)
            }
        
        elif isinstance(result, dict):
            # Dictionary result
            return {
                'success': True,
                'is_related': int(result.get('is_related', 0)),
                'reasoning': str(result.get('reasoning', ''))
            }
        
        else:
            # Try to parse as JSON string
            parsed = json.loads(str(result))
            return {
                'success': True,
                'is_related': int(parsed.get('is_related', 0)),
                'reasoning': str(parsed.get('reasoning', ''))
            }
            
    except Exception as e:
        frappe.log_error(
            f"Video analysis error: {str(e)}",
            "YouTube AI Analysis"
        )
        return {
            'success': False,
            'is_related': 0,
            'reasoning': f"Analysis failed: {str(e)}"
        }


def generate_social_post(agent_service, video_title, video_transcript):
    """
    Generate a social media post using the AI agent.
    
    Args:
        agent_service: AI Agent Service instance
        video_title: Video title
        video_transcript: Video transcript text
        
    Returns:
        dict: {
            'success': bool,
            'linkedin_post': str
        }
    """
    try:
        input_data = {
            "title": video_title or "",
            "transcript": video_transcript or ""
        }
        
        result = agent_service.invoke(**input_data)
        
        # Handle different result formats
        if hasattr(result, 'content'):
            # Object with attributes
            return {
                'success': True,
                'content': str(result.content)
            }
        
        elif isinstance(result, dict):
            # Dictionary result
            return {
                'success': True,
                'content': str(result.get('content', ''))
            }
        
        else:
            # Try to parse as JSON string
            parsed = json.loads(str(result))
            return {
                'success': True,
                'content': str(parsed.get('content', ''))
            }
            
    except Exception as e:
        frappe.log_error(
            f"Post generation error: {str(e)}",
            "YouTube AI Post Generation"
        )
        return {
            'success': False,
            'content': ''
        }


def get_analysis_agent():
    """
    Get the analysis AI agent from settings.
    
    Returns:
        AI Agent Service instance
    """
    settings = frappe.get_single("YouTube Settings")
    agent_name = settings.analysis_ai_agent
    
    if not agent_name:
        frappe.throw("Analysis AI Agent not configured in YouTube Settings")
    
    agent_doc = frappe.get_doc("AI Agent", agent_name)
    return agent_doc.agent_service
