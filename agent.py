"""Browser agent module for Auto Apply Job."""

import asyncio
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from browser_use import Agent, Browser

from config import (
    APP_ROOT,
    create_fallback_llm,
    create_primary_llm,
    get_candidate_profile,
    get_agent_llm_timeout_seconds,
    get_agent_step_timeout_seconds,
    require_verified_company,
    resolve_browser_executable,
    resolve_browser_profile_dir,
    should_skip_document_generation_for_apply,
    should_use_agent_thinking,
    should_use_agent_vision,
    validate_fallback_configuration,
    validate_target_job_url,
)
from documents import (
    classify_company_verification,
    fetch_job_posting_context,
    generate_application_documents,
)
from storage import (
    build_question_memory_context,
    clear_status_record,
    get_daily_application_target,
    load_status_record,
    print_daily_progress,
    record_application_event,
    save_status_record,
)


# =============================================================================
# Quota Error Handling
# =============================================================================


def is_quota_error(error_message: str) -> bool:
    """Check if error is a quota exhaustion."""
    lowered = error_message.lower()
    quota_markers = (
        "429",
        "resource_exhausted",
        "quota exceeded",
        "quotafailure",
        "rate limit",
        "too many requests",
        "generativelanguage.googleapis.com",
    )
    return any(marker in lowered for marker in quota_markers)


def is_daily_quota_exhausted(error_message: str) -> bool:
    """Check if daily quota is exhausted."""
    lowered = error_message.lower()
    return "requestsperday" in lowered or "perday" in lowered


def extract_retry_delay_seconds(error_message: str) -> Optional[float]:
    """Extract retry delay from error message."""
    patterns = (
        r"retry in ([\d\.]+)s",
        r"retrydelay['\"]?\s*[:=]\s*['\"]?([\d\.]+)s",
        r"retry delay['\"]?\s*[:=]\s*['\"]?([\d\.]+)s",
    )

    for pattern in patterns:
        match = re.search(pattern, error_message, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))

    return None


# =============================================================================
# Profile Cleanup
# =============================================================================


def cleanup_browser(profile_path: str) -> None:
    """Clean up browser profile directory."""
    if os.path.exists(profile_path):
        try:
            shutil.rmtree(profile_path)
            print("[*] Cleaned up stale browser profile.")
        except PermissionError:
            print("[!] Warning: Could not delete profile. Browser might be running.")


# =============================================================================
# Agent Task Building
# =============================================================================


def build_agent_task(job_url: str, candidate_profile: dict, upload_resume_path: str) -> str:
    """Build the task description for the browser agent."""
    question_memory_context = build_question_memory_context()
    return (
        f"Navigate to {job_url}. "
        f"Before applying, confirm the employer appears verified on the page. If verification is missing or ambiguous, stop without applying. "
        f"Fill the application using this candidate profile: {candidate_profile}. "
        f"Upload {upload_resume_path}. "
        f"{question_memory_context} "
        "Do not invent answers. If any required field cannot be answered from the provided data, stop and report the blocker. "
        "Submit only if the posting is from a verified company and the form is complete."
    )


# =============================================================================
# Preflight Check
# =============================================================================


