# 霓虹拳魂 NEON FIST SOUL — 开发契约（唯一事实来源）

> 纯 HTML5 Canvas 横板像素街机清版动作游戏。**不使用 Maker、不依赖任何外部库/网络资源、不打包构建**。
> 目标：双击 `index.html` 即可游玩（file:// 兼容），画面达到「精细像素 + 清晰可见的脸部/身体细节」。

---

## 0. 项目状态与文件所有权

当前目录：`C:\Users\Administrator\Desktop\像素风格测试DS`

| 所有者 | 文件 / 目录 |
| --- | --- |
| Lead | `index.html`、`styles.css`、`src/config.js`、`src/utils.js`、`src/assets.js`、`src/input.js`、`src/camera.js`、`src/render.js`、`src/stage.js`、`src/main.js`、`README.md`、`tools/shot.ps1` |
| 主角美术 | `assets/chars/hero/**`、`tools/gen_hero.py` |
| 敌人美术 | `assets/chars/enemies/**`、`tools/gen_enemies.py` |
| 场景 UI 美术 | `assets/world/**`、`assets/ui/**`、`tools/gen_world.py`、`assets/world/manifest.js` |
| 战斗玩法 | `src/player.js`、`src/enemies.js`、`src/game.js` |
| 特效 HUD | `src/fx.js`、`src/hud.js` |
| 音频 | `src/audio.js` |

**硬性规则**
1. 只修改自己名下的文件。需要改动别人文件/接口时，先给 Lead 发消息。
2. 不要改 `index.html`（脚本顺序已定）；不要新增 `<script>` 引用。
3. 不要重命名/移动已有文件；不要执行 git 操作；不要安装任何依赖。
4. 所有美术资源必须由 `tools/gen_*.py`（Python + Pillow）程序化生成，可重复运行，不得下载外部图片/字体资源（系统字体仅允许用于 Logo 的中文像素化处理）。
5. 代码保持 UTF-8 无 BOM；JS 为普通脚本（非 ES module），用 `window.NF` 命名空间。
6. 完成后把结果和截图路径用 `send_message` 报告给 `lead`；有阻塞立刻报告。
7. 每完成一批 JS 修改跑：`node --check <file>`；页面截图验证后再报完成。

**共享工具**
- 本地服务器已由 Lead 启动：`http://127.0.0.1:8123`（如不可用，报告 Lead，不要自己占用其他端口）。
- 截图命令（在项目根目录）：
  ```powershell
  & .\tools\shot.ps1 -Name <名字> -Query "?shot=battle&freeze=0.2" -WaitMs 4000
  ```
  输出到 `shots/<名字>.png`，用 `read_image` 查看。**不同成员用各自前缀命名**（如 `hero_`、`fx_`、`game_`），避免互相覆盖。
- 截图 URL 参数：`shot=title|battle|boss|victory|gameover|combo|intro`、`freeze=秒`、`touch=1`、`debug=1`。
- 页面截图由 `src/main.js` 在资源加载后同步模拟并渲染（`freeze` 秒），完成后 `window.__SHOT_READY === true`。

---

## 1. 游戏设计目标

- 单关卡「霓虹后巷」，横板清版：2.5D 纵深移动、连招、跳跃、必杀、波次敌人、Boss 战。
- 画面：90 年代街机像素美术 + 赛博霓虹夜巷；角色身高约 180–250 逻辑像素，**脸部（眼、眉、鼻、嘴、下颌）清晰可读**；环境有雨、霓虹反射、蒸汽、远景层次。
- 打击感：命中停顿（hitstop）、震屏、火花、伤害数字、连击数、KO 慢镜、必杀特写。
- 可玩性：键盘 + 触屏（虚拟摇杆/按钮）；标题/战斗/暂停/胜利/失败完整循环。
- 性能：60 FPS；逻辑分辨率 960×540。

### 1.1 战斗设定（玩法模块实现，其他模块按此出图/出 UI）

- 玩家「凯 KAI」：HP 120，移动速度约 150 px/s（纵深 60%），三段连击（J），重击（K），跳跃（L），必杀（U，需要 100 气）。
- 三段连击：
  1. 刺拳：4 帧动画，伤害 6，硬直 0.25s
  2. 直拳：4 帧，伤害 8，硬直 0.28s
  3. 上勾拳：5 帧，伤害 14，击飞，硬直 0.4s
