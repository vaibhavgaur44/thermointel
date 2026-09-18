import { X } from "lucide-react";

import { Panel, PanelBody, PanelHeader } from "@/components/common/Panel";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/common/PanelStates";
import { ConfidenceReadout, ThreatBadge } from "@/components/common/Indicators";
import { eventTypeMeta, sourceTypeLabel } from "@/constants/taxonomy";
import { useEventDetail } from "@/hooks/useThermoIntel";
import { useDashboard } from "@/state/DashboardContext";

const Field = ({ label, value, mono = true, testId }) => (
  <div className="flex items-baseline justify-between gap-3 border-b border-slate-800/50 py-1.5 last:border-0">
    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-300">
      {label}
    </span>
    <span
      data-testid={testId}
      className={`truncate text-right text-[12px] text-slate-200 ${mono ? "font-mono tabular-nums" : ""}`}
    >
      {value ?? "—"}
    </span>
  </div>
);

const formatDateTime = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "—";

export const SelectedEventPanel = () => {
  const { selectedEventId, clearSelection } = useDashboard();
  const { data: event, isLoading, error } = useEventDetail(selectedEventId);

  const meta = event ? eventTypeMeta(event.event_type) : null;
  const source = event ? sourceTypeLabel(event.source_type) : null;

  return (
    <Panel testId="selected-event-panel" className="w-full">
      <PanelHeader
        eyebrow="Selected Event Intelligence"
        title={source || meta?.label || "Event"}
        right={
          <button
            type="button"
            data-testid="close-selected-event-button"
            onClick={clearSelection}
            className="shrink-0 rounded-sm border border-slate-700/60 p-1 text-slate-400 transition-colors duration-200 hover:border-red-400/60 hover:text-red-300"
            aria-label="Close selected event"
          >
            <X className="h-3 w-3" />
          </button>
        }
      />
      <PanelBody>
        {isLoading && <LoadingState testId="selected-event-loading" />}
        {error && (
          <ErrorState message={error.message} testId="selected-event-error" />
        )}
        {event && (
          <div className="space-y-4">
            <div>
              <p
                data-testid="selected-event-type"
                className="font-mono text-[15px] font-bold uppercase tracking-[0.1em]"
                style={{ color: meta.color }}
              >
                {meta.label}
              </p>
              <div className="mt-2 flex items-center gap-2">
                <ThreatBadge
                  level={event.threat_level}
                  score={event.threat_score}
                  testId="selected-event-threat"
                />
                {event.data_origin === "demo" && (
                  <span className="rounded-sm border border-amber-400/50 bg-amber-400/10 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-amber-300">
                    Demo
                  </span>
                )}
              </div>
              <div className="mt-2">
                <ConfidenceReadout
                  confidence={event.model_confidence}
                  testId="selected-event-confidence"
                />
              </div>
            </div>

            <div>
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-sky-300/70">
                Why flagged
              </p>
              <div className="mt-2">
                {event.supporting_evidence?.length ? (
                  <ul
                    data-testid="selected-event-evidence"
                    className="space-y-1.5"
                  >
                    {event.supporting_evidence.map((item) => (
                      <li
                        key={item.code}
                        className="flex items-start gap-2 text-[12px] text-slate-300"
                      >
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-sky-400" />
                        <span>
                          {item.label}
                          {item.detail && (
                            <span className="block font-mono text-[10px] text-slate-300">
                              {item.detail}
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    testId="selected-event-evidence-empty"
                    title="No evidence recorded"
                    detail="Supporting evidence is produced by the threat/anomaly engine, which is not yet implemented."
                  />
                )}
              </div>
            </div>

            <div>
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-sky-300/70">
                Event record
              </p>
              <div className="mt-1.5">
                <Field
                  label="Status"
                  value={event.status}
                  testId="selected-event-status"
                />
                <Field label="State / UT" value={event.state} mono={false} />
                <Field
                  label="Position"
                  value={`${event.latitude.toFixed(4)}, ${event.longitude.toFixed(4)}`}
                />
                <Field label="Detections" value={event.detection_count} />
                <Field
                  label="First detected"
                  value={formatDateTime(event.first_detected)}
                />
                <Field
                  label="Last detected"
                  value={formatDateTime(event.last_detected)}
                />
                <Field
                  label="Peak FRP"
                  value={event.peak_frp != null ? `${event.peak_frp} MW` : null}
                />
                <Field
                  label="Latest FRP"
                  value={
                    event.latest_frp != null ? `${event.latest_frp} MW` : null
                  }
                />
                <Field
                  label="Model version"
                  value={event.model_version_id}
                  testId="selected-event-model-version"
                />
              </div>
            </div>
          </div>
        )}
      </PanelBody>
    </Panel>
  );
};
