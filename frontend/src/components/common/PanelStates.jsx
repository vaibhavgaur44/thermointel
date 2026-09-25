import { AlertTriangle, Loader2, Inbox } from "lucide-react";

export const LoadingState = ({ label = "Loading", testId }) => (
  <div
    data-testid={testId}
    className="flex items-center gap-2 px-1 py-6 text-slate-400"
  >
    <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-400" />
    <span className="font-mono text-[11px] uppercase tracking-[0.2em]">
      {label}
    </span>
  </div>
);

export const ErrorState = ({ message, testId }) => (
  <div
    data-testid={testId}
    className="flex items-start gap-2 rounded border border-red-500/30 bg-red-500/5 px-3 py-3"
  >
    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-400" />
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-red-300">
        Request failed
      </p>
      <p className="mt-1 text-xs text-slate-400">{message}</p>
    </div>
  </div>
);

export const EmptyState = ({ title, detail, testId }) => (
  <div
    data-testid={testId}
    className="rounded border border-dashed border-slate-700/60 px-3 py-6"
  >
    <div className="flex items-center gap-2">
      <Inbox className="h-3.5 w-3.5 text-slate-300" />
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
        {title}
      </p>
    </div>
    {detail && <p className="mt-2 text-xs leading-relaxed text-slate-300">{detail}</p>}
  </div>
);
