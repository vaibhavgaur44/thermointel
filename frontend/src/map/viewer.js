import { loadCesium } from "@/lib/cesiumLoader";

export const INDIA_RECTANGLE = [68.1, 6.5, 97.4, 35.7];

const ION_TOKEN = process.env.REACT_APP_CESIUM_ION_TOKEN || "";

export const hasIonToken = Boolean(ION_TOKEN);

const esri = (Cesium, service, maximumLevel) =>
  new Cesium.UrlTemplateImageryProvider({
    url: `https://services.arcgisonline.com/ArcGIS/rest/services/${service}/MapServer/tile/{z}/{y}/{x}`,
    maximumLevel,
    credit: "Esri, HERE, Garmin, OpenStreetMap contributors",
  });

/**
 * Basemap stacks. Roads, places and labels come from the street/reference
 * layers so detailed map information appears as the camera descends from the
 * globe to a regional view. Cesium Ion world imagery is used for "satellite"
 * when a token is configured, otherwise Esri imagery is the fallback.
 */
export const createImageryLayers = async (Cesium, basemap) => {
  if (basemap === "streets") {
    return [{ provider: esri(Cesium, "World_Street_Map", 19) }];
  }
  if (basemap === "satellite") {
    const base = hasIonToken
      ? await Cesium.IonImageryProvider.fromAssetId(2)
      : esri(Cesium, "World_Imagery", 19);
    return [
      { provider: base, brightness: 0.9 },
      {
        provider: esri(Cesium, "Canvas/World_Dark_Gray_Reference", 16),
        alpha: 0.9,
      },
    ];
  }
  // Dark technical basemap: full street detail colour-graded down so the
  // event markers remain the dominant visual element.
  return [
    {
      provider: esri(Cesium, "World_Street_Map", 19),
      brightness: 0.24,
      contrast: 1.5,
      saturation: 0.2,
      gamma: 0.8,
    },
  ];
};

export const createViewer = async (container, basemap) => {
  const Cesium = await loadCesium();
  if (ION_TOKEN) Cesium.Ion.defaultAccessToken = ION_TOKEN;

  const viewer = new Cesium.Viewer(container, {
    baseLayer: false,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    animation: false,
    timeline: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    shouldAnimate: false,
    creditContainer: document.createElement("div"),
  });

  const { scene } = viewer;
  scene.globe.baseColor = Cesium.Color.fromCssColorString("#060911");
  scene.globe.showGroundAtmosphere = true;
  scene.globe.enableLighting = false;
  scene.globe.depthTestAgainstTerrain = false;
  scene.skyAtmosphere.brightnessShift = -0.35;
  scene.skyAtmosphere.saturationShift = -0.2;
  scene.fog.enabled = true;
  scene.fog.density = 0.00012;
  scene.highDynamicRange = false;
  scene.screenSpaceCameraController.enableCollisionDetection = true;
  scene.screenSpaceCameraController.minimumZoomDistance = 800;

  await setBasemap(viewer, basemap);

  // Start wide, then settle on India: Earth -> India -> region -> detail.
  viewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(79, 22, 26000000),
  });
  viewer.camera.flyTo({
    destination: Cesium.Rectangle.fromDegrees(...INDIA_RECTANGLE),
    duration: 2.6,
  });

  return { viewer, Cesium };
};

export const setBasemap = async (viewer, basemap) => {
  const Cesium = window.Cesium;
  const layers = await createImageryLayers(Cesium, basemap);
  viewer.imageryLayers.removeAll();
  layers.forEach(({ provider, brightness, contrast, saturation, alpha, gamma }) => {
    const layer = viewer.imageryLayers.addImageryProvider(provider);
    if (brightness != null) layer.brightness = brightness;
    if (contrast != null) layer.contrast = contrast;
    if (saturation != null) layer.saturation = saturation;
    if (alpha != null) layer.alpha = alpha;
    if (gamma != null) layer.gamma = gamma;
  });
};

export const flyToBoundingBox = (viewer, bbox, duration = 1.4) => {
  const Cesium = window.Cesium;
  viewer.camera.flyTo({
    destination: Cesium.Rectangle.fromDegrees(...bbox),
    duration,
  });
};

export const flyToPoint = (viewer, longitude, latitude, height = 90000) => {
  const Cesium = window.Cesium;
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(longitude, latitude, height),
    duration: 1.4,
  });
};
