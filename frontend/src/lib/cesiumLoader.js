/**
 * CesiumJS is loaded from a CDN bundle declared in public/index.html.
 * This keeps the webpack config untouched and the build reproducible.
 */
let readyPromise = null;

export const loadCesium = () => {
  if (window.Cesium) return Promise.resolve(window.Cesium);
  if (readyPromise) return readyPromise;

  readyPromise = new Promise((resolve, reject) => {
    const started = Date.now();
    const poll = setInterval(() => {
      if (window.Cesium) {
        clearInterval(poll);
        resolve(window.Cesium);
      } else if (Date.now() - started > 20000) {
        clearInterval(poll);
        reject(new Error("CesiumJS failed to load"));
      }
    }, 80);
  });

  return readyPromise;
};
