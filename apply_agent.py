#!/usr/bin/env python
"""
Auto Apply Job - Main Entry Point

Automates job-application prep and browser submission with local fallback LLM support.

Usage:
    python apply_agent.py --preflight --job-url <url> --resume <pdf>
    python apply_agent.py --job-url <url> --resume <pdf>
    python apply_agent.py --job-urls-file jobs.txt --resume <pdf>
    python apply_agent.py --discover-only --job-search-query "data engineer" --resume <pdf>
    python apply_agent.py --generate-docs-only --job-url <url> --resume <pdf>
"""

import argparse
import asyncio
import sys
from pathlib import Path

from config import (
    APP_ROOT,
    get_candidate_profile,
    get_daily_application_target,
    get_resume_path,
    validate_target_job_url,
)
from discovery import load_job_urls, discover_job_urls
from documents import (
    extract_resume_text,
    fetch_job_posting_context,
    score_job_context,
    classify_company_verification,
    generate_application_documents,
)
from agent import (
    run_application_agent,
    run_startup_preflight,
    prepare_application_package,
    smoke_test_browser,
)
from storage import (
    count_successful_applications_today,
    initialize_application_store,
    print_daily_progress,
    record_application_event,
)


# =============================================================================
# CLI Argument Parsing
# =============================================================================


def parse_cli_args():
    """Parse command line arguments."""
    import os
    parser = argparse.ArgumentParser(
        description="Run the browser-use job application agent."
    )
    parser.add_argument(
        "--job-url",
        dest="job_url",
        help="Real application form URL to open.",
    )
    parser.add_argument(
        "--job-urls-file",
        dest="job_urls_file",
        help="Path to a text file with one job URL per line.",
    )
    parser.add_argument(
        "--job-search-query",
        dest="job_search_query",
        help="Search job portals for matching roles before ranking.",
    )
    parser.add_argument(
        "--job-search-location",
        dest="job_search_location",
        help="Optional location filter for automatic job discovery.",
    )
    parser.add_argument(
        "--job-search-portal",
        dest="job_search_portal",
        default=os.getenv("JOB_SEARCH_PORTAL", "linkedin"),
        help="Portal to search for jobs automatically. Currently supports: linkedin, greenhouse, lever.",
    )
    parser.add_argument(
        "--resume",
        dest="resume_path",
        help="Path to the resume PDF to upload.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate config and prerequisites, then exit without running the agent.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Launch the browser only, then exit without running the agent.",
    )
    parser.add_argument(
        "--generate-docs-only",
        action="store_true",
        help="Generate the tailored resume/interview prep artifacts but do not submit applications.",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Discover and rank matching jobs but do not generate documents or submit applications.",
    )
    return parser.parse_args()


def has_explicit_job_input(args) -> bool:
    """Check if any job input was provided."""
    return any(
        [
            args.job_url,
            args.job_urls_file,
            args.job_search_query,
        ]
    )


# =============================================================================
# Job Ranking
# =============================================================================


def rank_job_urls(job_urls: list[str], resume_path: str, candidate_profile: dict) -> list[dict]:
    """Rank job URLs by fit score."""
    from config import require_verified_company

    resume_text = extract_resume_text(Path(resume_path).expanduser())
    ranked_jobs = []

    for job_url in job_urls:
        try:
            job_context = fetch_job_posting_context(job_url)
            verified, verification_source = classify_company_verification(job_context)
            job_context["verified"] = verified
            job_context["verification_source"] = verification_source

            if require_verified_company() and not verified:
                ranked_jobs.append(
                    {
                        "url": job_url,
                        "job_context": job_context,
                        "eligible": False,
                        "score": -1,
                        "reasons": ["company verification not confirmed"],
                    }
                )
                continue

            score, reasons = score_job_context(job_context, resume_text, candidate_profile)
            ranked_jobs.append(
                {
                    "url": job_url,
                    "job_context": job_context,
                    "eligible": True,
                    "score": score,
                    "reasons": reasons,
                }
            )
        except Exception as exc:
            ranked_jobs.append(
                {
                    "url": job_url,
                    "job_context": {
                        "url": job_url,
                        "company_name": "Unknown Company",
                        "job_title": job_url,
                    },
                    "eligible": False,
                    "score": -1,
                    "reasons": [f"screening error: {exc}"],
                }
            )

    ranked_jobs.sort(key=lambda item: (item["eligible"], item["score"]), reverse=True)
    return ranked_jobs


