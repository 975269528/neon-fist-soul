/* 霓虹拳魂 NEON FIST SOUL — 通用工具函数 */
window.NF = window.NF || {};

(function () {
  const TAU = Math.PI * 2;

  const util = {
    TAU,
    clamp(v, a, b) { return v < a ? a : (v > b ? b : v); },
    clamp01(v) { return v < 0 ? 0 : (v > 1 ? 1 : v); },
    lerp(a, b, t) { return a + (b - a) * t; },
    invLerp(a, b, v) { return a === b ? 0 : (v - a) / (b - a); },
    damp(a, b, lambda, dt) { return util.lerp(a, b, 1 - Math.exp(-lambda * dt)); },
    approach(v, target, step) {
      if (v < target) return Math.min(v + step, target);
      return Math.max(v - step, target);
    },
    sign(v) { return v < 0 ? -1 : (v > 0 ? 1 : 0); },
    rand(a, b) { return a + Math.random() * (b - a); },
    randInt(a, b) { return Math.floor(a + Math.random() * (b - a + 1)); },
    chance(p) { return Math.random() < p; },
    choice(arr) { return arr[Math.floor(Math.random() * arr.length)]; },
    shuffle(arr) {
      for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const t = arr[i]; arr[i] = arr[j]; arr[j] = t;
      }
      return arr;
    },
    dist2(x1, y1, x2, y2) { const dx = x2 - x1, dy = y2 - y1; return dx * dx + dy * dy; },
    dist(x1, y1, x2, y2) { return Math.sqrt(util.dist2(x1, y1, x2, y2)); },
    rectsOverlap(a, b) {
      return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    },
    pointInRect(px, py, r) {
      return px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h;
    },
    pad(n, len, ch) { ch = ch || '0'; let s = String(Math.max(0, Math.floor(n))); while (s.length < len) s = ch + s; return s; },
    fmtScore(n) { return util.pad(n, 7); },
    fmtTime(sec) {
      const s = Math.max(0, Math.ceil(sec));
      return util.pad(Math.floor(s / 60), 2) + ':' + util.pad(s % 60, 2);
    },
    easeOutQuad(t) { return 1 - (1 - t) * (1 - t); },
    easeInQuad(t) { return t * t; },
    easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); },
    easeInCubic(t) { return t * t * t; },
    easeInOutQuad(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; },
    easeOutBack(t) { const c = 1.70158; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); },
    easeOutElastic(t) {
      if (t === 0 || t === 1) return t;
      const c = (2 * Math.PI) / 3;
      return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c) + 1;
    },
    pulse(t, speed, min, max) { return min + (max - min) * (0.5 + 0.5 * Math.sin(t * speed)); },
    flicker(t, seed, speed) {
      const n = Math.sin(t * speed + seed * 12.9898) * 43758.5453;
      return (n - Math.floor(n)) > 0.08 ? 1 : 0.35;
    },
    /* 确定性伪随机：用于美术/特效稳定抖动 */
    hash(n) {
      const s = Math.sin(n * 127.1 + 311.7) * 43758.5453123;
      return s - Math.floor(s);
    },
    hash2(x, y) { return util.hash(x * 57.31 + y * 113.97); },
    deg(r) { return r * 180 / Math.PI; },
    rad(d) { return d * Math.PI / 180; },
    now() { return (typeof performance !== 'undefined' ? performance.now() : Date.now()) / 1000; }
  };

  NF.util = util;
})();
