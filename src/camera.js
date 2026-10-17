/* 霓虹拳魂 NEON FIST SOUL — 摄像机（跟随 + 震屏 + 关卡锁定） */
window.NF = window.NF || {};

NF.camera = {
  x: 0,
  desired: 0,
  shakeX: 0,
  shakeY: 0,

  reset(x) {
    this.x = NF.util.clamp(x || 0, 0, NF.config.STAGE_W - NF.config.VIEW_W);
    this.desired = this.x;
    this.shakeX = 0;
    this.shakeY = 0;
  },

  focusX() {
    const game = NF.game;
    if (!game) return this.x + NF.config.VIEW_W * 0.42;
    if (typeof game.cameraLockX === 'number') return game.cameraLockX + NF.config.VIEW_W * 0.5;
    const p = game.player;
    if (p && typeof p.x === 'number') return p.x + p.facing * NF.config.CAMERA_LOOKAHEAD;
    return this.x + NF.config.VIEW_W * 0.42;
  },

  update(dt) {
    const cfg = NF.config;
    const vw = cfg.VIEW_W;
    let target;
    if (NF.game && typeof NF.game.cameraLockX === 'number') {
      target = NF.game.cameraLockX;
    } else {
      const focus = this.focusX();
      target = focus - vw * 0.42;
    }
    target = NF.util.clamp(target, 0, Math.max(0, cfg.STAGE_W - vw));
    this.desired = target;
    const k = 1 - Math.pow(0.001, dt * (cfg.CAMERA_LERP / 6.5));
    this.x = NF.util.lerp(this.x, target, k);
    if (Math.abs(this.x - target) < 0.35) this.x = target;

    let sx = 0, sy = 0;
    if (NF.fx && NF.fx.shakeOffset) {
      const s = NF.fx.shakeOffset();
      sx = s.x; sy = s.y;
    }
    this.shakeX = sx;
    this.shakeY = sy;
  },

  apply(ctx) {
    ctx.save();
    ctx.translate(-Math.round(this.x) + Math.round(this.shakeX), Math.round(this.shakeY));
  },

  restore(ctx) { ctx.restore(); },

  /** 世界坐标 → 屏幕坐标（不含震屏） */
  toScreenX(worldX) { return worldX - this.x; },
  toWorldX(screenX) { return screenX + this.x; }
};