def build_ranked_job_preview(job_urls: list[str], resume_path: str) -> dict:
    """Build preview of ranked jobs."""
    candidate_profile = get_candidate_profile()
    ranked_jobs = rank_job_urls(job_urls, resume_path, candidate_profile)
    eligible_ranked_jobs = [item for item in ranked_jobs if item["eligible"]]
    target_count = min(get_daily_application_target(), len(eligible_ranked_jobs))
    return {
        "ranked_jobs": ranked_jobs,
        "eligible_ranked_jobs": eligible_ranked_jobs,
        "selected_jobs": eligible_ranked_jobs[:target_count],
        "target_count": target_count,
    }


def print_ranked_job_summary(ranked_jobs: list[dict], selection_count: int) -> None:
    """Print summary of ranked jobs."""
    print(f"[*] Ranked {len(ranked_jobs)} jobs. Selecting top {selection_count} verified postings.")
    for index, item in enumerate(ranked_jobs[:selection_count], start=1):
        context = item["job_context"]
        reason_text = "; ".join(item["reasons"][:3]) if item["reasons"] else "no scoring reasons"
        print(
            f"[{index}] score={item['score']} | {context.get('company_name')} | {context.get('job_title')} | {reason_text}"
        )


def preview_ranked_jobs(job_urls: list[str], resume_path: str) -> bool:
    """Preview ranked jobs without applying."""
    preview = build_ranked_job_preview(job_urls, resume_path)
    ranked_jobs = preview["ranked_jobs"]
    eligible_ranked_jobs = preview["eligible_ranked_jobs"]
    target_count = preview["target_count"]

    if not eligible_ranked_jobs:
        print("[!] No verified jobs qualified for application after screening.")
        for item in ranked_jobs:
            context = item["job_context"]
            reason_text = "; ".join(item["reasons"][:3]) if item["reasons"] else "not eligible"
            print(f"[-] {context.get('company_name')} | {context.get('job_title')} | {reason_text}")
        return False

    print_ranked_job_summary(eligible_ranked_jobs, target_count)
    for index, item in enumerate(eligible_ranked_jobs[:target_count], start=1):
        context = item["job_context"]
        print(f"    -> {index}. {context.get('job_title')} at {context.get('company_name')} ({item['url']})")
    return True


# =============================================================================
# Document Generation Only
# =============================================================================


def generate_docs_only(job_url: str, resume_path: str) -> bool:
    """Generate documents for a single job."""
    candidate_profile = get_candidate_profile()
    package = prepare_application_package(job_url, resume_path, candidate_profile)

    if not package["should_apply"]:
        raise ValueError(package["reason"])

    if package["artifacts"].get("tailored_resume_html_path"):
        print(f"[*] Tailored resume HTML: {package['artifacts']['tailored_resume_html_path']}")
    if package["artifacts"].get("tailored_resume_pdf_path"):
        print(f"[*] Tailored resume PDF: {package['artifacts']['tailored_resume_pdf_path']}")
    if package["artifacts"].get("gap_analysis_path"):
        print(f"[*] Resume gap analysis: {package['artifacts']['gap_analysis_path']}")
    if package["artifacts"].get("follow_up_path"):
        print(f"[*] Recruiter follow-up pack: {package['artifacts']['follow_up_path']}")
    print(f"[*] Interview prep doc: {package['artifacts']['interview_prep_path']}")
    return True


