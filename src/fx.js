/* ============================================================================
 * 霓虹拳魂 NEON FIST SOUL — 打击特效 / 屏幕叠加层
 * 所有实现均为程序化 Canvas 绘制，无外部资源、无每帧新建 canvas。
 *
 * 对外 API（契约 §2.9，签名必须保持）：
 *   NF.fx.update(dt)
 *   NF.fx.draw(ctx)                 世界空间粒子（相机变换内）
 *   NF.fx.drawOverlay(ctx)          屏幕空间叠加层（雨/尘埃/霓虹光斑/暗角/扫描线，HUD 之前）
 *   NF.fx.drawTop(ctx)              顶层闪白/红屏/必杀霓虹闪（HUD 之后）
 *   NF.fx.shakeOffset() -> {x,y}
 *   NF.fx.shake(mag, dur)
 *   NF.fx.hitSpark(x, y, dir, power)    dir: -1/1，power: 0..1
 *   NF.fx.dust(x, y, opts)
 *   NF.fx.damageNumber(x, y, amount, opts)
 *   NF.fx.text(x, y, text, opts)
 *   NF.fx.flash(color, alpha, dur)
 *   NF.fx.clear()
 *
 * 额外便利接口（玩法模块可选用）：
 *   NF.fx.specialFlash()          必杀全屏霓虹闪 + 放射速度线
 *   NF.fx.koLines(dur)            KO 慢镜速度线
 *   NF.fx.koBurst(x, y)           KO 爆发
 *   NF.fx.roar(x, y, dur)         Boss 咆哮红光
 *   NF.fx.comboBurst(x, y, n)     连击爆发
 *   NF.fx.ring(x, y, opts)        冲击环
 *   NF.fx.speedLines(dur)         屏幕速度线
 * ========================================================================== */
window.NF = window.NF || {};

