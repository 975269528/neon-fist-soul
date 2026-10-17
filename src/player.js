/* 霓虹拳魂 NEON FIST SOUL — 玩家「凯 KAI」
 *
 * 2.5D 横板清版主角：
 *   - x 世界横向 / y 纵深（脚底 356~502）/ z 跳跃离地高度
 *   - J 三段连击（刺拳→直拳→上勾拳），输入缓冲 + 连段取消窗口
 *   - K 重击（可接在连段后）、L 跳跃（可空中攻击）、U 必杀（需 100 气）
 *   - 受击：无敌帧 / 闪白 / 击退 / 硬直；HP 归零播 ko
 *
 * 本文件只实现「实体自身」的行为与姿态；命中判定、计分、特效、音效
 * 全部通过 NF.game 的回调完成，保证玩家/敌人两套实体解耦。
 */
window.NF = window.NF || {};

(function () {
  'use strict';

  const cfg = NF.config;
  const U = NF.util;

  const GROUND_TOP = cfg.GROUND_TOP;
  const GROUND_BOTTOM = cfg.GROUND_BOTTOM;

  /* ---------------- 数值参数 ---------------- */
  const SPEED_X = 150;            // 横向移动速度 px/s
  const SPEED_Y = SPEED_X * 0.6;  // 纵深移动 60%
  const GRAVITY = 1500;           // z 重力（z 向上为正）
  const JUMP_VZ = 445;            // 起跳初速 → 跳跃高度约 66px
  const AIR_MOVE = 0.92;          // 空中横向控制保留率

  const BODY_HALF_W = 24;         // 身体半宽（受击 / 推挤用）
  const BODY_DEPTH = 20;          // 纵深半深
  const BODY_HEIGHT = 186;

  const COMBO_BUFFER = 0.22;      // 连段输入缓冲窗口（秒）

  /* ---------------- 并行模块防御性调用 ---------------- */
  function callFx(name) {
    const m = NF.fx;
    if (!m || typeof m[name] !== 'function') return;
    const args = Array.prototype.slice.call(arguments, 1);
    try { m[name].apply(m, args); } catch (err) { /* 特效模块异常不影响玩法 */ }
  }
  function callSfx(name) {
    const a = NF.audio;
    if (!a || typeof a.sfx !== 'function') return;
    try { a.sfx(name); } catch (err) { /* ignore */ }
  }

  /* ---------------- 招式表 ----------------
   * dur        整招时长（秒）
   * cancelFrom 允许连段取消的时刻
   * chain      下一段连击名称
   * lunge/lungeFrom/lungeTo  攻击中的前冲
   * hits[]     命中窗口：from~to 之间每帧检测，每段对同一目标只命中一次
   *   dmg/stun/kb/power/shake/hitstop/score/gain/reach/z0/z1/launch/sfx/finisher
   */
  const MOVES = {
    punch1: {
      anim: 'punch1', dur: 4 / 14, chain: 'punch2',
      cancelFrom: 2.2 / 14, inputFrom: 0.8 / 14,
      lunge: 150, lungeFrom: 0.4 / 14, lungeTo: 2.6 / 14,
      hits: [{
        from: 0.85 / 14, to: 2.1 / 14,
        dmg: 6, stun: 0.25, kb: 70, power: 0.4,
        shake: 2.2, hitstop: cfg.HITSTOP_LIGHT, score: 100, gain: 6,
        reach: 32, z0: 12, z1: 168, sfx: 'hit'
      }]
    },
    punch2: {
      anim: 'punch2', dur: 4 / 14, chain: 'punch3',
      cancelFrom: 2.2 / 14, inputFrom: 0.8 / 14,
      lunge: 185, lungeFrom: 0.4 / 14, lungeTo: 2.6 / 14,
      hits: [{
        from: 0.85 / 14, to: 2.1 / 14,
        dmg: 8, stun: 0.28, kb: 104, power: 0.5,
        shake: 2.8, hitstop: 0.052, score: 100, gain: 7,
        reach: 38, z0: 12, z1: 168, sfx: 'hit'
      }]
    },
    punch3: {
      anim: 'punch3', dur: 5 / 12, chain: null,
      cancelFrom: 3.1 / 12, inputFrom: 0.9 / 12,
      lunge: 130, lungeFrom: 0.5 / 12, lungeTo: 3.2 / 12,
      hits: [{
        from: 1.6 / 12, to: 3.45 / 12,
        dmg: 14, stun: 0.4, kb: 170, launch: true, power: 0.82,
        shake: 5.2, hitstop: cfg.HITSTOP_HEAVY + 0.01, score: 100, gain: 9,
        reach: 32, z0: 0, z1: 190, sfx: 'hitHeavy'
      }]
    },
    heavy: {
      anim: 'kick', dur: 5 / 12, chain: null,
      cancelFrom: 3.2 / 12, inputFrom: 0.9 / 12,
      lunge: 200, lungeFrom: 0.5 / 12, lungeTo: 3.2 / 12,
      hits: [{
        from: 1.65 / 12, to: 3.35 / 12,
        dmg: 18, stun: 0.5, kb: 300, power: 0.95,
        shake: 6.2, hitstop: 0.1, score: 180, gain: 12,
        reach: 46, z0: 0, z1: 180, sfx: 'hitHeavy'
      }]
    },
    special: {
      anim: 'special', dur: 8 / 12, chain: null,
      cancelFrom: 99, inputFrom: 99,
      lunge: 95, lungeFrom: 0.6 / 12, lungeTo: 3.4 / 12,
      hits: [
        { from: 1.65 / 12, to: 2.5 / 12, dmg: 8, stun: 0.22, kb: 30, power: 0.6, shake: 3.2, hitstop: 0.04, score: 60, gain: 0, reach: 36, z0: 0, z1: 200, sfx: 'hit' },
        { from: 2.75 / 12, to: 3.6 / 12, dmg: 8, stun: 0.22, kb: 40, power: 0.66, shake: 3.6, hitstop: 0.04, score: 60, gain: 0, reach: 38, z0: 0, z1: 204, sfx: 'hit' },
        { from: 3.85 / 12, to: 4.7 / 12, dmg: 8, stun: 0.22, kb: 50, power: 0.72, shake: 4.0, hitstop: 0.045, score: 60, gain: 0, reach: 40, z0: 0, z1: 208, sfx: 'hit' },
        { from: 4.95 / 12, to: 5.8 / 12, dmg: 8, stun: 0.24, kb: 70, power: 0.8, shake: 4.6, hitstop: 0.05, score: 60, gain: 0, reach: 42, z0: 0, z1: 214, sfx: 'hit' },
        { from: 6.05 / 12, to: 7.2 / 12, dmg: 8, stun: 0.36, kb: 280, launch: true, power: 1, shake: 8, hitstop: 0.09, score: 60, gain: 0, reach: 46, z0: -20, z1: 230, sfx: 'hitHeavy', finisher: true }
      ]
    },
    /* 空中攻击（每次跳跃仅一次，用 punch2 帧） */
    air: {
      anim: 'punch2', dur: 4 / 14, chain: null,
      cancelFrom: 99, inputFrom: 0,
      hits: [{
        from: 0.5 / 14, to: 2.4 / 14,
        dmg: 10, stun: 0.3, kb: 120, power: 0.5,
        shake: 2.6, hitstop: 0.05, score: 100, gain: 5,
        reach: 44, z0: -30, z1: 170, sfx: 'hit'
      }]
    }
  };

  function makeHitSets(move) {
    const arr = [];
    for (let i = 0; i < move.hits.length; i++) arr.push(new Set());
    return arr;
  }

  /* ================================================================ */
  class Player {
    constructor() {
      this.maxHp = cfg.PLAYER_MAX_HP || 120;
      this.maxSpecial = cfg.MAX_SPECIAL || 100;
      this.halfW = BODY_HALF_W;
      this.depth = BODY_DEPTH;
      this.height = BODY_HEIGHT;
      this.reset(cfg.PLAYER_START_X, cfg.PLAYER_START_Y);
    }

    reset(x, y) {
      this.x = x == null ? cfg.PLAYER_START_X : x;
      this.y = y == null ? cfg.PLAYER_START_Y : y;
      this.z = 0;
      this.vx = 0; this.vy = 0; this.vz = 0;
      this.facing = 1;
      this.hp = this.maxHp;
      this.special = 0;
      this.state = 'idle';
      this.anim = 'idle';
      this.animTime = 0;
      this.move = null;
      this.moveName = '';
      this.moveTime = 0;
      this.hitDone = [];
      this.bufferAction = '';
      this.bufferTimer = 0;
      this.invuln = 0;
      this.flash = 0;
      this.hurtTimer = 0;
      this.koTimer = 0;
      this.airAttackUsed = false;
      this.airAttackT = -1;
      this.airAttackHits = [];
      this.alive = true;
      this.minX = 40;
      this.maxX = cfg.STAGE_W - 40;
      this.walkPhase = 0;
    }

    addSpecial(n) {
      this.special = U.clamp(this.special + n, 0, this.maxSpecial);
    }

    /** 命中停顿期间仍要吃掉攻击输入，保证连段缓冲手感（由 game 在 hitstop 时调用） */
    captureInput(inp) {
      if (!inp) return;
      if (inp.justPressed('attack')) this.setBuffer('attack');
      if (inp.justPressed('heavy')) this.setBuffer('heavy');
      if (inp.justPressed('special') && this.special >= this.maxSpecial) this.setBuffer('special');
    }

    /* 出招时自动朝向附近敌人（清版动作游戏的手感优化，避免打空气） */
    _autoFace() {
      const g = NF.game;
      if (!g || !g.enemies) return;
      let best = null;
      let bestD = 1e9;
      for (let i = 0; i < g.enemies.length; i++) {
        const e = g.enemies[i];
        if (!e || e.state === 'dead' || e.state === 'ko' || e.invuln > 0) continue;
        const dx = e.x - this.x;
        const dy = Math.abs(e.y - this.y);
        if (dy > 56) continue;
        const adx = Math.abs(dx);
        if (adx > 178 || adx < 2) continue;
        const d = adx + dy * 1.4;
        if (d < bestD) { bestD = d; best = e; }
      }
      if (best) this.facing = best.x >= this.x ? 1 : -1;
    }

    /* ---------------- 招式启动 ---------------- */
    startMove(name) {
      const m = MOVES[name];
      if (!m) return;
      if (name === 'special') {
        if (this.special < this.maxSpecial) return;
        this.special = 0;
        this.invuln = Math.max(this.invuln, 0.38); // 必杀起手短暂霸体
        const g = NF.game;
        if (g && typeof g.onSpecialStart === 'function') {
          try { g.onSpecialStart(this); } catch (err) { /* ignore */ }
        }
      }
      this._autoFace();
      if (name === 'heavy') callSfx('heavy');
      else if (name === 'special') callSfx('special');
      else callSfx('punch');

      this.state = 'attack';
      this.moveName = name;
      this.move = m;
      this.moveTime = 0;
      this.anim = m.anim;
      this.animTime = 0;
      this.hitDone = makeHitSets(m);
      this.bufferAction = '';
      this.bufferTimer = 0;
      this.vx = 0;
    }

    startJump() {
      if (this.z > 0) return;
      this.z = 0.01;
      this.vz = JUMP_VZ;
      this.state = 'jump';
      this.anim = 'jump';
      this.animTime = 0;
      this.airAttackUsed = false;
      this.airAttackT = -1;
      this.airAttackHits = [];
      this.move = null;
      this.moveName = '';
      callSfx('jump');
      callFx('dust', this.x, this.y, { power: 0.5 });
    }

    setBuffer(action) {
      this.bufferAction = action;
      this.bufferTimer = COMBO_BUFFER;
    }

    /* ---------------- 受击 / 死亡 ---------------- */
    takeHit(dmg, fromX, opts) {
      if (!this.alive || this.invuln > 0 || this.state === 'ko') return false;
      if (this.state === 'attack' && this.moveName === 'special') return false; // 必杀霸体
      opts = opts || {};
      this.hp = Math.max(0, this.hp - dmg);
      this.flash = 1;
      this.invuln = 0.6;
      this.bufferAction = ''; this.bufferTimer = 0;
      this.move = null; this.moveName = '';
      this.state = 'hurt';
      this.anim = 'hurt';
      this.animTime = 0;
      this.hurtTimer = opts.stun || 0.3;
      const dir = U.sign(this.x - fromX) || -this.facing;
      this.vx = dir * (opts.kb == null ? 150 : opts.kb);
      if (this.z > 0) this.vz = Math.min(this.vz, 120);
      if (this.hp <= 0) this._die();
      return true;
    }

    /** Boss 咆哮等无伤害推开 */
    knockbackFrom(fromX, strength) {
      if (!this.alive) return;
      this.vx = (U.sign(this.x - fromX) || 1) * (strength || 200);
      if (this.state === 'idle' || this.state === 'walk') {
        this.state = 'hurt';
        this.anim = 'hurt';
        this.animTime = 0;
        this.hurtTimer = 0.2;
      }
    }

    _die() {
      this.alive = false;
      this.state = 'ko';
      this.anim = 'ko';
      this.animTime = 0;
      this.vx = this.vx || -this.facing * 140;
      this.vz = Math.max(this.vz, 90);
      const g = NF.game;
      if (g && typeof g.onPlayerDeath === 'function') {
        try { g.onPlayerDeath(this); } catch (err) { /* ignore */ }
      }
    }

    /* ---------------- 调试/截图姿态 ---------------- */
    pose(animName, t, state) {
      this.anim = animName || 'idle';
      this.animTime = t || 0;
      this.move = null; this.moveName = ''; this.moveTime = 0;
      this.vx = 0; this.vy = 0;
      if (MOVES[animName]) {
        this.state = 'attack';
        this.moveName = animName;
        this.move = MOVES[animName];
        this.moveTime = t || 0;
        this.hitDone = makeHitSets(this.move);
      } else if (animName === 'jump') {
        this.state = 'jump';
      } else if (animName === 'hurt') {
        this.state = 'hurt'; this.hurtTimer = 0.3;
      } else if (animName === 'ko') {
        this.state = 'ko'; this.alive = false;
      } else if (animName === 'victory') {
        this.state = 'victory';
      } else {
        this.state = state || 'idle';
      }
    }

    /* ---------------- 每帧更新 ---------------- */
    update(dt) {
      const inp = NF.input;
      this.animTime += dt;
      if (this.flash > 0) this.flash = Math.max(0, this.flash - dt * 6.5);
      if (this.invuln > 0) this.invuln -= dt;
      if (this.bufferTimer > 0) this.bufferTimer -= dt;

      if (!this.alive || this.state === 'ko') { this._updateKO(dt); return; }
      if (this.state === 'victory') return;
      if (this.state === 'hurt') { this._updateHurt(dt); return; }
      if (this.state === 'attack') { this._updateAttack(dt, inp); return; }
      if (this.state === 'jump') { this._updateJump(dt, inp); return; }
      this._updateGround(dt, inp);
    }

    _clampX() {
      this.x = U.clamp(this.x, this.minX, this.maxX);
    }

    _updateGround(dt, inp) {
      /* 输入优先级：必杀 > 重击 > 跳跃 > 攻击 */
      if (inp.justPressed('special') && this.special >= this.maxSpecial) { this.startMove('special'); return; }
      if (inp.justPressed('heavy')) { this.startMove('heavy'); return; }
      if (inp.justPressed('jump')) { this.startJump(); return; }
      if (inp.justPressed('attack')) { this.startMove('punch1'); return; }

      const ax = inp.axisX();
      const ay = inp.axisY();
      let moving = false;
      if (Math.abs(ax) > 0.14) {
        this.facing = ax > 0 ? 1 : -1;
        this.x += ax * SPEED_X * dt;
        moving = true;
      }
      if (Math.abs(ay) > 0.14) {
        this.y += ay * SPEED_Y * dt;
        moving = true;
      }
      this._clampX();
      this.y = U.clamp(this.y, GROUND_TOP + 6, GROUND_BOTTOM);

      if (moving) {
        if (this.state !== 'walk') { this.state = 'walk'; this.anim = 'walk'; this.animTime = 0; }
        this.walkPhase += dt;
      } else if (this.state !== 'idle') {
        this.state = 'idle'; this.anim = 'idle'; this.animTime = 0;
      }
    }

    _updateJump(dt, inp) {
      /* z 物理（z 向上为正，vz 向上为正） */
      this.vz -= GRAVITY * dt;
      this.z += this.vz * dt;

      /* 空中控制 */
      const ax = inp.axisX();
      const ay = inp.axisY();
      if (Math.abs(ax) > 0.14) {
        this.facing = ax > 0 ? 1 : -1;
        this.x += ax * SPEED_X * AIR_MOVE * dt;
      }
      if (Math.abs(ay) > 0.14) this.y += ay * SPEED_Y * dt;
      this._clampX();
      this.y = U.clamp(this.y, GROUND_TOP + 6, GROUND_BOTTOM);

      /* 空中攻击（每次跳跃一次） */
      if (!this.airAttackUsed && (inp.justPressed('attack') || inp.justPressed('heavy'))) {
        this.airAttackUsed = true;
        this.airAttackT = 0;
        this.airAttackHits = makeHitSets(MOVES.air);
        this.anim = 'punch2';
        this.animTime = 0;
        callSfx('punch');
      }
      if (this.airAttackUsed && this.airAttackT >= 0) {
        this.airAttackT += dt;
        this._applyHits(NF.game, MOVES.air, this.airAttackT, this.airAttackHits);
        if (this.airAttackT >= MOVES.air.dur) {
          this.airAttackT = -1;
          this.anim = 'jump';
          this.animTime = 0.24;
        }
      }

      if (this.z <= 0 && this.vz < 0) this._land();
    }

    _land() {
      this.z = 0;
      this.vz = 0;
      this.state = 'idle';
      this.anim = 'idle';
      this.animTime = 0;
      this.airAttackUsed = false;
      this.airAttackT = -1;
      callSfx('land');
      callFx('dust', this.x, this.y, { power: 0.75 });
    }

    _updateHurt(dt) {
      this.hurtTimer -= dt;
      this.x += this.vx * dt;
      this.vx = U.damp(this.vx, 0, 10, dt);
      this._clampX();
      this.y = U.clamp(this.y, GROUND_TOP + 6, GROUND_BOTTOM);
      if (this.z > 0 || this.vz !== 0) {
        this.vz -= GRAVITY * dt;
        this.z += this.vz * dt;
        if (this.z <= 0) { this.z = 0; this.vz = 0; }
      }
      if (this.hurtTimer <= 0) {
        this.state = 'idle';
        this.anim = 'idle';
        this.animTime = 0;
      }
    }

    _updateKO(dt) {
      this.vx = U.damp(this.vx, 0, 6, dt);
      this.x += this.vx * dt;
      this._clampX();
      this.y = U.clamp(this.y, GROUND_TOP + 6, GROUND_BOTTOM);
      if (this.z > 0 || this.vz !== 0) {
        this.vz -= GRAVITY * dt;
        this.z += this.vz * dt;
        if (this.z <= 0) {
          this.z = 0;
          if (this.vz < -80) { this.vz = -this.vz * 0.3; } else { this.vz = 0; this.vx *= 0.5; }
        }
      }
      this.koTimer += dt;
    }

    _updateAttack(dt, inp) {
      const m = this.move;
      if (!m) { this.state = 'idle'; this.anim = 'idle'; return; }
      this.moveTime += dt;

      /* 连段输入缓冲 */
      if (inp.justPressed('attack')) this.setBuffer('attack');
      if (inp.justPressed('heavy')) this.setBuffer('heavy');
      if (inp.justPressed('special') && this.special >= this.maxSpecial) this.setBuffer('special');

      /* 前冲 */
      if (m.lunge && this.moveTime >= m.lungeFrom && this.moveTime <= m.lungeTo) {
        this.x += this.facing * m.lunge * dt;
        this._clampX();
      }

      /* 命中窗检测 */
      this._applyHits(NF.game, m, this.moveTime, this.hitDone);

      /* 连段取消 */
      if (this.bufferTimer > 0 && this.moveTime >= (m.cancelFrom == null ? 99 : m.cancelFrom)) {
        const a = this.bufferAction;
        if (a === 'attack' && m.chain) { this.startMove(m.chain); return; }
        if (a === 'heavy') { this.startMove('heavy'); return; }
        if (a === 'special' && this.special >= this.maxSpecial) { this.startMove('special'); return; }
      }

      if (this.moveTime >= m.dur) this._finishMove();
    }

    _applyHits(game, move, time, hitSets) {
      if (!game || typeof game.playerAttackHit !== 'function' || !move) return;
      for (let i = 0; i < move.hits.length; i++) {
        const h = move.hits[i];
        if (time >= h.from && time < h.to) {
          try { game.playerAttackHit(this, h, hitSets[i]); } catch (err) { /* ignore */ }
        }
      }
    }

    _finishMove() {
      this.move = null;
      this.moveName = '';
      this.moveTime = 0;
      if (this.bufferTimer > 0) {
        const a = this.bufferAction;
        if (a === 'attack') { this.startMove('punch1'); return; }
        if (a === 'heavy') { this.startMove('heavy'); return; }
        if (a === 'special' && this.special >= this.maxSpecial) { this.startMove('special'); return; }
      }
      this.state = 'idle';
      this.anim = 'idle';
      this.animTime = 0;
    }

    /* ---------------- 绘制（由 NF.game.draw 按脚底 y 排序调用） ---------------- */
    drawShadow(ctx) {
      const shrink = this.z > 0 ? U.clamp(1 - this.z / 260, 0.55, 1) : 1;
      NF.render.drawShadow(ctx, this.x, this.y, 64 * shrink, 0.34 * shrink);
    }

    drawSprite(ctx) {
      let alpha = 1;
      if (this.invuln > 0 && this.alive && this.state !== 'attack') {
        alpha = 0.58 + 0.42 * Math.abs(Math.sin(this.invuln * 42));
      }
      let scale = 1;
      if (this.state === 'attack' && this.moveName === 'special') {
        scale = 1 + 0.03 * Math.abs(Math.sin(this.moveTime * 36));
      }
      NF.render.drawCharAnim(ctx, 'hero', this.anim, this.animTime, this.x, this.y - this.z, {
        facing: this.facing,
        flash: this.flash,
        alpha: alpha,
        scale: scale
      });
    }
  }

  Player.MOVES = MOVES;
  NF.Player = Player;
})();
