import { Siren } from "lucide-react";

import { Panel, PanelBody, PanelHeader } from "@/components/common/Panel";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/common/PanelStates";
import { ThreatBadge } from "@/components/common/Indicators";
import { eventTypeMeta, sourceTypeLabel } from "@/constants/taxonomy";
import { useAlerts } from "@/hooks/useThermoIntel";
import { useDashboard } from "@/state/DashboardContext";

export const AlertQueuePanel = () => {
  const { data, isLoading, error } = useAlerts();
  const { selectEvent } = useDashboard();
  const alerts = data?.items || [];

  return (
    <Panel testId="alert-queue-panel" className="w-full">
      <PanelHeader
        eyebrow="Alert Queue"
        title={`${alerts.length} open`}
        right={<Siren className="mt-1 h-3.5 w-3.5 shrink-0 text-red-400/80" />}
      />
      {isLoading && (
        <PanelBody>
          <LoadingState testId="alerts-loading" />
        </PanelBody>
      )}
      {error && (
        <PanelBody>
          <ErrorState message={error.message} testId="alerts-error" />
        </PanelBody>
      )}
      {!isLoading && !error && alerts.length === 0 && (
        <PanelBody>
          <EmptyState
            testId="alerts-empty"
            title="No alerts raised"
            detail="Alerts are threat/anomaly outcomes. The alert threshold is intentionally undefined until it can be set from real data."
          />
        </PanelBody>
      )}
      {alerts.length > 0 && (
        <ul className="divide-y divide-slate-800/50">
          {alerts.map((alert) => {
            const meta = eventTypeMeta(alert.event_type);
            return (
              <li key={alert.alert_id}>
                <button
                  type="button"
                  data-testid={`alert-item-${alert.alert_id}`}
                  onClick={() => selectEvent(alert.event_id)}
                  className="w-full px-3 py-2.5 text-left transition-colors duration-200 hover:bg-slate-800/40"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span
                      className="truncate font-mono text-[10px] font-semibold uppercase tracking-[0.16em]"
                      style={{ color: meta.color }}
                    >
                      {meta.short || meta.label}
                    </span>
                    <ThreatBadge level={alert.threat_level} />
                  </span>
                  <span className="mt-1 block truncate text-[13px] text-slate-200">
                    {alert.primary_reason || "Flagged by threat engine"}
                  </span>
                  <span className="mt-0.5 block truncate font-mono text-[10px] uppercase tracking-[0.14em] text-slate-300">
                    {sourceTypeLabel(alert.source_type) || "—"} ·{" "}
                    {alert.state || "Unassigned"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
};