(function () {
  'use strict';
  const NF = window.NF;
  const cfg = NF.config;
  const U = NF.util;
  const VW = cfg.VIEW_W;
  const VH = cfg.VIEW_H;
  const TAU = Math.PI * 2;
  const clamp = U.clamp;
  const clamp01 = U.clamp01;

  const MAX_PARTS = 240;   /* 粒子池上限（契约要求 ≤300） */
  const MAX_TEXTS = 44;    /* 飘字池 */
  const MAX_FLASH = 8;     /* 叠加闪屏 */
  const MAX_RAIN = 110;    /* 屏幕空间雨（环境层，非战斗粒子） */

  /* 截图模式（?shot=）：debugStart 只布景一次然后冻结，因此把粒子寿命拉长、
   * 速度压慢，保证 freeze 0.2–1.5s 时命中特效仍然清晰可见（契约 §5.1）。 */
  const SHOT_MODE = !!cfg.SHOT;
  const LIFE_MUL = SHOT_MODE ? 5.5 : 1;
  const VEL_MUL = SHOT_MODE ? 0.35 : 1;
  const GRAV_MUL = SHOT_MODE ? 0.18 : 1;
  const TEXT_MUL = SHOT_MODE ? 3 : 1;

  /* ---------------------------------------------------------------- 颜色 */
  const RGB = {
    white: [255, 255, 255],
    yellow: [255, 210, 63],
    cyan: [61, 243, 255],
    magenta: [255, 47, 142],
    purple: [122, 60, 255],
    red: [255, 59, 92],
    orange: [255, 138, 42],
    lime: [141, 255, 90],
    blue: [59, 109, 255],
    steel: [176, 196, 224],
    deep: [22, 12, 38]
  };

  function rgba(name, a) {
    const c = RGB[name] || RGB.white;
    return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')';
  }
  function colorCss(name) {
    const c = RGB[name] || RGB.white;
    return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
  }
  /* 允许传入命名色（white/cyan…）或任意 CSS 颜色（#ffd23f 等） */
  function cssColor(name) {
    if (name == null) return '#ffffff';
    if (RGB[name]) return colorCss(name);
    return String(name);
  }
  function pick(a, b) { return Math.random() < 0.5 ? a : b; }
  function pick3(a, b, c) { const r = Math.random(); return r < 0.34 ? a : (r < 0.67 ? b : c); }

  /* ------------------------------------------------------------ 离屏缓存 */
  const cache = {
    glow: Object.create(null),
    vignette: null,
    redVig: null,
    scanPattern: null,
    scanTile: null,
    built: false
  };

  function buildGlow(name) {
    if (cache.glow[name]) return cache.glow[name];
    if (typeof document === 'undefined') return null;
    try {
      const c = document.createElement('canvas');
      c.width = c.height = 64;
      const g = c.getContext('2d');
      const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      grd.addColorStop(0, rgba(name, 1));
      grd.addColorStop(0.24, rgba(name, 0.72));
      grd.addColorStop(0.55, rgba(name, 0.22));
      grd.addColorStop(1, rgba(name, 0));
      g.fillStyle = grd;
      g.fillRect(0, 0, 64, 64);
      cache.glow[name] = c;
    } catch (err) {
      cache.glow[name] = null;
    }
    return cache.glow[name];
  }

  function glowSprite(name) {
    return cache.glow[name] !== undefined ? cache.glow[name] : buildGlow(name);
  }

  /* 暗角 / 受伤红光暗角 / 扫描线纹理：一次性生成 */
  function buildScreenLayers() {
    if (cache.built) return;
    cache.built = true;
    if (typeof document === 'undefined') return;

    try {
      const c = document.createElement('canvas');
      c.width = VW; c.height = VH;
      const g = c.getContext('2d');
      const grd = g.createRadialGradient(VW * 0.5, VH * 0.47, VH * 0.26, VW * 0.5, VH * 0.47, VH * 0.9);
      grd.addColorStop(0, 'rgba(4,2,12,0)');
      grd.addColorStop(0.58, 'rgba(4,2,12,0.08)');
      grd.addColorStop(1, 'rgba(2,1,8,0.6)');
      g.fillStyle = grd;
      g.fillRect(0, 0, VW, VH);
      const lg = g.createLinearGradient(0, 0, 0, VH);
      lg.addColorStop(0, 'rgba(3,1,9,0.42)');
      lg.addColorStop(0.16, 'rgba(3,1,9,0)');
      lg.addColorStop(0.84, 'rgba(3,1,9,0)');
      lg.addColorStop(1, 'rgba(3,1,9,0.46)');
      g.fillStyle = lg;
      g.fillRect(0, 0, VW, VH);
      cache.vignette = c;
    } catch (err) { cache.vignette = null; }

    try {
      const c2 = document.createElement('canvas');
      c2.width = VW; c2.height = VH;
      const g2 = c2.getContext('2d');
      const grd2 = g2.createRadialGradient(VW * 0.5, VH * 0.5, VH * 0.18, VW * 0.5, VH * 0.5, VH * 0.82);
      grd2.addColorStop(0, 'rgba(255,20,60,0)');
      grd2.addColorStop(0.6, 'rgba(255,24,64,0.16)');
      grd2.addColorStop(1, 'rgba(255,10,40,0.78)');
      g2.fillStyle = grd2;
      g2.fillRect(0, 0, VW, VH);
      cache.redVig = c2;
    } catch (err) { cache.redVig = null; }

    try {
      const t = document.createElement('canvas');
      t.width = 1; t.height = 3;
      const tg = t.getContext('2d');
      tg.fillStyle = 'rgba(0,0,0,0.16)';
      tg.fillRect(0, 0, 1, 1);
      cache.scanTile = t;
    } catch (err) { cache.scanTile = null; }
  }

  /* -------------------------------------------------------------- 粒子池 */
  const parts = [];
  for (let i = 0; i < MAX_PARTS; i++) {
    parts.push({
      a: false, k: '', x: 0, y: 0, vx: 0, vy: 0,
      life: 0, lifeMax: 1, size: 1, size2: 1,
      col: 'white', add: 0, drag: 0, grav: 0, rot: 0, rotV: 0
    });
  }
  let pCur = 0;

  function pAlloc() {
    const p = parts[pCur];
    pCur = (pCur + 1) % MAX_PARTS;
    p.a = true;
    p.drag = 0;
    p.grav = 0;
    p.rot = 0;
    p.rotV = 0;
    p.size2 = p.size;
    return p;
  }

  function eGlow(x, y, size, col, life) {
    if (!(life > 0)) return;
    const p = pAlloc();
    p.k = 'glow'; p.x = x; p.y = y; p.vx = 0; p.vy = 0;
    p.life = p.lifeMax = life * LIFE_MUL; p.size = size; p.col = col || 'white'; p.add = 1;
  }

  function eSpark(x, y, vx, vy, life, col, size, drag, grav) {
    if (!(life > 0)) return;
    const p = pAlloc();
    p.k = 'spark'; p.x = x; p.y = y;
    p.vx = vx * VEL_MUL; p.vy = vy * VEL_MUL;
    p.life = p.lifeMax = life * LIFE_MUL; p.size = size || 1.6; p.col = col || 'white';
    p.add = 1; p.drag = (drag == null ? 2.2 : drag) * (SHOT_MODE ? 2.2 : 1);
    p.grav = (grav == null ? 760 : grav) * GRAV_MUL;
  }

  function eShard(x, y, vx, vy, life, col, size) {
    if (!(life > 0)) return;
    const p = pAlloc();
    p.k = 'shard'; p.x = x; p.y = y;
    p.vx = vx * VEL_MUL; p.vy = vy * VEL_MUL;
    p.life = p.lifeMax = life * LIFE_MUL; p.size = size || 2.6; p.col = col || 'cyan';
    p.add = 1; p.drag = SHOT_MODE ? 3 : 1.6; p.grav = 520 * GRAV_MUL;
    p.rot = Math.random() * TAU; p.rotV = U.rand(-14, 14) * (SHOT_MODE ? 0.3 : 1);
  }

  function eRing(x, y, r0, r1, life, col, width) {
    if (!(life > 0)) return;
    const p = pAlloc();
    p.k = 'ring'; p.x = x; p.y = y; p.vx = 0; p.vy = 0;
    p.life = p.lifeMax = life * LIFE_MUL; p.size = r0; p.size2 = r1;
    p.col = col || 'cyan'; p.add = 1; p.drag = 0; p.grav = 0;
    p.rot = width == null ? 2.4 : width;
  }

  function eShock(x, y, r0, r1, life, col) {
    if (!(life > 0)) return;
    const p = pAlloc();
    p.k = 'shock'; p.x = x; p.y = y; p.vx = 0; p.vy = 0;
    p.life = p.lifeMax = life * LIFE_MUL; p.size = r0; p.size2 = r1;
    p.col = col || 'magenta'; p.add = 1; p.drag = 0; p.grav = 0;
  }

  function eStreak(x, y, rot, len, life, col, width) {
    if (!(life > 0)) return;
    const p = pAlloc();
    p.k = 'streak'; p.x = x; p.y = y; p.vx = 0; p.vy = 0;
    p.life = p.lifeMax = life * LIFE_MUL; p.size = width || 1.5; p.size2 = len || 30;
    p.col = col || 'white'; p.add = 1; p.rot = rot || 0;
  }

  function ePuff(x, y, vx, vy, size, grow, life, col) {
    if (!(life > 0)) return;
    const p = pAlloc();
    p.k = 'puff'; p.x = x; p.y = y;
    p.vx = (vx || 0) * VEL_MUL; p.vy = (vy || 0) * VEL_MUL;
    p.life = p.lifeMax = life * LIFE_MUL; p.size = size || 14;
    p.size2 = (grow || 24) * (SHOT_MODE ? 0.35 : 1);
    p.col = col || 'steel'; p.add = 1; p.drag = 1.4; p.grav = -20 * GRAV_MUL;
  }

  function eCross(x, y, size, life, col) {
    if (!(life > 0)) return;
    const p = pAlloc();
    p.k = 'cross'; p.x = x; p.y = y; p.vx = 0; p.vy = 0;
    p.life = p.lifeMax = life * LIFE_MUL; p.size = size || 24; p.col = col || 'white'; p.add = 1;
  }

  function updateParts(dt) {
    for (let i = 0; i < MAX_PARTS; i++) {
      const p = parts[i];
      if (!p.a) continue;
      p.life -= dt;
      if (p.life <= 0) { p.a = false; continue; }
      if (p.drag) {
        const d = Math.exp(-p.drag * dt);
        p.vx *= d; p.vy *= d;
      }
      if (p.grav) p.vy += p.grav * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      if (p.rotV) p.rot += p.rotV * dt;
      if (p.k === 'puff') p.size += p.size2 * dt;
    }
  }

  function drawParts(ctx, addPass) {
    const wantAdd = addPass ? 1 : 0;
    for (let i = 0; i < MAX_PARTS; i++) {
      const p = parts[i];
      if (!p.a || p.add !== wantAdd) continue;
      const f = clamp01(p.life / p.lifeMax);
      switch (p.k) {
        case 'glow': {
          const spr = glowSprite(p.col);
          if (!spr) break;
          ctx.globalAlpha = clamp01(f * f * 1.1) * (SHOT_MODE ? 0.5 : 1);
          const s = p.size;
          ctx.drawImage(spr, p.x - s * 0.5, p.y - s * 0.5, s, s);
          break;
        }
        case 'spark': {
          const a = clamp01(f * 1.7);
          ctx.strokeStyle = rgba(p.col, a.toFixed(3));
          ctx.lineWidth = p.size;
          /* 截图模式速度被压低，用更长的拖尾还原速度感 */
          const lm = SHOT_MODE ? 0.055 : 0.018;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x - p.vx * lm, p.y - p.vy * lm);
          ctx.stroke();
          break;
        }
        case 'shard': {
          const a = clamp01(f * 1.5);
          ctx.save();
          ctx.translate(p.x, p.y);
          ctx.rotate(p.rot);
          ctx.fillStyle = rgba(p.col, a.toFixed(3));
          ctx.fillRect(-p.size * 0.5, -p.size * 0.3, p.size, p.size * 0.6);
          ctx.restore();
          break;
        }
        case 'ring': {
          const pr = 1 - f;
          const r = p.size + (p.size2 - p.size) * pr;
          ctx.strokeStyle = rgba(p.col, (f * 0.85).toFixed(3));
          ctx.lineWidth = Math.max(0.7, p.rot * f);
          ctx.beginPath();
          ctx.arc(p.x, p.y, Math.max(0.5, r), 0, TAU);
          ctx.stroke();
          break;
        }
        case 'shock': {
          const pr = 1 - f;
          const r = p.size + (p.size2 - p.size) * U.easeOutQuad(pr);
          ctx.strokeStyle = rgba(p.col, (f * f * 0.8).toFixed(3));
          ctx.lineWidth = Math.max(0.8, 3.2 * f);
          ctx.beginPath();
          ctx.ellipse(p.x, p.y, Math.max(0.5, r), Math.max(0.4, r * 0.3), 0, 0, TAU);
          ctx.stroke();
          break;
        }
        case 'streak': {
          const a = clamp01(f * 1.4);
          const dx = Math.cos(p.rot) * p.size2;
          const dy = Math.sin(p.rot) * p.size2;
          ctx.strokeStyle = rgba(p.col, a.toFixed(3));
          ctx.lineWidth = p.size;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p.x + dx, p.y + dy);
          ctx.stroke();
          break;
        }
        case 'puff': {
          const spr = glowSprite(p.col);
          if (!spr) break;
          ctx.globalAlpha = clamp01(f * 0.24) * (SHOT_MODE ? 0.45 : 1);
          ctx.drawImage(spr, p.x - p.size * 0.5, p.y - p.size * 0.5, p.size, p.size);
          break;
        }
        case 'cross': {
          const a = clamp01(f * 1.3);
          const s = p.size * (0.6 + (1 - f) * 0.7);
          ctx.strokeStyle = rgba(p.col, a.toFixed(3));
          ctx.lineWidth = 2.2 * f + 0.6;
          ctx.beginPath();
          ctx.moveTo(p.x - s, p.y); ctx.lineTo(p.x + s, p.y);
          ctx.moveTo(p.x, p.y - s * 0.72); ctx.lineTo(p.x, p.y + s * 0.72);
          ctx.stroke();
          break;
        }
        default: break;
      }
    }
    ctx.globalAlpha = 1;
  }

  /* -------------------------------------------------------------- 飘字池 */
  const texts = [];
  for (let i = 0; i < MAX_TEXTS; i++) {
    texts.push({
      a: false, x: 0, y: 0, vx: 0, vy: 0, life: 0, lifeMax: 1,
      str: '', scale: 2, col: 'white', glow: '', age: 0, pixel: true, alphaMul: 1
    });
  }
  let tCur = 0;
  const ASCII_RE = /^[\x20-\x7E]+$/;

  function tAlloc() {
    const t = texts[tCur];
    tCur = (tCur + 1) % MAX_TEXTS;
    t.a = true; t.age = 0; t.alphaMul = 1; t.glow = ''; t.pixel = true;
    return t;
  }

  function spawnText(x, y, str, opts) {
    opts = opts || {};
    const t = tAlloc();
    t.x = x; t.y = y;
    t.vx = opts.vx == null ? U.rand(-12, 12) : opts.vx;
    t.vy = (opts.vy == null ? -86 : opts.vy) * (SHOT_MODE ? 0.32 : 1);
    t.life = t.lifeMax = (opts.life || 0.95) * TEXT_MUL;
    t.str = String(str == null ? '' : str);
    t.scale = Math.max(1, Math.round(opts.scale || 2));
    t.col = opts.color || 'white';
    t.pixel = ASCII_RE.test(t.str);
    t.alphaMul = opts.alpha == null ? 1 : opts.alpha;
    return t;
  }

  function updateTexts(dt) {
    for (let i = 0; i < MAX_TEXTS; i++) {
      const t = texts[i];
      if (!t.a) continue;
      t.life -= dt;
      t.age += dt;
      if (t.life <= 0) { t.a = false; continue; }
      t.vy *= Math.exp(-2.6 * dt);
      t.x += t.vx * dt;
      t.y += t.vy * dt;
    }
  }

  function drawTexts(ctx) {
    for (let i = 0; i < MAX_TEXTS; i++) {
      const t = texts[i];
      if (!t.a) continue;
      const f = clamp01(t.life / t.lifeMax);
      const alpha = clamp01(f * 3.2) * t.alphaMul;
      if (alpha <= 0.01) continue;
      /* 弹出：前 0.06s 使用更大的整数号，保证像素清晰 */
      const pop = t.age < 0.06 ? 1 : 0;
      const scale = t.scale + pop;
      const hud = NF.hud;
      if (t.pixel && hud && typeof hud.pixelText === 'function') {
        hud.pixelText(ctx, t.str, t.x, t.y, {
          scale: scale,
          color: cssColor(t.col),
          align: 'center',
          baseline: 'middle',
          alpha: alpha,
          shadow: true,
          glow: t.scale >= 3 ? '#ffd23f' : ''
        });
      } else {
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.font = 'bold ' + (scale * 10) + 'px "Microsoft YaHei", Consolas, monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(8,4,16,0.9)';
        ctx.strokeText(t.str, t.x, t.y);
        ctx.fillStyle = cssColor(t.col);
        ctx.fillText(t.str, t.x, t.y);
        ctx.restore();
      }
    }
  }

  /* ---------------------------------------------------------- 环境（雨） */
  const amb = {
    ready: false,
    rain: [],
    motes: [],
    spots: [],
    steam: []
  };

  function newDrop(initial) {
    return {
      x: U.rand(-90, VW + 90),
      y: initial ? U.rand(-40, VH) : U.rand(-160, -20),
      len: U.rand(9, 24),
      spd: U.rand(700, 1180),
      slant: U.rand(80, 170),
      gy: U.rand(330, 522),
      splash: 0,
      splashMax: 0.26,
      sx: 0,
      sy: 0
    };
  }

  function initAmbient() {
    if (amb.ready) return;
    amb.ready = true;
    for (let i = 0; i < MAX_RAIN; i++) amb.rain.push(newDrop(true));
    for (let i = 0; i < 26; i++) {
      amb.motes.push({
        x: U.rand(0, VW), y: U.rand(0, VH),
        vx: U.rand(-9, 9), vy: U.rand(-16, -4),
        s: U.rand(2, 5), ph: U.rand(0, TAU), sp: U.rand(0.3, 1.1),
        col: Math.random() < 0.5 ? 'cyan' : 'magenta',
        a: U.rand(0.05, 0.14)
      });
    }
    for (let i = 0; i < 6; i++) {
      const left = i % 2 === 0;
      amb.spots.push({
        x: left ? U.rand(20, 300) : U.rand(660, 940),
        y: i < 3 ? U.rand(20, 190) : U.rand(360, 530),
        r: U.rand(120, 280),
        col: i % 3 === 0 ? 'cyan' : (i % 3 === 1 ? 'magenta' : 'purple'),
        ph: U.rand(0, TAU), sp: U.rand(0.08, 0.2),
        a: U.rand(0.03, 0.07)
      });
    }
    for (let i = 0; i < 16; i++) {
      amb.steam.push({
        x: i % 2 === 0 ? U.rand(40, 240) : U.rand(700, 930),
        y: U.rand(320, 530),
        vy: U.rand(-22, -8),
        s: U.rand(22, 64),
        ph: U.rand(0, TAU),
        a: U.rand(0.02, 0.05)
      });
    }
  }

  function updateAmbient(dt) {
    if (!amb.ready) initAmbient();
    const rain = amb.rain;
    for (let i = 0; i < rain.length; i++) {
      const d = rain[i];
      if (d.splash > 0) {
        d.splash -= dt;
        if (d.splash <= 0) {
          const nd = newDrop(false);
          d.x = nd.x; d.y = nd.y; d.len = nd.len; d.spd = nd.spd;
          d.slant = nd.slant; d.gy = nd.gy; d.splash = 0;
        }
        continue;
      }
      d.x += d.slant * dt;
      d.y += d.spd * dt;
      if (d.y >= d.gy) {
        d.splash = U.rand(0.14, 0.3);
        d.splashMax = d.splash;
        d.sx = d.x;
        d.sy = d.gy;
      }
      if (d.y > VH + 60 || d.x > VW + 140) {
        const nd = newDrop(false);
        d.x = nd.x; d.y = nd.y; d.slant = nd.slant;
        d.len = nd.len; d.spd = nd.spd; d.gy = nd.gy;
      }
    }
    for (let i = 0; i < amb.motes.length; i++) {
      const m = amb.motes[i];
      m.ph += m.sp * dt;
      m.x += (m.vx + Math.sin(m.ph) * 6) * dt;
      m.y += m.vy * dt;
      if (m.y < -12) { m.y = VH + 10; m.x = U.rand(0, VW); }
      if (m.x < -12) m.x = VW + 10;
      if (m.x > VW + 12) m.x = -10;
    }
    for (let i = 0; i < amb.steam.length; i++) {
      const s = amb.steam[i];
      s.ph += dt;
      s.y += s.vy * dt;
      if (s.y < 250) { s.y = U.rand(500, 545); s.x = i % 2 === 0 ? U.rand(40, 240) : U.rand(700, 930); }
    }
  }

  function drawRain(ctx) {
    const rain = amb.rain;
    ctx.save();
    ctx.strokeStyle = 'rgba(158,205,255,0.24)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < rain.length; i++) {
      const d = rain[i];
      if (d.splash > 0) continue;
      ctx.moveTo(d.x, d.y);
      ctx.lineTo(d.x - d.len * 0.3, d.y - d.len);
    }
    ctx.stroke();

    /* 地面水花：两道小斜线 + 光点 */
    ctx.strokeStyle = 'rgba(196,230,255,0.34)';
    ctx.beginPath();
    for (let i = 0; i < rain.length; i++) {
      const d = rain[i];
      if (d.splash <= 0) continue;
      const k = clamp01(d.splash / d.splashMax);
      const w = 2 + (1 - k) * 4;
      ctx.moveTo(d.sx - w, d.sy);
      ctx.lineTo(d.sx - w * 0.3, d.sy - 2 - (1 - k) * 2);
      ctx.moveTo(d.sx + w, d.sy);
      ctx.lineTo(d.sx + w * 0.3, d.sy - 2 - (1 - k) * 2);
    }
    ctx.stroke();
    ctx.restore();
  }

  function drawAmbientGlow(ctx, time) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    /* 霓虹光斑 */
    for (let i = 0; i < amb.spots.length; i++) {
      const s = amb.spots[i];
      const spr = glowSprite(s.col);
      if (!spr) continue;
      const px = s.x + Math.sin(time * s.sp + s.ph) * 26;
      const py = s.y + Math.cos(time * s.sp * 0.7 + s.ph) * 18;
      ctx.globalAlpha = s.a * (0.75 + 0.25 * Math.sin(time * 0.6 + s.ph));
      ctx.drawImage(spr, px - s.r * 0.5, py - s.r * 0.5, s.r, s.r);
    }
    /* 蒸汽 */
    for (let i = 0; i < amb.steam.length; i++) {
      const s = amb.steam[i];
      const spr = glowSprite('steel');
      if (!spr) continue;
      ctx.globalAlpha = s.a * (0.6 + 0.4 * Math.sin(s.ph));
      const px = s.x + Math.sin(s.ph * 1.3) * 18;
      ctx.drawImage(spr, px - s.s * 0.5, s.y - s.s * 0.5, s.s, s.s);
    }
    /* 漂浮尘埃 */
    for (let i = 0; i < amb.motes.length; i++) {
      const m = amb.motes[i];
      const spr = glowSprite(m.col);
      if (!spr) continue;
      ctx.globalAlpha = m.a * (0.55 + 0.45 * Math.sin(m.ph));
      ctx.drawImage(spr, m.x - m.s * 0.5, m.y - m.s * 0.5, m.s, m.s);
    }
    ctx.restore();
  }

  /* -------------------------------------------------------- 屏幕状态特效 */
  const state = {
    shakeMag: 0, shakeT: 0, shakeDur: 0.25, sx: 0, sy: 0,
    flashes: [],
    ko: { t: 0, dur: 0, max: 0 },
    speed: { t: 0, dur: 0, max: 0, dir: 0 },
    special: { t: 0, dur: 0, max: 0, x: VW * 0.5, y: VH * 0.5 },
    roar: { t: 0, dur: 0, max: 0, x: VW * 0.5, y: VH * 0.5 }
  };

  function normFlashColor(color) {
    if (!color) return { css: 'rgb(255,255,255)', add: true };
    const s = String(color).trim();
    const low = s.toLowerCase();
    if (RGB[low]) return { css: colorCss(low), add: low !== 'red' };
    if (low === 'white' || low === '#fff' || low === '#ffffff') return { css: '#ffffff', add: true };
    if (low === 'red' || low === '#f00' || low === '#ff0000') return { css: '#ff3b5c', add: false };
    if (s.charAt(0) === '#' && (s.length === 4 || s.length === 7)) {
      let hex = s.slice(1);
      if (hex.length === 3) hex = hex.charAt(0) + hex.charAt(0) + hex.charAt(1) + hex.charAt(1) + hex.charAt(2) + hex.charAt(2);
      const r = parseInt(hex.slice(0, 2), 16) || 0;
      const g = parseInt(hex.slice(2, 4), 16) || 0;
      const b = parseInt(hex.slice(4, 6), 16) || 0;
      return { css: 'rgb(' + r + ',' + g + ',' + b + ')', add: !(r > 140 && g < 110 && b < 130) };
    }
    return { css: s, add: true };
  }

  function screenPosWorld(x, y) {
    const camX = NF.camera && typeof NF.camera.x === 'number' ? NF.camera.x : 0;
    return { x: x - camX, y: y };
  }

  /* --------------------------------------------------- 游戏状态自动联动 */
  function watchGame() {
    const game = NF.game;
    if (!game) return;
    const p = game.player;
    if (p && p.anim !== api._lastAnim) {
      if (p.anim === 'special' && !cfg.SHOT) api.specialFlash();
      api._lastAnim = p.anim;
    }
    const boss = game.boss;
    if (boss && boss.anim !== api._lastBossAnim) {
      if (boss.anim === 'roar' && !cfg.SHOT) {
        api.roar(typeof boss.x === 'number' ? boss.x : (p ? p.x + 300 : 700),
          (typeof boss.y === 'number' ? boss.y : 470) - 165, 1.25);
      }
      api._lastBossAnim = boss.anim;
    }
    if (!cfg.SHOT) {
      const st = game.state;
      if (st !== api._lastState) {
        if (st === 'gameover' && api._lastState && api._lastState !== 'title') {
          api.koLines(1.9);
          api.flash('red', 0.42, 0.75);
          api.shake(7, 0.5);
        } else if (st === 'victory' && api._lastState && api._lastState !== 'title') {
          api.specialFlash();
        }
        api._lastState = st;
      }
      const combo = game.combo | 0;
      if (combo > api._lastCombo && combo >= 10 && combo % 10 === 0 && p) {
        api.comboBurst(p.x + (p.facing === -1 ? -40 : 40), (p.y || 470) - 120, combo);
      }
      api._lastCombo = combo;
    }
  }

  /* --------------------------------------------- 截图场景预览（无 gameplay 数据时）
   * 仅在 URL 带 ?shot= 且玩法模块未接管（game.shotFrozen 为假）时启用，
   * 用于自检特效外观；真实玩法 debugStart 会设置 shotFrozen=true，此时自动关闭。 */
  function previewTick(dt) {
    const shot = cfg.SHOT;
    if (!shot) return;
    const game = NF.game;
    if (!game || game.shotFrozen) return;
    api._pv = (api._pv || 0) + dt;
    const prev = api._pv - dt;
    const p = game.player;
    const px = p && typeof p.x === 'number' ? p.x : 520;
    const py = p && typeof p.y === 'number' ? p.y : 470;
    const facing = p && p.facing === -1 ? -1 : 1;
    const hx = px + facing * 92;
    const hy = py - 132;

    if (shot === 'battle') {
      if (Math.floor(api._pv / 0.8) !== Math.floor(prev / 0.8)) {
        doHitSpark(hx, hy, facing, 0.5);
        doDamageNumber(hx, hy - 6, [6, 8, 14, 18][Math.floor(api._pv / 0.8) % 4], {});
      }
    } else if (shot === 'combo') {
      if (Math.floor(api._pv / 0.18) !== Math.floor(prev / 0.18)) {
        doHitSpark(hx + U.rand(-26, 24), hy + U.rand(-30, 34), facing, U.rand(0.35, 0.95));
        doDamageNumber(hx + U.rand(-22, 22), hy + U.rand(-26, 12), U.randInt(6, 24), { big: Math.random() < 0.3 });
      }
    } else if (shot === 'boss' || shot === 'intro') {
      if (Math.floor(api._pv / 1.4) !== Math.floor(prev / 1.4)) {
        const boss = game.boss;
        const bx = boss && typeof boss.x === 'number' ? boss.x : px + 320;
        const by = boss && typeof boss.y === 'number' ? boss.y : py;
        api.roar(bx, by - 165, 1.15);
      }
    } else if (shot === 'victory') {
      if (Math.floor(api._pv / 0.1) !== Math.floor(prev / 0.1)) {
        const cx = (NF.camera && NF.camera.x ? NF.camera.x : 0) + U.rand(110, 850);
        const cy = U.rand(80, 220);
        const col = pick3('lime', 'cyan', 'magenta');
        eSpark(cx, cy, U.rand(-70, 70), U.rand(40, 150), U.rand(0.7, 1.5), col, U.rand(1.5, 2.6), 0.5, 60);
        if (Math.random() < 0.35) eGlow(cx, cy, U.rand(10, 24), pick('yellow', 'cyan'), U.rand(0.5, 0.9));
      }
    }
  }

  /* ------------------------------------------------------------ 命中特效 */
  function doHitSpark(x, y, dir, power) {
    if (typeof x !== 'number' || typeof y !== 'number' || !isFinite(x) || !isFinite(y)) return;
    const pw = clamp01(power == null ? 0.5 : power);
    const d = dir === -1 ? -1 : 1;

    /* 白/黄核心 + 光晕 */
    eGlow(x, y, 26 + pw * 34, 'white', 0.07 + pw * 0.08);
    eGlow(x, y, 44 + pw * 54, 'yellow', 0.12 + pw * 0.12);
    eGlow(x + d * 6, y, 52 + pw * 62, pick('cyan', 'magenta'), 0.11 + pw * 0.12);
    eCross(x, y, 16 + pw * 30, 0.09 + pw * 0.06, 'white');

    /* 白/黄火星 */
    const nSpark = Math.round(7 + pw * 13);
    for (let i = 0; i < nSpark; i++) {
      const ang = (d > 0 ? 0 : Math.PI) + U.rand(-1, 1) * (0.6 + pw * 0.55);
      const spd = U.rand(240, 470) * (0.8 + pw * 0.95);
      eSpark(
        x + U.rand(-4, 4), y + U.rand(-5, 5),
        Math.cos(ang) * spd, Math.sin(ang) * spd - U.rand(0, 80),
        U.rand(0.16, 0.34) * (0.85 + pw * 0.7),
        Math.random() < 0.55 ? 'white' : 'yellow',
        U.rand(1, 2.4)
      );
    }

    /* 青/品红碎光 */
    const nShard = Math.round(4 + pw * 9);
    for (let i = 0; i < nShard; i++) {
      const ang = U.rand(0, TAU);
      const spd = U.rand(110, 330) * (0.7 + pw * 0.8);
      eShard(
        x + U.rand(-6, 6), y + U.rand(-6, 6),
        Math.cos(ang) * spd, Math.sin(ang) * spd - U.rand(20, 120),
        U.rand(0.34, 0.72), i % 2 ? 'cyan' : 'magenta', U.rand(1.6, 4)
      );
    }

    /* 冲击环 */
    eRing(x, y, 3, 24 + pw * 36, 0.24 + pw * 0.14, pick('cyan', 'white'), 2.6);
    eRing(x, y, 2, 13 + pw * 18, 0.15, 'white', 1.7);

    /* 短速度线 */
    const nStreak = 3 + Math.round(pw * 4);
    for (let i = 0; i < nStreak; i++) {
      eStreak(
        x + U.rand(-8, 8), y + U.rand(-10, 10),
        (d > 0 ? 0 : Math.PI) + U.rand(-0.38, 0.38),
        U.rand(24, 56) * (0.7 + pw * 0.9),
        U.rand(0.1, 0.2),
        pick3('cyan', 'magenta', 'white'),
        U.rand(1, 2.1)
      );
    }

    /* 重击：低频冲击波 + 大光斑 */
    if (pw >= 0.62) {
      eShock(x, y + 16, 8, 62 + pw * 96, 0.44, pick('cyan', 'magenta'));
      eGlow(x, y, 92 + pw * 58, pick('cyan', 'magenta'), 0.16);
      for (let i = 0; i < 5; i++) {
        ePuff(x + U.rand(-30, 30), y + U.rand(-8, 22), U.rand(-56, 56) * d, U.rand(-36, 8),
          U.rand(16, 30), 46, U.rand(0.4, 0.7), pick('cyan', 'magenta'));
      }
    }
    if (pw >= 0.85) {
      eGlow(x, y, 138, 'white', 0.09);
      eShock(x, y + 24, 12, 170, 0.55, 'white');
    }
  }

  function doDamageNumber(x, y, amount, opts) {
    opts = opts || {};
    const big = !!opts.big;
    const col = opts.color ? String(opts.color) : (big ? 'yellow' : 'white');
    if (big) {
      eGlow(x, y, 46, 'yellow', 0.22);
    }
    spawnText(x + U.rand(-7, 7), y + U.rand(-4, 4), Math.round(Number(amount) || 0), {
      color: col,
      scale: big ? 3 : 2,
      life: big ? 1.15 : 0.9,
      vy: big ? -104 : -84,
      alpha: 1
    });
  }

  /* ------------------------------------------------------------ 公共 API */
  const api = {
    time: 0,
    _lastAnim: '',
    _lastBossAnim: '',
    _lastState: '',
    _lastCombo: 0,
    _pv: 0,

    update(dt) {
      dt = Math.min(0.05, Math.max(0, Number(dt) || 0));
      this.time += dt;
      buildScreenLayers();

      /* 震屏衰减（可叠加） */
      if (state.shakeT > 0) {
        state.shakeT -= dt;
        const k = clamp01(state.shakeT / Math.max(0.0001, state.shakeDur));
        const amp = state.shakeMag * k * k;
        const t = this.time;
        state.sx = (Math.sin(t * 143.7) * 0.62 + Math.sin(t * 91.3 + 1.3) * 0.38) * amp;
        state.sy = (Math.cos(t * 151.1) * 0.55 + Math.sin(t * 83.7 + 2.1) * 0.45) * amp * 0.72;
      } else {
        state.sx = 0;
        state.sy = 0;
      }

      /* 闪屏倒计时 */
      for (let i = state.flashes.length - 1; i >= 0; i--) {
        const f = state.flashes[i];
        f.t -= dt;
        if (f.t <= 0) state.flashes.splice(i, 1);
      }

      /* 状态特效计时 */
      tickTimer(state.ko, dt);
      tickTimer(state.speed, dt);
      tickTimer(state.special, dt);
      tickTimer(state.roar, dt);

      updateParts(dt);
      updateTexts(dt);
      updateAmbient(dt);
      watchGame();
      previewTick(dt);
    },

    draw(ctx) {
      if (!ctx) return;
      /* 实心层：碎光、速度线 */
      ctx.save();
      drawParts(ctx, false);
      ctx.globalCompositeOperation = 'lighter';
      drawParts(ctx, true);
      ctx.globalCompositeOperation = 'source-over';
      drawTexts(ctx);
      ctx.restore();
    },

    drawOverlay(ctx) {
      if (!ctx) return;
      buildScreenLayers();
      initAmbient();
      const t = this.time;

      /* 1. 环境霓虹光斑 / 蒸汽 / 尘埃（低透明度，不遮挡角色） */
      drawAmbientGlow(ctx, t);

      /* 2. 雨 + 地面水花 */
      drawRain(ctx);

      /* 3. 必杀放射速度线 */
      if (state.speed.t > 0) {
        const p = 1 - state.speed.t / state.speed.max;
        drawRadiantLines(ctx, clamp01(p), state.speed.dir);
      }

      /* 4. 必杀霓虹环 */
      if (state.special.t > 0) {
        const p = 1 - state.special.t / state.special.max;
        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        for (let i = 0; i < 3; i++) {
          const r = 40 + U.easeOutQuad(clamp01(p)) * (360 + i * 180);
          ctx.strokeStyle = rgba(i % 2 ? 'cyan' : 'magenta', (0.5 * (1 - p) * (i === 0 ? 1 : 0.6)).toFixed(3));
          ctx.lineWidth = 4 - i;
          ctx.beginPath();
          ctx.arc(state.special.x, state.special.y + i * 12, r, 0, TAU);
          ctx.stroke();
        }
        ctx.restore();
      }

      /* 5. Boss 咆哮红光 */
      if (state.roar.t > 0) {
        const p = 1 - state.roar.t / state.roar.max;
        const pulse = Math.sin(Math.min(1, p) * Math.PI);
        ctx.save();
        if (cache.redVig) {
          ctx.globalAlpha = 0.55 * pulse;
          ctx.drawImage(cache.redVig, 0, 0);
          ctx.globalAlpha = 1;
        }
        ctx.globalCompositeOperation = 'lighter';
        for (let i = 0; i < 3; i++) {
          const r = 20 + U.easeOutQuad(clamp01(p)) * (150 + i * 130);
          ctx.strokeStyle = rgba('red', (0.6 * (1 - p)).toFixed(3));
          ctx.lineWidth = 3 - i * 0.7;
          ctx.beginPath();
          ctx.arc(state.roar.x, state.roar.y, r, 0, TAU);
          ctx.stroke();
        }
        ctx.restore();
      }

      /* 6. KO 慢镜速度线 */
      if (state.ko.t > 0) {
        drawKoSpeed(ctx, clamp01(1 - state.ko.t / state.ko.max));
      }

      /* 7. 低血量红色边缘 */
      const game = NF.game;
      const p = game && game.player;
      if (p && p.maxHp > 0 && typeof p.hp === 'number') {
        const r = clamp(p.hp / p.maxHp, 0, 1);
        if (r <= 0.34 && cache.redVig) {
          const pulse = 0.5 + 0.5 * Math.sin(t * 7.4);
          const a = ((0.34 - r) / 0.34) * (0.16 + 0.2 * pulse);
          ctx.save();
          ctx.globalAlpha = a;
          ctx.drawImage(cache.redVig, 0, 0);
          ctx.restore();
        }
      }

      /* 8. 暗角 */
      if (cache.vignette) ctx.drawImage(cache.vignette, 0, 0);

      /* 9. 极轻扫描线 */
      if (cache.scanTile && !cache.scanPattern && ctx.createPattern) {
        try { cache.scanPattern = ctx.createPattern(cache.scanTile, 'repeat'); } catch (err) { cache.scanPattern = null; }
      }
      if (cache.scanPattern) {
        ctx.save();
        ctx.globalAlpha = 0.55;
        ctx.fillStyle = cache.scanPattern;
        ctx.fillRect(0, 0, VW, VH);
        ctx.restore();
      }
    },

    drawTop(ctx) {
      if (!ctx) return;
      const list = state.flashes;
      if (!list.length) return;
      ctx.save();
      for (let i = 0; i < list.length; i++) {
        const f = list[i];
        const k = clamp01(f.t / f.dur);
        const a = f.a * Math.pow(k, 1.4);
        if (a <= 0.004) continue;
        ctx.globalCompositeOperation = f.add ? 'lighter' : 'source-over';
        ctx.globalAlpha = a;
        if (f.neon) {
          const g = ctx.createLinearGradient(0, 0, VW, VH);
          g.addColorStop(0, 'rgba(61,243,255,0.95)');
          g.addColorStop(0.42, 'rgba(255,255,255,1)');
          g.addColorStop(0.72, 'rgba(255,47,142,0.95)');
          g.addColorStop(1, 'rgba(122,60,255,0.9)');
          ctx.fillStyle = g;
        } else {
          ctx.fillStyle = f.css;
        }
        ctx.fillRect(0, 0, VW, VH);
      }
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
      ctx.restore();
    },

    shakeOffset() { return { x: state.sx, y: state.sy }; },

    shake(mag, dur) {
      const m = Math.abs(Number(mag) || 0);
      if (m <= 0) return;
      const d = Math.max(0.05, Number(dur) || 0.25);
      state.shakeMag = Math.min(30, Math.max(m, state.shakeMag * 0.72));
      state.shakeT = Math.max(d, state.shakeT);
      state.shakeDur = state.shakeT;
    },

    flash(color, alpha, dur) {
      const c = normFlashColor(color);
      const a = clamp01(alpha == null ? 0.5 : alpha);
      const d = Math.max(0.05, Number(dur) || 0.24);
      if (state.flashes.length >= MAX_FLASH) state.flashes.shift();
      state.flashes.push({ css: c.css, add: c.add, a: a, t: d, dur: d, neon: false });
    },

    hitSpark(x, y, dir, power) { doHitSpark(x, y, dir, power); },

    dust(x, y, opts) {
      opts = opts || {};
      const n = Math.max(1, Math.min(14, opts.count | 0 || 6));
      const col = opts.color || 'steel';
      const dir = Number(opts.dir) || 0;
      const spread = opts.spread == null ? 1 : opts.spread;
      for (let i = 0; i < n; i++) {
        const ang = (opts.up ? -Math.PI * 0.5 : Math.PI * 0.5) + U.rand(-1.15, 1.15);
        ePuff(
          x + U.rand(-10, 10) * spread, y + U.rand(-4, 4),
          Math.cos(ang) * U.rand(18, 80) + dir * 30,
          Math.sin(ang) * U.rand(8, 42),
          U.rand(9, 20), U.rand(20, 52), U.rand(0.4, 0.85), col
        );
      }
      eRing(x, y, 3, U.rand(14, 28), 0.28, col, 1.3);
    },

    damageNumber(x, y, amount, opts) { doDamageNumber(x, y, amount, opts); },

    text(x, y, str, opts) {
      opts = opts || {};
      spawnText(x, y, str, {
        color: opts.color || 'white',
        scale: opts.scale || opts.size || 2,
        life: opts.life || 1.1,
        vy: opts.vy == null ? -54 : opts.vy,
        vx: opts.vx,
        alpha: opts.alpha
      });
    },

    ring(x, y, opts) {
      opts = opts || {};
      eRing(x, y, opts.r0 || 6, opts.r1 || 60, opts.life || 0.4,
        opts.color || 'cyan', opts.width || 2.5);
      if (opts.shock) eShock(x, y + 12, 8, (opts.r1 || 60) * 1.6, (opts.life || 0.4) * 1.2, opts.color || 'magenta');
    },

    speedLines(dur, dir) {
      const d = Math.max(0.1, Number(dur) || 0.5);
      state.speed.max = d;
      state.speed.t = d;
      state.speed.dir = dir || 0;
    },

    koLines(dur) {
      const d = Math.max(0.2, Number(dur) || 1.4);
      state.ko.max = d;
      state.ko.t = d;
    },

    koBurst(x, y) {
      doHitSpark(x, y, 1, 1);
      doHitSpark(x, y, -1, 0.8);
      eGlow(x, y, 200, 'white', 0.24);
      eShock(x, y + 10, 10, 220, 0.6, 'white');
      api.koLines(1.6);
      api.flash('white', 0.55, 0.4);
      api.shake(10, 0.55);
    },

    specialFlash() {
      const g = NF.game;
      const p = g && g.player;
      const pos = p && typeof p.x === 'number' ? screenPosWorld(p.x, (p.y || 470) - 130) : { x: VW * 0.5, y: VH * 0.5 };
      state.special.max = 0.8;
      state.special.t = 0.8;
      state.special.x = pos.x;
      state.special.y = pos.y;
      state.speed.max = 0.7;
      state.speed.t = 0.7;
      state.speed.dir = p && p.facing === -1 ? -1 : 1;
      if (state.flashes.length >= MAX_FLASH) state.flashes.shift();
      state.flashes.push({ css: '', add: true, a: 0.9, t: 0.5, dur: 0.5, neon: true });
      api.shake(9, 0.5);
    },

    roar(x, y, dur) {
      const d = Math.max(0.3, Number(dur) || 1.2);
      const pos = typeof x === 'number' ? screenPosWorld(x, typeof y === 'number' ? y : 340) : { x: VW * 0.5, y: VH * 0.42 };
      state.roar.max = d;
      state.roar.t = d;
      state.roar.x = pos.x;
      state.roar.y = pos.y;
      api.shake(6, d * 0.7);
      if (typeof x === 'number' && typeof y === 'number') {
        eGlow(x, y, 60, 'red', 0.5);
        eGlow(x, y, 120, 'red', 0.32);
        for (let i = 0; i < 18; i++) {
          const ang = U.rand(0, TAU);
          eSpark(x + U.rand(-40, 40), y + U.rand(-20, 40),
            Math.cos(ang) * U.rand(60, 220), Math.sin(ang) * U.rand(40, 180) - 60,
            U.rand(0.4, 0.9), pick3('red', 'magenta', 'orange'), U.rand(1.4, 3));
        }
      }
    },

    comboBurst(x, y, n) {
      eGlow(x, y, 90, 'yellow', 0.3);
      eShock(x, y + 30, 6, 140, 0.5, 'yellow');
      eRing(x, y, 6, 70, 0.36, 'cyan', 2.6);
      for (let i = 0; i < 12; i++) {
        const ang = U.rand(0, TAU);
        eSpark(x, y, Math.cos(ang) * U.rand(140, 340), Math.sin(ang) * U.rand(120, 300) - 60,
          U.rand(0.3, 0.6), pick3('yellow', 'cyan', 'white'), U.rand(1.4, 2.6));
      }
      spawnText(x, y - 46, 'COMBO ' + String(n | 0), { color: 'yellow', scale: 3, life: 0.9, vy: -70 });
      api.shake(3, 0.16);
    },

    clear() {
      for (let i = 0; i < MAX_PARTS; i++) parts[i].a = false;
      for (let i = 0; i < MAX_TEXTS; i++) texts[i].a = false;
      state.flashes.length = 0;
      state.shakeMag = 0; state.shakeT = 0; state.shakeDur = 0.25; state.sx = 0; state.sy = 0;
      state.ko.t = 0; state.speed.t = 0; state.special.t = 0; state.roar.t = 0;
      this._pv = 0;
      this._lastAnim = '';
      this._lastBossAnim = '';
      this._lastState = '';
      this._lastCombo = 0;
    }
  };

  function tickTimer(tm, dt) {
    if (tm.t > 0) {
      tm.t -= dt;
      if (tm.t < 0) tm.t = 0;
    }
  }

  function drawRadiantLines(ctx, progress, dir) {
    const cx = VW * 0.5;
    const cy = VH * 0.52;
    const n = 30;
    const fade = Math.sin(clamp01(progress) * Math.PI);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < n; i++) {
      const h = U.hash(i * 7.13 + 1.7);
      const ang = (i / n) * TAU + h * 0.4 + (dir < 0 ? 0.12 : 0);
      const r0 = 100 + h * 190 + progress * 190;
      const len = 60 + h * 150;
      const a = fade * (0.1 + 0.26 * h);
      ctx.strokeStyle = rgba(i % 2 ? 'cyan' : 'magenta', a.toFixed(3));
      ctx.lineWidth = 1 + h * 1.8;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(ang) * r0, cy + Math.sin(ang) * r0);
      ctx.lineTo(cx + Math.cos(ang) * (r0 + len), cy + Math.sin(ang) * (r0 + len));
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawKoSpeed(ctx, progress) {
    const fade = Math.sin(clamp01(progress) * Math.PI);
    ctx.save();
    ctx.fillStyle = 'rgba(10,8,32,' + (0.16 * fade).toFixed(3) + ')';
    ctx.fillRect(0, 0, VW, VH);
    ctx.globalCompositeOperation = 'lighter';
    const n = 20;
    for (let i = 0; i < n; i++) {
      const h = U.hash(i * 3.77 + 0.3);
      const y = h * VH;
      const toRight = i % 2 === 0;
      const len = 130 + h * 300;
      const x = toRight
        ? (-progress * 420 + h * VW + 120)
        : (VW - h * VW - 120 + progress * 420);
      const a = fade * (0.05 + h * 0.12);
      ctx.fillStyle = 'rgba(222,236,255,' + a.toFixed(3) + ')';
      ctx.fillRect(Math.round(x), Math.round(y), Math.round(len), h > 0.72 ? 2 : 1);
    }
    ctx.restore();
  }

  /* 初始化离屏资源（首次 update 时创建，避免脚本加载期开销） */
  buildScreenLayers();

  NF.fx = api;
})();