- 重击：5 帧，伤害 18，大幅击退；可接在连击后。
- 跳跃：起跳高度约 70px，可空中攻击（用 `punch2` 或 `kick` 帧）。
- 必杀「霓虹爆裂」：8 帧，多段判定，总伤害约 40，全屏闪白 + 强震屏 + 慢镜，清空气槽。
- 敌人：
  - `punk` 混混：HP 40，速度 95，近身 4 帧攻击，伤害 7。
  - `brute` 壮汉：HP 95，速度 60，5 帧重拳，伤害 16、击退大。
  - `boss` 铁面 IRON MASK：HP 420，两套攻击（横扫/冲拳），有咆哮前摇和第二阶段（HP<50% 加速、攻击更频繁）。
- 命中规则：攻击 hitbox 与敌人身体矩形相交（x/z 距离 + 纵深 |dy| < 40）。每段攻击对同一目标只命中一次。
- 敌人被击：闪白、击退、硬直、受击音效、火花、伤害数字、连击 +1、加分。死亡播放 `ko` 非循环动画后消失，概率掉血包（+20 HP）。
- 玩家被击：红色闪屏、震屏、无敌时间 0.6s；HP 归零进入 `gameover`。
- 波次：读取 `NF.config.STAGE.waves`（4 波，最后一波 Boss）。清除当前波后，下一波在玩家推进到对应 x 或清场后触发。Boss 波触发时锁定摄像机 `game.cameraLockX = STAGE_W - VIEW_W`，显示 Boss 血条与登场卡。
- 通关：Boss 死亡 → 慢镜 → `victory` 状态。
- 摄像机/排序：实体按脚底 `y` 从远到近排序绘制；影子在角色之下。
- 游戏状态：`title`、`playing`、`paused`、`gameover`、`victory`。`NF.game.update(dt)` 内部处理输入/状态；主循环只调用接口。

### 1.2 音效名称（玩法模块调用，音频模块实现）

`punch`、`heavy`、`hit`、`hitHeavy`、`block`、`whiff`、`ko`、`jump`、`land`、`dash`、`special`、`pickup`、`ui`、`start`、`roar`、`victory`、`gameover`、`wave`、`combo`

音乐场景：`title`、`battle`、`boss`、`victory`、`gameover`、`none`

---

## 2. 引擎 API（已实现，直接调用）

### 2.1 `NF.config`
```js
NF.config.VIEW_W=960, VIEW_H=540, STAGE_W=3200
NF.config.GROUND_TOP=356, GROUND_BOTTOM=502       // 脚底 y 范围
NF.config.PLAYER_START_X=320, PLAYER_START_Y=470
NF.config.SHOT / FREEZE / DEBUG / FORCE_TOUCH / MUTE   // URL 调试参数
NF.config.COLORS = { ink, paper, cyan, magenta, purple, yellow, orange, lime, red, blue, steel, deep, ... }
NF.config.STAGE = { name, subtitle, bossArenaX, bossLockCameraX, waves:[{at,count,types,label,boss}] }
NF.config.PLAYER_MAX_HP=120, NF.config.MAX_SPECIAL=100
```

### 2.2 `NF.util`
`clamp, clamp01, lerp, damp, approach, sign, rand, randInt, chance, choice, shuffle, dist, dist2, rectsOverlap, pointInRect, pad, fmtScore, fmtTime, easeOutQuad, easeInCubic, easeOutBack, easeOutElastic, pulse, flicker, hash, hash2, rad, deg`

### 2.3 `NF.chars` / `NF.registerChar`（美术模块使用）
见 §4.1 角色清单结构。

### 2.4 `NF.assets`
```js
NF.assets.get(path)        // path 相对于 assets/，返回 HTMLImageElement 或 null
NF.assets.ui(name)         // 取 NF.world.ui 中注册的 UI 图，返回 Image 或 null
NF.assets.portrait(char)   // 取角色头像 Image 或 null
NF.assets.anim(char, name) // 取动画定义
NF.assets.loaded           // 是否已加载完
```

