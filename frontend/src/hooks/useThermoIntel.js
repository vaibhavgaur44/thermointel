import { useQuery } from "@tanstack/react-query";

import { thermoIntelApi } from "@/api/thermointel";
import { useDashboard } from "@/state/DashboardContext";

const key = (name, filters) => [name, filters];

export const useRegions = () =>
  useQuery({
    queryKey: ["regions"],
    queryFn: thermoIntelApi.regions,
    staleTime: Infinity,
  });

export const useRegionalOverview = () => {
  const { queryFilters } = useDashboard();
  return useQuery({
    queryKey: key("regional-overview", queryFilters),
    queryFn: () => thermoIntelApi.regionalOverview(queryFilters),
  });
};

export const useMapEvents = () => {
  const { queryFilters } = useDashboard();
  return useQuery({
    queryKey: key("map-events", queryFilters),
    queryFn: () => thermoIntelApi.events({ ...queryFilters, limit: 2000 }),
  });
};

export const usePriorityEvents = () => {
  const { queryFilters } = useDashboard();
  return useQuery({
    queryKey: key("priority-events", queryFilters),
    queryFn: () => thermoIntelApi.priorityEvents({ ...queryFilters, limit: 5 }),
  });
};

export const useAlerts = () => {
  const { queryFilters } = useDashboard();

  return useQuery({
    queryKey: key("alerts", queryFilters),
    queryFn: () =>
      thermoIntelApi.alerts({
        ...queryFilters,
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
