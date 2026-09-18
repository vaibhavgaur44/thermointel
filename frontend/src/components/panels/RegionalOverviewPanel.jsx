import { Panel, PanelBody, PanelHeader } from "@/components/common/Panel";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/common/PanelStates";
import { OVERVIEW_ORDER, eventTypeMeta } from "@/constants/taxonomy";
import { useRegionalOverview } from "@/hooks/useThermoIntel";
import { useDashboard } from "@/state/DashboardContext";

const CountRow = ({ eventType, count }) => {
  const meta = eventTypeMeta(eventType);
  return (
    <li
      data-testid={`overview-row-${eventType.toLowerCase()}`}
      className="flex items-center justify-between gap-3 border-b border-slate-800/50 py-2 last:border-0"
    >
      <span className="flex min-w-0 items-center gap-2.5">
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{
            backgroundColor: meta.color,
            boxShadow: `0 0 10px ${meta.color}80`,
          }}
        />
        <span className="truncate text-[13px] text-slate-300">{meta.label}</span>
      </span>
      <span
        data-testid={`overview-count-${eventType.toLowerCase()}`}
        className="font-mono text-sm font-semibold tabular-nums text-slate-100"
      >
        {count}
      </span>
    </li>
  );
};

export const RegionalOverviewPanel = () => {
  const { filters, setRegion } = useDashboard();
  const { data, isLoading, error } = useRegionalOverview();
  const regionName = filters.region?.name || "India";

  return (
    <Panel testId="regional-overview-panel" className="w-full">
      <PanelHeader
        eyebrow="Regional Overview"
        title={regionName}
        right={
          filters.region ? (
            <button
              type="button"
              data-testid="overview-reset-region-button"
              onClick={() => setRegion(null)}
              className="shrink-0 rounded-sm border border-slate-700/60 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400 transition-colors duration-200 hover:border-sky-400/60 hover:text-sky-300"
            >
              All India
            </button>
          ) : null
        }
      />
      <PanelBody>
        {isLoading && <LoadingState testId="overview-loading" />}
        {error && <ErrorState message={error.message} testId="overview-error" />}
        {data && (
          <>
            <div className="flex items-end justify-between border-b border-slate-800/60 pb-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-slate-300">
                Total Events
              </span>
              <span
                data-testid="overview-total-events"
                className="font-mono text-3xl font-bold leading-none tabular-nums text-slate-50"
              >
                {data.total_events}
              </span>
            </div>
            {data.total_events === 0 ? (
              <div className="pt-3">
                <EmptyState
                  testId="overview-empty"
                  title="No events in scope"
                  detail="FIRMS ingestion and event formation are delivered in a later phase. Enable DEMO DATA to exercise the interface."
                />
              </div>
            ) : (
              <ul className="pt-1">
                {OVERVIEW_ORDER.filter(
                  (t) => t !== "UNKNOWN_AGRICULTURAL_FIRE" ||
                    (data.by_event_type?.UNKNOWN_AGRICULTURAL_FIRE || 0) > 0,
                ).map((eventType) => (
                  <CountRow
                    key={eventType}
                    eventType={eventType}
                    count={data.by_event_type?.[eventType] ?? 0}
                  />
                ))}
                {data.unclassified_events > 0 && (
                  <CountRow
                    eventType="UNCLASSIFIED"
                    count={data.unclassified_events}
                  />
                )}
              </ul>
            )}
            <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">
              Scope · {data.status_scope}
            </p>
          </>
        )}
      </PanelBody>
    </Panel>
  );
};
