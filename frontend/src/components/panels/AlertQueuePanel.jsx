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

/** Human-readable phrasing for the engine's internal signal names. */
const REASON_LABELS = {
  frp_magnitude: "high fire radiative power",
  baseline_deviation: "unusual brightness vs typical levels",
  detection_strength: "strong detection confidence",
};

const friendlyReason = (reason) => {
  if (!reason) return "Flagged by the threat engine";
  const match = reason.match(/^([a-z_]+):\s*normalized=([\d.]+)/);
  if (!match) return reason;
  const label = REASON_LABELS[match[1]] || match[1].replace(/_/g, " ");
  const value = Number(match[2]);
  const intensity =
    value >= 1 ? "max" : value >= 0.75 ? "very strong" : "strong";
  return `Flagged: ${intensity} ${label}`;
};

export const AlertQueuePanel = () => {
  const { data, isLoading, error } = useAlerts();
  const { filters, selectEvent } = useDashboard();
  const alerts = data?.items || [];
  const scope = filters.region?.name || "India";

  return (
    <Panel testId="alert-queue-panel" className="w-full">
      <PanelHeader
        eyebrow="Alert Queue"
        title={`${alerts.length} open · ${scope}`}
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
            title={`No alerts for ${scope}`}
            detail="This state currently has no open alerts. Alerts stay in the queue until they are resolved - they are not removed by the map's time window."
          />
        </PanelBody>
      )}
      {alerts.length > 0 && (
        <ul className="divide-y divide-slate-800/50">
          {alerts.map((alert) => {
            const meta = eventTypeMeta(alert.event_type);
            const source = sourceTypeLabel(alert.source_type);
            const facility =
              source && alert.state ? `${source} · ${alert.state}` : null;
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
                    {friendlyReason(alert.primary_reason)}
                  </span>
                  <span className="mt-0.5 block truncate font-mono text-[10px] uppercase tracking-[0.14em] text-slate-300">
                    {facility || source || alert.state || "Location not assigned"}
                    <span className="text-slate-700"> · </span>
                    {alert.raised_at
                      ? new Date(alert.raised_at).toLocaleString(undefined, {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "—"}
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
