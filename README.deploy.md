# Deploying Resume Fixer to a live URL (Render)

This is a **config-only** deployment. No parser / scoring / rendering / UI logic
was changed. The only code edit is env-driven CORS (`backend/main.py`): when
`ALLOWED_ORIGINS` is set it allows the deployed frontend domain; when unset it
keeps the original localhost list, so local development is untouched.

## What was added (deployment artifacts)

| File | Purpose |
|------|---------|
| `render.yaml` | Render Blueprint: backend Web Service (Docker) + frontend Static Site |
| `backend/Dockerfile` | Linux image: Python 3.11-slim + Pango/Cairo (WeasyPrint) + app |
| `backend/.dockerignore` | Keeps secrets, logs, fixtures out of the image |
| `frontend/.env.example` | Documents `VITE_API_URL` (build-time API base) |
| `.gitignore` | Never commit `.env`, `node_modules`, logs, builds |

## Linux PDF-engine verification (the flagged risk)

On Linux, `requirements.txt` installs **WeasyPrint** (`sys_platform != "win32"`).
The Docker image apt-installs its native deps (Pango/Cairo/gdk-pixbuf). Even if
WeasyPrint fails to import on a given host, `template_engine.py` auto-falls back
to pure-Python **xhtml2pdf** — the exact engine your local Windows build uses —
so PDF output is guaranteed. After deploy, confirm which engine is live via
`GET /health` → `"pdf_engine": "weasyprint"` (or `"xhtml2pdf"`).

## Step 1 — put the project on GitHub

```bash
cd "C:\Users\HP\Downloads\Projects\ResumeBuilder"
git init
git add -A
git commit -m "Resume Fixer - deploy-ready (env CORS + Docker + Render blueprint)"
git branch -M main
git remote add origin https://github.com/vikas2286/resume-fixer.git
git push -u origin main
```

(If `git push` prompts, use your GitHub PAT / Git Credential Manager. Do NOT
commit `.env` — `.gitignore` protects it; verify with `git status --ignored`.)

## Step 2 — deploy via Render Blueprint

1. Create a free account at https://render.com (sign in with your GitHub).
2. Dashboard → **New → Blueprint** → pick the `resume-fixer` repo.
3. Render auto-detects `render.yaml` and creates **two** services:
   - `resume-fixer-backend` (Web Service, Docker) → `https://resume-fixer-backend.onrender.com`
   - `resume-fixer-frontend` (Static Site, Vite build) → `https://resume-fixer-frontend.onrender.com`
4. In the **backend** service → Environment, set these **secret** env vars:
   - `GEMINI_API_KEY` → your Google AI Studio key (never in the repo)
   - `ALLOWED_ORIGINS` → `https://resume-fixer-frontend.onrender.com`
   - (optional) `GEMINI_MODEL` default is already `gemini-3.5-flash-lite`
5. Click **Manual Deploy → Deploy latest commit**. Wait for "Live".
6. The frontend's `VITE_API_URL` is wired to the backend via `render.yaml`
   (`fromService`), so no manual linking needed.

> **Single instance:** sessions are in-memory (2h TTL). Keep the backend on
> **1 instance** (Render free tier default) — scaling to >1 breaks session
> stickiness. Fine for demos/judging.

## Step 3 — smoke-test the live URL

- Backend health: `https://resume-fixer-backend.onrender.com/health`
  → expect `{"status":"ok","gemini":true,"pdf_engine":"weasyprint"|"xhtml2pdf"}`
- Frontend: `https://resume-fixer-frontend.onrender.com` → dark upload screen

Then upload one of the 7 reference fixtures (e.g. `backend/ashmit_resume.pdf`):
score ring → Fix My Resume → 1-page PDF → Download PDF.

## Rollback / local fallback

Local stack (`localhost:5173` + `:8000`) is untouched: CORS defaults to the
localhost list when `ALLOWED_ORIGINS` is unset, and `VITE_API_URL` defaults to
`http://localhost:8000`. If the deployed version misbehaves during judging,
demo from local — identical code.
