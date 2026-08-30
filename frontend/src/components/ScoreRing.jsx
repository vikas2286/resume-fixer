import { useEffect, useState } from "react";

/**
 * Circular score gauge. The arc color encodes the score band
 * (red -> amber -> green) and the arc itself animates from empty to the
 * score's sweep on mount / score change.
 */
export function ringColor(score) {
  const s = Math.max(0, Math.min(100, Number(score) || 0));
  if (s >= 75) return "#34d399";   // success
  if (s >= 50) return "#fbbf24";   // warn
  return "#f87171";                // danger
}

export default function ScoreRing({
  score, size = 180, stroke = 12, label = "Overall", track = "#1c2740",
}) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const target = c - (c * pct) / 100;
  const [offset, setOffset] = useState(c); // start empty, animate to target

  useEffect(() => {
    setOffset(c);
    const id = requestAnimationFrame(() => setOffset(target));
    return () => cancelAnimationFrame(id);
  }, [target, c]);

  const color = ringColor(pct);

  return (
    <div className="flex flex-col items-center" style={{ width: size }}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                  stroke={track} strokeWidth={stroke} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                  stroke={color} strokeWidth={stroke} strokeLinecap="round"
                  strokeDasharray={c} strokeDashoffset={offset}
                  style={{
                    transition: "stroke-dashoffset 1s cubic-bezier(.22,.61,.36,1), stroke 0.4s",
                    filter: `drop-shadow(0 0 6px ${color}66)`,
                  }} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-extrabold tracking-tight"
                style={{ fontSize: size * 0.30, color, lineHeight: 1 }}>
            {Math.round(pct)}
          </span>
          <span className="text-faint" style={{ fontSize: size * 0.115 }}>
            / 100
          </span>
        </div>
      </div>
      <span className="mt-2 text-xs font-medium uppercase tracking-widest text-mute">
        {label}
      </span>
    </div>
  );
}

/** Compact variant for sub-scores next to the main gauge. */
export function MiniRing({ score, size = 72, stroke = 7, label }) {
  return (
    <ScoreRing score={score} size={size} stroke={stroke} label={label}
               track="#1a2440" />
  );
}
