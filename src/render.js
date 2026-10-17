/* 霓虹拳魂 NEON FIST SOUL — 精灵渲染器
 *
 * 所有角色动画都是横向排列的精灵表（spritesheet）：
 * 每帧尺寸 = manifest.frameW × manifest.frameH，
 * 第 n 帧的源矩形 = (n * frameW, 0, frameW, frameH)。
 * 绘制锚点 (anchorX, anchorY) 表示「双脚落点」在帧内的坐标。
 */
window.NF = window.NF || {};

NF.render = {
  init() {
    this.ctx = null;
  },

  /** 帧索引：根据动画时间和 fps 计算，loop=false 时停在最后一帧 */
  frameIndex(animDef, time) {
    if (!animDef) return 0;
    const frames = Math.max(1, animDef.frames | 0);
    const fps = animDef.fps || 8;
    let f = Math.floor(time * fps);
    if (f < 0) f = 0;
    if (animDef.loop === false) return Math.min(frames - 1, f);
    return f % frames;
  },

  drawCharAnim(ctx, charName, animName, animTime, x, y, opts) {
    const c = NF.chars[charName];
    if (!c) { this.drawPlaceholder(ctx, x, y, charName, animName, opts); return 0; }
    let anim = c.animations && c.animations[animName];
    if (!anim) anim = c.animations && c.animations.idle;
    const frame = this.frameIndex(anim, animTime || 0);
    this.drawChar(ctx, charName, animName, frame, x, y, opts);
    return frame;
  },

  drawChar(ctx, charName, animName, frame, x, y, opts) {
    opts = opts || {};
    const c = NF.chars[charName];
    const scale = opts.scale == null ? 1 : opts.scale;
    const facing = opts.facing === -1 ? -1 : 1;
    const alpha = opts.alpha == null ? 1 : opts.alpha;
    const flash = opts.flash || 0;

    if (!c) { this.drawPlaceholder(ctx, x, y, charName, animName, opts); return; }

    let anim = c.animations && (c.animations[animName] || c.animations.idle);
    if (!anim) { this.drawPlaceholder(ctx, x, y, charName, animName, opts); return; }
    const img = NF.assets.get(anim.file);
    if (!img) { this.drawPlaceholder(ctx, x, y, charName, animName, opts); return; }

    const fw = c.frameW, fh = c.frameH;
    const sx = NF.util.clamp(frame | 0, 0, Math.max(0, anim.frames - 1)) * fw;

    ctx.save();
    ctx.globalAlpha *= alpha;
    ctx.imageSmoothingEnabled = false;
    ctx.translate(Math.round(x), Math.round(y));
    ctx.scale(facing * scale, scale);
    if (flash > 0.01) {
      ctx.filter = 'brightness(' + (1 + flash * 3.2).toFixed(2) + ') saturate(' + (1 - flash * 0.7).toFixed(2) + ')';
    }
    ctx.drawImage(img, sx, 0, fw, fh, -c.anchorX, -c.anchorY, fw, fh);
    if (flash > 0.55) {
      /* 强闪光：叠加一层提亮，强化打击感 */
      ctx.globalCompositeOperation = 'lighter';
      ctx.globalAlpha *= (flash - 0.55) * 0.9;
      ctx.drawImage(img, sx, 0, fw, fh, -c.anchorX, -c.anchorY, fw, fh);
    }
    ctx.filter = 'none';
    ctx.restore();
  },

  drawPlaceholder(ctx, x, y, charName, animName, opts) {
    opts = opts || {};
    const scale = opts.scale == null ? 1 : opts.scale;
    const facing = opts.facing === -1 ? -1 : 1;
    const def = NF.chars[charName];
    const h = (def && def.bodyHeight) || 180;
    const w = h * 0.42;
    const hue = (charName || 'x').charCodeAt(0) * 37 % 360;
    ctx.save();
    ctx.translate(Math.round(x), Math.round(y));
    ctx.scale(facing * scale, scale);
    ctx.globalAlpha *= (opts.alpha == null ? 1 : opts.alpha) * 0.85;
    ctx.fillStyle = 'hsl(' + hue + ',45%,26%)';
    ctx.fillRect(-w / 2, -h, w, h);
    ctx.fillStyle = 'hsl(' + hue + ',65%,52%)';
    ctx.beginPath();
    ctx.arc(0, -h + w * 0.42, w * 0.36, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillRect(-w * 0.34, -h * 0.62, w * 0.68, h * 0.32);
    ctx.strokeStyle = 'rgba(255,255,255,0.55)';
    ctx.lineWidth = 1;
    ctx.strokeRect(-w / 2, -h, w, h);
    ctx.fillStyle = '#fff';
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    ctx.fillText((charName || '?') + ':' + (animName || '?'), 0, -h - 6);
    ctx.restore();
  },

  /** 角色脚底阴影 */
  drawShadow(ctx, x, y, width, alpha) {
    if (width == null) width = 52;
    if (alpha == null) alpha = 0.32;
    ctx.save();
    ctx.globalAlpha *= alpha;
    ctx.fillStyle = '#05020a';
    ctx.beginPath();
    ctx.ellipse(Math.round(x), Math.round(y) + 1, width * 0.5, width * 0.17, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
};
