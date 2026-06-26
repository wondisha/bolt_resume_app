# Setup and Operating Steps

## Prerequisites

1. **Python 3.13** installed
2. **Chrome or Edge** browser installed
3. **Ollama** installed locally (for fallback LLM)
4. **Git** (optional, for version control)

## Initial Setup

### Step 1: Clone or Download

```powershell
git clone <repository-url>
cd auto-apply-job
```

### Step 2: Create Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies

```powershell
pip install -r requirements.txt
```

For PDF rendering support:

```powershell
pip install weasyprint
```

### Step 4: Configure Environment

```powershell
copy .env.example .env
```

Edit `.env` and set:

- `GOOGLE_API_KEY` - Your Google Gemini API key
- `CANDIDATE_*` fields - Your personal information
- `RESUME_PATH` - Path to your resume PDF
- `VERIFIED_COMPANY_ALLOWLIST` - Trusted company names

### Step 5: Install Ollama and Pull Model

```powershell
# Download and install from https://ollama.ai
ollama pull qwen2.5:3b
```

### Step 6: Verify Installation

```powershell
python apply_agent.py --preflight --job-url "https://example.com/apply" --resume "wondi.pdf"
```

## Operating Modes

### Preflight Check

Validates configuration without running the agent:

```powershell
python apply_agent.py --preflight --job-url <job-url> --resume <resume.pdf>
```

### Single Job Application

Apply to one job posting:

```powershell
python apply_agent.py --job-url <job-url> --resume <resume.pdf>
```

### Batch Application

Apply to multiple jobs from a file:

```powershell
python apply_agent.py --job-urls-file jobs.txt --resume <resume.pdf>
```

### Job Discovery

Discover matching jobs without applying:

```powershell
python apply_agent.py --discover-only --job-search-query "data engineer" --job-search-location "Texas" --resume <resume.pdf>
```

Discover and apply to top matches:

```powershell
python apply_agent.py --job-search-query "data engineer" --job-search-location "Texas" --resume <resume.pdf>
```

### Document Generation Only

Generate tailored resume and interview prep without applying:

```powershell
python apply_agent.py --generate-docs-only --job-url <job-url> --resume <resume.pdf>
```

### Browser Smoke Test

Test browser setup:

```powershell
python apply_agent.py --smoke-test
```

## Dashboard

Launch the Streamlit dashboard:

```powershell
streamlit run streamlit_app.py
```

Features:

- View recent application history
- Discover and preview ranked jobs
- Generate prep packs for specific URLs
- Manage reusable screening answers
- Configure verification settings

## Backend API

Start the FastAPI backend:

```powershell
uvicorn app_backend.main:app --reload
```

API documentation available at: http://localhost:8000/docs

## Understanding the Workflow

1. **Discovery**: Find job URLs from LinkedIn, Greenhouse, or Lever
2. **Screening**: Verify companies and rank jobs by fit
3. **Document Generation**: Create tailored resume and interview prep
4. **Application**: Browser agent fills and submits the form
5. **Tracking**: Record progress toward daily target

## Daily Target Behavior

- Set `DAILY_APPLICATION_TARGET` in `.env` (default: 5)
- Successful applications are tracked
- Batch mode stops when target is reached
- Progress resets daily

## Verified Company Policy

The agent defaults to only applying to verified companies.

Verification passes when:

1. Page contains a verification marker (e.g., "verified company")
2. Company name is in `VERIFIED_COMPANY_ALLOWLIST`

Disable verification requirement:

```env
REQUIRE_VERIFIED_COMPANY=false
```

## Troubleshooting

### Browser Not Found

Set `BROWSER_EXECUTABLE_PATH` in `.env`:

```env
BROWSER_EXECUTABLE_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

### Ollama Not Running

Start the Ollama service:

```powershell
ollama serve
```

### Gemini Quota Exhausted

The agent automatically falls back to Ollama. Ensure:

1. `FALLBACK_LLM_MODEL=qwen2.5:3b` is set
2. Ollama is running
3. Model is pulled: `ollama pull qwen2.5:3b`

### LinkedIn Discovery Returns No Results

- Verify search query is not too specific
- Try different location keywords
- Check if LinkedIn guest API is accessible from your network

### Document Generation Slow

For local models, reduce character limits:

```env
DOCUMENT_RESUME_CHAR_LIMIT=2000
DOCUMENT_JOB_CHAR_LIMIT=1500
DOCUMENT_MAX_TOKENS=300
```

## File Locations

| File | Purpose |
|------|---------|
| `.env` | Configuration secrets |
| `jobs.txt` | Batch job URLs |
| `artifacts/` | Generated documents |
| `.application_history.json` | Application records |
| `.question_memory.json` | Saved screening answers |
| `.agent_status.json` | Runtime status |
