/* 霓虹拳魂 NEON FIST SOUL — 敌人系统
 *
 * punk 混混 / brute 壮汉 / boss 铁面 IRON MASK
 *   - 纵深靠拢 / 绕位 / 前摇（带视觉预警）/ 攻击 / 硬直 / 受击 / 击飞 / KO
 *   - 同屏同时攻击的敌人 ≤ 2（由 NF.game.canEnemyAttack 分配攻击令牌）
 *   - 敌人之间保持间距，避免站位重叠；Boss 两套攻击 + 二阶段强化 + 咆哮
 *
 * 对外接口：
 *   NF.enemies.types
 *   NF.enemies.spawn(type, x, y, opts) -> Enemy
 *   Enemy: update(dt, game) / takeHit(hit, game) / pose(anim, t, state)
 *          drawShadow / drawSprite / drawTelegraph / drawHpBar
 */
window.NF = window.NF || {};

(function () {
  'use strict';

  const cfg = NF.config;
  const U = NF.util;

  const GROUND_TOP = cfg.GROUND_TOP;
  const GROUND_BOTTOM = cfg.GROUND_BOTTOM;
  const GRAVITY = 1650;

  function callFx(name) {
    const m = NF.fx;
    if (!m || typeof m[name] !== 'function') return;
    const args = Array.prototype.slice.call(arguments, 1);
    try { m[name].apply(m, args); } catch (err) { /* ignore */ }
  }
  function callSfx(name) {
    const a = NF.audio;
    if (!a || typeof a.sfx !== 'function') return;
    try { a.sfx(name); } catch (err) { /* ignore */ }
  }

  /* ---------------- 敌人类型表 ---------------- */
  const TYPES = {
    punk: {
      key: 'punk', char: 'punk', label: '混混',
      hp: 40, speed: 95, damage: 7, kb: 150, stun: 0.3,
      halfW: 22, depth: 18, height: 176,
      reach: 26, range: 78, standDist: 60,
      windup: 0.44, attackAnim: 'attack', attackFps: 10, attackDur: 4 / 10,
      hitFrom: 0.13, hitTo: 0.28, recover: 0.42,
      cooldown: [0.7, 1.4],
      dropChance: 0.25, score: 300,
      shadowW: 48, hpBarW: 42, koDur: 4 / 8,
      telegraphColor: '#ff8a2a'
    },
    brute: {
      key: 'brute', char: 'brute', label: '壮汉',
      hp: 95, speed: 62, damage: 16, kb: 240, stun: 0.42,
      halfW: 32, depth: 22, height: 216,
      reach: 32, range: 94, standDist: 74,
      windup: 0.64, attackAnim: 'attack', attackFps: 9, attackDur: 5 / 9,
      hitFrom: 0.2, hitTo: 0.4, recover: 0.62,
      cooldown: [1.1, 1.9],
      dropChance: 0.25, score: 300,
      shadowW: 64, hpBarW: 56, koDur: 4 / 7,
      telegraphColor: '#ff3b5c'
    },
    boss: {
      key: 'boss', char: 'boss', label: '铁面', boss: true,
      hp: 420, speed: 72, damage: 16, kb: 250, stun: 0.38,
      halfW: 42, depth: 26, height: 250,
      reach: 46, range: 126, standDist: 96,
      windup: 0.54, attackAnim: 'attack1', attackFps: 9, attackDur: 5 / 9,
      hitFrom: 0.18, hitTo: 0.37, recover: 0.68,
      cooldown: [1.25, 2.0],
      dropChance: 1, score: 5000,
      shadowW: 96, hpBarW: 0, koDur: 6 / 6,
      telegraphColor: '#ff2f8e',
      /* 冲拳（第二套攻击） */
      dashAnim: 'attack2', dashDamage: 22, dashKb: 320, dashStun: 0.45,
      dashSpeed: 560, dashRange: 640
    }
  };

  let UID = 1;

  /* ================================================================ */
  class Enemy {
    constructor(type, x, y, opts) {
      opts = opts || {};
      const def = TYPES[type] || TYPES.punk;
      this.def = def;
      this.type = def.key;
      this.uid = UID++;
      this.isBoss = !!def.boss;
      this.halfW = def.halfW;
      this.depth = def.depth;
      this.height = def.height;

      this.x = x;
      this.y = y;
      this.z = 0;
      this.vx = 0;
      this.vy = 0;
      this.vz = 0;
      this.facing = opts.facing || -1;

      this.maxHp = def.hp;
      this.hp = opts.hp != null ? U.clamp(opts.hp, 1, def.hp) : def.hp;

      this.state = opts.state || 'chase'; // chase/windup/attack/recover/hurt/knockdown/ko/dead/intro/roar
      this.anim = opts.state === 'intro' ? 'walk' : 'idle';
      this.animTime = Math.random() * 0.5;
      this.flash = 0;
      this.invuln = opts.invuln || (this.state === 'intro' ? 9 : 0);
      this.alpha = 1;
      this.dead = false;

      this.attackToken = false;
      this.cooldown = U.rand(0.5, 1.4);
      this.windupT = 0;
      this.windupDur = def.windup;
      this.attackT = 0;
      this.attackKind = 'basic';
      this.attackDef = null;
      this.didHit = false;
      this.recoverT = 0;
      this.hurtT = 0;
      this.lieT = 0;
      this.knockT = 0;
      this.koT = 0;
      this.introT = 0;
      this.roarT = 0;
      this.life = 0;
      this.stagger = 0;
      this.phase = 1;
      this.speedMul = 1;
      this.windups = 0;

      this.depthOffset = opts.depthOffset != null
        ? opts.depthOffset
        : U.choice([-20, -8, 12, 20]);
      this.side = opts.side || 1;
      this.roarCd = this.isBoss ? 12 : 0;
    }

    /* ---------------- 位置约束 ---------------- */
    _clampX(game) {
      const lock = game && typeof game.cameraLockX === 'number' ? game.cameraLockX : null;
      const minX = lock != null ? lock + 110 : 56;
      this.x = U.clamp(this.x, minX, cfg.STAGE_W - 90);
    }

    _clampY() {
      this.y = U.clamp(this.y, GROUND_TOP + 18, GROUND_BOTTOM - 4);
    }

    _releaseToken() {
      this.attackToken = false;
    }

    _setAnim(name) {
      if (this.anim !== name) {
        this.anim = name;
        this.animTime = 0;
      }
    }

    /* ---------------- 受击 ---------------- */
    takeHit(hit, game) {
      if (this.state === 'ko' || this.state === 'dead') return false;
      if (this.invuln > 0) return false;
      hit = hit || {};
      const dmg = Math.max(1, Math.round(hit.dmg || 1));
      this.hp -= dmg;
      this.flash = 1;
      const dir = hit.dir || (game && game.player && this.x < game.player.x ? 1 : -1);
      const heavy = !!hit.launch || (hit.kb || 0) >= 200;

      if (this.isBoss) {
        /* Boss 霸体：轻击只闪白不进硬直，累计伤害或重击才打断 */
        this.stagger += dmg;
        if (heavy) {
          this.stagger = 0;
          this._flinch(dir, hit, true);
        } else if (this.stagger >= 52) {
          this.stagger = 0;
          this._flinch(dir, hit, false);
        }
      } else {
        this._flinch(dir, hit, heavy);
      }

      if (this.hp <= 0) {
        this.hp = 0;
        this._die(game, dir, hit);
      }
      return true;
    }

    _flinch(dir, hit, launch) {
      this._releaseToken();
      this.state = launch ? 'knockdown' : 'hurt';
      this.knockT = 0;
      this.lieT = 0;
      this.anim = launch ? 'ko' : 'hurt';
      this.animTime = 0;
      const kb = hit.kb == null ? 140 : hit.kb;
      if (this.isBoss) {
        /* Boss 不会被击飞，只有强力硬直 */
        this.state = 'hurt';
        this.anim = 'hurt';
        this.hurtT = launch ? 0.3 : 0.32;
        this.vx = dir * Math.min(kb, 190) * 0.32;
        this.vz = 0;
      } else if (launch) {
        this.vz = 290;
        this.vx = dir * kb * 0.85;
        this.hurtT = 0;
      } else {
        this.hurtT = hit.stun || 0.28;
        this.vx = dir * kb;
      }
    }

    _die(game, dir, hit) {
      this.state = 'ko';
      this.anim = 'ko';
      this.animTime = 0;
      this.koT = 0;
      this.flash = 0.9;
      this._releaseToken();
      this.attackDef = null;
      this.vx = dir * (hit && hit.launch ? 250 : 170);
      this.vz = hit && hit.launch ? 250 : 110;
      this.z = Math.max(this.z, 1);
      if (game && typeof game.onEnemyKilled === 'function') {
        try { game.onEnemyKilled(this, hit); } catch (err) { /* ignore */ }
      }
    }

    /* ---------------- 每帧更新 ---------------- */
    update(dt, game) {
      this.life += dt;
      this.animTime += dt;
      if (this.flash > 0) this.flash = Math.max(0, this.flash - dt * 5.5);
      if (this.invuln > 0) this.invuln -= dt;
      if (this.cooldown > 0) this.cooldown -= dt;
      if (this.isBoss && this.phase === 2 && this.roarCd > 0) this.roarCd -= dt;

      switch (this.state) {
        case 'dead': return;
        case 'ko': this._updateKO(dt, game); return;
        case 'hurt': this._updateHurt(dt, game); return;
        case 'knockdown': this._updateKnockdown(dt, game); return;
        case 'intro': this._updateIntro(dt, game); return;
        case 'roar': this._updateRoar(dt, game); return;
        case 'windup': this._updateWindup(dt, game); return;
        case 'attack': this._updateAttack(dt, game); return;
        case 'recover': this._updateRecover(dt, game); return;
        default: this._think(dt, game);
      }
    }

    _physics(dt) {
      this.x += this.vx * dt;
      this.vx = U.damp(this.vx, 0, 8, dt);
      /* z 向上为正、vz 向上为正 */
      if (this.z > 0 || this.vz !== 0) {
        this.vz -= GRAVITY * dt;
        this.z += this.vz * dt;
        if (this.z <= 0) {
          this.z = 0;
          if (this.vz < -140) { this.vz = -this.vz * 0.34; } else { this.vz = 0; this.vx *= 0.55; }
        }
      }
      /* 安全钳制：异常 z 直接落地，避免实体飞出可攻击范围 */
      if (!isFinite(this.z) || this.z > 420) { this.z = 0; this.vz = 0; }
      this._clampY();
    }

    _updateHurt(dt, game) {
      this.hurtT -= dt;
      this._physics(dt);
      this._clampX(game);
      if (this.hurtT <= 0) {
        this.state = 'chase';
        this._setAnim('idle');
        this.cooldown = Math.max(this.cooldown, 0.28);
      }
    }

    _updateKnockdown(dt, game) {
      this.knockT += dt;
      this._physics(dt);
      this._clampX(game);
      if (this.z <= 0 && this.vz === 0) {
        this.lieT += dt;
        if (this.anim !== 'ko') this._setAnim('ko');
        if (this.lieT > 0.62) {
          /* 起身 */
          this.state = 'chase';
          this.anim = 'idle';
          this.animTime = 0;
          this.invuln = Math.max(this.invuln, 0.22);
          this.cooldown = Math.max(this.cooldown, 0.4);
        }
      } else if (this.anim !== 'ko') {
        this._setAnim('ko');
      }
    }

    _updateKO(dt, game) {
      this.koT += dt;
      this._physics(dt);
      this._clampX(game);
      const wait = this.def.koDur + (this.isBoss ? 1.2 : 0.75);
      if (this.koT > wait) {
        this.alpha = Math.max(0, 1 - (this.koT - wait) / 0.4);
        if (this.koT > wait + 0.42) {
          this.alpha = 0;
          this.state = 'dead';
        }
      }
    }

    _updateIntro(dt, game) {
      this.introT += dt;
      const p = game.player;
      if (p) this.facing = p.x >= this.x ? 1 : -1;
      /* 缓步走进场，保持压迫感 */
      const targetX = (p ? p.x : this.x - 300) + 230;
      if (Math.abs(targetX - this.x) > 30) {
        this.x += U.sign(targetX - this.x) * this.speedMul * 62 * dt;
        this._setAnim('walk');
      } else {
        this._setAnim('idle');
      }
      this._clampX(game);
      if (this.introT > 2.3) {
        this.state = 'chase';
        this.invuln = Math.max(this.invuln, 0.2);
        this.cooldown = 0.6;
      }
    }

    _updateRoar(dt, game) {
      this.roarT += dt;
      if (!this.roarDone && this.roarT > 0.42) {
        this.roarDone = true;
        const p = game.player;
        if (p && p.knockbackFrom && Math.abs(p.x - this.x) < 380 && Math.abs(p.y - this.y) < 90) {
          p.knockbackFrom(this.x, 240);
        }
        callFx('shake', 10, 0.6);
        callFx('dust', this.x, this.y, { power: 1 });
      }
      if (this.roarT > 1.15) {
        this.state = 'chase';
        this.anim = 'idle';
        this.animTime = 0;
        this.roarDone = false;
        this.cooldown = Math.max(this.cooldown, 0.55);
      }
    }

    _startRoar(game) {
      this.state = 'roar';
      this.roarT = 0;
      this.roarDone = false;
      this.roarCd = U.rand(12, 17);
      this.anim = 'roar';
      this.animTime = 0;
      this.invuln = Math.max(this.invuln, 1.1);
      this._releaseToken();
      this.attackDef = null;
      callSfx('roar');
      callFx('flash', '#ff2f8e', 0.36, 0.35);
      callFx('shake', 8, 0.5);
      if (game && typeof game.onBossRoar === 'function') {
        try { game.onBossRoar(this); } catch (err) { /* ignore */ }
      }
    }

    /* ---------------- AI ---------------- */
    _think(dt, game) {
      const p = game.player;
      if (!p || !p.alive) {
        this._setAnim('idle');
        return;
      }
      const def = this.def;
      const dx = p.x - this.x;
      const dy = p.y - this.y;
      const adx = Math.abs(dx);
      const ady = Math.abs(dy);

      if (this.isBoss && this.phase === 1 && this.hp <= this.maxHp * 0.5) {
        this._enterPhase2(game);
        return;
      }
      if (this.isBoss && this.phase === 2 && this.roarCd <= 0 && adx > 120) {
        this._startRoar(game);
        return;
      }

      this.facing = dx >= 0 ? 1 : -1;

      const ready = this.cooldown <= 0;
      if (this.isBoss) {
        if (ready && ady <= 48 && game.canEnemyAttack(this)) {
          const close = adx <= 128;
          const far = adx > 160 && adx < def.dashRange;
          if (close || far) { this._startWindup(game); return; }
        }
      } else if (ready && adx <= def.range && ady <= 30 && game.canEnemyAttack(this)) {
        this._startWindup(game);
        return;
      }

      /* 站位：绕着玩家侧面保持攻击距离 */
      const side = this.x >= p.x ? 1 : -1;
      const standDist = this.isBoss ? 92 : def.standDist;
      let targetX = p.x + side * standDist;
      let targetY = p.y + this.depthOffset;
      /* 冷却中/等令牌时轻微游走，制造压迫感 */
      if (this.cooldown > 0 && adx < def.range + 26) {
        targetY += Math.sin(this.life * 1.9 + this.uid * 0.7) * 26;
      }
      this._moveToward(dt, game, targetX, targetY);
    }

    _startWindup(game) {
      const def = this.def;
      const p = game.player;
      this.state = 'windup';
      this.windupT = 0;
      this.windups++;
      this.attackToken = true;
      this.vx = 0;
      const dx = p ? p.x - this.x : this.facing;
      this.facing = dx >= 0 ? 1 : -1;
      if (this.isBoss) {
        const close = Math.abs(dx) <= 150;
        this.attackKind = close ? 'sweep' : 'dash';
        const base = this.attackKind === 'dash' ? 0.72 : 0.5;
        this.windupDur = base * (this.phase === 2 ? 0.74 : 1);
      } else {
        this.attackKind = 'basic';
        this.windupDur = def.windup * U.rand(0.9, 1.15) * (this.phase === 2 ? 0.85 : 1);
      }
      this.anim = 'idle';
      this.animTime = 0;
      callFx('text', this.x, this.y - this.height - 14, '!', {
        color: def.telegraphColor, size: 20, life: 0.5
      });
    }

    _updateWindup(dt, game) {
      this.windupT += dt;
      const p = game.player;
      if (p) this.facing = p.x >= this.x ? 1 : -1;
      if (this.isBoss && this.attackKind === 'dash') {
        /* 冲拳前摇时向后蓄力 */
        if (this.windupT < this.windupDur * 0.7) {
          this.x -= this.facing * 22 * dt;
          this._clampX(game);
        }
      }
      if (this.windupT >= this.windupDur) this._startAttack(game);
    }

    _startAttack(game) {
      const def = this.def;
      const isDash = this.attackKind === 'dash';
      this.state = 'attack';
      this.attackT = 0;
      this.didHit = false;
      this.attackToken = true;
      this.anim = isDash ? (def.dashAnim || 'attack2') : def.attackAnim;
      this.animTime = 0;
      this.attackDef = {
        kind: isDash ? 'dash' : 'basic',
        damage: Math.round((isDash ? def.dashDamage : def.damage) * (this.phase === 2 ? 1.1 : 1)),
        kb: isDash ? def.dashKb : def.kb,
        stun: isDash ? def.dashStun : def.stun,
        reach: def.reach + (isDash ? 12 : (this.isBoss ? 12 : 0)),
        sfx: (isDash || def.damage >= 14) ? 'hitHeavy' : 'hit'
      };
      if (isDash) {
        callSfx('dash');
        callFx('dust', this.x, this.y, { power: 0.7 });
      } else {
        callSfx(def.damage >= 14 ? 'heavy' : 'punch');
      }
    }

    _hitWindow() {
      const d = this.def;
      if (this.attackKind === 'dash') return { from: 0.12, to: 0.4 };
      return { from: d.hitFrom, to: d.hitTo };
    }

    _attackDuration() {
      const d = this.def;
      return this.attackKind === 'dash' ? 0.56 : d.attackDur;
    }

    _updateAttack(dt, game) {
      const d = this.def;
      this.attackT += dt;

      if (this.attackKind === 'dash') {
        const t = this.attackT;
        if (t > 0.07 && t < 0.34) {
          this.x += this.facing * d.dashSpeed * this.speedMul * dt;
          this._clampX(game);
          if (Math.random() < 0.45) {
            callFx('dust', this.x - this.facing * 26, this.y, { power: 0.45 });
          }
        }
      }

      const win = this._hitWindow();
      if (!this.didHit && this.attackT >= win.from && this.attackT <= win.to) {
        if (this.attackDef && game.enemyAttackHit(this, this.attackDef)) this.didHit = true;
      }

      if (this.attackT >= this._attackDuration()) {
        this.state = 'recover';
        this.recoverT = d.recover * (this.phase === 2 ? 0.8 : 1);
        const cd = d.cooldown;
        this.cooldown = U.rand(cd[0], cd[1]) * (this.phase === 2 ? 0.62 : 1);
        this._releaseToken();
        this.attackDef = null;
        this._setAnim('idle');
      }
    }

    _updateRecover(dt, game) {
      this.recoverT -= dt;
      if (this.recoverT <= 0) {
        this.state = 'chase';
        this._setAnim('idle');
      }
    }

    _enterPhase2(game) {
      this.phase = 2;
      this.speedMul = 1.3;
      this.stagger = 0;
      this.invuln = Math.max(this.invuln, 0.4);
      callFx('flash', '#ff2f8e', 0.5, 0.5);
      callFx('shake', 12, 0.8);
      callSfx('roar');
      if (game && typeof game.onBossPhase2 === 'function') {
        try { game.onBossPhase2(this); } catch (err) { /* ignore */ }
      }
      this._startRoar(game);
    }

    _moveToward(dt, game, tx, ty) {
      const def = this.def;
      const sp = def.speed * this.speedMul;
      let moving = false;

      const ddx = tx - this.x;
      if (Math.abs(ddx) > 5) {
        this.x += U.sign(ddx) * Math.min(sp * dt, Math.abs(ddx));
        moving = true;
      }
      const ddy = ty - this.y;
      if (Math.abs(ddy) > 2.5) {
        this.y += U.sign(ddy) * Math.min(sp * 0.6 * dt, Math.abs(ddy));
        moving = true;
      }

      /* 与其他敌人分离，避免站位重叠 */
      const sep = this._separation(game);
      this.x += sep.x * dt;
      this.y += sep.y * dt;

      /* 不与玩家重叠 */
      const p = game.player;
      if (p) {
        const minDX = this.halfW + p.halfW - 4;
        if (Math.abs(this.y - p.y) < 32 && Math.abs(this.x - p.x) < minDX) {
          const dir = U.sign(this.x - p.x) || this.facing;
          this.x = p.x + dir * minDX;
        }
      }

      this._clampX(game);
      this._clampY();
      if (moving) this._setAnim('walk');
      else this._setAnim('idle');
    }

    _separation(game) {
      let sx = 0;
      let sy = 0;
      const list = game.enemies;
      for (let i = 0; i < list.length; i++) {
        const o = list[i];
        if (!o || o === this || o.state === 'dead' || o.state === 'ko') continue;
        const dx = this.x - o.x;
        const dy = this.y - o.y;
        const d2 = dx * dx + dy * dy * 2.2;
        const R = this.isBoss ? 74 : 58;
        if (d2 < R * R && d2 > 0.01) {
          const d = Math.sqrt(d2);
          const f = (R - d) / R;
          sx += (dx / d) * f * 150;
          sy += (dy / d) * f * 130;
        }
      }
      return { x: sx, y: sy };
    }

    /* ---------------- 调试/截图姿态 ---------------- */
    pose(animName, t, state) {
      this.anim = animName || 'idle';
      this.animTime = t || 0;
      if (state) this.state = state;
      if (animName === 'ko') this.state = 'ko';
      else if (animName === 'hurt') this.state = 'hurt';
      else if (animName === 'walk') this.state = 'chase';
    }

    /* ---------------- 绘制 ---------------- */
    drawShadow(ctx) {
      const shrink = this.z > 0 ? U.clamp(1 - this.z / 300, 0.5, 1) : 1;
      NF.render.drawShadow(ctx, this.x, this.y, this.def.shadowW * shrink, 0.3 * shrink);
    }

    drawSprite(ctx) {
      if (this.alpha <= 0) return;
      let alpha = this.alpha;
      if (this.state === 'intro') alpha *= 0.95;
      NF.render.drawCharAnim(ctx, this.def.char, this.anim, this.animTime, this.x, this.y - this.z, {
        facing: this.facing,
        flash: this.flash,
        alpha: alpha
      });
    }

    /** 前摇预警 / Boss 二阶段气场（世界空间、脚底附近） */
    drawTelegraph(ctx) {
      if (this.state === 'windup') {
        const k = U.clamp01(this.windupT / Math.max(0.001, this.windupDur));
        const col = this.def.telegraphColor;
        ctx.save();
        ctx.globalAlpha = 0.35 + 0.3 * Math.abs(Math.sin(this.life * 26));
        ctx.strokeStyle = col;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(this.x, this.y, this.halfW * 1.75, this.halfW * 0.62, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 0.95;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.ellipse(this.x, this.y, this.halfW * 1.95, this.halfW * 0.7, 0, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * k);
        ctx.stroke();
        if (this.attackKind === 'dash') {
          ctx.globalAlpha = 0.28 + 0.22 * Math.abs(Math.sin(this.life * 22));
          ctx.fillStyle = col;
          const len = 420;
          ctx.fillRect(this.facing > 0 ? this.x : this.x - len, this.y - 8, len, 6);
        }
        ctx.restore();
      }
      if (this.isBoss && this.phase === 2 && (this.state === 'chase' || this.state === 'windup')) {
        ctx.save();
        ctx.globalAlpha = 0.22 + 0.16 * Math.abs(Math.sin(this.life * 8));
        ctx.strokeStyle = '#ff2f8e';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(this.x, this.y - 4, this.halfW * 1.6, this.halfW * 0.5, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha *= 0.5;
        ctx.strokeStyle = '#3df3ff';
        ctx.beginPath();
        ctx.ellipse(this.x, this.y - 4, this.halfW * 2.1, this.halfW * 0.66, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }

    drawHpBar(ctx) {
      if (this.isBoss) return;
      if (this.state === 'ko' || this.state === 'dead') return;
      if (this.hp >= this.maxHp) return;
      const w = this.def.hpBarW;
      const h = 4;
      const x = Math.round(this.x - w / 2);
      const y = Math.round(this.y - this.z - this.height - 16);
      ctx.save();
      ctx.fillStyle = 'rgba(8,4,16,0.78)';
      ctx.fillRect(x - 1, y - 1, w + 2, h + 2);
      ctx.fillStyle = '#3b1030';
      ctx.fillRect(x, y, w, h);
      const ratio = U.clamp01(this.hp / this.maxHp);
      ctx.fillStyle = ratio < 0.34 ? '#ff3b5c' : '#ff8a2a';
      ctx.fillRect(x, y, Math.round(w * ratio), h);
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.fillRect(x, y, Math.round(w * ratio), 1);
      ctx.restore();
    }
  }

  NF.enemies = {
    types: TYPES,
    Enemy: Enemy,
    spawn(type, x, y, opts) {
      return new Enemy(type, x, y, opts);
    },
    /* 兼容占位接口 */
    update() {},
    draw() {}
  };
})();
