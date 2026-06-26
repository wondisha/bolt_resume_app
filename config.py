"""Configuration management for Auto Apply Job."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# Path Constants
# =============================================================================

APP_ROOT = Path(__file__).resolve().parent
STATUS_FILE = APP_ROOT / ".agent_status.json"
APPLICATION_LOG_FILE = APP_ROOT / ".application_history.json"
APPLICATION_DB_FILE = APP_ROOT / ".application_data.sqlite3"
QUESTION_MEMORY_FILE = APP_ROOT / ".question_memory.json"
ARTIFACTS_ROOT = APP_ROOT / "artifacts"


# =============================================================================
# Verification Markers
# =============================================================================

VERIFIED_MARKERS = (
    "verified company",
    "verified employer",
    "linkedin verified",
    "verified hiring",
)

SUPPORTED_SEARCH_PORTALS = {"linkedin", "greenhouse", "lever"}


# =============================================================================
# Resolution Functions
# =============================================================================


def resolve_ollama_executable() -> str:
    """Find the Ollama executable path."""
    env_path = os.getenv("OLLAMA_EXECUTABLE_PATH") or os.getenv("FALLBACK_OLLAMA_EXECUTABLE_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(f"OLLAMA_EXECUTABLE_PATH does not exist: {candidate}")

    path_executable = shutil.which("ollama")
    if path_executable:
        return path_executable

    candidates = [
        Path(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")),
        Path(r"C:\Program Files\Ollama\ollama.exe"),
        Path("/usr/local/bin/ollama"),
        Path("/usr/bin/ollama"),
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "Ollama is not installed or not discoverable. Install Ollama, add it to PATH, or set OLLAMA_EXECUTABLE_PATH."
    )


def resolve_browser_executable() -> str:
    """Find the Chrome or Edge executable path."""
    env_path = os.getenv("BROWSER_EXECUTABLE_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(f"BROWSER_EXECUTABLE_PATH does not exist: {candidate}")

    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe")),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe")),
        # Linux paths
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/chromium"),
        Path("/snap/bin/chromium"),
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "No supported Chrome/Edge executable was found. Set BROWSER_EXECUTABLE_PATH to a valid browser binary."
    )


def resolve_browser_profile_dir() -> tuple[str, bool]:
    """Get browser profile directory and whether it should be cleaned up."""
    env_dir = os.getenv("BROWSER_USER_DATA_DIR")
    if env_dir:
        profile_dir = Path(env_dir).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)
        return str(profile_dir), False

    import tempfile
    profile_dir = Path(tempfile.mkdtemp(prefix="browser-use-profile-"))
    return str(profile_dir), True


# =============================================================================
# Candidate Profile
# =============================================================================


def get_candidate_profile() -> dict:
    """Get candidate profile from environment variables."""
    return {
        "first_name": os.getenv("CANDIDATE_FIRST_NAME", "Wondi"),
        "last_name": os.getenv("CANDIDATE_LAST_NAME", "Wolde"),
        "email": os.getenv("CANDIDATE_EMAIL", "wondenad@gmail.com"),
        "phone": os.getenv("CANDIDATE_PHONE", "240-505-7107"),
        "linkedin_url": os.getenv("CANDIDATE_LINKEDIN_URL", "https://linkedin.com/in/wondi"),
        "github_url": os.getenv("CANDIDATE_GITHUB_URL", "https://github.com/wondisha"),
        "location": os.getenv("CANDIDATE_LOCATION", "Garland, Texas"),
        "sponsorship_needed": os.getenv("CANDIDATE_SPONSORSHIP_NEEDED", "No"),
    }


# =============================================================================
# Boolean Config Getters
# =============================================================================


def _get_bool_env(name: str, default: bool = False) -> bool:
    """Get boolean value from environment."""
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no"}


def require_verified_company() -> bool:
    """Check if verified company is required before applying."""
    return _get_bool_env("REQUIRE_VERIFIED_COMPANY", True)


def should_use_agent_thinking() -> bool:
    """Check if agent should use thinking mode."""
    configured = os.getenv("AGENT_USE_THINKING", "").strip().lower()
    if configured:
        return configured not in {"0", "false", "no"}
    return get_fallback_provider_name() != "ollama"


def should_use_agent_vision() -> bool:
    """Check if agent should use vision mode."""
    configured = os.getenv("AGENT_USE_VISION", "").strip().lower()
    if configured:
        return configured not in {"0", "false", "no"}
    provider = get_fallback_provider_name()
    if provider == "ollama":
        return False
    return True


def should_generate_interview_prep_only() -> bool:
    """Check if only interview prep should be generated."""
    return _get_bool_env("INTERVIEW_PREP_ONLY", False)


def should_skip_document_generation_for_apply() -> bool:
    """Check if document generation should be skipped during apply."""
    return _get_bool_env("SKIP_DOCUMENT_GENERATION_ON_APPLY", False)


# =============================================================================
# Integer Config Getters
# =============================================================================


def _get_int_env(name: str, default: int, min_value: int = 1) -> int:
    """Get integer value from environment with validation."""
    configured = os.getenv(name, str(default)).strip() or str(default)
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer. Got: {configured}") from exc

    if value < min_value:
        raise ValueError(f"{name} must be >= {min_value}. Got: {value}")

    return value


def get_daily_application_target() -> int:
    """Get daily application target."""
    return _get_int_env("DAILY_APPLICATION_TARGET", 5)


def get_search_result_limit() -> int:
    """Get maximum search results to fetch."""
    return _get_int_env("JOB_SEARCH_RESULT_LIMIT", 25)


def get_agent_llm_timeout_seconds() -> int:
    """Get LLM timeout in seconds."""
    return _get_int_env("AGENT_LLM_TIMEOUT", 180)


def get_agent_step_timeout_seconds() -> int:
    """Get agent step timeout in seconds."""
    return _get_int_env("AGENT_STEP_TIMEOUT", 240)


def get_document_resume_char_limit() -> int:
    """Get character limit for resume text in prompts."""
    return _get_int_env("DOCUMENT_RESUME_CHAR_LIMIT", 3500, min_value=500)


def get_document_job_char_limit() -> int:
    """Get character limit for job text in prompts."""
    return _get_int_env("DOCUMENT_JOB_CHAR_LIMIT", 2000, min_value=500)


def get_document_max_tokens() -> int:
    """Get max tokens for document generation."""
    return _get_int_env("DOCUMENT_MAX_TOKENS", 450)


# =============================================================================
# String Config Getters
# =============================================================================


def get_document_model() -> str:
    """Get model name for document generation."""
    return os.getenv("DOCUMENT_LLM_MODEL", "").strip() or os.getenv("FALLBACK_LLM_MODEL", "qwen2.5:3b")


def get_fallback_provider_name() -> str:
    """Get fallback LLM provider name."""
    return os.getenv("FALLBACK_LLM_PROVIDER", os.getenv("FALLBACK_PROVIDER", "google")).strip().lower()


def get_verified_company_allowlist() -> set[str]:
    """Get set of verified company names."""
    allowlist = os.getenv("VERIFIED_COMPANY_ALLOWLIST", "")
    return {entry.strip().lower() for entry in allowlist.split(",") if entry.strip()}


def split_csv_env(name: str, fallback: str = "") -> list[str]:
    """Split comma-separated environment variable into list."""
    raw_value = os.getenv(name, fallback)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def get_preferred_role_keywords() -> list[str]:
    """Get preferred role keywords for job scoring."""
    return split_csv_env(
        "PREFERRED_ROLE_KEYWORDS",
        "snowflake,data engineer,database administrator,data platform,cloud data operations,sql server",
    )


def get_preferred_location_keywords() -> list[str]:
    """Get preferred location keywords for job scoring."""
    candidate_profile = get_candidate_profile()
    return split_csv_env(
        "PREFERRED_LOCATION_KEYWORDS",
        f"{candidate_profile['location']},Dallas,Texas,Remote,Hybrid",
    )


def get_portal_company_slugs(portal_name: str) -> list[str]:
    """Get company slugs for a job portal."""
    env_map = {
        "greenhouse": "GREENHOUSE_COMPANY_SLUGS",
        "lever": "LEVER_COMPANY_SLUGS",
    }
    env_var = env_map.get(portal_name)
    if not env_var:
        return []
    return [item.strip() for item in os.getenv(env_var, "").split(",") if item.strip()]


def get_resume_path() -> str:
    """Get resume path from config."""
    return os.getenv("RESUME_PATH", "wondi.pdf")


# =============================================================================
# LLM Creation
# =============================================================================


def create_primary_llm():
    """Create the primary LLM instance."""
    if _get_bool_env("USE_FALLBACK_AS_PRIMARY", False):
        fallback_llm = create_fallback_llm()
        if fallback_llm is None:
            raise ValueError("USE_FALLBACK_AS_PRIMARY is enabled, but no fallback LLM is configured.")
        return fallback_llm

    from browser_use import ChatGoogle

    return ChatGoogle(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        max_retries=_get_int_env("GEMINI_MAX_RETRIES", 2),
        retry_base_delay=float(os.getenv("GEMINI_RETRY_BASE_DELAY", "2")),
        retry_max_delay=float(os.getenv("GEMINI_RETRY_MAX_DELAY", "30")),
    )


def create_fallback_llm():
    """Create the fallback LLM instance."""
    provider = get_fallback_provider_name()
    model = os.getenv("FALLBACK_LLM_MODEL", os.getenv("FALLBACK_MODEL", "")).strip()

    if not model:
        return None

    if provider == "google":
        from browser_use import ChatGoogle
        return ChatGoogle(
            model=model,
            api_key=os.getenv("FALLBACK_GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
            max_retries=_get_int_env("FALLBACK_GEMINI_MAX_RETRIES", _get_int_env("GEMINI_MAX_RETRIES", 2)),
            retry_base_delay=float(os.getenv("FALLBACK_GEMINI_RETRY_BASE_DELAY", os.getenv("GEMINI_RETRY_BASE_DELAY", "2"))),
            retry_max_delay=float(os.getenv("FALLBACK_GEMINI_RETRY_MAX_DELAY", os.getenv("GEMINI_RETRY_MAX_DELAY", "30"))),
        )

    if provider == "openai":
        from browser_use import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=os.getenv("FALLBACK_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("FALLBACK_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            max_retries=_get_int_env("FALLBACK_OPENAI_MAX_RETRIES", 2),
        )

    if provider == "anthropic":
        from browser_use import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=os.getenv("FALLBACK_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY"),
        )

    if provider == "groq":
        from browser_use import ChatGroq
        return ChatGroq(
            model=model,
            api_key=os.getenv("FALLBACK_GROQ_API_KEY") or os.getenv("GROQ_API_KEY"),
        )

    if provider == "litellm":
        from browser_use import ChatLiteLLM
        return ChatLiteLLM(
            model=model,
            api_key=os.getenv("FALLBACK_LITELLM_API_KEY") or os.getenv("LITELLM_API_KEY"),
            base_url=os.getenv("FALLBACK_LITELLM_BASE_URL") or os.getenv("LITELLM_BASE_URL"),
        )

    if provider == "ollama":
        from browser_use import ChatOllama
        return ChatOllama(
            model=model,
            host=os.getenv("FALLBACK_OLLAMA_HOST") or os.getenv("OLLAMA_HOST"),
        )

    raise ValueError(
        f"Unsupported FALLBACK_LLM_PROVIDER '{provider}'. Supported values: google, openai, anthropic, groq, litellm, ollama."
    )


# =============================================================================
# Validation Functions
# =============================================================================


def validate_ollama_runtime(model: str) -> None:
    """Validate Ollama is installed and model is available."""
    try:
        ollama_executable = resolve_ollama_executable()
    except FileNotFoundError as exc:
        raise ValueError(
            "Fallback provider 'ollama' is configured, but Ollama is not installed or not discoverable. "
            "Install Ollama, add it to PATH, or set OLLAMA_EXECUTABLE_PATH."
        ) from exc

    try:
        result = subprocess.run(
            [ollama_executable, "list"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Ollama is installed, but 'ollama list' timed out. Make sure the Ollama service is running.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValueError(f"Ollama is installed, but model discovery failed: {stderr or exc}") from exc

    installed_models = result.stdout.lower()
    requested_model = model.lower()
    if requested_model not in installed_models:
        raise ValueError(
            f"Ollama fallback model '{model}' is not installed. Run 'ollama pull {model}' first."
        )


def validate_fallback_configuration() -> Optional[tuple[str, str]]:
    """Validate fallback LLM configuration."""
    provider = get_fallback_provider_name()
    model = os.getenv("FALLBACK_LLM_MODEL", os.getenv("FALLBACK_MODEL", "")).strip()

    if not model:
        return None

    required_by_provider = {
        "google": ["FALLBACK_GOOGLE_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "openai": ["FALLBACK_OPENAI_API_KEY", "OPENAI_API_KEY"],
        "anthropic": ["FALLBACK_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"],
        "groq": ["FALLBACK_GROQ_API_KEY", "GROQ_API_KEY"],
        "litellm": [],
        "ollama": [],
    }

    if provider not in required_by_provider:
        raise ValueError(
            f"Unsupported FALLBACK_LLM_PROVIDER '{provider}'. Supported values: google, openai, anthropic, groq, litellm, ollama."
        )

    required_vars = required_by_provider[provider]
    if required_vars and not any(os.getenv(name) for name in required_vars):
        raise ValueError(
            f"Fallback provider '{provider}' requires one of these environment variables: {', '.join(required_vars)}"
        )

    if provider == "ollama":
        validate_ollama_runtime(model)

    return provider, model


def validate_target_job_url(job_url: str) -> None:
    """Validate job URL format."""
    from urllib.parse import urlparse
    parsed = urlparse(job_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"TARGET_JOB_URL must be a valid http(s) URL. Got: {job_url}")

    placeholder_hosts = {"example.com", "www.example.com"}
    if parsed.netloc.lower() in placeholder_hosts:
        raise ValueError(
            "TARGET_JOB_URL is still set to the example placeholder. Set it to the real application form URL."
        )
