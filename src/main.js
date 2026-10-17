/* 霓虹拳魂 NEON FIST SOUL — 启动、主循环、渲染管线、调试截图 */
(function () {
  const NF = window.NF;
  const cfg = NF.config;
  let canvas, ctx;
  let last = 0;
  let started = false;
  let elapsed = 0;
  let shotMode = false;
  let pausedByVisibility = false;

  function showError(err) {
    const box = document.getElementById('error-box');
    if (!box) return;
    box.classList.remove('hidden');
    box.textContent = '游戏脚本出错：\n' + (err && (err.stack || err.message) ? (err.stack || err.message) : String(err));
    console.error(err);
  }

  window.addEventListener('error', (e) => showError(e.error || e.message));
  window.addEventListener('unhandledrejection', (e) => showError(e.reason));

  function setupCanvas() {
    canvas = document.getElementById('game');
    ctx = canvas.getContext('2d', { alpha: false });
    NF.render.ctx = ctx;
    ctx.imageSmoothingEnabled = false;
  }

  function drawLoading() {
    ctx.fillStyle = '#07050f';
    ctx.fillRect(0, 0, cfg.VIEW_W, cfg.VIEW_H);
    ctx.fillStyle = '#3df3ff';
    ctx.font = 'bold 28px Consolas, monospace';
    ctx.textAlign = 'center';
    ctx.fillText('NEON FIST SOUL', cfg.VIEW_W / 2, cfg.VIEW_H / 2 - 10);
    ctx.fillStyle = '#8d84a8';
    ctx.font = '14px "Microsoft YaHei", sans-serif';
    ctx.fillText('正在加载霓虹后巷……', cfg.VIEW_W / 2, cfg.VIEW_H / 2 + 26);
  }

  /* 固定步长模拟（截图/调试用） */
  function simulate(seconds) {
    const step = 1 / 60;
    const count = Math.max(0, Math.round((seconds || 0) / step));
    for (let i = 0; i < count; i++) {
      elapsed += step;
      NF.input.poll();
      NF.game.update(step);
      NF.fx.update(step);
      NF.audio.update(step);
      NF.camera.update(step);
      NF.input.endFrame();
    }
  }

  function render() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, cfg.VIEW_W, cfg.VIEW_H);

    const camX = NF.camera.x;
    NF.camera.apply(ctx);
    NF.stage.drawBack(ctx, camX, elapsed);
    NF.game.draw(ctx);
    NF.stage.drawForeground(ctx, camX, elapsed);
    NF.fx.draw(ctx);
    NF.camera.restore(ctx);

    NF.fx.drawOverlay(ctx);
    NF.hud.draw(ctx, NF.game, elapsed);
    NF.fx.drawTop(ctx);
  }

  function frame(now) {
    const dt = Math.min(0.05, Math.max(0, (now - last) / 1000 || 0));
    last = now;
    if (!shotMode) {
      elapsed += dt;
      NF.input.poll();
      NF.game.update(dt);
      NF.fx.update(dt);
      NF.audio.update(dt);
      NF.camera.update(dt);
      NF.input.endFrame();
      render();
    }
    requestAnimationFrame(frame);
  }

  function runShot(shotName) {
    shotMode = true;
    const freezeDefault = { title: 0.9, battle: 1.3, boss: 1.6, victory: 1.4, gameover: 1.4, combo: 1.2, intro: 1.2 };
    const freeze = cfg.FREEZE >= 0 ? cfg.FREEZE : (freezeDefault[shotName] || 1.2);
    try {
      if (NF.game.debugStart) NF.game.debugStart(shotName);
      else NF.game.state = 'title';
    } catch (err) { showError(err); }
    /* 用固定步长推进到目标时刻，保证截图可复现 */
    simulate(freeze);
    NF.camera.update(1);
    if (cfg.DEBUG) {
      console.log('[NEON] shot', shotName, 'elapsed', elapsed.toFixed(2));
    }
    render();
    window.__SHOT_READY = true;
    document.title = 'SHOT-READY — ' + shotName;
  }

  function bindSystemButtons() {
    const muteBtn = document.getElementById('btn-mute');
    if (muteBtn) {
      muteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const muted = NF.audio.toggleMute();
        muteBtn.textContent = muted ? '×' : '♪';
      });
    }
    const pauseBtn = document.getElementById('btn-pause');
    if (pauseBtn) {
      pauseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (NF.game.togglePause) NF.game.togglePause();
      });
    }
    const fsBtn = document.getElementById('btn-fullscreen');
    if (fsBtn) {
      fsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const el = document.documentElement;
        if (!document.fullscreenElement) {
          if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
        } else if (document.exitFullscreen) {
          document.exitFullscreen().catch(() => {});
        }
      });
    }
  }

  function boot() {
    setupCanvas();
    drawLoading();
    bindSystemButtons();

    NF.render.init();
    NF.input.init(canvas);
    NF.audio.init();
    if (cfg.MUTE) NF.audio.setMuted(true);
    NF.game.init();
    NF.camera.reset(0);

    NF.input.onFirstGesture(() => {
      NF.audio.unlock();
      if (!started) started = true;
    });

    NF.assets.loadAll().then(() => {
      drawLoading();
      if (cfg.SHOT) {
        runShot(cfg.SHOT);
      } else {
        /* 让标题画面/主循环立即开始 */
        last = performance.now();
        requestAnimationFrame(frame);
      }
      window.__NF_READY = true;
    }).catch((err) => {
      showError(err);
    });

    document.addEventListener('visibilitychange', () => {
      pausedByVisibility = document.hidden;
      if (document.hidden) NF.audio.duck && NF.audio.duck(true);
      else { NF.audio.duck && NF.audio.duck(false); last = performance.now(); }
    });
  }

  window.addEventListener('load', boot);
  window.addEventListener('resize', () => {
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
  });

  /* 供调试/截图脚本调用 */
  NF.debug = {
    get elapsed() { return elapsed; },
    simulate(seconds) { simulate(seconds); render(); },
    render,
    shot(name) {
      shotMode = true;
      if (NF.game.debugStart) NF.game.debugStart(name);
      simulate(1);
      NF.camera.update(1);
      render();
    }
  };
})();
