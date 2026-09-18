import { cn } from "@/lib/utils";

/** Floating translucent surface. The map must stay visible behind it. */
export const Panel = ({ className, children, testId }) => (
  <section
    data-testid={testId}
    className={cn(
       "pointer-events-auto rounded-xl border border-slate-600/35 bg-[#020817]/80 backdrop-blur-xl",
      "shadow-[0_18px_50px_-18px_rgba(0,0,0,0.9)]",
      className,
    )}
  >
    {children}
  </section>
);

export const PanelHeader = ({ eyebrow, title, right, testId }) => (
  <header
    data-testid={testId}
    className="flex items-start justify-between gap-3 border-b border-slate-700/40 px-4 py-3"
  >
    <div className="min-w-0">
      {eyebrow && (
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.24em] text-sky-300/70">
          {eyebrow}
        </p>
      )}
      <h2 className="truncate text-base font-semibold tracking-tight text-slate-50">
        {title}
      </h2>
    </div>
    {right}
  </header>
);

export const PanelBody = ({ className, children }) => (
  <div className={cn("px-4 py-3", className)}>{children}</div>
);
