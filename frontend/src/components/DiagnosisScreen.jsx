import ScoreRing, { MiniRing, ringColor } from "./ScoreRing.jsx";

const humanize = (s) =>
  (s || "").replace(/_/g, " ").replace(/^\w/, (ch) => ch.toUpperCase());

function CheckRow({ check }) {
  return (
    <li className="flex gap-2.5 items-baseline py-1 border-b border-line/60 last:border-0">
      <span className="w-4 shrink-0 text-center font-bold">
        {check.passed
          ? <span className="text-success">✓</span>
          : <span className="text-danger">✗</span>}
      </span>
      <span className={"shrink-0 text-xs font-medium " +
        (check.passed ? "text-mute" : "text-ink")}>
        {humanize(check.check)}
      </span>
      <span className="text-xs text-faint flex-1">{check.reason}</span>
    </li>
  );
}

function ScorePanel({ title, scoreObj }) {
  if (!scoreObj) return null;
  const checks = scoreObj.checks || [];
  const passedCount = checks.filter((c) => c.passed).length;
  return (
    <div className="card p-5 animate-fadeUp">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-mute">
          {title}
        </h3>
        <span className="text-sm font-bold"
              style={{ color: ringColor(scoreObj.score) }}>
          {scoreObj.score}<span className="text-faint font-normal">/100</span>
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden mb-4">
        <div className="h-full rounded-full transition-all duration-700"
             style={{ width: scoreObj.score + "%",
                      background: ringColor(scoreObj.score) }} />
      </div>
      <p className="text-xs text-faint mb-2">
        {passedCount}/{checks.length} checks passed
      </p>
      <ul>
        {checks.map((c) => <CheckRow key={c.check} check={c} />)}
      </ul>
    </div>
  );
}

