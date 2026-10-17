/* 霓虹拳魂 NEON FIST SOUL — 资源注册与加载
 *
 * 美术模块通过 NF.registerChar / NF.registerWorld 注册资源清单。
 * 所有图片路径都相对于 assets/ 目录。
 *
 * 角色清单结构：
 * NF.registerChar('hero', {
 *   frameW: 240, frameH: 240,
 *   anchorX: 120, anchorY: 226,   // 帧内「双脚落点」的像素坐标
 *   bodyHeight: 190,              // 参考身高（HUD/挨打框用）
 *   portrait: 'chars/hero/portrait.png',
 *   animations: {
 *     idle:    { file: 'chars/hero/idle.png',    frames: 4, fps: 6,  loop: true },
 *     walk:    { file: 'chars/hero/walk.png',    frames: 8, fps: 12, loop: true },
 *     ...
 *   }
 * });
 *
 * 场景清单结构：
 * NF.registerWorld({
 *   stageW: 3200,
 *   layers: {
 *     far:  { file: 'world/bg_far.png',  factor: 0.12, y: 0, tile: true },
 *     mid:  { file: 'world/bg_mid.png',  factor: 0.45, y: 0 },
 *     near: { file: 'world/bg_near.png', factor: 1.0,  y: 0 },
 *     fg:   { file: 'world/bg_fg.png',   factor: 1.12, y: 0, alpha: 1 }
 *   },
 *   ui: { logo: 'ui/logo.png', titleBg: 'ui/title_bg.png' }
 * });
 */
window.NF = window.NF || {};

NF.chars = Object.create(null);
NF.world = { stageW: 3200, layers: {}, ui: {} };

NF.registerChar = function (name, def) {
  if (!name || !def) return;
  NF.chars[name] = def;
};

NF.registerWorld = function (def) {
  if (!def) return;
  NF.world = def;
  if (!NF.world.stageW) NF.world.stageW = NF.config.STAGE_W;
  if (!NF.world.layers) NF.world.layers = {};
  if (!NF.world.ui) NF.world.ui = {};
};

NF.assets = {
  images: Object.create(null),
  loaded: false,
  loadError: false,
  _promise: null,

  path(file) { return 'assets/' + String(file || '').replace(/^assets\//, ''); },

  get(file) {
    if (!file) return null;
    return this.images[file] || null;
  },

  /** 角色动画定义（不存在时返回 null） */
  anim(charName, animName) {
    const c = NF.chars[charName];
    if (!c || !c.animations) return null;
    return c.animations[animName] || null;
  },

  char(charName) { return NF.chars[charName] || null; },

  portrait(charName) {
    const c = NF.chars[charName];
    if (!c || !c.portrait) return null;
    return this.get(c.portrait);
  },

  ui(name) {
    const map = NF.world.ui || {};
    return this.get(map[name]);
  },

  _collect() {
    const paths = [];
    const add = (p) => { if (p && paths.indexOf(p) < 0) paths.push(p); };
    Object.keys(NF.chars).forEach((name) => {
      const c = NF.chars[name];
      Object.keys(c.animations || {}).forEach((k) => add(c.animations[k].file));
      add(c.portrait);
    });
    const layers = (NF.world && NF.world.layers) || {};
    Object.keys(layers).forEach((k) => add(layers[k] && layers[k].file));
    const ui = (NF.world && NF.world.ui) || {};
    Object.keys(ui).forEach((k) => add(ui[k]));
    return paths;
  },

  loadAll() {
    if (this._promise) return this._promise;
    const paths = this._collect();
    const jobs = paths.map((p) => new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        this.images[p] = img;
        resolve();
      };
      img.onerror = () => {
        this.loadError = true;
        console.warn('[NEON] 图片加载失败（将使用占位图）:', this.path(p));
        resolve();
      };
      img.src = this.path(p);
    }));
    this._promise = Promise.race([
      Promise.all(jobs).then(() => { this.loaded = true; }),
      new Promise((resolve) => setTimeout(() => {
        console.warn('[NEON] 资源加载超时，使用已加载部分继续');
        this.loaded = true;
        resolve();
      }, 15000))
    ]).then(() => { this.loaded = true; });
    return this._promise;
  }
};
