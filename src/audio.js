/* 霓虹拳魂 NEON FIST SOUL — 音频模块（纯 WebAudio 程序化合成，无任何外部音频文件）
 *
 * 对外 API（DEV_CONTRACT.md §1.2 / §2.11 / §6，签名必须保持）：
 *   NF.audio.init()                 初始化（轻量：不创建 AudioContext，等首次手势再创建）
 *   NF.audio.unlock()               首次用户手势解锁（创建/恢复上下文，启动待播音乐）
 *   NF.audio.update(dt)             每帧调用：16 步 lookahead 序列器、场景切换清理
 *   NF.audio.sfx(name)              播放音效：punch heavy hit hitHeavy block whiff ko jump
 *                                   land dash special pickup ui start roar victory gameover wave combo
 *   NF.audio.music(scene)           切换音乐：'none'|'title'|'battle'|'boss'|'victory'|'gameover'
 *   NF.audio.setMuted(bool) -> bool 静音（主 GainNode 平滑归零，不销毁上下文）
 *   NF.audio.toggleMute()   -> bool
 *   NF.audio.duck(bool)             页面隐藏时压低音乐（×0.25）
 *   NF.audio.muted / NF.audio.ready  只读状态（可选扩展）
 *
 * 设计要点：
 *  - 音乐：16 步 lookahead 序列器（提前 0.15s 排程），每场景独立曲目 GainNode，
 *          切场景 0.35s 淡出 + 0.4s 淡入，交叉淡化不爆破；用力度/时值抖动做人性化。
 *  - 音效：分层合成（attack whiff 风声 + impact 噪声/金属 + body 低频），
 *          音高/滤波随机微调，按名称节流 + 全局并发上限，避免爆音。
 *  - 健壮：AudioContext 不可用 / 被自动播放策略阻止 / 无头截图无手势时全部静默降级，
 *          任何公开方法都不抛异常、不阻塞主线程。
 *  - 兼容 OfflineAudioContext：此时没有实时时钟，由 update(dt) 推进虚拟时钟，便于离线数值自检。
 */
window.NF = window.NF || {};

