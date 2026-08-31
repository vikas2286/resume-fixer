import { useState } from "react";
import RedFlagList from "./RedFlagList.jsx";
import JDMatchPanel from "./JDMatchPanel.jsx";
import { ringColor } from "./ScoreRing.jsx";

function PillScore({ label, score }) {
  const color = ringColor(score);
  return (
    <div className="flex-1 bg-surface-2/70 border border-line rounded-md p-3 text-center">
      <div className="text-[10px] uppercase tracking-widest text-faint">{label}</div>
      <div className="text-2xl font-bold" style={{ color }}>{score}</div>
    </div>
  );
}

function CompareChecks({ before, after }) {
  if (!before || !after) return null;
  return (
    <table className="w-full text-sm my-3">
      <thead><tr>
        <th className="text-left py-1.5 text-xs uppercase tracking-widest text-faint font-medium">Check</th>
        <th className="text-center py-1.5 text-xs uppercase tracking-widest text-faint font-medium">Before</th>
        <th className="text-center py-1.5 text-xs uppercase tracking-widest text-faint font-medium">After</th></tr></thead>
      <tbody>
        {before.checks.map((b) => {
          const a = after.checks.find((x) => x.check === b.check);
          const aOk = a?.passed;
          return (
            <tr key={b.check} className="border-t border-line/70">
              <td className="py-1.5 text-mute">{b.check.replace(/_/g, " ")}</td>
              <td className={b.passed ? "text-success text-center" : "text-danger text-center"}>
                {b.passed ? "pass" : "FAIL"}
              </td>
              <td className={aOk === undefined ? "text-faint text-center" :
                                  aOk ? "text-success text-center" : "text-danger text-center"}>
                {aOk ? "pass" : aOk === false ? "FAIL" : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function JDTrigger({ onSubmit, busy, setBusy, setErr }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const go = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true); setErr(null);
    try { await onSubmit(text); }
    catch (err) { setErr(err.message); }
    finally { setBusy(false); }
  };
  return (
    <div className="relative">
      {open ? (
        <form onSubmit={go} className="flex gap-2 items-start">
          <textarea value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Paste the job description here…"
            className="w-72 h-24 bg-surface-2 border border-line rounded-md p-2 text-sm
                       resize-y text-ink placeholder:text-faint
                       focus:outline-none focus:border-primary/60" />
          <div className="flex flex-col gap-1">
            <button type="submit" disabled={busy} className="btn-primary text-sm">
              {busy ? "Matching…" : "Match"}
            </button>
            <button type="button"
                    onClick={() => { setOpen(false); setText(""); }}
                    className="btn-ghost text-sm">
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button onClick={() => setOpen(true)} disabled={busy} className="btn-ghost">
          Match Against Job Description
        </button>
      )}
    </div>
  );
}

export default function DiffView({ before, after, scores, fixedUrl, origUrl,
                                  jd, redFlags, engine, onJdSubmit,
                                  onRedFlags, busy, setBusy, setErr }) {
  const beforeObj = before || scores;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold tracking-tight">Before / After</h2>
        <div className="flex items-center gap-3 text-2xl font-extrabold tracking-tight">
          <span className="text-faint">{beforeObj?.overall}</span>
          <span className="text-primary">→</span>
          <span style={{ color: ringColor(after?.overall) }}>{after?.overall}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div className="card p-5 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-mute">
            ATS parseability
          </h3>
          <div className="flex gap-3">
            <PillScore label="before" score={beforeObj?.ats?.score} />
            <PillScore label="after" score={after?.ats?.score} />
          </div>
        </div>
        <div className="card p-5 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-mute">
            Visual / recruiter
          </h3>
          <div className="flex gap-3">
            <PillScore label="before" score={beforeObj?.visual?.score} />
            <PillScore label="after" score={after?.visual?.score} />
          </div>
        </div>
      </div>

      <div className="card p-5 overflow-x-auto">
        <CompareChecks before={beforeObj?.ats} after={after?.ats} />
        <CompareChecks before={beforeObj?.visual} after={after?.visual} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card overflow-hidden">
          <div className="bg-surface-2/80 border-b border-line px-4 py-2 text-xs
                          font-semibold uppercase tracking-widest text-mute
                          flex justify-between items-center">
            <span>Before (your upload)</span>
          </div>
          {origUrl ? (
            <iframe src={origUrl} title="before" className="w-full h-[420px] bg-white" />
          ) : (
            <div className="p-6 text-sm text-faint">
              Original PDF preview is only available for PDF uploads (DOCX must be
              saved as PDF to preview).
            </div>
          )}
        </div>
        <div className="card overflow-hidden border-primary/30">
          <div className="bg-primary/10 border-b border-primary/20 px-4 py-2 text-xs
                          font-semibold uppercase tracking-widest text-primary
                          flex justify-between items-center">
            <span>After (fixed)</span>
            {fixedUrl && (
              <a href={fixedUrl} download="resume_fixed.pdf"
                 className="text-xs normal-case tracking-normal hover:underline">
                Download PDF ↓
              </a>
            )}
          </div>
          {fixedUrl ? (
            <iframe src={fixedUrl} title="after" className="w-full h-[420px] bg-white" />
          ) : (
            <div className="p-6 text-sm text-faint">No fixed resume yet.</div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button onClick={onRedFlags} disabled={busy} className="btn-ghost">
          {busy ? "Scanning…" : "Re-scan Red Flags"}
        </button>
        <JDTrigger onSubmit={onJdSubmit} busy={busy} setBusy={setBusy} setErr={setErr} />
      </div>

      {redFlags && <RedFlagList flags={redFlags} engine={engine} />}
      {jd && <JDMatchPanel result={jd} />}
    </div>
  );
}

