/* 霓虹拳魂 — 基于 Chrome DevTools Protocol 的冒烟测试
 * 用法：先启动本地服务器（python -m http.server 8123），然后在项目根目录：
 *   node tools/cdp_smoke.mjs
 * 作用：真实浏览器加载游戏 → 键盘开始 → 移动/攻击 → 各 debug 场景 → 捕获异常与截图。
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const ROOT = process.cwd();
const CHROME = fs.existsSync('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe')
  ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  : 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9300 + Math.floor(Math.random() * 200);
const PROFILE = path.join(os.tmpdir(), 'nfsmoke_' + Date.now());
const URL = 'http://127.0.0.1:8123/index.html?debug=1';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const results = [];
const errors = [];
const pageErrors = [];
let chrome;

function record(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? '  — ' + detail : ''));
}

async function fetchJson(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok) return await r.json();
    } catch (err) { /* retry */ }
    await sleep(150);
  }
  throw new Error('timeout waiting for ' + url);
}

class CDP {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.pending = new Map();
    this.events = [];
  }
  async open() {
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = (e) => reject(new Error('ws error: ' + (e.message || 'unknown')));
    });
    this.ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (err) { return; }
      if (msg.id) {
        const p = this.pending.get(msg.id);
        if (p) {
          this.pending.delete(msg.id);
          if (msg.error) p.reject(new Error(JSON.stringify(msg.error)));
          else p.resolve(msg.result);
        }
      } else {
        this.events.push(msg);
        if (msg.method === 'Runtime.exceptionThrown') {
          const d = msg.params.exceptionDetails;
          pageErrors.push(d.exception ? (d.exception.description || d.exception.value) : d.text);
        } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
          pageErrors.push(msg.params.args.map((a) => a.value || a.description || '').join(' '));
        }
      }
    };
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) {
      throw new Error('eval exception: ' + (r.exceptionDetails.exception ? r.exceptionDetails.exception.description : r.exceptionDetails.text));
    }
    return r.result ? r.result.value : undefined;
  }
  async waitFor(expression, timeoutMs = 20000, label = expression) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        if (await this.eval(expression)) return true;
      } catch (err) { /* page may be navigating */ }
      await sleep(150);
    }
    throw new Error('timeout waiting for ' + label);
  }
  async key(type, code, key, vk) {
    await this.send('Input.dispatchKeyEvent', {
      type, code, key, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk
    });
  }
  async screenshot(file) {
    const shot = await this.send('Page.captureScreenshot', { format: 'png' });
    fs.mkdirSync(path.join(ROOT, 'shots'), { recursive: true });
    fs.writeFileSync(file, Buffer.from(shot.data, 'base64'));
  }
}

