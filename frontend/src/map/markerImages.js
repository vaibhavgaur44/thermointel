/**
 * Canvas-generated marker artwork.
 *
 * Phase 1 marker language:
 *   Industrial Fire / Alert -> red pin with a ball top, visually prominent
 *   Persistent Heat Source  -> blue, translucent, depth-like
 *   Agricultural Fire       -> light green, translucent, depth-like
 *   Forest Fire             -> dark green, translucent, depth-like
 *
 * Non-alert markers are deliberately soft radial fields, never flat opaque
 * circles, so overlapping detections stay readable.
 */
const cache = new Map();

const hexToRgb = (hex) => {
  const clean = hex.replace("#", "");
  const value = parseInt(
    clean.length === 3
      ? clean
          .split("")
          .map((c) => c + c)
          .join("")
      : clean,
    16,
  );
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
};

const rgba = (hex, alpha) => {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${alpha})`;
};

const canvasOf = (width, height) => {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
};

/** Translucent depth-like field marker. */
export const softMarkerImage = (color) => {
  const cacheKey = `soft:${color}`;
  if (cache.has(cacheKey)) return cache.get(cacheKey);

  const size = 112;
  const canvas = canvasOf(size, size);
  const ctx = canvas.getContext("2d");
  const c = size / 2;

  const glow = ctx.createRadialGradient(c, c, 2, c, c, c);
  glow.addColorStop(0, rgba(color, 0.92));
  glow.addColorStop(0.28, rgba(color, 0.42));
  glow.addColorStop(0.62, rgba(color, 0.16));
  glow.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(c, c, c, 0, Math.PI * 2);
  ctx.fill();

  // Thin definition ring gives the marker depth without becoming opaque.
  ctx.strokeStyle = rgba(color, 0.75);
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(c, c, size * 0.24, 0, Math.PI * 2);
  ctx.stroke();

  ctx.fillStyle = rgba("#ffffff", 0.7);
  ctx.beginPath();
  ctx.arc(c, c, 2.4, 0, Math.PI * 2);
  ctx.fill();

  const url = canvas.toDataURL();
  cache.set(cacheKey, url);
  return url;
};

/** Prominent alert pin with a ball top. */
export const pinMarkerImage = (color) => {
  const cacheKey = `pin:${color}`;
  if (cache.has(cacheKey)) return cache.get(cacheKey);

  const width = 72;
  const height = 104;
  const canvas = canvasOf(width, height);
  const ctx = canvas.getContext("2d");
  const cx = width / 2;
  const ballY = 30;
  const ballR = 18;
  const tipY = height - 6;

  ctx.shadowColor = "rgba(0,0,0,0.55)";
  ctx.shadowBlur = 10;
  ctx.shadowOffsetY = 3;

  // Stem tapering from the ball down to the anchor point.
  ctx.beginPath();
  ctx.moveTo(cx - ballR * 0.62, ballY + ballR * 0.72);
  ctx.quadraticCurveTo(cx - 5, tipY - 22, cx, tipY);
  ctx.quadraticCurveTo(cx + 5, tipY - 22, cx + ballR * 0.62, ballY + ballR * 0.72);
  ctx.closePath();
  const stem = ctx.createLinearGradient(0, ballY, 0, tipY);
  stem.addColorStop(0, color);
  stem.addColorStop(1, rgba(color, 0.55));
  ctx.fillStyle = stem;
  ctx.fill();

  ctx.shadowColor = "transparent";

  // Ball top.
  const ball = ctx.createRadialGradient(
    cx - 5,
    ballY - 6,
    2,
    cx,
    ballY,
    ballR,
  );
  ball.addColorStop(0, "#ffd9d6");
  ball.addColorStop(0.35, color);
  ball.addColorStop(1, "#7f1d1d");
  ctx.beginPath();
  ctx.arc(cx, ballY, ballR, 0, Math.PI * 2);
  ctx.fillStyle = ball;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(cx, ballY, 5.5, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(10,10,12,0.85)";
  ctx.fill();

  // Ground anchor.
  ctx.beginPath();
  ctx.ellipse(cx, tipY - 1, 7, 2.6, 0, 0, Math.PI * 2);
  ctx.fillStyle = rgba(color, 0.45);
  ctx.fill();

  const url = canvas.toDataURL();
  cache.set(cacheKey, url);
  return url;
};

/** Selection reticle drawn behind the selected marker. */
export const selectionRingImage = () => {
  const cacheKey = "selection-ring";
  if (cache.has(cacheKey)) return cache.get(cacheKey);

  const size = 148;
  const canvas = canvasOf(size, size);
  const ctx = canvas.getContext("2d");
  const c = size / 2;

  ctx.strokeStyle = "rgba(226,232,240,0.9)";
  ctx.lineWidth = 2;
  ctx.setLineDash([10, 8]);
  ctx.beginPath();
  ctx.arc(c, c, c - 12, 0, Math.PI * 2);
  ctx.stroke();

  ctx.setLineDash([]);
  ctx.strokeStyle = "rgba(226,232,240,0.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(c, c, c - 26, 0, Math.PI * 2);
  ctx.stroke();

  const url = canvas.toDataURL();
  cache.set(cacheKey, url);
  return url;
};
