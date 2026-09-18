import { threatMeta } from "@/constants/taxonomy";

export const ThreatBadge = ({ level, score, testId }) => {
  const meta = threatMeta(level);
  const unassessed = !level;

  return (
    <span
      data-testid={testId}
      className="inline-flex items-center gap-1.5 rounded-sm border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em]"
      style={{
        borderColor: `${meta.color}59`,
        backgroundColor: `${meta.color}1f`,
        color: unassessed ? "#94a3b8" : meta.color,
      }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: meta.color }}
      />
      {meta.label}
      {typeof score === "number" && (
        <span className="text-slate-300/80">{score.toFixed(1)}</span>
      )}
    </span>
  );
};

/**
 * Model confidence is a calibrated probability produced by the ML stack.
 * No value exists until Phase 4/5, so the unavailable state is explicit.
 */
export const ConfidenceReadout = ({ confidence, testId }) => {
  const available = typeof confidence === "number";
  return (
    <div data-testid={testId} className="flex items-baseline gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-300">
        Model confidence
      </span>
      <span
        className={
          available
            ? "font-mono text-sm font-semibold text-slate-100"
            : "font-mono text-[11px] uppercase tracking-[0.14em] text-amber-400/80"
        }
      >
        {available ? `${Math.round(confidence * 100)}%` : "Unavailable"}
      </span>
    </div>
  );
};

export const EventTypeTag = ({ meta, testId }) => (
  <span
    data-testid={testId}
    className="inline-flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.16em]"
    style={{ color: meta.color }}
  >
    <span
      className="h-2 w-2 rounded-full ring-2"
      style={{ backgroundColor: meta.color, ringColor: meta.color }}
    />
    {meta.short || meta.label}
  </span>
);
