import { useQuery } from "@tanstack/react-query";

import { thermoIntelApi } from "@/api/thermointel";
import { useDashboard } from "@/state/DashboardContext";

const key = (name, filters) => [name, filters];

/**
 * Event-query scope for the dashboard's time-range chips.
 *
 * The backend's time_range filters events on last_detected (detection age),
 * while status filtering is a separate axis. The lifecycle expires an event
 * to EXPIRED once last_detected is older than 24h, so forcing status=ACTIVE
 * makes every window wider than 24h a no-op (1W == 24h) and hides events that
 * are still inside the user's selected week. For the 1W view we therefore
 * drop the ACTIVE constraint and let the 7-day detection window do the
 * scoping; 1h/6h/24h keep ACTIVE because EXPIRED events are always older
 * than 24h by the lifecycle's own rule, so those results are identical
 * either way. Priority Events deliberately stays ACTIVE-only (live ranking).
 */
const useEventScope = () => {
  const { queryFilters } = useDashboard();

  const activeScoped = { ...queryFilters, status: "ACTIVE" };
  const windowScoped =
    queryFilters.timeRange === "1w"
      ? { ...queryFilters, status: undefined }
      : activeScoped;

  return { activeScoped, windowScoped };
};

export const useRegions = () =>
  useQuery({
    queryKey: ["regions"],
    queryFn: thermoIntelApi.regions,
    staleTime: Infinity,
  });export const useRegionalOverview = () => {
  const { windowScoped } = useEventScope();
  return useQuery({
    queryKey: key("regional-overview", windowScoped),
    queryFn: () => thermoIntelApi.regionalOverview(windowScoped),
  });
};

export const useMapEvents = () => {
  const { windowScoped } = useEventScope();
  return useQuery({
    queryKey: key("map-events", windowScoped),
    queryFn: () => thermoIntelApi.events({ ...windowScoped, limit: 2000 }),
  });
};

export const usePriorityEvents = () => {
  const { activeScoped } = useEventScope();
  return useQuery({
    queryKey: key("priority-events", activeScoped),
    queryFn: () => thermoIntelApi.priorityEvents({ ...activeScoped, limit: 5 }),
  });
};

export const useAlerts = () => {
  const { queryFilters } = useDashboard();

  // Alerts deliberately EXCLUDE the dashboard's time_range filter. The
  // 24h/6h/1h window is a DETECTION-time scope (it filters events by
  // last_detected); alerts use raised_at, which is set once when an event
  // first qualifies - duplicate suppression means one alert per event, ever.
  // Filtering alerts by the detection window hid still-valid OPEN alerts
  // whenever the event crossed the threshold more than 24h ago, which made
  // the Alert Queue appear empty (especially for a single selected state).
  // State / classification / source-type scoping still applies as usual.
  const { timeRange, ...alertFilters } = queryFilters;

  return useQuery({
    queryKey: key("alerts", alertFilters),
    queryFn: () =>
      thermoIntelApi.alerts({
        ...alertFilters,
        status: "OPEN",
        limit: 25,
      }),
  });
};

export const useEventDetail = (eventId) =>
  useQuery({
    queryKey: ["event", eventId],
    queryFn: () => thermoIntelApi.event(eventId),
    enabled: Boolean(eventId),
  });

export const useIngestionStatus = () =>
  useQuery({
    queryKey: ["ingestion-status"],
    queryFn: thermoIntelApi.ingestionStatus,
    refetchInterval: 60000,
  });
