import { useState } from "react";
import * as api from "./api/client.js";
import UploadZone from "./components/UploadZone.jsx";
import DiagnosisScreen from "./components/DiagnosisScreen.jsx";
import DiffView from "./components/DiffView.jsx";
import LoadingChecklist, { FIX_STEPS } from "./components/LoadingChecklist.jsx";


export default function App() {
  const [status, setStatus] = useState("idle"); // idle | uploading | diagnosis | fixing | diff
  const [session, setSession] = useState(null);
  const [parsed, setParsed] = useState(null);
  const [scores, setScores] = useState(null);
  const [gemini, setGemini] = useState(false);
  const [after, setAfter] = useState(null);
  const [beforeScore, setBeforeScore] = useState(null);
  const [fixedUrl, setFixedUrl] = useState(null);
  const [origUrl, setOrigUrl] = useState(null);
    const [redFlags, setRedFlags] = useState(null);
  const [rewrittenCount, setRewrittenCount] = useState(null);
  const [engine, setEngine] = useState("rules");
  const [jd, setJd] = useState(null);
  const [template, setTemplate] = useState("auto");
  const [fixAssessment, setFixAssessment] = useState(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("");
  const [err, setErr] = useState(null);

  const onUploaded = (res) => {
    setSession(res.session_id);
    setParsed(res.parsed);
    setScores(res.scores);
    setBeforeScore(res.scores);
    setGemini(res.gemini_enabled);
    setFixAssessment(res.fix_assessment || null);
    setStatus("diagnosis");
  };

    const runRedFlags = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.redflags(session);
      setRedFlags(r.flags); setEngine(r.engine);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  };

  const runRewrite = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.rewrite(session);
      setRewrittenCount(r.bullets_rewritten);
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  };

  const runFix = async () => {
    setStatus("fixing"); setErr(null);
    try {
      const g = await api.generatePdf(session, template);
      const url = URL.createObjectURL(g.blob);
      setFixedUrl(url);
      setAfter({ overall: parseInt(g.after, 10), });
      // fetch the structured after-scores
      const r = await api.rescore(session);
      setAfter(r.after);
      setBeforeScore(r.before);
      // original preview (pdf only)
      const ob = await api.originalPdfBlob(session);
      if (ob) setOrigUrl(URL.createObjectURL(ob));
      setStatus("diff");
    } catch (e) { setErr(e.message); setStatus("diagnosis"); }
    finally { setBusy(false); }
  };

  const onJdSubmit = async (jdText) => {
    setBusy(true); setErr(null);
    try {
      setJd(await api.jdmatch(session, jdText));
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  };

  const reset = () => {
    setSession(null); setParsed(null); setScores(null); setAfter(null);
    setFixedUrl(fixedUrl && URL.revokeObjectURL(fixedUrl)); setOrigUrl(null);
    setRedFlags(null); setJd(null); setErr(null); setBusy(false);
    setStatus("idle");
  };

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-10 bg-canvas/80 backdrop-blur border-b border-line">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl
                             bg-gradient-to-br from-primary to-primary-dim
                             text-canvas font-extrabold shadow-glow">R</span>
            <h1 className="text-lg font-bold tracking-tight">Resume Fixer</h1>
          </div>
          {status === "diff" && (
            <button onClick={reset} className="btn-ghost text-xs">
              New Resume
            </button>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {err && (
          <div className="card p-3 border-danger/40 text-sm text-danger animate-fadeUp">
            {err}
          </div>
        )}

        {status === "idle" && (
          <UploadZone onUpload={onUploaded} busy={busy} setBusy={setBusy} setErr={setErr} />
        )}

        {status === "diagnosis" && (
                    <DiagnosisScreen
            parsed={parsed} scores={scores} gemini={gemini} template={template}
            setTemplate={setTemplate} busy={busy} busyLabel={busyLabel}
            onRedFlags={runRedFlags} onFix={runFix} onRewrite={runRewrite}
            rewrittenCount={rewrittenCount}
            fixAssessment={fixAssessment}
          />
        )}

        {status === "fixing" && (
          <LoadingChecklist steps={FIX_STEPS} title="Rebuilding your resume" />
        )}

                {status === "diff" && (
          <DiffView
            before={beforeScore} after={after} scores={scores}
            fixedUrl={fixedUrl} origUrl={origUrl}
            jd={jd} redFlags={redFlags} engine={engine}
            onJdSubmit={onJdSubmit} onRedFlags={runRedFlags}
            busy={busy} setBusy={setBusy} setErr={setErr}
          />
        )}
      </main>

      <footer className="text-center text-xs text-faint py-8">
        Resume Fixer · rule-based scoring (no API key needed) · set GEMINI_API_KEY for AI rewrites
      </footer>
    </div>
  );
}


