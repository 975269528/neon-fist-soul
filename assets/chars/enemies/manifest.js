/* 霓虹拳魂 NEON FIST SOUL — 敌人与 Boss 资源清单
 * 由 tools/gen_enemies.py 自动生成，请勿手改。
 * 敌人：punk 混混 / brute 壮汉 / boss 铁面 IRON MASK
 */
(function () {
  var NF = window.NF;
  if (!NF || !NF.registerChar) return;

  NF.registerChar('punk', {
    frameW: 220, frameH: 220, anchorX: 110, anchorY: 206,
    bodyHeight: 176,
    portrait: 'chars/enemies/punk/portrait.png',
    animations: {
      idle: { file: 'chars/enemies/punk/idle.png', frames: 4, fps: 6, loop: true },
      walk: { file: 'chars/enemies/punk/walk.png', frames: 6, fps: 10, loop: true },
      attack: { file: 'chars/enemies/punk/attack.png', frames: 4, fps: 10, loop: false },
      hurt: { file: 'chars/enemies/punk/hurt.png', frames: 2, fps: 10, loop: false },
      ko: { file: 'chars/enemies/punk/ko.png', frames: 4, fps: 8, loop: false }
    }
  });

  NF.registerChar('brute', {
    frameW: 280, frameH: 280, anchorX: 140, anchorY: 264,
    bodyHeight: 216,
    portrait: 'chars/enemies/brute/portrait.png',
    animations: {
      idle: { file: 'chars/enemies/brute/idle.png', frames: 4, fps: 5, loop: true },
      walk: { file: 'chars/enemies/brute/walk.png', frames: 6, fps: 8, loop: true },
      attack: { file: 'chars/enemies/brute/attack.png', frames: 5, fps: 9, loop: false },
      hurt: { file: 'chars/enemies/brute/hurt.png', frames: 2, fps: 8, loop: false },
      ko: { file: 'chars/enemies/brute/ko.png', frames: 4, fps: 7, loop: false }
    }
  });

  NF.registerChar('boss', {
    frameW: 340, frameH: 340, anchorX: 170, anchorY: 322,
    bodyHeight: 250,
    portrait: 'chars/enemies/boss/portrait.png',
    animations: {
      idle: { file: 'chars/enemies/boss/idle.png', frames: 4, fps: 5, loop: true },
      walk: { file: 'chars/enemies/boss/walk.png', frames: 6, fps: 8, loop: true },
      attack1: { file: 'chars/enemies/boss/attack1.png', frames: 5, fps: 9, loop: false },
      attack2: { file: 'chars/enemies/boss/attack2.png', frames: 5, fps: 9, loop: false },
      roar: { file: 'chars/enemies/boss/roar.png', frames: 6, fps: 8, loop: false },
      hurt: { file: 'chars/enemies/boss/hurt.png', frames: 2, fps: 8, loop: false },
      ko: { file: 'chars/enemies/boss/ko.png', frames: 6, fps: 6, loop: false }
    }
  });
})();