### 2.5 `NF.input`
```js
NF.input.axisX() / axisY()          // -1..1，触屏摇杆+键盘合成
NF.input.isDown(action)             // 持续按住
NF.input.justPressed(action)        // 本帧按下（主循环每帧末清空）
NF.input.justReleased(action)
NF.input.tapped                     // 本帧点击画布/触屏（用于标题开始）
NF.input.touchMode                  // 是否触屏模式
actions: left,right,up,down,attack,heavy,jump,special,start,pause,mute,dash
```

### 2.6 `NF.camera`
主循环自动 update/apply；`NF.camera.x` 为当前摄像机左边界（世界坐标）。
游戏可通过 `NF.game.cameraLockX`（数字）锁定摄像机；`NF.camera.toScreenX(worldX)`。
世界坐标绘制：主循环已应用摄像机变换，**实体直接用自己的世界坐标绘制**。

### 2.7 `NF.render`
```js
NF.render.drawChar(ctx, charName, animName, frameIndex, x, y, opts)
   // (x,y)=世界坐标中的双脚落点；opts: {facing:1|-1, scale, alpha, flash:0..1}
NF.render.drawCharAnim(ctx, charName, animName, animTime, x, y, opts) // 按 fps 自动算帧
NF.render.frameIndex(animDef, time)
NF.render.drawShadow(ctx, x, y, width, alpha)
```
`(x, y)` 是脚底；跳跃请自行把绘制 y 减去 `z`。

### 2.8 `NF.stage`
主循环自动绘制；无需调用。

### 2.9 `NF.fx`（特效模块实现，玩法模块调用）
```js
NF.fx.update(dt)
NF.fx.draw(ctx)                  // 世界空间粒子（相机内）
NF.fx.drawOverlay(ctx)           // 屏幕叠加层（雨/暗角/速度线/扫描线，HUD 前）
NF.fx.drawTop(ctx)               // 顶层闪白/红屏（HUD 后）
NF.fx.shakeOffset() -> {x,y}
NF.fx.shake(mag, dur)
NF.fx.hitSpark(x, y, dir, power)         // dir: -1/1 击退方向；power: 0..1
NF.fx.dust(x, y, opts)
NF.fx.damageNumber(x, y, amount, opts)   // opts: {color, big, combo}
NF.fx.text(x, y, text, opts)             // 飘字
NF.fx.flash(color, alpha, dur)
NF.fx.clear()
```
额外可自行增加，但以上必须存在且签名兼容。

### 2.10 `NF.hud`（HUD 模块实现，主循环调用）
```js
NF.hud.init()
NF.hud.draw(ctx, game, time)     // 每帧绘制全部 UI（根据 game.state 分支：标题/战斗 HUD/暂停/失败/胜利/Boss登场）
NF.hud.toast(text, opts)
NF.hud.pixelText(ctx, text, x, y, opts)   // 像素字（ASCII），供其他模块使用
NF.hud.drawPortrait(ctx, charName, x, y, size)
```
HUD 在屏幕坐标绘制（不受摄像机影响）。

### 2.11 `NF.audio`（音频模块实现）
```js
NF.audio.init(); NF.audio.unlock(); NF.audio.update(dt);
NF.audio.sfx(name); NF.audio.music(scene);
NF.audio.setMuted(bool) -> bool; NF.audio.toggleMute() -> bool; NF.audio.duck(bool)
```

### 2.12 `NF.game`（玩法模块实现，主循环调用）
```js
NF.game.init()
NF.game.update(dt)
NF.game.draw(ctx)            // 世界空间：影子、玩家、敌人、掉落物
NF.game.togglePause()
NF.game.debugStart(name)     // 截图场景，见 §5.3
NF.game.state                // 'title'|'playing'|'paused'|'gameover'|'victory'
```
HUD 依赖的字段（必须维护）：
```js
game.player                  // 必须含 hp,maxHp,special,maxSpecial,x,y,facing,alive,anim
game.state, game.time, game.score, game.highScore, game.wave, game.totalWaves,
game.combo, game.comboTimer, game.maxCombo, game.kills,
game.banner                  // {label, sub, timer, max} 或 null（波次/Boss提示）
game.boss                    // null 或 {name, hp, maxHp, active}
game.cameraLockX             // 数字或 undefined
game.gameoverReason          // 'HP 归零' 等
game.shotFrozen              // 截图场景冻结标志
```
HUD 允许通过 `game.player` 等字段推导显示，不得要求玩法模块调用 HUD 内部函数。

