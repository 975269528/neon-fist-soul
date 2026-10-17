/* NEON FIST SOUL — 主角「凯 KAI」像素资源清单。
 * 由 tools/gen_hero.py 程序化生成并烘焙，请勿手改。
 * 帧尺寸 240x240，锚点 (120,224)=双脚落点，默认朝右绘制（引擎水平翻转）。
 */
/* eslint-disable */
NF.registerChar('hero', {
  frameW: 240, frameH: 240, anchorX: 120, anchorY: 224, bodyHeight: 186,
  portrait: 'chars/hero/portrait.png',
  animations: {
    idle: { file: 'chars/hero/idle.png', frames: 4, fps: 6, loop: true },
    walk: { file: 'chars/hero/walk.png', frames: 8, fps: 10, loop: true },
    punch1: { file: 'chars/hero/punch1.png', frames: 4, fps: 14, loop: false },
    punch2: { file: 'chars/hero/punch2.png', frames: 4, fps: 14, loop: false },
    punch3: { file: 'chars/hero/punch3.png', frames: 5, fps: 12, loop: false },
    kick: { file: 'chars/hero/kick.png', frames: 5, fps: 12, loop: false },
    jump: { file: 'chars/hero/jump.png', frames: 4, fps: 10, loop: false },
    hurt: { file: 'chars/hero/hurt.png', frames: 2, fps: 10, loop: false },
    ko: { file: 'chars/hero/ko.png', frames: 5, fps: 8, loop: false },
    special: { file: 'chars/hero/special.png', frames: 8, fps: 12, loop: false },
    victory: { file: 'chars/hero/victory.png', frames: 5, fps: 8, loop: false },
  }
});
