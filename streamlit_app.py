"""Streamlit dashboard for Auto Apply Job."""

import subprocess
import sys
from pathlib import Path

import streamlit as st
from dotenv import dotenv_values, set_key

# Check if running in cloud (no browser available)
BROWSER_AUTOMATION_AVAILABLE = False
try:
    from browser_use import Agent, Browser  # noqa: F401
    BROWSER_AUTOMATION_AVAILABLE = True
except ImportError:
    pass

# Import from new modular structure
from config import (
    APP_ROOT,
    ARTIFACTS_ROOT,
    get_candidate_profile,
    get_daily_application_target,
    get_resume_path,
    require_verified_company,
    get_verified_company_allowlist,
    get_portal_company_slugs,
    get_preferred_role_keywords,
    get_preferred_location_keywords,
)
from discovery import discover_job_urls, load_job_urls
from documents import build_ranked_job_preview
from storage import (
    list_recent_application_events,
    load_question_memory,
    save_question_memory,
)


st.set_page_config(page_title="Auto Apply Job", layout="wide")

ENV_FILE = APP_ROOT / ".env"


def run_cli_command(arguments):
    """Run CLI command and return result."""
    command = [sys.executable, str(APP_ROOT / "apply_agent.py"), *arguments]
    completed = subprocess.run(
        command,
        cwd=str(APP_ROOT),
        capture_output=True,
        text=True,
    )
    return completed, command


def render_command_result(result, command):
    """Render command result in Streamlit."""
    st.code(" ".join(command), language="powershell")
    if result.returncode == 0:
        st.success("Command completed successfully.")
    else:
        st.error(f"Command failed with exit code {result.returncode}.")

    if result.stdout.strip():
        st.text_area("Standard output", result.stdout, height=240)
    if result.stderr.strip():
        st.text_area("Standard error", result.stderr, height=180)


def load_env_settings():
    """Load settings from .env file."""
    if not ENV_FILE.exists():
        return {}
    return {
        key: value
        for key, value in dotenv_values(str(ENV_FILE)).items()
        if value is not None
    }


def save_env_setting(key, value):
    """Save setting to .env file."""
    set_key(str(ENV_FILE), key, str(value))


def render_dashboard():
    """Render dashboard tab."""
    st.subheader("Recent Applications")
    events = list_recent_application_events(limit=50)
    if not events:
        st.info("No structured application events recorded yet.")
        return

    table_rows = []
    for event in events:
        table_rows.append(
            {
                "Timestamp": event["timestamp"],
                "Status": event["status"],
                "Company": event["company_name"],
                "Role": event["job_title"],
                "Verified": "Yes" if event["verified"] else "No",
                "Reason": event["reason"] or "",
            }
        )
    st.dataframe(table_rows, use_container_width=True)

    # Daily progress
    target = get_daily_application_target()
    today_count = sum(1 for e in events if e["status"] == "success")
    st.metric("Daily Progress", f"{today_count}/{target}")


def render_discovery():
    """Render discovery tab."""
    st.subheader("Discover and Rank Jobs")
    default_resume = get_resume_path()
    query = st.text_input("Job search query", value="data engineer")
    location = st.text_input("Location", value="Texas")
    resume_path = st.text_input("Resume path", value=default_resume)
    portal = st.selectbox("Portal", options=["linkedin", "greenhouse", "lever"], index=0)

    if st.button("Preview ranked jobs"):
        try:
            job_urls = discover_job_urls(
                query,
                location,
                portal=portal,
                max_results=25,
            )
            preview = build_ranked_job_preview(job_urls, resume_path)
            ranked_jobs = preview["ranked_jobs"]
            selected_jobs = preview["selected_jobs"]
            if selected_jobs:
                st.success(
                    f"Discovered {len(job_urls)} jobs and selected {len(selected_jobs)} eligible jobs from {portal}."
                )
            else:
                st.warning("No verified jobs qualified in the ranked preview.")

            display_rows = []
            for item in ranked_jobs:
                context = item["job_context"]
                display_rows.append(
                    {
                        "Eligible": "Yes" if item["eligible"] else "No",
                        "Score": item["score"],
                        "Company": context.get("company_name"),
                        "Role": context.get("job_title"),
                        "URL": item["url"],
                        "Reasons": "; ".join(item["reasons"][:3]),
                    }
                )
            if display_rows:
                st.dataframe(display_rows, use_container_width=True)
        except Exception as exc:
            st.error(str(exc))


def render_documents():
    """Render documents tab."""
    st.subheader("Generate Prep Pack")
    default_resume = get_resume_path()
    job_url = st.text_input(
        "Job URL",
        value="https://www.linkedin.com/jobs/view/senior-data-engineer-at-hcltech-4414046431",
    )
    resume_path = st.text_input("Resume path", value=default_resume, key="docs_resume_path")

    if st.button("Generate artifacts"):
        try:
            result, command = run_cli_command(
                ["--generate-docs-only", "--job-url", job_url, "--resume", resume_path]
            )
            render_command_result(result, command)
            st.caption(f"Artifacts root: {ARTIFACTS_ROOT}")
        except Exception as exc:
            st.error(str(exc))


