/* 霓虹拳魂 NEON FIST SOUL — 全局常量与调参 */
window.NF = window.NF || {};

(function () {
  const qs = new URLSearchParams(location.search);
  const num = (k, d) => {
    const v = parseFloat(qs.get(k));
    return Number.isFinite(v) ? v : d;
  };

  NF.config = {
    /* 画布逻辑分辨率（16:9），所有坐标都使用这个空间 */
    VIEW_W: 960,
    VIEW_H: 540,

    /* 关卡世界宽度，摄像机范围 [0, STAGE_W - VIEW_W] */
    STAGE_W: 3200,

    /* 地面纵深：角色脚底 y 的取值范围 */
    GROUND_TOP: 356,
    GROUND_BOTTOM: 502,
    PLAYER_START_X: 320,
    PLAYER_START_Y: 470,

    /* 摄像机跟随 */
    CAMERA_LERP: 6.5,
    CAMERA_DEADZONE: 72,
    CAMERA_LOOKAHEAD: 46,

    /* 调试与截图：?shot=title|battle|boss|victory|gameover&freeze=1.5&touch=1&debug=1 */
    SHOT: qs.get('shot') || '',
    FREEZE: num('freeze', -1),
    DEBUG: qs.get('debug') === '1',
    FORCE_TOUCH: qs.get('touch') === '1',
    MUTE: qs.get('mute') === '1',
    SHOW_FPS: qs.get('fps') === '1',
    NO_AUDIO: qs.get('silent') === '1',

    /* 战斗数值（各模块可在此基础上细化） */
    HITSTOP_LIGHT: 0.045,
    HITSTOP_HEAVY: 0.09,
    MAX_SPECIAL: 100,
    PLAYER_MAX_HP: 120,

    COLORS: {
      ink: '#120c1c',
      ink2: '#1d1230',
      paper: '#f7f1ff',
      cyan: '#3df3ff',
      cyanDim: '#1a8ca8',
      magenta: '#ff2f8e',
      magentaDim: '#a11856',
      purple: '#7a3cff',
      yellow: '#ffd23f',
      orange: '#ff8a2a',
      lime: '#8dff5a',
      red: '#ff3b5c',
      blue: '#3b6dff',
      steel: '#9aa7c7',
      deep: '#07050f'
    }
  };

  /* 关卡数据：单个关卡「霓虹后巷」的波次与摄像机锁定点 */
  NF.config.STAGE = {
    name: '霓虹后巷',
    subtitle: 'NEON BACK ALLEY — 第 1 区',
    bossArenaX: 2540,
    bossLockCameraX: NF.config.STAGE_W - NF.config.VIEW_W,
    waves: [
      { at: 0, count: 2, types: ['punk', 'punk'], label: 'WAVE 1' },
      { at: 760, count: 3, types: ['punk', 'punk', 'brute'], label: 'WAVE 2' },
      { at: 1560, count: 4, types: ['punk', 'brute', 'punk', 'punk'], label: 'WAVE 3' },
      { at: 2440, count: 1, types: ['boss'], label: 'BOSS', boss: true }
    ]
  };
})();
