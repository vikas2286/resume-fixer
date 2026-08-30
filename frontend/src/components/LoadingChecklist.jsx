import { useEffect, useState } from "react";

export const ANALYZE_STEPS = [
  "Reading resume structure…",
  "Checking ATS parseability…",
  "Analyzing visual formatting…",
  "Scanning for red flags…",
];

export const FIX_STEPS = [
  "Rendering a clean ATS-safe template…",
  "Re-scoring the fixed PDF…",
  "Preparing the before/after comparison…",
];

function StepRow({ text, state }) {
  // state: "pending" | "active" | "done"
  return (
    <li className={`flex items-center gap-3 transition-all duration-300
                    ${state === "pending" ? "opacity-35" : "opacity-100"}`}>
      <span className="flex h-5 w-5 shrink-0 items-center justify-center">
        {state === "done" ? (
          <span className="flex h-5 w-5 items-center justify-center rounded-full
                           bg-success/15 text-success text-xs font-bold
                           border border-success/40 animate-fadeUp">✓</span>
        ) : state === "active" ? (
          <span className="h-3 w-3 rounded-full bg-primary animate-pulseSoft
                           shadow-glow ring-2 ring-primary/30" />
        ) : (
          <span className="h-2.5 w-2.5 rounded-full bg-line" />
        )}
      </span>
      <span className={`text-sm ${state === "done" ? "text-mute" :
                        state === "active" ? "text-ink font-medium" : "text-faint"}`}>
        {text}
      </span>
    </li>
  );
}

/**
 * Progressive step checklist shown while a request runs. Steps advance on a
 * timer (visual pacing only — real progress data isn't available); when the
 * request outlives the script, the last step keeps pulsing.
 */
export default function LoadingChecklist({ steps, title, intervalMs = 900 }) {
  const [done, setDone] = useState(0);

  useEffect(() => {
    setDone(0);
    const iv = setInterval(
      () => setDone((d) => Math.min(d + 1, steps.length)),
      intervalMs,
    );
    return () => clearInterval(iv);
  }, [steps, intervalMs]);

  const finished = done >= steps.length;

  return (
    <div className="card p-6 animate-fadeUp max-w-md mx-auto">
      <div className="flex items-center gap-3 mb-4">
        <span className="h-2.5 w-2.5 rounded-full bg-primary animate-pulseSoft" />
        <h3 className="text-sm font-semibold uppercase tracking-widest text-mute">
          {title || "Working"}
        </h3>
      </div>
      <ul className="space-y-3">
        {steps.map((text, i) => (
          <StepRow key={text} text={text}
                   state={i < done ? "done" : i === done ? "active" : "pending"} />
        ))}
      </ul>
      {finished && (
        <p className="mt-4 text-xs text-faint animate-pulseSoft">
          Still working — large files take a little longer…
        </p>
      )}
    </div>
  );
}
