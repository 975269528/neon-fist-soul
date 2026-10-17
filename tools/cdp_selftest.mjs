/* 霓虹拳魂 — 玩法自检机器人（读取 game.js 内置 ?selftest=1）
 * 用法：node tools/cdp_selftest.mjs [mode]   mode = victory | gameover
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const ROOT = process.cwd();
const mode = process.argv[2] || 'victory';
const CHROME = fs.existsSync('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe')
  ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  : 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9500 + Math.floor(Math.random() * 200);
const PROFILE = path.join(os.tmpdir(), 'nfself_' + Date.now());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let chrome;

async function fetchJson(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try { const r = await fetch(url); if (r.ok) return await r.json(); } catch (e) { /* retry */ }
    await sleep(150);
  }
  throw new Error('timeout: ' + url);
}

class CDP {
  constructor(url) { this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); }
  open() {
    return new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = (e) => reject(new Error('ws: ' + (e.message || 'err')));
    }).then(() => {
      this.ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (!msg.id) return;
        const p = this.pending.get(msg.id);
        if (!p) return;
        this.pending.delete(msg.id);
        if (msg.error) p.reject(new Error(JSON.stringify(msg.error)));
        else p.resolve(msg.result);
      };
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' ' + JSON.stringify(r.exceptionDetails.exception || {}));
    return r.result ? r.result.value : undefined;
  }
  async waitFor(expr, timeoutMs = 90000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try { if (await this.eval(expr)) return true; } catch (e) { /* page busy */ }
      await sleep(300);
    }
    throw new Error('timeout waiting ' + expr);
  }
}

async function main() {
  chrome = spawn(CHROME, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
    '--no-first-run', '--disable-extensions', '--no-default-browser-check',
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + PROFILE,
    '--window-size=1280,720', 'about:blank'
  ], { stdio: 'ignore' });
  const targets = await fetchJson('http://127.0.0.1:' + PORT + '/json/list');
  const page = targets.find((t) => t.type === 'page');
  const cdp = new CDP(page.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  const url = 'http://127.0.0.1:8123/index.html?selftest=1&mode=' + encodeURIComponent(mode);
  console.log('navigate:', url);
  await cdp.send('Page.navigate', { url });
  await cdp.waitFor('window.__NF_READY === true', 30000);
  await cdp.waitFor('window.__NF_SELFTEST !== undefined', 120000);
  const res = await cdp.eval('window.__NF_SELFTEST');
  console.log(JSON.stringify(res, null, 2));
  const errors = res.errors || 0;
  const ok = mode === 'victory' ? res.victory === 1 : res.gameover === 1;
  console.log(mode === 'victory' ? (ok && !errors ? 'SELFTEST PASS' : 'SELFTEST FAIL') : (ok && !errors ? 'SELFTEST PASS' : 'SELFTEST FAIL'));
  process.exitCode = ok && !errors ? 0 : 1;
}

main().catch((err) => { console.error('SELFTEST RUNNER ERROR', err); process.exitCode = 2; })
  .finally(async () => {
    try { if (chrome) chrome.kill(); } catch (e) { /* ignore */ }
    await sleep(400);
    try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) { /* ignore */ }
  });
