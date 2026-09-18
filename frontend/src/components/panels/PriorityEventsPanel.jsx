import { ChevronRight } from "lucide-react";

import { Panel, PanelBody, PanelHeader } from "@/components/common/Panel";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/common/PanelStates";
import { EventTypeTag, ThreatBadge } from "@/components/common/Indicators";
import { eventTypeMeta, sourceTypeLabel } from "@/constants/taxonomy";
import { usePriorityEvents } from "@/hooks/useThermoIntel";
import { useDashboard } from "@/state/DashboardContext";

const relativeTime = (iso) => {
  if (!iso) return "—";
  const minutes = Math.max(
    0,
    Math.round((Date.now() - new Date(iso).getTime()) / 60000),
  );
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
};

const PriorityRow = ({ event, rank, selected, onSelect }) => {
  const meta = eventTypeMeta(event.event_type);
  const source = sourceTypeLabel(event.source_type);

  return (
    <li>
      <button
        type="button"
        data-testid={`priority-event-${event.event_id}`}
        onClick={() => onSelect(event)}
        className={`group flex w-full items-start gap-3 border-l-2 px-3 py-3 text-left transition-colors duration-200 ${
          selected
            ? "border-l-sky-400 bg-sky-400/[0.07]"
            : "border-l-transparent hover:border-l-slate-600 hover:bg-slate-800/40"
        }`}
      >
        <span className="mt-0.5 font-mono text-[11px] font-bold tabular-nums text-slate-400">
          {String(rank).padStart(2, "0")}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center justify-between gap-2">
            <EventTypeTag meta={meta} />
            <ThreatBadge
              level={event.threat_level}
              score={event.threat_score}
              testId={`priority-threat-${event.event_id}`}
            />
          </span>
          {source && (
            <span className="mt-1 block truncate text-[13px] font-medium text-slate-100">
              {source}
            </span>
          )}
          <span className="mt-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-300">
            <span className="truncate">{event.state || "Unassigned"}</span>
            <span className="text-slate-700">/</span>
            <span>{event.detection_count} det</span>
            <span className="text-slate-700">/</span>
            <span>{relativeTime(event.last_detected)}</span>
          </span>
        </span>
        <ChevronRight className="mt-1 h-3.5 w-3.5 shrink-0 text-slate-400 transition-colors duration-200 group-hover:text-sky-300" />
      </button>
    </li>
  );
};

export const PriorityEventsPanel = () => {
  const { filters, selectedEventId, selectEvent } = useDashboard();
  const { data, isLoading, error } = usePriorityEvents();
  const scope = filters.region?.name || "India";

  return (
    <Panel testId="priority-events-panel" className="w-full">
      <PanelHeader
        eyebrow="Priority Events"
        title={`Top 5 · ${scope}`}
        right={
          <span className="shrink-0 pt-1 font-mono text-[9px] uppercase tracking-[0.18em] text-slate-300">
            by threat score
          </span>
        }
      />
      {isLoading && (
        <PanelBody>
          <LoadingState testId="priority-loading" />
        </PanelBody>
      )}
      {error && (
        <PanelBody>
          <ErrorState message={error.message} testId="priority-error" />
        </PanelBody>
      )}
      {data && data.length === 0 && (
        <PanelBody>
          <EmptyState
            testId="priority-empty"
            title="No active events"
            detail="Ranked events appear once FIRMS ingestion, event formation and the threat engine are live. Nothing is fabricated here."
          />
        </PanelBody>
      )}
      {data && data.length > 0 && (
        <ul className="divide-y divide-slate-800/50 py-1">
          {data.map((event, index) => (
            <PriorityRow
              key={event.event_id}
              event={event}
              rank={index + 1}
              selected={event.event_id === selectedEventId}
              onSelect={(e) =>
                selectEvent(e.event_id, {
                  latitude: e.latitude,
                  longitude: e.longitude,
                })
              }
            />
          ))}
        </ul>
      )}
    </Panel>
  );
};
