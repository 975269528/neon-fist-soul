/* 霓虹拳魂 NEON FIST SOUL — 输入系统（键盘 / 触屏 / 手柄） */
window.NF = window.NF || {};

(function () {
  const ACTIONS = ['left', 'right', 'up', 'down', 'attack', 'heavy', 'jump', 'special', 'start', 'pause', 'mute', 'dash', 'restart'];

  const KEYMAP = {
    ArrowLeft: 'left', KeyA: 'left',
    ArrowRight: 'right', KeyD: 'right',
    ArrowUp: 'up', KeyW: 'up',
    ArrowDown: 'down', KeyS: 'down',
    KeyJ: 'attack', KeyZ: 'attack',
    KeyK: 'heavy', KeyX: 'heavy',
    Space: 'jump', KeyL: 'jump',
    KeyU: 'special', KeyI: 'special', KeyC: 'special',
    Enter: 'start', NumpadEnter: 'start',
    Escape: 'pause', KeyP: 'pause',
    KeyM: 'mute',
    KeyR: 'restart',
    ShiftLeft: 'dash', ShiftRight: 'dash'
  };

  const input = {
    down: Object.create(null),
    pressed: Object.create(null),
    released: Object.create(null),
    analog: { x: 0, y: 0, active: false },
    tapped: false,
    touchMode: false,
    enabled: true,
    canvas: null,
    _stickPointerId: null,
    _stickCenter: { x: 0, y: 0 },
    _stickRadius: 46,
    _firstGestureCbs: [],

    init(canvas) {
      this.canvas = canvas;
      ACTIONS.forEach((a) => { this.down[a] = false; this.pressed[a] = false; this.released[a] = false; });

      const isTouch = NF.config.FORCE_TOUCH ||
        (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) ||
        (navigator.maxTouchPoints > 0 && 'ontouchstart' in window);
      this.touchMode = !!isTouch;
      document.body.classList.toggle('touch', this.touchMode);
      document.body.classList.toggle('force-touch', NF.config.FORCE_TOUCH);

      window.addEventListener('keydown', (e) => this._onKey(e, true), { passive: false });
      window.addEventListener('keyup', (e) => this._onKey(e, false), { passive: false });
      window.addEventListener('blur', () => this.clearAll());

      canvas.addEventListener('pointerdown', (e) => {
        this.tapped = true;
        this._fireFirstGesture();
        if (e.pointerType === 'touch') e.preventDefault();
      });

      document.addEventListener('pointerdown', () => this._fireFirstGesture(), { passive: true });

      this._initTouch();
      this.refreshTouchUI();
    },

    onFirstGesture(cb) { this._firstGestureCbs.push(cb); },
    _fireFirstGesture() {
      if (!this._firstGestureCbs.length) return;
      const cbs = this._firstGestureCbs.slice();
      this._firstGestureCbs.length = 0;
      cbs.forEach((cb) => { try { cb(); } catch (err) { console.warn(err); } });
    },

    refreshTouchUI() {
      const ui = document.getElementById('touch-ui');
      if (!ui) return;
      const show = this.touchMode;
      ui.classList.toggle('hidden', !show);
      if (show) {
        const pause = document.getElementById('btn-pause');
        if (pause) pause.classList.remove('hidden');
      }
    },

    _onKey(e, isDown) {
      const action = KEYMAP[e.code];
      if (!action) return;
      if (['Space', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Enter'].includes(e.code)) {
        e.preventDefault();
      }
      if (e.repeat) return;
      this._set(action, isDown);
    },

    _set(action, isDown) {
      if (!ACTIONS.includes(action)) return;
      if (isDown) {
        if (!this.down[action]) this.pressed[action] = true;
        this.down[action] = true;
      } else {
        if (this.down[action]) this.released[action] = true;
        this.down[action] = false;
      }
    },

    _initTouch() {
      const zone = document.getElementById('stick-zone');
      const base = document.getElementById('stick-base');
      const knob = document.getElementById('stick-knob');
      if (!zone || !base || !knob) return;

      const setKnob = (dx, dy) => {
        knob.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
      };

      const updateStick = (e) => {
        const rect = base.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const max = rect.width * 0.36;
        let dx = e.clientX - cx;
        let dy = e.clientY - cy;
        const len = Math.hypot(dx, dy);
        if (len > max) { dx = dx / len * max; dy = dy / len * max; }
        setKnob(dx, dy);
        const nx = dx / max;
        const ny = dy / max;
        const dead = 0.18;
        this.analog.x = Math.abs(nx) < dead ? 0 : NF.util.clamp(nx, -1, 1);
        this.analog.y = Math.abs(ny) < dead ? 0 : NF.util.clamp(ny, -1, 1);
        this.analog.active = true;
      };

      zone.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        this._stickPointerId = e.pointerId;
        zone.setPointerCapture(e.pointerId);
        updateStick(e);
        this.tapped = true;
        this._fireFirstGesture();
      });
      zone.addEventListener('pointermove', (e) => {
        if (e.pointerId !== this._stickPointerId) return;
        e.preventDefault();
        updateStick(e);
      });
      const endStick = (e) => {
        if (e.pointerId !== this._stickPointerId) return;
        this._stickPointerId = null;
        this.analog.x = 0; this.analog.y = 0; this.analog.active = false;
        setKnob(0, 0);
      };
      zone.addEventListener('pointerup', endStick);
      zone.addEventListener('pointercancel', endStick);
      zone.addEventListener('lostpointercapture', endStick);

      const buttons = document.querySelectorAll('[data-action]');
      buttons.forEach((btn) => {
        const action = btn.getAttribute('data-action');
        const press = (e) => {
          e.preventDefault();
          btn.classList.add('on');
          this._set(action, true);
          this.tapped = true;
          this._fireFirstGesture();
          if (btn.setPointerCapture && e.pointerId !== undefined) {
            try { btn.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
          }
        };
        const release = (e) => {
          if (e) e.preventDefault();
          btn.classList.remove('on');
          this._set(action, false);
        };
        btn.addEventListener('pointerdown', press);
        btn.addEventListener('pointerup', release);
        btn.addEventListener('pointercancel', release);
        btn.addEventListener('pointerleave', (e) => {
          if (e.pointerType === 'mouse' && e.buttons === 0) release(e);
        });
        btn.addEventListener('contextmenu', (e) => e.preventDefault());
      });
    },

    poll() {
      /* 手柄（可选）：左摇杆移动 + 按键映射 */
      if (!navigator.getGamepads) return;
      let pad = null;
      try {
        const pads = navigator.getGamepads();
        for (let i = 0; i < pads.length; i++) if (pads[i]) { pad = pads[i]; break; }
      } catch (err) { return; }
      if (!pad) return;
      const ax = pad.axes[0] || 0;
      if (Math.abs(ax) > 0.25) {
        if (ax < -0.4) this._set('left', true); else if (ax > 0.4) this._set('right', true);
        else { this._set('left', false); this._set('right', false); }
      }
      const b = pad.buttons;
      const map = { 0: 'attack', 2: 'heavy', 1: 'jump', 3: 'special', 9: 'start', 8: 'pause' };
      Object.keys(map).forEach((i) => {
        if (b[i]) this._set(map[i], !!b[i].pressed);
      });
    },

    isDown(action) { return !!this.down[action]; },
    justPressed(action) { return !!this.pressed[action]; },
    justReleased(action) { return !!this.released[action]; },
    anyPressed() {
      for (let i = 0; i < ACTIONS.length; i++) if (this.pressed[ACTIONS[i]]) return true;
      return false;
    },

    axisX() {
      let v = 0;
      if (this.down.left) v -= 1;
      if (this.down.right) v += 1;
      if (this.analog.active && Math.abs(this.analog.x) > Math.abs(v)) v = this.analog.x;
      return NF.util.clamp(v, -1, 1);
    },
    axisY() {
      let v = 0;
      if (this.down.up) v -= 1;
      if (this.down.down) v += 1;
      if (this.analog.active && Math.abs(this.analog.y) > Math.abs(v)) v = this.analog.y;
      return NF.util.clamp(v, -1, 1);
    },

    endFrame() {
      for (let i = 0; i < ACTIONS.length; i++) {
        this.pressed[ACTIONS[i]] = false;
        this.released[ACTIONS[i]] = false;
      }
      this.tapped = false;
    },

    clearAll() {
      ACTIONS.forEach((a) => { this.down[a] = false; this.pressed[a] = false; this.released[a] = false; });
      this.analog.x = 0; this.analog.y = 0; this.analog.active = false;
      const knob = document.getElementById('stick-knob');
      if (knob) knob.style.transform = 'translate(0px,0px)';
      document.querySelectorAll('.tbtn.on').forEach((b) => b.classList.remove('on'));
    }
  };

  NF.input = input;
})();