### 2.13 主循环渲染顺序（已固定）
```
stage.drawBack → game.draw → stage.drawForeground → fx.draw
→ fx.drawOverlay → hud.draw → fx.drawTop
```
主循环每帧：`input.poll → game.update → fx.update → audio.update → camera.update → input.endFrame → render`。
镜头震动由 `NF.fx.shakeOffset()` 提供，主循环应用。

---

## 3. 美术总纲（所有美术模块共同遵守）

- 风格：90 年代街机 / 32-bit 像素风，赛博霓虹夜巷；**1px 深色描边**（如 `#150b22`，不要纯黑），色块分区清晰。
- 调色板（全局基调）：
  - 夜空/背景：`#07050f #0d0820 #1a0d33 #2a1245 #3d1a5c`
  - 霓虹：青 `#3df3ff #1a8ca8`；品红 `#ff2f8e #a11856`；紫 `#7a3cff`；黄 `#ffd23f`；橙 `#ff8a2a`
  - 皮肤：`#f2c49b #d99a72 #a8634a #6e3a36`；暗部偏紫红
  - 金属：`#d7e2f7 #9aa7c7 #5d6b8f #2c3450`
  - 不要大面积纯黑/纯白；阴影向紫/蓝偏移，亮部向黄/品红偏移。
- 每块材质至少 3 个色阶；大色块可用抖动/斜线纹理，脸部禁止抖动噪点。
- **脸是验收重点**：脸部约 40–60px 高（主角），必须能看清：白色眼白+虹膜/瞳孔、上眼线、眉毛、鼻梁阴影+鼻头高光、嘴线（攻击时咬牙/张嘴）、下颌/颧骨阴影、耳朵；主角可加刀疤、胡茬或耳饰。
- 角色默认朝右画（引擎水平翻转朝左）；3/4 侧脸，允许双眼可见。
- 使用全局光照方向：左后方青色轮廓光、右后方品红轮廓光。
- 不要烘焙影子（引擎绘制）；不要烘焙文字（Logos 除外）；角色动画帧内不要带背景。
- 所有角色帧布局：横向精灵表，`frames` 个等宽帧，透明底；**任何肢体不得越出帧边界**。
- 生成脚本必须可复跑；输出 PNG 为 RGBA，png 无损。

### 3.1 角色帧规格与动画清单

| 角色 | 帧尺寸 frameW×frameH | 锚点 anchorX, anchorY | 参考身高 | 说明 |
| --- | --- | --- | --- | --- |
| `hero` 凯 | 240×240 | 120, 224 | 186px | 主角，精瘦有力，刺猬头 |
| `punk` 混混 | 220×220 | 110, 206 | 176px | 莫西干/脏辫，瘦 |
| `brute` 壮汉 | 280×280 | 140, 264 | 216px | 光头/络腮胡，巨大 |
| `boss` 铁面 | 340×340 | 170, 322 | 250px | 鬼面具+大衣+机械臂 |

**主角 hero 动画（必须全部实现）**

| anim | 帧数 | fps | loop | 内容 |
| --- | --- | --- | --- | --- |
| idle | 4 | 6 | true | 战斗待机，轻微起伏/呼吸，双拳架势 |
| walk | 8 | 10 | true | 侧向行走，手臂摆动 |
| punch1 | 4 | 14 | false | 左手刺拳，收招 |
| punch2 | 4 | 14 | false | 右手直拳，身体前倾 |
| punch3 | 5 | 12 | false | 上勾拳，腰部发力和上挑 |
| kick | 5 | 12 | false | 回旋踢/侧踹，腿部伸展 |
| jump | 4 | 10 | false | 起跳-滞空-下落（收腿） |
| hurt | 2 | 10 | false | 后仰受击、痛苦表情 |
| ko | 5 | 8 | false | 中招倒地，闭眼 |
| special | 8 | 12 | false | 蓄力→多段连打/升龙式必杀，带自身霓虹光 |
| victory | 5 | 8 | false | 胜利姿势/握拳，可复用待机加手势 |

