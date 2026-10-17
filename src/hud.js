/* ============================================================================
 * 霓虹拳魂 NEON FIST SOUL — HUD / 菜单 / 像素字体
 * 960×540 屏幕坐标。像素街机风：深色半透明面板 + 霓虹描边 + 斜切角 + 扫描线。
 *
 * 对外 API（契约 §2.10）：
 *   NF.hud.init()
 *   NF.hud.draw(ctx, game, time)        每帧绘制全部 UI（按 game.state 分支）
 *   NF.hud.toast(text, opts)            顶部短提示
 *   NF.hud.pixelText(ctx, text, x, y, opts)   5×7 像素字（ASCII）
 *   NF.hud.drawPortrait(ctx, charName, x, y, size, opts)   角色头像（左上角坐标）
 *   NF.hud.cnText(ctx, text, x, y, opts)      中文粗体 + 描边（内部/外部均可用）
 *
 * HUD 只读取 game 字段（契约 §2.12），所有字段缺失时都有安全兜底。
 * ========================================================================== */
window.NF = window.NF || {};

(function () {
  'use strict';
  const NF = window.NF;
  const cfg = NF.config;
  const U = NF.util;
  const VW = cfg.VIEW_W;
  const VH = cfg.VIEW_H;
  const C = cfg.COLORS;
  const clamp = U.clamp;
  const clamp01 = U.clamp01;
  const num = (v, d) => (typeof v === 'number' && isFinite(v) ? v : d);

  const CN_FONT = '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", "Heiti SC", "SimHei", sans-serif';

  /* ========================================================================
   *  5×7 ASCII 点阵字体
   * ===================================================================== */
  const FONT_SRC = {
    ' ': '00000/00000/00000/00000/00000/00000/00000',
    '!': '00100/00100/00100/00100/00100/00000/00100',
    '"': '01010/01010/00000/00000/00000/00000/00000',
    '#': '01010/01010/11111/01010/11111/01010/01010',
    '$': '00100/01111/10100/01110/00101/11110/00100',
    '%': '11001/11010/00010/00100/01000/01011/10011',
    '&': '01100/10010/10100/01000/10101/10010/01101',
    "'": '00100/00100/00000/00000/00000/00000/00000',
    '(': '00010/00100/01000/01000/01000/00100/00010',
    ')': '01000/00100/00010/00010/00010/00100/01000',
    '*': '00000/10101/01110/11111/01110/10101/00000',
    '+': '00000/00100/00100/11111/00100/00100/00000',
    ',': '00000/00000/00000/00000/00110/00100/01000',
    '-': '00000/00000/00000/11111/00000/00000/00000',
    '.': '00000/00000/00000/00000/00000/01100/01100',
    '/': '00001/00010/00010/00100/01000/01000/10000',
    '0': '01110/10001/10011/10101/11001/10001/01110',
    '1': '00100/01100/00100/00100/00100/00100/01110',
    '2': '01110/10001/00001/00010/00100/01000/11111',
    '3': '11110/00001/00001/01110/00001/00001/11110',
    '4': '00010/00110/01010/10010/11111/00010/00010',
    '5': '11111/10000/11110/00001/00001/10001/01110',
    '6': '00110/01000/10000/11110/10001/10001/01110',
    '7': '11111/00001/00010/00100/01000/01000/01000',
    '8': '01110/10001/10001/01110/10001/10001/01110',
    '9': '01110/10001/10001/01111/00001/00010/01100',
    ':': '00000/01100/01100/00000/01100/01100/00000',
    ';': '00000/01100/01100/00000/01100/00100/01000',
    '<': '00010/00100/01000/10000/01000/00100/00010',
    '=': '00000/00000/11111/00000/11111/00000/00000',
    '>': '01000/00100/00010/00001/00010/00100/01000',
    '?': '01110/10001/00001/00110/00100/00000/00100',
    '@': '01110/10001/10111/10101/10111/10000/01110',
    'A': '01110/10001/10001/11111/10001/10001/10001',
    'B': '11110/10001/10001/11110/10001/10001/11110',
    'C': '01110/10001/10000/10000/10000/10001/01110',
    'D': '11110/10001/10001/10001/10001/10001/11110',
    'E': '11111/10000/10000/11110/10000/10000/11111',
    'F': '11111/10000/10000/11110/10000/10000/10000',
    'G': '01110/10001/10000/10111/10001/10001/01110',
    'H': '10001/10001/10001/11111/10001/10001/10001',
    'I': '11111/00100/00100/00100/00100/00100/11111',
    'J': '00111/00010/00010/00010/00010/10010/01100',
    'K': '10001/10010/10100/11000/10100/10010/10001',
    'L': '10000/10000/10000/10000/10000/10000/11111',
    'M': '10001/11011/10101/10101/10001/10001/10001',
    'N': '10001/11001/10101/10011/10001/10001/10001',
    'O': '01110/10001/10001/10001/10001/10001/01110',
    'P': '11110/10001/10001/11110/10000/10000/10000',
    'Q': '01110/10001/10001/10001/10101/10010/01101',
    'R': '11110/10001/10001/11110/10100/10010/10001',
    'S': '01111/10000/10000/01110/00001/00001/11110',
    'T': '11111/00100/00100/00100/00100/00100/00100',
    'U': '10001/10001/10001/10001/10001/10001/01110',
    'V': '10001/10001/10001/10001/10001/01010/00100',
    'W': '10001/10001/10001/10101/10101/11011/10001',
    'X': '10001/10001/01010/00100/01010/10001/10001',
    'Y': '10001/10001/01010/00100/00100/00100/00100',
    'Z': '11111/00001/00010/00100/01000/10000/11111',
    '[': '01110/01000/01000/01000/01000/01000/01110',
    '\\': '10000/01000/01000/00100/00010/00010/00001',
    ']': '01110/00010/00010/00010/00010/00010/01110',
    '^': '00100/01010/10001/00000/00000/00000/00000',
    '_': '00000/00000/00000/00000/00000/00000/11111',
    '`': '01000/00100/00010/00000/00000/00000/00000',
    '{': '00110/01000/01000/11000/01000/01000/00110',
    '|': '00100/00100/00100/00100/00100/00100/00100',
    '}': '01100/00010/00010/00011/00010/00010/01100',
    '~': '00000/00000/01001/10110/00000/00000/00000'
  };

  const GLYPHS = Object.create(null);
  (function parseFont() {
    Object.keys(FONT_SRC).forEach((ch) => {
      const rows = FONT_SRC[ch].split('/');
      const bits = [];
      for (let r = 0; r < 7; r++) {
        const row = rows[r] || '00000';
        let v = 0;
        for (let c = 0; c < 5; c++) if (row.charAt(c) === '1') v |= (16 >> c);
        bits.push(v);
      }
      GLYPHS[ch] = bits;
    });
  })();

  function drawGlyphs(ctx, str, x, y, scale, spacing, color) {
    ctx.fillStyle = color;
    let cx = x;
    for (let i = 0; i < str.length; i++) {
      const rows = GLYPHS[str.charAt(i)];
      if (rows) {
        for (let r = 0; r < 7; r++) {
          const bits = rows[r];
          if (!bits) continue;
          const ry = y + r * scale;
          let run = 0;
          for (let c = 0; c <= 5; c++) {
            const on = c < 5 && (bits & (16 >> c));
            if (on) {
              run++;
            } else if (run > 0) {
              ctx.fillRect(cx + (c - run) * scale, ry, run * scale, scale);
              run = 0;
            }
          }
        }
      }
      cx += (5 + spacing) * scale;
    }
  }

  function measurePixel(str, scale, spacing) {
    str = String(str == null ? '' : str);
    if (!str.length) return 0;
    scale = Math.max(1, Math.round(scale || 2));
    spacing = spacing == null ? 1 : Math.max(0, spacing | 0);
    return (str.length * (5 + spacing) - spacing) * scale;
  }

  /* 像素字：x/y 默认按 alphabetic（y 为基线，与旧占位实现一致） */
  function pixelText(ctx, text, x, y, opts) {
    opts = opts || {};
    if (text == null) return 0;
    const str = String(text).toUpperCase();
    const scale = Math.max(1, Math.round(opts.scale || opts.size || 2));
    const spacing = opts.spacing == null ? 1 : Math.max(0, opts.spacing | 0);
    const width = measurePixel(str, scale, spacing);
    let x0 = x;
    const align = opts.align || 'left';
    if (align === 'center') x0 = x - width * 0.5;
    else if (align === 'right') x0 = x - width;
    const bl = opts.baseline || 'alphabetic';
    let y0 = y;
    if (bl === 'top') y0 = y;
    else if (bl === 'middle') y0 = y - 7 * scale * 0.5;
    else y0 = y - 7 * scale;
    x0 = Math.round(x0);
    y0 = Math.round(y0);

    ctx.save();
    if (opts.alpha != null) ctx.globalAlpha *= clamp01(opts.alpha);
    ctx.imageSmoothingEnabled = false;
    const main = opts.gradient || opts.color || '#f7f1ff';
    if (opts.shadow !== false) {
      drawGlyphs(ctx, str, x0 + Math.max(1, scale), y0 + Math.max(1, scale), scale, spacing,
        opts.shadowColor || 'rgba(8,4,16,0.88)');
    }
    if (opts.outline) {
      const oc = opts.outlineColor || 'rgba(8,4,16,0.95)';
      const o = Math.max(1, scale);
      drawGlyphs(ctx, str, x0 - o, y0, scale, spacing, oc);
      drawGlyphs(ctx, str, x0 + o, y0, scale, spacing, oc);
      drawGlyphs(ctx, str, x0, y0 - o, scale, spacing, oc);
      drawGlyphs(ctx, str, x0, y0 + o, scale, spacing, oc);
    }
    if (opts.glow) {
      ctx.save();
      ctx.shadowColor = opts.glow;
      ctx.shadowBlur = opts.glowBlur == null ? 9 : opts.glowBlur;
      drawGlyphs(ctx, str, x0, y0, scale, spacing, main);
      ctx.restore();
    }
    drawGlyphs(ctx, str, x0, y0, scale, spacing, main);
    ctx.restore();
    return width;
  }

  /* 中文：整数像素字号 + 深色描边 + 可选发光 */
  function cnText(ctx, text, x, y, opts) {
    opts = opts || {};
    if (text == null) return 0;
    const str = String(text);
    const size = Math.max(8, Math.round(opts.size || 16));
    const weight = opts.weight || 'bold';
    ctx.save();
    ctx.font = weight + ' ' + size + 'px ' + CN_FONT;
    ctx.textAlign = opts.align || 'left';
    ctx.textBaseline = opts.baseline || 'alphabetic';
    if (opts.alpha != null) ctx.globalAlpha *= clamp01(opts.alpha);
    const outline = opts.outline === false ? null : (opts.outlineColor || 'rgba(9,5,17,0.94)');
    if (outline) {
      ctx.lineJoin = 'round';
      ctx.miterLimit = 2;
      ctx.lineWidth = opts.outlineWidth == null ? Math.max(2, Math.round(size * 0.17)) : opts.outlineWidth;
      ctx.strokeStyle = outline;
      ctx.strokeText(str, x, y);
    }
    const fill = opts.gradient || opts.color || '#f7f1ff';
    if (opts.glow) {
      ctx.save();
      ctx.shadowColor = opts.glow;
      ctx.shadowBlur = opts.glowBlur == null ? Math.round(size * 0.55) : opts.glowBlur;
      ctx.fillStyle = fill;
      ctx.fillText(str, x, y);
      ctx.fillStyle = fill;
      ctx.fillText(str, x, y);
      ctx.restore();
    }
    ctx.fillStyle = fill;
    ctx.fillText(str, x, y);
    const w = ctx.measureText(str).width;
    ctx.restore();
    return w;
  }

  /* ========================================================================
   *  基础绘制工具
   * ===================================================================== */
  function panelPath(ctx, x, y, w, h, cut) {
    const c = Math.min(cut == null ? 12 : cut, w * 0.5, h * 0.5);
    ctx.beginPath();
    ctx.moveTo(x + c, y);
    ctx.lineTo(x + w, y);
    ctx.lineTo(x + w, y + h - c);
    ctx.lineTo(x + w - c, y + h);
    ctx.lineTo(x, y + h);
    ctx.lineTo(x, y + c);
    ctx.closePath();
  }

  function drawPanel(ctx, x, y, w, h, opts) {
    opts = opts || {};
    const cut = opts.cut == null ? 12 : opts.cut;
    const accent = opts.accent || C.cyan;
    ctx.save();
    const baseA = ctx.globalAlpha;
    panelPath(ctx, x, y, w, h, cut);
    const grd = ctx.createLinearGradient(x, y, x, y + h);
    grd.addColorStop(0, opts.bg1 || 'rgba(16,8,32,0.88)');
    grd.addColorStop(0.55, opts.bg2 || 'rgba(11,6,24,0.84)');
    grd.addColorStop(1, opts.bg3 || 'rgba(6,3,14,0.9)');
    ctx.fillStyle = grd;
    ctx.fill();

    /* 内部扫描线 */
    ctx.save();
    panelPath(ctx, x, y, w, h, cut);
    ctx.clip();
    ctx.fillStyle = 'rgba(255,255,255,0.024)';
    for (let i = y + 2; i < y + h; i += 3) ctx.fillRect(x, i, w, 1);
    /* 左上角高光 */
    const hl = ctx.createLinearGradient(x, y, x + w * 0.6, y);
    hl.addColorStop(0, 'rgba(255,255,255,0.10)');
    hl.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = hl;
    ctx.fillRect(x, y, w * 0.6, 2);
    ctx.restore();

    /* 外描边 */
    panelPath(ctx, x + 0.5, y + 0.5, w - 1, h - 1, Math.max(2, cut - 1));
    ctx.lineWidth = opts.lineWidth == null ? 2 : opts.lineWidth;
    ctx.strokeStyle = accent;
    ctx.globalAlpha = baseA * (opts.borderAlpha == null ? 0.82 : opts.borderAlpha);
    ctx.stroke();
    ctx.globalAlpha = baseA;

    /* 顶部霓虹短条 */
    ctx.fillStyle = accent;
    ctx.globalAlpha = baseA * 0.95;
    ctx.fillRect(x + cut + 4, y, Math.min(w * 0.36, 96), 2);
    ctx.globalAlpha = baseA;

    /* 四角刻线 */
    if (opts.ticks !== false) {
      const t = Math.min(12, w * 0.12);
      ctx.strokeStyle = accent;
      ctx.globalAlpha = baseA * 0.55;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x + 3, y + t); ctx.lineTo(x + 3, y + 4); ctx.lineTo(x + 3 + t, y + 4);
      ctx.moveTo(x + w - 3, y + h - t); ctx.lineTo(x + w - 3, y + h - 4); ctx.lineTo(x + w - 3 - t, y + h - 4);
      ctx.stroke();
      ctx.globalAlpha = baseA;
    }
    ctx.restore();
  }

  function drawBar(ctx, x, y, w, h, ratio, opts) {
    opts = opts || {};
    ratio = clamp01(ratio);
    const trail = opts.trail == null ? ratio : clamp01(opts.trail);
    ctx.save();
    const baseA = ctx.globalAlpha;
    /* 底槽 */
    ctx.fillStyle = opts.bg || 'rgba(14,7,26,0.96)';
    ctx.fillRect(x, y, w, h);
    /* 白色延迟掉血层 */
    const tx = Math.round(w * ratio);
    const tw = Math.max(0, Math.round(w * trail) - tx);
    if (tw > 0) {
      ctx.fillStyle = opts.trailColor || 'rgba(255,255,255,0.72)';
      ctx.fillRect(x + tx, y, tw, h);
    }
    /* 主体 */
    const fw = Math.round(w * ratio);
    if (fw > 0) {
      const grd = ctx.createLinearGradient(0, y, 0, y + h);
      grd.addColorStop(0, opts.c1 || '#ffe98a');
      grd.addColorStop(0.45, opts.c2 || '#ff8a2a');
      grd.addColorStop(1, opts.c3 || '#ff3b5c');
      ctx.fillStyle = grd;
      ctx.fillRect(x, y, fw, h);
      /* 顶部高光 */
      ctx.fillStyle = 'rgba(255,255,255,0.28)';
      ctx.fillRect(x, y, fw, Math.max(1, Math.floor(h * 0.28)));
      /* 流动光带 */
      if (opts.shine && fw > 6) {
        const sx = x + ((opts.shinePhase || 0) * 90) % Math.max(1, fw);
        ctx.fillStyle = 'rgba(255,255,255,0.20)';
        ctx.fillRect(x + sx, y, Math.min(10, fw - sx), h);
      }
    }
    /* 分段刻度 */
    const seg = opts.segments | 0;
    if (seg > 1) {
      ctx.fillStyle = 'rgba(4,2,10,0.55)';
      for (let i = 1; i < seg; i++) ctx.fillRect(x + Math.round(w * i / seg), y, 1, h);
    }
    /* 边框 */
    ctx.strokeStyle = opts.border || 'rgba(4,2,10,0.9)';
    ctx.lineWidth = 2;
    ctx.strokeRect(x - 1, y - 1, w + 2, h + 2);
    if (opts.edge) {
      ctx.strokeStyle = opts.edge;
      ctx.globalAlpha = baseA * 0.7;
      ctx.lineWidth = 1;
      ctx.strokeRect(x - 0.5, y - 0.5, w + 1, h + 1);
      ctx.globalAlpha = baseA;
    }
    ctx.restore();
  }

  function neonLine(ctx, x1, y1, x2, y2, color, alpha, width) {
    ctx.save();
    const baseA = ctx.globalAlpha;
    ctx.globalCompositeOperation = 'lighter';
    ctx.strokeStyle = color;
    ctx.globalAlpha = baseA * (alpha == null ? 0.8 : alpha);
    ctx.lineWidth = width == null ? 2 : width;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.restore();
  }

  function glowDot(ctx, x, y, r, color, alpha) {
    ctx.save();
    const baseA = ctx.globalAlpha;
    ctx.globalCompositeOperation = 'lighter';
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, color);
    g.addColorStop(0.4, color);
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.globalAlpha = baseA * (alpha == null ? 0.7 : alpha);
    ctx.fillStyle = g;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
    ctx.restore();
  }

  function screenFrame(ctx, time, accent) {
    const m = 12;
    const len = 26;
    ctx.save();
    const baseA = ctx.globalAlpha;
    ctx.globalAlpha = baseA * 0.55;
    ctx.strokeStyle = accent || C.cyan;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(m, m + len); ctx.lineTo(m, m); ctx.lineTo(m + len, m);
    ctx.moveTo(VW - m, m + len); ctx.lineTo(VW - m, m); ctx.lineTo(VW - m - len, m);
    ctx.moveTo(m, VH - m - len); ctx.lineTo(m, VH - m); ctx.lineTo(m + len, VH - m);
    ctx.moveTo(VW - m, VH - m - len); ctx.lineTo(VW - m, VH - m); ctx.lineTo(VW - m - len, VH - m);
    ctx.stroke();
    ctx.globalAlpha = baseA * 0.4;
    ctx.strokeStyle = C.magenta;
    ctx.beginPath();
    ctx.moveTo(VW * 0.5 - 18, VH - 7); ctx.lineTo(VW * 0.5 + 18, VH - 7);
    ctx.stroke();
    ctx.restore();
  }

  /* ========================================================================
   *  角色头像（真实资源缺失时程序化霓虹剪影）
   * ===================================================================== */
  function silhouettePath(ctx, kind, s) {
    /* 以左上角为原点、s 为边长的头肩剪影 */
    ctx.beginPath();
    if (kind === 'boss') {
      /* 大衣肩部 */
      ctx.moveTo(-0.02 * s, 1.02 * s);
      ctx.lineTo(0.06 * s, 0.78 * s);
      ctx.quadraticCurveTo(0.18 * s, 0.68 * s, 0.34 * s, 0.70 * s);
      ctx.lineTo(0.66 * s, 0.70 * s);
      ctx.quadraticCurveTo(0.82 * s, 0.68 * s, 0.94 * s, 0.78 * s);
      ctx.lineTo(1.02 * s, 1.02 * s);
      ctx.closePath();
      /* 头 */
      ctx.moveTo(0.50 * s, 0.20 * s);
      ctx.ellipse(0.50 * s, 0.42 * s, 0.235 * s, 0.235 * s, 0, 0, Math.PI * 2);
      /* 鬼角 */
      ctx.moveTo(0.27 * s, 0.36 * s);
      ctx.lineTo(0.10 * s, 0.04 * s);
      ctx.lineTo(0.36 * s, 0.26 * s);
      ctx.closePath();
      ctx.moveTo(0.73 * s, 0.36 * s);
      ctx.lineTo(0.90 * s, 0.04 * s);
      ctx.lineTo(0.64 * s, 0.26 * s);
      ctx.closePath();
      /* 下颌 */
      ctx.moveTo(0.34 * s, 0.56 * s);
      ctx.lineTo(0.66 * s, 0.56 * s);
      ctx.lineTo(0.62 * s, 0.70 * s);
      ctx.lineTo(0.38 * s, 0.70 * s);
      ctx.closePath();
    } else if (kind === 'brute') {
      ctx.moveTo(-0.02 * s, 1.02 * s);
      ctx.lineTo(0.02 * s, 0.76 * s);
      ctx.quadraticCurveTo(0.16 * s, 0.66 * s, 0.32 * s, 0.68 * s);
      ctx.lineTo(0.68 * s, 0.68 * s);
      ctx.quadraticCurveTo(0.84 * s, 0.66 * s, 0.98 * s, 0.76 * s);
      ctx.lineTo(1.02 * s, 1.02 * s);
      ctx.closePath();
      ctx.moveTo(0.50 * s, 0.14 * s);
      ctx.ellipse(0.50 * s, 0.38 * s, 0.24 * s, 0.245 * s, 0, 0, Math.PI * 2);
      /* 络腮胡 */
      ctx.moveTo(0.28 * s, 0.44 * s);
      ctx.quadraticCurveTo(0.30 * s, 0.70 * s, 0.50 * s, 0.70 * s);
      ctx.quadraticCurveTo(0.70 * s, 0.70 * s, 0.72 * s, 0.44 * s);
      ctx.quadraticCurveTo(0.62 * s, 0.58 * s, 0.50 * s, 0.58 * s);
      ctx.quadraticCurveTo(0.38 * s, 0.58 * s, 0.28 * s, 0.44 * s);
      ctx.closePath();
    } else if (kind === 'punk') {
      ctx.moveTo(0.02 * s, 1.02 * s);
      ctx.lineTo(0.08 * s, 0.80 * s);
      ctx.quadraticCurveTo(0.22 * s, 0.71 * s, 0.36 * s, 0.72 * s);
      ctx.lineTo(0.64 * s, 0.72 * s);
      ctx.quadraticCurveTo(0.78 * s, 0.71 * s, 0.92 * s, 0.80 * s);
      ctx.lineTo(0.98 * s, 1.02 * s);
      ctx.closePath();
      ctx.moveTo(0.50 * s, 0.18 * s);
      ctx.ellipse(0.50 * s, 0.44 * s, 0.195 * s, 0.225 * s, 0, 0, Math.PI * 2);
      /* 莫西干 */
      for (let i = 0; i < 4; i++) {
        const bx = (0.36 + i * 0.09) * s;
        ctx.moveTo(bx, 0.30 * s);
        ctx.lineTo(bx + 0.03 * s, 0.03 * s);
        ctx.lineTo(bx + 0.08 * s, 0.30 * s);
        ctx.closePath();
      }
    } else {
      /* hero */
      ctx.moveTo(0.04 * s, 1.02 * s);
      ctx.lineTo(0.10 * s, 0.79 * s);
      ctx.quadraticCurveTo(0.22 * s, 0.70 * s, 0.35 * s, 0.71 * s);
      ctx.lineTo(0.65 * s, 0.71 * s);
      ctx.quadraticCurveTo(0.78 * s, 0.70 * s, 0.90 * s, 0.79 * s);
      ctx.lineTo(0.96 * s, 1.02 * s);
      ctx.closePath();
      ctx.moveTo(0.50 * s, 0.16 * s);
      ctx.ellipse(0.50 * s, 0.44 * s, 0.20 * s, 0.235 * s, 0, 0, Math.PI * 2);
      /* 刺猬头 */
      const spikes = [
        [0.30, 0.34, 0.20, 0.04, 0.42, 0.28],
        [0.40, 0.27, 0.38, 0.01, 0.52, 0.22],
        [0.52, 0.24, 0.55, 0.00, 0.63, 0.24],
        [0.62, 0.28, 0.72, 0.04, 0.72, 0.34],
        [0.24, 0.42, 0.10, 0.22, 0.28, 0.44]
      ];
      for (let i = 0; i < spikes.length; i++) {
        const sp = spikes[i];
        ctx.moveTo(sp[0] * s, sp[1] * s);
        ctx.lineTo(sp[2] * s, sp[3] * s);
        ctx.lineTo(sp[4] * s, sp[5] * s);
        ctx.closePath();
      }
    }
  }

  function drawSilhouette(ctx, charName, x, y, s) {
    const kind = charName === 'boss' ? 'boss' : (charName === 'brute' ? 'brute' : (charName === 'punk' ? 'punk' : 'hero'));
    const eyeCol = kind === 'boss' ? C.red : (kind === 'brute' ? C.orange : (kind === 'punk' ? C.yellow : C.cyan));
    const dark = '#130b20';
    ctx.save();
    ctx.translate(x, y);
    /* 霓虹轮廓光 */
    ctx.globalAlpha = 0.85;
    ctx.fillStyle = C.cyan;
    ctx.save(); ctx.translate(-0.035 * s, -0.012 * s); silhouettePath(ctx, kind, s); ctx.fill(); ctx.restore();
    ctx.fillStyle = C.magenta;
    ctx.save(); ctx.translate(0.035 * s, -0.012 * s); silhouettePath(ctx, kind, s); ctx.fill(); ctx.restore();
    /* 主体暗色 */
    ctx.globalAlpha = 1;
    ctx.fillStyle = dark;
    silhouettePath(ctx, kind, s);
    ctx.fill();
    /* 面部暗部 */
    ctx.fillStyle = 'rgba(62,34,80,0.55)';
    ctx.beginPath();
    ctx.ellipse(0.50 * s, 0.46 * s, 0.15 * s, 0.17 * s, 0, 0, Math.PI * 2);
    ctx.fill();
    /* 发光眼 */
    ctx.globalCompositeOperation = 'lighter';
    const eyeY = kind === 'boss' ? 0.405 : 0.425;
    const eW = kind === 'boss' ? 0.075 : 0.062;
    glowDot(ctx, 0.50 * s, eyeY * s, 0.20 * s, 'rgba(' + hexRgb(eyeCol) + ',0.55)', 0.8);
    ctx.fillStyle = eyeCol;
    if (kind === 'hero' || kind === 'brute') {
      /* 斜挑的怒目 */
      ctx.beginPath();
      ctx.moveTo(0.402 * s, eyeY * s);
      ctx.lineTo(0.402 * s + eW * s, eyeY * s - 0.012 * s);
      ctx.lineTo(0.402 * s + eW * s, eyeY * s + 0.008 * s);
      ctx.lineTo(0.402 * s, eyeY * s + 0.018 * s);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(0.598 * s - eW * s, eyeY * s - 0.012 * s);
      ctx.lineTo(0.598 * s, eyeY * s);
      ctx.lineTo(0.598 * s, eyeY * s + 0.018 * s);
      ctx.lineTo(0.598 * s - eW * s, eyeY * s + 0.008 * s);
      ctx.closePath();
      ctx.fill();
    } else {
      ctx.fillRect((0.415 - eW * 0.5) * s, eyeY * s, eW * s, 0.020 * s);
      ctx.fillRect((0.585 - eW * 0.5) * s, eyeY * s, eW * s, 0.020 * s);
    }
    if (kind === 'boss') {
      /* 面具竖向嘴缝 */
      ctx.fillStyle = 'rgba(255,59,92,0.55)';
      for (let i = 0; i < 3; i++) ctx.fillRect((0.42 + i * 0.06) * s, 0.57 * s, 0.012 * s, 0.09 * s);
    } else if (kind === 'punk') {
      ctx.strokeStyle = 'rgba(255,210,63,0.55)';
      ctx.lineWidth = Math.max(1, 0.008 * s);
      ctx.beginPath();
      ctx.moveTo(0.40 * s, 0.585 * s);
      ctx.quadraticCurveTo(0.50 * s, 0.63 * s, 0.61 * s, 0.575 * s);
      ctx.stroke();
    } else if (kind === 'hero') {
      /* 眉毛 */
      ctx.strokeStyle = 'rgba(61,243,255,0.65)';
      ctx.lineWidth = Math.max(1, 0.014 * s);
      ctx.beginPath();
      ctx.moveTo(0.395 * s, eyeY * s - 0.024 * s);
      ctx.lineTo(0.462 * s, eyeY * s - 0.040 * s);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(255,47,142,0.65)';
      ctx.beginPath();
      ctx.moveTo(0.605 * s, eyeY * s - 0.024 * s);
      ctx.lineTo(0.538 * s, eyeY * s - 0.040 * s);
      ctx.stroke();
      /* 嘴线 */
      ctx.strokeStyle = 'rgba(240,210,255,0.35)';
      ctx.lineWidth = Math.max(1, 0.009 * s);
      ctx.beginPath();
      ctx.moveTo(0.455 * s, 0.548 * s);
      ctx.lineTo(0.545 * s, 0.548 * s);
      ctx.stroke();
      /* 刀疤 */
      ctx.strokeStyle = 'rgba(255,47,142,0.6)';
      ctx.lineWidth = Math.max(1, 0.01 * s);
      ctx.beginPath();
      ctx.moveTo(0.585 * s, 0.47 * s);
      ctx.lineTo(0.625 * s, 0.53 * s);
      ctx.stroke();
    }
    ctx.restore();
  }

  function hexRgb(hex) {
    const s = String(hex || '#fff').replace('#', '');
    const h = s.length === 3 ? s.charAt(0) + s.charAt(0) + s.charAt(1) + s.charAt(1) + s.charAt(2) + s.charAt(2) : s;
    const r = parseInt(h.slice(0, 2), 16) || 255;
    const g = parseInt(h.slice(2, 4), 16) || 255;
    const b = parseInt(h.slice(4, 6), 16) || 255;
    return r + ',' + g + ',' + b;
  }

  function drawPortrait(ctx, charName, x, y, size, opts) {
    opts = opts || {};
    const s = Math.max(12, Math.round(size || 64));
    x = Math.round(x); y = Math.round(y);
    const img = (NF.assets && NF.assets.portrait) ? NF.assets.portrait(charName || 'hero') : null;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x, y, s, s);
    ctx.clip();
    /* 背景 */
    const bg = ctx.createLinearGradient(x, y, x, y + s);
    bg.addColorStop(0, 'rgba(44,22,72,0.95)');
    bg.addColorStop(0.6, 'rgba(22,12,44,0.95)');
    bg.addColorStop(1, 'rgba(8,4,18,0.98)');
    ctx.fillStyle = bg;
    ctx.fillRect(x, y, s, s);

    if (img && img.width) {
      const side = Math.min(img.width, img.height);
      const sx = (img.width - side) * 0.5;
      const sy = (img.height - side) * clamp01(opts.cropY == null ? 0.42 : opts.cropY);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(img, sx, sy, side, side, x, y, s, s);
    } else {
      drawSilhouette(ctx, charName || 'hero', x, y, s);
    }

    /* 扫描线 + 霓虹染色 */
    ctx.fillStyle = 'rgba(0,0,0,0.18)';
    for (let i = 2; i < s; i += 3) ctx.fillRect(x, y + i, s, 1);
    const tint = ctx.createLinearGradient(x, y, x + s, y + s);
    tint.addColorStop(0, 'rgba(61,243,255,0.14)');
    tint.addColorStop(0.48, 'rgba(0,0,0,0)');
    tint.addColorStop(1, 'rgba(255,47,142,0.16)');
    ctx.fillStyle = tint;
    ctx.fillRect(x, y, s, s);
    ctx.restore();
  }

  /* 头像 + 霓虹边框 */
  function portraitFrame(ctx, charName, x, y, size, opts) {
    opts = opts || {};
    const accent = opts.accent || C.cyan;
    const s = Math.max(12, Math.round(size || 64));
    ctx.save();
    drawPanel(ctx, x - 4, y - 4, s + 8, s + 8, {
      cut: 8, accent: accent, bg1: 'rgba(8,4,18,0.92)', bg2: 'rgba(6,3,14,0.92)', bg3: 'rgba(4,2,10,0.95)',
      borderAlpha: 0.9, lineWidth: 2, ticks: false
    });
    drawPortrait(ctx, charName, x, y, s, opts);
    /* 四角 */
    ctx.strokeStyle = accent;
    ctx.lineWidth = 2;
    ctx.globalAlpha = 0.95;
    const c = Math.max(4, s * 0.16);
    ctx.beginPath();
    ctx.moveTo(x, y); ctx.lineTo(x + c, y);
    ctx.moveTo(x, y); ctx.lineTo(x, y + c);
    ctx.moveTo(x + s, y); ctx.lineTo(x + s - c, y);
    ctx.moveTo(x + s, y); ctx.lineTo(x + s, y + c);
    ctx.moveTo(x, y + s); ctx.lineTo(x + c, y + s);
    ctx.moveTo(x, y + s); ctx.lineTo(x, y + s - c);
    ctx.moveTo(x + s, y + s); ctx.lineTo(x + s - c, y + s);
    ctx.moveTo(x + s, y + s); ctx.lineTo(x + s, y + s - c);
    ctx.stroke();
    ctx.restore();
  }

  /* ========================================================================
   *  游戏数据读取（全部安全兜底）
   * ===================================================================== */
  const qs = (function () {
    try { return new URLSearchParams(window.location.search); } catch (err) { return null; }
  })();
  const HUDTEST = qs ? (qs.get('hudtest') || '') : '';

  function splitName(name, cnDef, enDef) {
    const s = name == null ? '' : String(name);
    const cnMatch = s.match(/[\u4e00-\u9fa5]+/);
    const enMatch = s.match(/[A-Za-z][A-Za-z0-9 .'-]*/);
    return {
      cn: cnMatch ? cnMatch[0] : cnDef,
      en: (enMatch ? enMatch[0] : enDef).replace(/\s+/g, ' ').trim().toUpperCase()
    };
  }

  function readView(game) {
    game = game || {};
    const shot = cfg.SHOT || '';
    const demo = !!shot && !game.shotFrozen;

    const p = game.player || {};
    const maxHp = Math.max(1, num(p.maxHp, cfg.PLAYER_MAX_HP || 120));
    const hp = clamp(num(p.hp, maxHp), 0, maxHp);
    const maxSp = Math.max(1, num(p.maxSpecial, cfg.MAX_SPECIAL || 100));
    const sp = clamp(num(p.special, 0), 0, maxSp);

    const totalWaves = Math.max(1, Math.round(num(game.totalWaves,
      cfg.STAGE && cfg.STAGE.waves ? cfg.STAGE.waves.length : 4)));
    let wave = Math.round(num(game.waveDisplay, num(game.wave, 1)));
    if (!(wave >= 1)) wave = 1;
    wave = clamp(wave, 1, totalWaves);

    let score = Math.max(0, Math.round(num(game.score, 0)));
    let highScore = Math.max(0, Math.round(num(game.highScore, 0)));
    let maxCombo = Math.max(0, Math.round(num(game.maxCombo, 0)));
    let kills = Math.max(0, Math.round(num(game.kills, 0)));
    let combo = Math.max(0, Math.round(num(game.combo, 0)));
    let comboTimer = Math.max(0, num(game.comboTimer, 0));

    let boss = game.boss && typeof game.boss === 'object' ? game.boss : null;
    if (boss) {
      const bMax = Math.max(1, num(boss.maxHp, 420));
      const bHp = clamp(num(boss.hp, bMax), 0, bMax);
      boss = {
        raw: boss,
        name: boss.name,
        cn: splitName(boss.name, '铁面', 'IRON MASK').cn,
        en: splitName(boss.name, '铁面', 'IRON MASK').en,
        title: boss.title || '鬼面执行者',
        hp: bHp,
        maxHp: bMax,
        ratio: bHp / bMax,
        active: boss.active !== false,
        phase: num(boss.phase, bHp / bMax < 0.5 ? 2 : 1)
      };
    }

    /* 截图预览兜底（只在 URL 带 shot 且玩法模块未接管时启用） */
    if (demo) {
      if (shot === 'battle' && combo < 2) { combo = 7; comboTimer = 1.7; maxCombo = Math.max(maxCombo, 7); score = Math.max(score, 7200); }
      if (shot === 'combo' && combo < 2) { combo = 23; comboTimer = 1.65; maxCombo = Math.max(maxCombo, 23); score = Math.max(score, 14800); }
      if (shot === 'boss' && combo < 2) { combo = 4; comboTimer = 1.5; score = Math.max(score, 19800); }
      if (shot === 'victory' || shot === 'gameover') {
        if (score <= 0) score = shot === 'victory' ? 28640 : 12450;
        if (maxCombo <= 0) maxCombo = shot === 'victory' ? 31 : 17;
        if (kills <= 0) kills = shot === 'victory' ? 17 : 11;
      }
      if ((shot === 'boss' || shot === 'intro') && !boss) {
        boss = {
          raw: {}, name: '铁面 IRON MASK', cn: '铁面', en: 'IRON MASK', title: '鬼面执行者',
          hp: shot === 'intro' ? 420 : 302, maxHp: 420, ratio: shot === 'intro' ? 1 : 302 / 420,
          active: true, phase: shot === 'intro' ? 1 : 2
        };
      }
    }

    const high = Math.max(highScore, score);
    return {
      game, state: game.state || 'title', demo,
      hp, maxHp, sp, maxSp,
      hpRatio: hp / maxHp, spRatio: sp / maxSp,
      combo, comboTimer, maxCombo, score, highScore: high, kills, wave, totalWaves,
      boss, reason: game.gameoverReason || '',
      playerName: splitName(p.name, '凯', 'KAI'),
      banner: game.banner && typeof game.banner === 'object' ? game.banner : null,
      elapsed: num(game.time, 0)
    };
  }

  /* ========================================================================
   *  HUD 内部动画状态
   * ===================================================================== */
  const S = {
    lastTime: 0,
    time: 0,
    whiteHp: 1,
    whiteBoss: 1,
    lastCombo: -1,
    comboPop: 0,
    lastScore: -1,
    scorePop: 0,
    toasts: [],
    warned: false,
    frame: 0
  };

  /* ========================================================================
   *  标题画面
   * ===================================================================== */
  function drawProceduralLogo(ctx, cx, cy, time) {
    const flick = U.flicker(time, 2.3, 6.2);
    /* 背后放射光 */
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.translate(cx, cy);
    for (let i = 0; i < 16; i++) {
      const a = (i / 16) * Math.PI * 2 + time * 0.05;
      ctx.rotate(0);
      ctx.strokeStyle = i % 2 ? 'rgba(61,243,255,0.045)' : 'rgba(255,47,142,0.045)';
      ctx.lineWidth = 10;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * 150, Math.sin(a) * 150);
      ctx.lineTo(Math.cos(a) * 520, Math.sin(a) * 520);
      ctx.stroke();
    }
    ctx.restore();

    const titleY = cy + 6;
    /* 冷色/品红错位（霓虹管效果） */
    cnText(ctx, '霓虹拳魂', cx - 4, titleY + 2, { size: 80, align: 'center', color: C.cyan, outline: false, alpha: 0.55 * flick });
    cnText(ctx, '霓虹拳魂', cx + 4, titleY + 2, { size: 80, align: 'center', color: C.magenta, outline: false, alpha: 0.55 * flick });
    /* 主字：铬色渐变 + 深色描边 + 发光 */
    const grad = ctx.createLinearGradient(0, titleY - 66, 0, titleY + 8);
    grad.addColorStop(0, '#fffdf2');
    grad.addColorStop(0.35, '#ffe98a');
    grad.addColorStop(0.62, '#ffd23f');
    grad.addColorStop(0.82, '#ff8a2a');
    grad.addColorStop(1, '#ff2f8e');
    cnText(ctx, '霓虹拳魂', cx, titleY, {
      size: 80, align: 'center', gradient: grad,
      outline: true, outlineColor: 'rgba(16,6,26,0.98)', outlineWidth: 9,
      glow: 'rgba(255,47,142,0.95)', glowBlur: 26
    });
    /* 内高光 */
    cnText(ctx, '霓虹拳魂', cx, titleY - 2, {
      size: 80, align: 'center', color: 'rgba(255,255,255,0.16)', outline: false, alpha: 0.8
    });

    /* 英文副标题 */
    const subY = titleY + 44;
    pixelText(ctx, 'NEON FIST SOUL', cx - 3, subY, {
      scale: 4, spacing: 2, align: 'center', color: C.magenta, outline: false, alpha: 0.55
    });
    pixelText(ctx, 'NEON FIST SOUL', cx + 3, subY, {
      scale: 4, spacing: 2, align: 'center', color: C.cyan, outline: false, alpha: 0.55
    });
    pixelText(ctx, 'NEON FIST SOUL', cx, subY, {
      scale: 4, spacing: 2, align: 'center', color: '#f7f1ff', glow: 'rgba(61,243,255,0.9)', glowBlur: 12
    });
    /* 装饰横线 + 菱形 */
    const lineY = subY + 16;
    neonLine(ctx, cx - 250, lineY, cx - 24, lineY, C.cyan, 0.55, 2);
    neonLine(ctx, cx + 24, lineY, cx + 250, lineY, C.magenta, 0.55, 2);
    ctx.save();
    ctx.fillStyle = C.yellow;
    ctx.beginPath();
    ctx.moveTo(cx, lineY - 5); ctx.lineTo(cx + 6, lineY); ctx.lineTo(cx, lineY + 5); ctx.lineTo(cx - 6, lineY);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    /* 中文章节小字 */
    cnText(ctx, '霓 虹 后 巷 · 第 一 区', cx, lineY + 20, {
      size: 13, align: 'center', color: 'rgba(210,190,255,0.9)', outlineColor: 'rgba(6,3,12,0.92)'
    });
  }

  function drawPosterCard(ctx, charName, x, y, size, opts) {
    opts = opts || {};
    const accent = opts.accent || C.cyan;
    ctx.save();
    const baseA = ctx.globalAlpha;
    /* 背面光晕 */
    glowDot(ctx, x + size * 0.5, y + size * 0.5, size * 0.85, accent, 0.10);
    /* 倾斜装饰条 */
    ctx.globalAlpha = baseA * 0.5;
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x - 8, y + size + 22);
    ctx.lineTo(x + size + 12, y + 14);
    ctx.stroke();
    ctx.globalAlpha = baseA;

    portraitFrame(ctx, charName, x, y, size, { accent: accent, cropY: 0.36 });

    /* 名牌 */
    const nx = x - 4;
    const ny = y + size + 8;
    drawPanel(ctx, nx, ny, size + 8, 24, {
      cut: 6, accent: accent, bg1: 'rgba(12,6,24,0.9)', bg2: 'rgba(8,4,16,0.9)', bg3: 'rgba(5,2,12,0.92)',
      borderAlpha: 0.7, lineWidth: 1, ticks: false
    });
    cnText(ctx, opts.nameCn, nx + 8, ny + 17, { size: 13, color: '#f7f1ff' });
    pixelText(ctx, opts.nameEn, nx + size + 2, ny + 17, {
      scale: 1, align: 'right', color: accent, alpha: 0.9
    });
    ctx.restore();
  }

  function keyCap(ctx, x, y, label, accent) {
    const w = label.length > 2 ? 22 + (label.length - 1) * 8 : 22;
    const h = 20;
    drawPanel(ctx, x, y, w, h, {
      cut: 4, accent: accent || C.cyan, bg1: 'rgba(24,12,44,0.95)', bg2: 'rgba(14,7,28,0.95)', bg3: 'rgba(8,4,16,0.96)',
      borderAlpha: 0.9, lineWidth: 1, ticks: false
    });
    pixelText(ctx, label, x + w * 0.5, y + h * 0.5 + 1, {
      scale: 1, align: 'center', baseline: 'middle', color: accent || C.cyan, shadow: false
    });
    return w;
  }

  function drawControls(ctx, time, game) {
    const touch = NF.input && NF.input.touchMode;
    /* 触屏模式：底部两侧有 DOM 虚拟摇杆/按钮，面板改成中间窄条 */
    const x = touch ? 150 : 100;
    const w = touch ? VW - 300 : VW - 200;
    const y = 466, h = touch ? 46 : 56;
    drawPanel(ctx, x, y, w, h, {
      cut: 10, accent: C.cyan, bg1: 'rgba(12,6,26,0.82)', bg2: 'rgba(8,4,18,0.8)', bg3: 'rgba(5,2,12,0.86)',
      borderAlpha: 0.55, lineWidth: 1
    });
    if (touch) {
      cnText(ctx, '虚拟摇杆移动 · 右侧按钮 攻击 / 重击 / 跳跃 / 必杀', VW * 0.5, y + 20, {
        size: 13, align: 'center', color: '#e8dcff'
      });
      cnText(ctx, '横屏游玩体验更佳', VW * 0.5, y + 38, {
        size: 11, align: 'center', color: 'rgba(170,150,210,0.85)', outline: false
      });
      return;
    }
    const caps = [
      ['WASD', '移动'], ['J', '攻击'], ['K', '重击'], ['L', '跳跃'], ['U', '必杀']
    ];
    /* 先量宽度 */
    let total = 0;
    const sizes = [];
    for (let i = 0; i < caps.length; i++) {
      const cw = caps[i][0].length > 2 ? 22 + (caps[i][0].length - 1) * 8 : 22;
      const labelW = caps[i][1].length * 14 + 4;
      sizes.push({ cw: cw, labelW: labelW });
      total += cw + 8 + labelW + (i < caps.length - 1 ? 26 : 0);
    }
    let cx = VW * 0.5 - total * 0.5;
    const cy = y + 12;
    for (let i = 0; i < caps.length; i++) {
      ctx.save();
      const kc = keyCap(ctx, cx, cy, caps[i][0], i === 0 ? C.cyan : (i === 4 ? C.magenta : C.yellow));
      cnText(ctx, caps[i][1], cx + kc + 8, cy + 15, { size: 13, color: '#e8dcff' });
      cx += kc + 8 + sizes[i].labelW + (i < caps.length - 1 ? 26 : 0);
      ctx.restore();
    }
    cnText(ctx, '霓虹后巷 · 击败「铁面 IRON MASK」', VW * 0.5, y + 46, {
      size: 11, align: 'center', color: 'rgba(170,150,210,0.9)', outline: false
    });
  }

  function drawStartPrompt(ctx, time) {
    const touch = NF.input && NF.input.touchMode;
    const blink = 0.62 + 0.38 * Math.sin(time * 4.6);
    const y = 420;
    ctx.save();
    /* 呼吸光晕 */
    glowDot(ctx, VW * 0.5, y - 8, 150, 'rgba(255,47,142,0.5)', 0.05 + 0.05 * blink);
    const mainTxt = touch ? '点击屏幕 开始游戏' : '点击 / 按 ENTER 开始';
    cnText(ctx, mainTxt, VW * 0.5, y, {
      size: 24, align: 'center', color: '#ffffff',
      outlineColor: 'rgba(10,4,18,0.96)', outlineWidth: 5,
      glow: 'rgba(255,47,142,0.95)', glowBlur: 18, alpha: blink
    });
    pixelText(ctx, touch ? 'TAP  TO  START' : 'PRESS  ENTER  TO  START', VW * 0.5, y + 22, {
      scale: 1, spacing: 1, align: 'center', color: C.cyan, alpha: 0.55 + 0.35 * blink
    });
    /* 两侧三角箭头 */
    const arrowOn = Math.sin(time * 4.6) > -0.2;
    if (arrowOn) {
      ctx.fillStyle = C.yellow;
      const ax = VW * 0.5 - 190;
      ctx.beginPath();
      ctx.moveTo(ax, y - 18); ctx.lineTo(ax - 12, y - 10); ctx.lineTo(ax, y - 2);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(VW - ax, y - 18); ctx.lineTo(VW - ax + 12, y - 10); ctx.lineTo(VW - ax, y - 2);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function drawTitle(ctx, game, time) {
    const v = readView(game);
    const touch = NF.input && NF.input.touchMode;

    /* 压暗背景，突出海报排版 */
    const g = ctx.createLinearGradient(0, 0, 0, VH);
    g.addColorStop(0, 'rgba(5,2,12,0.72)');
    g.addColorStop(0.3, 'rgba(5,2,12,0.30)');
    g.addColorStop(0.55, 'rgba(5,2,12,0.24)');
    g.addColorStop(1, 'rgba(4,1,10,0.82)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, VW, VH);

    /* 顶部 / 底部海报条 */
    ctx.fillStyle = 'rgba(3,1,8,0.55)';
    ctx.fillRect(0, 0, VW, 6);
    ctx.fillRect(0, VH - 6, VW, 6);

    /* Logo 区径向压暗，让标题像招牌一样从背景里“打光”出来 */
    const logoShade = ctx.createRadialGradient(VW * 0.5, 132, 50, VW * 0.5, 132, 540);
    logoShade.addColorStop(0, 'rgba(4,2,10,0.66)');
    logoShade.addColorStop(0.62, 'rgba(4,2,10,0.34)');
    logoShade.addColorStop(1, 'rgba(4,2,10,0)');
    ctx.fillStyle = logoShade;
    ctx.fillRect(0, 0, VW, 300);

    /* Logo */
    const logo = NF.assets && NF.assets.ui ? NF.assets.ui('logo') : null;
    if (HUDTEST === 'diag') {
      const lines = [
        'LOADED ' + (NF.assets && NF.assets.loaded ? 1 : 0),
        'IMGS ' + (NF.assets && NF.assets.images ? Object.keys(NF.assets.images).length : -1),
        'UIKEY ' + String(NF.world && NF.world.ui ? NF.world.ui.logo : 'none'),
        'LOGO ' + (logo ? logo.width + 'x' + logo.height : 'null')
      ];
      for (let i = 0; i < lines.length; i++) {
        pixelText(ctx, lines[i], 300, 340 + i * 16, { scale: 1, color: '#00ff88', shadow: false });
      }
    }
    if (logo && logo.width) {
      const maxW = 680;
      const sc = Math.min(maxW / logo.width, 208 / logo.height);
      const lw = Math.round(logo.width * sc);
      const lh = Math.round(logo.height * sc);
      const lx = Math.round((VW - lw) * 0.5);
      const ly = 30;
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      glowDot(ctx, lx + lw * 0.24, ly + lh * 0.5, 150, 'rgba(61,243,255,0.5)', 0.10 + 0.03 * Math.sin(time * 2));
      glowDot(ctx, lx + lw * 0.76, ly + lh * 0.5, 150, 'rgba(255,47,142,0.5)', 0.10 + 0.03 * Math.cos(time * 2));
      ctx.restore();
      ctx.save();
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(logo, lx, ly, lw, lh);
      ctx.restore();
      /* 倒影 */
      ctx.save();
      ctx.beginPath();
      ctx.rect(lx, ly + lh, lw, 40);
      ctx.clip();
      ctx.globalAlpha = 0.13;
      ctx.imageSmoothingEnabled = true;
      ctx.translate(0, (ly + lh) * 2);
      ctx.scale(1, -1);
      ctx.drawImage(logo, lx, ly, lw, lh);
      ctx.restore();
      cnText(ctx, '霓虹后巷 · 第 一 区', VW * 0.5, ly + lh + 34, {
        size: 13, align: 'center', color: 'rgba(210,190,255,0.92)', outlineColor: 'rgba(6,3,12,0.92)'
      });
    } else {
      drawProceduralLogo(ctx, VW * 0.5, 128, time);
    }

    /* 主角 / Boss 头像海报（触屏模式缩小，避开 DOM 虚拟按键） */
    drawPosterCard(ctx, 'hero', 40, touch ? 236 : 246, touch ? 144 : 168, {
      nameCn: '凯 KAI', nameEn: 'HERO', accent: C.cyan
    });
    drawPosterCard(ctx, 'boss', touch ? 762 : 746, touch ? 226 : 232, touch ? 148 : 184, {
      nameCn: '铁面', nameEn: 'IRON MASK', accent: C.magenta
    });

    /* 最高分（让开右上角 DOM 系统按钮） */
    const hiX = VW - 88;
    pixelText(ctx, 'HI-SCORE', hiX, 52, { scale: 1, align: 'right', color: C.cyan, alpha: 0.85 });
    pixelText(ctx, U.fmtScore(v.highScore), hiX, 76, {
      scale: 2, align: 'right', color: C.yellow, glow: 'rgba(255,210,63,0.8)', glowBlur: 6
    });
    /* 左上 1P */
    pixelText(ctx, '1P', 20, 34, { scale: 2, color: C.red });
    pixelText(ctx, 'PLAYER', 20, 56, { scale: 1, color: 'rgba(240,220,255,0.7)' });
    /* 左下 / 右下小字（触屏模式右下被虚拟按键占用，省略） */
    pixelText(ctx, '©1994 NEON WORKS', 18, 534, { scale: 1, color: 'rgba(150,130,190,0.7)', shadow: false });
    if (!touch) {
      pixelText(ctx, '1 CREDIT', VW - 18, 534, {
        scale: 1, align: 'right', color: 'rgba(150,130,190,0.7)', shadow: false
      });
    }

    drawStartPrompt(ctx, time);
    drawControls(ctx, time, game);
    screenFrame(ctx, time, C.cyan);
    if (HUDTEST === 'toast') {
      toast('连击 10 达成！「霓虹爆裂」已就绪', { dur: 6 });
    }
  }

  /* ========================================================================
   *  战斗 HUD
   * ===================================================================== */
  function drawPlayerPanel(ctx, v, time, dt) {
    const X = 14, Y = 12, W = 342, H = 104;
    drawPanel(ctx, X, Y, W, H, {
      cut: 12, accent: C.cyan, borderAlpha: 0.75
    });

    /* 头像 */
    const pSize = 62;
    portraitFrame(ctx, 'hero', X + 12, Y + 12, pSize, { accent: C.cyan });

    /* 名字 */
    ctx.save();
    ctx.fillStyle = C.cyan;
    ctx.globalAlpha = 0.9;
    ctx.fillRect(X + 78, Y + 16, 3, 22);
    ctx.restore();
    cnText(ctx, v.playerName.cn, X + 88, Y + 34, {
      size: 20, color: '#ffffff', outlineColor: 'rgba(8,4,16,0.95)', outlineWidth: 3
    });
    pixelText(ctx, v.playerName.en, X + 88 + 26, Y + 33, {
      scale: 2, color: C.cyan, alpha: 0.95
    });

    /* 血条 */
    const hbX = X + 86, hbY = Y + 42, hbW = W - 86 - 14, hbH = 15;
    const lowHp = v.hpRatio <= 0.3;
    const pulse = lowHp ? 0.7 + 0.3 * Math.sin(time * 10) : 1;
    drawBar(ctx, hbX, hbY, hbW, hbH, v.hpRatio, {
      trail: S.whiteHp,
      segments: 12,
      c1: lowHp ? '#ff9aa8' : '#fff6c9',
      c2: lowHp ? '#ff3b5c' : '#ff8a2a',
      c3: lowHp ? '#a1122f' : '#ff3b5c',
      edge: lowHp ? 'rgba(255,59,92,' + pulse.toFixed(2) + ')' : null,
      shine: true,
      shinePhase: time * 0.7
    });
    if (lowHp) {
      /* 低血量警示 */
      ctx.save();
      ctx.globalAlpha = 0.35 + 0.35 * Math.sin(time * 10);
      pixelText(ctx, 'DANGER', hbX + hbW - 2, hbY - 3, {
        scale: 1, align: 'right', color: C.red, shadow: false
      });
      ctx.restore();
    }

    /* 气槽 */
    const spY = Y + 64;
    drawBar(ctx, hbX, spY, hbW, 9, v.spRatio, {
      trail: v.spRatio,
      segments: 10,
      c1: '#d8fdff',
      c2: C.cyan,
      c3: C.purple,
      edge: 'rgba(61,243,255,0.5)'
    });
    const ready = v.spRatio >= 0.999;
    if (ready) {
      const blink = 0.55 + 0.45 * Math.sin(time * 8.5);
      pixelText(ctx, '必杀', hbX + 2, spY + 22, {
        scale: 1, color: C.yellow, alpha: blink, shadow: false
      });
      cnText(ctx, 'READY', hbX + 30, spY + 24, {
        size: 12, color: C.yellow, alpha: blink, outline: false, glow: 'rgba(255,210,63,0.9)', glowBlur: 8
      });
    } else {
      pixelText(ctx, 'SP', hbX + 2, spY + 22, { scale: 1, color: 'rgba(180,160,220,0.75)', shadow: false });
      pixelText(ctx, Math.round(v.sp) + '/' + Math.round(v.maxSp), hbX + hbW, spY + 22, {
        scale: 1, align: 'right', color: 'rgba(180,160,220,0.75)', shadow: false
      });
    }
  }

  function drawScorePanel(ctx, v, time) {
    /* 右上角让出 DOM 系统按钮（♪ ❚❚ ⛶）的空间，面板右边界 884 */
    const X = 542, Y = 12, W = 342, H = 104;
    drawPanel(ctx, X, Y, W, H, { cut: 12, accent: C.magenta, borderAlpha: 0.72 });

    pixelText(ctx, 'SCORE', X + 16, Y + 22, { scale: 1, color: 'rgba(61,243,255,0.85)', shadow: false });
    pixelText(ctx, U.fmtScore(v.score), X + 16, Y + 50, {
      scale: 3, color: '#ffffff', glow: 'rgba(61,243,255,0.55)', glowBlur: 8
    });

    pixelText(ctx, 'HI-SCORE', X + W - 16, Y + 22, {
      scale: 1, align: 'right', color: 'rgba(255,210,63,0.85)', shadow: false
    });
    pixelText(ctx, U.fmtScore(v.highScore), X + W - 16, Y + 46, {
      scale: 2, align: 'right', color: C.yellow
    });

    /* WAVE */
    pixelText(ctx, 'WAVE', X + 16, Y + 86, { scale: 2, color: 'rgba(240,224,255,0.9)' });
    pixelText(ctx, v.wave + '/' + v.totalWaves, X + 74, Y + 86, {
      scale: 2, color: C.magenta, glow: 'rgba(255,47,142,0.6)', glowBlur: 6
    });
    /* 波次进度点 */
    const px0 = X + 152;
    for (let i = 0; i < v.totalWaves; i++) {
      const on = i < v.wave;
      const bx = px0 + i * 16;
      ctx.save();
      ctx.fillStyle = on ? C.cyan : 'rgba(120,100,160,0.35)';
      ctx.beginPath();
      ctx.moveTo(bx, Y + 82); ctx.lineTo(bx + 5, Y + 87); ctx.lineTo(bx, Y + 92); ctx.lineTo(bx - 5, Y + 87);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
    /* 关卡名 */
    const stage = cfg.STAGE && cfg.STAGE.name ? cfg.STAGE.name : '霓虹后巷';
    cnText(ctx, stage, X + W - 16, Y + 92, {
      size: 12, align: 'right', color: 'rgba(190,170,230,0.8)', outline: false
    });
  }

  function drawCombo(ctx, v, time, dt) {
    if (v.combo < 2 || v.comboTimer <= 0) return;
    const comboMax = 2.2;
    const timerRatio = clamp01(v.comboTimer / comboMax);
    const tier = v.combo >= 20 ? 2 : (v.combo >= 10 ? 1 : 0);
    const col = tier === 2 ? C.magenta : (tier === 1 ? C.yellow : C.cyan);
    const X = 44;
    const Y = 158;
    const pop = S.comboPop;
    const sc = 1 + pop * 0.22 + 0.012 * Math.sin(time * 6);
    const numStr = String(v.combo);
    const numW = measurePixel(numStr, 6, 1);

    /* 斜切背景条 */
    ctx.save();
    const baseA = ctx.globalAlpha;
    ctx.globalAlpha = baseA * 0.85;
    const bgW = Math.max(186, numW + 148);
    ctx.fillStyle = 'rgba(8,4,18,0.7)';
    ctx.beginPath();
    ctx.moveTo(X - 18, Y - 16);
    ctx.lineTo(X + bgW, Y - 16);
    ctx.lineTo(X + bgW - 26, Y + 82);
    ctx.lineTo(X - 18, Y + 82);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = col;
    ctx.globalAlpha = baseA * 0.55;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();

    /* 数字（弹跳缩放，渐变必须在局部坐标系里创建） */
    ctx.save();
    ctx.translate(X, Y);
    ctx.scale(sc, sc);
    const grad = ctx.createLinearGradient(0, 0, 0, 42);
    grad.addColorStop(0, '#ffffff');
    grad.addColorStop(0.5, col);
    grad.addColorStop(1, tier === 2 ? '#ff9acb' : (tier === 1 ? '#ffe98a' : '#b5fbff'));
    pixelText(ctx, numStr, 0, 0, {
      scale: 6, spacing: 0, baseline: 'top', gradient: grad, outline: true,
      outlineColor: 'rgba(10,4,18,0.95)', glow: col, glowBlur: 14
    });
    ctx.restore();

    ctx.save();
    ctx.translate(X + numW * sc + 10, Y + 18);
    ctx.scale(sc, sc);
    pixelText(ctx, 'HITS', 0, 0, {
      scale: 3, baseline: 'top', color: col, outline: true, outlineColor: 'rgba(10,4,18,0.9)'
    });
    ctx.restore();
    const rank = tier === 2 ? 'INSANE' : (tier === 1 ? 'SUPER' : 'GOOD');
    /* 评级带「RANK」前缀，避免 scale=1 的小字被误读成数字 */
    pixelText(ctx, 'RANK ' + rank, X + bgW - 18, Y - 8, {
      scale: 1, align: 'right', color: 'rgba(240,224,255,0.8)', shadow: false
    });
    /* COMBO 小标 */
    pixelText(ctx, 'COMBO', X, Y - 10, { scale: 1, color: 'rgba(61,243,255,0.8)', shadow: false });

    /* 连击计时条 */
    const tbY = Y + 54;
    const tbW = 176;
    ctx.save();
    ctx.fillStyle = 'rgba(10,5,20,0.8)';
    ctx.fillRect(X, tbY, tbW, 5);
    const grd = ctx.createLinearGradient(X, 0, X + tbW, 0);
    grd.addColorStop(0, col);
    grd.addColorStop(1, C.magenta);
    ctx.fillStyle = grd;
    ctx.fillRect(X, tbY, Math.round(tbW * timerRatio), 5);
    ctx.strokeStyle = 'rgba(4,2,10,0.9)';
    ctx.lineWidth = 1;
    ctx.strokeRect(X - 0.5, tbY - 0.5, tbW + 1, 6);
    ctx.restore();
  }

  function drawBossBar(ctx, v, time, dt) {
    const b = v.boss;
    if (!b || !b.active) return;
    if (b.hp <= 0 && b.ratio <= 0) return;
    const W = 626;
    const X = (VW - W) * 0.5;
    const Y = 468;
    const H = 58;
    drawPanel(ctx, X, Y, W, H, {
      cut: 10, accent: b.phase >= 2 ? C.red : C.magenta, bg1: 'rgba(26,6,18,0.88)',
      bg2: 'rgba(14,4,14,0.86)', bg3: 'rgba(7,2,10,0.92)', borderAlpha: 0.85
    });
    /* 小头像 */
    portraitFrame(ctx, 'boss', X + 9, Y + 8, 42, { accent: b.phase >= 2 ? C.red : C.magenta });

    /* 名称 */
    const nameX = X + 62;
    cnText(ctx, b.cn, nameX, Y + 22, {
      size: 16, color: '#ffffff', glow: 'rgba(255,59,92,0.5)', glowBlur: 6
    });
    pixelText(ctx, b.en, nameX + 38, Y + 21, { scale: 1, color: 'rgba(255,190,210,0.9)' });
    pixelText(ctx, 'BOSS', X + W - 12, Y + 20, {
      scale: 1, align: 'right', color: b.phase >= 2 ? C.red : C.magenta, shadow: false
    });
    if (b.phase >= 2) {
      const bl = 0.5 + 0.5 * Math.sin(time * 7);
      cnText(ctx, '暴走', X + W - 44, Y + 22, {
        size: 11, color: C.red, alpha: 0.6 + 0.4 * bl, outline: false
      });
    }

    /* 血条 */
    drawBar(ctx, nameX, Y + 30, W - 62 - 18, 15, b.ratio, {
      trail: S.whiteBoss,
      segments: 20,
      c1: b.phase >= 2 ? '#ffb3bd' : '#ffd9e6',
      c2: b.phase >= 2 ? '#ff3b5c' : '#ff2f8e',
      c3: '#7a0f35',
      edge: 'rgba(255,47,142,0.55)',
      shine: true,
      shinePhase: time * 0.5
    });
    /* 50% 阶段线 */
    ctx.save();
    ctx.fillStyle = 'rgba(255,210,63,0.8)';
    const halfX = Math.round(nameX + (W - 62 - 18) * 0.5);
    ctx.fillRect(halfX, Y + 28, 2, 19);
    ctx.restore();
    /* 血量数值 */
    pixelText(ctx, Math.round(Math.max(0, b.hp)) + '/' + Math.round(b.maxHp), X + W - 12, Y + 56, {
      scale: 1, align: 'right', color: 'rgba(255,175,195,0.75)', shadow: false
    });
  }

  function drawBattleHud(ctx, game, time, dt) {
    const v = readView(game);
    drawPlayerPanel(ctx, v, time, dt);
    drawScorePanel(ctx, v, time);
    drawCombo(ctx, v, time, dt);
    drawBossBar(ctx, v, time, dt);
    screenFrame(ctx, time, C.cyan);
    return v;
  }

  /* ========================================================================
   *  波次横幅 & Boss 登场卡
   * ===================================================================== */
  function bannerColors(label) {
    const bright = (hex, t) => {
      const s = String(hex || '#3df3ff').replace('#', '');
      const r = parseInt(s.slice(0, 2), 16) || 61;
      const g = parseInt(s.slice(2, 4), 16) || 243;
      const b = parseInt(s.slice(4, 6), 16) || 255;
      const mix = (v) => Math.round(v + (255 - v) * t);
      return 'rgb(' + mix(r) + ',' + mix(g) + ',' + mix(b) + ')';
    };
    const s = String(label || '').toUpperCase();
    let cols;
    if (s.indexOf('BOSS') >= 0) cols = { a: C.red, b: C.magenta };
    else if (s.indexOf('CLEAR') >= 0) cols = { a: C.lime, b: C.cyan };
    else cols = { a: C.cyan, b: C.magenta };
    cols.light = bright(cols.b, 0.42);
    return cols;
  }

  function drawWaveBanner(ctx, game, time) {
    const b = game.banner;
    if (!b || typeof b !== 'object') return;
    const max = Math.max(0.4, num(b.max, 2.2));
    const timer = clamp(num(b.timer, 0), 0, max);
    if (timer <= 0.001) return;
    const p = 1 - timer / max;
    const inK = U.easeOutCubic(clamp01(p / 0.16));
    const outK = clamp01((1 - p) / 0.22);
    const a = Math.min(inK, outK);
    if (a <= 0.01) return;

    const label = String(b.label || 'WAVE');
    const sub = String(b.sub || '');
    const cols = bannerColors(label);
    const slide = (1 - inK) * -80;
    const cy = 190;
    const bandTop = 140;
    const bandH = 104;

    ctx.save();
    ctx.globalAlpha = a * 0.94;
    /* 横带：上下渐隐 + 斜切边 */
    const grd = ctx.createLinearGradient(0, bandTop, 0, bandTop + bandH);
    grd.addColorStop(0, 'rgba(5,2,12,0)');
    grd.addColorStop(0.16, 'rgba(7,3,16,0.9)');
    grd.addColorStop(0.34, 'rgba(9,4,20,0.97)');
    grd.addColorStop(0.72, 'rgba(9,4,20,0.97)');
    grd.addColorStop(0.88, 'rgba(7,3,16,0.9)');
    grd.addColorStop(1, 'rgba(5,2,12,0)');
    ctx.fillStyle = grd;
    ctx.fillRect(0, bandTop, VW, bandH);
    /* 内部扫描线 */
    ctx.globalAlpha = a * 0.12;
    ctx.fillStyle = '#ffffff';
    for (let y = bandTop + 8; y < bandTop + bandH - 8; y += 3) ctx.fillRect(0, y, VW, 1);
    ctx.restore();

    ctx.save();
    ctx.globalAlpha = a;
    /* 斜切左右装饰块 */
    ctx.globalAlpha = a * 0.85;
    ctx.fillStyle = cols.b;
    for (let s = 0; s < 2; s++) {
      const dir = s === 0 ? -1 : 1;
      const bx = VW * 0.5 + dir * (VW * 0.5 - 10) + slide;
      ctx.beginPath();
      ctx.moveTo(bx, bandTop);
      ctx.lineTo(bx + dir * 18, bandTop);
      ctx.lineTo(bx + dir * 18 - dir * 26, bandTop + bandH);
      ctx.lineTo(bx - dir * 8, bandTop + bandH);
      ctx.closePath();
      ctx.fill();
    }
    ctx.globalAlpha = a;

    /* 上下霓虹线 */
    const lineY1 = bandTop + 10;
    const lineY2 = bandTop + bandH - 10;
    neonLine(ctx, VW * 0.5 - 380 + slide, lineY1, VW * 0.5 + 340 + slide, lineY1, cols.b, 0.85, 2);
    neonLine(ctx, VW * 0.5 - 340 + slide, lineY2, VW * 0.5 + 380 + slide, lineY2, cols.a, 0.85, 2);
    /* 两侧箭标 */
    ctx.fillStyle = cols.b;
    for (let i = 0; i < 3; i++) {
      const ax = VW * 0.5 - 300 + slide - i * 26;
      ctx.fillRect(ax, cy - 4, 16, 8);
      const bx = VW * 0.5 + 300 + slide + i * 26;
      ctx.fillRect(bx, cy - 4, 16, 8);
    }

    /* 主标题 */
    const grad = ctx.createLinearGradient(0, cy - 40, 0, cy + 14);
    grad.addColorStop(0, '#ffffff');
    grad.addColorStop(0.45, cols.a);
    grad.addColorStop(1, cols.light);
    if (/^[\x20-\x7E]+$/.test(label)) {
      pixelText(ctx, label, VW * 0.5 + slide, cy + 12, {
        scale: 6, spacing: 1, align: 'center',
        gradient: grad, outline: true, outlineColor: 'rgba(6,2,12,0.97)',
        glow: cols.b, glowBlur: 18
      });
    } else {
      cnText(ctx, label, VW * 0.5 + slide, cy + 20, {
        size: 42, align: 'center', gradient: grad,
        outlineColor: 'rgba(6,2,12,0.97)', glow: cols.b, glowBlur: 16
      });
    }
    if (sub) {
      /* 副标题小背板，避免和背景霓虹招牌混在一起 */
      ctx.save();
      ctx.globalAlpha = a * 0.72;
      ctx.fillStyle = 'rgba(4,2,10,0.78)';
      const subW = Math.min(380, sub.length * 16 + 40);
      ctx.fillRect(VW * 0.5 - subW * 0.5 + slide, cy + 20, subW, 22);
      ctx.restore();
      cnText(ctx, sub, VW * 0.5 + slide, cy + 38, {
        size: 14, align: 'center', color: 'rgba(240,228,255,0.96)', outlineColor: 'rgba(8,4,16,0.92)'
      });
    }
    ctx.restore();
  }

  /* Boss 登场卡状态探测（兼容玩法模块可能使用的多种字段） */
  function getBossIntro(game, time) {
    game = game || {};
    const banner = game.banner;
    if (banner && typeof banner === 'object') {
      const desc = String(banner.label || '').toUpperCase();
      const isBoss = banner.boss === true || desc.indexOf('BOSS') >= 0;
      if (isBoss) {
        const max = Math.max(0.6, num(banner.max, 2.2));
        const timer = clamp(num(banner.timer, 0), 0, max);
        if (timer > 0.001) return { p: clamp01(1 - timer / max), max: max };
      }
    }
    const bi = game.bossIntro;
    if (typeof bi === 'number' && bi > 0) {
      return { p: clamp01(1 - bi / 2.2), max: 2.2 };
    }
    if (bi && typeof bi === 'object') {
      const max = Math.max(0.6, num(bi.max, bi.dur, 2.2));
      const timer = clamp(num(bi.timer, bi.t, 0), 0, max);
      if (timer > 0.001) return { p: clamp01(1 - timer / max), max: max };
    }
    const it = game.introTimer;
    if (typeof it === 'number' && it > 0) return { p: clamp01(1 - it / 2.2), max: 2.2 };
    /* 截图专用：?shot=intro 且玩法模块未提供时循环播放，便于验证排版 */
    if (cfg.SHOT === 'intro' && !game.shotFrozen) {
      const cyc = 3.0;
      return { p: (time % cyc) / cyc, max: cyc };
    }
    return null;
  }

  function drawBossIntro(ctx, game, time, info) {
    const p = clamp01(info.p);
    const inK = U.easeOutCubic(clamp01(p / 0.14));
    const outK = clamp01((1 - p) / 0.14);
    const a = Math.min(inK, outK);
    if (a <= 0.01) return;
    const v = readView(game);
    const boss = v.boss || { cn: '铁面', en: 'IRON MASK', title: '鬼面执行者' };

    /* 暗场 */
    ctx.save();
    ctx.globalAlpha = 0.9 * a;
    const g = ctx.createLinearGradient(0, 0, VW, VH);
    g.addColorStop(0, 'rgba(22,2,10,0.97)');
    g.addColorStop(0.5, 'rgba(5,2,9,0.98)');
    g.addColorStop(1, 'rgba(20,2,16,0.97)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, VW, VH);
    ctx.restore();

    ctx.save();
    ctx.globalAlpha = a;
    /* 背景斜条纹 */
    ctx.save();
    ctx.globalAlpha = a * 0.12;
    ctx.fillStyle = C.magenta;
    for (let i = -1; i < 7; i++) {
      const bx = i * 190 - 60 + p * 120;
      ctx.beginPath();
      ctx.moveTo(bx, VH);
      ctx.lineTo(bx + 90, VH);
      ctx.lineTo(bx + 260, 0);
      ctx.lineTo(bx + 170, 0);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();

    /* 入场斜切光带 */
    const sweep = U.easeOutCubic(clamp01(p / 0.22));
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = a * (0.85 * (1 - clamp01((p - 0.12) / 0.2)));
    const swGrad = ctx.createLinearGradient(0, 0, VW, 0);
    swGrad.addColorStop(0, 'rgba(61,243,255,0)');
    swGrad.addColorStop(0.5, 'rgba(255,255,255,0.85)');
    swGrad.addColorStop(1, 'rgba(255,47,142,0)');
    ctx.fillStyle = swGrad;
    const swx = -300 + sweep * (VW + 600);
    ctx.beginPath();
    ctx.moveTo(swx, VH);
    ctx.lineTo(swx + 130, VH);
    ctx.lineTo(swx + 330, 0);
    ctx.lineTo(swx + 200, 0);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    /* Boss 头像 */
    const pw = 214;
    const px = 88 + (1 - inK) * -70;
    const py = 118;
    glowDot(ctx, px + pw * 0.5, py + pw * 0.5, pw * 1.05, 'rgba(255,47,142,0.8)', 0.22 * a);
    /* 头像框 */
    ctx.save();
    ctx.globalAlpha = a;
    drawPanel(ctx, px - 8, py - 8, pw + 16, pw + 16, {
      cut: 14, accent: C.magenta, bg1: 'rgba(30,4,18,0.95)', bg2: 'rgba(16,3,12,0.95)', bg3: 'rgba(8,2,8,0.96)',
      borderAlpha: 1, lineWidth: 2
    });
    drawPortrait(ctx, 'boss', px, py, pw, { cropY: 0.28 });
    /* 框角 */
    ctx.strokeStyle = C.red;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(px - 8, py + 24); ctx.lineTo(px - 8, py - 8); ctx.lineTo(px + 30, py - 8);
    ctx.moveTo(px + pw + 8, py + pw - 24); ctx.lineTo(px + pw + 8, py + pw + 8); ctx.lineTo(px + pw - 30, py + pw + 8);
    ctx.stroke();
    ctx.restore();

    /* 右侧文字 */
    const tx = 366 + (1 - inK) * 80;
    const wobble = Math.sin(time * 20) * 1.4;
    /* WARNING */
    ctx.save();
    ctx.globalAlpha = a * (0.55 + 0.45 * Math.sin(time * 9));
    pixelText(ctx, 'WARNING', tx, 132, {
      scale: 2, color: C.red, glow: 'rgba(255,59,92,0.9)', glowBlur: 10
    });
    ctx.restore();
    /* BOSS 大字 */
    const bgrad = ctx.createLinearGradient(0, 150, 0, 214);
    bgrad.addColorStop(0, '#ffffff');
    bgrad.addColorStop(0.45, C.yellow);
    bgrad.addColorStop(1, C.orange);
    pixelText(ctx, 'BOSS', tx + wobble, 204, {
      scale: 6, gradient: bgrad, outline: true, outlineColor: 'rgba(16,2,8,0.96)',
      glow: 'rgba(255,138,42,0.9)', glowBlur: 18
    });
    /* 中文名 */
    cnText(ctx, boss.cn, tx, 264, {
      size: 46, color: '#ffffff',
      outlineColor: 'rgba(16,2,8,0.96)', outlineWidth: 8,
      glow: 'rgba(255,47,142,0.95)', glowBlur: 20
    });
    /* 英文名 */
    pixelText(ctx, boss.en, tx + 4, 298, {
      scale: 3, color: C.cyan, glow: 'rgba(61,243,255,0.9)', glowBlur: 12
    });
    /* 称号 */
    cnText(ctx, boss.title || '鬼面执行者', tx + 4, 330, {
      size: 16, color: 'rgba(255,190,215,0.95)', outlineColor: 'rgba(10,2,8,0.9)'
    });
    /* 霓虹分隔线 */
    neonLine(ctx, tx, 344, tx + 380, 344, C.magenta, a * 0.8, 2);
    neonLine(ctx, tx, 348, tx + 260, 348, C.cyan, a * 0.5, 1);
    /* 提示 */
    cnText(ctx, '「霓虹后巷」最终 BOSS 出现', tx + 4, 372, {
      size: 12, color: 'rgba(190,170,225,0.85)', outline: false
    });

    ctx.restore();
    neonLine(ctx, 40, VH - 24, VW - 40, VH - 24, C.magenta, a * 0.35, 1);
    screenFrame(ctx, time, C.magenta);
  }

  /* ========================================================================
   *  暂停 / 失败 / 胜利
   * ===================================================================== */
  function drawPause(ctx, game, time) {
    ctx.save();
    ctx.fillStyle = 'rgba(4,2,10,0.74)';
    ctx.fillRect(0, 0, VW, VH);
    /* 扫描光带 */
    const sweepY = (time * 120) % (VH + 120) - 60;
    ctx.globalCompositeOperation = 'lighter';
    const sg = ctx.createLinearGradient(0, sweepY - 40, 0, sweepY + 40);
    sg.addColorStop(0, 'rgba(61,243,255,0)');
    sg.addColorStop(0.5, 'rgba(61,243,255,0.06)');
    sg.addColorStop(1, 'rgba(61,243,255,0)');
    ctx.fillStyle = sg;
    ctx.fillRect(0, sweepY - 40, VW, 80);
    ctx.restore();

    const W = 470, H = 268;
    const X = (VW - W) * 0.5, Y = (VH - H) * 0.5 - 6;
    drawPanel(ctx, X, Y, W, H, { cut: 18, accent: C.cyan, borderAlpha: 0.9 });
    glowDot(ctx, VW * 0.5, Y + 70, 180, 'rgba(61,243,255,0.6)', 0.10);

    cnText(ctx, '暂停', VW * 0.5, Y + 82, {
      size: 46, align: 'center', color: '#ffffff', glow: 'rgba(61,243,255,0.9)', glowBlur: 18
    });
    pixelText(ctx, 'PAUSED', VW * 0.5, Y + 132, {
      scale: 3, spacing: 2, align: 'center', color: C.cyan, glow: 'rgba(61,243,255,0.8)', glowBlur: 10
    });
    neonLine(ctx, X + 60, Y + 148, X + W - 60, Y + 148, C.magenta, 0.7, 2);

    const touch = NF.input && NF.input.touchMode;
    const blink = 0.7 + 0.3 * Math.sin(time * 5);
    if (touch) {
      cnText(ctx, '点击右上角 ❚❚ 按钮继续游戏', VW * 0.5, Y + 186, {
        size: 16, align: 'center', color: '#f0e6ff'
      });
    } else {
      cnText(ctx, '按 ENTER / P 继续游戏', VW * 0.5, Y + 186, {
        size: 16, align: 'center', color: '#f0e6ff', alpha: blink
      });
    }
    /* 重开提示：输入系统支持 restart 动作时显示按键，否则提示刷新页面，避免给出无效按键 */
    const restartSupported = !!(NF.input && NF.input.down &&
      Object.prototype.hasOwnProperty.call(NF.input.down, 'restart'));
    cnText(ctx, restartSupported ? '按 R 重新开始' : '重开：刷新页面', VW * 0.5, Y + 216, {
      size: 13, align: 'center', color: 'rgba(190,170,225,0.9)', outline: false
    });
    pixelText(ctx, '- GAME PAUSED -', VW * 0.5, Y + 246, {
      scale: 1, align: 'center', color: 'rgba(160,140,200,0.8)', shadow: false
    });
    screenFrame(ctx, time, C.cyan);
  }

  function drawStatsPanel(ctx, X, Y, W, rows, time, accent) {
    const rowH = 40;
    const H = rows.length * rowH + 18;
    drawPanel(ctx, X, Y, W, H, { cut: 12, accent: accent || C.cyan, borderAlpha: 0.8 });
    for (let i = 0; i < rows.length; i++) {
      const ry = Y + 14 + i * rowH;
      const row = rows[i];
      cnText(ctx, row[0], X + 22, ry + 26, { size: 14, color: 'rgba(220,205,245,0.92)' });
      if (row[2]) {
        pixelText(ctx, row[1], X + W - 22, ry + 28, {
          scale: 3, align: 'right', color: row[2], glow: row[2], glowBlur: 6
        });
      } else {
        pixelText(ctx, row[1], X + W - 22, ry + 28, {
          scale: 3, align: 'right', color: '#ffffff'
        });
      }
      if (i < rows.length - 1) {
        ctx.save();
        ctx.globalAlpha = 0.25;
        ctx.fillStyle = row[2] || accent || C.cyan;
        ctx.fillRect(X + 20, ry + rowH - 2, W - 40, 1);
        ctx.restore();
      }
    }
    return H;
  }

  function drawGameover(ctx, game, time) {
    const v = readView(game);
    /* 红色暗场 */
    ctx.save();
    ctx.globalAlpha = 0.9;
    const rg = ctx.createRadialGradient(VW * 0.5, VH * 0.38, 60, VW * 0.5, VH * 0.5, 700);
    rg.addColorStop(0, 'rgba(40,3,14,0.86)');
    rg.addColorStop(0.55, 'rgba(12,2,8,0.92)');
    rg.addColorStop(1, 'rgba(3,1,6,0.97)');
    ctx.fillStyle = rg;
    ctx.fillRect(0, 0, VW, VH);
    ctx.restore();
    /* 红色扫描线 */
    ctx.save();
    ctx.globalAlpha = 0.10;
    ctx.fillStyle = C.red;
    for (let y = 0; y < VH; y += 4) ctx.fillRect(0, y, VW, 1);
    ctx.restore();
    /* K.O. 区域压暗，避免背景霓虹招牌干扰主信息 */
    const band = ctx.createLinearGradient(0, 30, 0, 300);
    band.addColorStop(0, 'rgba(6,1,8,0)');
    band.addColorStop(0.35, 'rgba(6,1,8,0.6)');
    band.addColorStop(0.75, 'rgba(6,1,8,0.6)');
    band.addColorStop(1, 'rgba(6,1,8,0)');
    ctx.fillStyle = band;
    ctx.fillRect(0, 30, VW, 270);

    /* K.O.（像素大字：青/品红错位 + 红色渐变，街机感更强） */
    const koY = 148;
    const flick = 0.85 + 0.15 * Math.sin(time * 13);
    const kg = ctx.createLinearGradient(0, koY - 84, 0, koY);
    kg.addColorStop(0, '#fff6f6');
    kg.addColorStop(0.42, '#ffb0bb');
    kg.addColorStop(0.74, C.red);
    kg.addColorStop(1, '#7a0f2a');
    ctx.save();
    ctx.globalAlpha = flick;
    pixelText(ctx, 'K.O.', VW * 0.5 - 6, koY, {
      scale: 12, spacing: 1, align: 'center', color: C.cyan, alpha: 0.5, shadow: false
    });
    pixelText(ctx, 'K.O.', VW * 0.5 + 6, koY, {
      scale: 12, spacing: 1, align: 'center', color: C.magenta, alpha: 0.5, shadow: false
    });
    pixelText(ctx, 'K.O.', VW * 0.5, koY, {
      scale: 12, spacing: 1, align: 'center', gradient: kg,
      outline: true, outlineColor: 'rgba(12,2,6,0.97)',
      glow: 'rgba(255,59,92,0.95)', glowBlur: 26
    });
    ctx.restore();
    cnText(ctx, '你倒下了', VW * 0.5, koY + 44, {
      size: 24, align: 'center', color: '#ffffff', outlineColor: 'rgba(10,2,8,0.95)', outlineWidth: 5
    });
    if (v.reason) {
      cnText(ctx, v.reason, VW * 0.5, koY + 68, {
        size: 13, align: 'center', color: 'rgba(255,190,200,0.9)', outline: false
      });
    }
    neonLine(ctx, VW * 0.5 - 200, koY + 86, VW * 0.5 + 200, koY + 86, C.red, 0.65, 2);

    /* 结算 */
    const rows = [
      ['分数 SCORE', U.fmtScore(v.score), C.yellow],
      ['最高连击 MAX COMBO', padCombo(v.maxCombo), C.cyan],
      ['击杀 K.O.', U.pad(v.kills, 2), C.magenta]
    ];
    const W = 430;
    const X = (VW - W) * 0.5;
    const SY = 250;
    drawStatsPanel(ctx, X, SY, W, rows, time, C.red);

    /* 最高分 / 新纪录 */
    const record = v.score > 0 && v.score >= v.highScore;
    cnText(ctx, (record ? 'NEW RECORD  ' : 'HI-SCORE  ') + U.fmtScore(v.highScore), VW * 0.5, SY + 160, {
      size: 14, align: 'center',
      color: record ? C.yellow : 'rgba(210,190,240,0.9)',
      alpha: record ? (0.7 + 0.3 * Math.sin(time * 8)) : 1,
      outlineColor: 'rgba(8,2,8,0.9)'
    });

    const blink = 0.6 + 0.4 * Math.sin(time * 5.2);
    cnText(ctx, '按 ENTER / 点击屏幕 重新开始', VW * 0.5, 500, {
      size: 16, align: 'center', color: '#ffffff',
      outlineColor: 'rgba(10,2,8,0.95)', alpha: blink
    });
    screenFrame(ctx, time, C.red);
  }

  function padCombo(n) {
    return U.pad(n, 2) + ' HITS';
  }

  function drawVictory(ctx, game, time) {
    const v = readView(game);
    /* 霓虹渐变暗场 */
    ctx.save();
    const vg = ctx.createLinearGradient(0, 0, 0, VH);
    vg.addColorStop(0, 'rgba(6,2,20,0.86)');
    vg.addColorStop(0.45, 'rgba(18,4,34,0.78)');
    vg.addColorStop(1, 'rgba(4,1,12,0.94)');
    ctx.fillStyle = vg;
    ctx.fillRect(0, 0, VW, VH);
    /* 放射光线 */
    ctx.globalCompositeOperation = 'lighter';
    ctx.save();
    ctx.translate(VW * 0.5, 150);
    for (let i = 0; i < 22; i++) {
      const a = (i / 22) * Math.PI * 2 + time * 0.12;
      const grad = ctx.createLinearGradient(0, 0, Math.cos(a) * 460, Math.sin(a) * 460);
      grad.addColorStop(0, i % 2 ? 'rgba(61,243,255,0.16)' : 'rgba(255,47,142,0.16)');
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.strokeStyle = grad;
      ctx.lineWidth = 16;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(Math.cos(a) * 520, Math.sin(a) * 520);
      ctx.stroke();
    }
    ctx.restore();
    ctx.restore();

    /* STAGE CLEAR */
    const titleY = 138 + Math.sin(time * 1.6) * 3;
    cnText(ctx, 'STAGE CLEAR', VW * 0.5 - 5, titleY, {
      size: 62, align: 'center', color: C.cyan, outline: false, alpha: 0.5
    });
    cnText(ctx, 'STAGE CLEAR', VW * 0.5 + 5, titleY, {
      size: 62, align: 'center', color: C.magenta, outline: false, alpha: 0.5
    });
    const cg = ctx.createLinearGradient(0, titleY - 56, 0, titleY + 8);
    cg.addColorStop(0, '#fffdf2');
    cg.addColorStop(0.4, C.yellow);
    cg.addColorStop(0.75, C.orange);
    cg.addColorStop(1, '#ff8ac4');
    pixelText(ctx, 'STAGE CLEAR', VW * 0.5, titleY + 4, {
      scale: 7, spacing: 1, align: 'center', gradient: cg,
      outline: true, outlineColor: 'rgba(10,2,16,0.97)',
      glow: 'rgba(255,210,63,0.9)', glowBlur: 26
    });
    cnText(ctx, '霓 虹 后 巷 已 清 空', VW * 0.5, 196, {
      size: 24, align: 'center', color: '#ffffff',
      outlineColor: 'rgba(10,2,16,0.95)', outlineWidth: 5,
      glow: 'rgba(255,47,142,0.6)', glowBlur: 10
    });
    /* 装饰线 */
    neonLine(ctx, VW * 0.5 - 240, 212, VW * 0.5 + 240, 212, C.cyan, 0.75, 2);
    ctx.save();
    ctx.fillStyle = C.yellow;
    ctx.beginPath();
    ctx.moveTo(VW * 0.5, 206); ctx.lineTo(VW * 0.5 + 7, 212); ctx.lineTo(VW * 0.5, 218); ctx.lineTo(VW * 0.5 - 7, 212);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    /* 结算 */
    const rows = [
      ['分数 SCORE', U.fmtScore(v.score), C.yellow],
      ['最高连击 MAX COMBO', padCombo(v.maxCombo), C.cyan],
      ['击杀 K.O.', U.pad(v.kills, 2), C.magenta]
    ];
    const W = 430;
    const X = (VW - W) * 0.5;
    const SY = 238;
    drawStatsPanel(ctx, X, SY, W, rows, time, C.cyan);

    const record = v.score > 0 && v.score >= v.highScore;
    cnText(ctx, (record ? 'NEW RECORD  ' : 'HI-SCORE  ') + U.fmtScore(v.highScore), VW * 0.5, SY + 160, {
      size: 14, align: 'center',
      color: record ? C.yellow : 'rgba(210,190,240,0.9)',
      alpha: record ? (0.7 + 0.3 * Math.sin(time * 8)) : 1,
      outlineColor: 'rgba(8,2,16,0.9)'
    });

    const blink = 0.6 + 0.4 * Math.sin(time * 5.2);
    cnText(ctx, '按 ENTER / 点击屏幕 再玩一次', VW * 0.5, 500, {
      size: 16, align: 'center', color: '#ffffff',
      outlineColor: 'rgba(8,2,16,0.95)', alpha: blink
    });
    screenFrame(ctx, time, C.yellow);
  }

  /* ========================================================================
   *  Toast
   * ===================================================================== */
  function toast(text, opts) {
    opts = opts || {};
    S.toasts.push({
      text: String(text == null ? '' : text),
      t: 0,
      dur: Math.max(0.5, num(opts.dur, 2.4)),
      color: opts.color || null
    });
    if (S.toasts.length > 3) S.toasts.shift();
  }

  function drawToasts(ctx, dt) {
    if (!S.toasts.length) return;
    for (let i = S.toasts.length - 1; i >= 0; i--) {
      S.toasts[i].t += dt;
      if (S.toasts[i].t >= S.toasts[i].dur) S.toasts.splice(i, 1);
    }
    for (let i = 0; i < S.toasts.length; i++) {
      const t = S.toasts[i];
      const fade = clamp01(Math.min(1, t.t / 0.18) * Math.min(1, (t.dur - t.t) / 0.3));
      if (fade <= 0.02) continue;
      const y = 120 + i * 34;
      const text = t.text;
      const isAscii = /^[\x20-\x7E]+$/.test(text);
      ctx.save();
      ctx.globalAlpha = clamp01(fade);
      /* 背板 */
      const w = isAscii ? measurePixel(text, 2, 1) + 40 : Math.min(560, text.length * 15 + 44);
      const x = (VW - w) * 0.5;
      drawPanel(ctx, x, y - 18, w, 30, {
        cut: 6, accent: t.color || C.cyan, bg1: 'rgba(10,5,22,0.9)',
        bg2: 'rgba(8,4,18,0.88)', bg3: 'rgba(5,2,12,0.9)', borderAlpha: 0.75, lineWidth: 1, ticks: false
      });
      if (isAscii) {
        pixelText(ctx, text, VW * 0.5, y + 3, {
          scale: 2, align: 'center', color: t.color || '#f7f1ff'
        });
      } else {
        cnText(ctx, text, VW * 0.5, y + 3, {
          size: 14, align: 'center', color: t.color || '#f7f1ff', outlineColor: 'rgba(8,4,16,0.9)'
        });
      }
      ctx.restore();
    }
  }

  /* ========================================================================
   *  每帧更新 & 分发
   * ===================================================================== */
  function updateState(dt, game, time) {
    const v = readView(game);
    /* 血条白色延迟层：首帧给一小段“刚掉血”残留，随后快速追上真实血量 */
    if (S.whiteHp < 0) S.whiteHp = Math.min(1, v.hpRatio + 0.16);
    if (v.hpRatio > S.whiteHp) S.whiteHp = v.hpRatio;
    else if (v.hpRatio < S.whiteHp) S.whiteHp = U.damp(S.whiteHp, v.hpRatio, 3.2, Math.max(dt, 0.001));

    if (v.boss) {
      if (S.whiteBoss < 0) S.whiteBoss = Math.min(1, v.boss.ratio + 0.16);
      if (v.boss.ratio > S.whiteBoss) S.whiteBoss = v.boss.ratio;
      else if (v.boss.ratio < S.whiteBoss) S.whiteBoss = U.damp(S.whiteBoss, v.boss.ratio, 2.6, Math.max(dt, 0.001));
    } else {
      S.whiteBoss = -1;
    }

    /* 连击弹跳 */
    if (v.combo !== S.lastCombo) {
      if (v.combo > S.lastCombo && v.combo >= 2) S.comboPop = 1;
      S.lastCombo = v.combo;
    }
    S.comboPop = Math.max(0, S.comboPop - dt * 5.5);
    return v;
  }

  function drawAll(ctx, game, time) {
    game = game || NF.game || {};
    time = num(time, 0);
    if (!S.lastTime) { S.lastTime = time > 0 ? -1 : 0; }
    let dt = 0;
    if (S.lastTime >= 0) dt = clamp(time - S.lastTime, 0, 0.06);
    S.lastTime = time > 0 ? time : 0;
    S.time = time;

    const state = (game && game.state) || 'title';
    updateState(dt, game, time);

    if (state === 'title') {
      drawTitle(ctx, game, time);
      drawToasts(ctx, dt);
      return;
    }

    /* Boss 登场卡 / 结算画面期间隐藏战斗 HUD，保证标题与结算信息干净可读 */
    const intro = getBossIntro(game, time);
    const hideHud = state === 'gameover' || state === 'victory' || !!intro;

    if (!hideHud) {
      drawBattleHud(ctx, game, time, dt);
      drawWaveBanner(ctx, game, time);
    }

    if (state === 'gameover') drawGameover(ctx, game, time);
    else if (state === 'victory') drawVictory(ctx, game, time);
    else if (state === 'paused') drawPause(ctx, game, time);

    if (intro && state !== 'gameover' && state !== 'victory') {
      drawBossIntro(ctx, game, time, intro);
    }
    /* 仅开发自检：?hudtest=banner|pause 用于截图验证横幅/暂停排版 */
    if (HUDTEST === 'banner' && state === 'playing') {
      drawWaveBanner(ctx, { banner: { label: 'WAVE 3', sub: '4 名敌人', timer: 1.5, max: 2.2 } }, time);
    }
    if (HUDTEST === 'pause' && state === 'playing') {
      drawPause(ctx, game, time);
    }
    drawToasts(ctx, dt);
  }

  /* ========================================================================
   *  对外 API
   * ===================================================================== */
  NF.hud = {
    init() {
      S.lastTime = 0;
      S.time = 0;
      S.whiteHp = -1;
      S.whiteBoss = -1;
      S.lastCombo = -1;
      S.comboPop = 0;
      S.lastScore = -1;
      S.toasts.length = 0;
      S.warned = false;
    },

    draw(ctx, game, time) {
      if (!ctx) return;
      ctx.save();
      ctx.imageSmoothingEnabled = false;
      try {
        drawAll(ctx, game, time);
      } catch (err) {
        if (!S.warned) {
          S.warned = true;
          if (window.console && console.warn) console.warn('[NEON][hud] 绘制异常（已兜底）:', err);
        }
      }
      ctx.restore();
    },

    toast(text, opts) { toast(text, opts); },

    pixelText(ctx, text, x, y, opts) { return pixelText(ctx, text, x, y, opts); },

    cnText(ctx, text, x, y, opts) { return cnText(ctx, text, x, y, opts); },

    measurePixel(text, scale, spacing) { return measurePixel(text, scale, spacing); },

    drawPortrait(ctx, charName, x, y, size, opts) { drawPortrait(ctx, charName, x, y, size, opts); },

    drawPanel(ctx, x, y, w, h, opts) { drawPanel(ctx, x, y, w, h, opts); },

    /* 供调试/截图脚本确认 HUD 内部状态 */
    debug() {
      return { whiteHp: S.whiteHp, whiteBoss: S.whiteBoss, comboPop: S.comboPop, toasts: S.toasts.length };
    }
  };

  /* 默认初始化一次，保证不依赖 game.init 时序 */
  NF.hud.init();
})();
