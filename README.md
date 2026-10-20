# LegalDebunkr

An AI-powered web app that breaks dense legal documents and jargon into clear,
accessible explanations for non-expert users.

Upload a lease, contract, NDA, or terms of service (PDF, Word, or a photo of a
page) and get back a plain-English summary, key parties/dates/money, red flags,
a section-by-section translation with a jargon glossary, and a Q&A box grounded
in the document.

## How it works

| Step | Azure service | What it does | Code |
|------|---------------|--------------|------|
| 1 | **Azure AI Document Intelligence** (`prebuilt-layout`) | OCR + structure: headings, paragraphs, tables. Groups text into explainable sections. | `legaldebunkr/document_intelligence.py` |
| 2 | **Azure AI Content Understanding** (custom analyzer) | Extracts structured legal fields: document type, parties, term, payment, termination, liability, dispute resolution, governing law, key obligations. | `legaldebunkr/content_understanding.py` |
| 3 | **Language generation** (Azure OpenAI chat model) | Writes the plain-English overview, per-section explanations, jargon definitions, red flags, and grounded answers to follow-up questions. | `legaldebunkr/language_generation.py` |

`legaldebunkr/pipeline.py` wires them together; `app.py` is the Flask API and
`templates/` + `static/` hold the UI (original text on the left, plain English
on the right).

```
upload -> Document Intelligence -> sections ─┐
      └-> Content Understanding -> fields ───┼-> Azure OpenAI -> overview + section explanations
                                             └-> follow-up Q&A (keyword retrieval over sections)
```

## Setup

1. Create Azure resources:
   - **Azure AI Document Intelligence** (or a multi-service Azure AI Services resource)
   - **Azure AI Content Understanding** (an Azure AI Services resource in a supported region)
   - **Azure OpenAI** with a chat deployment (e.g. `gpt-4o`)
2. Install and configure:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env     # fill in endpoints and keys
   ```
3. Run:
   ```bash
   python app.py            # http://localhost:5000
   ```
   or with Docker:
   ```bash
   docker build -t legaldebunkr . && docker run -p 8000:8000 --env-file .env legaldebunkr
   ```
4. Check configuration at `GET /health`. Run tests with `pytest` (no Azure needed).

   Before pushing to GitHub, read **Publishing to GitHub safely** below.

## Content Understanding version note

Content Understanding is a fast-moving service. The default
`AZURE_CONTENT_UNDERSTANDING_API_VERSION` is `2025-05-01-preview`. If you use a
newer GA version, check Microsoft's current docs; those versions may need
`AZURE_CONTENT_UNDERSTANDING_BASE_ANALYZER_ID` (for example `prebuilt-document`)
and `AZURE_CONTENT_UNDERSTANDING_COMPLETION_MODEL`, both supported through env
vars. If extraction fails, the app still runs and the overview is generated from
the Document Intelligence text alone, with a warning in the UI.

## API

- `POST /api/analyze`: multipart `file` -> analysis JSON (`overview`, `sections`, `fields`, `warnings`)
- `POST /api/ask`: `{doc_id, question}` -> `{answer, sections_used, confidence}`
- `GET /health`: which services are configured

## Security and cost protection

- **Secrets:** all keys are read from environment variables. `.env` is git-ignored and only `.env.example` (placeholders) is committed.
- **Rate limiting** (Flask-Limiter, per client IP): `/api/analyze` defaults to 5/minute and 30/day, `/api/ask` to 20/minute and 200/day. Tune with `RATE_LIMIT_*` in `.env`.
- **Spend cap:** `MAX_CONCURRENT_ANALYSES` limits simultaneous Azure-heavy jobs; `MAX_SECTIONS` and `MAX_UPLOAD_MB` bound the size of each job.
- **Upload checks:** extension allow-list plus file-signature check, size limit, empty-file check.
- **Privacy:** files are processed in memory and never written to disk; analyses expire after `STORE_TTL_SECONDS`.
- **Hardening:** CSP and other security headers, generic error messages (details go to server logs only), Flask debug off unless `FLASK_DEBUG=1`, container runs as a non-root user.
- **Behind a proxy:** set `TRUST_PROXY_HOPS=1` so limits use the real client IP.
- **Multiple workers or instances:** set `RATELIMIT_STORAGE_URI=redis://...` (and move the analysis store to Redis). The default Docker setup uses one worker with threads so in-memory limits stay accurate.

## Publishing to GitHub safely

1. Check your secrets are ignored **before** the first commit:
   ```bash
   git init
   git check-ignore -v .env      # must print a .gitignore rule
   git add .
   git status                    # .env must NOT be listed; .env.example should be
   ```
2. Optional but recommended, block secrets from ever being committed:
   ```bash
   pip install pre-commit && pre-commit install
   ```
3. Commit and push:
   ```bash
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<you>/legaldebunkr.git
   git push -u origin main
   ```
4. On GitHub: Settings > Code security > enable **Secret scanning** and **Push protection**. The included CI also runs tests and a gitleaks scan on every push.
5. For deploying, put the variables from `.env.example` in your host's secret store (GitHub Actions secrets, Azure App Service settings, Render/Fly/Railway env vars). Never in code.

**If a key ever gets committed:** rotate it in the Azure portal right away (Keys and Endpoint > Regenerate). Deleting the commit or the repo does not make it safe, because scrapers pick up leaked keys within minutes.

Don't commit real contracts or leases as test files; `.gitignore` already excludes `*.pdf` and `*.docx` by default.

## Disclaimer

LegalDebunkr explains documents in plain language. It is not a lawyer and its
output is not legal advice.