**punk 混混**：`idle 4@6`、`walk 6@10`、`attack 4@10`、`hurt 2@10`、`ko 4@8`
**brute 壮汉**：`idle 4@5`、`walk 6@8`、`attack 5@9`、`hurt 2@8`、`ko 4@7`
**boss 铁面**：`idle 4@5`、`walk 6@8`、`attack1 5@9`、`attack2 5@9`、`roar 6@8`、`hurt 2@8`、`ko 6@6`

**每个角色的 manifest.js** 必须注册：`frameW, frameH, anchorX, anchorY, bodyHeight, portrait, animations{...}`。
文件路径示例：
```js
NF.registerChar('hero', {
  frameW:240, frameH:240, anchorX:120, anchorY:224, bodyHeight:186,
  portrait:'chars/hero/portrait.png',
  animations:{
    idle:{file:'chars/hero/idle.png', frames:4, fps:6, loop:true},
    walk:{file:'chars/hero/walk.png', frames:8, fps:10, loop:true},
    punch1:{file:'chars/hero/punch1.png', frames:4, fps:14, loop:false},
    /* ...全部动画... */
  }
});
```

**头像 portrait**：主角 `192×192`，敌人/Boss `160×160`，透明底，头肩特写，必须体现脸部细节，用于标题/HUD/Boss登场。放在角色目录下。

### 3.2 场景图层规格（场景 UI 美术）

| 文件 | 尺寸 | 视差 factor | 说明 |
| --- | --- | --- | --- |
| `assets/world/bg_far.png` | 1600×540 | 0.12（横向可平铺） | 夜空、远景楼群、霓虹天际线、雨雾；左右边缘必须无缝衔接 |
| `assets/world/bg_mid.png` | 3200×540 | 0.45 | 中景楼体、拉面店/居酒屋招牌、海报、空调外机、灯牌 |
| `assets/world/bg_near.png` | 3200×540 | 1.0 | 近景街面、人行道边缘、湿沥青反光、水洼、垃圾、消防栓、卷帘门；角色活动区（y≈350–505）要偏暗、低对比，保证角色可读性 |
| `assets/world/bg_fg.png` | 3200×540 | 1.12 | 透明前景剪影：电线杆、电线、蒸汽管、箱子、雨棚边缘，别遮挡屏幕中央面部区域；可少量底部反光 |

世界宽 3200，画布 960×540。地面纵深线：`GROUND_TOP=356`，`GROUND_BOTTOM=502`（脚底 y），美术布局按此。
`assets/world/manifest.js`：
```js
NF.registerWorld({
  stageW: 3200,
  layers: {
    far:{file:'world/bg_far.png', factor:0.12, y:0, tile:true},
    mid:{file:'world/bg_mid.png', factor:0.45, y:0},
    near:{file:'world/bg_near.png', factor:1.0, y:0},
    fg:{file:'world/bg_fg.png', factor:1.12, y:0, alpha:1}
  },
  ui:{ logo:'ui/logo.png' }
});
```

**UI 美术**：`assets/ui/logo.png` 760×240 RGBA，透明底。标题「霓虹拳魂」+ 副标题「NEON FIST SOUL」，90 年代街机金属/霓虹字效（中文可用系统字体阈值化后做像素化，再用描边/渐变/霓虹辉光处理），必须清晰、有设计感。标题画面由 HUD 模块用 logo + 背景 + 角色头像排版。

### 3.3 美术自检要求

1. 先做静态关键帧（idle + portrait），渲染到深色棋盘格/截图检查，**用 `read_image` 自己看**，确认脸部可读、描边干净、无锯齿色边。
2. 再批量烘焙所有动画，生成 contact sheet（`assets/<...>/preview.png` 等，可额外放 `shots/art_*.png`），逐帧检查肢体不越界、关节无断裂、动画连贯。
3. 把 idle 帧放进游戏里用截图工具看整体大小与场景比例；主角身高应约 186px、Boss 约 250px（逻辑像素）。
4. 发现比例/锚点错误，改脚本重新烘焙，不要手改 PNG。

---

## 4. 玩法模块要求（`src/player.js`、`src/enemies.js`、`src/game.js`）

