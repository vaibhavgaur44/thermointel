/**
 * India state / Union Territory boundary overlay.
 * Also acts as the pick target for region selection.
 */
const FILL = "rgba(56,189,248,0.035)";
const FILL_SELECTED = "rgba(56,189,248,0.13)";
const STROKE = "rgba(125,211,252,0.5)";
const STROKE_SELECTED = "rgba(186,230,253,0.95)";

export const loadIndiaBoundaries = async (viewer) => {
  const Cesium = window.Cesium;
  const dataSource = await Cesium.GeoJsonDataSource.load(
    "/geo/india_states.geojson",
    {
      stroke: Cesium.Color.fromCssColorString(STROKE),
      fill: Cesium.Color.fromCssColorString(FILL),
      strokeWidth: 1,
      clampToGround: false,
    },
  );
  dataSource.name = "india-boundaries";
  await viewer.dataSources.add(dataSource);

  dataSource.entities.values.forEach((entity) => {
    if (!entity.polygon) return;
    entity.polygon.height = 0;
    entity.polygon.outline = true;
    entity.polygon.outlineColor = Cesium.Color.fromCssColorString(STROKE);
  });

  return dataSource;
};

export const highlightRegion = (dataSource, regionName) => {
  const Cesium = window.Cesium;
  if (!dataSource) return;
  dataSource.entities.values.forEach((entity) => {
    if (!entity.polygon) return;
    const name = entity.properties?.state?.getValue();
    const selected = Boolean(regionName) && name === regionName;
    entity.polygon.material = Cesium.Color.fromCssColorString(
      selected ? FILL_SELECTED : FILL,
    );
    entity.polygon.outlineColor = Cesium.Color.fromCssColorString(
      selected ? STROKE_SELECTED : STROKE,
    );
  });
};

export const regionNameFromPick = (picked) => {
  const properties = picked?.id?.properties;
  if (!properties?.state) return null;
  return properties.state.getValue();
};

export const regionBboxFromPick = (picked) => {
  const properties = picked?.id?.properties;
  if (!properties?.bbox) return null;
  return properties.bbox.getValue();
};
