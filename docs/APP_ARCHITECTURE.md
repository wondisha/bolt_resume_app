# Application Architecture

## Overview

Auto Apply Job is a browser automation system that discovers job postings, generates tailored application materials, and submits applications through web forms.

## Components

### Core Script: `apply_agent.py`

The main automation engine handling:

- CLI argument parsing
- Job discovery from multiple portals
- Company verification and job ranking
- Resume tailoring via LLM
- Interview preparation generation
- Browser agent orchestration
- Application tracking

### Dashboard: `streamlit_app.py`

Lightweight web UI for:

- Viewing application history
- Job discovery preview
- Document generation on demand
- Screening answer management
- Settings configuration

### Backend: `app_backend/`

FastAPI scaffold providing:

- REST API for application status
- WebSocket support for live updates
- Job queue management
- External integrations

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                          │
├─────────────────────┬───────────────────────┬───────────────────┤
│   CLI Interface     │   Streamlit Dashboard  │   FastAPI Backend │
│   (apply_agent.py)  │   (streamlit_app.py)  │   (app_backend/)  │
└─────────────────────┴───────────────────────┴───────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────────────┐
│                      CORE SERVICES                                │
├──────────────────┬──────────────────┬────────────────────────────┤
│  Job Discovery   │  Document Gen   │  Browser Agent              │
│  (discovery.py)  │  (documents.py) │  (agent.py)                  │
├──────────────────┴──────────────────┴────────────────────────────┤
│  Configuration & Storage (config.py, storage.py)                 │
└───────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────────────┐
│                      EXTERNAL SERVICES                            │
├─────────────────┬─────────────────┬─────────────────────────────┤
│  LLM Providers  │  Job Portals     │  Supabase (Cloud Storage)    │
│  - Gemini       │  - LinkedIn      │  - Applications table        │
│  - Ollama       │  - Greenhouse    │  - Question memory table     │
│  - OpenAI       │  - Lever         │  - Real-time subscriptions   │
└─────────────────┴─────────────────┴───────────────────────────────┘
```

## Data Flow

### Single Job Application Flow

```
job_url ──► validate_url ──► fetch_context ──► verify_company
                                                        │
                    prepare_application_package ◄───────┘
                           │
                           ▼
              generate_application_documents
              (if SKIP_DOCUMENT_GENERATION_ON_APPLY=false)
                           │
                           ▼
              build_agent_task ──► browser_agent.run()
                                        │
                    record_application_event ◄──┘
                                        │
                                  update_daily_progress
```

### Batch Processing Flow

```
job_urls ──► load_urls ──► rank_job_urls ──► select_top_verified
                                               │
                                               ▼
                    for each selected_job:
                         run_application_agent
                                    │
                              count_successful_applications_today
                                    │
                              stop if target_reached
```

### Discovery Flow

```
search_query+location ──► discover_job_urls (linkedin/greenhouse/lever)
                                    │
                                    ▼
                          rank_job_urls
                                    │
                          score_job_context (role match, location, resume overlap)
                                    │
                          filter_eligible_verified
                                    │
                          preview_ranked_jobs (if --discover-only)
                          OR
                          feed to batch apply
```

## Storage Schema

### Supabase Tables

#### `applications`

| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| created_at | timestamptz | Application timestamp |
| status | text | success/failed/skipped |
| url | text | Job posting URL |
| company_name | text | Employer name |
| job_title | text | Position title |
| verified | boolean | Company verification status |
| verification_source | text | How verification was determined |
| score | integer | Fit score |
| reason | text | Failure/skip reason |
| artifacts | jsonb | Generated document paths |
| gap_analysis | jsonb | Resume gap analysis |

#### `question_memory`

| Column | Type | Description |
|--------|------|-------------|
| id | uuid | Primary key |
| normalized_question | text | Normalized for lookup |
| question_text | text | Original question |
| answer_text | text | Saved answer |
| source | text | Where answer was saved |
| updated_at | timestamptz | Last update time |

## Configuration Management

Settings are loaded from:

1. Environment variables (highest priority)
2. `.env` file
3. Hardcoded defaults (lowest priority)

Categories:

- **LLM**: API keys, model names, timeouts
- **Browser**: Executable paths, profile directory
- **Candidate**: PII for form filling
- **Discovery**: Search portals, company slugs
- **Ranking**: Preferred keywords, location prefs
- **Policy**: Verification requirements, daily targets

## Security Considerations

### Current Implementation

- Secrets stored in `.env` (git-ignored)
- API keys passed via environment
- Browser profile cleaned up after runs

### Recommendations

- Use Supabase Vault for API key storage in production
- Implement user authentication for dashboard
- Add rate limiting on discovery endpoints
- Sanitize all user inputs before subprocess calls

## Scaling Considerations

### Current Limitations

- Single-threaded discovery
- Local file storage (SQLite/JSON)
- No job queue system
- Manual retry logic

### Recommended Improvements

1. **Discovery**: Use `asyncio.gather()` for parallel API calls
2. **Storage**: Migrate to Supabase for multi-device access
3. **Queue**: Add Redis-backed job queue for batch processing
4. **Retries**: Implement exponential backoff with circuit breaker

## Module Structure (Recommended Refactor)

```
auto_apply_job/
├── __init__.py
├── __main__.py           # CLI entrypoint
├── config.py             # Configuration loading
├── storage.py            # Supabase persistence
├── discovery/
│   ├── __init__.py
│   ├── linkedin.py
│   ├── greenhouse.py
│   └── lever.py
├── documents/
│   ├── __init__.py
│   ├── resume.py
│   └── interview.py
├── agent/
│   ├── __init__.py
│   ├── browser.py
│   └── llm.py
├── ranking/
│   ├── __init__.py
│   └── scoring.py
└── api/
    ├── __init__.py
    └── routes.py
```

## Testing Strategy

### Unit Tests

- Configuration loading
- URL parsing and validation
- Scoring algorithms
- Document generation prompts

### Integration Tests

- Job discovery (mocked API responses)
- Supabase operations (test project)
- LLM responses (mocked)

### End-to-End Tests

- Browser smoke tests
- Full application flow (sandbox environment)