- 用 `NF.render.drawCharAnim` 绘制角色；绘制位置 = `(x, y - z)`，影子 `NF.render.drawShadow(ctx, x, y, w, alpha)`。
- 实体按脚底 `y` 排序绘制（远→近）；玩家也参与排序。
- 攻击判定：攻击帧窗口内生成 hitbox；对同一目标每段只命中一次；命中调用 `NF.fx.hitSpark`、`NF.fx.damageNumber`、`NF.fx.shake`、`NF.audio.sfx('hit'/'hitHeavy')`，并触发 hitstop（`game.hitstop`）。
- 连击：命中时 `game.combo++`、刷新 `comboTimer≈2.2s`、加分；连击结束归零；`game.maxCombo` 记录最高。
- 计分：普通 100、重击 180、必杀每段 60、KO 300 + 连击加成；通关结算。
- 掉落：敌人死亡 25% 掉血包（+20HP），Boss 必掉；拾取音效 `pickup`。
- AI：敌人在纵深上向玩家靠拢，进入攻击距离后停下并蓄力（前摇 0.3–0.7s，有视觉变化），攻击后硬直；同屏同时攻击的敌人 ≤2；不要重叠站位；被击飞/KO 有物理位移。
- Boss：两套攻击（近身横扫、蓄力冲拳），HP<50% 进二阶段（速度/频率提升、偶尔咆哮），有登场卡（`game.banner`）和血条（`game.boss`）。
- 摄像机：Boss 波设置 `game.cameraLockX` 锁定到 `STAGE_W - VIEW_W`；波次推进按 `NF.config.STAGE.waves`。
- 游戏结束：HP 归零 → `gameover` + 音效 + 慢镜；`start` 回到标题；标题 `start` 开始游戏。
- 暂停：`NF.game.togglePause()` 在 `playing`/`paused` 间切换；暂停时音效/音乐处理见音频契约（`NF.audio.music('none')`，恢复 `battle`/`boss`）。
- 性能：每帧实体 ≤ 8，粒子调用合理；不要创建 DOM。
- 调试截图 `debugStart(name)`：
  - 必须设置 `game.shotFrozen = true`，`update()` 在冻结时只推进 HUD 需要的时间，不移动实体，保证画面可复现。
  - `title`：标题状态。
  - `battle`：玩家居中偏左，做出 `punch3` 命中姿态；2 个 punk + 1 个 brute 分布在玩家右前方，其中一只处于受击后仰；生成火花/伤害数字；combo=7；HUD 完整。
  - `boss`：Boss 与玩家对峙/交手中，Boss 血条可见，摄像机锁定 Boss 区。
  - `victory` / `gameover`：设置对应状态与结算数据。
  - `combo`：高连击展示（combo=23、满屏火花、伤害数字）。
  - `intro`：Boss 登场卡。

---

## 5. 特效 HUD 模块要求（`src/fx.js`、`src/hud.js`）

### 5.1 FX
- 雨（世界屏幕空间均可，建议 `drawOverlay` 前处理）、地面水花、霓虹光斑/蒸汽/漂浮灰尘。
- 命中：白/黄火花 + 青色/品红碎光、冲击环、短暂速度线；重击加强并触发更强震屏；KO 触发慢镜线条。
- 屏幕：`shake`（带衰减）、`flash`（命中白闪/受伤红闪/必杀全屏霓虹闪）、暗角、可选扫描线（轻微，不影响清晰度）。
- 伤害数字：像素字体，上飘+淡出，暴击/重击更大更黄。
- `drawTop` 负责覆盖 HUD 的闪白/红屏。
- 性能：粒子池 ≤ 300，避免每帧新建 canvas；截图场景效果需在 1.5s 内仍可见（debug 场景用较长寿命）。

### 5.2 HUD / 菜单
- 960×540 屏幕坐标系；风格与像素美术统一（深色半透明面板、1–2px 霓虹描边、斜切角、扫描线纹理）。
- 战斗 HUD：
  - 左上：主角头像（48–64px）+ 名字「凯 KAI」+ 血条（含白色延迟掉血层）+ 气槽（满时闪烁「必杀 READY」）。
  - 右上：SCORE 7 位、WAVE x/4、最高分。
  - 中左：连击「xx HITS」（大号、弹跳缩放、连击计时条）。
  - 底部中央：Boss 血条 + 名称「铁面 IRON MASK」（仅 Boss 战）。
  - 波次横幅：滑入/淡出（`game.banner`）；Boss 登场卡：暗场 + Boss 头像 + 名称/称号 + 霓虹线条，显示约 2.2s。
