import { useEffect, useState } from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";

import { useDashboard } from "@/state/DashboardContext";
import "leaflet/dist/leaflet.css";

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
  const { filters, setRegion } = useDashboard();
  const [boundaries, setBoundaries] = useState(null);

  useEffect(() => {
    fetch("/geo/india_states.geojson")
      .then((response) => response.json())
      .then((data) => setBoundaries(data))
      .catch((error) => console.error("Failed to load India boundaries:", error));
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