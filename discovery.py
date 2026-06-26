"""Job discovery module for Auto Apply Job."""

import re
from urllib.parse import quote_plus, urlparse
from typing import Optional

import requests

from config import (
    SUPPORTED_SEARCH_PORTALS,
    get_portal_company_slugs,
    get_search_result_limit,
)


# =============================================================================
# URL Builders
# =============================================================================


def build_linkedin_search_url(search_query: str, search_location: str, start: int = 0) -> str:
    """Build LinkedIn search URL (authenticated)."""
    keyword_value = quote_plus(search_query.strip())
    location_value = quote_plus(search_location.strip()) if search_location.strip() else ""
    url = f"https://www.linkedin.com/jobs/search/?keywords={keyword_value}"
    if location_value:
        url += f"&location={location_value}"
    if start > 0:
        url += f"&start={start}"
    return url


def build_linkedin_guest_search_url(search_query: str, search_location: str, start: int = 0) -> str:
    """Build LinkedIn guest search API URL."""
    keyword_value = quote_plus(search_query.strip())
    location_value = quote_plus(search_location.strip()) if search_location.strip() else ""
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword_value}"
    if location_value:
        url += f"&location={location_value}"
    if start > 0:
        url += f"&start={start}"
    return url


# =============================================================================
# URL Extraction
# =============================================================================


def extract_job_urls_from_search_html(html_text: str) -> list[str]:
    """Extract job URLs from LinkedIn search HTML."""
    matches = re.findall(
        r'https://www\.linkedin\.com/jobs/view/[^"\'\s?]+|/jobs/view/[^"\'\s?]+',
        html_text,
        flags=re.IGNORECASE,
    )
    discovered = []
    seen = set()
    for match in matches:
        normalized = match if match.startswith("http") else f"https://www.linkedin.com{match}"
        normalized = normalized.split("?", 1)[0]
        if normalized not in seen:
            discovered.append(normalized)
            seen.add(normalized)
    return discovered


# =============================================================================
# Job Matching
# =============================================================================


def normalize_text(value: str) -> str:
    """Normalize text for comparison."""
    return re.sub(r"\s+", " ", value.lower()).strip()


def job_matches_search(job_title: str, job_location: str, search_query: str, search_location: str) -> bool:
    """Check if job matches search criteria."""
    normalized_query = normalize_text(search_query)
    title_text = normalize_text(job_title)

    # All query tokens must appear in title
    query_tokens = [token for token in normalized_query.split() if token]
    query_match = all(token in title_text for token in query_tokens) if query_tokens else True
    if not query_match:
        return False

    # Location must match if specified
    if search_location:
        normalized_location = normalize_text(search_location)
        return normalized_location in normalize_text(job_location)

    return True


# =============================================================================
# Portal-Specific Discovery
# =============================================================================


def discover_linkedin_job_urls(search_query: str, search_location: str, max_results: int) -> list[str]:
    """Discover job URLs from LinkedIn."""
    discovered = []
    seen = set()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JobDiscovery/1.0)"}

    page_size = 25
    for start in range(0, max_results, page_size):
        search_url = build_linkedin_guest_search_url(search_query, search_location, start=start)
        try:
            response = requests.get(search_url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            break

        page_urls = extract_job_urls_from_search_html(response.text)
        if not page_urls:
            break

        new_on_page = 0
        for url in page_urls:
            if url in seen:
                continue
            discovered.append(url)
            seen.add(url)
            new_on_page += 1
            if len(discovered) >= max_results:
                return discovered

        if new_on_page == 0:
            break

    return discovered


def discover_greenhouse_job_urls(search_query: str, search_location: str, max_results: int) -> list[str]:
    """Discover job URLs from Greenhouse."""
    slugs = get_portal_company_slugs("greenhouse")
    if not slugs:
        raise ValueError("GREENHOUSE_COMPANY_SLUGS is required to search greenhouse open positions.")

    discovered = []
    seen = set()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JobDiscovery/1.0)"}

    for slug in slugs:
        try:
            response = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue

        try:
            payload = response.json()
        except ValueError:
            continue

        for job in payload.get("jobs", []):
            title = job.get("title", "")
            location_name = ((job.get("location") or {}).get("name") or "")
            if not job_matches_search(title, location_name, search_query, search_location):
                continue
            absolute_url = job.get("absolute_url")
            if absolute_url and absolute_url not in seen:
                discovered.append(absolute_url)
                seen.add(absolute_url)
                if len(discovered) >= max_results:
                    return discovered

    return discovered


