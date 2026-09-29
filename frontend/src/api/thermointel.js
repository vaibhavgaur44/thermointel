import { apiClient } from "@/api/client";

/**
 * Single place where ThermoIntel API contracts are expressed.
 * The frontend never derives classification or threat values - it only reads.
 */

const buildParams = (filters = {}) => {
  const params = new URLSearchParams();
  if (filters.status) params.append("status", filters.status);
  if (filters.state) params.append("state", filters.state);
  if (filters.timeRange) params.append("time_range", filters.timeRange);
  (filters.classifications || []).forEach((c) =>
    params.append("classification", c),
  );
  (filters.sourceTypes || []).forEach((s) => params.append("source_type", s));
  if (filters.includeDemo) params.append("include_demo", "true");
  if (filters.sortBy) params.append("sort_by", filters.sortBy);
  if (filters.limit) params.append("limit", String(filters.limit));
  return params;
};

export const thermoIntelApi = {
  health: async () => (await apiClient.get("/health")).data,

  regions: async () => (await apiClient.get("/regions")).data,

  taxonomy: async () => (await apiClient.get("/taxonomy")).data,

  regionalOverview: async (filters) =>
    (await apiClient.get("/events/summary", { params: buildParams(filters) }))
      .data,

  events: async (filters) =>
    (await apiClient.get("/events", { params: buildParams(filters) })).data,

  priorityEvents: async (filters) =>
    (await apiClient.get("/events/priority", { params: buildParams(filters) }))
      .data,

  event: async (eventId) => (await apiClient.get(`/events/${eventId}`)).data,

  alerts: async (filters) =>
    (await apiClient.get("/alerts", { params: buildParams(filters) })).data,

  facilities: async (filters) =>
    (await apiClient.get("/facilities", { params: buildParams(filters) })).data,

  ingestionStatus: async () => (await apiClient.get("/ingestion/status")).data,

  runIngestion: async (windowHours = 24) =>
    (await apiClient.post(`/ingestion/run?window_hours=${windowHours}`)).data,

  // Reprocess EXISTING stored production records with the CURRENT installed
  // M1 via the backend's existing inference path. No FIRMS data is fetched;
  // nothing is inserted or deleted. The dashboard Refresh button triggers
  // this explicit manual operation. Long-running: override the client's
  // default 20s timeout for this request only.
  reprocessExistingData: async (limit) =>
    (
      await apiClient.post(
        limit
          ? `/reprocess/existing-data?limit=${limit}`
          : "/reprocess/existing-data",
        null,
        { timeout: 300000 },
      )
    ).data,

  models: async () => (await apiClient.get("/models")).data,

  demoDataStatus: async () => (await apiClient.get("/dev/demo-data/status")).data,

  seedDemoData: async () => (await apiClient.post("/dev/demo-data/seed")).data,

  clearDemoData: async () => (await apiClient.delete("/dev/demo-data/clear")).data,
};
