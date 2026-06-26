# Deploy to Streamlit Cloud

Streamlit Cloud provides free hosting for Streamlit applications. This guide walks you through deploying the Auto Apply Job app.

## Prerequisites

- GitHub account
- Streamlit Cloud account (sign up at [streamlit.io/cloud](https://streamlit.io/cloud))

## Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/auto-apply-job.git
git push -u origin main
```

## Step 2: Connect to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click "New app"
4. Select your repository: `auto-apply-job`
5. Set the main file path: `streamlit_app.py`
6. Click "Deploy"

## Step 3: Configure Secrets

In Streamlit Cloud, add your secrets (Settings > Secrets):

```toml
# LLM Provider (choose one)
GOOGLE_API_KEY = "your-google-api-key"
# OPENAI_API_KEY = "your-openai-api-key"
# ANTHROPIC_API_KEY = "your-anthropic-api-key"

# Supabase
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your-anon-key"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"

# Candidate Profile
CANDIDATE_FULL_NAME = "Your Name"
CANDIDATE_EMAIL = "your@email.com"
CANDIDATE_PHONE = "+1-555-123-4567"
CANDIDATE_LOCATION = "Your City, State"
CANDIDATE_LINKEDIN_URL = "https://linkedin.com/in/yourprofile"
CANDIDATE_PORTFOLIO_URL = "https://yourportfolio.com"
CANDIDATE_RESUME_PATH = "artifacts/resume.pdf"

# Job Preferences
PREFERRED_ROLE_KEYWORDS = "data engineer,ml engineer"
PREFERRED_LOCATION_KEYWORDS = "remote,texas,california"
DAILY_APPLICATION_TARGET = "10"
```

## Step 4: Upload Resume

1. Create an `artifacts/` folder in your repo
2. Upload your resume PDF: `artifacts/resume.pdf`
3. Commit and push

## Features Available in Cloud Mode

| Feature | Cloud | Local |
|---------|-------|-------|
| Job Discovery | Yes | Yes |
| Document Generation | Yes | Yes |
| Application History | Yes | Yes |
| Question Memory | Yes | Yes |
| Browser Automation | No | Yes |

**Note**: Browser automation requires a Chrome/Edge browser which isn't available in Streamlit Cloud's sandboxed environment. Use the local deployment for full apply flows.

## Local Development

For full functionality including browser automation:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install all dependencies including browser automation
pip install streamlit
pip install browser-use>=0.1.0
pip install -r requirements.txt

# Run the app
streamlit run streamlit_app.py
```

## Troubleshooting

### App won't start
- Check that `streamlit_app.py` is in the root directory
- Verify all dependencies in `requirements.txt` are valid

### Secrets not loading
- Ensure secrets are set in Streamlit Cloud dashboard (not `.env`)
- Restart the app after adding secrets

### Import errors
- Check that all modules (`config.py`, `storage.py`, etc.) are in the repo
- Verify the Python version matches (3.11+)
