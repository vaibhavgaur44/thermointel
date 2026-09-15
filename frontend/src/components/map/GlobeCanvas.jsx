import { useEffect, useMemo, useRef, useState } from "react";

import {
  createEventDataSource,
  eventIdFromPick,
  renderEvents,
} from "@/map/eventLayer";
import {
  highlightRegion,
  loadIndiaBoundaries,
  regionBboxFromPick,
  regionNameFromPick,
} from "@/map/boundaryLayer";
import {
  INDIA_RECTANGLE,
  createViewer,
  flyToBoundingBox,
  flyToPoint,
  setBasemap,
} from "@/map/viewer";
import { useDashboard } from "@/state/DashboardContext";
import { useMapEvents } from "@/hooks/useThermoIntel";

export const GlobeCanvas = () => {
  const containerRef = useRef(null);
  const viewerRef = useRef(null);
  const eventSourceRef = useRef(null);
  const boundaryRef = useRef(null);
  const [status, setStatus] = useState("loading");

  const {
    filters,
    selectedEventId,
    basemap,
    selectEvent,
    clearSelection,
    setRegion,
  } = useDashboard();
  const { data } = useMapEvents();
  const events = useMemo(() => data?.items || [], [data]);

  // Stable reference so the Cesium pick handler always sees current events.
  const eventsRef = useRef(events);
  eventsRef.current = events;

  useEffect(() => {
    let disposed = false;
    let handler = null;

    (async () => {
      try {
        const { viewer, Cesium } = await createViewer(
          containerRef.current,
          basemap,
        );
        if (disposed) {
          viewer.destroy();
          return;
        }
        viewerRef.current = viewer;
        boundaryRef.current = await loadIndiaBoundaries(viewer);
        eventSourceRef.current = await createEventDataSource(viewer);

        handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((movement) => {
          const picked = viewer.scene.pick(movement.position);
          const eventId = eventIdFromPick(picked);
          if (eventId) {
            const event = eventsRef.current.find((e) => e.event_id === eventId);
            selectEvent(
              eventId,
              event
                ? { latitude: event.latitude, longitude: event.longitude }
                : null,
            );
            return;
          }
          const regionName = regionNameFromPick(picked);
          if (regionName) {
            setRegion({ name: regionName, bbox: regionBboxFromPick(picked) });
            return;
          }
          clearSelection();
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        setStatus("ready");
      } catch (error) {
        console.error(error);
        setStatus("error");
      }
    })();

    return () => {
      disposed = true;
      if (handler) handler.destroy();
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep a stable reference for the pick handler.
  useEffect(() => {
    if (status !== "ready") return;
    renderEvents(eventSourceRef.current, events, selectedEventId);
  }, [events, selectedEventId, status]);

  useEffect(() => {
    if (status !== "ready") return;
    highlightRegion(boundaryRef.current, filters.region?.name);
    if (filters.region?.bbox) {
      flyToBoundingBox(viewerRef.current, filters.region.bbox);
    } else {
      flyToBoundingBox(viewerRef.current, INDIA_RECTANGLE, 1.8);
    }
  }, [filters.region, status]);

  useEffect(() => {
    if (status !== "ready" || !selectedEventId) return;
    const event = eventsRef.current.find((e) => e.event_id === selectedEventId);
    if (event) {
      flyToPoint(viewerRef.current, event.longitude, event.latitude);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEventId, status]);

  useEffect(() => {
    if (status !== "ready") return;
    setBasemap(viewerRef.current, basemap);
  }, [basemap, status]);

  return (
    <div className="absolute inset-0 z-0" data-testid="globe-canvas">
      <div ref={containerRef} className="h-full w-full" />
      {status !== "ready" && (
        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center bg-[#04060c]"
          data-testid="globe-status-overlay"
        >
          <p className="font-mono text-[11px] uppercase tracking-[0.35em] text-sky-300/70">
            {status === "error"
              ? "Globe unavailable"
              : "Initialising globe"}
          </p>
        </div>
      )}
    </div>
  );
};