function NextSteps({ failed }) {
  return (
    <div className="card p-5 border-warn/30 animate-fadeUp">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-warn">
          Next steps
        </h3>
        <span className="text-xs text-faint">
          {failed.length} fix{failed.length === 1 ? "" : "es"} needed
        </span>
      </div>
      {failed.length === 0 ? (
        <p className="text-sm text-success flex items-center gap-2">
          <span className="font-bold">✓</span>
          All checks passed — nothing blocking a clean render.
        </p>
      ) : (
        <ul className="space-y-2">
          {failed.map((c, i) => (
            <li key={c.check + i}
                className="flex items-start gap-2.5 bg-surface-2/70 border border-line
                           rounded-md px-3 py-2 text-sm animate-fadeUp">
              <span className="text-warn shrink-0 mt-0.5">⚠</span>
              <span>
                <span className="text-ink font-medium">{humanize(c.check)}</span>
                {c.reason && (
                  <span className="text-faint text-xs"> — {c.reason}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Evidence({ parsed }) {
  if (!parsed) return null;
  const row = "flex gap-2 text-xs";
  return (
    <div className="card p-5 text-mute animate-fadeUp">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-faint mb-3">
        Parsed evidence
      </h3>
      <div className={row}><span className="text-faint w-24 shrink-0">Type</span>
        <span>{parsed.file_type.toUpperCase()} · {parsed.n_pages} page(s)</span></div>
      <div className={row}><span className="text-faint w-24 shrink-0">Fonts</span>
        <span className="truncate">{parsed.fonts.join(", ") || "(none)"}</span></div>
      <div className={row}><span className="text-faint w-24 shrink-0">Layout</span>
        <span>multi-column: {parsed.multicolumn ? "yes" : "no"} · tables: {parsed.has_tables ? "yes" : "no"}</span></div>
      <div className={row}><span className="text-faint w-24 shrink-0">Sections</span>
        <span>{(parsed.sections_found || []).join(", ") || "(none)"}</span></div>
      <p className="mt-2 truncate text-xs text-faint">
        Preview: {parsed.preview_text}…
      </p>
    </div>
  );
}

export default function DiagnosisScreen({ parsed, scores, gemini, template,
                                          setTemplate, busy, onRedFlags,
                                          onFix, onRewrite, rewrittenCount,
                                          fixAssessment, usage }) {
  if (!scores) return null;
  const minorMode = fixAssessment && !fixAssessment.needs_major_fix;
  const suggestions = (minorMode && fixAssessment.minor_suggestions) || [];

  // Daily AI usage: show remaining actions and disable the AI-powered
  // buttons once the limit is hit.  Admins (usage.admin) see nothing.
  const limitHit = !!(usage && !usage.admin && usage.gemini
                      && usage.remaining !== null && usage.remaining <= 0);
  const usageBadge = (usage && !usage.admin && usage.gemini
                      && usage.remaining !== null) ? (
    limitHit
      ? `Daily AI limit reached (${usage.used}/${usage.limit}) — resets at ${usage.resets_at}`
      : `${usage.remaining} AI action${usage.remaining === 1 ? "" : "s"} remaining today`
  ) : null;

  // "Next steps" digest: every FAILED check across all score groups,
  // derived straight from the existing pass/fail data (no backend changes).
  const failedChecks = [
    ...(scores.content?.checks || []),
    ...(scores.ats?.checks || []),
    ...(scores.visual?.checks || []),
  ].filter((c) => c && c.passed === false);

  return (
    <div className="space-y-6">
      {/* ---- hero: overall gauge + sub-score mini rings ---- */}
      <div className="card p-8">
        <div className="flex flex-col sm:flex-row items-center gap-8">
          <ScoreRing score={scores.overall} size={190} stroke={13} />
          <div className="flex-1">
            <h2 className="text-2xl font-bold tracking-tight mb-1">
              Resume Diagnosis
            </h2>
            <p className="text-sm text-faint mb-5">
              Rule-based scoring across ATS parseability, visual formatting
              and content quality.
            </p>
            <div className="flex flex-wrap gap-6">
              <MiniRing score={scores.ats?.score} label="ATS" />
              <MiniRing score={scores.visual?.score} label="Visual" />
              {scores.content && (
                <MiniRing score={scores.content.score} label="Content" />
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ---- at-a-glance: failed checks only ---- */}
      <NextSteps failed={failedChecks} />

      {/* ---- fix-mode assessment banners ---- */}
      {minorMode ? (
        <div className="card p-5 border-success/30 animate-fadeUp">
          <p className="font-medium text-success mb-3">
            ✓ {fixAssessment.message}
          </p>
          <ul className="space-y-2">
            {suggestions.map((f, i) => (
              <li key={i} className="bg-surface-2/70 border border-line rounded-md p-3">
                <span className="inline-block text-[10px] font-semibold uppercase
                                 tracking-wider px-1.5 py-0.5 rounded bg-warn/10
                                 text-warn border border-warn/30 mr-2">
                  {String(f.type || "suggestion").replace(/_/g, " ")}
                </span>
                <span className="text-sm text-ink">{f.quote}</span>
                {f.fix && <span className="block text-xs text-faint mt-1">→ {f.fix}</span>}
              </li>
            ))}
            {suggestions.length === 0 && (
              <li className="text-sm text-mute">No wording issues found at all.</li>
            )}
          </ul>
        </div>
      ) : (
        <div className="card p-4 border-danger/40 text-sm text-danger animate-fadeUp">
          {fixAssessment ? fixAssessment.message
            : "This resume has structural problems — use the full fix below."}
        </div>
      )}

      {/* ---- full pass/fail breakdown ---- */}
      {scores.content && <ScorePanel title="Content quality" scoreObj={scores.content} />}
      <ScorePanel title="ATS parseability" scoreObj={scores.ats} />
      <ScorePanel title="Visual / recruiter" scoreObj={scores.visual} />

      <Evidence parsed={parsed} />

      {!gemini && (
        <div className="card p-3 border-warn/30 text-xs text-warn animate-fadeUp">
          Gemini API key not set — AI bullet rewriting &amp; JD-match are disabled.
          Scoring, red-flag scanning and the auto-fix template still work.
        </div>
      )}

      {/* ---- actions ---- */}
      <div className="flex flex-wrap gap-3 pt-1 items-center">
        <button onClick={onRedFlags} disabled={busy} className="btn-ghost">
          {busy ? "Scanning…" : "Scan Red Flags"}
        </button>
        {gemini && (
          <button onClick={onRewrite} disabled={busy || limitHit}
                  title={limitHit ? "Daily AI limit reached — resets tomorrow" : undefined}
                  className="btn bg-primary/15 text-primary border border-primary/40
                             hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed">
            {busy ? "Rewriting…" : "✨ AI Rewrite Bullets"}
          </button>
        )}
        <button onClick={onFix} disabled={busy || limitHit}
                title={limitHit ? "Daily AI limit reached — resets tomorrow" : undefined}
                className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed">
          {busy ? "Generating…"
            : (minorMode ? "Generate polished copy (optional) →" : "Fix My Resume →")}
        </button>
        {usageBadge && (
          <span className={"text-xs rounded-lg px-2.5 py-1.5 border " +
            (limitHit
              ? "text-danger bg-danger/10 border-danger/30"
              : "text-mute bg-surface-2 border-line")}>
            {limitHit ? `⛔ ${usageBadge}` : `⚡ ${usageBadge}`}
          </span>
        )}
        <label className="text-xs text-mute flex items-center gap-1.5">
          Template
          <select value={template} onChange={(e) => setTemplate(e.target.value)}
                  className="bg-surface-2 border border-line rounded-md px-2 py-1.5
                             text-xs text-ink focus:outline-none focus:border-primary/60">
            <option value="auto">Auto (recommended)</option>
            <option value="classic">Classic</option>
            <option value="modern">Modern</option>
          </select>
        </label>
        {rewrittenCount !== null && (
          <span className="text-xs text-success bg-success/10 border border-success/30
                           rounded-lg px-2.5 py-1.5">
            ✨ {rewrittenCount} bullet(s) rewritten — click “Fix My Resume” to apply.
          </span>
        )}
      </div>
    </div>
  );
}