async function main() {
  fs.mkdirSync(path.join(ROOT, 'shots'), { recursive: true });
  chrome = spawn(CHROME, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
    '--no-first-run', '--disable-extensions', '--no-default-browser-check',
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + PROFILE,
    '--window-size=1280,720', 'about:blank'
  ], { stdio: 'ignore', detached: false });

  const targets = await fetchJson('http://127.0.0.1:' + PORT + '/json/list');
  const page = targets.find((t) => t.type === 'page');
  if (!page) throw new Error('no page target');
  const cdp = new CDP(page.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  await cdp.send('Log.enable');
  await cdp.send('Page.bringToFront');
  await cdp.send('Page.navigate', { url: URL });

  await cdp.waitFor('window.__NF_READY === true', 25000, 'assets loaded');
  record('页面加载完成 (__NF_READY)', true);
  const assetsOk = await cdp.eval('NF.assets && NF.assets.loadError === false');
  record('所有美术资源加载成功（无 404）', assetsOk === true, String(assetsOk));

  const errText = await cdp.eval("(document.getElementById('error-box') || {}).className || ''");
  record('无页面错误覆盖层', !String(errText).includes('hidden') === false, String(errText));

  const state0 = await cdp.eval('NF.game.state');
  record('初始为标题状态', state0 === 'title', String(state0));

  await cdp.key('keyDown', 'Enter', 'Enter', 13);
  await cdp.key('keyUp', 'Enter', 'Enter', 13);
  await sleep(500);
  const state1 = await cdp.eval('NF.game.state');
  record('Enter 开始游戏', state1 === 'playing', String(state1));

  const x0 = await cdp.eval('NF.game.player.x');
  await cdp.key('keyDown', 'KeyD', 'd', 68);
  await sleep(600);
  await cdp.key('keyUp', 'KeyD', 'd', 68);
  const x1 = await cdp.eval('NF.game.player.x');
  record('按 D 玩家向右移动', x1 > x0 + 20, 'x ' + x0.toFixed(1) + ' -> ' + x1.toFixed(1));

  await cdp.key('keyDown', 'KeyJ', 'j', 74);
  await cdp.key('keyUp', 'KeyJ', 'j', 74);
  await sleep(180);
  const attacking = await cdp.eval("!!(NF.game.player.anim && NF.game.player.anim.indexOf('punch') === 0) || !!NF.game.player.attackTimer || !!NF.game.player.comboStep");
  record('攻击键触发攻击动作', attacking, await cdp.eval('NF.game.player.anim'));

  /* 暂停 / 按 R 重开 */
  await cdp.key('keyDown', 'KeyP', 'p', 80);
  await cdp.key('keyUp', 'KeyP', 'p', 80);
  await sleep(300);
  const paused = await cdp.eval('NF.game.state');
  record('P 进入暂停', paused === 'paused', String(paused));
  await cdp.screenshot(path.join(ROOT, 'shots', 'final_pause.png'));
  await cdp.key('keyDown', 'KeyR', 'r', 82);
  await cdp.key('keyUp', 'KeyR', 'r', 82);
  await sleep(400);
  const restarted = await cdp.eval('JSON.stringify({state:NF.game.state,x:Math.round(NF.game.player.x),wave:NF.game.wave})');
  record('暂停中按 R 重新开始', /"state":"playing"/.test(restarted), restarted);

  /* 真实用户手势解锁音频 */
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: 640, y: 360, button: 'left', clickCount: 1 });
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: 640, y: 360, button: 'left', clickCount: 1 });
  await sleep(500);
  const audio = await cdp.eval("JSON.stringify({audio: !!NF.audio, ready: NF.audio && NF.audio.ready, scene: NF.audio && NF.audio.scene, muted: NF.audio && NF.audio.muted, mutedFn: typeof (NF.audio && NF.audio.toggleMute)})");
  record('音频模块可调用（无异常）', /"audio":true/.test(audio), audio);
  record('用户手势后音频已解锁', /"ready":true/.test(audio), audio);

  const combat = await cdp.eval(`(function(){
    if (NF.game.debugStart) NF.game.debugStart('battle');
    return { state: NF.game.state, frozen: !!NF.game.shotFrozen, enemies: (NF.game.enemies||[]).length,
             hasBossField: 'boss' in NF.game, hp: NF.game.player ? NF.game.player.hp : null };
  })()`);
  record('battle 调试场景生成敌人', combat.enemies >= 1, JSON.stringify(combat));
  await sleep(250);
  await cdp.screenshot(path.join(ROOT, 'shots', 'cdp_battle.png'));

  const boss = await cdp.eval(`(function(){
    if (NF.game.debugStart) NF.game.debugStart('boss');
    return { boss: !!NF.game.boss, state: NF.game.state, lock: NF.game.cameraLockX };
  })()`);
  record('boss 调试场景生成 Boss', boss.boss === true, JSON.stringify(boss));
  await sleep(250);
  await cdp.screenshot(path.join(ROOT, 'shots', 'cdp_boss.png'));

  const vic = await cdp.eval(`(function(){ if (NF.game.debugStart) NF.game.debugStart('victory'); return NF.game.state; })()`);
  record('victory 调试场景', vic === 'victory', String(vic));

  const over = await cdp.eval(`(function(){ if (NF.game.debugStart) NF.game.debugStart('gameover'); return NF.game.state; })()`);
  record('gameover 调试场景', over === 'gameover', String(over));

  const hudFields = await cdp.eval(`(function(){
    const g = NF.game; return JSON.stringify({
      score: typeof g.score, wave: typeof g.wave, combo: typeof g.combo,
      totalWaves: typeof g.totalWaves, maxCombo: typeof g.maxCombo, kills: typeof g.kills
    });
  })()`);
  record('HUD 依赖字段存在', !/undefined/.test(hudFields), hudFields);

  const pageErr = await cdp.eval("(document.getElementById('error-box') || {}).textContent || ''");
  record('无 JS 运行时异常', pageErrors.length === 0 && !String(pageErr).trim(), pageErrors.slice(0, 3).join(' | '));

  const failed = results.filter((r) => !r.ok);
  console.log('\n===== 结果 =====');
  console.log(JSON.stringify({ pass: results.length - failed.length, fail: failed.length, pageErrors }, null, 2));
  process.exitCode = failed.length ? 1 : 0;
}

main().catch((err) => {
  console.error('SMOKE TEST ERROR:', err);
  process.exitCode = 2;
}).finally(async () => {
  try { if (chrome) chrome.kill(); } catch (err) { /* ignore */ }
  await sleep(400);
  try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (err) { /* ignore */ }
});