def render_run_controls():
    """Render run controls tab."""
    st.subheader("Run Application Flows")

    if not BROWSER_AUTOMATION_AVAILABLE:
        st.info(
            "Browser automation requires a local environment with Chrome/Edge. "
            "Run `apply_agent.py` locally for full application flows."
        )
        return

    default_resume = get_resume_path()
    single_job_url = st.text_input(
        "Single job URL",
        value="https://www.linkedin.com/jobs/view/senior-data-engineer-at-hcltech-4414046431",
    )
    batch_file = st.text_input(
        "Batch file path", value=str((APP_ROOT / "jobs.txt").resolve())
    )
    resume_path = st.text_input(
        "Resume path", value=default_resume, key="run_resume_path"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Run preflight"):
            result, command = run_cli_command(
                ["--preflight", "--job-url", single_job_url, "--resume", resume_path]
            )
            render_command_result(result, command)
    with col2:
        if st.button("Apply single job"):
            result, command = run_cli_command(
                ["--job-url", single_job_url, "--resume", resume_path]
            )
            render_command_result(result, command)
    with col3:
        if st.button("Run batch apply"):
            result, command = run_cli_command(
                ["--job-urls-file", batch_file, "--resume", resume_path]
            )
            render_command_result(result, command)


def render_question_memory():
    """Render question memory tab."""
    st.subheader("Screening Answer Memory")
    current_memory = load_question_memory()
    if current_memory:
        st.dataframe(
            [
                {
                    "Question": item["question"],
                    "Answer": item["answer"],
                    "Source": item["source"],
                    "Updated": item["updated_at"],
                }
                for item in sorted(
                    current_memory.values(), key=lambda entry: entry["question"].lower()
                )
            ],
            use_container_width=True,
        )
    else:
        st.info("No saved screening answers yet.")

    with st.form("question_memory_form"):
        question = st.text_input("Question")
        answer = st.text_input("Answer")
        submitted = st.form_submit_button("Save answer")
        if submitted:
            if not question.strip() or not answer.strip():
                st.error("Question and answer are required.")
            else:
                save_question_memory(question, answer, source="streamlit-app")
                st.success("Saved screening answer.")


def render_candidate_profile():
    """Render candidate profile tab."""
    st.subheader("Candidate Profile Snapshot")
    profile = get_candidate_profile()
    st.json(profile)

    st.info(
        "Edit candidate profile in .env file using CANDIDATE_* environment variables."
    )


def render_settings():
    """Render settings tab."""
    st.subheader("Verification Settings")
    env_settings = load_env_settings()
    current_require_verified = require_verified_company()
    current_allowlist = ",".join(get_verified_company_allowlist())
    current_greenhouse_slugs = ",".join(get_portal_company_slugs("greenhouse"))
    current_lever_slugs = ",".join(get_portal_company_slugs("lever"))

    with st.form("verification_settings_form"):
        require_verified = st.checkbox(
            "Require verified company before apply", value=current_require_verified
        )
        allowlist = st.text_input(
            "Verified company allowlist",
            value=current_allowlist,
            help="Comma-separated company names such as HCLTech,Dexian,Anblicks",
        )
        greenhouse_slugs = st.text_input(
            "Greenhouse company slugs",
            value=current_greenhouse_slugs,
            help="Comma-separated Greenhouse board slugs such as stripe,notion,airbnb",
        )
        lever_slugs = st.text_input(
            "Lever company slugs",
            value=current_lever_slugs,
            help="Comma-separated Lever company slugs such as netflix,figma,sourcegraph",
        )
        submitted = st.form_submit_button("Save verification settings")
        if submitted:
            save_env_setting("REQUIRE_VERIFIED_COMPANY", "1" if require_verified else "0")
            save_env_setting("VERIFIED_COMPANY_ALLOWLIST", allowlist)
            save_env_setting("GREENHOUSE_COMPANY_SLUGS", greenhouse_slugs)
            save_env_setting("LEVER_COMPANY_SLUGS", lever_slugs)
            st.success("Saved verification settings to .env")
            st.caption(
                "Rerun your discovery or apply action after saving so the new settings are used."
            )


# Main app
st.title("Auto Apply Job App")

# Show mode indicator
if not BROWSER_AUTOMATION_AVAILABLE:
    st.warning(
        "**Cloud Mode**: Browser automation is not available. Job discovery, document "
        "generation, and application history work normally. To run full apply flows, "
        "deploy locally or use a VPS with Chrome installed."
    )

st.caption(
    "Lightweight dashboard for discovery, prep generation, application history, "
    "and screening-answer memory."
)

(
    dashboard_tab,
    discovery_tab,
    docs_tab,
    run_tab,
    memory_tab,
    profile_tab,
    settings_tab,
) = st.tabs(
    ["Dashboard", "Discover", "Prep Pack", "Run", "Question Memory", "Profile", "Settings"]
)

with dashboard_tab:
    render_dashboard()

with discovery_tab:
    render_discovery()

with docs_tab:
    render_documents()

with run_tab:
    render_run_controls()

with memory_tab:
    render_question_memory()

with profile_tab:
    render_candidate_profile()

with settings_tab:
    render_settings()
