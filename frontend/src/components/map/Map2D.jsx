import { useEffect, useState } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Pane,
  TileLayer,
  useMap,
} from "react-leaflet";

import { eventTypeMeta } from "@/constants/taxonomy";
import "leaflet/dist/leaflet.css";

import { useDashboard } from "@/state/DashboardContext";
import { useMapEvents } from "@/hooks/useThermoIntel";

const RegionZoom = ({ bbox }) => {
  const map = useMap();

  useEffect(() => {
    if (!bbox || bbox.length !== 4) return;

    const [west, south, east, north] = bbox;

    map.fitBounds(
      [
        [south, west],
        [north, east],
      ],
      {
        padding: [40, 40],
        maxZoom: 7,
      }
    );
  }, [bbox, map]);

  return null;
};

export const Map2D = () => {
   const {
  filters,
  setRegion,
  selectEvent,
  clearSelection,
  selectedEventId,
} = useDashboard();

  const { data: eventsData } = useMapEvents();
  const events = eventsData?.items || [];

  const [boundaries, setBoundaries] = useState(null);

  useEffect(() => {
    fetch("/geo/india_states.geojson")
      .then((response) => response.json())
      .then((data) => setBoundaries(data))
      .catch((error) =>
        console.error("Failed to load India boundaries:", error)
      );
  }, []);

  return (
    <div className="absolute inset-0 z-0">
      <MapContainer
        center={[20.6, 78.9]}
        zoom={5}
        className="h-full w-full"
        scrollWheelZoom
      >
        <RegionZoom bbox={filters.region?.bbox} />
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="© OpenStreetMap contributors"
        />
<Pane name="events" style={{ zIndex: 1000 }}>
  {events.map((event) => {
  const colors = {
    INDUSTRIAL_FIRE: "#EF4444",
    PERSISTENT_HEAT_SOURCE: "#3B82F6",
    AGRICULTURAL_FIRE: "#84CC16",
    FOREST_FIRE: "#059669",
    UNKNOWN_AGRICULTURAL_FIRE: "#A3E635",
  };

  const isIndustrialFire = event.event_type === "INDUSTRIAL_FIRE";
const color = colors[event.event_type] || "#64748B";
const isSelected = selectedEventId === event.event_id;

  return (
    <CircleMarker
      key={event.event_id}
      center={[event.latitude, event.longitude]}
      radius={isIndustrialFire ? 8 : 7}
      pathOptions={{
  color: isSelected ? "#FFFFFF" : color,
  fillColor: color,
  fillOpacity: isSelected
    ? 0.9
    : isIndustrialFire
      ? 0.95
      : 0.55,
  weight: isSelected ? 2.5 : 1.5,
}}
      eventHandlers={{
        click: (e) => {
          e.originalEvent.stopPropagation();

          selectEvent(event.event_id, {
            latitude: event.latitude,
            longitude: event.longitude,
          });
        },
      }}
    />
  );
})}
</Pane>

        {boundaries && (
          <GeoJSON
            key={filters.region?.name || "india"}
            data={boundaries}
            style={(feature) => {
              const selected =
                filters.region?.name === feature.properties?.state;

              return {
                color: selected ? "#bae6fd" : "#08435f",
                weight: selected ? 2 : 1,
                fillColor: selected ? "#124f69" : "#124f69",
                fillOpacity: selected ? 0.13 : 0.035,
              };
            }}
            onEachFeature={(feature, layer) => {
              layer.on({
                click: () => {
                  const name = feature.properties?.state;
                  const bbox = feature.properties?.bbox;

                  if (name) {
                    setRegion({
                      name,
                      bbox,
                    });
                  }
                },
              });
            }}
          />
        )}
      </MapContainer>
    </div>
  );
};