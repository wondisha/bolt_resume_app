# Auto Apply Job

Automates job-application prep and browser submission with local fallback LLM support.

## What's New

- **Modular Architecture**: Split into separate modules for config, storage, discovery, documents, and agent
- **Supabase Integration**: Cloud-backed storage for applications and question memory
- **Configurable Candidate Profile**: PII loaded from environment variables instead of hardcoded
- **FastAPI Backend**: REST API scaffold for integration with external apps
- **Improved Security**: Input validation, proper escaping, RLS policies

See [CHANGELOG.md](CHANGELOG.md) for release details.

## Features

- Browser preflight for Chrome or Edge
- Native `browser_use.Agent` fallback LLM support
- Local Ollama fallback using `qwen2.5:3b`
- Verified-company policy with allowlist override
- Automatic LinkedIn job discovery from a search query
- Optional Greenhouse and Lever open-position discovery
- Ranking verified jobs and selecting the top matches by fit
- Batch processing from a job URL list file
- Per-job artifacts:
  - `job_context.json`
  - `gap_analysis.md`
  - `follow_up.md`
  - `tailored_resume.html`
  - `interview_prep.md`

## Repository Layout

```text
apply_agent.py          Main automation script (entry point)
config.py               Configuration management
storage.py              Persistence layer (Supabase + SQLite)
discovery.py            Job discovery from portals
documents.py            Resume tailoring and interview prep
agent.py                Browser automation agent
streamlit_app.py        Lightweight operator dashboard
app_backend/            FastAPI backend scaffold
.env.example            Safe environment template
jobs.example.txt        Example batch input file
docs/STEPS.md           Setup and operating steps
docs/APP_ARCHITECTURE.md Architecture documentation
docs/MIGRATION_GUIDE.md Migration instructions
artifacts/              Generated per-job outputs (git-ignored)
```

## Requirements

- Python 3.13
- Chrome or Edge installed
- Ollama installed locally (for fallback)
- `qwen2.5:3b` pulled in Ollama
- Optional: Gemini API key for primary model

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .\.venv\Scripts\Activate.ps1  # Windows

pip install -r requirements.txt
```

Optional for PDF rendering:
```bash
pip install weasyprint
```

## Configure

1. Copy `.env.example` to `.env`
2. Set your API keys and candidate profile
3. Add trusted employers to `VERIFIED_COMPANY_ALLOWLIST`
4. Point `RESUME_PATH` to your resume PDF

```bash
# Required: Your candidate profile
CANDIDATE_FIRST_NAME=YourName
CANDIDATE_LAST_NAME=YourLastName
CANDIDATE_EMAIL=your@email.com
CANDIDATE_PHONE=your-phone
CANDIDATE_LOCATION=Your City, State

# Required: LLM API keys
GOOGLE_API_KEY=your_key_here

# Optional: Supabase for cloud storage
SUPABASE_URL=your-project-url
SUPABASE_ANON_KEY=your-key
```

## Typical Commands

Preflight one posting:
```bash
python apply_agent.py --preflight --job-url "https://linkedin.com/jobs/view/123/" --resume resume.pdf
```

Generate documents only:
```bash
python apply_agent.py --generate-docs-only --job-url "https://linkedin.com/jobs/view/123/" --resume resume.pdf
```

Apply to one posting:
```bash
python apply_agent.py --job-url "https://linkedin.com/jobs/view/123/" --resume resume.pdf
```

Batch from file:
```bash
python apply_agent.py --job-urls-file jobs.txt --resume resume.pdf
```

Discover and preview:
```bash
python apply_agent.py --discover-only --job-search-query "data engineer" --job-search-location "Texas" --resume resume.pdf
```

Discover and apply:
```bash
python apply_agent.py --job-search-query "data engineer" --job-search-location "Texas" --resume resume.pdf
```

Launch dashboard:
```bash
streamlit run streamlit_app.py
```

Start backend API:
```bash
uvicorn app_backend.main:app --reload
```

## Module Reference

| Module | Purpose |
|--------|---------|
| `config.py` | Environment loading, defaults, validation |
| `storage.py` | Supabase + SQLite persistence |
| `discovery.py` | Job URL discovery from portals |
| `documents.py` | Resume tailoring, interview prep |
| `agent.py` | Browser automation with agent |
| `apply_agent.py` | CLI entry point |

## Verified Company Policy

Default: `REQUIRE_VERIFIED_COMPANY=true`

Verification passes when:
1. Page contains a verification marker (e.g., "verified company")
2. Company name is in `VERIFIED_COMPANY_ALLOWLIST`

Disable with `REQUIRE_VERIFIED_COMPANY=false`

## Daily Target

- Default: 5 applications
- Successful apps tracked in Supabase/SQLite
- Batch mode stops when target is reached

## Supabase Integration

The app uses Supabase when configured for:
- Application event history
- Question memory (screening answers)
- Real-time dashboard updates

Configure with:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

## Deployment Options

### Streamlit Cloud (Free, Limited)

Host the dashboard on Streamlit Cloud for free. Browser automation is not available in cloud mode, but job discovery, document generation, and application history work normally.

See [Streamlit Cloud Deployment Guide](docs/STREAMLIT_CLOUD_DEPLOY.md) for step-by-step instructions.

### Local Deployment (Full Features)

Run locally for complete browser automation:

```bash
streamlit run streamlit_app.py
```

### VPS/Docker (Coming Soon)

Deploy to a VPS with Chrome installed for full cloud-based automation.

## Notes

- `.env`, resumes, artifacts, and runtime state are git-ignored
- Without `weasyprint`, HTML resumes are generated but PDF falls back to original
- Local models are slow; tune `DOCUMENT_*_CHAR_LIMIT` to keep generation bounded
- LinkedIn guest pages often lack verification badges - use `VERIFIED_COMPANY_ALLOWLIST`

## Documentation

- [Setup Steps](docs/STEPS.md)
- [Architecture](docs/APP_ARCHITECTURE.md)
- [Migration Guide](docs/MIGRATION_GUIDE.md)
- [Streamlit Cloud Deployment](docs/STREAMLIT_CLOUD_DEPLOY.md)
