"""FastAPI backend for Auto Apply Job."""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

app = FastAPI(
    title="Auto Apply Job API",
    description="Backend API for job application automation",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Models
# =============================================================================


class ApplicationRequest(BaseModel):
    """Request model for job application."""
    job_url: str
    resume_path: Optional[str] = None


class DiscoveryRequest(BaseModel):
    """Request model for job discovery."""
    query: str
    location: Optional[str] = None
    portal: Optional[str] = "linkedin"
    max_results: Optional[int] = 25


class QuestionMemoryItem(BaseModel):
    """Model for question memory item."""
    question: str
    answer: str
    source: Optional[str] = "api"


class SettingsUpdate(BaseModel):
    """Model for settings update."""
    require_verified_company: Optional[bool] = None
    daily_application_target: Optional[int] = None
    verified_company_allowlist: Optional[str] = None


class ApplicationStatus(BaseModel):
    """Model for application status response."""
    id: Optional[str] = None
    timestamp: Optional[str] = None
    status: str
    url: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    verified: Optional[bool] = None
    reason: Optional[str] = None


# =============================================================================
# Background Tasks
# =============================================================================


async def run_application_task(job_url: str, resume_path: str) -> bool:
    """Background task to run application agent."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agent import run_application_agent
    return await run_application_agent(job_url, resume_path)


def run_docs_task(job_url: str, resume_path: str) -> bool:
    """Background task to generate documents only."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from documents import fetch_job_posting_context, generate_application_documents
    from config import get_candidate_profile
    from pathlib import Path

    job_context = fetch_job_posting_context(job_url)
    candidate_profile = get_candidate_profile()
    artifacts = generate_application_documents(job_context, Path(resume_path), candidate_profile)
    return bool(artifacts.get("interview_prep_path"))


# =============================================================================
# Health Check
# =============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# =============================================================================
# Dashboard Endpoints
# =============================================================================


@app.get("/api/applications")
async def list_applications(limit: int = 50):
    """List recent application events."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from storage import list_recent_application_events

    events = list_recent_application_events(limit=limit)
    return {"applications": events, "count": len(events)}


@app.get("/api/applications/daily-progress")
async def get_daily_progress():
    """Get daily application progress."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from storage import count_successful_applications_today
    from config import get_daily_application_target

    successes = count_successful_applications_today()
    target = get_daily_application_target()
    return {
        "successful": successes,
        "target": target,
        "remaining": max(target - successes, 0),
        "complete": successes >= target,
    }


@app.get("/api/applications/{application_id}")
async def get_application(application_id: int):
    """Get specific application details."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from storage import list_recent_application_events

    events = list_recent_application_events(limit=1000)
    for event in events:
        if event.get("id") == application_id or str(event.get("timestamp")) == application_id:
            return event

    raise HTTPException(status_code=404, detail="Application not found")


# =============================================================================
# Discovery Endpoints
# =============================================================================


@app.post("/api/discover")
async def discover_jobs(request: DiscoveryRequest):
    """Discover jobs from portals."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from discovery import discover_job_urls
    from documents import fetch_job_posting_context, classify_company_verification, score_job_context, extract_resume_text
    from config import get_candidate_profile, get_resume_path

    try:
        job_urls = discover_job_urls(
            request.query,
            request.location or "",
            portal=request.portal,
            max_results=request.max_results,
        )

        # Enrich with basic info
        results = []
        resume_path = request.resume_path or get_resume_path()
        resume_text = ""

        try:
            resume_text = extract_resume_text(Path(resume_path))
        except Exception:
            pass

        candidate_profile = get_candidate_profile()

        for url in job_urls[:request.max_results]:
            try:
                job_context = fetch_job_posting_context(url)
                verified, verification_source = classify_company_verification(job_context)
                job_context["verified"] = verified
                job_context["verification_source"] = verification_source

                score = 0
                reasons = []
                if resume_text:
                    score, reasons = score_job_context(job_context, resume_text, candidate_profile)

                results.append({
                    "url": url,
                    "company_name": job_context["company_name"],
                    "job_title": job_context["job_title"],
                    "verified": verified,
                    "score": score,
                    "reasons": reasons[:3],
                })
            except Exception:
                results.append({
                    "url": url,
                    "company_name": "Unknown",
                    "job_title": "Unknown",
                    "verified": False,
                    "score": -1,
                    "reasons": ["Could not fetch job details"],
                })

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)

        return {
            "discovered": len(job_urls),
            "jobs": results,
            "query": request.query,
            "location": request.location,
            "portal": request.portal,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")


@app.post("/api/discover/ranked")
async def discover_ranked_jobs(request: DiscoveryRequest):
    """Discover and rank jobs."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from discovery import load_job_urls, discover_job_urls
    from documents import rank_job_urls_from_contexts
    from config import get_resume_path

    try:
        job_urls = discover_job_urls(
            request.query,
            request.location or "",
            portal=request.portal,
            max_results=request.max_results,
        )

        resume_path = request.resume_path or get_resume_path()
        ranked = rank_job_urls_from_contexts(job_urls, resume_path)

        return {
            "discovered": len(job_urls),
            "ranked": ranked,
            "selected_count": min(5, len([j for j in ranked if j.get("eligible")])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ranking failed: {str(e)}")


# =============================================================================
# Document Generation Endpoints
# =============================================================================


@app.post("/api/documents/generate")
async def generate_documents(request: ApplicationRequest, background_tasks: BackgroundTasks):
    """Generate application documents for a job."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import get_resume_path

    resume_path = request.resume_path or get_resume_path()

    try:
        success = run_docs_task(request.job_url, resume_path)
        if success:
            return {"status": "success", "message": "Documents generated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Document generation failed")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Application Endpoints
# =============================================================================


@app.post("/api/apply")
async def apply_to_job(request: ApplicationRequest, background_tasks: BackgroundTasks):
    """Submit job application via browser agent."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import get_resume_path

    resume_path = request.resume_path or get_resume_path()

    # Queue the application as a background task
    background_tasks.add_task(run_application_task, request.job_url, resume_path)

    return {
        "status": "queued",
        "job_url": request.job_url,
        "message": "Application has been queued for processing",
    }


@app.post("/api/apply/sync")
async def apply_to_job_sync(request: ApplicationRequest):
    """Submit job application synchronously (for testing)."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import get_resume_path

    resume_path = request.resume_path or get_resume_path()

    try:
        success = await run_application_task(request.job_url, resume_path)
        if success:
            return {"status": "success", "job_url": request.job_url}
        else:
            raise HTTPException(status_code=500, detail="Application failed")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Question Memory Endpoints
# =============================================================================


@app.get("/api/memory")
async def list_question_memory():
    """List all saved screening answers."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from storage import load_question_memory

    memory = load_question_memory()
    return {
        "questions": list(memory.values()),
        "count": len(memory),
    }


@app.post("/api/memory")
async def save_question_memory(item: QuestionMemoryItem):
    """Save a screening answer."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from storage import save_question_memory as save_memory

    if not item.question.strip() or not item.answer.strip():
        raise HTTPException(status_code=400, detail="Question and answer are required")

    save_memory(item.question, item.answer, source=item.source or "api")
    return {"status": "saved", "question": item.question}


@app.delete("/api/memory/{question_hash}")
async def delete_question_memory(question_hash: str):
    """Delete a screening answer (not implemented in storage layer)."""
    raise HTTPException(status_code=501, detail="Delete not implemented")


# =============================================================================
# Settings Endpoints
# =============================================================================


@app.get("/api/settings")
async def get_settings():
    """Get current settings."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import (
        get_candidate_profile,
        get_daily_application_target,
        get_preferred_role_keywords,
        get_preferred_location_keywords,
        require_verified_company,
        get_verified_company_allowlist,
    )
    import os

    return {
        "candidate_profile": get_candidate_profile(),
        "daily_target": get_daily_application_target(),
        "require_verified_company": require_verified_company(),
        "verified_allowlist": list(get_verified_company_allowlist()),
        "preferred_roles": get_preferred_role_keywords(),
        "preferred_locations": get_preferred_location_keywords(),
        "job_search_portal": os.getenv("JOB_SEARCH_PORTAL", "linkedin"),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        "fallback_model": os.getenv("FALLBACK_LLM_MODEL", "qwen2.5:3b"),
    }


# =============================================================================
# Candidate Profile Endpoints
# =============================================================================


@app.get("/api/candidate")
async def get_candidate():
    """Get candidate profile."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import get_candidate_profile

    return get_candidate_profile()


# =============================================================================
# Application Entry
# =============================================================================


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
