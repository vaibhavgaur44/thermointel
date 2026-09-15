import { eventTypeMeta } from "@/constants/taxonomy";
import {
  pinMarkerImage,
  selectionRingImage,
  softMarkerImage,
} from "@/map/markerImages";

export const EVENT_SOURCE_NAME = "thermointel-events";

export const createEventDataSource = async (viewer) => {
  const Cesium = window.Cesium;
  const dataSource = new Cesium.CustomDataSource(EVENT_SOURCE_NAME);
  await viewer.dataSources.add(dataSource);
  return dataSource;
};

const SOFT_SCALE = () =>
  new window.Cesium.NearFarScalar(150000, 1.0, 9000000, 0.34);
const PIN_SCALE = () =>
  new window.Cesium.NearFarScalar(150000, 1.0, 9000000, 0.45);
const TRANSLUCENCY = () =>
  new window.Cesium.NearFarScalar(150000, 1.0, 14000000, 0.72);

export const renderEvents = (dataSource, events, selectedEventId) => {
  const Cesium = window.Cesium;
  if (!dataSource) return;

  dataSource.entities.removeAll();

  events.forEach((event) => {
    const meta = eventTypeMeta(event.event_type);
    const isPin = meta.marker === "pin";
    const position = Cesium.Cartesian3.fromDegrees(
      event.longitude,
      event.latitude,
    );

    dataSource.entities.add({
      id: `event:${event.event_id}`,
      position,
      billboard: {
        image: isPin ? pinMarkerImage(meta.color) : softMarkerImage(meta.color),
        verticalOrigin: isPin
          ? Cesium.VerticalOrigin.BOTTOM
          : Cesium.VerticalOrigin.CENTER,
        scaleByDistance: isPin ? PIN_SCALE() : SOFT_SCALE(),
        translucencyByDistance: isPin ? undefined : TRANSLUCENCY(),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        eyeOffset: new Cesium.Cartesian3(0, 0, isPin ? -4000 : 0),
      },
      properties: { eventId: event.event_id },
    });
  });

  const selected = events.find((e) => e.event_id === selectedEventId);
  if (selected) {
    dataSource.entities.add({
      id: "event-selection-ring",
      position: Cesium.Cartesian3.fromDegrees(
        selected.longitude,
        selected.latitude,
      ),
      billboard: {
        image: selectionRingImage(),
        verticalOrigin: Cesium.VerticalOrigin.CENTER,
        scaleByDistance: new Cesium.NearFarScalar(150000, 1.0, 9000000, 0.3),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        eyeOffset: new Cesium.Cartesian3(0, 0, -1000),
      },
    });
  }
};

export const eventIdFromPick = (picked) => {
  const properties = picked?.id?.properties;
  if (!properties?.eventId) return null;
  return properties.eventId.getValue();
};