(function () {
  'use strict';

  const NF = window.NF;

  /* ================================================================== *
   * 常量与状态
   * ================================================================== */

  const LOOKAHEAD = 0.15;      // 序列器排程提前量（契约要求 0.1–0.2s）
  const FADE_IN = 0.4;         // 音乐淡入时长
  const FADE_OUT = 0.35;       // 音乐淡出时长
  const MUSIC_LEVEL = 0.62;    // 音乐总线电平
  const SFX_LEVEL = 0.86;      // 音效总线电平
  const DUCK_FACTOR = 0.25;    // duck 时的音乐电平系数
  const MAX_SFX = 12;          // 同时存在的音效调用上限（避免爆音/CPU 峰值）
  const SFX_LEAD = 0.008;      // 音效排程提前量（秒）
  const RESUME_RETRY = 2.0;    // 上下文被挂起后的重试间隔（秒）

  const EPS = 0.0001;          // 指数包络的极小值（不能对 0 做指数斜坡）

  let ctx = null;              // AudioContext | OfflineAudioContext | null
  let inited = false;          // init() 是否调用过
  let disabled = false;        // ?silent=1 或环境不支持时彻底禁用
  let unlocked = false;        // 用户手势解锁过
  let offline = false;         // 是否 OfflineAudioContext（用虚拟时钟）
  let graphReady = false;      // 主图是否搭好

  let master = null;           // 主音量（静音入口）
  let limiter = null;          // 总线限幅（防削波）
  let musicBus = null;         // 音乐总线电平
  let duckGain = null;         // duck 增益（页面隐藏时压低音乐）
  let sfxBus = null;           // 音效总线电平
  let sfxOut = null;           // 当前音效调用的 trim 增益节点（每次 sfx() 临时创建）

  let muted = false;
  let ducked = false;

  let desiredScene = 'none';   // 最近一次 music() 请求的场景
  let activeScene = 'none';    // 正在播放的场景
  let activeSong = null;       // 当前曲目对象
  const fadingSongs = [];      // 正在淡出的旧曲目

  let vclock = 0;              // 仅离线模式：虚拟时钟（由 update(dt) 推进）
  let lastResumeTry = -1e9;    // 上次尝试 resume 的时刻
  let noiseCache = null;       // 共享白噪声缓冲
  let distCache = null;        // 共享失真曲线
  let clipCache = null;        // 共享主总线软削波曲线

  const sfxActive = [];              // 正在发声的音效调用 {end, name}
  const lastSfxAt = Object.create(null); // 每个音效名上次触发时刻（节流）
  const gestureTypes = ['pointerdown', 'keydown', 'touchstart'];
  let gestureHandler = null;
  let gestureBound = false;

  /* ================================================================== *
   * 小工具
   * ================================================================== */

  const clamp = (v, a, b) => (v < a ? a : (v > b ? b : v));
  const rnd = (a, b) => a + Math.random() * (b - a);
  const rr = (spread) => 1 + (Math.random() * 2 - 1) * spread; // 随机倍率（音高/滤波微调）
  const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);        // MIDI 音高 → Hz

  /** 当前音频时刻：实时上下文用 currentTime；离线上下文用 update(dt) 累计的虚拟时钟 */
  function nowTime() {
    if (offline) return vclock;
    return ctx ? ctx.currentTime : 0;
  }

  function safe(fn) {
    try { fn(); } catch (err) { /* 音频异常绝不能打断游戏主循环 */ }
  }

  /* ================================================================== *
   * 底层合成原语
   * ================================================================== */

  function makeNoiseBuffer() {
    if (noiseCache) return noiseCache;
    const sr = (ctx && ctx.sampleRate) || 44100;
    const len = Math.max(1, Math.floor(sr * 0.6));
    const buf = ctx.createBuffer(1, len, sr);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    noiseCache = buf;
    return buf;
  }

  /** 主总线软削波曲线：|x|<=0.7 完全线性（打击瞬态不会被压扁），以上平滑饱和到 <1 防削波。
   *  比 DynamicsCompressor 更适合游戏：零起音/释放时间，不会把短促打击音压小、不产生抽吸感。 */
  function softClipCurve() {
    if (clipCache) return clipCache;
    const n = 2048;
    const knee = 0.7;
    const curve = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * 2 - 1;
      const a = Math.abs(x);
      const y = a <= knee ? a : knee + (1 - knee) * Math.tanh((a - knee) / (1 - knee));
      curve[i] = x < 0 ? -y : y;
    }
    clipCache = curve;
    return curve;
  }

  function distCurve(amount) {
    if (distCache && distCache.amount === amount) return distCache.curve;
    const n = 1024;
    const curve = new Float32Array(n);
    const d = Math.tanh(amount);
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * 2 - 1;
      curve[i] = Math.tanh(x * amount) / d;
    }
    distCache = { amount: amount, curve: curve };
    return curve;
  }

  /** 单振荡器音符（带可选滤波/滑音/声像），返回结束时刻 */
  function tone(t, o) {
    if (!ctx || !o || !o.dest) return t;
    if (t < 0) t = 0; // 离线渲染/首帧时小负偏移钳到 0，避免 start(-x) 抛错
    const dur = Math.max(0.02, o.dur || 0.1);
    const atk = clamp(o.attack == null ? 0.005 : o.attack, 0.0005, dur * 0.6);
    const peak = Math.max(EPS, o.gain == null ? 0.1 : o.gain);
    const src = ctx.createOscillator();
    src.type = o.type || 'square';
    const f0 = Math.max(1, o.freq || 220);
    src.frequency.setValueAtTime(f0, t);
    if (o.to != null && o.to !== f0) {
      const gd = clamp(o.glideDur == null ? dur * 0.9 : o.glideDur, 0.008, dur);
      src.frequency.exponentialRampToValueAtTime(Math.max(1, o.to), t + gd);
    }
    if (o.detune) src.detune.setValueAtTime(o.detune, t);

    let node = src;
    if (o.filter) {
      const f = ctx.createBiquadFilter();
      f.type = o.filter.type || 'lowpass';
      f.frequency.setValueAtTime(Math.max(20, o.filter.freq || 1200), t);
      if (o.filter.to) {
        f.frequency.exponentialRampToValueAtTime(Math.max(20, o.filter.to), t + (o.filter.dur || dur * 0.8));
      }
      if (o.filter.q != null) f.Q.value = o.filter.q;
      node.connect(f);
      node = f;
    }

    const g = ctx.createGain();
    g.gain.setValueAtTime(EPS, t);
    g.gain.exponentialRampToValueAtTime(peak, t + atk);
    if (o.hold != null && dur > atk + 0.02) {
      g.gain.setValueAtTime(peak, t + clamp(o.hold, atk + 0.005, dur - 0.005));
    }
    g.gain.exponentialRampToValueAtTime(EPS, t + dur);
    node.connect(g);

    let out = g;
    if (o.pan != null && ctx.createStereoPanner) {
      const p = ctx.createStereoPanner();
      p.pan.setValueAtTime(clamp(o.pan, -1, 1), t);
      g.connect(p);
      out = p;
    }
    out.connect(o.dest);

    src.start(t);
    src.stop(t + dur + 0.03);
    return t + dur;
  }

  /** 噪声爆发（带可选滤波扫频/声像），返回结束时刻 */
  function noiseBurst(t, o) {
    if (!ctx || !o || !o.dest) return t;
    if (t < 0) t = 0; // 同上
    const dur = Math.max(0.02, o.dur || 0.1);
    const atk = clamp(o.attack == null ? 0.002 : o.attack, 0.0005, dur * 0.7);
    const peak = Math.max(EPS, o.gain == null ? 0.15 : o.gain);
    const src = ctx.createBufferSource();
    src.buffer = makeNoiseBuffer();
    src.loop = true;
    src.playbackRate.setValueAtTime(clamp(o.rate == null ? rnd(0.85, 1.2) : o.rate, 0.2, 4), t);

    const f = ctx.createBiquadFilter();
    f.type = o.type || 'bandpass';
    f.frequency.setValueAtTime(Math.max(20, o.freq || 1200), t);
    if (o.to) {
      f.frequency.exponentialRampToValueAtTime(Math.max(20, o.to), t + (o.filterDur || dur * 0.9));
    }
    f.Q.value = o.q == null ? 1 : o.q;
    src.connect(f);

    const g = ctx.createGain();
    g.gain.setValueAtTime(EPS, t);
    g.gain.exponentialRampToValueAtTime(peak, t + atk);
    g.gain.exponentialRampToValueAtTime(EPS, t + dur);
    f.connect(g);

    let out = g;
    if (o.pan != null && ctx.createStereoPanner) {
      const p = ctx.createStereoPanner();
      p.pan.setValueAtTime(clamp(o.pan, -1, 1), t);
      g.connect(p);
      out = p;
    }
    out.connect(o.dest);

    src.start(t, rnd(0, 0.4));
    src.stop(t + dur + 0.03);
    return t + dur;
  }

  /* ================================================================== *
   * 音频图搭建 / 解锁
   * ================================================================== */

  function bindGestures() {
    if (gestureBound || typeof window.addEventListener !== 'function') return;
    gestureBound = true;
    gestureHandler = function () {
      safe(function () { api.unlock(); });
      if (unlocked) unbindGestures();
    };
    for (let i = 0; i < gestureTypes.length; i++) {
      window.addEventListener(gestureTypes[i], gestureHandler, true);
    }
  }

  function unbindGestures() {
    if (!gestureBound || !gestureHandler) return;
    gestureBound = false;
    for (let i = 0; i < gestureTypes.length; i++) {
      window.removeEventListener(gestureTypes[i], gestureHandler, true);
    }
    gestureHandler = null;
  }

  function createContext() {
    const W = window;
    const AC = W.AudioContext || W.webkitAudioContext;
    if (!AC) { disabled = true; return; }
    let c = null;
    try {
      c = new AC({ latencyHint: 'interactive' });
    } catch (err) {
      try { c = new AC(); } catch (err2) { c = null; }
    }
    if (!c) { disabled = true; return; }
    ctx = c;
    /* OfflineAudioContext 没有实时时钟：用 update(dt) 推进虚拟时钟 */
    offline = (typeof ctx.startRendering === 'function');
    noiseCache = null;
    distCache = null;
    vclock = 0;
  }

  function buildGraph() {
    if (!ctx || graphReady) return;
    master = ctx.createGain();
    master.gain.value = muted ? 0 : 1;

    /* 主总线软削波限幅（WaveShaper）：零起音/释放时间，短促打击瞬态不被压扁，峰值恒 <1 防削波 */
    limiter = ctx.createWaveShaper();
    limiter.curve = softClipCurve();
    limiter.oversample = '2x';

    master.connect(limiter);
    limiter.connect(ctx.destination);

    musicBus = ctx.createGain();
    musicBus.gain.value = MUSIC_LEVEL;
    musicBus.connect(master);

    duckGain = ctx.createGain();
    duckGain.gain.value = ducked ? DUCK_FACTOR : 1;
    duckGain.connect(musicBus);

    sfxBus = ctx.createGain();
    sfxBus.gain.value = SFX_LEVEL;
    sfxBus.connect(master);

    graphReady = true;
  }

  function applyMuted(immediate) {
    if (!master) return;
    const now = nowTime();
    safe(function () {
      const g = master.gain;
      const cur = g.value;
      const target = muted ? 0 : 1;
      g.cancelScheduledValues(now);
      if (immediate) {
        g.setValueAtTime(target, now);
      } else {
        g.setValueAtTime(Math.max(0, cur), now);
        g.linearRampToValueAtTime(target, now + 0.12);
      }
    });
  }

  function applyDuck(immediate) {
    if (!duckGain) return;
    const now = nowTime();
    safe(function () {
      const g = duckGain.gain;
      const cur = g.value;
      const target = ducked ? DUCK_FACTOR : 1;
      g.cancelScheduledValues(now);
      if (immediate) {
        g.setValueAtTime(target, now);
      } else {
        g.setValueAtTime(Math.max(EPS, cur), now);
        g.linearRampToValueAtTime(target, now + 0.15);
      }
    });
  }

  /* ================================================================== *
   * 音乐：音色与节奏型
   * ================================================================== */

  /* ---- 鼓组 ---- */

  function pKick(song, t, g) {
    g = g == null ? 1 : g;
    tone(t, {
      type: 'sine', freq: 150, to: 44, glideDur: 0.1, dur: 0.22,
      gain: 0.82 * g, attack: 0.002, dest: song.bus.drums
    });
    noiseBurst(t, {
      type: 'highpass', freq: 1400, dur: 0.026, gain: 0.15 * g,
      attack: 0.001, dest: song.bus.drums
    });
  }

  function pSnare(song, t, g) {
    g = g == null ? 1 : g;
    noiseBurst(t, {
      type: 'bandpass', freq: 1900, q: 0.8, dur: 0.14, gain: 0.38 * g,
      attack: 0.001, dest: song.bus.drums
    });
    noiseBurst(t, {
      type: 'highpass', freq: 6200, dur: 0.05, gain: 0.12 * g,
      attack: 0.001, dest: song.bus.drums
    });
    tone(t, {
      type: 'triangle', freq: 220, to: 128, glideDur: 0.06, dur: 0.09,
      gain: 0.2 * g, attack: 0.001, dest: song.bus.drums
    });
  }

  function pHat(song, t, g, open) {
    g = g == null ? 1 : g;
    noiseBurst(t, {
      type: 'highpass', freq: open ? 6600 : 8200,
      dur: open ? 0.22 : 0.045, gain: (open ? 0.15 : 0.1) * g,
      attack: 0.001, dest: song.bus.drums, pan: rnd(-0.18, 0.18)
    });
  }

  function pCrash(song, t, g) {
    g = g == null ? 1 : g;
    noiseBurst(t, {
      type: 'highpass', freq: 4200, dur: 1.0, gain: 0.18 * g,
      attack: 0.002, dest: song.bus.drums, pan: rnd(-0.25, -0.05)
    });
    noiseBurst(t, {
      type: 'bandpass', freq: 7600, q: 2, dur: 0.6, gain: 0.06 * g,
      attack: 0.002, dest: song.bus.drums
    });
  }

  function pTom(song, t, midi, g) {
    g = g == null ? 1 : g;
    const f = mtof(midi);
    tone(t, {
      type: 'sine', freq: f, to: f * 0.6, glideDur: 0.12, dur: 0.2,
      gain: 0.3 * g, attack: 0.002, dest: song.bus.drums
    });
  }

  /* ---- 和声/旋律 ---- */

  function pBass(song, t, midi, durSec, g, bright) {
    g = g == null ? 1 : g;
    const f = mtof(midi);
    const peak = 0.3 * g;
    tone(t, {
      type: 'sawtooth', freq: f, dur: durSec,
      gain: peak, attack: 0.004, hold: Math.max(0.02, durSec * 0.4),
      filter: { type: 'lowpass', freq: bright ? 1500 : 900, to: 200, q: 1.5, dur: durSec * 0.85 },
      dest: song.bus.bass
    });
    tone(t, {
      type: 'sine', freq: f, dur: durSec * 1.05,
      gain: peak * 0.85, attack: 0.006, hold: Math.max(0.02, durSec * 0.5),
      dest: song.bus.bass
    });
  }

  function pLead(song, t, midi, durSec, g, opts) {
    g = g == null ? 1 : g;
    opts = opts || {};
    const f = mtof(midi);
    const cut = opts.cut || 2600;
    const type = opts.type || 'square';
    tone(t, {
      type: type, freq: f, dur: durSec, gain: 0.15 * g, attack: 0.008,
      hold: Math.max(0.02, durSec * 0.5),
      filter: { type: 'lowpass', freq: cut, q: 0.8 },
      dest: song.bus.lead
    });
    tone(t, {
      type: type, freq: f, detune: opts.detune == null ? 8 : opts.detune,
      dur: durSec, gain: 0.085 * g, attack: 0.012,
      hold: Math.max(0.02, durSec * 0.45),
      filter: { type: 'lowpass', freq: cut * 0.8, q: 0.7 },
      dest: song.bus.lead
    });
  }

  /** Boss 用失真 lead：双振荡器 → 低通 → WaveShaper → 包络 */
  function pLeadDist(song, t, midi, durSec, g) {
    g = g == null ? 1 : g;
    const f = mtof(midi);
    const o1 = ctx.createOscillator();
    o1.type = 'sawtooth';
    o1.frequency.setValueAtTime(f, t);
    o1.detune.setValueAtTime(-9, t);
    const o2 = ctx.createOscillator();
    o2.type = 'square';
    o2.frequency.setValueAtTime(f, t);
    o2.detune.setValueAtTime(7, t);

    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.setValueAtTime(2600, t);
    lp.frequency.exponentialRampToValueAtTime(1100, t + Math.max(0.05, durSec * 0.8));
    lp.Q.value = 1.2;

    const shaper = ctx.createWaveShaper();
    shaper.curve = distCurve(3.2);
    shaper.oversample = '2x';

    const env = ctx.createGain();
    const atk = 0.006;
    const peak = Math.max(EPS, 0.2 * g);
    env.gain.setValueAtTime(EPS, t);
    env.gain.exponentialRampToValueAtTime(peak, t + atk);
    if (durSec > atk + 0.03) {
      env.gain.setValueAtTime(peak, t + clamp(durSec * 0.6, atk + 0.005, durSec - 0.005));
    }
    env.gain.exponentialRampToValueAtTime(EPS, t + durSec);

    o1.connect(lp);
    o2.connect(lp);
    lp.connect(shaper);
    shaper.connect(env);
    env.connect(song.bus.lead);
    o1.start(t); o2.start(t);
    o1.stop(t + durSec + 0.03); o2.stop(t + durSec + 0.03);
  }

  function pArp(song, t, midi, g, opts) {
    g = g == null ? 1 : g;
    opts = opts || {};
    tone(t, {
      type: opts.type || 'square', freq: mtof(midi), dur: opts.dur || 0.1,
      gain: 0.042 * g, attack: 0.002,
      filter: { type: 'lowpass', freq: opts.cut || 4200, q: 0.7 },
      dest: song.bus.arp,
      pan: opts.pan
    });
  }

  function pPad(song, t, notes, durSec, g, cut) {
    g = g == null ? 1 : g;
    if (!notes || !notes.length) return;
    const n = notes.length;
    for (let i = 0; i < n; i++) {
      const f = mtof(notes[i]);
      const pan = n > 1 ? (-0.35 + 0.7 * (i / (n - 1))) : 0;
      tone(t, {
        type: 'sawtooth', freq: f, detune: -6, dur: durSec,
        gain: 0.048 * g, attack: durSec * 0.22,
        hold: durSec * 0.68,
        filter: { type: 'lowpass', freq: cut || 900, q: 0.6 },
        dest: song.bus.pad, pan: pan
      });
      tone(t, {
        type: 'triangle', freq: f, detune: 5, dur: durSec,
        gain: 0.05 * g, attack: durSec * 0.2,
        hold: durSec * 0.72,
        dest: song.bus.pad, pan: -pan
      });
    }
  }

  /* ================================================================== *
   * 音乐：曲目数据
   * ================================================================== */

  // title —— A 小调暗色氛围（Am9 / Fmaj7 / Dm9 / E7b9），BPM 92
  const TITLE_BARS = [
    { root: 33, pad: [57, 60, 64, 67, 71], arp: [72, 76, 79, 83] },
    { root: 41, pad: [53, 57, 60, 64, 67], arp: [69, 72, 76, 79] },
    { root: 38, pad: [50, 53, 57, 60, 64], arp: [74, 77, 81, 84] },
    { root: 40, pad: [52, 56, 59, 62, 65], arp: [71, 74, 77, 80] }
  ];
  const TITLE_ARP_STEPS = [3, 6, 10, 13];

  // battle —— E 小调驱动（Em / C / D / B），BPM 128
  const BATTLE_BARS = [
    { root: 40, arp: [64, 67, 71, 76], lead: [[0, 64, 3], [4, 67, 1], [6, 71, 2], [8, 69, 4], [12, 71, 2], [14, 74, 2]] },
    { root: 36, arp: [60, 64, 67, 72], lead: [[0, 72, 3], [4, 71, 1], [6, 67, 2], [8, 64, 4], [12, 67, 2], [14, 69, 2]] },
    { root: 38, arp: [62, 66, 69, 74], lead: [[0, 74, 3], [4, 72, 1], [6, 69, 2], [8, 66, 4], [12, 69, 2], [14, 72, 2]] },
    { root: 35, arp: [59, 63, 66, 71], lead: [[0, 71, 4], [4, 75, 1], [6, 78, 2], [8, 76, 3], [12, 74, 2], [14, 71, 2]] }
  ];
  const BATTLE_BASS_OCT = [0, 0, 12, 0, 0, 12, 0, 12];

  // boss —— D 和声小调压迫感（Dm / Bb / Gm / A），BPM 140
  const BOSS_BARS = [
    { root: 38, arp: [50, 53, 57], lead: [[0, 62, 2], [2, 65, 1], [3, 69, 1], [4, 65, 2], [6, 62, 2], [8, 57, 4], [12, 62, 2], [14, 65, 2]] },
    { root: 34, arp: [46, 50, 53], lead: [[0, 58, 2], [2, 62, 1], [3, 65, 1], [4, 62, 2], [6, 58, 2], [8, 53, 4], [12, 58, 2], [14, 62, 2]] },
    { root: 43, arp: [43, 46, 50], lead: [[0, 55, 2], [2, 58, 1], [3, 62, 1], [4, 58, 2], [6, 55, 2], [8, 50, 4], [12, 55, 2], [14, 58, 2]] },
    { root: 33, arp: [45, 49, 52], lead: [[0, 57, 2], [2, 61, 1], [3, 64, 1], [4, 61, 2], [6, 57, 2], [8, 52, 4], [12, 57, 2], [14, 61, 2]] }
  ];

  // victory —— C 大调号角（C / Am / F / G），BPM 132
  const VICTORY_BARS = [
    { root: 36, chord: [60, 64, 67], lead: [[0, 72, 2], [2, 76, 2], [4, 79, 4], [8, 76, 2], [10, 79, 2], [12, 84, 4]] },
    { root: 45, chord: [57, 60, 64], lead: [[0, 81, 2], [2, 79, 2], [4, 76, 4], [8, 72, 4]] },
    { root: 41, chord: [53, 57, 60], lead: [[0, 74, 2], [2, 77, 2], [4, 81, 4], [8, 77, 2], [10, 81, 2], [12, 86, 4]] },
    { root: 43, chord: [55, 59, 62], lead: [[0, 79, 4], [4, 76, 2], [6, 72, 4], [10, 84, 4]] }
  ];

  // gameover —— D 小调下行短句，BPM 72（两小节乐句 + 两小节留白）
  const GAMEOVER_DESC = [[0, 62, 3], [4, 60, 3], [8, 58, 3], [12, 57, 4]];
  const GAMEOVER_BARS = [
    { root: 38, chord: [50, 53, 57] },
    { root: 38, chord: [50, 53, 57] },
    { root: null, chord: null },
    { root: null, chord: null }
  ];

  /* ================================================================== *
   * 音乐：16 步序列器（每场景一个 step 回调）
   * ================================================================== */

  function stepTitle(song, t, step, bar) {
    const barDef = TITLE_BARS[bar % TITLE_BARS.length];
    const barDur = song.stepDur * 16;
    if (step === 0) pPad(song, t, barDef.pad, barDur * 1.04, 1, 1000);
    if (step === 0 || step === 8) {
      tone(t, {
        type: 'sine', freq: mtof(barDef.root), dur: 0.78, gain: 0.38,
        attack: 0.008, hold: 0.2, dest: song.bus.bass
      });
      tone(t, {
        type: 'triangle', freq: mtof(barDef.root), dur: 0.55, gain: 0.13,
        attack: 0.01, filter: { type: 'lowpass', freq: 420, q: 0.7 },
        dest: song.bus.bass
      });
    }
    const idx = TITLE_ARP_STEPS.indexOf(step);
    if (idx >= 0) {
      const notes = barDef.arp;
      const note = notes[(idx + bar) % notes.length];
      pArp(song, t, note, 0.9, { dur: 0.5, cut: 5200, type: 'triangle', pan: rnd(-0.35, 0.35) });
    }
  }

  function stepBattle(song, t, step, bar) {
    const barDef = BATTLE_BARS[bar % 4];
    const bar4 = bar % 4;
    const sd = song.stepDur;

    if (step === 0 || step === 8 || (step === 6 && bar4 % 2 === 0) || (step === 14 && bar4 === 3)) {
      pKick(song, t, step === 0 ? 1 : 0.88);
    }
    if (step === 4 || step === 12) pSnare(song, t, 1);
    if (step % 2 === 0) pHat(song, t, step % 4 === 0 ? 1 : 0.64, step === 14 && bar4 % 2 === 1);
    if (bar4 === 0 && step === 0) pCrash(song, t, 0.8);

    if (step % 2 === 0) {
      const i = step / 2;
      pBass(song, t, barDef.root + BATTLE_BASS_OCT[i], sd * 1.75, 1);
    }

    for (let i = 0; i < barDef.lead.length; i++) {
      const n = barDef.lead[i];
      if (n[0] === step) pLead(song, t, n[1], n[2] * sd * 0.9, 1);
    }

    pArp(song, t, barDef.arp[step % barDef.arp.length] + 12, 0.55, { dur: 0.085, cut: 5000 });

    if (bar4 === 3 && (step === 13 || step === 15)) pSnare(song, t, 0.55);
  }

  function stepBoss(song, t, step, bar) {
    const barDef = BOSS_BARS[bar % 4];
    const bar4 = bar % 4;
    const sd = song.stepDur;

    if (step === 0 || step === 3 || step === 6 || step === 8 || step === 11 || step === 14) {
      pKick(song, t, step === 0 || step === 8 ? 1 : 0.72);
    }
    if (step === 4 || step === 12) pSnare(song, t, 1.05);
    pHat(song, t, step % 4 === 0 ? 1 : (step % 2 === 0 ? 0.6 : 0.38), step === 14 && bar4 % 2 === 1);
    if (bar4 === 0 && step === 0) pCrash(song, t, 1);
    if (bar4 === 3 && step >= 13) pTom(song, t, 43 - (step - 13) * 3, 0.8);

    if (step % 2 === 0) pBass(song, t, barDef.root, sd * 1.6, 1.05, true);
    if (step === 3 || step === 7 || step === 11 || step === 15) {
      pBass(song, t, barDef.root + 12, sd * 0.8, 0.66, true);
    }

    for (let i = 0; i < barDef.lead.length; i++) {
      const n = barDef.lead[i];
      if (n[0] === step) pLeadDist(song, t, n[1], n[2] * sd * 0.92, 1);
    }

    if (step === 0) pStabDist(song, t, [barDef.root + 12, barDef.root + 19], sd * 2.2, 0.9);
    if (step % 2 === 1) pArp(song, t, barDef.arp[step % 3] + 24, 0.32, { dur: 0.06, cut: 6000 });
  }

  /** 失真强力和弦重音 */
  function pStabDist(song, t, notes, durSec, g) {
    for (let i = 0; i < notes.length; i++) {
      pLeadDist(song, t, notes[i], durSec, (g == null ? 1 : g) * 0.55);
    }
  }

  function stepVictory(song, t, step, bar) {
    const barDef = VICTORY_BARS[bar % 4];
    const bar4 = bar % 4;
    const sd = song.stepDur;

    if (step === 0 || step === 8) pKick(song, t, 0.9);
    if (step === 4 || step === 12) pSnare(song, t, 0.9);
    if (step % 2 === 0) pHat(song, t, 0.66, false);
    if (step === 0 && (bar4 === 0 || bar4 === 2)) pCrash(song, t, 0.8);

    if (step === 0 || step === 8) pBass(song, t, barDef.root, sd * 3.6, 0.95);
    if (step === 4 || step === 12) pBass(song, t, barDef.root + 7, sd * 2.2, 0.62);

    for (let i = 0; i < barDef.lead.length; i++) {
      const n = barDef.lead[i];
      if (n[0] === step) pLead(song, t, n[1], n[2] * sd * 0.95, 1.15, { type: 'sawtooth', cut: 3400 });
    }
    if (step === 0) {
      for (let i = 0; i < barDef.chord.length; i++) {
        pLead(song, t, barDef.chord[i], sd * 2.0, 0.5, { type: 'sawtooth', cut: 2200, detune: 12 });
      }
    }
  }

  function stepGameover(song, t, step, bar) {
    const bar4 = bar % 4;
    const barDef = GAMEOVER_BARS[bar4];
    const sd = song.stepDur;

    if (bar4 === 0) {
      for (let i = 0; i < GAMEOVER_DESC.length; i++) {
        const n = GAMEOVER_DESC[i];
        if (n[0] !== step) continue;
        pLead(song, t, n[1], n[2] * sd * 0.95, 0.85, { type: 'triangle', cut: 1700, detune: 0 });
        tone(t, {
          type: 'sine', freq: mtof(n[1] - 12), dur: n[2] * sd,
          gain: 0.16, attack: 0.02, hold: n[2] * sd * 0.5,
          dest: song.bus.bass
        });
      }
    }
    if (bar4 === 1 && step === 0) {
      pPad(song, t, barDef.chord, sd * 16 * 1.1, 1.2, 700);
      tone(t, {
        type: 'sine', freq: mtof(barDef.root), dur: sd * 10,
        gain: 0.32, attack: 0.02, hold: sd * 4, dest: song.bus.bass
      });
    }
  }

  /* ================================================================== *
   * 音乐：曲目定义 / 创建 / 切换 / 调度
   * ================================================================== */

  const SONG_DEFS = {
    title: {
      bpm: 92, level: 0.95,
      delay: 0.489, feedback: 0.45, wet: 0.42, delayTone: 1800,
      mix: { drums: 0, bass: 0.8, lead: 0.5, arp: 0.7, pad: 0.75 },
      step: stepTitle
    },
    battle: {
      bpm: 128, level: 0.92,
      delay: 0.352, feedback: 0.28, wet: 0.22, delayTone: 2600,
      mix: { drums: 0.95, bass: 0.8, lead: 0.7, arp: 0.5, pad: 0 },
      step: stepBattle
    },
    boss: {
      bpm: 140, level: 0.85,
      delay: 0.321, feedback: 0.3, wet: 0.2, delayTone: 2200,
      mix: { drums: 1, bass: 0.85, lead: 0.75, arp: 0.45, pad: 0 },
      step: stepBoss
    },
    victory: {
      bpm: 132, level: 0.92,
      delay: 0.34, feedback: 0.25, wet: 0.22, delayTone: 2600,
      mix: { drums: 0.9, bass: 0.75, lead: 0.8, arp: 0, pad: 0 },
      step: stepVictory
    },
    gameover: {
      bpm: 72, level: 0.95,
      delay: 0.55, feedback: 0.35, wet: 0.3, delayTone: 1400,
      mix: { drums: 0, bass: 0.8, lead: 0.65, arp: 0, pad: 0.6 },
      step: stepGameover
    }
  };

  function makeSong(scene, def) {
    const t0 = nowTime();
    const nodes = [];

    const out = ctx.createGain();
    out.gain.value = 0;
    out.connect(duckGain);
    nodes.push(out);

    /* 附点八分延迟（合成器空间的来源），随曲目一起销毁 */
    const delayIn = ctx.createGain();
    delayIn.gain.value = 1;
    const delay = ctx.createDelay(2.5);
    delay.delayTime.value = def.delay;
    const toneLP = ctx.createBiquadFilter();
    toneLP.type = 'lowpass';
    toneLP.frequency.value = def.delayTone;
    const feedback = ctx.createGain();
    feedback.gain.value = def.feedback;
    const wet = ctx.createGain();
    wet.gain.value = def.wet;
    delayIn.connect(delay);
    delay.connect(toneLP);
    toneLP.connect(feedback);
    feedback.connect(delay);
    toneLP.connect(wet);
    wet.connect(out);
    nodes.push(delayIn, delay, toneLP, feedback, wet);

    function bus(level) {
      const g = ctx.createGain();
      g.gain.value = level;
      g.connect(out);
      nodes.push(g);
      return g;
    }
    function send(from, amount) {
      const g = ctx.createGain();
      g.gain.value = amount;
      from.connect(g);
      g.connect(delayIn);
      nodes.push(g);
    }

    const mix = def.mix;
    const song = {
      scene: scene,
      def: def,
      out: out,
      bus: {
        drums: bus(mix.drums),
        bass: bus(mix.bass),
        lead: bus(mix.lead),
        arp: bus(mix.arp),
        pad: bus(mix.pad)
      },
      stepDur: 60 / def.bpm / 4,
      nextTime: t0 + 0.06,
      step: 0,
      stopAt: Infinity,
      nodes: nodes
    };
    send(song.bus.lead, 0.3);
    send(song.bus.arp, 0.42);
    send(song.bus.pad, 0.22);
    return song;
  }

  function cleanupSong(song) {
    if (!song) return;
    /* 离线渲染没有"实时播放完毕"的概念，渲染在模拟结束后才进行：
     * 此处若断开连接会让已排程的整段时间线丢失，因此离线模式交给上下文一次性渲染后回收。 */
    if (offline) return;
    safe(function () {
      song.out.gain.value = 0;
      song.out.disconnect();
    });
    for (let i = 0; i < song.nodes.length; i++) {
      safe(function () { song.nodes[i].disconnect(); });
    }
    song.nodes.length = 0;
  }

  function fadeOutSong(song, now) {
    song.stopAt = now + FADE_OUT + 0.5;
    fadingSongs.push(song);
    safe(function () {
      const g = song.out.gain;
      const cur = Math.max(0, g.value);
      g.cancelScheduledValues(now);
      g.setValueAtTime(cur, now);
      g.linearRampToValueAtTime(0, now + FADE_OUT);
    });
  }

  /** 切场景：旧曲淡出 + 新曲淡入（交叉淡化，避免切歌爆音） */
  function switchScene(scene) {
    if (!ctx || !unlocked || !graphReady) return;
    if (scene === activeScene) return;
    const now = nowTime();

    if (activeSong) {
      fadeOutSong(activeSong, now);
      activeSong = null;
    }
    activeScene = scene;

    if (scene === 'none' || !SONG_DEFS[scene]) {
      activeScene = 'none';
      return;
    }
    const def = SONG_DEFS[scene];
    const song = makeSong(scene, def);
    activeSong = song;
    safe(function () {
      const g = song.out.gain;
      g.cancelScheduledValues(now);
      g.setValueAtTime(0, now);
      g.linearRampToValueAtTime(def.level, now + FADE_IN);
    });
  }

  function scheduleStep(song, t) {
    const step = song.step % 16;
    const bar = Math.floor(song.step / 16);
    song.def.step(song, t, step, bar);
  }

  function scheduleSong(song, now) {
    if (!song) return;
    /* 掉帧/后台标签页回来：跳到下一个小节，避免一口气补排大量音符 */
    if (song.nextTime < now - 0.15) {
      song.step += (16 - (song.step % 16)) % 16;
      song.nextTime = now + 0.03;
    }
    const horizon = now + LOOKAHEAD;
    let guard = 0;
    while (song.nextTime < horizon && guard++ < 64) {
      scheduleStep(song, song.nextTime);
      song.step++;
      song.nextTime += song.stepDur;
    }
  }

  /* ================================================================== *
   * 音效
   * ================================================================== */

  const SFX_DEFS = {
    /* 打击音：风声 whiff + 冲击 impact + 低频 body 三层 */
    punch: function (t) {
      const p = rr(0.07);
      noiseBurst(t - 0.008, {
        type: 'bandpass', freq: 900 * p, to: 300, q: 0.9, dur: 0.075,
        gain: 0.085, attack: 0.003, dest: sfxOut, pan: rnd(-0.12, 0.12)
      });
      noiseBurst(t, {
        type: 'bandpass', freq: 1700 * p, q: 0.9, dur: 0.085,
        gain: 0.27, attack: 0.001, dest: sfxOut
      });
      tone(t, {
        type: 'square', freq: 1300 * p, to: 260, glideDur: 0.03, dur: 0.035,
        gain: 0.06, attack: 0.001, filter: { type: 'lowpass', freq: 5200 },
        dest: sfxOut
      });
      tone(t, {
        type: 'sine', freq: 165, to: 54, glideDur: 0.1, dur: 0.17,
        gain: 0.38, attack: 0.002, dest: sfxOut
      });
    },

    heavy: function (t) {
      const p = rr(0.06);
      noiseBurst(t - 0.012, {
        type: 'bandpass', freq: 700 * p, to: 260, q: 0.8, dur: 0.12,
        gain: 0.1, attack: 0.004, dest: sfxOut
      });
      noiseBurst(t, {
        type: 'lowpass', freq: 2400 * p, to: 400, dur: 0.18,
        gain: 0.32, attack: 0.001, dest: sfxOut
      });
      tone(t, {
        type: 'sawtooth', freq: 220 * p, to: 70, glideDur: 0.12, dur: 0.2,
        gain: 0.13, attack: 0.002,
        filter: { type: 'lowpass', freq: 2400, to: 600 },
        dest: sfxOut
      });
      tone(t, {
        type: 'sine', freq: 110, to: 34, glideDur: 0.22, dur: 0.3,
        gain: 0.44, attack: 0.003, dest: sfxOut
      });
      noiseBurst(t + 0.005, {
        type: 'bandpass', freq: 5200, q: 6, dur: 0.12,
        gain: 0.055, attack: 0.001, dest: sfxOut
      });
    },

    hit: function (t) {
      const p = rr(0.08);
      noiseBurst(t, {
        type: 'bandpass', freq: 1500 * p, q: 1.1, dur: 0.075,
        gain: 0.23, attack: 0.001, dest: sfxOut, pan: rnd(-0.1, 0.1)
      });
      tone(t, {
        type: 'triangle', freq: 190 * p, to: 70, glideDur: 0.08, dur: 0.12,
        gain: 0.26, attack: 0.001, dest: sfxOut
      });
      tone(t, {
        type: 'square', freq: 900 * p, to: 200, glideDur: 0.03, dur: 0.03,
        gain: 0.045, attack: 0.001,
        filter: { type: 'lowpass', freq: 4000 }, dest: sfxOut
      });
    },

    hitHeavy: function (t) {
      noiseBurst(t, {
        type: 'lowpass', freq: 2200, to: 500, dur: 0.16,
        gain: 0.28, attack: 0.001, dest: sfxOut
      });
      tone(t, {
        type: 'sine', freq: 108, to: 40, glideDur: 0.16, dur: 0.26,
        gain: 0.44, attack: 0.002, dest: sfxOut
      });
      noiseBurst(t, {
        type: 'bandpass', freq: 3000 * rr(0.1), q: 4, dur: 0.18,
        gain: 0.065, attack: 0.001, dest: sfxOut
      });
      tone(t + 0.01, {
        type: 'square', freq: 760 * rr(0.05), to: 180, glideDur: 0.04, dur: 0.05,
        gain: 0.05, attack: 0.001,
        filter: { type: 'lowpass', freq: 3000 }, dest: sfxOut
      });
    },

    block: function (t) {
      noiseBurst(t, {
        type: 'highpass', freq: 2600, dur: 0.07,
        gain: 0.17, attack: 0.001, dest: sfxOut
      });
      tone(t, {
        type: 'square', freq: 760 * rr(0.06), to: 620, dur: 0.06,
        gain: 0.09, attack: 0.001,
        filter: { type: 'bandpass', freq: 1800, q: 3 }, dest: sfxOut
      });
      tone(t, {
        type: 'triangle', freq: 2400, dur: 0.12,
        gain: 0.08, attack: 0.001, dest: sfxOut
      });
    },

    whiff: function (t) {
      noiseBurst(t, {
        type: 'bandpass', freq: 500, to: 1600, q: 1.4, dur: 0.14,
        gain: 0.15, attack: 0.02, dest: sfxOut, pan: rnd(-0.2, 0.2)
      });
      noiseBurst(t + 0.02, {
        type: 'highpass', freq: 1800, dur: 0.1,
        gain: 0.045, attack: 0.02, dest: sfxOut
      });
    },

    ko: function (t) {
      noiseBurst(t, {
        type: 'lowpass', freq: 3000, to: 180, dur: 0.55,
        gain: 0.38, attack: 0.002, dest: sfxOut
      });
      tone(t, {
        type: 'sine', freq: 120, to: 26, glideDur: 0.5, dur: 0.8,
        gain: 0.55, attack: 0.003, dest: sfxOut
      });
      tone(t, {
        type: 'sawtooth', freq: 300, to: 60, glideDur: 0.45, dur: 0.6,
        gain: 0.11, attack: 0.004,
        filter: { type: 'lowpass', freq: 1200, to: 200 }, dest: sfxOut
      });
      noiseBurst(t + 0.02, {
        type: 'bandpass', freq: 4200, q: 3, dur: 0.5,
        gain: 0.075, attack: 0.002, dest: sfxOut
      });
      tone(t + 0.12, {
        type: 'square', freq: 440, to: 110, glideDur: 0.35, dur: 0.4,
        gain: 0.06, attack: 0.005,
        filter: { type: 'lowpass', freq: 2000, to: 600 }, dest: sfxOut
      });
    },

    jump: function (t) {
      noiseBurst(t, {
        type: 'bandpass', freq: 320, to: 1500, q: 1.2, dur: 0.16,
        gain: 0.11, attack: 0.01, dest: sfxOut
      });
      tone(t, {
        type: 'triangle', freq: 300, to: 620, glideDur: 0.15, dur: 0.18,
        gain: 0.09, attack: 0.004,
        filter: { type: 'lowpass', freq: 1800 }, dest: sfxOut
      });
    },

    land: function (t) {
      noiseBurst(t, {
        type: 'lowpass', freq: 1200, to: 200, dur: 0.12,
        gain: 0.18, attack: 0.001, dest: sfxOut
      });
      tone(t, {
        type: 'sine', freq: 130, to: 46, glideDur: 0.1, dur: 0.2,
        gain: 0.32, attack: 0.002, dest: sfxOut
      });
    },

    dash: function (t) {
      noiseBurst(t, {
        type: 'bandpass', freq: 400, to: 2600, q: 1.1, dur: 0.22,
        gain: 0.18, attack: 0.008, dest: sfxOut, pan: rnd(-0.25, 0.25)
      });
      noiseBurst(t + 0.03, {
        type: 'highpass', freq: 2200, dur: 0.14,
        gain: 0.055, attack: 0.01, dest: sfxOut
      });
    },

    special: function (t) {
      /* 充能 0.5s → 爆发 */
      tone(t, {
        type: 'sawtooth', freq: 110, to: 880, glideDur: 0.5, dur: 0.6,
        gain: 0.12, attack: 0.03,
        filter: { type: 'bandpass', freq: 400, to: 3200, q: 2.5, dur: 0.5 },
        dest: sfxOut
      });
      noiseBurst(t, {
        type: 'bandpass', freq: 600, to: 5200, q: 2, dur: 0.55,
        gain: 0.075, attack: 0.05, dest: sfxOut
      });
      const b = t + 0.5;
      noiseBurst(b, {
        type: 'lowpass', freq: 5200, to: 300, dur: 0.5,
        gain: 0.4, attack: 0.002, dest: sfxOut
      });
      tone(b, {
        type: 'sine', freq: 150, to: 30, glideDur: 0.35, dur: 0.6,
        gain: 0.5, attack: 0.002, dest: sfxOut
      });
      tone(b, {
        type: 'square', freq: 600, to: 120, glideDur: 0.25, dur: 0.4,
        gain: 0.1, attack: 0.002,
        filter: { type: 'lowpass', freq: 3000, to: 800 }, dest: sfxOut
      });
      noiseBurst(b, {
        type: 'bandpass', freq: 3600, q: 4, dur: 0.45,
        gain: 0.09, attack: 0.002, dest: sfxOut
      });
    },

    pickup: function (t) {
      const notes = [84, 88, 91];
      for (let i = 0; i < notes.length; i++) {
        tone(t + i * 0.055, {
          type: 'square', freq: mtof(notes[i]), dur: 0.12,
          gain: 0.08, attack: 0.002,
          filter: { type: 'lowpass', freq: 6000 }, dest: sfxOut
        });
      }
      tone(t + 0.11, {
        type: 'sine', freq: mtof(96), dur: 0.18,
        gain: 0.055, attack: 0.002, dest: sfxOut
      });
    },

    ui: function (t) {
      tone(t, {
        type: 'square', freq: 880, to: 1175, glideDur: 0.03, dur: 0.05,
        gain: 0.07, attack: 0.001,
        filter: { type: 'lowpass', freq: 4000 }, dest: sfxOut
      });
      tone(t + 0.05, {
        type: 'square', freq: 1320, dur: 0.05,
        gain: 0.045, attack: 0.001,
        filter: { type: 'lowpass', freq: 5000 }, dest: sfxOut
      });
    },

    start: function (t) {
      const seq = [72, 76, 79, 84];
      for (let i = 0; i < seq.length; i++) {
        tone(t + i * 0.08, {
          type: 'square', freq: mtof(seq[i]), dur: 0.18,
          gain: 0.09, attack: 0.003,
          filter: { type: 'lowpass', freq: 3600 }, dest: sfxOut
        });
        tone(t + i * 0.08, {
          type: 'triangle', freq: mtof(seq[i]) / 2, dur: 0.2,
          gain: 0.055, attack: 0.003, dest: sfxOut
        });
      }
      noiseBurst(t + 0.24, {
        type: 'highpass', freq: 5200, dur: 0.5,
        gain: 0.06, attack: 0.01, dest: sfxOut
      });
    },

    roar: function (t) {
      const f = 95 * rr(0.05);
      tone(t, {
        type: 'sawtooth', freq: f, to: f * 0.72, glideDur: 0.75, dur: 0.85,
        gain: 0.22, attack: 0.06,
        filter: { type: 'lowpass', freq: 700, to: 300, q: 3 }, dest: sfxOut
      });
      tone(t, {
        type: 'sawtooth', freq: f * 1.07, to: f * 0.75, glideDur: 0.7, dur: 0.8,
        gain: 0.1, attack: 0.08,
        filter: { type: 'lowpass', freq: 520, to: 260, q: 2 }, dest: sfxOut
      });
      tone(t, {
        type: 'square', freq: f * 0.5, to: f * 0.42, glideDur: 0.7, dur: 0.8,
        gain: 0.08, attack: 0.08,
        filter: { type: 'lowpass', freq: 400 }, dest: sfxOut
      });
      noiseBurst(t, {
        type: 'bandpass', freq: 420, to: 260, q: 1.2, dur: 0.8,
        gain: 0.1, attack: 0.08, dest: sfxOut
      });
    },

    victory: function (t) {
      const seq = [[0, 72], [0.12, 76], [0.24, 79], [0.4, 84]];
      for (let i = 0; i < seq.length; i++) {
        const at = t + seq[i][0];
        tone(at, {
          type: 'sawtooth', freq: mtof(seq[i][1]), dur: 0.24,
          gain: 0.1, attack: 0.004,
          filter: { type: 'lowpass', freq: 3200 }, dest: sfxOut
        });
        tone(at, {
          type: 'square', freq: mtof(seq[i][1]), dur: 0.2,
          gain: 0.05, attack: 0.004,
          filter: { type: 'lowpass', freq: 3000 }, dest: sfxOut
        });
      }
      const chord = [72, 76, 79, 84];
      for (let i = 0; i < chord.length; i++) {
        tone(t + 0.5, {
          type: 'triangle', freq: mtof(chord[i]), dur: 0.45,
          gain: 0.06, attack: 0.02, dest: sfxOut
        });
      }
    },

    gameover: function (t) {
      const seq = [[0, 62], [0.22, 60], [0.44, 58], [0.66, 57]];
      for (let i = 0; i < seq.length; i++) {
        const at = t + seq[i][0];
        tone(at, {
          type: 'triangle', freq: mtof(seq[i][1]), dur: 0.34,
          gain: 0.12, attack: 0.01,
          filter: { type: 'lowpass', freq: 1600 }, dest: sfxOut
        });
        tone(at, {
          type: 'sine', freq: mtof(seq[i][1] - 12), dur: 0.36,
          gain: 0.07, attack: 0.01, dest: sfxOut
        });
      }
      tone(t, {
        type: 'sawtooth', freq: mtof(38), dur: 1.1,
        gain: 0.13, attack: 0.02, hold: 0.3,
        filter: { type: 'lowpass', freq: 500, to: 180 }, dest: sfxOut
      });
    },

    wave: function (t) {
      tone(t, {
        type: 'square', freq: 880, dur: 0.1,
        gain: 0.07, attack: 0.002,
        filter: { type: 'lowpass', freq: 4000 }, dest: sfxOut
      });
      tone(t + 0.14, {
        type: 'square', freq: 1320, dur: 0.12,
        gain: 0.07, attack: 0.002,
        filter: { type: 'lowpass', freq: 5000 }, dest: sfxOut
      });
      noiseBurst(t, {
        type: 'highpass', freq: 6000, dur: 0.3,
        gain: 0.035, attack: 0.01, dest: sfxOut
      });
    },

    combo: function (t) {
      const m = 88 + Math.floor(Math.random() * 5);
      tone(t, {
        type: 'square', freq: mtof(m), dur: 0.08,
        gain: 0.055, attack: 0.001,
        filter: { type: 'lowpass', freq: 6000 }, dest: sfxOut
      });
      tone(t + 0.06, {
        type: 'square', freq: mtof(m + 7), dur: 0.1,
        gain: 0.045, attack: 0.001,
        filter: { type: 'lowpass', freq: 6000 }, dest: sfxOut
      });
    }
  };

  const SFX_DUR = {
    punch: 0.2, heavy: 0.34, hit: 0.18, hitHeavy: 0.3, block: 0.16, whiff: 0.16,
    ko: 1.0, jump: 0.2, land: 0.22, dash: 0.26, special: 1.35, pickup: 0.35,
    ui: 0.12, start: 0.8, roar: 0.95, victory: 1.1, gameover: 1.2, wave: 0.5, combo: 0.2
  };

  const SFX_GAP = {
    punch: 0.028, heavy: 0.05, hit: 0.03, hitHeavy: 0.05, block: 0.04, whiff: 0.05,
    ko: 0.4, jump: 0.05, land: 0.06, dash: 0.06, special: 0.6, pickup: 0.05,
    ui: 0.06, start: 0.5, roar: 0.8, victory: 0.8, gameover: 0.8, wave: 0.2, combo: 0.05
  };

  /* 每个音效名的音量配平系数（以实测峰值为准：打击感强的音效略高，提示音保持克制） */
  const SFX_TRIM = {
    punch: 1.0, heavy: 1.0, hit: 1.5, hitHeavy: 1.3, block: 1.55, whiff: 2.8,
    ko: 1.0, jump: 2.2, land: 1.3, dash: 1.9, special: 1.0, pickup: 1.5,
    ui: 1.9, start: 1.5, roar: 1.3, victory: 1.35, gameover: 1.1,
    wave: 1.8, combo: 2.0
  };

  /* ================================================================== *
   * 公开 API
   * ================================================================== */

  function init() {
    if (inited) return;
    inited = true;
    safe(function () {
      if (NF.config && NF.config.NO_AUDIO) disabled = true;
    });
    if (disabled) return;
    /* 保险：即使引擎的 onFirstGesture 没回调，自己也在首个手势解锁 */
    bindGestures();
  }

  function unlock() {
    if (disabled) return;
    safe(function () {
      if (!inited) init();
      if (!ctx) createContext();
      if (!ctx || disabled) return;
      buildGraph();
      if (unlocked && graphReady) return;
      unlocked = true;
      if (!offline) {
        safe(function () {
          if (ctx.state === 'suspended') {
            const p = ctx.resume();
            if (p && p.catch) p.catch(function () {});
          }
        });
      }
      applyMuted(true);
      applyDuck(true);
      if (desiredScene !== activeScene) switchScene(desiredScene);
      unbindGestures();
    });
  }

  function update(dt) {
    if (!ctx) return;
    const d = (typeof dt === 'number' && isFinite(dt) && dt > 0) ? Math.min(dt, 0.25) : 0;
    if (offline) vclock += d;
    if (!unlocked || !graphReady) return;
    safe(function () {
      const now = nowTime();
      /* 浏览器策略/切后台导致挂起时，限频重试恢复（不阻塞主线程） */
      if (!offline && ctx.state === 'suspended' && now - lastResumeTry > RESUME_RETRY) {
        lastResumeTry = now;
        const p = ctx.resume();
        if (p && p.catch) p.catch(function () {});
      }
      if (ctx.state === 'closed') return;

      /* 清理已淡出的旧曲目 */
      for (let i = fadingSongs.length - 1; i >= 0; i--) {
        if (now >= fadingSongs[i].stopAt) {
          cleanupSong(fadingSongs[i]);
          fadingSongs.splice(i, 1);
        }
      }
      /* 清理过期音效计数 */
      for (let i = sfxActive.length - 1; i >= 0; i--) {
        if (now >= sfxActive[i].end) sfxActive.splice(i, 1);
      }
      /* 兜底：请求场景与当前场景不一致（例如解锁晚于 music() 时已被处理） */
      if (desiredScene !== activeScene) switchScene(desiredScene);

      if (activeSong) scheduleSong(activeSong, now);
    });
  }

  function sfx(name) {
    if (disabled || !unlocked || !graphReady || !ctx) return;
    safe(function () {
      const def = SFX_DEFS[name];
      if (!def) return;
      const now = nowTime();
      const gap = SFX_GAP[name] == null ? 0.03 : SFX_GAP[name];
      const last = lastSfxAt[name];
      if (last != null && now - last < gap) return;

      for (let i = sfxActive.length - 1; i >= 0; i--) {
        if (now >= sfxActive[i].end) sfxActive.splice(i, 1);
      }
      if (sfxActive.length >= MAX_SFX) return;

      lastSfxAt[name] = now;
      sfxActive.push({ end: now + (SFX_DUR[name] || 0.3), name: name });
      /* 每次调用一个独立 trim 增益（音量配平），音效播完后由 GC 回收 */
      const trim = SFX_TRIM[name] == null ? 1 : SFX_TRIM[name];
      const out = ctx.createGain();
      out.gain.value = trim;
      out.connect(sfxBus);
      sfxOut = out;
      try { def(now + SFX_LEAD); } finally { sfxOut = null; }
    });
  }

  function music(scene) {
    const s = (typeof scene === 'string' && scene) ? scene : 'none';
    desiredScene = (s === 'none' || SONG_DEFS[s]) ? s : 'none';
    if (!ctx || !unlocked || !graphReady) return;
    safe(function () {
      if (desiredScene !== activeScene) switchScene(desiredScene);
    });
  }

  function setMuted(m) {
    muted = !!m;
    applyMuted(false);
    return muted;
  }

  function toggleMute() {
    return setMuted(!muted);
  }

  function duck(on) {
    ducked = !!on;
    applyDuck(false);
  }

  const api = {
    init: init,
    unlock: unlock,
    update: update,
    sfx: sfx,
    music: music,
    setMuted: setMuted,
    toggleMute: toggleMute,
    duck: duck,
    get muted() { return muted; },
    get ready() { return !!ctx && unlocked; }
  };

  NF.audio = api;
})();