def run_docs_plan(job_urls: list[str], resume_path: str) -> bool:
    """Generate documents for multiple jobs."""
    all_generated = True
    for job_url in job_urls:
        try:
            generate_docs_only(job_url, resume_path)
        except Exception as exc:
            print(f"[!] Failed to prepare documents for {job_url}: {exc}")
            all_generated = False
    return all_generated


# =============================================================================
# Application Orchestration
# =============================================================================


async def run_job_plan(job_urls: list[str], resume_path: str, docs_only: bool = False) -> bool:
    """Run the job plan (documents or full application)."""
    if docs_only:
        return run_docs_plan(job_urls, resume_path)

    if len(job_urls) == 1:
        return await run_application_agent(job_urls[0], resume_path)

    # Batch mode
    target = get_daily_application_target()
    starting_successes = count_successful_applications_today()
    remaining_target = max(target - starting_successes, 0)
    print(f"[*] Starting batch run with {len(job_urls)} URLs. Daily target: {target}")

    if starting_successes >= target:
        print("[*] Daily target already met. No new applications will be submitted.")
        return True

    candidate_profile = get_candidate_profile()
    ranked_jobs = rank_job_urls(job_urls, resume_path, candidate_profile)
    eligible_ranked_jobs = [item for item in ranked_jobs if item["eligible"]]

    if not eligible_ranked_jobs:
        print("[!] No verified jobs qualified for application after screening.")
        for item in ranked_jobs:
            context = item["job_context"]
            record_application_event(
                context,
                "skipped",
                reason="; ".join(item["reasons"]) or "job did not qualify during ranking",
                artifacts={},
            )
        return False

    selected_jobs = eligible_ranked_jobs[:remaining_target]
    print_ranked_job_summary(selected_jobs, len(selected_jobs))

    # Record skipped jobs
    skipped_jobs = [item for item in ranked_jobs if item not in selected_jobs]
    for item in skipped_jobs:
        context = item["job_context"]
        record_application_event(
            context,
            "skipped",
            reason="; ".join(item["reasons"]) or "not selected in top-ranked jobs",
            artifacts={},
        )

    # Run applications
    for item in selected_jobs:
        if count_successful_applications_today() >= target:
            break
        await run_application_agent(item["url"], resume_path)

    final_successes = count_successful_applications_today()
    print(f"[*] Batch complete. Daily verified applications: {final_successes}/{target}")
    return final_successes >= target


# =============================================================================
# Main Entry Point
# =============================================================================


def main():
    """Main entry point."""
    args = parse_cli_args()
    initialize_application_store()

    target_job_url = args.job_url or "https://example.com/apply"
    my_resume_path = args.resume_path or get_resume_path()

    # Load job URLs
    try:
        job_urls = load_job_urls(
            args.job_url,
            args.job_urls_file,
            job_search_query=args.job_search_query,
            job_search_location=args.job_search_location,
            job_search_portal=args.job_search_portal,
        )
    except (FileNotFoundError, ValueError) as exc:
        if has_explicit_job_input(args):
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc
        job_urls = [target_job_url]

    # Preflight mode
    if args.preflight:
        try:
            for job_url in job_urls:
                run_startup_preflight(job_url, my_resume_path)
            print("[+] Preflight OK")
        except (FileNotFoundError, ValueError) as exc:
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc
        raise SystemExit(0)

    # Document generation only
    if args.generate_docs_only:
        try:
            success = run_docs_plan(job_urls, my_resume_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc
        raise SystemExit(0 if success else 1)

    # Discover only
    if args.discover_only:
        try:
            success = preview_ranked_jobs(job_urls, my_resume_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc
        raise SystemExit(0 if success else 1)

    # Browser smoke test
    if args.smoke_test:
        asyncio.run(smoke_test_browser())
        raise SystemExit(0)

    # Run application
    try:
        success = asyncio.run(run_job_plan(job_urls, my_resume_path, docs_only=False))
    except (FileNotFoundError, ValueError) as exc:
        print(f"[!] Configuration error: {exc}")
        raise SystemExit(1) from exc

    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
