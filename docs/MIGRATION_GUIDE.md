# Changelog

## 2026-06-25 - Major Refactor

### Added

- Modular architecture with separate packages:
  - `config.py` - Configuration management with environment variable loading
  - `storage.py` - Persistence layer with Supabase + SQLite fallback
  - `discovery.py` - Job discovery from LinkedIn, Greenhouse, Lever
  - `documents.py` - Resume tailoring and interview prep generation
  - `agent.py` - Browser automation agent
  - `app_backend/` - FastAPI REST API backend
- Supabase integration for cloud storage of applications and question memory
- Candidate profile loaded from environment variables (moved from hardcoded)
- Comprehensive `.env.example` with all configuration options documented
- `docs/STEPS.md` - Detailed setup and operating instructions
- `docs/APP_ARCHITECTURE.md` - Architecture documentation
- `jobs.example.txt` - Example batch job URLs file

### Changed

- Candidate PII now configurable via `CANDIDATE_*` environment variables
- Storage layer prioritizes Supabase with local SQLite/JSON fallback
- Browser executable detection now includes Linux paths
- All configuration centralized in `config.py` module
- Question memory synced to both Supabase and local storage

### Security

- Candidate PII no longer hardcoded in source
- Shell command arguments properly escaped
- Input validation for URLs and file paths
- RLS policies enabled on Supabase tables

### Migration Guide

1. Update `.env` with your candidate profile:
   ```bash
   CANDIDATE_FIRST_NAME=YourName
   CANDIDATE_LAST_NAME=YourLastName
   CANDIDATE_EMAIL=your@email.com
   # ... see .env.example for all options
   ```

2. Reinstall dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run preflight to verify:
   ```bash
   python apply_agent.py --preflight --job-url <url> --resume <pdf>
   ```

4. Optional: Configure Supabase for cloud storage
   ```
   SUPABASE_URL=your-project-url
   SUPABASE_ANON_KEY=your-anon-key
   ```

---

## 2026-06-20

### Added

- Automatic LinkedIn job discovery from a search query
- `--discover-only` mode to preview ranked jobs without applying
- `JOB_SEARCH_PORTAL` and `JOB_SEARCH_RESULT_LIMIT` configuration options
- Runtime controls for agent LLM timeout, step timeout, thinking mode, and vision mode
- Interview-prep-only generation mode
- Skip-document-generation mode for live apply flows

### Changed

- LinkedIn discovery now uses the guest job postings endpoint and broader URL extraction
- Batch mode can auto-discover, rank, and select the top verified jobs from a search query
- Documentation now includes search-based discovery and preview examples
- Local fallback model behavior is more configurable for slower or non-vision setups

### Fixed

- Browser agent runtime compatibility by initializing missing task timing state
- Explicit discovery and configuration error handling for search-driven runs
