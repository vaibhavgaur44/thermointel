export const EVENT_SOURCE_NAME = "thermointel-events";

export const createEventDataSource = async (viewer) => {
  const Cesium = window.Cesium;

  const dataSource = new Cesium.CustomDataSource(EVENT_SOURCE_NAME);
  await viewer.dataSources.add(dataSource);

  return dataSource;
};

const COLORS = {
  INDUSTRIAL_FIRE: "#EF4444",
  PERSISTENT_HEAT_SOURCE: "#3B82F6",
  AGRICULTURAL_FIRE: "#84CC16",
  FOREST_FIRE: "#059669",
  UNKNOWN_AGRICULTURAL_FIRE: "#A3E635",
};

export const renderEvents = (dataSource, events, selectedEventId) => {
  const Cesium = window.Cesium;

  if (!dataSource) return;

  dataSource.entities.removeAll();

  events.forEach((event) => {
    const color = COLORS[event.event_type] || "#64748B";
    const isIndustrialFire = event.event_type === "INDUSTRIAL_FIRE";
    const isSelected = event.event_id === selectedEventId;

    dataSource.entities.add({
      id: `event:${event.event_id}`,

      position: Cesium.Cartesian3.fromDegrees(
        event.longitude,
        event.latitude,
      ),

      point: {
        pixelSize: isIndustrialFire ? 24 : 20,

        color: Cesium.Color.fromCssColorString(color).withAlpha(
          isSelected
            ? 0.9
            : isIndustrialFire
              ? 0.95
              : 0.6,
        ),

        outlineColor: Cesium.Color.WHITE,

        outlineWidth: isSelected ? 1.5 : 0,

        disableDepthTestDistance: Number.POSITIVE_INFINITY,

        scaleByDistance: new Cesium.NearFarScalar(
          150000,
          1.0,
          9000000,
          1.0,
        ),
      },

      properties: {
        eventId: event.event_id,
      },
    });
  });
};

export const eventIdFromPick = (picked) => {
  const properties = picked?.id?.properties;

  if (!properties?.eventId) return null;

  return properties.eventId.getValue();
};