def run_startup_preflight(job_url: str, resume_path: str) -> Optional[tuple[str, str]]:
    """Run startup validation checks."""
    from pathlib import Path
    validate_target_job_url(job_url)

    resume_file = Path(resume_path).expanduser()
    if not resume_file.is_file():
        raise FileNotFoundError(f"Resume file not found: {resume_file}")

    browser_path = resolve_browser_executable()
    fallback_config = validate_fallback_configuration()
    status = load_status_record()
    primary_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    job_context = fetch_job_posting_context(job_url)
    verified, verification_source = classify_company_verification(job_context)

    print(f"[*] Browser executable: {browser_path}")
    print(f"[*] Target job URL: {job_url}")
    print(f"[*] Parsed job: {job_context['company_name']} / {job_context['job_title']}")
    print(f"[*] Primary LLM: google/{primary_model}")
    print(f"[*] Verified-only mode: {'on' if require_verified_company() else 'off'}")

    if fallback_config is None:
        print("[!] No fallback LLM configured. Gemini quota exhaustion will stop the run.")
    else:
        provider, model = fallback_config
        print(f"[*] Fallback LLM ready: {provider}/{model}")
        print(
            f"[*] Agent runtime settings: llm_timeout={get_agent_llm_timeout_seconds()}s, "
            f"step_timeout={get_agent_step_timeout_seconds()}s, use_thinking={'on' if should_use_agent_thinking() else 'off'}, "
            f"use_vision={'on' if should_use_agent_vision() else 'off'}"
        )

    if verified:
        print(f"[*] Company verification accepted via {verification_source}")
    else:
        print(f"[!] Company verification not confirmed: {verification_source}")

    if (
        status.get("daily_quota_exhausted")
        and status.get("provider") == "google"
        and status.get("model") == primary_model
    ):
        print(
            "[!] Previous run recorded Gemini daily quota exhaustion for the current primary model. "
            "If quota has not reset yet, the primary model will fail immediately."
        )

    print_daily_progress()
    return fallback_config


# =============================================================================
# Application Package Preparation
# =============================================================================


def prepare_application_package(job_url: str, resume_path: str, candidate_profile: dict) -> dict:
    """Prepare application package including documents."""
    from pathlib import Path
    job_context = fetch_job_posting_context(job_url)
    verified, verification_source = classify_company_verification(job_context)
    job_context["verified"] = verified
    job_context["verification_source"] = verification_source

    if require_verified_company() and not verified:
        return {
            "job_context": job_context,
            "should_apply": False,
            "reason": "Company verification not confirmed.",
            "artifacts": {},
            "upload_resume_path": str(Path(resume_path).expanduser()),
        }

    if should_skip_document_generation_for_apply():
        print("[!] Skipping tailored document generation for live apply. Using the original resume for upload.")
        return {
            "job_context": job_context,
            "should_apply": True,
            "reason": None,
            "artifacts": {},
            "upload_resume_path": str(Path(resume_path).expanduser()),
        }

    artifacts = generate_application_documents(job_context, Path(resume_path).expanduser(), candidate_profile)
    upload_resume_path = artifacts.get("tailored_resume_pdf_path") or str(Path(resume_path).expanduser())
    if not artifacts.get("tailored_resume_pdf_path"):
        print("[!] Tailored resume PDF was not rendered. Using the original PDF for upload; tailored HTML was still generated.")

    return {
        "job_context": job_context,
        "should_apply": True,
        "reason": None,
        "artifacts": artifacts,
        "upload_resume_path": upload_resume_path,
    }


# =============================================================================
# History Error Summarization
# =============================================================================


def summarize_history_errors(history) -> list[str]:
    """Extract errors from agent history."""
    return [error for error in history.errors() if error]


# =============================================================================
# Main Agent Runner
# =============================================================================


