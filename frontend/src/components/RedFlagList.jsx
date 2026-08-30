export default function RedFlagList({ flags, engine }) {
  if (!flags || flags.length === 0) return null;
  return (
    <div className="space-y-3 pt-2 animate-fadeUp">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-mute">
          Red-Flag Scanner
        </h3>
        <span className="text-xs text-faint">engine: {engine}</span>
      </div>
      <div className="space-y-3">
        {flags.map((f, i) => (
          <div key={i} className="card p-4 border-l-4 border-l-danger animate-fadeUp">
            <span className="inline-block text-[10px] font-semibold uppercase
                             tracking-wider px-2 py-0.5 rounded bg-danger/10
                             text-danger border border-danger/30">
              {f.type.replace("_", " ")}
            </span>
            <blockquote className="text-sm italic text-ink mt-2">
              “{f.quote}”
            </blockquote>
            <p className="text-sm text-mute mt-2"><b className="text-ink">Hurts:</b> {f.issue}</p>
            <p className="text-sm text-mute mt-0.5"><b className="text-ink">Try:</b> {f.fix}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

