import { createContext, useCallback, useContext, useMemo, useState } from "react";

const DashboardContext = createContext(null);

const INITIAL_FILTERS = {
  // null region == India (whole operational scope)
  region: null,
  classifications: [],
  sourceTypes: [],
  timeRange: "24h",
  // LIVE shows only ACTIVE events; HISTORICAL includes inactive/expired records.
  viewMode: "LIVE",
};

export const DashboardProvider = ({ children }) => {
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [demoMode, setDemoMode] = useState(true);
  const [basemap, setBasemap] = useState("dark");
  const [mapMode, setMapMode] = useState("2D");
  const [cameraTarget, setCameraTarget] = useState(null);

  const setRegion = useCallback((region) => {
    setFilters((prev) => ({ ...prev, region }));
    setSelectedEventId(null);
  }, []);

  const toggleClassification = useCallback((value) => {
    setFilters((prev) => ({
      ...prev,
      classifications: prev.classifications.includes(value)
        ? prev.classifications.filter((c) => c !== value)
        : [...prev.classifications, value],
    }));
  }, []);

  const toggleSourceType = useCallback((value) => {
    setFilters((prev) => ({
      ...prev,
      sourceTypes: prev.sourceTypes.includes(value)
        ? prev.sourceTypes.filter((s) => s !== value)
        : [...prev.sourceTypes, value],
    }));
  }, []);

  const setTimeRange = useCallback((timeRange) => {
    setFilters((prev) => ({ ...prev, timeRange }));
  }, []);

  const setViewMode = useCallback((viewMode) => {
    setFilters((prev) => ({ ...prev, viewMode }));
  }, []);

  const resetFilters = useCallback(() => {
    setFilters(INITIAL_FILTERS);
    setSelectedEventId(null);
  }, []);

  const selectEvent = useCallback((eventId, position) => {
    setSelectedEventId(eventId);
    if (position) setCameraTarget({ ...position, key: `${eventId}-${Date.now()}` });
  }, []);

  const clearSelection = useCallback(() => setSelectedEventId(null), []);

  /** Query params consumed by the API layer. */
  const queryFilters = useMemo(
    () => ({
      status: filters.viewMode === "LIVE" ? "ACTIVE" : undefined,
      state: filters.region?.name,
      timeRange: filters.timeRange,
      classifications: filters.classifications,
      sourceTypes: filters.sourceTypes,
      includeDemo: demoMode,
    }),
    [filters, demoMode],
  );

  const value = useMemo(
  () => ({
    filters,
    queryFilters,
    selectedEventId,
    demoMode,
    basemap,
    mapMode,
    cameraTarget,
    setRegion,
    toggleClassification,
    toggleSourceType,
    setTimeRange,
    setViewMode,
    resetFilters,
    selectEvent,
    clearSelection,
    setDemoMode,
    setBasemap,
    setMapMode,
    setCameraTarget,
  }),
  [
    filters,
    queryFilters,
    selectedEventId,
    demoMode,
    basemap,
    mapMode,
    cameraTarget,
    setRegion,
    toggleClassification,
    toggleSourceType,
    setTimeRange,
    setViewMode,
    resetFilters,
    selectEvent,
    clearSelection,
  ],
);
  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  );
};

export const useDashboard = () => {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboard must be used inside DashboardProvider");
  return ctx;
};