async def run_application_agent(job_url: str, resume_path: str) -> bool:
    """Run the browser application agent for a single job."""
    candidate_profile = get_candidate_profile()

    run_startup_preflight(job_url, resume_path)
    package = prepare_application_package(job_url, resume_path, candidate_profile)
    job_context = package["job_context"]

    if not package["should_apply"]:
        print(f"[!] Skipping application for {job_context['company_name']}: {package['reason']}")
        record_application_event(job_context, "skipped", reason=package["reason"], artifacts=package["artifacts"])
        return False

    browser_executable = resolve_browser_executable()
    profile_path, cleanup_profile = resolve_browser_profile_dir()

    if not cleanup_profile:
        cleanup_browser(profile_path)

    browser = Browser(
        executable_path=browser_executable,
        headless=os.getenv("BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"},
        user_data_dir=profile_path,
    )

    try:
        llm = create_primary_llm()
        fallback_llm = create_fallback_llm()
        if fallback_llm is not None:
            print(f"[*] Fallback LLM enabled: provider={fallback_llm.provider}, model={fallback_llm.model}")

        task = build_agent_task(job_url, candidate_profile, os.path.abspath(package["upload_resume_path"]))
        max_retries = int(os.getenv("AGENT_MAX_RETRIES", "3"))
        llm_timeout = get_agent_llm_timeout_seconds()
        step_timeout = get_agent_step_timeout_seconds()
        use_thinking = should_use_agent_thinking()
        use_vision = should_use_agent_vision()

        for attempt in range(max_retries):
            agent = Agent(
                task=task,
                llm=llm,
                fallback_llm=fallback_llm,
                browser=browser,
                llm_timeout=llm_timeout,
                step_timeout=step_timeout,
                use_thinking=use_thinking,
                use_vision=use_vision,
            )
            if not hasattr(agent, "_task_start_time"):
                agent._task_start_time = time.time()
            print(f"[*] Starting agent (Attempt {attempt + 1})")

            try:
                history = await agent.run()
            except Exception as exc:
                error_msg = str(exc)
                if is_quota_error(error_msg) and attempt < max_retries - 1:
                    wait_time = extract_retry_delay_seconds(error_msg)
                    if wait_time is None or wait_time <= 0:
                        wait_time = min(30 * (attempt + 1), 300)
                    print(f"[!] Quota exhausted before completion. Sleeping for {wait_time:.1f} seconds...")
                    await asyncio.sleep(wait_time + 2)
                    continue

                print(f"[!] Unexpected error: {error_msg}")
                record_application_event(job_context, "failed", reason=error_msg, artifacts=package["artifacts"])
                return False

            if history.is_successful():
                clear_status_record()
                record_application_event(job_context, "success", artifacts=package["artifacts"])
                print("[+] Application workflow complete!")
                print_daily_progress()
                return True

            history_errors = summarize_history_errors(history)
            if history_errors:
                error_msg = "\n".join(history_errors[-3:])
                if is_quota_error(error_msg):
                    if is_daily_quota_exhausted(error_msg):
                        save_status_record(
                            {
                                "daily_quota_exhausted": True,
                                "provider": "google",
                                "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                                "last_error": error_msg,
                            }
                        )
                        record_application_event(job_context, "failed", reason=error_msg, artifacts=package["artifacts"])
                        print("[!] Gemini daily free-tier quota exhausted. Retry tomorrow or switch to a billed API key/model.")
                        return False

                    if attempt < max_retries - 1:
                        wait_time = extract_retry_delay_seconds(error_msg)
                        if wait_time is None or wait_time <= 0:
                            wait_time = min(30 * (attempt + 1), 300)
                        print(f"[!] Gemini rate limit hit. Sleeping for {wait_time:.1f} seconds before retry...")
                        await asyncio.sleep(wait_time + 2)
                        continue

                    print("[!] Gemini quota exhausted and retry budget reached.")
                    save_status_record(
                        {
                            "daily_quota_exhausted": False,
                            "provider": "google",
                            "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                            "last_error": error_msg,
                        }
                    )
                    record_application_event(job_context, "failed", reason=error_msg, artifacts=package["artifacts"])
                    return False

                save_status_record({"daily_quota_exhausted": False, "last_error": error_msg})
                record_application_event(job_context, "failed", reason=error_msg, artifacts=package["artifacts"])
                print(f"[!] Agent stopped with errors:\n{error_msg}")
                return False

            message = "Agent stopped without completing the task."
            save_status_record({"daily_quota_exhausted": False, "last_error": message})
            record_application_event(job_context, "failed", reason=message, artifacts=package["artifacts"])
            print(f"[!] {message}")
            return False

        return False
    finally:
        await browser.close()

        if cleanup_profile:
            cleanup_browser(profile_path)


# =============================================================================
# Smoke Test
# =============================================================================


async def smoke_test_browser() -> None:
    """Test browser setup without running agent."""
    browser_executable = resolve_browser_executable()
    profile_path, cleanup_profile = resolve_browser_profile_dir()
    browser = Browser(
        executable_path=browser_executable,
        headless=True,
        user_data_dir=profile_path,
    )

    try:
        await browser.start()
        print(f"[+] Browser launch OK with {browser_executable}")
    finally:
        await browser.close()
        if cleanup_profile:
            cleanup_browser(profile_path)
