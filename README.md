# Resume Fixer

A tool that takes a messy, unprofessional resume and:

1. **Diagnoses** why it fails the recruiter "3-second filter" with a dual score
   (ATS parseability + visual/recruiters score), each check explained.
2. **Auto-fixes** it into a clean, ATS-safe resume via a Jinja2 → PDF pipeline,
   then re-scores the fixed version for a side-by-side **before/after diff**.
3. **Optionally** matches the resume to a job description and flags weak/cliché
   content using Gemini (graceful rule-based fallbacks when no API key is set).

**Core demo loop:** Upload messy resume → see the score tank → click *Fix* → see
the clean version + score jump, side by side. The entire loop works with **zero
API keys** (Gemini is optional).

---

## Architecture

```
resume-fixer/
├── frontend/                     # React + Vite + Tailwind UI
│   ├── src/
│   │   ├── api/client.js         # fetch wrappers for every endpoint
│   │   ├── App.jsx               # state machine: idle → diagnosis → diff
│   │   └── components/
│   │       ├── UploadZone.jsx
│   │       ├── DiagnosisScreen.jsx
│   │       ├── DiffView.jsx      # before/after iframes + score table
│   │       ├── JDMatchPanel.jsx
│   │       └── RedFlagList.jsx
│   └── dist/                     # production build
├── backend/
│   ├── main.py                   # FastAPI app (7 endpoints, in-mem session)
│   ├── parser.py                 # PyMuPDF / python-docx → structured JSON
│   ├── scoring.py                # rule-based ATS + visual scores + reasons
│   ├── llm_service.py            # Gemini: rewrite / red-flags / JD-match
│   ├── template_engine.py        # Jinja2 HTML → PDF (WeasyPrint w/ fallback)
│   ├── templates/
│   │   ├── classic.html
│   │   └── modern.html
│   ├── session_store.py          # thread-safe in-memory dict (swap for Redis)
│   └── test_e2e.py               # run the whole pipeline without a server
└── README.md
```

### Backend services

| Component | Tech | Notes |
|---|---|---|
| API / orchestration | FastAPI + Uvicorn | CORS enabled for `localhost:5173` |
| Parser | PyMuPDF (`fitz`) + `python-docx` | extracts text, fonts, sizes, line geometry, tables, multi-column detection, header/footer contact check |
| Scoring | pure-Python rules | deterministic, explainable, no ML. ATS = 70% of overall, Visual = 30% |
| LLM (optional) | Gemini 1.5 Flash | bullet rewriting, red-flag detection, JD keyword matching, resume structuring |
| Rendering | WeasyPrint → xhtml2pdf fallback | **Windows has no GTK**, so the fallback is used automatically there |
| Session store | in-memory dict | keyed by `session_id`, 2h TTL |

### Frontend

React 18 + Vite + Tailwind. Proxies `/upload`, `/score`, `/generate`, etc. to
`http://localhost:8000` during dev. Built static output in `frontend/dist/`.

---

## Setup & run (dev)

```bash
# backend
cd backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# frontend (in a second terminal)
cd frontend
npm install
npm run dev      # serves on http://localhost:5173
```

### One-shot verification (backend, no server needed)

```bash
cd backend
python make_sample_resume.py     # creates messy_resume.pdf
python test_e2e.py               # uploads -> scores -> fixes -> rescues
```

Typical result:

```
BEFORE overall=51 ats=65 visual=30
AFTER  overall=86 ats=90 visual=80
SCORE JUMP: 51 -> 86 (+35)
```

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/upload` | PDF/DOCX → parse + initial score; returns `session_id` + trimmed parse preview |
| `GET`  | `/score/{sid}` | ATS + visual score + per-check reasons |
| `POST` | `/rewrite/{sid}` | LLM bullet rewrite (requires `GEMINI_API_KEY`, else 503) |
| `POST` | `/redflags/{sid}` | cliché / passive-voice / missing-metrics scan |
| `POST` | `/jdmatch/{sid}` | body `{jd_text}` → keyword gap + relevance ranking |
| `POST` | `/generate/{sid}?template=classic\|modern` | render fixed PDF, re-score, return file + `X-Overall-Before/After` headers |
| `GET`  | `/rescore/{sid}` | the "after" scores from the generated PDF |
| `GET`  | `/original/{sid}` | original PDF preview for the before-side iframe |
| `GET`  | `/health` | `status`, `gemini`, `pdf_engine` |

The scoring rubric is in `backend/scoring.py` — each check returns
`{check, passed, reason}` and is shown verbatim on the diagnosis screen.

---

## Optional: Gemini

```bash
export GEMINI_API_KEY="YOUR_KEY"   # Windows: setx GEMINI_API_KEY YOUR_KEY
```

With a key set, `/rewrite`, the LLM path of `/redflags`, `/jdmatch`, and
LLM-based resume structuring light up. **Without a key the app still does 100%
of the demo**: rule-based scoring, rule-based red-flag scan, rule-based JD
keyword matching, and template-based PDF auto-fix.

---

## Production build

```bash
cd frontend
npm run build          # -> frontend/dist/
```

Serve `frontend/dist/` with any static file server; set `VITE_API_URL` (defaults
to `http://localhost:8000`) at build time if the backend lives elsewhere.

### Run both together (production)

```bash
# backend
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000

# static frontend
npx serve ../frontend/dist   # or any static server
```
