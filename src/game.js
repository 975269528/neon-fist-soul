/* 霓虹拳魂 NEON FIST SOUL — 游戏状态机 / 波次 / 战斗规则 / 绘制
 *
 * 对外接口（主循环调用）：
 *   NF.game.init() / update(dt) / draw(ctx) / togglePause() / debugStart(name)
 *   NF.game.state  'title' | 'playing' | 'paused' | 'gameover' | 'victory'
 *
 * HUD 依赖字段全部在此维护（见 DEV_CONTRACT §2.12）：
 *   player(hp,maxHp,special,maxSpecial,x,y,facing,alive,anim)
 *   state/time/score/highScore/wave/totalWaves/combo/comboTimer/maxCombo/kills
 *   banner {label,sub,timer,max,kind} / boss {name,hp,maxHp,active,phase}
 *   cameraLockX / gameoverReason / shotFrozen
 *
 * 本文件只画「世界空间」内容；屏幕空间 UI 由 NF.hud 绘制。
 */
window.NF = window.NF || {};

(function () {
  'use strict';

  const cfg = NF.config;
  const U = NF.util;
  const STAGE = cfg.STAGE || {};
  const WAVES = Array.isArray(STAGE.waves) ? STAGE.waves : [];
  const GROUND_TOP = cfg.GROUND_TOP;
  const GROUND_BOTTOM = cfg.GROUND_BOTTOM;
  const HS_KEY = 'neon_fist_soul_high_score_v1';

  /* ---------------- 并行模块防御性调用 ---------------- */
  function callFx(name) {
    const m = NF.fx;
    if (!m || typeof m[name] !== 'function') return;
    const args = Array.prototype.slice.call(arguments, 1);
    try { m[name].apply(m, args); } catch (err) { /* 特效异常不影响玩法 */ }
  }
  function callSfx(name) {
    const a = NF.audio;
    if (!a || typeof a.sfx !== 'function') return;
    try { a.sfx(name); } catch (err) { /* ignore */ }
  }
  function callMusic(scene) {
    const a = NF.audio;
    if (!a || typeof a.music !== 'function') return;
    try { a.music(scene); } catch (err) { /* ignore */ }
  }
  function callHudToast(text) {
    const h = NF.hud;
    if (!h || typeof h.toast !== 'function') return;
    try { h.toast(text); } catch (err) { /* ignore */ }
  }

  const game = {
    /* ---------------- 状态 ---------------- */
    state: 'title',
    time: 0,
    shotFrozen: false,

    /* 实体 */
    player: null,
    enemies: [],
    pickups: [],

    /* 计分 / 连击 / 统计 */
    score: 0,
    highScore: 0,
    wave: 0,
    totalWaves: Math.max(1, WAVES.length),
    combo: 0,
    comboTimer: 0,
    comboMaxTime: 2.2,
    maxCombo: 0,
    kills: 0,

    /* HUD 字段 */
    banner: null,
    boss: null,
    cameraLockX: undefined,
    gameoverReason: '',

    /* 手感 */
    hitstop: 0,
    slowmo: 0,
    slowmoScale: 0.34,

    /* 流程计时 */
    runTime: 0,
    endTimer: 0,

    /* 波次 */
    waveIndex: -1,
    wavePhase: 'idle', // idle | fighting | cleared | intro
    waveClearTimer: 0,
    waveAdvanceTimer: 0,
    promptTimer: 0,

    /* 结算序列 */
    victoryPending: false,
    victoryTimer: 0,
    deathPending: false,
    deathTimer: 0,

    /* 自检标记（仅开发调试） */
    _selftestSawBoss: 0,
    _selftestSawPhase2: 0,
    _selftestSawRoar: 0,
    _selftestSawBanner: 0,

    /* ================================================================ */
    init() {
      this.highScore = this._loadHighScore();
      this.totalWaves = Math.max(1, WAVES.length);
      this.player = new NF.Player();
      this.resetRun();
      this.state = 'title';
      callMusic('title');
      if (NF.hud && typeof NF.hud.init === 'function') {
        try { NF.hud.init(); } catch (err) { /* ignore */ }
      }
      /* 仅开发自检：?selftest=1[&mode=victory|gameover]（无头验证完整流程用） */
      try {
        const q = new URLSearchParams(location.search);
        if (q.get('selftest')) {
          this._selftestRun(q.get('mode') || 'victory');
        }
      } catch (err) { /* ignore */ }
    },

    _loadHighScore() {
      try {
        const v = parseInt(localStorage.getItem(HS_KEY) || '0', 10);
        return Number.isFinite(v) && v > 0 ? v : 0;
      } catch (err) { return 0; }
    },

    saveHighScore() {
      try {
        this.highScore = Math.max(this.highScore, this.score);
        localStorage.setItem(HS_KEY, String(Math.floor(this.highScore)));
      } catch (err) { /* file:// 下可能不可用，忽略 */ }
    },

    /* ---------------- 生命周期 ---------------- */
    resetRun() {
      this.enemies.length = 0;
      this.pickups.length = 0;
      this.score = 0;
      this.wave = 0;
      this.combo = 0;
      this.comboTimer = 0;
      this.maxCombo = 0;
      this.kills = 0;
      this.banner = null;
      this.boss = null;
      this.cameraLockX = undefined;
      this.gameoverReason = '';
      this.hitstop = 0;
      this.slowmo = 0;
      this.slowmoScale = 0.34;
      this.runTime = 0;
      this.endTimer = 0;
      this.waveIndex = -1;
      this.wavePhase = 'idle';
      this.waveClearTimer = 0;
      this.waveAdvanceTimer = 0;
      this.promptTimer = 0;
      this.victoryPending = false;
      this.victoryTimer = 0;
      this.deathPending = false;
      this.deathTimer = 0;
      this._selftestSawBoss = 0;
      this._selftestSawPhase2 = 0;
      this._selftestSawRoar = 0;
      this._selftestSawBanner = 0;
      if (this.player) this.player.reset(cfg.PLAYER_START_X, cfg.PLAYER_START_Y);
      if (NF.camera && typeof NF.camera.reset === 'function') {
        try { NF.camera.reset(0); } catch (err) { /* ignore */ }
      }
      if (NF.fx && typeof NF.fx.clear === 'function') {
        try { NF.fx.clear(); } catch (err) { /* ignore */ }
      }
    },

    toTitle() {
      this.resetRun();
      this.state = 'title';
      if (this.player) { this.player.anim = 'idle'; this.player.animTime = 0; }
      callMusic('title');
    },

    startRun() {
      this.resetRun();
      this.state = 'playing';
      this.spawnWave(0);
    },

    togglePause() {
      if (this.state === 'playing') {
        this.state = 'paused';
        callMusic('none');
      } else if (this.state === 'paused') {
        this.state = 'playing';
        this._resumeMusic();
      }
    },

    _resumeMusic() {
      callMusic(this.boss ? 'boss' : 'battle');
    },

    /* ---------------- 主更新 ---------------- */
    update(dt) {
      const inp = NF.input;
      const realDt = U.clamp(dt || 0, 0, 0.05);
      this.time += realDt;

      /* 截图冻结：只推进 HUD 时间（this.time），实体完全静止，保证可复现 */
      if (this.shotFrozen) return;

      if (inp.justPressed('pause') && (this.state === 'playing' || this.state === 'paused')) {
        this.togglePause();
        return;
      }

      switch (this.state) {
        case 'title': this._updateTitle(realDt, inp); return;
        case 'paused': this._updatePaused(realDt, inp); return;
        case 'gameover':
        case 'victory': this._updateEnding(realDt, inp); return;
        case 'playing': this.updatePlaying(realDt); return;
        default: return;
      }
    },

    _updateTitle(dt, inp) {
      if (this.player) {
        this.player.anim = 'idle';
        this.player.animTime += dt;
      }
      this.updateBanner(dt);
      if (inp.justPressed('start') || inp.tapped) {
        callSfx('start');
        this.startRun();
      }
    },

    _updatePaused(dt, inp) {
      if (inp.justPressed('start')) { this.togglePause(); return; }
      if (inp.justPressed('restart')) { this.startRun(); return; }
    },

    _updateEnding(dt, inp) {
      this.endTimer += dt;
      this.updateBanner(dt);
      if (this.player && this.player.state === 'victory') this.player.animTime += dt;
      if (this.endTimer > 0.85 && (inp.justPressed('start') || inp.tapped)) {
        this.toTitle();
      }
    },

    updateBanner(dt) {
      if (!this.banner) return;
      this.banner.timer -= dt;
      if (this.banner.timer <= 0) this.banner = null;
    },

    updatePlaying(dt) {
      this.runTime += dt;
      this.updateBanner(dt);

      if (this.comboTimer > 0) {
        this.comboTimer -= dt;
        if (this.comboTimer <= 0) { this.comboTimer = 0; this.combo = 0; }
      }

      /* 命中停顿：实体完全冻结，只留特效继续播；但输入仍要缓冲，连段才顺 */
      if (this.hitstop > 0) {
        this.hitstop -= dt;
        if (this.player && typeof this.player.captureInput === 'function') {
          this.player.captureInput(NF.input);
        }
        return;
      }

      /* 慢镜（KO / 必杀终结 / Boss 死亡） */
      let scale = 1;
      if (this.slowmo > 0) {
        this.slowmo -= dt;
        scale = this.slowmoScale;
      }
      const sdt = dt * scale;
      const p = this.player;

      /* 玩家活动范围：Boss 战锁在竞技场内 */
      if (p) {
        if (typeof this.cameraLockX === 'number') {
          p.minX = this.cameraLockX + 120;
          p.maxX = cfg.STAGE_W - 70;
        } else {
          p.minX = 40;
          p.maxX = cfg.STAGE_W - 40;
        }
        try { p.update(sdt); } catch (err) { console.error(err); }
      }

      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (!e || e.state === 'dead') continue;
        try { e.update(sdt, this); } catch (err) { console.error(err); }
      }

      this.resolveBodies();
      this.updatePickups(sdt);
      this.cleanupEntities();
      this.updateBossState();
      this.checkWaves(dt);
      this.checkSequences(dt);
    },

    /* ---------------- 波次 ---------------- */
    spawnWave(index) {
      const w = WAVES[index];
      if (!w) return;
      this.waveIndex = index;
      this.wave = index + 1;
      this.wavePhase = 'fighting';
      this.waveClearTimer = 0;
      this.waveAdvanceTimer = 0;
      this.promptTimer = 0;
      this._selftestSawBanner = 1;
      const isBoss = !!w.boss;
      this.banner = {
        label: w.label || ('WAVE ' + this.wave),
        sub: isBoss ? '铁面 IRON MASK' : (w.count + ' 名敌人'),
        timer: isBoss ? 2.8 : 1.9,
        max: isBoss ? 2.8 : 1.9,
        kind: isBoss ? 'boss' : 'wave'
      };
      if (isBoss) {
        this.cameraLockX = typeof STAGE.bossLockCameraX === 'number'
          ? STAGE.bossLockCameraX
          : (cfg.STAGE_W - cfg.VIEW_W);
        this._spawnBoss(w);
        callMusic('boss');
      } else {
        this._spawnEnemies(w);
        callMusic(this.boss ? 'boss' : 'battle');
      }
      callSfx('wave');
    },

    _spawnEnemies(w) {
      const p = this.player;
      if (!p) return;
      const types = (w.types || []).slice(0, 6);
      for (let i = 0; i < types.length; i++) {
        const type = types[i];
        const side = i % 2 === 0 ? 1 : -1;
        let sx = p.x + side * (470 + Math.floor(i / 2) * 64 + U.rand(0, 50));
        sx = U.clamp(sx, 80, cfg.STAGE_W - 90);
        if (Math.abs(sx - p.x) < 290) {
          sx = U.clamp(p.x - side * 470, 80, cfg.STAGE_W - 90);
        }
        const sy = U.clamp(p.y + U.rand(-64, 64), GROUND_TOP + 24, GROUND_BOTTOM - 8);
        const enemy = NF.enemies.spawn(type, sx, sy, {
          side: side,
          facing: sx > p.x ? -1 : 1,
          depthOffset: ((i % 3) - 1) * 20 + U.rand(-5, 5)
        });
        if (enemy) this.enemies.push(enemy);
      }
    },

    _spawnBoss(w) {
      const p = this.player;
      const bx = U.clamp((STAGE.bossArenaX || 2540) + 360, 2000, cfg.STAGE_W - 150);
      const by = U.clamp(p ? p.y : 470, GROUND_TOP + 34, GROUND_BOTTOM - 12);
      const boss = NF.enemies.spawn('boss', bx, by, {
        side: 1, facing: -1, state: 'intro', invuln: 9, depthOffset: 0
      });
      if (boss) {
        boss.x = bx;
        boss.y = by;
        this.enemies.push(boss);
      }
      this._selftestSawBoss = 1;
      this.boss = {
        name: '铁面 IRON MASK',
        title: '后巷霸主',
        hp: boss ? boss.hp : 420,
        maxHp: boss ? boss.maxHp : 420,
        active: true,
        phase: 1
      };
    },

    _showAdvancePrompt(dt) {
      this.promptTimer -= dt;
      if (this.promptTimer > 0) return;
      this.promptTimer = 5.5;
      this.banner = { label: '前进', sub: '向右推进 →', timer: 2.2, max: 2.2, kind: 'hint' };
      callSfx('ui');
    },

    checkWaves(dt) {
      if (this.deathPending || this.victoryPending) return;

      if (this.wavePhase === 'fighting') {
        let alive = 0;
        for (let i = 0; i < this.enemies.length; i++) {
          const e = this.enemies[i];
          if (!e || e.state === 'dead' || e.state === 'ko') continue;
          alive++;
        }
        if (alive > 0) return;
        const w = WAVES[this.waveIndex];
        if (w && w.boss) return; // Boss 死亡由 onEnemyKilled → _beginVictory 接管
        this.wavePhase = 'cleared';
        this.waveClearTimer = 0;
        this.waveAdvanceTimer = 0;
        this.banner = null;
        this.addScore(200 + this.wave * 100);
        callSfx('wave');
        callHudToast('WAVE CLEAR');
        return;
      }

      if (this.wavePhase === 'cleared') {
        this.waveClearTimer += dt;
        this.waveAdvanceTimer += dt;
        const nextIdx = this.waveIndex + 1;
        const nextW = WAVES[nextIdx];
        if (!nextW || !this.player) return;
        if (nextW.boss) {
          /* Boss 战：必须推进到竞技场才触发（摄像机锁定） */
          if (this.player.x >= nextW.at - 40) {
            this.spawnWave(nextIdx);
          } else if (this.waveClearTimer > 1.2) {
            this._showAdvancePrompt(dt);
          }
        } else if (this.waveClearTimer > 0.9 &&
          (this.player.x >= nextW.at || this.waveAdvanceTimer > 3.8)) {
          this.spawnWave(nextIdx);
        }
      }
    },

    checkSequences(dt) {
      if (this.deathPending) {
        this.deathTimer += dt;
        if (this.deathTimer > 1.5 && this.state === 'playing') this._finishGameOver();
        return;
      }
      if (this.victoryPending) {
        this.victoryTimer -= dt;
        if (this.victoryTimer <= 0 && this.state === 'playing') this._finishVictory();
      }
    },

    updateBossState() {
      let bossEnemy = null;
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (e && e.isBoss && e.state !== 'dead') { bossEnemy = e; break; }
      }
      if (bossEnemy) {
        if (!this.boss) {
          this.boss = {
            name: '铁面 IRON MASK', title: '后巷霸主',
            hp: bossEnemy.hp, maxHp: bossEnemy.maxHp, active: true, phase: 1
          };
        }
        this.boss.hp = Math.max(0, bossEnemy.hp);
        this.boss.maxHp = bossEnemy.maxHp;
        this.boss.phase = bossEnemy.phase;
        this.boss.active = bossEnemy.state !== 'ko';
      } else if (this.boss) {
        this.boss.hp = 0;
        this.boss.active = false;
      }
    },

    /* ---------------- 命中判定 ---------------- */
    /** 三段式近似碰撞：横向 reach + 纵深 40 + z 高度重叠 */
    _overlapAttack(attacker, target, hit) {
      if (!attacker || !target) return false;
      const dy = Math.abs(attacker.y - target.y);
      if (dy > 40) return false;
      const dx = target.x - attacker.x;
      if (dx * attacker.facing < -8) return false; // 目标必须在面向侧（贴身允许）
      const reach = hit.reach == null ? 32 : hit.reach;
      if (Math.abs(dx) > attacker.halfW + reach + target.halfW) return false;
      const z0 = attacker.z + (hit.z0 == null ? 0 : hit.z0);
      const z1 = attacker.z + (hit.z1 == null ? attacker.height : hit.z1);
      const tz0 = target.z;
      const tz1 = target.z + target.height;
      return z0 < tz1 && z1 > tz0;
    },

    /** 玩家攻击 → 敌人；每一段对同一目标只命中一次（hitSet 由 Player 维护） */
    playerAttackHit(player, hit, hitSet) {
      if (!player || !hit || !hitSet) return;
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (!e || e.state === 'dead' || e.state === 'ko') continue;
        if (e.invuln > 0) continue;
        if (hitSet.has(e.uid)) continue;
        if (!this._overlapAttack(player, e, hit)) continue;
        hitSet.add(e.uid);
        const applied = e.takeHit({
          dmg: hit.dmg,
          dir: player.facing,
          kb: hit.kb,
          launch: !!hit.launch,
          stun: hit.stun,
          power: hit.power
        }, this);
        if (applied) this._onPlayerHitEnemy(player, e, hit);
      }
    },

    _onPlayerHitEnemy(player, enemy, hit) {
      this.combo += 1;
      this.comboTimer = this.comboMaxTime;
      if (this.combo > this.maxCombo) this.maxCombo = this.combo;

      this.addScore(hit.score == null ? 100 : hit.score);
      if (hit.gain && typeof player.addSpecial === 'function') player.addSpecial(hit.gain);

      const power = hit.power == null ? 0.4 : hit.power;
      this.hitstop = Math.max(this.hitstop, hit.hitstop == null ? cfg.HITSTOP_LIGHT : hit.hitstop);
      callFx('shake', hit.shake == null ? 2.5 : hit.shake, 0.12 + power * 0.22);

      const dir = player.facing;
      const hx = enemy.x - dir * enemy.halfW * 0.5;
      const hy = enemy.y - Math.min(enemy.height * 0.62, 130) - enemy.z;
      callFx('hitSpark', hx, hy, dir, U.clamp01(power));
      callFx('damageNumber', enemy.x, enemy.y - enemy.height - 10 - enemy.z, hit.dmg, {
        color: hit.launch ? '#ffd23f' : '#f7f1ff',
        big: !!hit.launch || power >= 0.8,
        combo: this.combo
      });
      callSfx(hit.sfx || 'hit');
      if (this.combo === 2 || this.combo === 5 || this.combo % 5 === 0) callSfx('combo');

      if (hit.finisher) {
        callFx('flash', '#bffcff', 0.55, 0.2);
        callFx('shake', 10, 0.35);
      } else if (hit.launch) {
        callFx('flash', '#fff2c0', 0.16, 0.07);
      }
    },

    /** 敌人攻击 → 玩家 */
    enemyAttackHit(enemy, atk) {
      const p = this.player;
      if (!p || !p.alive || !atk) return false;
      if (!this._overlapAttack(enemy, p, atk)) return false;
      const applied = p.takeHit(atk.damage, enemy.x, { kb: atk.kb, stun: atk.stun });
      if (applied) this._onPlayerHitByEnemy(enemy, atk);
      return applied;
    },

    _onPlayerHitByEnemy(enemy, atk) {
      this.combo = 0;
      this.comboTimer = 0;
      this.hitstop = Math.max(this.hitstop, 0.06);
      const p = this.player;
      callFx('shake', 6.5, 0.3);
      callFx('flash', '#ff3b5c', 0.34, 0.22);
      callFx('hitSpark', p.x + (p.x >= enemy.x ? 18 : -18), p.y - 112, U.sign(p.x - enemy.x) || 1, 0.8);
      callFx('damageNumber', p.x, p.y - 172, atk.damage, { color: '#ff5c7a' });
      callSfx(atk.sfx || 'hitHeavy');
    },

    /* ---------------- 击杀 / 掉落 / 结算 ---------------- */
    onEnemyKilled(enemy, hit) {
      if (!enemy) return;
      const isBoss = !!enemy.isBoss;
      this.kills += 1;
      this.combo += 1;
      this.comboTimer = this.comboMaxTime;
      if (this.combo > this.maxCombo) this.maxCombo = this.combo;
      this.addScore(300 + this.combo * 20);

      const p = this.player;
      const dir = U.sign(enemy.x - (p ? p.x : enemy.x)) || 1;
      callFx('hitSpark', enemy.x, enemy.y - enemy.height * 0.55, dir, 1);
      callFx('text', enemy.x, enemy.y - enemy.height - 26, 'K.O.', {
        color: '#ffd23f', size: 22, life: 0.9
      });
      callFx('shake', isBoss ? 16 : 7, isBoss ? 1.1 : 0.32);
      callFx('flash', isBoss ? '#ffffff' : '#ffd8f0', isBoss ? 0.85 : 0.14, isBoss ? 0.6 : 0.1);
      callSfx('ko');
      this.hitstop = Math.max(this.hitstop, isBoss ? 0.14 : 0.06);

      const chance = isBoss ? 1 : (enemy.def && enemy.def.dropChance != null ? enemy.def.dropChance : 0.25);
      if (isBoss || Math.random() < chance) this.spawnHealthPack(enemy.x, enemy.y);

      if (isBoss) this._beginVictory();
    },

    onPlayerDeath() {
      if (this.deathPending || this.state !== 'playing') return;
      this.deathPending = true;
      this.deathTimer = 0;
      this.combo = 0;
      this.comboTimer = 0;
      this.slowmo = 1.5;
      this.slowmoScale = 0.32;
      this.banner = null;
      callMusic('none');
      callFx('flash', '#ff3b5c', 0.65, 0.55);
      callFx('shake', 13, 0.8);
      callSfx('ko');
    },

    _beginVictory() {
      if (this.victoryPending || this.state === 'victory') return;
      this.victoryPending = true;
      this.victoryTimer = 2.4;
      this.slowmo = 2.4;
      this.slowmoScale = 0.28;
      this.banner = {
        label: 'K.O.', sub: '铁面 IRON MASK 被击倒',
        timer: 2.2, max: 2.2, kind: 'boss'
      };
      callMusic('none');
      callFx('flash', '#ffffff', 0.95, 0.7);
      callFx('shake', 18, 1.2);
      callSfx('victory');
      this.addScore(3000);
    },

    _finishVictory() {
      this.victoryPending = false;
      this.state = 'victory';
      this.endTimer = 0;
      const p = this.player;
      if (p) {
        p.state = 'victory';
        p.anim = 'victory';
        p.animTime = 0;
        p.z = 0;
        p.vx = 0;
        p.invuln = 0;
      }
      this.addScore(5000 + Math.max(0, p ? p.hp : 0) * 12);
      this.saveHighScore();
      callMusic('victory');
      callSfx('victory');
      callHudToast('STAGE CLEAR');
    },

    _finishGameOver() {
      this.deathPending = false;
      this.state = 'gameover';
      this.endTimer = 0;
      this.gameoverReason = 'HP 归零';
      this.saveHighScore();
      callMusic('gameover');
      callSfx('gameover');
    },

    addScore(n) {
      this.score += Math.max(0, Math.round(n));
      if (this.score > this.highScore) this.highScore = this.score;
    },

    /* ---------------- 掉落物 ---------------- */
    spawnHealthPack(x, y) {
      this.pickups.push({
        uid: 'pack_' + Math.floor(this.time * 1000) + '_' + this.pickups.length,
        x: x,
        y: y,
        z: 78,
        vx: U.rand(-36, 36),
        vz: U.rand(20, 70),
        life: 14,
        age: 0
      });
      callFx('dust', x, y, { power: 0.4 });
    },

    updatePickups(dt) {
      const p = this.player;
      for (let i = this.pickups.length - 1; i >= 0; i--) {
        const k = this.pickups[i];
        k.age += dt;
        k.life -= dt;
        k.vz -= 900 * dt;   /* z 向上为正，重力为负 */
        k.z += k.vz * dt;
        k.x += k.vx * dt;
        if (k.z <= 0) {
          k.z = 0;
          if (k.vz < -70) k.vz = -k.vz * 0.4;
          else { k.vz = 0; k.vx *= 0.6; }
        }
        k.x = U.clamp(k.x, 60, cfg.STAGE_W - 60);
        if (p && p.alive && Math.abs(k.x - p.x) < 36 && Math.abs(k.y - p.y) < 30 && k.z < 70) {
          this._pickupHealth(k);
          this.pickups.splice(i, 1);
          continue;
        }
        if (k.life <= 0) this.pickups.splice(i, 1);
      }
    },

    _pickupHealth(k) {
      const p = this.player;
      const before = p.hp;
      p.hp = Math.min(p.maxHp, p.hp + 20);
      const healed = Math.max(0, p.hp - before);
      this.addScore(50);
      callSfx('pickup');
      callFx('text', k.x, k.y - 70, '+' + (healed || 20) + ' HP', {
        color: '#8dff5a', size: 16, life: 0.8
      });
      callFx('flash', '#8dff5a', 0.16, 0.18);
      callHudToast('HP +' + (healed || 20));
    },

    /* ---------------- 角色推挤 ---------------- */
    resolveBodies() {
      const p = this.player;
      const list = this.enemies;
      if (p && p.alive) {
        for (let i = 0; i < list.length; i++) {
          const e = list[i];
          if (!e || e.state === 'dead' || e.state === 'ko') continue;
          if (Math.abs(p.y - e.y) > 26) continue;
          const minDist = p.halfW + e.halfW - 8;
          const dx = p.x - e.x;
          if (Math.abs(dx) < minDist) {
            const dir = dx >= 0 ? 1 : -1;
            const push = (minDist - Math.abs(dx)) * 0.5;
            if (e.isBoss) {
              p.x = U.clamp(p.x + dir * push * 2, p.minX, p.maxX);
            } else {
              p.x = U.clamp(p.x + dir * push, p.minX, p.maxX);
              e.x = U.clamp(e.x - dir * push, 60, cfg.STAGE_W - 90);
            }
          }
        }
      }
      for (let i = 0; i < list.length; i++) {
        for (let j = i + 1; j < list.length; j++) {
          const a = list[i];
          const b = list[j];
          if (!a || !b || a.state === 'dead' || b.state === 'dead') continue;
          if (a.state === 'ko' || b.state === 'ko') continue;
          if (Math.abs(a.y - b.y) > 24) continue;
          const minDist = a.halfW + b.halfW - 6;
          const dx = a.x - b.x;
          if (Math.abs(dx) < minDist) {
            const dir = dx >= 0 ? 1 : -1;
            const push = (minDist - Math.abs(dx)) * 0.5;
            a.x = U.clamp(a.x + dir * push, 60, cfg.STAGE_W - 90);
            b.x = U.clamp(b.x - dir * push, 60, cfg.STAGE_W - 90);
          }
        }
      }
    },

    cleanupEntities() {
      for (let i = this.enemies.length - 1; i >= 0; i--) {
        const e = this.enemies[i];
        if (!e || e.state === 'dead') this.enemies.splice(i, 1);
      }
    },

    /** 敌人攻击令牌：同屏同时攻击（前摇/出招）的敌人 ≤ 2 */
    canEnemyAttack(enemy) {
      if (!enemy) return false;
      if (enemy.attackToken) return true;
      let count = 0;
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (!e || e === enemy) continue;
        if (e.attackToken && (e.state === 'windup' || e.state === 'attack')) count++;
      }
      return count < 2;
    },

    /* ---------------- Boss 事件 ---------------- */
    onBossPhase2(boss) {
      this._selftestSawPhase2 = 1;
      this.banner = { label: 'IRON MASK', sub: '第二阶段 — 暴走', timer: 1.8, max: 1.8, kind: 'boss' };
      this.addScore(500);
      callHudToast('铁面 进入第二阶段');
      if (this.player) this.player.addSpecial(20);
    },

    onBossRoar(boss) {
      this._selftestSawRoar = 1;
      callHudToast('铁面 咆哮');
    },

    onSpecialStart(player) {
      this.hitstop = Math.max(this.hitstop, 0.06);
      callFx('flash', '#bffcff', 0.42, 0.2);
      callFx('shake', 8, 0.4);
      callFx('text', player.x, player.y - 218, '霓虹爆裂', {
        color: '#ffd23f', size: 26, life: 0.9
      });
    },

    /* ================================================================ */
    /* 世界空间绘制（主循环已应用摄像机变换）                             */
    draw(ctx) {
      /* 胜负结算由 HUD 全屏覆盖；世界层不再绘制角色，避免半截人物从面板后露出 */
      if (this.state === 'victory' || this.state === 'gameover') return;

      const camX = NF.camera ? NF.camera.x : 0;
      const vw = cfg.VIEW_W;
      const inView = (x) => x > camX - 280 && x < camX + vw + 280;

      const items = [];
      const p = this.player;
      if (p) items.push({ kind: 'player', e: p, y: p.y });
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (e && e.state !== 'dead') items.push({ kind: 'enemy', e: e, y: e.y });
      }
      for (let i = 0; i < this.pickups.length; i++) {
        const k = this.pickups[i];
        items.push({ kind: 'pickup', e: k, y: k.y });
      }
      items.sort((a, b) => a.y - b.y);

      /* 1) 影子（全部垫底） */
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        if (!inView(it.e.x)) continue;
        if (it.kind === 'pickup') {
          NF.render.drawShadow(ctx, it.e.x, it.e.y, 22, 0.25);
        } else {
          it.e.drawShadow(ctx);
        }
      }
      /* 2) 地面预警 / Boss 气场 */
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        if (it.kind !== 'enemy' || !inView(it.e.x)) continue;
        it.e.drawTelegraph(ctx);
      }
      /* 3) 角色与掉落（按脚底 y 从远到近） */
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        if (!inView(it.e.x)) continue;
        if (it.kind === 'pickup') this._drawPickup(ctx, it.e);
        else it.e.drawSprite(ctx);
      }
      /* 4) 敌人血条（最上层） */
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        if (it.kind !== 'enemy' || !inView(it.e.x)) continue;
        it.e.drawHpBar(ctx);
      }
    },

    _drawPickup(ctx, k) {
      if (k.life < 3.2 && Math.floor(k.age * 12) % 2 === 0) return; // 即将消失时闪烁
      const bob = Math.sin(k.age * 5.2) * 2.5;
      const x = Math.round(k.x);
      const y = Math.round(k.y - k.z - 15 - bob);
      ctx.save();
      ctx.translate(x, y);
      /* 绿色霓虹光晕 */
      ctx.globalAlpha = 0.2 + 0.07 * Math.sin(k.age * 6);
      ctx.fillStyle = '#8dff5a';
      ctx.beginPath();
      ctx.ellipse(0, 0, 27, 21, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      /* 医疗箱 */
      ctx.fillStyle = '#0a0614';
      ctx.fillRect(-13, -11, 26, 22);
      ctx.fillStyle = '#f7f1ff';
      ctx.fillRect(-11.5, -9.5, 23, 19);
      ctx.fillStyle = '#ff3b5c';
      ctx.fillRect(-2.5, -7, 5, 14);
      ctx.fillRect(-7, -2.5, 14, 5);
      ctx.fillStyle = 'rgba(255,255,255,0.65)';
      ctx.fillRect(-11.5, -9.5, 23, 2);
      ctx.restore();
    },

    /* ================================================================ */
    /* 截图场景（无人工操作即可布景；配合 game.shotFrozen 冻结）          */
    debugStart(name) {
      this.shotFrozen = false;
      this.hitstop = 0;
      this.slowmo = 0;
      this.slowmoScale = 0.34;
      if (NF.fx && typeof NF.fx.clear === 'function') {
        try { NF.fx.clear(); } catch (err) { /* ignore */ }
      }
      switch (name) {
        case 'title': this._shotTitle(); break;
        case 'battle': this._shotBattle(); break;
        case 'boss': this._shotBoss(); break;
        case 'intro': this._shotIntro(); break;
        case 'combo': this._shotCombo(); break;
        case 'victory': this._shotVictory(); break;
        case 'gameover': this._shotGameover(); break;
        default: this._shotBattle(); break;
      }
      this.hitstop = 0;
      this.slowmo = 0;
      this.shotFrozen = true;
      /* 重置 HUD 内部 toast/弹跳动画，避免截图中残留多条「WAVE N」提示 */
      if (NF.hud && typeof NF.hud.init === 'function') {
        try { NF.hud.init(); } catch (err) { /* ignore */ }
      }
    },

    _shotCamera(lockX) {
      if (!NF.camera || typeof NF.camera.reset !== 'function') return;
      const vw = cfg.VIEW_W;
      const maxX = Math.max(0, cfg.STAGE_W - vw);
      let x = lockX;
      if (x == null) {
        const p = this.player;
        x = (p ? p.x + p.facing * 46 : cfg.PLAYER_START_X) - vw * 0.42;
      }
      try { NF.camera.reset(U.clamp(x, 0, maxX)); } catch (err) { /* ignore */ }
    },

    _shotPlayer(x, y, facing, anim, t, opts) {
      const p = this.player;
      opts = opts || {};
      p.reset(x, y);
      p.facing = facing == null ? 1 : facing;
      p.hp = opts.hp == null ? p.maxHp : opts.hp;
      p.special = opts.special == null ? p.maxSpecial : opts.special;
      p.invuln = 0;
      p.flash = 0;
      p.pose(anim || 'idle', t || 0, opts.state);
      return p;
    },

    _shotEnemy(type, x, y, opts) {
      opts = opts || {};
      const e = NF.enemies.spawn(type, x, y, {
        side: opts.side || 1,
        facing: opts.facing || -1,
        depthOffset: opts.depthOffset || 0,
        hp: opts.hp
      });
      if (!e) return null;
      e.state = opts.state || 'chase';
      e.anim = opts.anim || 'idle';
      e.animTime = opts.t || 0;
      e.hp = opts.hp == null ? e.maxHp : opts.hp;
      e.flash = opts.flash || 0;
      if (e.state === 'hurt') e.hurtT = 0.3;
      this.enemies.push(e);
      return e;
    },

    _shotTitle() {
      this.toTitle();
      this._shotCamera(0);
      if (this.player) {
        this.player.x = cfg.PLAYER_START_X;
        this.player.y = cfg.PLAYER_START_Y;
        this.player.anim = 'idle';
        this.player.animTime = 0.25;
      }
      this.banner = null;
      this.boss = null;
    },

    _shotBattle() {
      this.startRun();
      this.enemies.length = 0;
      this.pickups.length = 0;
      this.waveIndex = 1;
      this.wave = 2;
      this.wavePhase = 'fighting';
      this.banner = null;
      this._shotPlayer(560, 466, 1, 'punch3', 3.2 / 12, { hp: 88, special: 64 });

      const e1 = this._shotEnemy('punk', 704, 470, { hp: 22, state: 'hurt', anim: 'hurt', t: 0.06, flash: 0.42, depthOffset: 4 });
      this._shotEnemy('punk', 800, 448, { hp: 34, depthOffset: -16, facing: -1 });
      this._shotEnemy('brute', 872, 492, { hp: 71, depthOffset: 12, facing: -1 });
      if (e1) { e1.facing = 1; e1.vx = 20; }

      this.combo = 7;
      this.comboTimer = 1.95;
      this.maxCombo = 7;
      this.score = 1260;
      this.kills = 3;
      this.addScore(0);

      callFx('hitSpark', 648, 386, 1, 0.85);
      callFx('hitSpark', 668, 356, 1, 0.55);
      callFx('hitSpark', 618, 408, 1, 0.4);
      if (e1) callFx('hitSpark', e1.x - 6, e1.y - 104, 1, 0.5);
      callFx('damageNumber', 654, 332, 14, { color: '#ffd23f', big: true, combo: 7 });
      callFx('damageNumber', 706, 318, 8, { color: '#f7f1ff', combo: 7 });
      callFx('damageNumber', 804, 286, 6, { color: '#f7f1ff', combo: 7 });
      callFx('flash', '#fff4d8', 0.10, 0.06);
      this._shotCamera(null);
      this.updateBossState();
    },

    _shotBoss() {
      this.startRun();
      this.enemies.length = 0;
      this.pickups.length = 0;
      this.waveIndex = 3;
      this.wave = 4;
      this.wavePhase = 'fighting';
      this.cameraLockX = typeof STAGE.bossLockCameraX === 'number'
        ? STAGE.bossLockCameraX : (cfg.STAGE_W - cfg.VIEW_W);
      this.banner = null;
      this._shotPlayer(2500, 470, 1, 'punch3', 3.2 / 12, { hp: 72, special: 100 });

      const boss = NF.enemies.spawn('boss', 2688, 470, { side: 1, facing: -1, depthOffset: 0 });
      if (boss) {
        boss.hp = 250;
        boss.state = 'attack';
        boss.attackKind = 'sweep';
        boss.attackT = 0.22;
        boss.anim = 'attack1';
        boss.animTime = 0.22;
        boss.invuln = 0;
        this.enemies.push(boss);
        this.boss = {
          name: '铁面 IRON MASK', title: '后巷霸主',
          hp: boss.hp, maxHp: boss.maxHp, active: true, phase: 1
        };
      }
      this.combo = 5;
      this.comboTimer = 1.7;
      this.maxCombo = 9;
      this.score = 5400;
      this.kills = 6;

      callFx('hitSpark', 2622, 356, 1, 0.9);
      callFx('hitSpark', 2588, 388, 1, 0.6);
      callFx('damageNumber', 2612, 306, 12, { color: '#ffd23f', big: true, combo: 5 });
      callFx('flash', '#ffd8f0', 0.10, 0.06);
      this._shotCamera(this.cameraLockX);
      this.updateBossState();
    },

    _shotIntro() {
      this.startRun();
      this.enemies.length = 0;
      this.pickups.length = 0;
      this.waveIndex = 3;
      this.wave = 4;
      this.wavePhase = 'intro';
      this.cameraLockX = typeof STAGE.bossLockCameraX === 'number'
        ? STAGE.bossLockCameraX : (cfg.STAGE_W - cfg.VIEW_W);
      this._shotPlayer(2478, 474, 1, 'idle', 0.2, { hp: 120, special: 100 });

      const boss = NF.enemies.spawn('boss', 2960, 466, {
        side: 1, facing: -1, state: 'intro', invuln: 9, depthOffset: 0
      });
      if (boss) {
        boss.introT = 0.6;
        boss.anim = 'walk';
        boss.animTime = 0.12;
        this.enemies.push(boss);
        this.boss = {
          name: '铁面 IRON MASK', title: '后巷霸主',
          hp: boss.hp, maxHp: boss.maxHp, active: true, phase: 1
        };
      }
      this.banner = { label: 'BOSS', sub: '铁面 IRON MASK', timer: 1.8, max: 2.6, kind: 'boss' };
      this.combo = 0;
      this.comboTimer = 0;
      this.score = 4200;
      this.kills = 5;
      callFx('flash', '#ff2f8e', 0.22, 0.35);
      callFx('shake', 3, 0.5);
      this._shotCamera(this.cameraLockX);
      this.updateBossState();
    },

    _shotCombo() {
      this.startRun();
      this.enemies.length = 0;
      this.pickups.length = 0;
      this.waveIndex = 2;
      this.wave = 3;
      this.wavePhase = 'fighting';
      this.banner = null;
      this._shotPlayer(1480, 470, 1, 'punch2', 1.1 / 14, { hp: 104, special: 100 });

      const e1 = this._shotEnemy('punk', 1584, 476, { hp: 12, state: 'hurt', anim: 'hurt', t: 0.03, flash: 0.45, depthOffset: 4 });
      this._shotEnemy('punk', 1652, 448, { hp: 26, depthOffset: -14, facing: -1 });
      this._shotEnemy('brute', 1738, 496, { hp: 60, depthOffset: 14, facing: -1 });
      if (e1) e1.facing = 1;

      this.combo = 23;
      this.comboTimer = 2.1;
      this.maxCombo = 23;
      this.score = 8420;
      this.kills = 5;

      for (let i = 0; i < 7; i++) {
        callFx('hitSpark', 1550 + (i % 3) * 34, 330 + (i % 4) * 26, 1, 0.5 + (i % 3) * 0.2);
      }
      callFx('damageNumber', 1546, 300, 14, { color: '#ffd23f', big: true, combo: 23 });
      callFx('damageNumber', 1594, 334, 8, { color: '#f7f1ff', combo: 23 });
      callFx('damageNumber', 1640, 286, 6, { color: '#f7f1ff', combo: 23 });
      callFx('damageNumber', 1690, 316, 18, { color: '#ffd23f', big: true, combo: 23 });
      callFx('flash', '#fff4d8', 0.14, 0.08);
      this._shotCamera(null);
      this.updateBossState();
    },

    _shotVictory() {
      this.startRun();
      this.enemies.length = 0;
      this.pickups.length = 0;
      this.waveIndex = 3;
      this.wave = 4;
      this.wavePhase = 'cleared';
      this.cameraLockX = typeof STAGE.bossLockCameraX === 'number'
        ? STAGE.bossLockCameraX : (cfg.STAGE_W - cfg.VIEW_W);
      this._shotPlayer(2640, 470, 1, 'victory', 0.1, { hp: 84, special: 100 });
      if (this.player) {
        this.player.state = 'victory';
        this.player.alive = true;
      }
      this.combo = 0;
      this.comboTimer = 0;
      this.maxCombo = 31;
      this.score = 28640;
      this.kills = 11;
      this.highScore = Math.max(this.highScore, this.score);
      this.boss = {
        name: '铁面 IRON MASK', title: '后巷霸主',
        hp: 0, maxHp: 420, active: false, phase: 2
      };
      this.state = 'victory';
      this.endTimer = 1.1;
      this.banner = null;
      callFx('flash', '#3df3ff', 0.18, 0.5);
      this._shotCamera(this.cameraLockX);
    },

    _shotGameover() {
      this.startRun();
      this.enemies.length = 0;
      this.pickups.length = 0;
      this.waveIndex = 2;
      this.wave = 3;
      this.wavePhase = 'fighting';
      this._shotPlayer(1760, 478, 1, 'ko', 0.62, { hp: 0, special: 46 });
      this.player.alive = false;
      this.player.state = 'ko';
      this.player.z = 0;
      this.player.vx = 0;
      this.combo = 0;
      this.comboTimer = 0;
      this.maxCombo = 17;
      this.score = 7340;
      this.kills = 7;
      this.state = 'gameover';
      this.endTimer = 1.1;
      this.gameoverReason = 'HP 归零';
      this.banner = null;
      this.boss = null;
      callFx('flash', '#ff3b5c', 0.2, 0.4);
      this._shotCamera(null);
    },

    /* ================================================================ */
    /* 开发自检（?selftest=1）：机器人无头跑完整流程，结果写入 document.title
     * 仅用于验证 状态机/波次/Boss/胜负流程 无异常，不参与正式玩法。 */
    _selftestRun(mode) {
      const results = {
        mode: String(mode || 'victory'),
        state: 'init', steps: 0, seconds: 0,
        victory: 0, gameover: 0, score: 0, maxCombo: 0, kills: 0,
        waves: 0, waveIndex: -1, playerHp: 0,
        bossHp: -1, bossPhase: 0,
        sawBoss: 0, sawPhase2: 0, sawRoar: 0, sawBanner: 0,
        errors: 0, err: '', transitions: ''
      };
      const maxSteps = 60 * 320;
      try {
        this.toTitle();
        this.startRun();
        this.shotFrozen = false;
        const inp = NF.input;
        let lastState = this.state;
        for (let i = 0; i < maxSteps; i++) {
          this._selftestBot(inp, mode, i);
          try {
            this.update(1 / 60);
            if (NF.fx && typeof NF.fx.update === 'function') NF.fx.update(1 / 60);
            if (NF.camera && typeof NF.camera.update === 'function') NF.camera.update(1 / 60);
          } catch (err) {
            results.errors++;
            results.err = String(err && err.message ? err.message : err).slice(0, 110);
            break;
          }
          if (NF.input && typeof NF.input.endFrame === 'function') NF.input.endFrame();
          results.steps = i + 1;
          if (this.state !== lastState) {
            lastState = this.state;
            results.transitions += this.state + '@' + (i + 1) + ';';
            if (this.state === 'victory' || this.state === 'gameover') break;
          }
        }
        results.state = this.state;
        results.victory = this.state === 'victory' ? 1 : 0;
        results.gameover = this.state === 'gameover' ? 1 : 0;
        results.score = this.score;
        results.maxCombo = this.maxCombo;
        results.kills = this.kills;
        results.waves = this.wave;
        results.waveIndex = this.waveIndex;
        results.playerHp = Math.round(this.player ? this.player.hp : 0);
        results.bossHp = this.boss ? Math.round(this.boss.hp) : -1;
        results.bossPhase = this.boss ? this.boss.phase : 0;
        results.sawBoss = this._selftestSawBoss;
        results.sawPhase2 = this._selftestSawPhase2;
        results.sawRoar = this._selftestSawRoar;
        results.sawBanner = this._selftestSawBanner;
        results.seconds = Math.round(results.steps / 60);
        results.dbg = this._selftestDebug();
        /* 重开流程：结算画面 → 标题 → 新一局（验证完整循环） */
        let restartOk = 0;
        let restartTrans = '';
        try {
          const inp2 = NF.input;
          let lastState2 = this.state;
          for (let k = 0; k < 300; k++) {
            inp2.down.left = false; inp2.down.right = false; inp2.down.up = false; inp2.down.down = false;
            inp2.pressed.attack = false; inp2.pressed.heavy = false; inp2.pressed.jump = false;
            inp2.pressed.special = false; inp2.pressed.start = false;
            if (this.state === 'gameover' || this.state === 'victory' || this.state === 'title') {
              inp2.pressed.start = true;
            }
            this.update(1 / 60);
            if (NF.fx && typeof NF.fx.update === 'function') NF.fx.update(1 / 60);
            if (NF.camera && typeof NF.camera.update === 'function') NF.camera.update(1 / 60);
            NF.input.endFrame();
            if (this.state !== lastState2) {
              lastState2 = this.state;
              restartTrans += this.state + ';';
            }
            if (this.state === 'playing' && this.wave === 1 && this.enemies.length > 0) { restartOk = 1; break; }
          }
        } catch (err2) {
          results.errors++;
          results.err = 'restart:' + String(err2 && err2.message ? err2.message : err2).slice(0, 100);
        }
        results.restartOk = restartOk;
        results.restartTrans = restartTrans.slice(0, 80);
      } catch (err) {
        results.errors++;
        results.err = String(err && err.message ? err.message : err).slice(0, 110);
      }
      window.__NF_SELFTEST = results;
      try { document.title = 'SELFTEST ' + JSON.stringify(results); } catch (err) { /* ignore */ }
    },

    _selftestDebug() {
      const p = this.player;
      const pp = p ? ('p@' + Math.round(p.x) + ',' + Math.round(p.y) + ' f' + p.facing +
        ' ' + p.state + '/' + p.anim + ' hp' + Math.round(p.hp)) : 'p@none';
      const list = [];
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (!e) continue;
        list.push(e.type + ':' + e.state + ':' + Math.round(e.x) + ',' + Math.round(e.y) +
          ':hp' + Math.round(e.hp) + ':z' + Math.round(e.z));
      }
      return (pp + ' | ' + list.join(' ; ')).slice(0, 300);
    },

    _selftestBot(inp, mode, frame) {
      inp.down.left = false;
      inp.down.right = false;
      inp.down.up = false;
      inp.down.down = false;
      inp.pressed.attack = false;
      inp.pressed.heavy = false;
      inp.pressed.jump = false;
      inp.pressed.special = false;
      inp.pressed.start = false;

      if (this.state === 'title') { inp.pressed.start = true; return; }
      if (this.state === 'gameover' || this.state === 'victory') return;

      const p = this.player;
      if (!p || !p.alive) return;
      /* 自检模式保证机器人能推进到 Boss（只验证流程，不代表平衡性） */
      if (mode === 'victory' && p.hp < 80) p.hp = p.maxHp;

      let target = null;
      let best = 1e9;
      for (let i = 0; i < this.enemies.length; i++) {
        const e = this.enemies[i];
        if (!e || e.state === 'ko' || e.state === 'dead') continue;
        const d = Math.abs(e.x - p.x) + Math.abs(e.y - p.y) * 1.3;
        if (d < best) { best = d; target = e; }
      }
      if (!target) {
        inp.down.right = true; // 无敌人时向右推进，触发下一波 / Boss
        return;
      }
      const dx = target.x - p.x;
      const dy = target.y - p.y;
      if (Math.abs(dx) > 64) {
        if (dx > 0) inp.down.right = true; else inp.down.left = true;
      } else if (Math.abs(dx) < 30) {
        if (dx > 0) inp.down.left = true; else inp.down.right = true;
      }
      if (Math.abs(dy) > 12) {
        if (dy > 0) inp.down.down = true; else inp.down.up = true;
      }
      if (mode === 'gameover') return; // 送死模式：靠近但不还手
      if (Math.abs(dx) < 76 && Math.abs(dy) < 32) {
        inp.pressed.attack = true;
        if (frame % 6 === 0) inp.pressed.heavy = true;
      }
      if (p.special >= p.maxSpecial) inp.pressed.special = true;
      if (frame % 300 === 0) inp.pressed.jump = true;
    }
  };

  NF.game = game;
})();
