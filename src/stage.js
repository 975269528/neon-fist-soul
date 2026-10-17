/* 霓虹拳魂 NEON FIST SOUL — 视差舞台背景 */
window.NF = window.NF || {};

NF.stage = {
  time: 0,

  _layerDef(name, defaults) {
    const defs = { far: { factor: 0.12, y: 0, tile: true }, mid: { factor: 0.45, y: 0 }, near: { factor: 1.0, y: 0 }, fg: { factor: 1.12, y: 0 } };
    const base = Object.assign({}, defs[name] || {}, defaults || {});
    const layers = (NF.world && NF.world.layers) || {};
    return Object.assign(base, layers[name] || {});
  },

  drawBack(ctx, camX, time) {
    this.time = time || 0;
    const cfg = NF.config;
    const far = this._layerDef('far');
    const mid = this._layerDef('mid');
    const near = this._layerDef('near');

    /* 兜底天空（任何图层缺失时都不会出现空白） */
    this._drawFallbackSky(ctx, camX, time);

    this._drawLayer(ctx, far, camX, () => this._drawFallbackFar(ctx, camX));
    this._drawLayer(ctx, mid, camX, () => this._drawFallbackMid(ctx, camX));
    this._drawLayer(ctx, near, camX, () => this._drawFallbackNear(ctx, camX));
  },

  drawForeground(ctx, camX, time) {
    const fg = this._layerDef('fg');
    if (!fg.file) return;
    const img = NF.assets.get(fg.file);
    if (!img) return;
    ctx.save();
    if (fg.alpha != null) ctx.globalAlpha *= fg.alpha;
    const factor = fg.factor == null ? 1.12 : fg.factor;
    const x = Math.round(camX * (1 - factor));
    const y = Math.round(fg.y || 0);
    if (fg.tile) {
      const start = this._tileStart(x, img.width, camX);
      for (let dx = start; dx < camX + NF.config.VIEW_W + img.width; dx += img.width) {
        ctx.drawImage(img, Math.round(dx), y);
      }
    } else {
      ctx.drawImage(img, x, y);
    }
    ctx.restore();
  },

  _tileStart(x, width, camX) {
    let start = x % width;
    if (start > 0) start -= width;
    while (start > camX) start -= width;
    return start;
  },

  _drawLayer(ctx, def, camX, fallback) {
    const img = def.file ? NF.assets.get(def.file) : null;
    if (!img) { if (fallback) fallback(); return; }
    const factor = def.factor == null ? 1 : def.factor;
    const x = Math.round(camX * (1 - factor));
    const y = Math.round(def.y || 0);
    ctx.save();
    if (def.alpha != null) ctx.globalAlpha *= def.alpha;
    if (def.tile) {
      const start = this._tileStart(x, img.width, camX);
      for (let dx = start; dx < camX + NF.config.VIEW_W + img.width; dx += img.width) {
        ctx.drawImage(img, Math.round(dx), y);
      }
    } else {
      ctx.drawImage(img, x, y);
    }
    ctx.restore();
  },

  /* ---------------- 占位背景（美术资源就绪前保证可玩可截图） ---------------- */
  _drawFallbackSky(ctx, camX, time) {
    const cfg = NF.config;
    const view = { x: camX, y: 0, w: cfg.VIEW_W, h: cfg.VIEW_H };
    const g = ctx.createLinearGradient(0, 0, 0, cfg.VIEW_H);
    g.addColorStop(0, '#080516');
    g.addColorStop(0.42, '#1a0d33');
    g.addColorStop(0.7, '#35104a');
    g.addColorStop(1, '#0b0716');
    ctx.fillStyle = g;
    ctx.fillRect(view.x, 0, view.w, view.h);

    /* 月亮 + 霓虹光晕 */
    ctx.save();
    ctx.globalAlpha = 0.85;
    ctx.fillStyle = '#ffd9f0';
    ctx.beginPath();
    ctx.arc(view.x + 740, 88, 34, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = '#ff2f8e';
    ctx.beginPath();
    ctx.arc(view.x + 740, 88, 82, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  },

  _drawFallbackFar(ctx, camX) {
    const viewX = camX;
    ctx.save();
    const base = camX * 0.12;
    ctx.fillStyle = '#120a24';
    for (let i = 0; i < 26; i++) {
      const bx = ((i * 173 - base) % 1500) + viewX - 260;
      const bw = 40 + ((i * 53) % 80);
      const bh = 70 + ((i * 97) % 130);
      ctx.fillRect(Math.round(bx), 350 - bh, bw, bh);
      ctx.fillStyle = 'rgba(70,200,230,0.10)';
      for (let wy = 0; wy < 4; wy++) {
        for (let wx = 0; wx < 3; wx++) {
          if ((i + wx * 3 + wy * 7) % 5 === 0) ctx.fillRect(Math.round(bx + 8 + wx * 14), 352 - bh + 12 + wy * 18, 4, 6);
        }
      }
      ctx.fillStyle = '#120a24';
    }
    ctx.restore();
  },

  _drawFallbackMid(ctx, camX) {
    const base = camX * 0.45;
    ctx.save();
    for (let i = 0; i < 18; i++) {
      const bx = ((i * 241 - base) % 1900) + camX - 320;
      const bw = 90 + ((i * 67) % 120);
      const bh = 150 + ((i * 113) % 170);
      ctx.fillStyle = i % 3 === 0 ? '#160c2a' : '#1b0f2e';
      ctx.fillRect(Math.round(bx), 500 - bh, bw, bh);
      /* 窗户 */
      for (let wy = 0; wy < 6; wy++) {
        for (let wx = 0; wx < 4; wx++) {
          const lit = (i * 13 + wx * 7 + wy * 3) % 11;
          if (lit < 4) {
            ctx.fillStyle = lit < 2 ? 'rgba(255,210,63,0.5)' : 'rgba(61,243,255,0.34)';
            ctx.fillRect(Math.round(bx + 12 + wx * 18), 500 - bh + 18 + wy * 22, 8, 9);
          }
        }
      }
      /* 霓虹灯牌 */
      if (i % 3 === 1) {
        ctx.fillStyle = 'rgba(255,47,142,0.55)';
        ctx.fillRect(Math.round(bx + bw * 0.62), 500 - bh + 26, 8, 54);
        ctx.fillStyle = 'rgba(255,47,142,0.16)';
        ctx.fillRect(Math.round(bx + bw * 0.62) - 5, 500 - bh + 21, 18, 64);
      }
      if (i % 4 === 2) {
        ctx.fillStyle = 'rgba(61,243,255,0.4)';
        ctx.fillRect(Math.round(bx + 10), 500 - bh + 40, bw - 20, 5);
      }
    }
    ctx.restore();
  },

  _drawFallbackNear(ctx, camX) {
    ctx.save();
    /* 地面 */
    const g = ctx.createLinearGradient(0, 350, 0, 540);
    g.addColorStop(0, '#241436');
    g.addColorStop(0.35, '#1b1029');
    g.addColorStop(1, '#0d0817');
    ctx.fillStyle = g;
    ctx.fillRect(camX - 40, 350, NF.config.VIEW_W + 80, 190);
    /* 人行道边沿 */
    ctx.fillStyle = '#2d1b45';
    ctx.fillRect(camX - 40, 342, NF.config.VIEW_W + 80, 10);
    ctx.fillStyle = 'rgba(61,243,255,0.28)';
    ctx.fillRect(camX - 40, 342, NF.config.VIEW_W + 80, 2);
    /* 透视地砖 */
    ctx.strokeStyle = 'rgba(120,80,180,0.12)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 16; i++) {
      const x = camX + i * 140 - (camX % 140);
      ctx.beginPath();
      ctx.moveTo(x, 352);
      ctx.lineTo(x - 90, 540);
      ctx.stroke();
    }
    /* 霓虹倒影 */
    ctx.globalAlpha = 0.22;
    ctx.fillStyle = '#ff2f8e';
    ctx.fillRect(camX + 120, 430, 160, 5);
    ctx.fillStyle = '#3df3ff';
    ctx.fillRect(camX + 430, 480, 220, 4);
    ctx.globalAlpha = 1;
    ctx.restore();
  }
};
