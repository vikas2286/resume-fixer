function Chip({ children, color }) {
  const cls = {
    green: "bg-success/10 text-success border-success/30",
    red: "bg-danger/10 text-danger border-danger/30",
    blue: "bg-primary/10 text-primary border-primary/30",
  }[color] || "bg-surface-2 text-mute border-line";
  return (
    <span className={`text-xs px-2.5 py-0.5 rounded border ${cls}`}>
      {children}
    </span>
  );
}

export default function JDMatchPanel({ result }) {
  if (!result) return null;
  const match = result.match_score;
  const color = match >= 70 ? "green" : match >= 40 ? "blue" : "red";
  const barColor = match >= 70 ? "#34d399" : match >= 40 ? "#22d3ee" : "#f87171";
  return (
    <div className="card p-5 pt-2 space-y-3 animate-fadeUp">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-mute">
          Job-Description Match
        </h3>
        <Chip color={color}>matched via {result.engine}</Chip>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-2xl font-bold" style={{ color: barColor }}>
          {match}%<span className="text-sm text-faint font-normal"> match</span>
        </div>
        <div className="flex-1 h-2 bg-surface-2 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-700"
               style={{ width: `${match}%`, background: barColor }}></div>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        <div className="bg-surface-2/70 border border-line rounded-xl p-3">
          <h4 className="font-medium text-success mb-2 text-xs uppercase
                         tracking-widest">
            Present in your resume
          </h4>
          {result.matched?.length ? (
            <div className="flex flex-wrap gap-1">
              {result.matched.map((m, i) => <Chip key={i} color="green">{m.keyword}</Chip>)}
            </div>
          ) : <p className="text-faint text-xs">None of the key JD terms appear.</p>}
        </div>
        <div className="bg-surface-2/70 border border-line rounded-xl p-3">
          <h4 className="font-medium text-danger mb-2 text-xs uppercase
                         tracking-widest">
            Missing — add these to land the role
          </h4>
          {result.missing?.length ? (
            <div className="flex flex-wrap gap-1">
              {result.missing.map((m, i) => <Chip key={i} color="red">{m.keyword}</Chip>)}
            </div>
          ) : <p className="text-faint text-xs">Nothing critical missing.</p>}
        </div>
      </div>
    </div>
  );
}
