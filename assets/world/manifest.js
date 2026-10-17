/* 霓虹拳魂 NEON FIST SOUL — 场景 / UI 资源清单
 * 由 tools/gen_world.py 生成，可安全手工微调（不会自动覆盖时请重跑 gen_world.py）。
 * 视差系数：far 0.12(横向平铺) / mid 0.45 / near 1.0 / fg 1.12
 */
window.NF = window.NF || {};
(function () {
  if (!NF.registerWorld) {
    console.error('[NEON] NF.registerWorld 未定义：请检查脚本加载顺序（assets.js 必须在 world/manifest.js 之前）');
    return;
  }
  NF.registerWorld({
    stageW: 3200,
    layers: {
      far:  { file: 'world/bg_far.png',  factor: 0.12, y: 0, tile: true },
      mid:  { file: 'world/bg_mid.png',  factor: 0.45, y: 0 },
      near: { file: 'world/bg_near.png', factor: 1.0,  y: 0 },
      fg:   { file: 'world/bg_fg.png',   factor: 1.12, y: 0, alpha: 1 }
    },
    ui: {
      logo: 'ui/logo.png'
    }
  });
})();
