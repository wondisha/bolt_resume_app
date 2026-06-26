"""Document generation module for Auto Apply Job."""

import html
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from config import (
    ARTIFACTS_ROOT,
    VERIFIED_MARKERS,
    get_candidate_profile,
    get_document_job_char_limit,
    get_document_max_tokens,
    get_document_model,
    get_document_resume_char_limit,
    get_preferred_location_keywords,
    get_preferred_role_keywords,
    should_generate_interview_prep_only,
    get_preferred_location_keywords,
    get_preferred_role_keywords,
)


# =============================================================================
# HTML Processing
# =============================================================================


def strip_html_tags(html_text: str) -> str:
    """Strip HTML tags from text."""
    without_scripts = re.sub(r"<script.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    without_styles = re.sub(r"<style.*?</style>", " ", without_scripts, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_styles)
    normalized = html.unescape(re.sub(r"\s+", " ", without_tags)).strip()
    return normalized


def slugify(value: str) -> str:
    """Convert string to URL-safe slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "job"


# =============================================================================
# Job Context Extraction
# =============================================================================


def extract_job_identity(title_text: str) -> tuple[str, str]:
    """Extract company name and job title from page title."""
    stripped_title = title_text.strip()
    if " hiring " in stripped_title and " | LinkedIn" in stripped_title:
        company_name, remainder = stripped_title.split(" hiring ", 1)
        job_title = remainder.rsplit(" | LinkedIn", 1)[0]
        if " in " in job_title:
            job_title = job_title.rsplit(" in ", 1)[0]
        return company_name.strip(), job_title.strip()

    cleaned_title = stripped_title.rsplit("|", 1)[0].strip()
    return "Unknown Company", cleaned_title


def fetch_job_posting_context(job_url: str) -> dict:
    """Fetch and parse job posting page."""
    response = requests.get(job_url, headers={"User-Agent": "Mozilla/5.0 (compatible; JobDiscovery/1.0)"}, timeout=30)
    response.raise_for_status()

    html_text = response.text
    title_match = re.search(r"<title>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    description_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    title_text = html.unescape(title_match.group(1)).strip() if title_match else job_url
    description_text = html.unescape(description_match.group(1)).strip() if description_match else ""
    company_name, job_title = extract_job_identity(title_text)
    page_text = strip_html_tags(html_text)

    return {
        "url": job_url,
        "page_title": title_text,
        "job_title": job_title,
        "company_name": company_name,
        "description": description_text,
        "page_text": page_text[:12000],
        "page_html": html_text[:12000],
    }


def classify_company_verification(job_context: dict) -> tuple[bool, str]:
    """Check if company is verified."""
    from config import get_verified_company_allowlist

    allowlist = get_verified_company_allowlist()
    company_name = job_context["company_name"].strip().lower()

    if company_name and company_name in allowlist:
        return True, "allowlist"

    combined_text = f"{job_context['page_title']}\n{job_context['description']}\n{job_context['page_text']}\n{job_context['page_html']}".lower()
    for marker in VERIFIED_MARKERS:
        if marker in combined_text:
            return True, f"marker:{marker}"

    return False, "no verified marker found"


# =============================================================================
# Resume Handling
# =============================================================================


def extract_resume_text(resume_path: Path) -> str:
    """Extract text from resume PDF."""
    from pypdf import PdfReader

    reader = PdfReader(str(resume_path))
    extracted_pages = [(page.extract_text() or "").strip() for page in reader.pages]
    resume_text = "\n\n".join(page for page in extracted_pages if page)
    if not resume_text.strip():
        raise ValueError(f"Could not extract text from resume PDF: {resume_path}")
    return resume_text


def extract_resume_keywords(resume_text: str) -> list[str]:
    """Extract keywords from resume for matching."""
    candidate_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9\+#\.\-/]{2,}", resume_text.lower())
    stopwords = {
        "with", "from", "that", "this", "have", "your", "will", "team", "role", "years", "using",
        "into", "such", "than", "their", "about", "work", "data", "engineer", "manager", "senior",
    }
    keywords = []
    seen = set()
    for term in candidate_terms:
        if term in stopwords or term in seen:
            continue
        seen.add(term)
        keywords.append(term)
        if len(keywords) >= 40:
            break
    return keywords


# =============================================================================
# Job Scoring
# =============================================================================


def normalize_text(value: str) -> str:
    """Normalize text for comparison."""
    return re.sub(r"\s+", " ", value.lower()).strip()


def count_keyword_hits(text: str, keywords: list[str]) -> list[str]:
    """Count keyword hits in text."""
    normalized = normalize_text(text)
    hits = []
    for keyword in keywords:
        lowered = normalize_text(keyword)
        if lowered and lowered in normalized:
            hits.append(keyword)
    return hits


def extract_priority_job_keywords(job_context: dict) -> list[str]:
    """Extract priority keywords from job posting."""
    combined_text = "\n".join(
        [job_context.get("job_title", ""), job_context.get("description", ""), job_context.get("page_text", "")[:4000]]
    ).lower()
    candidate_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9\+#\./-]{2,}", combined_text)
    stopwords = {
        "with", "from", "that", "this", "have", "your", "will", "team", "role", "years", "using",
        "into", "such", "than", "their", "about", "work", "data", "engineer", "manager", "senior",
        "experience", "required", "preferred", "strong", "including", "support", "design", "build",
    }
    keywords = []
    seen = set()
    for term in candidate_terms:
        if term in stopwords or term in seen:
            continue
        seen.add(term)
        keywords.append(term)
        if len(keywords) >= 60:
            break
    return keywords


def score_job_context(job_context: dict, resume_text: str, candidate_profile: dict) -> tuple[int, list[str]]:
    """Score job fit and return score with reasons."""
    combined_text = "\n".join(
        [job_context["page_title"], job_context["job_title"], job_context["description"], job_context["page_text"][:3000]]
    )
    score = 0
    reasons = []

    role_hits = count_keyword_hits(combined_text, get_preferred_role_keywords())
    if role_hits:
        score += 25 * len(role_hits)
        reasons.append(f"role matches: {', '.join(role_hits[:4])}")

    location_hits = count_keyword_hits(combined_text, get_preferred_location_keywords())
    if location_hits:
        score += 12 * len(location_hits)
        reasons.append(f"location matches: {', '.join(location_hits[:3])}")

    resume_hits = count_keyword_hits(combined_text, extract_resume_keywords(resume_text))
    if resume_hits:
        score += min(len(resume_hits), 10) * 4
        reasons.append(f"resume overlap: {', '.join(resume_hits[:5])}")

    eligibility_markers = (
        "green card",
        "u.s. citizens",
        "citizens only",
        "no sponsorship",
        "no opt",
    )
    eligibility_hits = count_keyword_hits(combined_text, list(eligibility_markers))
    if candidate_profile["sponsorship_needed"].strip().lower() == "no" and eligibility_hits:
        score += 10
        reasons.append("eligibility aligned")

    if job_context.get("verified"):
        score += 30
        reasons.append(f"verified via {job_context.get('verification_source')}")

    return score, reasons


# =============================================================================
# Gap Analysis
# =============================================================================


def analyze_resume_gaps(job_context: dict, resume_text: str, candidate_profile: dict) -> dict:
    """Analyze gaps between resume and job requirements."""
    job_keywords = extract_priority_job_keywords(job_context)
    resume_keywords = set(extract_resume_keywords(resume_text))
    preferred_roles = [normalize_text(item) for item in get_preferred_role_keywords()]

    matched_keywords = [keyword for keyword in job_keywords if normalize_text(keyword) in resume_keywords][:15]
    missing_keywords = [keyword for keyword in job_keywords if normalize_text(keyword) not in resume_keywords][:15]
    role_matches = [keyword for keyword in preferred_roles if keyword and keyword in normalize_text(job_context.get("page_text", ""))]

    readiness = "strong"
    if len(missing_keywords) >= 10:
        readiness = "medium"
    if len(missing_keywords) >= 14:
        readiness = "stretch"

    return {
        "readiness": readiness,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "role_matches": role_matches,
        "candidate_location": candidate_profile.get("location"),
    }


def render_gap_analysis_markdown(job_context: dict, gap_analysis: dict) -> str:
    """Render gap analysis as markdown."""
    matched = ", ".join(gap_analysis["matched_keywords"][:10]) or "No strong overlap detected"
    missing = ", ".join(gap_analysis["missing_keywords"][:10]) or "No major missing keywords detected"
    role_matches = ", ".join(gap_analysis["role_matches"][:6]) or "No preferred-role keyword matches recorded"
    return (
        "# Resume Gap Analysis\n\n"
        f"## Role\n- Company: {job_context['company_name']}\n- Title: {job_context['job_title']}\n- Readiness: {gap_analysis['readiness']}\n\n"
        f"## Current Matches\n- {matched}\n\n"
        f"## Likely Gaps To Prepare\n- {missing}\n\n"
        f"## Role Alignment Signals\n- {role_matches}\n"
    )


# =============================================================================
# Follow-Up Messages
# =============================================================================


def render_follow_up_markdown(job_context: dict, candidate_profile: dict) -> str:
    """Render follow-up messages as markdown."""
    recruiter_message = (
        f"Hi, I recently applied for the {job_context['job_title']} role at {job_context['company_name']}. "
        "My background includes Snowflake, SQL, ETL, and production data-platform support, and I would welcome the chance "
        "to discuss how I can contribute. Thank you for your time."
    )
    email_message = (
        f"Subject: Application Follow-Up - {job_context['job_title']}\n\n"
        f"Hello {job_context['company_name']} team,\n\n"
        f"I applied for the {job_context['job_title']} position and wanted to follow up with continued interest. "
        f"I bring experience in database and data-platform engineering, including Snowflake, SQL, ETL, automation, and production support. "
        "If helpful, I would be glad to discuss my background further.\n\n"
        f"Best regards,\n{candidate_profile['first_name']} {candidate_profile['last_name']}\n{candidate_profile['email']}\n{candidate_profile['phone']}"
    )
    return (
        "# Recruiter Follow-Up Pack\n\n"
        "## LinkedIn Message\n"
        f"{recruiter_message}\n\n"
        "## Email Follow-Up\n"
        f"```text\n{email_message}\n```\n"
    )


# =============================================================================
# LLM Generation
# =============================================================================


def generate_ollama_text(prompt: str, model: Optional[str] = None) -> str:
    """Generate text using Ollama API."""
    import os
    model_name = model or get_document_model()
    host = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")

    response = requests.post(
        f"{host}/api/generate",
        json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": get_document_max_tokens()},
        },
        timeout=300,
    )
    response.raise_for_status()
    payload = response.json()
    generated_text = payload.get("response", "").strip()
    if not generated_text:
        raise ValueError("Ollama returned an empty response while generating application materials.")
    return generated_text


# =============================================================================
# Resume HTML Generation
# =============================================================================


def build_contact_html(candidate_profile: dict) -> str:
    """Build contact information HTML."""
    return (
        "<h2>Contact Information</h2>"
        f"<p>Email: {html.escape(candidate_profile['email'])}<br>"
        f"Phone: {html.escape(candidate_profile['phone'])}<br>"
        f"LinkedIn: {html.escape(candidate_profile['linkedin_url'])}<br>"
        f"GitHub: {html.escape(candidate_profile['github_url'])}<br>"
        f"Location: {html.escape(candidate_profile['location'])}</p>"
    )


def wrap_resume_html(document_title: str, contact_html: str, body_html: str) -> str:
    """Wrap resume content in full HTML document."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(document_title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 28px; color: #111827; line-height: 1.45; }}
    h1 {{ font-size: 24px; margin-bottom: 8px; }}
    h2 {{ font-size: 16px; margin-top: 18px; border-bottom: 1px solid #d1d5db; padding-bottom: 4px; }}
    p, li {{ font-size: 11px; }}
    ul {{ padding-left: 18px; }}
  </style>
</head>
<body>
  <h1>{html.escape(document_title)}</h1>
    {contact_html}
  {body_html}
</body>
</html>
"""


def render_resume_pdf_if_available(html_path: Path) -> Optional[Path]:
    """Render HTML to PDF if weasyprint is available."""
    try:
        from weasyprint import HTML
    except ImportError:
        return None

    pdf_path = html_path.with_suffix(".pdf")
    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    return pdf_path


# =============================================================================
# Artifact Paths
# =============================================================================


def build_artifact_paths(job_context: dict) -> dict:
    """Build paths for job artifacts."""
    artifact_dir = ARTIFACTS_ROOT / date.today().isoformat() / slugify(
        f"{job_context['company_name']}-{job_context['job_title']}"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return {
        "artifact_dir": artifact_dir,
        "job_context_path": artifact_dir / "job_context.json",
        "gap_analysis_path": artifact_dir / "gap_analysis.md",
        "follow_up_path": artifact_dir / "follow_up.md",
        "tailored_resume_html_path": artifact_dir / "tailored_resume.html",
        "interview_prep_path": artifact_dir / "interview_prep.md",
    }


# =============================================================================
# Document Generation
# =============================================================================


def generate_application_documents(job_context: dict, resume_path: Path, candidate_profile: dict) -> dict:
    """Generate all application documents for a job."""
    artifact_paths = build_artifact_paths(job_context)
    resume_text = extract_resume_text(resume_path)
    model_name = get_document_model()
    resume_excerpt = resume_text[: get_document_resume_char_limit()]
    job_excerpt = job_context["page_text"][: get_document_job_char_limit()]
    gap_analysis = analyze_resume_gaps(job_context, resume_text, candidate_profile)

    # Save job context
    artifact_paths["job_context_path"].write_text(json.dumps(job_context, indent=2), encoding="utf-8")

    # Save gap analysis
    artifact_paths["gap_analysis_path"].write_text(
        render_gap_analysis_markdown(job_context, gap_analysis),
        encoding="utf-8",
    )

    # Save follow-up pack
    artifact_paths["follow_up_path"].write_text(
        render_follow_up_markdown(job_context, candidate_profile),
        encoding="utf-8",
    )

    # Generate interview prep
    interview_prompt = f"""
Create interview preparation notes in markdown for the following application.
Use only the provided company, role, posting details, candidate profile, and resume text.
Do not invent facts about the candidate. If company specifics are missing, say so.
Include these sections:
1. Role snapshot
2. Likely interview focus areas
3. Eight tailored interview questions with suggested talking points
4. Technical topics to review
5. Candidate stories to prepare based on the resume
6. Questions to ask the interviewer
Keep the whole document compact and practical.

Candidate profile:
{json.dumps(candidate_profile, indent=2)}

Job context:
Company: {job_context['company_name']}
Role: {job_context['job_title']}
Description: {job_context['description']}
Page excerpt: {job_excerpt}

Source resume text:
{resume_excerpt}
""".strip()

    interview_prep_markdown = generate_ollama_text(interview_prompt, model=model_name)
    artifact_paths["interview_prep_path"].write_text(interview_prep_markdown, encoding="utf-8")

    # Generate tailored resume unless interview-prep-only mode
    tailored_resume_pdf_path = None
    if not should_generate_interview_prep_only():
        resume_prompt = f"""
You are tailoring a resume for a specific job application.
Use only facts that appear in the source resume and candidate profile below.
Do not invent employers, degrees, certifications, dates, metrics, or responsibilities.
Do not include contact information in the response.
Do not name a technology unless it appears verbatim in the source resume text, candidate profile, or job title.
Return only an HTML fragment using h2, p, ul, and li tags. No markdown and no code fences.
Focus the wording toward the posted role while keeping it truthful and ATS-friendly.
Keep the result concise: a short summary plus 6 to 10 bullets total.

Candidate profile:
{json.dumps(candidate_profile, indent=2)}

Job context:
Company: {job_context['company_name']}
Role: {job_context['job_title']}
Description: {job_context['description']}
Page excerpt: {job_excerpt}

Source resume text:
{resume_excerpt}
""".strip()

        resume_fragment = generate_ollama_text(resume_prompt, model=model_name)
        tailored_resume_html = wrap_resume_html(
            f"{job_context['company_name']} - {job_context['job_title']} Tailored Resume",
            build_contact_html(candidate_profile),
            resume_fragment,
        )
        artifact_paths["tailored_resume_html_path"].write_text(tailored_resume_html, encoding="utf-8")
        tailored_resume_pdf_path = render_resume_pdf_if_available(artifact_paths["tailored_resume_html_path"])

    return {
        "artifact_dir": str(artifact_paths["artifact_dir"]),
        "job_context_path": str(artifact_paths["job_context_path"]),
        "gap_analysis_path": str(artifact_paths["gap_analysis_path"]),
        "follow_up_path": str(artifact_paths["follow_up_path"]),
        "gap_analysis": gap_analysis,
        "tailored_resume_html_path": str(artifact_paths["tailored_resume_html_path"]) if artifact_paths["tailored_resume_html_path"].exists() else None,
        "tailored_resume_pdf_path": str(tailored_resume_pdf_path) if tailored_resume_pdf_path else None,
        "interview_prep_path": str(artifact_paths["interview_prep_path"]),
    }