- 标题画面：背景（舞台）+ 暗角；`assets/ui/logo.png` 居中偏上；主角头像/立绘装饰；「点击 / 按 Enter 开始」呼吸闪烁；操作说明（WASD/方向键移动，J 攻击，K 重击，L 跳跃，U 必杀）；最高分。若 logo 图片未加载，绘制程序化标题兜底。
- 暂停：暗色遮罩 + 「暂停 PAUSED」+ 继续/重开提示。
- 失败：红色调遮罩，「K.O.」/「你倒下了」+ 分数/最高连击/击杀数 + 重新开始提示。
- 胜利：霓虹胜利字，「STAGE CLEAR / 霓虹后巷已清空」+ 结算数据 + 再玩一次提示。
- 像素字体：在 `hud.js` 内实现 5×7 ASCII 点阵字体（A-Z、0-9、常用标点）用于数字/英文；中文使用 `"Microsoft YaHei"/"PingFang SC"` 粗体，加 1px 深色描边与霓虹色，避免模糊大字号（整数像素字号）。
- 触屏模式提示（移动端可用虚拟按键）可由 HUD 在标题显示小提示，但按钮由 Lead 的 DOM 提供。

---

## 6. 音频模块要求（`src/audio.js`）

- 仅 WebAudio 程序化合成，无外部音频文件；首次用户手势后解锁（`unlock()`），`init()` 可提前创建上下文但必须容忍 suspended/不支持。
- 芯片音乐 + synthwave 风格：
  - `title`：慢速氛围合成器 pad + 稀疏琶音，BPM ≈ 92，暗色小调。
  - `battle`：BPM ≈ 128，驱动八分音符贝斯、方波主旋律、琶音、四四拍鼓（kick/snare/hat），16 步序列器循环。
  - `boss`：BPM ≈ 140，更重低音、失真 lead、密集鼓。
  - `victory`：短胜利 fanfare 循环；`gameover`：下行低音短句。
- 场景切换有淡入淡出（约 0.3–0.6s）；支持静音（主 GainNode，不销毁上下文）；页面隐藏时 duck。
- 音效列表见 §1.2；打击音要分层（attack whiff + impact + 低频 body），音量平衡避免刺耳；音效可随机微调音高。
- 不阻塞主线程：使用 lookahead 调度（`update(dt)` 中提前 0.1–0.2s 排程）。
- 无头截图环境（无手势）不得报错。

---

## 7. 验收与截图场景

必须用截图工具自查这些画面（命名 `shots/<模块>_*.png`）：

| shot | 内容 |
| --- | --- |
| `?shot=title&freeze=0.2` | 标题排版、logo、角色头像、开始提示 |
| `?shot=battle&freeze=0.2` | 战斗 HUD、连击、双方角色、特效 |
| `?shot=boss&freeze=0.2` | Boss 血条、Boss 立绘、锁定镜头 |
| `?shot=combo&freeze=0.2` | 高连击展示 |
| `?shot=victory&freeze=0.2` | 胜利结算 |
| `?shot=gameover&freeze=0.2` | 失败结算 |

最终由 Lead 集成并做整体截图验收。**美术资源不齐时，任何模块都不要用占位图冒充完成。**

---

## 8. 协作与交付

- 每个成员先领取任务（task board），再开始；完成后：
  1. `node --check` 所有改动的 js；
  2. 用截图工具验证自己负责的画面；
  3. `send_message` 给 `lead`，内容：做了什么、文件清单、截图路径、已知问题/待办、是否可集成。
- 不要长时间静默；阶段性成果（如第一版主角 idle）可以先给 Lead 看截图，再继续做动画。
- 遇到接口不匹配、资源尺寸/锚点问题，立刻报 Lead，不要自行改别人的文件。
- 本契约未尽事宜，以 Lead 最新消息为准。