def discover_lever_job_urls(search_query: str, search_location: str, max_results: int) -> list[str]:
    """Discover job URLs from Lever."""
    slugs = get_portal_company_slugs("lever")
    if not slugs:
        raise ValueError("LEVER_COMPANY_SLUGS is required to search lever open positions.")

    discovered = []
    seen = set()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JobDiscovery/1.0)"}

    for slug in slugs:
        try:
            response = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue

        try:
            postings = response.json()
        except ValueError:
            continue

        for job in postings:
            title = job.get("text", "")
            categories = job.get("categories") or {}
            location_name = categories.get("location", "")
            if not job_matches_search(title, location_name, search_query, search_location):
                continue
            absolute_url = job.get("hostedUrl") or job.get("applyUrl")
            if absolute_url and absolute_url not in seen:
                discovered.append(absolute_url)
                seen.add(absolute_url)
                if len(discovered) >= max_results:
                    return discovered

    return discovered


# =============================================================================
# Unified Discovery
# =============================================================================


def discover_job_urls(
    search_query: str,
    search_location: str,
    portal: Optional[str] = None,
    max_results: Optional[int] = None,
) -> list[str]:
    """Discover job URLs from specified portal."""
    import os
    portal_name = (portal or os.getenv("JOB_SEARCH_PORTAL", "linkedin")).strip().lower()

    if portal_name not in SUPPORTED_SEARCH_PORTALS:
        supported = ", ".join(sorted(SUPPORTED_SEARCH_PORTALS))
        raise ValueError(f"Unsupported job search portal '{portal_name}'. Supported values: {supported}")

    if not search_query or not search_query.strip():
        raise ValueError("Job search query is required for automatic discovery.")

    result_limit = max_results or get_search_result_limit()

    if portal_name == "linkedin":
        job_urls = discover_linkedin_job_urls(search_query, search_location or "", result_limit)
    elif portal_name == "greenhouse":
        job_urls = discover_greenhouse_job_urls(search_query, search_location or "", result_limit)
    elif portal_name == "lever":
        job_urls = discover_lever_job_urls(search_query, search_location or "", result_limit)
    else:
        job_urls = []

    if not job_urls:
        location_text = f" in {search_location}" if search_location else ""
        raise ValueError(f"No job postings were discovered for '{search_query}'{location_text} on {portal_name}.")

    return job_urls


def load_job_urls(
    job_url: Optional[str],
    job_urls_file: Optional[str],
    job_search_query: Optional[str] = None,
    job_search_location: Optional[str] = None,
    job_search_portal: Optional[str] = None,
) -> list[str]:
    """Load job URLs from various sources."""
    from pathlib import Path

    urls = []
    if job_url:
        urls.append(job_url)

    if job_urls_file:
        job_urls_path = Path(job_urls_file).expanduser()
        if not job_urls_path.is_file():
            raise FileNotFoundError(f"Job URL list file not found: {job_urls_path}")
        file_urls = [
            line.strip()
            for line in job_urls_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        urls.extend(file_urls)

    if job_search_query:
        discovered_urls = discover_job_urls(
            job_search_query,
            job_search_location,
            portal=job_search_portal,
            max_results=get_search_result_limit(),
        )
        print(
            f"[*] Discovered {len(discovered_urls)} {job_search_portal or 'linkedin'} jobs for "
            f"'{job_search_query}'{f' in {job_search_location}' if job_search_location else ''}."
        )
        urls.extend(discovered_urls)

    # Deduplicate
    deduplicated = []
    seen = set()
    for url in urls:
        if url not in seen:
            deduplicated.append(url)
            seen.add(url)

    if not deduplicated:
        raise ValueError("Provide --job-url or --job-urls-file with at least one real job posting URL.")

    return deduplicated
