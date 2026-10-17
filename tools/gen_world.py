#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
霓虹拳魂 NEON FIST SOUL — 场景与 UI 美术程序化生成器
====================================================
生成（全部纯程序化，不下载任何外部图片）：
  assets/world/bg_far.png   1600x540  RGBA  夜空 / 远景楼群 / 霓虹天际线 / 雨雾，横向无缝
  assets/world/bg_mid.png   3200x540  RGBA  中景楼体 / 拉面店 / 居酒屋 / 招牌 / 海报 / 空调外机
  assets/world/bg_near.png  3200x540  RGBA  近景街面 / 湿沥青反光 / 水洼 / 路缘石 / 消防栓 / 电线杆
  assets/world/bg_fg.png    3200x540  RGBA  透明前景剪影：电线 / 雨棚 / 蒸汽管 / 箱子
  assets/ui/logo.png        760x240   RGBA  标题 Logo（中文像素化 + 英文像素字）
  assets/world/manifest.js                   NF.registerWorld(...)
  shots/world_*.png                          自检预览（图层接触表 / 视口合成 / 接缝 / logo）

用法：
  python tools/gen_world.py               # 生成全部
  python tools/gen_world.py mid near      # 只生成部分图层（logo / manifest / far ...）
  python tools/gen_world.py preview       # 只重算预览

约定：地平线 / 街面（960x540 逻辑视口）
  天空 0..~326，楼体立面可见到 y=330（近景人行道从这里开始）
  人行道 330..356，路缘石 356..362，街面 362..540
  角色脚底活动带 GROUND_TOP=356 .. GROUND_BOTTOM=502，底部 502..540 为更近的湿地面
"""

import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ----------------------------------------------------------------------------
# 0. 路径 / 常量 / 调色板
# ----------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLD_DIR = os.path.join(ROOT, 'assets', 'world')
UI_DIR = os.path.join(ROOT, 'assets', 'ui')
SHOTS_DIR = os.path.join(ROOT, 'shots')

W = 3200                    # 世界宽度（near / mid / fg）
H = 540
FAR_W = 1600                # 远景可平铺宽度
VIEW_W, VIEW_H = 960, 540
GROUND_TOP = 356            # 角色脚底最远 / 最近
GROUND_BOTTOM = 502
WALK_TOP = 330              # 楼体基线（近景人行道起始）
STREET_TOP = 362            # 沥青街面上沿（路缘石下方）

FONT_CJK = r'C:\Windows\Fonts\msyhbd.ttf'
if not os.path.exists(FONT_CJK):
    FONT_CJK = r'C:\Windows\Fonts\msyh.ttf'
FONT_MONO = r'C:\Windows\Fonts\consolab.ttf'

# 全局基调（§3 调色板）
DEEP = '#07050f'
INK = '#150b22'
CYAN = '#3df3ff'
CYAN_D = '#1a8ca8'
MAGENTA = '#ff2f8e'
MAGENTA_D = '#a11856'
PURPLE = '#7a3cff'
YELLOW = '#ffd23f'
ORANGE = '#ff8a2a'
RED = '#ff3b5c'
STEEL = '#9aa7c7'
STEEL_L = '#d7e2f7'
STEEL_D = '#5d6b8f'
NAVY = '#2c3450'

# 天空 / 街面分阶调色板（用 ordered dither 过渡，保留硬边）
SKY_PAL = ['#05030c', '#07050f', '#090614', '#0c0719', '#0f091f', '#130a26',
           '#170c2d', '#1c0e34', '#22113d', '#2a1245', '#32164f']
STREET_PAL = ['#221a36', '#1e1730', '#1a142a', '#171225', '#140f20', '#120d1d',
              '#0f0b1a', '#0d0917', '#0b0714']
SIDEWALK_PAL = ['#2d2044', '#2a1e3f', '#271b3a', '#231833', '#1f152e']
CURB_TOP = '#4a3b63'
CURB_FACE = '#141021'
CURB_BOT = '#0a0714'
FACADE_PAL = ['#1a0d33', '#1d1036', '#201139', '#23133c', '#261440',
              '#1a1029', '#1e1230', '#221536']
FACADE_HI = ['#2e1c4d', '#332052', '#38235a', '#3d1a5c']
FACADE_DARK = ['#0f0919', '#110a1d', '#0d0717']
WINDOW_DARK = ['#0d0820', '#0b0619', '#100a1f']
WINDOW_LIT = ['#d8b04a', '#c99a2e', '#2f8f9f', '#24808f', '#a11856', '#7a2f6a',
              '#4a3a8f', '#c9d6ea', '#e0a84a', '#3f7f6a']
TRIM_PAL = ['#3d1a5c', '#4a2368', '#33204f', '#553070']

BAYER4 = np.array([[0, 8, 2, 10],
                   [12, 4, 14, 6],
                   [3, 11, 1, 9],
                   [15, 7, 13, 5]], dtype=np.float32) / 16.0


def hx(s, a=255):
    """'#rrggbb' 或 (r,g,b) -> (r,g,b,a)"""
    if isinstance(s, tuple):
        if len(s) >= 4:
            return (s[0], s[1], s[2], a)
        return (s[0], s[1], s[2], a)
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(a))


def rgb3(s):
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def mix(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def shade(s, f):
    r, g, b = rgb3(s)
    return (clamp(int(r * f), 0, 255), clamp(int(g * f), 0, 255), clamp(int(b * f), 0, 255))


# ----------------------------------------------------------------------------
# 1. 基础绘图工具
# ----------------------------------------------------------------------------
def bayer(h, w):
    return np.tile(BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]


def banded(arr, y0, y1, pal, x0=0, x1=None, gamma=1.0, dither=True):
    """把竖向渐变以「分阶 + Bayer 抖动」写入 float32 RGBA 数组（alpha=255）。"""
    if x1 is None:
        x1 = arr.shape[1]
    h = y1 - y0
    w = x1 - x0
    if h <= 0 or w <= 0:
        return
    p = np.array([rgb3(c) for c in pal], dtype=np.float32)
    t = (np.arange(h, dtype=np.float32) / max(1, h - 1)) ** gamma
    pos = t * (len(p) - 1)
    base = np.floor(pos).astype(np.int32)
    frac = pos - base
    if dither:
        b = bayer(h, w)
        idx = np.clip(base[:, None] + (frac[:, None] > b).astype(np.int32), 0, len(p) - 1)
    else:
        idx = np.clip(np.round(pos).astype(np.int32), 0, len(p) - 1)[:, None] * np.ones((1, w), np.int32)
    arr[y0:y1, x0:x1, :3] = p[idx]
    arr[y0:y1, x0:x1, 3] = 255.0


def add_radial(arr, cx, cy, rx, ry, color, gain=1.0, power=2.0, ellipse=False):
    """叠加椭圆径向光晕（加到 RGB 上）。"""
    h, w = arr.shape[:2]
    x0, x1 = max(0, int(cx - rx)), min(w, int(cx + rx) + 1)
    y0, y1 = max(0, int(cy - ry)), min(h, int(cy + ry) + 1)
    if x1 <= x0 or y1 <= y0:
        return
    xs = (np.arange(x0, x1, dtype=np.float32) - cx) / rx
    ys = (np.arange(y0, y1, dtype=np.float32) - cy) / ry
    d = np.sqrt(xs[None, :] ** 2 + ys[:, None] ** 2)
    f = np.clip(1.0 - d, 0.0, 1.0) ** power
    col = np.array(color, np.float32)
    arr[y0:y1, x0:x1, :3] += col[None, None, :] * (f[..., None] * gain)


def add_band(arr, y0, y1, color, gain=1.0, power=1.0, peak=0.5):
    """横向光带（在 y 方向按梯形/高斯衰减）。"""
    h = arr.shape[0]
    ys = np.arange(h, dtype=np.float32)
    cy = (y0 + y1) / 2.0
    half = max(1.0, (y1 - y0) / 2.0)
    f = np.clip(1.0 - np.abs(ys - cy) / half, 0.0, 1.0) ** power
    f = f * peak + f * (1 - peak)
    col = np.array(color, np.float32)
    arr[:, :, :3] += col[None, None, :] * (f[:, None, None] * gain)


class Layer:
    """一张带「霓虹自发光层」的画布：finish() 时先柔光(bloom)再叠硬边霓虹。"""

    def __init__(self, w, h, base=None):
        self.w, self.h = w, h
        self.img = base if base is not None else Image.new('RGBA', (w, h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.signs = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        self.sd = ImageDraw.Draw(self.signs)
        self.spills = []   # (x, y, w, color, strength)  招牌在地面 / 立面上的光斑

    def overlay(self, fn):
        ov = Image.new('RGBA', (self.w, self.h), (0, 0, 0, 0))
        fn(ImageDraw.Draw(ov))
        self.img.alpha_composite(ov)

    def finish(self, radius=8.0, gain=1.0, tight=2.0, tight_gain=0.65):
        if self.signs.getbbox() is None:
            self.d = None
            return
        arr = np.asarray(self.img).astype(np.float32)
        for r, g_amt in ((radius, gain), (tight, tight_gain)):
            if g_amt <= 0:
                continue
            bl = np.asarray(self.signs.filter(ImageFilter.GaussianBlur(r))).astype(np.float32)
            ga = np.clip(bl[..., 3:4] / 255.0 * g_amt, 0.0, 1.0)
            gc = bl[..., :3]
            base_a = arr[..., 3:4] / 255.0
            out_a = np.clip(base_a + ga * (1.0 - base_a), 0.0, 1.0)
            arr[..., :3] = 255.0 - (255.0 - arr[..., :3]) * (255.0 - gc * ga) / 255.0
            arr[..., 3:4] = out_a * 255.0
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        img.alpha_composite(self.signs)
        self.img = img
        self.d = None

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.img.save(path, optimize=True)


def rect(d, x, y, w, h, fill):
    if w <= 0 or h <= 0:
        return
    d.rectangle([int(x), int(y), int(x + w - 1), int(y + h - 1)], fill=fill)


def line(d, pts, fill, width=1):
    d.line([(int(x), int(y)) for x, y in pts], fill=fill, width=int(width))


def px(d, x, y, fill):
    d.point((int(x), int(y)), fill=fill)


# --- 文字位图 -------------------------------------------------------------
_font_cache = {}


def get_font(size):
    key = max(8, int(size))
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(FONT_CJK, key)
        except Exception:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def char_mask(ch, px_h, block=1, threshold=118):
    """把系统字体单字清染成像素块（block>1 时目标像素为 block x block 方块）。"""
    if ch == ' ':
        return None
    grid_h = px_h // block if block > 1 else px_h
    fsize = max(10, grid_h * (3 if block > 1 else 4))
    f = get_font(fsize)
    im = Image.new('L', (fsize * 3, fsize * 3), 0)
    ImageDraw.Draw(im).text((fsize, fsize), ch, font=f, fill=255, anchor='lt')
    bb = im.getbbox()
    if not bb:
        return None
    crop = im.crop(bb)
    w = max(1, int(round(crop.width * grid_h / crop.height)))
    small = crop.resize((w, grid_h), Image.BOX if block > 1 else Image.LANCZOS)
    small = small.point(lambda v: 255 if v >= threshold else 0)
    if block > 1:
        small = small.resize((w * block, px_h), Image.NEAREST)
    return small


def text_mask(text, px_h, block=1, vertical=False, gap=None, threshold=118):
    """中文 / 日文 / 符号文字 → 像素化 L 蒙版。"""
    if gap is None:
        gap = max(1, round(px_h * 0.10))
    glyphs = []
    for ch in text:
        m = char_mask(ch, px_h, block, threshold)
        if m is None:
            glyphs.append(Image.new('L', (max(2, px_h // 3), px_h), 0))
        else:
            glyphs.append(m)
    if not glyphs:
        return Image.new('L', (1, 1), 0)
    if vertical:
        wmax = max(g.width for g in glyphs)
        htot = sum(g.height for g in glyphs) + gap * (len(glyphs) - 1)
        out = Image.new('L', (wmax, htot), 0)
        yy = 0
        for g in glyphs:
            out.paste(g, ((wmax - g.width) // 2, yy))
            yy += g.height + gap
    else:
        hmax = max(g.height for g in glyphs)
        wtot = sum(g.width for g in glyphs) + gap * (len(glyphs) - 1)
        out = Image.new('L', (wtot, hmax), 0)
        xx = 0
        for g in glyphs:
            out.paste(g, (xx, (hmax - g.height) // 2))
            xx += g.width + gap
    return out


# 5x7 像素字体（英文招牌 / Logo 副标题）
FONT5 = {
    'A': ['01110', '10001', '10001', '11111', '10001', '10001', '10001'],
    'B': ['11110', '10001', '10001', '11110', '10001', '10001', '11110'],
    'C': ['01111', '10000', '10000', '10000', '10000', '10000', '01111'],
    'D': ['11110', '10001', '10001', '10001', '10001', '10001', '11110'],
    'E': ['11111', '10000', '10000', '11110', '10000', '10000', '11111'],
    'F': ['11111', '10000', '10000', '11110', '10000', '10000', '10000'],
    'G': ['01111', '10000', '10000', '10111', '10001', '10001', '01110'],
    'H': ['10001', '10001', '10001', '11111', '10001', '10001', '10001'],
    'I': ['11111', '00100', '00100', '00100', '00100', '00100', '11111'],
    'J': ['00111', '00010', '00010', '00010', '00010', '10010', '01100'],
    'K': ['10001', '10010', '10100', '11000', '10100', '10010', '10001'],
    'L': ['10000', '10000', '10000', '10000', '10000', '10000', '11111'],
    'M': ['10001', '11011', '10101', '10101', '10001', '10001', '10001'],
    'N': ['10001', '11001', '10101', '10011', '10001', '10001', '10001'],
    'O': ['01110', '10001', '10001', '10001', '10001', '10001', '01110'],
    'P': ['11110', '10001', '10001', '11110', '10000', '10000', '10000'],
    'Q': ['01110', '10001', '10001', '10001', '10101', '10010', '01101'],
    'R': ['11110', '10001', '10001', '11110', '10100', '10010', '10001'],
    'S': ['01111', '10000', '10000', '01110', '00001', '00001', '11110'],
    'T': ['11111', '00100', '00100', '00100', '00100', '00100', '00100'],
    'U': ['10001', '10001', '10001', '10001', '10001', '10001', '01110'],
    'V': ['10001', '10001', '10001', '10001', '10001', '01010', '00100'],
    'W': ['10001', '10001', '10001', '10101', '10101', '11011', '10001'],
    'X': ['10001', '10001', '01010', '00100', '01010', '10001', '10001'],
    'Y': ['10001', '10001', '01010', '00100', '00100', '00100', '00100'],
    'Z': ['11111', '00001', '00010', '00100', '01000', '10000', '11111'],
    '0': ['01110', '10011', '10101', '10101', '10101', '11001', '01110'],
    '1': ['00100', '01100', '00100', '00100', '00100', '00100', '01110'],
    '2': ['01110', '10001', '00001', '00110', '01000', '10000', '11111'],
    '3': ['11110', '00001', '00001', '01110', '00001', '00001', '11110'],
    '4': ['00010', '00110', '01010', '10010', '11111', '00010', '00010'],
    '5': ['11111', '10000', '11110', '00001', '00001', '10001', '01110'],
    '6': ['00110', '01000', '10000', '11110', '10001', '10001', '01110'],
    '7': ['11111', '00001', '00010', '00100', '01000', '01000', '01000'],
    '8': ['01110', '10001', '10001', '01110', '10001', '10001', '01110'],
    '9': ['01110', '10001', '10001', '01111', '00001', '00010', '01100'],
    '!': ['00100', '00100', '00100', '00100', '00100', '00000', '00100'],
    '.': ['00000', '00000', '00000', '00000', '00000', '00110', '00110'],
    '-': ['00000', '00000', '00000', '11111', '00000', '00000', '00000'],
    ':': ['00000', '00110', '00110', '00000', '00110', '00110', '00000'],
    ' ': ['00000', '00000', '00000', '00000', '00000', '00000', '00000'],
}


def pixel_mask(text, scale=1, gap=1):
    text = text.upper()
    total = 0
    for i, ch in enumerate(text):
        g = FONT5.get(ch, FONT5[' '])
        total += len(g[0]) + (gap if i < len(text) - 1 else 0)
    im = Image.new('L', (max(1, total * scale), 7 * scale), 0)
    d = ImageDraw.Draw(im)
    xx = 0
    for ch in text:
        g = FONT5.get(ch, FONT5[' '])
        wch = len(g[0])
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == '1':
                    rect(d, (xx + c) * scale, r * scale, scale, scale, 255)
        xx += wch + gap
    return im


def stamp(target, mask, x, y, color, alpha=255):
    """把 L 蒙版以指定颜色贴到 RGBA 图像上（硬边替换）。"""
    if mask is None:
        return
    col = color if isinstance(color, tuple) else hx(color, alpha)
    fill = Image.new('RGBA', mask.size, col)
    target.paste(fill, (int(x), int(y)), mask)


def stamp_dilate(target, mask, x, y, color, size=3, alpha=255):
    stamp(target, mask.filter(ImageFilter.MaxFilter(size)), x, y, color, alpha)


# --- 霓虹招牌 --------------------------------------------------------------
def sign_horizontal(layer, x, y, w, h, text, px_h, board='#140b1d', border=CYAN,
                    txt=CYAN, core='#eaffe9', border_w=2, dim_index=None, latin=False):
    d, sd = layer.d, layer.sd
    rect(d, x - 3, y - 3, w + 6, h + 6, hx('#08040f'))
    rect(d, x, y, w, h, hx(board))
    d.rectangle([x + 2, y + 2, x + w - 3, y + h - 3], outline=hx('#241534'))
    sd.rectangle([x, y, x + w - 1, y + h - 1], outline=hx(border), width=border_w)
    if text:
        if latin:
            m = pixel_mask(text, max(1, px_h // 7))
        else:
            m = text_mask(text, px_h)
        tx = x + (w - m.width) // 2
        ty = y + (h - m.height) // 2
        stamp(layer.signs, m, tx, ty, txt)
        stamp(layer.signs, m.filter(ImageFilter.MinFilter(3)), tx, ty, core, 210)
    return (x, y, w, h)


def sign_vertical(layer, x, y, w, h, text, px_h, board='#120b1d', border=MAGENTA,
                  txt=MAGENTA, core='#ffe8f4', border_w=2, dim_index=None, latin=False):
    d, sd = layer.d, layer.sd
    rect(d, x - 3, y - 3, w + 6, h + 6, hx('#08040f'))
    rect(d, x, y, w, h, hx(board))
    d.rectangle([x + 2, y + 2, x + w - 3, y + h - 3], outline=hx('#241534'))
    sd.rectangle([x, y, x + w - 1, y + h - 1], outline=hx(border), width=border_w)
    if text:
        if latin:
            m = text_mask_vertical_latin(text, max(1, px_h // 7))
        else:
            m = text_mask(text, px_h, vertical=True)
        tx = x + (w - m.width) // 2
        ty = y + (h - m.height) // 2
        stamp(layer.signs, m, tx, ty, txt)
        stamp(layer.signs, m.filter(ImageFilter.MinFilter(3)), tx, ty, core, 210)
    return (x, y, w, h)


def text_mask_vertical_latin(text, scale):
    mm = [pixel_mask(ch, scale) for ch in text]
    wmax = max(m.width for m in mm)
    gap = 2 * scale
    htot = sum(m.height for m in mm) + gap * (len(mm) - 1)
    out = Image.new('L', (wmax, htot), 0)
    yy = 0
    for m in mm:
        out.paste(m, ((wmax - m.width) // 2, yy))
        yy += m.height + gap
    return out


def glow_dot(layer, x, y, r, color, core='#ffffff'):
    layer.sd.ellipse([x - r, y - r, x + r, y + r], fill=hx(color))
    if r > 1:
        layer.sd.ellipse([x - r // 2, y - r // 2, x + r // 2, y + r // 2], fill=hx(core))


# ----------------------------------------------------------------------------
# 2. 远景 bg_far（1600 宽，左右无缝）
# ----------------------------------------------------------------------------
def sky_color_at(y):
    """用于给月亮开槽时取近似天空色。"""
    p = [rgb3(c) for c in SKY_PAL]
    t = (y / 352.0) ** 1.35
    pos = clamp(t, 0, 1) * (len(p) - 1)
    i = int(pos)
    j = min(len(p) - 1, i + 1)
    return mix(p[i], p[j], pos - i)


def draw_far_moon(arr):
    cx, cy, r = 1178, 190, 74
    # 外辉光
    add_radial(arr, cx, cy, 250, 250, (255, 47, 142), 0.16, 2.2)
    add_radial(arr, cx, cy, 130, 130, (255, 92, 168), 0.26, 1.7)
    h, w = arr.shape[:2]
    x0, x1 = max(0, cx - r - 2), min(w, cx + r + 3)
    y0, y1 = max(0, cy - r - 2), min(h, 352, cy + r + 3)
    if x1 <= x0:
        return
    xs = np.arange(x0, x1, dtype=np.float32)
    ys = np.arange(y0, y1, dtype=np.float32)
    dx = (xs[None, :] - cx)
    dy = (ys[:, None] - cy)
    dist = np.sqrt(dx * dx + dy * dy)
    inside = dist <= r
    # 下半部开横向凹槽（合成波风格），越往下缝越宽
    rel = (ys[:, None] - cy) / r
    slot_phase = ((ys[:, None] - cy) % 9.0)
    slot = (rel > 0.02) & (slot_phase < (1.2 + 2.4 * np.clip(rel, 0, 1)))
    mask = inside & (~slot)
    # 圆盘竖向渐变：上亮下暗
    grad = 0.95 - 0.45 * np.clip((ys[:, None] - (cy - r)) / (2 * r), 0, 1)
    col = np.array([255, 92, 158], np.float32)
    region = arr[y0:y1, x0:x1, :3]
    a = mask[..., None] * grad[..., None]
    region[:] = region * (1 - a) + col[None, None, :] * a
    # 明亮上缘
    rim = (np.abs(dist - r) < 1.6) & (dy < 0)
    region[rim] = np.array([255, 190, 220], np.float32)


def far_buildings(arr, rng):
    """远景楼群剪影（画在单独的 PIL 层上再合成，方便加窗）。"""
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    base = Image.new('RGBA', (FAR_W, 352), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)

    def wrap(x, w, fn):
        for off in (-FAR_W, 0, FAR_W):
            if x + off < FAR_W + w and x + off + w > -w:
                fn(x + off)

    # --- 最远层：低对比塔群 ---
    back = []
    x = -80
    while x < FAR_W + 60:
        w = rng.randint(56, 130)
        r = rng.random()
        if r < 0.18:
            top = rng.randint(60, 130)
        elif r < 0.6:
            top = rng.randint(130, 230)
        else:
            top = rng.randint(220, 300)
        back.append((x, w, top))
        x += w + rng.randint(-10, 26)
    for (x, w, top) in back:
        col = rng.choice(['#0a0616', '#0b0718', '#090514'])

        def draw_b(xx, w=w, top=top, col=col):
            d.rectangle([xx, top, xx + w - 1, 352], fill=hx(col))
            d.rectangle([xx, top, xx + w - 1, top + 1], fill=hx('#191030'))
            if w > 80 and rng.random() < 0.6:
                d.rectangle([xx + w // 3, top - rng.randint(8, 26), xx + w // 3 + 2, top], fill=hx('#0a0616'))
        wrap(x, w, draw_b)

    # --- 远层：有窗灯、天线、广告牌的楼 ---
    front = []
    x = -60
    while x < FAR_W + 80:
        w = rng.randint(64, 168)
        r = rng.random()
        if r < 0.20:
            top = rng.randint(36, 120)
        elif r < 0.55:
            top = rng.randint(120, 220)
        else:
            top = rng.randint(200, 300)
        front.append((x, w, top))
        x += w + rng.randint(-16, 30)
    for (x, w, top) in front:
        body = rng.choice(['#100a20', '#120b23', '#0e091e', '#140c26'])

        def draw_f(xx, w=w, top=top, body=body):
            d.rectangle([xx, top, xx + w - 1, 352], fill=hx(body))
            # 楼顶边缘与侧光
            d.rectangle([xx, top, xx + w - 1, top + 1], fill=hx('#251540'))
            d.rectangle([xx, top, xx + 1, 352], fill=hx('#1b1132'))
            d.rectangle([xx + w - 2, top, xx + w - 1, 352], fill=hx('#080411'))
            # 楼顶结构
            r = rng.random()
            if r < 0.32:
                tx = xx + rng.randint(6, max(8, w - 20))
                d.rectangle([tx, top - 14, tx + 14, top - 2], fill=hx('#120c22'))
                d.rectangle([tx + 1, top - 13, tx + 13, top - 3], fill=hx('#1a1230'))
                d.rectangle([tx + 2, top - 12, tx + 4, top - 2], fill=hx('#2a1c44'))
                d.rectangle([tx + 9, top - 12, tx + 11, top - 2], fill=hx(body))
            elif r < 0.55:
                tx = xx + rng.randint(4, max(6, w - 8))
                d.rectangle([tx, top - rng.randint(16, 34), tx + 1, top], fill=hx('#0b0717'))
                d.rectangle([tx - 5, top - 20, tx + 5, top - 19], fill=hx('#0b0717'))
            # 窗灯
            lit_prob = rng.uniform(0.08, 0.22)
            ww, wh = 2, 3
            gapx, gapy = 8, 10
            cols = max(1, (w - 12) // gapx)
            rows = max(1, (340 - top) // gapy)
            for rr in range(rows):
                for cc in range(cols):
                    if rng.random() < lit_prob:
                        wx = xx + 6 + cc * gapx
                        wy = top + 8 + rr * gapy
                        if wy + wh < 340:
                            c = rng.choice(['#b58c34', '#22606c', '#7a2250', '#c9cfe0', '#3a6a55'])
                            rect(d, wx, wy, ww, wh, hx(c, 210 if rng.random() < 0.3 else 255))
        wrap(x, w, draw_f)

    # 楼群整体压暗 + 雾气（远景低对比）
    haze = Image.new('RGBA', base.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(haze)
    for yy in range(90, 352, 1):
        t = clamp((yy - 90) / 262.0, 0, 1)
        hd.line([(0, yy), (FAR_W, yy)], fill=hx('#2a1846', int(70 * t ** 1.6)))
    base = Image.alpha_composite(base, haze)
    img.alpha_composite(base)
    return np.asarray(img).astype(np.float32)


def draw_far_viaduct(layer, rng):
    """远处高架桥 + 列车剪影。"""
    d, sd = layer.d, layer.sd
    deck_y = 300
    # 桥墩
    for x in range(-40, FAR_W + 60, 168):
        rect(d, x, 318, 16, 34, hx('#0b0717'))
        rect(d, x + 1, 319, 3, 33, hx('#170f28'))
    # 桥体
    rect(d, -10, deck_y, FAR_W + 20, 17, hx('#0d081b'))
    rect(d, -10, deck_y, FAR_W + 20, 3, hx('#1c1232'))
    rect(d, -10, deck_y + 15, FAR_W + 20, 4, hx('#070411'))
    # 桥缘青霓虹灯带
    sd.rectangle([-10, deck_y + 2, FAR_W + 9, deck_y + 2], fill=hx(CYAN_D))
    sd.rectangle([-10, deck_y + 3, FAR_W + 9, deck_y + 3], fill=hx(CYAN, 120))
    # 桥上路灯
    for x in range(30, FAR_W, 150):
        rect(d, x, deck_y - 12, 2, 12, hx('#0a0616'))
        rect(d, x - 3, deck_y - 13, 8, 2, hx('#0a0616'))
        glow_dot(layer, x + 1, deck_y - 11, 2, '#ffb347', '#fff0c8')
    # 列车（只在一段，避免瓷砖感太强）
    tx0, tx1 = 856, 1128
    ty = deck_y - 20
    rect(d, tx0, ty, tx1 - tx0, 20, hx('#191129'))
    rect(d, tx0, ty, tx1 - tx0, 3, hx('#2a1d44'))
    rect(d, tx0, ty + 17, tx1 - tx0, 3, hx('#0b0716'))
    for wx in range(tx0 + 10, tx1 - 14, 26):
        rect(d, wx, ty + 6, 14, 7, hx('#c9a53e', 190))
        rect(d, wx + 1, ty + 7, 12, 2, hx('#ffe9a0', 200))
    # 车头灯
    glow_dot(layer, tx1 - 2, ty + 12, 4, '#ff3b5c', '#ffd9c0')
    rect(d, tx0 + 6, ty + 19, tx1 - tx0 - 12, 2, hx('#05030c'))


def gen_far():
    rng = random.Random(19960317)
    arr = np.zeros((H, FAR_W, 4), np.float32)
    banded(arr, 0, 352, SKY_PAL, 0, FAR_W, gamma=1.35)
    banded(arr, 352, H, ['#150d28', '#120a22', '#0e081c', '#0a0614'], 0, FAR_W, gamma=0.7)
    # 地平线光污染
    add_band(arr, 250, 356, (255, 47, 142), 0.22, 2.2)
    add_band(arr, 292, 360, (122, 60, 255), 0.24, 1.8)
    add_band(arr, 318, 360, (255, 138, 42), 0.10, 1.6)
    draw_far_moon(arr)
    # 星点
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    layer = Layer(FAR_W, H, base=img)
    d = layer.d
    for _ in range(150):
        x, y = rng.randrange(FAR_W), rng.randrange(6, 250)
        c = rng.choice(['#8fa6c8', '#c8d6ea', '#7f8fb5', '#e0e8f7'])
        px(d, x, y, hx(c, rng.randint(70, 190)))
        if rng.random() < 0.06:
            px(d, x - 1, y, hx(c, 70))
            px(d, x + 1, y, hx(c, 70))
            px(d, x, y - 1, hx(c, 70))
            px(d, x, y + 1, hx(c, 70))
    # 远处楼群
    arr2 = np.asarray(layer.img).astype(np.float32)
    arr2 = far_buildings(arr2, rng)
    layer.img = Image.fromarray(np.clip(arr2, 0, 255).astype(np.uint8))
    layer.d = ImageDraw.Draw(layer.img)
    draw_far_viaduct(layer, rng)
    # --- 远景高塔（保证中景缝隙里能看到天际线） ---
    def far_tower(tx, tw, ttop):
        d = layer.d
        rect(d, tx, ttop, tw, 352 - ttop, hx('#0d081c'))
        rect(d, tx, ttop, tw, 2, hx('#221640'))
        rect(d, tx, ttop, 2, 352 - ttop, hx('#1a1232'))
        rect(d, tx + tw - 3, ttop, 3, 352 - ttop, hx('#070411'))
        cols = max(1, (tw - 10) // 9)
        rows = max(1, (330 - ttop) // 11)
        for rr in range(rows):
            for cc in range(cols):
                if rng.random() < 0.24:
                    wx = tx + 5 + cc * 9
                    wy = ttop + 10 + rr * 11
                    if wy + 4 < 338:
                        rect(d, wx, wy, 3, 4,
                             hx(rng.choice(['#b58c34', '#22606c', '#7a2250', '#c9cfe0'])))
        # 塔顶天线 + 红色警示灯
        rect(d, tx + tw // 2, ttop - rng.randint(12, 26), 2, 26, hx('#0a0616'))
        glow_dot(layer, tx + tw // 2 + 1, ttop - 22, 2, '#ff3b5c', '#ffd9e0')
        # 竖向霓虹条
        if rng.random() < 0.7:
            col = rng.choice([CYAN, MAGENTA, YELLOW])
            layer.sd.line([(tx + tw - 7, ttop + 16), (tx + tw - 7, ttop + 90)],
                          fill=hx(col, 200), width=2)
            layer.sd.line([(tx + tw - 6, ttop + 16), (tx + tw - 6, ttop + 90)],
                          fill=hx('#ffffff', 170), width=1)
            layer.spills.append((tx + tw - 10, ttop + 90, 8, col, 0.3))
    far_tower(142, 58, 58)
    far_tower(688, 46, 96)
    far_tower(1268, 64, 44)
    # 远层广告牌 / 霓虹小招牌
    def billboard(sd, d):
        # A. 竖招牌
        sign_vertical(layer, 742, 148, 15, 64, '夜', 12, board='#0d0819',
                      border=CYAN_D, txt=CYAN, core='#d9ffff', border_w=1)
        # B. 横向霓虹
        sign_horizontal(layer, 1236, 226, 92, 17, 'NEON', 12, board='#12081a',
                        border=MAGENTA_D, txt=MAGENTA, core='#ffd7ea', border_w=1, latin=True)
        # C. 屋顶大广告牌（抽象画面）
        bx, by, bw, bh = 286, 176, 104, 62
        rect(d, bx - 2, by - 2, bw + 4, bh + 4, hx('#080410'))
        rect(d, bx, by, bw, bh, hx('#1a0d2c'))
        rect(d, bx + 3, by + 3, bw - 6, bh - 6, hx('#30143f'))
        rect(d, bx + 8, by + 8, 42, 46, hx('#101a30'))
        rect(d, bx + 14, by + 16, 20, 22, hx('#ff2f8e'))
        rect(d, bx + 18, by + 20, 12, 10, hx('#ffd23f'))
        rect(d, bx + 56, by + 10, 30, 4, hx('#3df3ff'))
        rect(d, bx + 56, by + 18, 34, 4, hx('#ff2f8e'))
        rect(d, bx + 56, by + 26, 22, 4, hx('#ffd23f'))
        rect(d, bx + 56, by + 40, 30, 10, hx('#0d0819'))
        layer.sd.rectangle([bx, by, bx + bw - 1, by + bh - 1], outline=hx('#a11856'))
        layer.sd.rectangle([bx + 3, by + 3, bx + bw - 4, by + bh - 4], outline=hx('#ff2f8e', 170))
        # 支撑杆
        rect(d, bx + 12, by + bh, 3, 352 - by - bh, hx('#0a0616'))
        rect(d, bx + bw - 16, by + bh, 3, 352 - by - bh, hx('#0a0616'))
    billboard(None, layer.d)
    # 天线红色警示灯
    for (x, y) in [(520, 132), (1310, 158), (980, 118)]:
        rect(layer.d, x, y, 2, 2, hx('#ff3b5c'))
        glow_dot(layer, x + 1, y + 1, 2, '#ff3b5c', '#ffd9e0')
    # 远处街灯 / 车灯
    for _ in range(26):
        x = rng.randrange(FAR_W)
        y = rng.randrange(330, 350)
        c = rng.choice(['#ffd23f', '#ff8a2a', '#3df3ff', '#ff3b5c'])
        px(layer.d, x, y, hx(c, rng.randint(70, 150)))
    # 雨雾 / 雨丝
    def rain(od):
        for _ in range(46):
            x = rng.randrange(FAR_W)
            y = rng.randrange(30, 300)
            ln = rng.randrange(18, 52)
            od.line([(x, y), (x + rng.randint(-2, 1), y + ln)],
                    fill=hx('#9fb6d8', rng.randint(10, 26)))
        for i in range(4):
            y0 = 300 + i * 14
            for yy in range(y0, min(352, y0 + 12)):
                t = (yy - y0) / 12.0
                od.line([(0, yy), (FAR_W, yy)], fill=hx('#6a4a9a', int(9 * t)))
    layer.overlay(rain)
    layer.finish(radius=7.0, gain=1.05, tight=2.0, tight_gain=0.6)
    # 远景层必须完全不透明（星点曾用半透明色直接绘制）
    layer.img.putalpha(255)
    print('  far  :', FAR_W, H)
    return layer


# ----------------------------------------------------------------------------
# 3. 中景 bg_mid
# ----------------------------------------------------------------------------
def draw_water_tank(d, x, y, w=22, h=16):
    rect(d, x, y, w, h, hx('#171028'))
    rect(d, x, y, w, 2, hx('#241a3c'))
    rect(d, x, y + h - 2, w, 2, hx('#0c0817'))
    rect(d, x + 3, y + h, 2, 10, hx('#0c0817'))
    rect(d, x + w - 5, y + h, 2, 10, hx('#0c0817'))
    for i in range(2):
        rect(d, x + 3 + i * (w // 2), y + 2, 1, h - 4, hx('#0f0a1c'))


def draw_ac(d, rng, x, y, w=17, h=13):
    rect(d, x - 1, y - 1, w + 2, h + 2, hx('#0b0714'))
    rect(d, x, y, w, h, hx('#231a36'))
    rect(d, x, y, w, 2, hx('#39294f'))
    rect(d, x, y + h - 2, w, 2, hx('#120d20'))
    cx, cy = x + w // 2, y + h // 2 + 1
    r = min(w, h) // 2 - 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=hx('#0d0917'))
    d.line([cx - r, cy, cx + r, cy], fill=hx('#0d0917'))
    d.line([cx, cy - r, cx, cy + r], fill=hx('#0d0917'))
    # 支架 + 滴水管
    rect(d, x + 2, y + h + 2, w - 4, 1, hx('#0d0818'))
    rect(d, x + w - 4, y + h + 2, 1, rng.randint(14, 30), hx('#0b0714', 140))


def draw_poster(d, rng, x, y, w=13, h=17):
    if rng.random() < 0.3:
        d.rectangle([x - 1, y, x + w, y + h], outline=hx('#1d1430'))
        rect(d, x, y, w, h, hx('#0e0a19'))
        return
    rect(d, x - 1, y - 1, w + 2, h + 2, hx('#0a0613'))
    bg = rng.choice(['#3a2450', '#4a1a3a', '#123a44', '#3d2a1a', '#2a2450'])
    rect(d, x, y, w, h, hx(bg))
    kind = rng.randrange(4)
    if kind == 0:
        rect(d, x + 3, y + 3, w - 6, 5, hx(rng.choice([CYAN, MAGENTA, YELLOW, ORANGE])))
        rect(d, x + 2, y + 9, w - 4, 2, hx('#0f0a1a'))
        rect(d, x + 4, y + 12, w - 7, 2, hx('#0f0a1a'))
    elif kind == 1:
        d.ellipse([x + 3, y + 2, x + w - 4, y + 10], fill=hx(rng.choice(['#d8455a', '#c9a13a', '#3df3ff'])))
        rect(d, x + 2, y + 12, w - 4, 2, hx('#0f0a1a'))
    elif kind == 2:
        for i in range(4):
            rect(d, x + 1 + i * 3, y + 2, 2, h - 4, hx(rng.choice([CYAN, MAGENTA, YELLOW, PURPLE])))
    else:
        rect(d, x + 1, y + 1, w - 2, h - 2, hx('#1b1230'))
        rect(d, x + 3, y + 3, w - 6, 4, hx(YELLOW))
        rect(d, x + 3, y + 9, w - 6, 1, hx(STEEL_D))
        rect(d, x + 3, y + 11, w - 8, 1, hx(STEEL_D))
    # 撕角 / 胶带
    if rng.random() < 0.5:
        rect(d, x, y, 3, 2, hx('#d7c8a0', 120))
    if rng.random() < 0.4:
        d.polygon([(x + w - 1, y + h - 4), (x + w - 1, y + h - 1), (x + w - 4, y + h - 1)],
                  fill=hx('#0e0a19'))


def draw_pipe_v(d, x, y0, y1, w=3, col='#191129'):
    rect(d, x, y0, w, y1 - y0, hx(col))
    rect(d, x, y0, 1, y1 - y0, hx('#2a2040'))
    for y in range(y0 + 8, y1, 22):
        rect(d, x - 1, y, w + 2, 2, hx('#0d0818'))
    if (y1 - y0) > 20:
        rect(d, x + w - 1, y0, 1, y1 - y0, hx('#0a0614'))


def draw_windows(layer, rng, x, w, top, bottom=330, margin=13,
                 win_w=None, win_h=None, gapx=None, floor_h=None, lit_prob=0.32):
    d = layer.d
    win_w = win_w or rng.choice([8, 9, 10, 11, 12])
    win_h = win_h or win_w + rng.choice([2, 3, 4])
    gapx = gapx or rng.choice([6, 7, 8, 9])
    floor_h = floor_h or win_h + rng.choice([10, 12, 14])
    cols = max(1, (w - 2 * margin + gapx) // (win_w + gapx))
    rows = max(1, (bottom - 26 - (top + 16)) // floor_h)
    for rr in range(rows):
        for cc in range(cols):
            wx = x + margin + cc * (win_w + gapx)
            wy = top + 14 + rr * floor_h
            if wy + win_h > bottom - 6:
                continue
            lit = rng.random() < lit_prob
            rect(d, wx - 1, wy - 1, win_w + 2, win_h + 2, hx('#080510'))
            if lit:
                c = rng.choice(WINDOW_LIT)
                rect(d, wx, wy, win_w, win_h, hx(c))
                k = rng.random()
                if k < 0.25:
                    rect(d, wx, wy, win_w, 2, hx('#0d0a18'))
                    rect(d, wx, wy + 4, win_w, 1, hx('#0d0a18'))
                elif k < 0.4:
                    rect(d, wx, wy, win_w, win_h, hx(c))
                    rect(d, wx, wy + win_h - 3, win_w, 3, hx(shade(c, 0.55)))
                elif k < 0.5:
                    rect(d, wx + win_w // 2 - 1, wy + 2, 2, win_h - 2, hx(shade(c, 0.45)))
                # 窗框与窗台
                rect(d, wx + win_w // 2, wy, 1, win_h, hx('#0d0a18', 90))
                rect(d, wx - 1, wy + win_h + 1, win_w + 2, 1, hx('#332348'))
            else:
                rect(d, wx, wy, win_w, win_h, hx(rng.choice(WINDOW_DARK)))
                rect(d, wx, wy, win_w, 1, hx('#241a38'))
                rect(d, wx, wy, 1, win_h, hx('#1b1230'))
    return rows, cols


def draw_roof(layer, rng, x, w, top):
    """屋顶附加物（水塔 / 天线 / 空调 / 栏杆 / 广告架）"""
    d = layer.d
    rect(d, x - 2, top - 5, w + 4, 5, hx('#1b1130'))
    rect(d, x - 2, top - 6, w + 4, 2, hx('#2f1f4a'))
    r = rng.random()
    if r < 0.28:
        tx = x + rng.randint(8, max(10, w - 34))
        draw_water_tank(d, tx, top - 30, 22, 17)
    elif r < 0.5:
        tx = x + rng.randint(6, max(8, w - 12))
        hh = rng.randint(18, 40)
        rect(d, tx, top - hh, 2, hh, hx('#0b0716'))
        rect(d, tx - 5, top - hh + 8, 12, 1, hx('#0b0716'))
        rect(d, tx - 3, top - hh + 14, 8, 1, hx('#0b0716'))
        rect(d, tx, top - hh, 1, hh, hx('#241a3c'))
    elif r < 0.68:
        draw_ac(d, rng, x + rng.randint(4, max(6, w - 24)), top - 16, 17, 12)
    elif r < 0.82:
        # 栏杆
        for i in range(0, w, 9):
            rect(d, x + i, top - 12, 1, 12, hx('#0d0919'))
        rect(d, x, top - 13, w, 1, hx('#0d0919'))
    # 顶部小灯
    if rng.random() < 0.45:
        glow_dot(layer, x + rng.randint(6, max(8, w - 8)), top - 8, 1,
                 rng.choice([RED, CYAN, YELLOW]), '#ffffff')


def draw_awning(layer, rng, x, y, w, color1='#3a1a34', color2='#22112a'):
    d = layer.d
    rect(d, x, y, w, 4, hx('#0d0818'))
    rect(d, x, y + 4, w, 9, hx(color1))
    for i in range(0, w, 14):
        rect(d, x + i, y + 4, 7, 9, hx(color2))
    rect(d, x, y + 13, w, 2, hx('#0d0818'))
    # 支撑杆
    rect(d, x + 2, y + 15, 1, 8, hx('#0a0614'))
    rect(d, x + w - 3, y + 15, 1, 8, hx('#0a0614'))


def draw_shutter(layer, rng, x, y, w, h, gtag=True):
    d = layer.d
    rect(d, x - 2, y - 2, w + 4, h + 4, hx('#07040e'))
    rect(d, x, y, w, h, hx('#191228'))
    for yy in range(y + 2, y + h - 1, 3):
        rect(d, x + 1, yy, w - 2, 1, hx('#231a36'))
    rect(d, x, y, w, 1, hx('#2b2042'))
    rect(d, x, y + h - 2, w, 2, hx('#0d0917'))
    rect(d, x, y, 2, h, hx('#0d0917'))
    rect(d, x + w - 2, y, 2, h, hx('#0d0917'))
    if gtag:
        # 卷帘门涂鸦
        def graf(od):
            pal = [MAGENTA, CYAN, YELLOW, PURPLE, ORANGE]
            for _ in range(rng.randint(2, 3)):
                col = rng.choice(pal)
                pts = []
                xx = x + rng.randint(4, max(6, w - 30))
                yy = y + rng.randint(6, max(8, h - 14))
                for k in range(rng.randint(3, 6)):
                    pts.append((xx + rng.randint(0, 22), yy + rng.randint(-7, 7)))
                    xx += rng.randint(3, 9)
                od.line(pts, fill=hx(col, rng.randint(80, 150)), width=rng.choice([1, 1, 2]))
            # 滴落
            for _ in range(rng.randint(2, 5)):
                gx = x + rng.randint(4, max(6, w - 6))
                gy = y + rng.randint(8, max(10, h - 10))
                od.line([(gx, gy), (gx, gy + rng.randint(3, 12))],
                        fill=hx('#a11856', 90), width=1)
        layer.overlay(graf)
    # 底部锈迹
    rect(d, x + 2, y + h - 4, w - 4, 1, hx('#2a1622', 120))


def draw_noren(layer, rng, x, y, w, h=26, col='#7a1838'):
    d = layer.d
    panels = 3
    pw = (w - (panels - 1) * 2) // panels
    for i in range(panels):
        px0 = x + i * (pw + 2)
        rect(d, px0, y, pw, h, hx(col))
        rect(d, px0, y, pw, 2, hx(shade(col, 0.7)))
        rect(d, px0 + 1, y + h - 3, pw - 2, 2, hx(shade(col, 0.55)))
        rect(d, px0 + pw // 2, y + 5, 1, h - 10, hx(shade(col, 0.62)))
    rect(d, x - 2, y - 2, w + 4, 2, hx('#0a0614'))


def draw_lantern(d, x, y, r=8, col='#ff3b5c', dark='#8a1a34', ch=None):
    d.ellipse([x - r, y - r, x + r, y + r], fill=hx(col))
    d.ellipse([x - r, y - r, x + r, y + r], outline=hx('#0a0614'))
    for i in range(-1, 2):
        yy = y + i * max(2, r // 2)
        d.line([(x - r + 2, yy), (x + r - 2, yy)], fill=hx(dark))
    rect(d, x - 2, y - r - 3, 4, 3, hx('#0a0614'))
    rect(d, x - 2, y + r, 4, 3, hx('#0a0614'))
    rect(d, x, y + r + 3, 1, 3, hx('#0a0614'))


def draw_graffiti_wall(layer, rng, x, y, w, h):
    draw_shutter(layer, rng, x, y, w, h)


# --- 各类建筑 --------------------------------------------------------------
def bld_apartment(layer, rng, x, w, top):
    d = layer.d
    col = rng.choice(FACADE_PAL)
    rect(d, x, top, w, 344 - top, hx(col))
    rect(d, x, top, 2, 344 - top, hx(rng.choice(FACADE_HI)))
    rect(d, x + w - 3, top, 3, 344 - top, hx(rng.choice(FACADE_DARK)))
    for yy in range(top + 8, 336, rng.choice([7, 9, 11])):
        rect(d, x + 2, yy, w - 4, 1, hx('#000000', 30))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 336)
    # 侧墙空调外机 / 海报
    for _ in range(rng.randint(1, 3)):
        ax = x + rng.randint(6, max(8, w - 26))
        ay = rng.randint(top + 30, max(top + 34, 292))
        if rng.random() < 0.6:
            draw_ac(d, rng, ax, ay)
        else:
            draw_poster(d, rng, ax, ay)
    # 底层入口
    ex = x + rng.randint(10, max(12, w - 40))
    rect(d, ex, 300, 26, 30, hx('#0c0817'))
    rect(d, ex + 2, 302, 22, 26, hx('#241436'))
    rect(d, ex + 2, 302, 22, 2, hx('#3b2a52'))
    if rng.random() < 0.5:
        glow_dot(layer, ex + 13, 306, 2, '#ffd23f', '#fff4cc')


def bld_ramen(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#241227'))
    rect(d, x, top, 2, 344 - top, hx('#3a1c38'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0f0919'))
    # 上层窗
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 236, margin=16, lit_prob=0.5,
                 win_w=10, win_h=12, floor_h=26)
    # 店面木格栅
    for yy in range(240, 296, 6):
        rect(d, x + 8, yy, w - 16, 1, hx('#5a2a24', 90))
    # 横向主招牌
    sign_horizontal(layer, x + 12, 198, w - 24, 40, '拉面', 24,
                    board='#20101a', border='#ffd23f', txt='#ffd23f',
                    core='#fff6d2', border_w=2)
    # 招牌小灯
    for i in range(4):
        glow_dot(layer, x + 26 + i * (w - 60) // 3, 194, 1, '#ffd23f', '#ffffff')
    # 红灯笼
    draw_lantern(d, x + 26, 262, 8)
    draw_lantern(d, x + w - 27, 262, 8)
    layer.sd.ellipse([x + 18, 254, x + 34, 270], outline=hx('#ff3b5c', 120))
    layer.sd.ellipse([x + w - 35, 254, x + w - 19, 270], outline=hx('#ff3b5c', 120))
    # 门帘
    draw_noren(layer, rng, x + 32, 276, w - 64, 30, '#8a1a3a')
    # 门口暖光
    def warm(od):
        for yy in range(286, 330):
            t = (yy - 286) / 44.0
            od.line([(x + 18, yy), (x + w - 19, yy)],
                    fill=(255, 150, 70, int(26 + 34 * (1 - t))))
    layer.overlay(warm)
    # 竖排小招牌「麺」
    sign_vertical(layer, x + w - 22, 252, 15, 44, '面', 12,
                  board='#1a0c14', border='#ff8a2a', txt='#ffd23f', core='#fff3c8', border_w=1)


def bld_izakaya(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#1b1028'))
    rect(d, x, top, 2, 344 - top, hx('#33204a'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0d0818'))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 250, margin=18, lit_prob=0.4)
    # 木格栅装饰
    for yy in range(254, 300, 5):
        rect(d, x + 6, yy, w - 12, 1, hx('#4a2a1a', 70))
    # 竖招牌：居酒屋
    sign_vertical(layer, x + w - 44, 176, 30, 124, '居酒屋', 20,
                  board='#180b16', border=MAGENTA, txt=MAGENTA, core='#ffe0ef', border_w=2)
    # 灯笼串
    for i in range(4):
        lx = x + 18 + i * 20
        rect(d, lx, 250, 1, 8, hx('#0a0614'))
        draw_lantern(d, lx, 268, 7, '#ff8a2a', '#8a3a1a')
        layer.sd.ellipse([lx - 7, 261, lx + 7, 275], outline=hx('#ff8a2a', 110))
    # 门帘
    draw_noren(layer, rng, x + 16, 286, w - 84, 32, '#1a2444')
    # 门口暖光
    def warm(od):
        for yy in range(292, 330):
            od.line([(x + 12, yy), (x + w - 60, yy)], fill=(255, 120, 60, 30))
    layer.overlay(warm)
    # 侧墙小海报
    draw_poster(d, rng, x + 10, 210, 12, 16)


def bld_shutter(layer, rng, x, w, top, gtag=True):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx(rng.choice(['#1d112e', '#211432', '#191028'])))
    rect(d, x, top, 2, 344 - top, hx('#33204a'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0d0818'))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 210, margin=14, lit_prob=0.22)
    draw_shutter(layer, rng, x + 8, 236, w - 16, 96, gtag)
    # 海报 / 电表箱
    draw_poster(d, rng, x + 4, 246, 13, 17)
    rect(d, x + w - 22, 246, 14, 18, hx('#1f1730'))
    rect(d, x + w - 21, 247, 12, 8, hx('#0d0919'))
    rect(d, x + w - 21, 257, 12, 5, hx('#0d0919'))
    # 顶部小招牌
    if rng.random() < 0.6:
        sign_horizontal(layer, x + 6, 196, w - 12, 26, 'OPEN', 14,
                        board='#120a16', border=CYAN_D, txt=CYAN, core='#ddffff',
                        border_w=1, latin=True)


def bld_service(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#171026'))
    rect(d, x, top, 2, 344 - top, hx('#2a1c40'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0b0717'))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 230, margin=12, lit_prob=0.14, win_w=8, win_h=9)
    # 管道
    draw_pipe_v(d, x + 10, 236, 344, 3)
    draw_pipe_v(d, x + w - 16, 210, 344, 4)
    draw_pipe_v(d, x + w // 2, 254, 344, 2)
    # 消防梯
    for yy in range(198, 330, 16):
        rect(d, x + w - 42, yy, 28, 2, hx('#0d0919'))
        rect(d, x + w - 42, yy, 1, 16, hx('#0d0919'))
    # 排风口
    rect(d, x + 16, 260, 22, 14, hx('#0b0716'))
    for i in range(4):
        rect(d, x + 18 + i * 5, 262, 2, 10, hx('#241a3c'))
    # 蒸汽
    def steam(od):
        for i in range(3):
            cx = x + 28 + i * 6
            for k in range(18):
                yy = 252 - k * 2
                rr = 1 + k // 6
                od.ellipse([cx - rr, yy - rr, cx + rr, yy + rr],
                           outline=(200, 220, 255, max(0, 26 - k)))
    layer.overlay(steam)
    # 小霓虹箭头
    layer.sd.line([(x + w // 2 + 6, 214), (x + w // 2 + 22, 214)],
                  fill=hx(CYAN), width=2)
    layer.sd.polygon([(x + w // 2 + 20, 208), (x + w // 2 + 28, 214), (x + w // 2 + 20, 220)],
                     fill=hx(CYAN))


def bld_arcade(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#151029'))
    rect(d, x, top, 2, 344 - top, hx('#2b2050'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0b0717'))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 226, margin=14, lit_prob=0.3)
    # 大招牌「电玩」
    sign_horizontal(layer, x + 10, 172, w - 20, 44, '电玩', 26,
                    board='#0d1a26', border=CYAN, txt=CYAN, core='#e8ffff', border_w=2)
    # 竖排 GAME
    sign_vertical(layer, x + w - 26, 230, 16, 86, 'GAME', 12,
                  board='#120a1a', border=MAGENTA, txt=MAGENTA, core='#ffd9ec',
                  border_w=1, latin=True)
    # 明亮橱窗（街机厅）
    wx, wy, ww, wh = x + 12, 240, w - 52, 76
    rect(d, wx - 3, wy - 3, ww + 6, wh + 6, hx('#07040e'))
    rect(d, wx, wy, ww, wh, hx('#0e1a2a'))
    for i in range(3):
        for j in range(2):
            mx = wx + 8 + i * ((ww - 16) // 3)
            my = wy + 8 + j * 34
            body = rng.choice(['#241a3c', '#2a1a3e', '#1c1834'])
            rect(d, mx, my, 18, 26, hx(body))
            rect(d, mx + 2, my + 2, 14, 10, hx(rng.choice([CYAN, MAGENTA, YELLOW, PURPLE])))
            rect(d, mx + 2, my + 14, 14, 6, hx('#0d0919'))
            rect(d, mx + 4, my + 15, 3, 3, hx(ORANGE))
            rect(d, mx + 10, my + 15, 3, 3, hx(ORANGE))
            glow_dot(layer, mx + 9, my + 7, 1, CYAN, '#ffffff')
    # 橱窗地面反光
    def spill(od):
        for yy in range(300, 330):
            od.line([(wx, yy), (wx + ww, yy)], fill=(70, 220, 255, 22))
    layer.overlay(spill)
    # 门口
    rect(d, x + 14, 320, 20, 16, hx('#0b0716'))


def bld_ktv(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#1a0f2e'))
    rect(d, x, top, 2, 344 - top, hx('#33204f'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0c0818'))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 230, margin=12, lit_prob=0.35, win_w=8, win_h=10)
    # KTV 竖招牌
    sign_vertical(layer, x + 8, 150, 26, 96, 'KTV', 13,
                  board='#1a0a1e', border=MAGENTA, txt=MAGENTA, core='#ffe0f0', border_w=2)
    # 门头横招牌
    sign_horizontal(layer, x + 40, 214, w - 52, 26, 'KTV', 14,
                    board='#120a16', border=CYAN, txt=CYAN, core='#e6ffff', border_w=1, latin=True)
    # 粉色霓虹灯管
    layer.sd.line([(x + w - 10, 180), (x + w - 10, 330)], fill=hx(MAGENTA, 190), width=2)
    layer.sd.line([(x + w - 9, 180), (x + w - 9, 180)], fill=hx('#ffffff'))
    # 门口暖光
    rect(d, x + 16, 300, 22, 36, hx('#140a1a'))
    glow_dot(layer, x + 27, 302, 2, '#ff3b5c', '#ffd9e0')


def bld_bar(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#1b1226'))
    rect(d, x, top, 2, 344 - top, hx('#2f2348'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0c0816'))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 240, margin=14, lit_prob=0.27)
    # BAR 霓虹
    sign_horizontal(layer, x + 18, 196, w - 36, 34, 'BAR', 16,
                    board='#120a18', border=CYAN, txt=CYAN, core='#e8ffff', border_w=2, latin=True)
    # 鸡尾酒霓虹图标
    gx, gy = x + w - 40, 250
    layer.sd.polygon([(gx - 10, gy - 10), (gx + 10, gy - 10), (gx, gy + 4)], outline=hx(MAGENTA))
    layer.sd.line([(gx, gy + 4), (gx, gy + 12)], fill=hx(MAGENTA), width=2)
    layer.sd.line([(gx - 6, gy + 13), (gx + 6, gy + 13)], fill=hx(MAGENTA), width=2)
    layer.sd.ellipse([gx + 2, gy - 14, gx + 7, gy - 9], outline=hx(YELLOW))
    # 雨棚
    draw_awning(layer, rng, x + 12, 270, w - 24, '#3a1a34', '#22112a')
    # 门 + 暖光
    rect(d, x + 24, 292, 24, 44, hx('#0e0814'))
    rect(d, x + 26, 294, 20, 40, hx('#2a1626'))
    rect(d, x + 36, 294, 1, 40, hx('#0a0614'))
    glow_dot(layer, x + 30, 288, 1, '#ffd23f', '#ffffff')
    glow_dot(layer, x + 44, 288, 1, '#ffd23f', '#ffffff')
    # 小竖牌
    sign_vertical(layer, x + w - 20, 286, 14, 42, '酒', 12,
                  board='#1a0d14', border=YELLOW, txt=YELLOW, core='#fff6cc', border_w=1)


def bld_dojo(layer, rng, x, w, top):
    """Boss 区：铁面道场 —— 霸气的大型立面。"""
    d = layer.d
    # 主体
    rect(d, x, top, w, 344 - top, hx('#160c22'))
    rect(d, x, top, 3, 344 - top, hx('#2b1740'))
    rect(d, x + w - 4, top, 4, 344 - top, hx('#090512'))
    # 屋檐（多层瓦）
    for i in range(3):
        yy = top + 2 + i * 7
        rect(d, x - 6, yy, w + 12, 6, hx(['#1f1234', '#1a0f2c', '#150b25'][i]))
        rect(d, x - 6, yy, w + 12, 1, hx('#34204f'))
    rect(d, x - 10, top - 4, w + 20, 5, hx('#0b0716'))
    rect(d, x - 10, top - 6, w + 20, 2, hx('#3d1a5c'))
    # 屋顶两端翘角
    d.polygon([(x - 14, top - 2), (x - 2, top - 8), (x + 2, top - 1)], fill=hx('#0b0716'))
    d.polygon([(x + w + 12, top - 2), (x + w - 0, top - 8), (x + w - 4, top - 1)], fill=hx('#0b0716'))
    # 顶部霓虹描边
    layer.sd.line([(x - 12, top - 7), (x + w + 12, top - 7)], fill=hx(MAGENTA), width=2)
    # 大灯笼一对
    for lx in (x + 16, x + w - 17):
        rect(d, lx, 40, 1, 60, hx('#0a0614'))
        draw_lantern(d, lx, 128, 10, '#ff3b5c', '#8a1a34')
        layer.sd.ellipse([lx - 10, 118, lx + 10, 138], outline=hx('#ff3b5c', 130))
    # 巨型竖幅「铁面」
    bw, bh = 56, 190
    bx, by = x + w // 2 - bw // 2, 78
    rect(d, bx - 2, by - 2, bw + 4, bh + 4, hx('#07040e'))
    rect(d, bx, by, bw, bh, hx('#5a1220'))
    rect(d, bx, by, bw, 4, hx('#7a1a2c'))
    rect(d, bx, by, 3, bh, hx('#7a1a2c'))
    rect(d, bx + bw - 3, by, 3, bh, hx('#3a0812'))
    rect(d, bx, by + bh - 4, bw, 4, hx('#3a0812'))
    # 白字
    m = text_mask('铁面', 32, vertical=True, gap=10)
    stamp(layer.img, m, bx + (bw - m.width) // 2, by + 12, hx('#f7e9d7'))
    # 横幅霓虹框
    layer.sd.rectangle([bx - 4, by - 4, bx + bw + 3, by + bh + 3], outline=hx('#ff8a2a', 170))
    # 墙面龙纹（抽象剪影）
    def dragon(od):
        pts = []
        for i in range(26):
            t = i / 25.0
            pts.append((x + 30 + t * (w - 60), 210 + math.sin(t * 7.0 + 1) * 18 + t * 40))
        od.line(pts, fill=hx('#2a1a44', 160), width=3)
        for i in range(6):
            t = i / 5.0
            cx = x + 30 + t * (w - 60)
            cy = 210 + math.sin(t * 7.0 + 1) * 18 + t * 40
            od.line([(cx, cy), (cx - 6, cy - 8)], fill=hx('#2a1a44', 150), width=2)
    layer.overlay(dragon)
    # 底部铁门
    gx, gy, gw, gh = x + 22, 262, w - 44, 78
    rect(d, gx - 3, gy - 3, gw + 6, gh + 6, hx('#07040e'))
    rect(d, gx, gy, gw, gh, hx('#1d1830'))
    rect(d, gx, gy, gw // 2 - 2, gh, hx('#221d36'))
    rect(d, gx + gw // 2 + 2, gy, gw // 2 - 2, gh, hx('#1b1730'))
    for i in range(2):
        bx0 = gx + i * (gw // 2 + 2)
        for xx in range(bx0 + 4, bx0 + gw // 2 - 4, 9):
            rect(d, xx, gy + 4, 1, gh - 8, hx('#2c2744'))
        rect(d, bx0 + 2, gy + 4, gw // 2 - 4, 1, hx('#2c2744'))
        rect(d, bx0 + 2, gy + gh - 5, gw // 2 - 4, 1, hx('#0d0a18'))
        # 铆钉
        for yy in range(gy + 8, gy + gh - 8, 12):
            rect(d, bx0 + 6, yy, 1, 1, hx('#4a4368'))
            rect(d, bx0 + gw // 2 - 8, yy, 1, 1, hx('#4a4368'))
    # 警示条
    for xx in range(gx, gx + gw, 12):
        d.polygon([(xx, gy + gh + 3), (xx + 6, gy + gh + 3), (xx + 9, 343), (xx + 3, 343)],
                  fill=hx('#b8912a'))
        d.polygon([(xx + 6, gy + gh + 3), (xx + 12, gy + gh + 3), (xx + 15, 343), (xx + 9, 343)],
                  fill=hx('#141021'))
    # 霓虹门框
    layer.sd.line([(gx - 5, gy - 5), (gx + gw + 4, gy - 5)], fill=hx(CYAN), width=2)
    layer.sd.line([(gx - 5, gy - 5), (gx - 5, 336)], fill=hx(CYAN_D), width=1)
    layer.sd.line([(gx + gw + 4, gy - 5), (gx + gw + 4, 336)], fill=hx(CYAN_D), width=1)
    # 门口红光
    def redlight(od):
        for yy in range(300, 336):
            od.line([(gx, yy), (gx + gw, yy)], fill=(255, 59, 92, 22))
    layer.overlay(redlight)


def bld_industrial(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#191227'))
    rect(d, x, top, 2, 344 - top, hx('#2d2144'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0a0616'))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 250, margin=10, lit_prob=0.12, win_w=8, win_h=8,
                 floor_h=18, gapx=5)
    # 大排风管
    for i in range(2):
        yy = 190 + i * 58
        rect(d, x + 6, yy, w - 12, 14, hx('#221a34'))
        rect(d, x + 6, yy, w - 12, 2, hx('#33284c'))
        rect(d, x + 6, yy + 12, w - 12, 2, hx('#0d0918'))
        for xx in range(x + 10, x + w - 12, 18):
            rect(d, xx, yy, 2, 14, hx('#0d0918'))
    draw_pipe_v(d, x + 14, top + 20, 344, 4)
    draw_pipe_v(d, x + w - 18, 200, 344, 3)
    # 工业警示牌
    rect(d, x + w // 2 - 12, 252, 24, 16, hx('#b8912a'))
    rect(d, x + w // 2 - 10, 254, 20, 12, hx('#141021'))
    d.polygon([(x + w // 2, 256), (x + w // 2 + 5, 264), (x + w // 2 - 5, 264)], fill=hx('#b8912a'))
    # 小黄灯
    glow_dot(layer, x + 10, 210, 2, '#ffd23f', '#fff6cc')
    # 底部卷帘
    draw_shutter(layer, rng, x + 10, 286, w - 20, 42, gtag=False)


def bld_billboard(layer, rng, x, w, top):
    """巨型霓虹广告牌：霓虹 / NEON。"""
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#140d22'))
    rect(d, x, top, 2, 344 - top, hx('#291c42'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#090512'))
    draw_windows(layer, rng, x, w, top, 260, margin=14, lit_prob=0.18, win_w=9, win_h=10)
    # 广告牌支架
    bx, by, bw, bh = x - 12, 20, w + 24, 182
    for lx in (bx + 8, bx + bw // 2 - 2, bx + bw - 12):
        rect(d, lx, by + bh, 4, 344 - by - bh, hx('#0c0817'))
        rect(d, lx + 1, by + bh, 1, 344 - by - bh, hx('#241a3c'))
    # 牌面
    rect(d, bx - 2, by - 2, bw + 4, bh + 4, hx('#06030c'))
    rect(d, bx, by, bw, bh, hx('#0f0a20'))
    rect(d, bx + 3, by + 3, bw - 6, bh - 6, hx('#1a1030'))
    # 背景速度线
    for i in range(8):
        yy = by + 14 + i * 20
        d.polygon([(bx + 8, yy), (bx + bw - 8, yy - 8), (bx + bw - 8, yy - 5), (bx + 8, yy + 3)],
                  fill=hx('#241640'))
    # 大字「霓虹」竖排
    m = text_mask('霓虹', 62, block=2, vertical=True, gap=6)
    tx = bx + (bw - m.width) // 2
    ty = by + (bh - m.height) // 2
    # 描边暗色
    stamp(layer.img, m.filter(ImageFilter.MaxFilter(3)), tx - 2, ty - 2, hx('#0a0614'))
    # 霓（品红）虹（青）分别上色
    mm = text_mask('霓', 62, block=2)
    m2 = text_mask('虹', 62, block=2)
    stamp(layer.signs, mm, tx + (m.width - mm.width) // 2, ty, hx(MAGENTA))
    stamp(layer.signs, mm.filter(ImageFilter.MinFilter(3)), tx + (m.width - mm.width) // 2, ty, hx('#ffe0ef'), 220)
    stamp(layer.signs, m2, tx + (m.width - m2.width) // 2, ty + mm.height + 6, hx(CYAN))
    stamp(layer.signs, m2.filter(ImageFilter.MinFilter(3)), tx + (m.width - m2.width) // 2, ty + mm.height + 6, hx('#e8ffff'), 220)
    # 牌框霓虹
    layer.sd.rectangle([bx, by, bx + bw - 1, by + bh - 1], outline=hx(PURPLE), width=2)
    layer.sd.rectangle([bx + 3, by + 3, bx + bw - 4, by + bh - 4], outline=hx(CYAN_D, 160))
    # 角标
    for (cx, cy) in [(bx, by), (bx + bw - 1, by), (bx, by + bh - 1), (bx + bw - 1, by + bh - 1)]:
        glow_dot(layer, cx, cy, 2, YELLOW, '#fffde0')
    # 射灯
    for sx in (bx + 16, bx + bw - 18):
        rect(d, sx - 3, by - 8, 7, 7, hx('#241a36'))
        rect(d, sx - 2, by - 7, 5, 5, hx('#b8912a'))
    # 底部店面
    draw_shutter(layer, rng, x + 10, 288, w - 20, 42, gtag=False)
    glow_dot(layer, x + w // 2, 282, 2, MAGENTA, '#ffd9ec')


def bld_residential(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#1c1230'))
    rect(d, x, top, 2, 344 - top, hx('#33224d'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0c0817'))
    draw_roof(layer, rng, x, w, top)
    # 阳台层
    floors = max(2, (330 - top) // 46)
    for i in range(floors):
        fy = top + 26 + i * 46
        if fy + 30 > 334:
            break
        rect(d, x + 6, fy + 24, w - 12, 3, hx('#0d0918'))
        for xx in range(x + 6, x + w - 10, 5):
            rect(d, xx, fy + 18, 1, 7, hx('#0d0918'))
        rect(d, x + 6, fy + 18, w - 12, 1, hx('#0d0918'))
        # 阳台后窗
        for cc in range(max(1, (w - 24) // 22)):
            wx = x + 12 + cc * 22
            if wx + 12 > x + w - 8:
                break
            lit = rng.random() < 0.45
            rect(d, wx, fy + 4, 12, 14, hx(rng.choice(WINDOW_LIT) if lit else rng.choice(WINDOW_DARK)))
            if lit:
                rect(d, wx, fy + 4, 12, 2, hx('#0d0a18'))
            rect(d, wx - 1, fy + 3, 14, 16, outline=hx('#0a0614'))
        # 晒衣
        if rng.random() < 0.6:
            rect(d, x + 8, fy + 12, w - 18, 1, hx('#2a2140'))
            for k in range(rng.randint(2, 4)):
                cx = x + 18 + k * rng.randint(16, 30)
                if cx + 8 < x + w - 12:
                    hh = rng.randint(6, 12)
                    rect(d, cx, fy + 12, 7, hh, hx(rng.choice(['#2a1a3a', '#1a2440', '#3a2a28'])))
    # 空调
    for _ in range(rng.randint(1, 2)):
        draw_ac(d, rng, x + rng.randint(8, max(10, w - 26)), rng.randint(top + 26, max(top + 30, 300)))
    # 底层门洞
    rect(d, x + w // 2 - 12, 304, 24, 32, hx('#0a0617'))
    rect(d, x + w // 2 - 10, 306, 20, 30, hx('#1c1428'))
    glow_dot(layer, x + w // 2, 300, 2, '#ffd23f', '#fff4cc')


def bld_service2(layer, rng, x, w, top):
    d = layer.d
    rect(d, x, top, w, 344 - top, hx('#181126'))
    rect(d, x, top, 2, 344 - top, hx('#2a1e40'))
    rect(d, x + w - 3, top, 3, 344 - top, hx('#0a0616'))
    draw_roof(layer, rng, x, w, top)
    draw_windows(layer, rng, x, w, top, 260, margin=12, lit_prob=0.2)
    # 铁网围栏
    for xx in range(x + 8, x + w - 8, 6):
        rect(d, xx, 300, 1, 40, hx('#1f1830'))
    for yy in range(300, 340, 8):
        rect(d, x + 8, yy, w - 16, 1, hx('#1f1830'))
    # 空调 & 垃圾桶
    draw_ac(d, rng, x + 12, 250)
    rect(d, x + w - 40, 316, 18, 24, hx('#151022'))
    rect(d, x + w - 38, 314, 14, 3, hx('#241a36'))
    # 小霓虹「酒」
    sign_vertical(layer, x + w - 26, 180, 16, 44, '酒', 13,
                  board='#180b14', border=YELLOW, txt=YELLOW, core='#fff6cc', border_w=1)


def gen_mid():
    rng = random.Random(19880808)
    layer = Layer(W, H)
    d = layer.d
    # ---- 后层楼群（更暗，出现在楼顶轮廓与巷口） ----
    backs = [(-90, 210, -10), (150, 150, 70), (420, 190, 20), (690, 170, -20),
             (1030, 210, 10), (1350, 170, 40), (1580, 190, -10), (1810, 180, 20),
             (2000, 170, -10), (2200, 180, 50), (2420, 170, 10), (2700, 200, 30),
             (2950, 220, -10)]
    for (bx, bw, btop) in backs:
        col = rng.choice(['#120b22', '#140c26', '#110a20'])
        rect(d, bx, btop, bw, 344 - btop, hx(col))
        rect(d, bx, btop, bw, 2, hx('#1d1336'))
        rect(d, bx, btop, 2, 344 - btop, hx('#1a1130'))
        rect(d, bx + bw - 2, btop, 2, 344 - btop, hx('#080411'))
        # 零星窗
        for _ in range(rng.randint(3, 10)):
            wx = bx + rng.randint(6, max(8, bw - 8))
            wy = rng.randint(btop + 14, 320)
            if rng.random() < 0.5:
                rect(d, wx, wy, 2, 3, hx(rng.choice(['#8a6a20', '#22606c', '#7a2250']), 150))
        # 屋顶装置
        if rng.random() < 0.5:
            tx = bx + rng.randint(8, max(10, bw - 20))
            if rng.random() < 0.5:
                draw_water_tank(d, tx, btop - 24)
            else:
                rect(d, tx, btop - rng.randint(18, 40), 2, 40, hx('#0a0616'))
    # ---- 前层建筑 ----
    specs = [
        (-60, 260, 40, bld_apartment),
        (200, 210, 130, bld_ramen),
        (410, 190, 50, bld_izakaya),
        (600, 130, 150, bld_shutter),
        (730, 115, 190, bld_service),
        # 巷口 845..900
        (900, 190, 70, bld_arcade),
        (1090, 120, 30, bld_ktv),
        (1210, 180, 110, bld_bar),
        (1390, 210, 20, bld_dojo),
        (1600, 150, 120, bld_industrial),
        (1750, 200, 10, bld_billboard),
        (1950, 140, 90, bld_industrial),
        (2090, 170, 60, bld_apartment),
        (2260, 160, 190, bld_service2),
        (2420, 200, 70, bld_apartment),
        (2620, 200, 150, bld_shutter),
        (2820, 190, 40, bld_apartment),
        (3010, 210, 120, bld_bar),
    ]
    for (x, w, top, fn) in specs:
        fn(layer, rng, x, w, top)
    # ---- 巷口（看到远景 + 蒸汽 + 铁网门） ----
    ax0, ax1 = 845, 900
    rect(d, ax0, 180, ax1 - ax0, 164, hx('#0b0716', 190))
    # 巷口内部低亮度地面
    rect(d, ax0, 300, ax1 - ax0, 44, hx('#181026'))
    rect(d, ax0, 300, ax1 - ax0, 2, hx('#2a1c40'))
    for yy in range(306, 344, 9):
        rect(d, ax0, yy, ax1 - ax0, 1, hx('#0c0817', 120))
    # 铁网门
    for xx in range(ax0 + 2, ax1 - 1, 4):
        rect(d, xx, 250, 1, 94, hx('#1d1730'))
    for yy in range(254, 344, 6):
        rect(d, ax0, yy, ax1 - ax0, 1, hx('#1d1730'))
    rect(d, ax0, 250, ax1 - ax0, 3, hx('#241a3a'))
    # 蒸汽（巷口）
    def steam(od):
        for i in range(40):
            t = i / 39.0
            cx = ax0 + 28 + math.sin(t * 5) * 10
            cy = 330 - t * 120
            rr = int(3 + t * 12)
            a = int(30 * (1 - t) ** 1.4)
            if a > 1:
                od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(180, 200, 235, a))
    layer.overlay(steam)
    # 巷口上方的霓虹小灯
    glow_dot(layer, ax0 + 14, 244, 2, CYAN, '#ffffff')
    # ---- 远处地面的城市光（在建筑底部可见处） ----
    def cityglow(od):
        for yy in range(300, 344):
            t = (yy - 300) / 44.0
            od.line([(0, yy), (W, yy)], fill=(255, 80, 160, int(5 + 9 * t)))
    layer.overlay(cityglow)
    layer.finish(radius=9.0, gain=1.15, tight=2.2, tight_gain=0.62)
    print('  mid  :', W, H)
    return layer


# ----------------------------------------------------------------------------
# 4. 近景 bg_near
# ----------------------------------------------------------------------------
# ============================================================================
# 3b. 中景 —— 第二代楼体系统（更立体的立面 / 招牌 / 灯光 / 屋顶）
# ============================================================================
M2_TONES = ['#211636', '#1d1430', '#241a38', '#1b122c', '#261a36', '#1f1528',
            '#231830', '#1a1128', '#26192e', '#1e1632', '#18202e', '#1d2430',
            '#2a1b2e', '#221a2a', '#191326', '#201736']
M2_THEMES = [
    ('#e8b64a', '#8a5a1e', '#4a2e10'),   # 暖黄窗
    ('#a8dcea', '#3f7e90', '#1a3a46'),   # 冷青窗
    ('#dce6f5', '#7f8fb5', '#3a4560'),   # 白蓝窗
    ('#ff9ac8', '#a11856', '#4a1030'),   # 粉窗
    ('#ffb066', '#a14a1a', '#4a2010'),   # 橙窗
    ('#8fe8c8', '#2a7a6a', '#123a34'),   # 青绿窗
    ('#c9a3ff', '#5d3aa0', '#2a1648'),   # 紫窗
]


def blend(bg, fg, a):
    """把 fg 以 alpha a(0..1) 压到 bg 上的不透明近似色（避免 RGBA 透明洞）。"""
    return mix(rgb3(bg), rgb3(fg), a)


def m2_window(d, rng, x, y, w, h, lit, theme):
    """一扇像素窗：亮窗有多种生活细节，暗窗只有玻璃反光。"""
    rect(d, x - 1, y - 1, w + 2, h + 2, hx('#07040e'))
    if lit:
        cb, cm, cd = theme
        rect(d, x, y, w, h, hx(cm))
        rect(d, x, y, w, h - 3, hx(cb))
        rect(d, x, y, w, 1, hx(mix(rgb3(cb), (255, 255, 255), 0.45)))
        k = rng.random()
        if k < 0.20:      # 百叶 / 卷帘
            for yy in range(y + 2, y + h - 1, 2):
                rect(d, x + 1, yy, w - 2, 1, hx(cm))
        elif k < 0.32:    # 中梃 + 下半截暗
            rect(d, x + w // 2, y, 1, h, hx(cd))
            rect(d, x, y + h - 4, w, 3, hx(cd))
        elif k < 0.44:    # 人影
            rect(d, x + w // 2 - 1, y + h - 6, 3, 6, hx('#0f0a18'))
            rect(d, x + w // 2, y + h - 9, 2, 3, hx('#0f0a18'))
        elif k < 0.52:    # 窗台盆栽
            rect(d, x + 1, y + h - 3, 2, 2, hx('#2a6a4a'))
            rect(d, x + 3, y + h - 4, 1, 1, hx('#3f8a5a'))
        elif k < 0.62:    # 窗帘
            rect(d, x, y, 2, h, hx(cd))
            rect(d, x + w - 2, y, 2, h, hx(cd))
        # 底部窗框
        rect(d, x, y + h - 1, w, 1, hx(cd))
    else:
        rect(d, x, y, w, h, hx('#0c0819'))
        rect(d, x, y, w, 1, hx('#1b1430'))
        rect(d, x, y, 1, h, hx('#160f28'))
        rect(d, x + w - 1, y, 1, h, hx('#07040e'))
        if rng.random() < 0.2:
            rect(d, x + 1, y + 1, max(1, int(w * 0.55)), 1, hx('#22344a'))
    # 窗台 + 投影
    rect(d, x - 2, y + h, w + 4, 1, hx('#33264c'))
    rect(d, x - 1, y + h + 1, w + 2, 1, hx('#0a0614'))


def m2_facade(layer, rng, x, w, top, bottom=344, style='grid', tone=None, lit_prob=0.16,
              bay_w=None, win_w=None, win_h=None, floor_h=None, theme=None):
    """楼体立面：主体 + 材质 + 窗格。返回可复用的立面信息。"""
    d = layer.d
    tone = tone or rng.choice(M2_TONES)
    bay_w = bay_w or rng.choice([26, 28, 30, 32, 34])
    win_w = win_w or rng.choice([8, 9, 10])
    win_h = win_h or win_w + rng.choice([2, 3, 4])
    floor_h = floor_h or win_h + rng.choice([9, 11, 13])
    theme = theme or rng.choice(M2_THEMES)
    # --- 主体 ---
    rect(d, x, top, w, bottom - top, hx(tone))
    rect(d, x, top, 2, bottom - top, hx(shade(tone, 1.4)))
    rect(d, x + 2, top, 1, bottom - top, hx(shade(tone, 1.16)))
    rect(d, x + w - 5, top, 5, bottom - top, hx(shade(tone, 0.58)))
    rect(d, x + w - 1, top, 1, bottom - top, hx('#07040e'))
    # --- 材质：横向面板缝 / 色块 / 竖向雨渍 ---
    seam = rng.choice([6, 7, 8])
    for yy in range(top + 6, bottom, seam):
        rect(d, x + 3, yy, w - 8, 1, hx(shade(tone, 0.9)))
    for _ in range(max(1, w // 70)):
        pw = rng.randint(16, 46)
        ph = rng.randint(28, 86)
        pxx = x + rng.randint(3, max(4, w - pw - 3))
        pyy = top + rng.randint(4, max(6, bottom - top - ph - 4))
        rect(d, pxx, pyy, pw, ph, hx(shade(tone, rng.choice([1.07, 0.92, 0.96]))))
    for _ in range(max(1, w // 90)):
        gx = x + rng.randint(6, max(8, w - 10))
        gh = rng.randint(20, 60)
        gy = top + rng.randint(10, max(12, bottom - top - gh - 10))
        rect(d, gx, gy, 1, gh, hx(shade(tone, 0.86)))
    # --- 楼层线 ---
    floor_ys = []
    yy = top + rng.choice([14, 18, 22])
    while yy < bottom - 24:
        floor_ys.append(yy)
        yy += floor_h
    # --- 窗 ---
    if style == 'grid':
        bays = max(1, int((w - 12) // bay_w))
        start = x + (w - bays * bay_w) // 2
        for k in range(bays):
            bx = start + k * bay_w
            rect(d, bx, top + 2, 2, bottom - top - 6, hx(shade(tone, 1.2)))
            rect(d, bx + 2, top + 2, 1, bottom - top - 6, hx(shade(tone, 0.86)))
            wx = bx + (bay_w - win_w) // 2
            for fy in floor_ys:
                if fy + win_h > bottom - 14:
                    continue
                m2_window(d, rng, wx, fy, win_w, win_h, rng.random() < lit_prob, theme)
        for fy in floor_ys:
            rect(d, x + 2, fy - 3, w - 5, 1, hx(shade(tone, 1.42)))
            rect(d, x + 2, fy - 2, w - 5, 1, hx(shade(tone, 0.72)))
    elif style == 'strip':
        gh = max(7, win_h)
        for fy in floor_ys:
            rect(d, x + 6, fy - 1, w - 12, gh + 2, hx('#080512'))
            for wx in range(x + 7, x + w - 8, 8):
                seg = min(7, x + w - 8 - wx)
                if seg <= 2:
                    break
                if rng.random() < lit_prob:
                    cb, cm, cd = theme
                    rect(d, wx, fy, seg, gh, hx(cm))
                    rect(d, wx, fy, seg, gh - 2, hx(cb))
                    rect(d, wx, fy, seg, 1, hx(mix(rgb3(cb), (255, 255, 255), 0.4)))
                else:
                    rect(d, wx, fy, seg, gh, hx('#0c0819'))
                    rect(d, wx, fy, seg, 1, hx('#1a1230'))
            rect(d, x + 4, fy + gh, w - 8, 2, hx(shade(tone, 0.78)))
            rect(d, x + 4, fy + gh + 2, w - 8, 1, hx(shade(tone, 1.28)))
    elif style == 'balcony':
        bays = max(1, int((w - 12) // bay_w))
        start = x + (w - bays * bay_w) // 2
        bw = max(8, bay_w - 10)
        for fy in floor_ys:
            for k in range(bays):
                bx = start + k * bay_w + 5
                wy = fy
                if wy + win_h > bottom - 16:
                    continue
                m2_window(d, rng, bx, wy, bw, win_h, rng.random() < lit_prob, theme)
            # 阳台板
            rect(d, x + 2, fy + win_h + 2, w - 4, 3, hx(shade(tone, 1.36)))
            rect(d, x + 2, fy + win_h + 5, w - 4, 1, hx(shade(tone, 0.62)))
            rect(d, x + 2, fy + win_h + 6, w - 4, 1, hx('#0a0614'))
            # 栏杆
            for rx in range(x + 4, x + w - 4, 5):
                rect(d, rx, fy + win_h - 7, 1, 9, hx(shade(tone, 0.7)))
            rect(d, x + 2, fy + win_h - 7, w - 4, 1, hx(shade(tone, 1.18)))
    elif style == 'tower':
        for sx in range(x + 7, x + w - 10, 13):
            rect(d, sx - 2, top + 2, 2, bottom - top - 6, hx(shade(tone, 0.82)))
            for fy in floor_ys:
                if fy + win_h > bottom - 14:
                    continue
                lit = rng.random() < lit_prob * 1.5
                if lit:
                    cb, cm, cd = theme
                    rect(d, sx, fy, 9, win_h, hx(cm))
                    rect(d, sx, fy, 9, win_h - 2, hx(cb))
                    rect(d, sx, fy, 9, 1, hx(mix(rgb3(cb), (255, 255, 255), 0.4)))
                else:
                    rect(d, sx, fy, 9, win_h, hx('#0c0819'))
                    rect(d, sx, fy, 9, 1, hx('#1a1230'))
            rect(d, sx + 9, top + 2, 2, bottom - top - 6, hx(shade(tone, 1.3)))
    # --- 基座 ---
    ph = rng.choice([10, 12, 14])
    rect(d, x, bottom - ph, w, ph, hx(shade(tone, 0.66)))
    rect(d, x, bottom - ph, w, 1, hx(shade(tone, 1.08)))
    rect(d, x, bottom - ph, 2, ph, hx(shade(tone, 0.9)))
    rect(d, x, bottom - 2, w, 2, hx('#080510'))
    return dict(tone=tone, bay_w=bay_w, win_w=win_w, win_h=win_h, floor_h=floor_h,
                floor_ys=floor_ys, theme=theme)


def m2_ac(layer, rng, x, y, w=18, h=14):
    d = layer.d
    rect(d, x - 1, y - 1, w + 2, h + 2, hx('#0a0614'))
    rect(d, x, y, w, h, hx('#241b38'))
    rect(d, x, y, w, 2, hx('#3d2e58'))
    rect(d, x, y + h - 2, w, 2, hx('#110c1e'))
    cx, cy = x + w // 2, y + h // 2 + 1
    r = min(w, h) // 2 - 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=hx('#0c0817'))
    d.line([cx - r, cy, cx + r, cy], fill=hx('#0c0817'))
    d.line([cx, cy - r, cx, cy + r], fill=hx('#0c0817'))
    d.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=hx('#33264c'))
    # 支架与排水
    rect(d, x + 2, y + h + 1, w - 4, 1, hx('#0d0818'))
    rect(d, x + w - 5, y + h + 1, 1, rng.randint(10, 22), hx('#0a0614'))


def m2_poster(layer, rng, x, y, w=14, h=18):
    d = layer.d
    rect(d, x - 1, y - 1, w + 2, h + 2, hx('#0a0613'))
    bg = rng.choice(['#3a2450', '#4a1a3a', '#123a44', '#3d2a1a', '#2a2450', '#402a20'])
    rect(d, x, y, w, h, hx(bg))
    kind = rng.randrange(5)
    if kind == 0:
        rect(d, x + 2, y + 2, w - 4, 5, hx(rng.choice([CYAN, MAGENTA, YELLOW, ORANGE])))
        rect(d, x + 2, y + 9, w - 4, 2, hx('#0f0a1a'))
        rect(d, x + 3, y + 13, w - 7, 2, hx('#0f0a1a'))
    elif kind == 1:
        d.ellipse([x + 2, y + 2, x + w - 3, y + h // 2], fill=hx(rng.choice(['#d8455a', '#c9a13a', '#3df3ff'])))
        rect(d, x + 2, y + h // 2 + 2, w - 4, 2, hx('#0f0a1a'))
        rect(d, x + 3, y + h // 2 + 6, w - 6, 2, hx('#0f0a1a'))
    elif kind == 2:
        for i in range(4):
            rect(d, x + 1 + i * 3, y + 2, 2, h - 4, hx(rng.choice([CYAN, MAGENTA, YELLOW, PURPLE])))
    elif kind == 3:
        rect(d, x + 1, y + 1, w - 2, h - 2, hx('#1b1230'))
        rect(d, x + 3, y + 3, w - 6, 4, hx(YELLOW))
        rect(d, x + 3, y + 9, w - 6, 1, hx(STEEL_D))
        rect(d, x + 3, y + 11, w - 8, 1, hx(STEEL_D))
        rect(d, x + 3, y + 13, w - 6, 1, hx(STEEL_D))
    else:
        rect(d, x + 2, y + 2, w - 4, h - 6, hx('#0d1a26'))
        rect(d, x + 3, y + 4, w - 6, 2, hx(CYAN))
        rect(d, x + 3, y + 8, w - 9, 2, hx(MAGENTA))
    if rng.random() < 0.5:
        rect(d, x, y, 3, 2, hx('#c9b98a'))
    if rng.random() < 0.4:
        d.polygon([(x + w - 1, y + h - 4), (x + w - 1, y + h - 1), (x + w - 4, y + h - 1)],
                  fill=hx('#0e0a19'))


def m2_pipe_v(d, x, y0, y1, w=3, tone='#191129'):
    if y1 <= y0:
        return
    rect(d, x, y0, w, y1 - y0, hx(tone))
    rect(d, x, y0, 1, y1 - y0, hx(shade(tone, 1.6)))
    rect(d, x + w - 1, y0, 1, y1 - y0, hx(shade(tone, 0.5)))
    for y in range(y0 + 10, y1, 24):
        rect(d, x - 1, y, w + 2, 2, hx('#0d0818'))


def m2_lantern(layer, x, y, r=8, col='#ff3b5c', dark='#8a1a34'):
    d = layer.d
    rect(d, x - 1, y - r - 6, 2, 6, hx('#0a0614'))
    d.ellipse([x - r, y - r, x + r, y + r], fill=hx(col))
    d.ellipse([x - r, y - r, x + r, y + r], outline=hx('#0a0614'))
    for i in range(-1, 2):
        yy = y + i * max(2, r // 2)
        d.line([(x - r + 2, yy), (x + r - 2, yy)], fill=hx(dark))
    rect(d, x - 2, y - r - 2, 4, 2, hx('#0a0614'))
    rect(d, x - 2, y + r, 4, 2, hx('#0a0614'))
    layer.sd.ellipse([x - r, y - r, x + r, y + r], outline=hx(col, 150))
    layer.sd.ellipse([x - r + 2, y - r + 2, x + r - 2, y + r - 2], outline=hx(col, 90))


def m2_noren(layer, rng, x, y, w, h=28, col='#7a1838', mark=True):
    d = layer.d
    rect(d, x - 3, y - 3, w + 6, 3, hx('#0a0614'))
    panels = max(2, w // 18)
    pw = (w - (panels - 1) * 2) // panels
    for i in range(panels):
        px0 = x + i * (pw + 2)
        rect(d, px0, y, pw, h, hx(col))
        rect(d, px0, y, pw, 2, hx(shade(col, 0.62)))
        rect(d, px0 + 1, y + 2, 1, h - 4, hx(shade(col, 1.24)))
        rect(d, px0 + pw - 2, y + 2, 1, h - 4, hx(shade(col, 0.7)))
        rect(d, px0 + 1, y + h - 3, pw - 2, 2, hx(shade(col, 0.5)))
        if mark and pw > 12:
            rect(d, px0 + pw // 2 - 2, y + 7, 5, 1, hx('#e8dcc0', 220))
            rect(d, px0 + pw // 2 - 2, y + 11, 5, 1, hx('#e8dcc0', 220))


def m2_awning(layer, rng, x, y, w, col1='#4a1a34', col2='#2a1224', trim=None):
    d = layer.d
    rect(d, x - 2, y - 3, w + 4, 3, hx('#0a0614'))
    rect(d, x, y, w, 3, hx('#2a1628'))
    rect(d, x, y + 3, w, 10, hx(col1))
    for i in range(0, w, 16):
        rect(d, x + i, y + 3, 8, 10, hx(col2))
    rect(d, x, y + 13, w, 2, hx('#0a0614'))
    # 波浪边
    for i in range(0, w - 2, 10):
        d.arc([x + i, y + 10, x + i + 10, y + 20], 0, 180, fill=hx(col1))
    # 支撑杆 + 霓虹下缘
    rect(d, x + 3, y + 15, 1, 9, hx('#0a0614'))
    rect(d, x + w - 4, y + 15, 1, 9, hx('#0a0614'))
    if trim:
        layer.sd.line([(x + 1, y + 15), (x + w - 2, y + 15)], fill=hx(trim, 190), width=1)


def m2_shutter(layer, rng, x, y, w, h, gtag=True):
    d = layer.d
    rect(d, x - 2, y - 2, w + 4, h + 4, hx('#07040e'))
    rect(d, x, y, w, h, hx('#1a1329'))
    for yy in range(y + 2, y + h - 1, 3):
        rect(d, x + 1, yy, w - 2, 1, hx('#241b38'))
        rect(d, x + 1, yy + 1, w - 2, 1, hx('#120d1f'))
    rect(d, x, y, w, 1, hx('#31254b'))
    rect(d, x, y + h - 2, w, 2, hx('#0d0917'))
    rect(d, x, y, 2, h, hx('#0d0917'))
    rect(d, x + w - 2, y, 2, h, hx('#0d0917'))
    rect(d, x, y, w, 8, hx('#151022'))
    if gtag:
        def graf(od):
            pal = [MAGENTA, CYAN, YELLOW, PURPLE, ORANGE]
            for _ in range(rng.randint(2, 3)):
                col = rng.choice(pal)
                pts = []
                xx = x + rng.randint(3, max(5, w - 34))
                yy = y + rng.randint(8, max(10, h - 14))
                for _k in range(rng.randint(3, 6)):
                    pts.append((xx + rng.randint(0, 26), yy + rng.randint(-8, 8)))
                    xx += rng.randint(3, 9)
                od.line(pts, fill=hx(col, rng.randint(70, 130)), width=rng.choice([1, 1, 2]))
            for _ in range(rng.randint(2, 4)):
                gx = x + rng.randint(3, max(5, w - 5))
                gy = y + rng.randint(8, max(10, h - 10))
                od.line([(gx, gy), (gx, gy + rng.randint(3, 12))], fill=hx('#a11856', 80), width=1)
        layer.overlay(graf)


def m2_board_h(layer, x, y, w, h, text, px_h, board='#120b1d', border=CYAN, txt=CYAN,
               core='#eaffff', border_w=2, latin=False, spill=0.5, mount='top', spill_color=None):
    d, sd = layer.d, layer.sd
    # 固定支架
    if mount == 'top':
        rect(d, x + 6, y - 4, 3, 4, hx('#0a0616'))
        rect(d, x + w - 9, y - 4, 3, 4, hx('#0a0616'))
    elif mount == 'wall':
        rect(d, x - 4, y + h // 2, 4, 2, hx('#0a0616'))
        rect(d, x + w, y + h // 2, 4, 2, hx('#0a0616'))
    rect(d, x - 3, y - 3, w + 6, h + 6, hx('#08040f'))
    rect(d, x, y, w, h, hx(board))
    rect(d, x, y, w, 1, hx('#2c1f42'))
    rect(d, x, y + h - 1, w, 1, hx('#05030c'))
    d.rectangle([x + 2, y + 2, x + w - 3, y + h - 3], outline=hx('#241534'))
    sd.rectangle([x, y, x + w - 1, y + h - 1], outline=hx(border), width=border_w)
    if text:
        m = pixel_mask(text, max(1, px_h // 7)) if latin else text_mask(text, px_h)
        tx = x + (w - m.width) // 2
        ty = y + (h - m.height) // 2
        stamp(layer.signs, m, tx, ty, txt)
        stamp(layer.signs, m.filter(ImageFilter.MinFilter(3)), tx, ty, core, 210)
    if spill:
        layer.spills.append((x, y + h, w, spill_color or border, spill))
    # 四角螺丝
    for (cx, cy) in [(x + 1, y + 1), (x + w - 2, y + 1), (x + 1, y + h - 2), (x + w - 2, y + h - 2)]:
        rect(d, cx, cy, 1, 1, hx('#4a4368'))
    return m


def m2_board_v(layer, x, y, w, h, text, px_h, board='#120b1d', border=MAGENTA, txt=MAGENTA,
               core='#ffe8f4', border_w=2, latin=False, spill=0.5, spill_color=None):
    d, sd = layer.d, layer.sd
    rect(d, x + w // 2 - 1, y - 5, 2, 5, hx('#0a0616'))
    rect(d, x - 3, y - 3, w + 6, h + 6, hx('#08040f'))
    rect(d, x, y, w, h, hx(board))
    rect(d, x, y, 1, h, hx('#2c1f42'))
    rect(d, x + w - 1, y, 1, h, hx('#05030c'))
    d.rectangle([x + 2, y + 2, x + w - 3, y + h - 3], outline=hx('#241534'))
    sd.rectangle([x, y, x + w - 1, y + h - 1], outline=hx(border), width=border_w)
    if text:
        m = text_mask_vertical_latin(text, max(1, px_h // 7)) if latin else text_mask(text, px_h, vertical=True)
        tx = x + (w - m.width) // 2
        ty = y + (h - m.height) // 2
        stamp(layer.signs, m, tx, ty, txt)
        stamp(layer.signs, m.filter(ImageFilter.MinFilter(3)), tx, ty, core, 210)
    if spill:
        layer.spills.append((x - w, y + h, w * 3, spill_color or border, spill * 0.7))
    for (cx, cy) in [(x + 1, y + 1), (x + w - 2, y + 1), (x + 1, y + h - 2), (x + w - 2, y + h - 2)]:
        rect(d, cx, cy, 1, 1, hx('#4a4368'))


def m2_shop_window(layer, rng, x, y, w, h, glow='#ffcf8a', kind='ramen'):
    """一层店面的发光橱窗：内部暖光 + 剪影，外面有深色窗框。"""
    d = layer.d
    rect(d, x - 3, y - 3, w + 6, h + 6, hx('#07040e'))
    rect(d, x, y, w, h, hx(shade(glow, 0.28)))
    # 内部光（上亮下暗）
    bands = [(0.0, 1.0), (0.35, 0.85), (0.7, 0.62), (0.95, 0.42)]
    for i in range(len(bands) - 1):
        t0, f0 = bands[i]
        t1, f1 = bands[i + 1]
        yy0 = y + int(h * t0)
        yy1 = y + int(h * t1)
        rect(d, x, yy0, w, max(1, yy1 - yy0), hx(shade(glow, f0)))
    # 货架 / 吧台
    for i in range(rng.randint(1, 2)):
        ry = y + rng.randint(int(h * 0.35), int(h * 0.7))
        rect(d, x + 2, ry, w - 4, 2, hx(shade(glow, 0.4)))
        rect(d, x + 2, ry + 2, w - 4, 1, hx(shade(glow, 0.24)))
    # 剪影
    if kind == 'ramen':
        # 吧台 + 客人剪影
        rect(d, x + 2, y + h - int(h * 0.32), w - 4, 2, hx(shade(glow, 0.3)))
        for i in range(rng.randint(1, 3)):
            cx = x + rng.randint(5, max(7, w - 12))
            ch = rng.randint(int(h * 0.3), int(h * 0.55))
            rect(d, cx, y + h - ch, 7, ch, hx('#1a1020'))
            d.ellipse([cx, y + h - ch - 6, cx + 7, y + h - ch + 1], fill=hx('#1a1020'))
        # 蒸汽
        for i in range(4):
            gx = x + rng.randint(4, max(6, w - 6))
            for k in range(4):
                rect(d, gx + (k % 2), y - 4 - k * 3, 1, 2, hx(blend('#1a1020', glow, 0.5 - k * 0.1)))
    elif kind == 'arcade':
        for i in range(3):
            mx = x + 6 + i * ((w - 14) // 3)
            rect(d, mx, y + h - 30, 16, 28, hx('#221836'))
            rect(d, mx + 2, y + h - 27, 12, 9, hx(rng.choice([CYAN, MAGENTA, YELLOW, PURPLE])))
            rect(d, mx + 2, y + h - 16, 12, 1, hx('#0d0919'))
            rect(d, mx + 2, y + h - 22, 3, 3, hx(ORANGE))
            rect(d, mx + 7, y + h - 22, 3, 3, hx(ORANGE))
    elif kind == 'bar':
        for i in range(rng.randint(2, 4)):
            bx = x + 4 + i * 7
            rect(d, bx, y + 4, 3, 8, hx(rng.choice(['#8a5a20', '#3a7a6a', '#8a2a50'])))
            rect(d, bx + 1, y + 2, 1, 2, hx('#8a5a20'))
        rect(d, x + 2, y + h - 12, w - 4, 2, hx(shade(glow, 0.35)))
        rect(d, x + 8, y + h - 26, 5, 26, hx('#1a1020'))
        d.ellipse([x + 8, y + h - 34, x + 13, y + h - 26], fill=hx('#1a1020'))
    elif kind == 'ktv':
        for i in range(rng.randint(2, 3)):
            cx = x + rng.randint(3, max(5, w - 14))
            cy = y + rng.randint(3, max(5, h - 12))
            rect(d, cx, cy, 9, 7, hx(rng.choice([CYAN, MAGENTA, YELLOW])))
            rect(d, cx, cy, 9, 2, hx('#ffffff', 120))
    # 窗框 / 中梃
    rect(d, x, y, w, 1, hx('#0d0818'))
    rect(d, x, y + h - 1, w, 1, hx('#07040e'))
    rect(d, x, y, 1, h, hx('#241a38'))
    rect(d, x + w - 1, y, 1, h, hx('#07040e'))
    for i in range(1, max(2, w // 34)):
        rect(d, x + i * (w // max(2, w // 34)), y, 1, h, hx('#0d0818'))
    # 霓虹上沿
    layer.sd.line([(x + 1, y - 2), (x + w - 2, y - 2)], fill=hx(glow, 150), width=1)
    layer.spills.append((x, y + h, w, glow, 0.30))


def m2_door(layer, rng, x, y, w, h, light='#ffd9a0', col='#1c1428', open_=True):
    d = layer.d
    rect(d, x - 3, y - 3, w + 6, h + 5, hx('#07040e'))
    rect(d, x, y, w, h, hx(col))
    if open_:
        rect(d, x + 2, y + 3, w - 4, h - 4, hx(shade(light, 0.55)))
        rect(d, x + 2, y + 3, w - 4, 2, hx(light))
        # 内部剪影
        rect(d, x + w - 5, y + 8, 3, h - 10, hx('#1a1020'))
        d.ellipse([x + w - 6, y + 2, x + w - 1, y + 8], fill=hx('#1a1020'))
    rect(d, x, y, w, 2, hx('#2c2044'))
    rect(d, x + w - 2, y, 2, h, hx('#2c2044'))
    rect(d, x - 1, y + h, w + 2, 2, hx('#0d0918'))


def m2_stairs(d, x, y, w, steps=4, col='#1a1228'):
    for i in range(steps):
        rect(d, x - i * 2, y + i * 3, w + i * 4, 3, hx(shade(col, 1 + i * 0.06)))
        rect(d, x - i * 2, y + i * 3, w + i * 4, 1, hx(shade(col, 1.4)))
    rect(d, x - steps * 2, y + steps * 3, w + steps * 4, 2, hx('#0a0614'))


def m2_roof(layer, rng, x, w, top, kind=None):
    """屋顶：女儿墙 + 设备剪影（水塔 / 天线 / 楼梯间 / 空调 / 栏杆 / 霓虹小招牌）。"""
    d = layer.d
    # 女儿墙
    rect(d, x - 2, top - 5, w + 4, 5, hx('#1c1332'))
    rect(d, x - 2, top - 6, w + 4, 1, hx('#3d2c5c'))
    rect(d, x - 2, top - 6, 2, 6, hx('#2c2048'))
    rect(d, x + w, top - 6, 2, 6, hx('#0a0616'))
    # 屋顶面薄边
    rect(d, x, top - 8, w, 2, hx('#0d0919'))
    kind = kind or rng.choice(['tank', 'antenna', 'ac', 'stair', 'rail', 'vent', 'neon'])
    if kind == 'tank':
        tx = x + rng.randint(12, max(14, w - 44))
        ty = top - 34
        rect(d, tx, ty, 26, 18, hx('#1a1330'))
        rect(d, tx, ty, 26, 2, hx('#2e2148'))
        rect(d, tx, ty, 2, 18, hx('#2a1e44'))
        d.ellipse([tx, ty - 4, tx + 26, ty + 4], fill=hx('#22183a'))
        d.ellipse([tx, ty - 4, tx + 26, ty + 4], outline=hx('#3a2c58'))
        rect(d, tx + 4, ty + 18, 3, 8, hx('#0c0817'))
        rect(d, tx + 19, ty + 18, 3, 8, hx('#0c0817'))
        for k in range(3):
            rect(d, tx + 2, ty + 4 + k * 5, 22, 1, hx('#2a1f44'))
        rect(d, tx + 25, ty + 8, 1, 8, hx('#0a0614'))
    elif kind == 'antenna':
        tx = x + rng.randint(10, max(12, w - 24))
        hh = rng.randint(22, 48)
        rect(d, tx, top - 8 - hh, 2, hh, hx('#0b0717'))
        rect(d, tx, top - 8 - hh, 1, hh, hx('#241a3c'))
        for k in range(3):
            by = top - 14 - k * (hh // 3)
            rect(d, tx - 4, by, 10, 1, hx('#0b0717'))
        d.ellipse([tx - 8, top - 22, tx - 1, top - 15], outline=hx('#1b1232'))
        glow_dot(layer, tx + 1, top - 9 - hh, 1, RED, '#ffd9e0')
    elif kind == 'ac':
        m2_ac(layer, rng, x + rng.randint(8, max(10, w - 44)), top - 24)
        m2_ac(layer, rng, x + rng.randint(30, max(32, w - 24)), top - 20)
        rect(d, x + 10, top - 6, 26, 2, hx('#0e0a1a'))
    elif kind == 'stair':
        bx = x + rng.randint(10, max(12, w - 52))
        rect(d, bx, top - 24, 34, 18, hx('#1a1230'))
        rect(d, bx, top - 24, 34, 2, hx('#33254e'))
        rect(d, bx + 3, top - 18, 10, 12, hx('#0c0817'))
        rect(d, bx + 5, top - 16, 6, 9, hx('#3a2a20'))
        glow_dot(layer, bx + 8, top - 12, 1, '#ffd23f', '#fff4cc')
        rect(d, bx + 22, top - 20, 8, 8, hx('#120d20'))
    elif kind == 'rail':
        for i in range(0, w, 9):
            rect(d, x + i, top - 16, 1, 10, hx('#0d0919'))
        rect(d, x, top - 17, w, 1, hx('#0d0919'))
        rect(d, x, top - 9, w, 1, hx('#0d0919'))
    elif kind == 'vent':
        tx = x + rng.randint(10, max(12, w - 30))
        rect(d, tx, top - 26, 5, 20, hx('#1b1430'))
        rect(d, tx - 2, top - 28, 9, 3, hx('#2a1e44'))
        rect(d, tx - 3, top - 6, 12, 2, hx('#0c0817'))
        glow_dot(layer, tx + 2, top - 30, 1, CYAN, '#ffffff')
    elif kind == 'neon':
        bw, bh = 42, 18
        bx = x + rng.randint(6, max(8, w - bw - 6))
        by = top - 40
        rect(d, bx - 2, by - 2, bw + 4, bh + 4, hx('#07040e'))
        rect(d, bx, by, bw, bh, hx('#120a18'))
        for sx in (bx + 4, bx + bw - 6):
            rect(d, sx, by + bh, 2, 10, hx('#0a0616'))
        ch = rng.choice(['酒', '夜', '電', '薬', '龍', '氷'])
        col = rng.choice([CYAN, MAGENTA, YELLOW, ORANGE])
        m = text_mask(ch, 12)
        stamp(layer.signs, m, bx + (bw - m.width) // 2, by + (bh - m.height) // 2, hx(col))
        layer.sd.rectangle([bx, by, bx + bw - 1, by + bh - 1], outline=hx(col, 200))
        layer.spills.append((bx, by + bh, bw, col, 0.25))


# --- 各类楼体 --------------------------------------------------------------
def m2_bld_apartment(layer, rng, x, w, top):
    info = m2_facade(layer, rng, x, w, top, style='grid', lit_prob=rng.uniform(0.10, 0.2),
                     tone=rng.choice(['#211636', '#1d1430', '#231830', '#26192e']))
    m2_roof(layer, rng, x, w, top)
    # 立面的空调 / 海报 / 立管
    for _ in range(rng.randint(2, 4)):
        ax = x + rng.randint(8, max(10, w - 30))
        ay = rng.randint(top + 26, max(top + 30, 268))
        m2_ac(layer, rng, ax, ay)
    if rng.random() < 0.8:
        m2_poster(layer, rng, x + rng.randint(6, max(8, w - 22)), rng.randint(186, 260))
    m2_pipe_v(layer.d, x + w - 9, top + 10, 330)
    if rng.random() < 0.7:
        m2_pipe_v(layer.d, x + 7, top + 40, 330, 2)
    # 底层：楼梯入口 + 小门 + 灯
    ex = x + rng.randint(12, max(14, w - 48))
    m2_door(layer, rng, ex, 300, 22, 34, '#ffd9a0')
    rect(layer.d, ex - 4, 316, 30, 2, hx('#0d0918'))
    glow_dot(layer, ex + 11, 294, 2, '#ffd23f', '#fff4cc')
    layer.spills.append((ex - 6, 300, 34, '#ffd23f', 0.2))


def m2_bld_ramen(layer, rng, x, w, top):
    """拉面店：两层小楼 + 黄招牌 + 红灯笼 + 门帘 + 暖光橱窗。"""
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='grid', lit_prob=0.42,
                     tone='#2a172a', bay_w=34, win_w=12, win_h=14, floor_h=32,
                     theme=('#ffcf8a', '#8a5a24', '#4a2e12'))
    # 二层窗（暖光 + 窗框）
    for fy in info['floor_ys']:
        rect(d, x + 10, fy - 4, w - 20, 1, hx('#3a2234'))
    # 屋顶：招牌架 + 水塔
    m2_roof(layer, rng, x, w, top, kind='tank' if rng.random() < 0.5 else 'ac')
    # 主招牌（大，横向，黄底黑字式霓虹）
    sx, sy, sw, sh = x + 14, 214, w - 28, 46
    rect(d, sx - 4, sy - 4, sw + 8, sh + 8, hx('#0a0614'))
    rect(d, sx, sy, sw, sh, hx('#1c0f16'))
    rect(d, sx, sy, sw, 2, hx('#3a2410'))
    rect(d, sx, sy + sh - 2, sw, 2, hx('#0c0808'))
    # 黄霓虹双线边框
    layer.sd.rectangle([sx, sy, sx + sw - 1, sy + sh - 1], outline=hx('#ffd23f'), width=2)
    layer.sd.rectangle([sx + 3, sy + 3, sx + sw - 4, sy + sh - 4], outline=hx('#ff8a2a', 150))
    # 圆灯笼图标
    lx, ly = sx + 30, sy + sh // 2
    d.ellipse([lx - 12, ly - 12, lx + 12, ly + 12], fill=hx('#c8302a'))
    d.ellipse([lx - 12, ly - 12, lx + 12, ly + 12], outline=hx('#0a0614'))
    for k in range(-1, 2):
        line(d, [(lx - 10, ly + k * 4), (lx + 10, ly + k * 4)], hx('#8a1a18'))
    rect(d, lx - 3, ly - 16, 6, 3, hx('#0a0614'))
    layer.sd.ellipse([lx - 12, ly - 12, lx + 12, ly + 12], outline=hx('#ff3b5c', 190))
    # 「拉面」大字
    m = text_mask('拉面', 30)
    tx = lx + 22 + (sw - 56 - m.width) // 2
    ty = sy + (sh - m.height) // 2
    stamp(layer.signs, m, tx, ty, hx('#ffd23f'))
    stamp(layer.signs, m.filter(ImageFilter.MinFilter(3)), tx, ty, hx('#fff6d0'), 220)
    # 小字 RAMEN
    m2 = pixel_mask('RAMEN', 1)
    stamp(layer.signs, m2, tx + (m.width - m2.width) // 2, ty + m.height + 3, hx('#ff8a2a'), 190)
    layer.spills.append((sx, sy + sh, sw, '#ffd23f', 0.5))
    # 招牌小灯
    for i in range(3):
        glow_dot(layer, sx + sw - 14 - i * 18, sy - 3, 1, '#ffd23f', '#ffffff')
    # 灯笼
    m2_lantern(layer, x + 22, 276, 9, '#ff3b5c', '#8a1a34')
    m2_lantern(layer, x + w - 23, 276, 9, '#ff3b5c', '#8a1a34')
    # 雨棚
    m2_awning(layer, rng, x + 26, 272, w - 52, '#4a1a2a', '#2a0f1a', trim='#ff3b5c')
    # 门帘
    m2_noren(layer, rng, x + 40, 290, w - 80, 24, '#8a1a3a')
    # 发光橱窗（吧台 + 客人）
    m2_shop_window(layer, rng, x + 20, 314 - 34, 46, 34, '#ffcf8a', kind='ramen')
    # 右半：门
    m2_door(layer, rng, x + w - 60, 300, 26, 34, '#ffcf8a')
    # 竖排小招牌「面」
    m2_board_v(layer, x + w - 26, 226, 16, 46, '面', 13, board='#1a0c14',
               border='#ff8a2a', txt='#ffd23f', core='#fff3c8', border_w=1, spill=0.2)
    # 侧墙管道 + 小花盆
    m2_pipe_v(d, x + 8, top + 10, 214, 2)
    m2_poster(layer, rng, x + 6, 246, 12, 16)


def m2_bld_izakaya(layer, rng, x, w, top):
    """居酒屋：高大窄楼 + 竖招牌 + 灯笼串 + 木格栅暖光。"""
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='grid', lit_prob=0.22,
                     tone='#1f1428', bay_w=30, win_w=9, win_h=11,
                     theme=('#ffb066', '#a14a1a', '#4a2010'))
    m2_roof(layer, rng, x, w, top, kind=rng.choice(['rail', 'tank', 'antenna']))
    # 竖向大招牌「居酒屋」
    m2_board_v(layer, x + w - 46, 118, 34, 150, '居酒屋', 24,
               board='#180b16', border=MAGENTA, txt=MAGENTA, core='#ffe0ef', border_w=2, spill=0.5)
    # 灯笼串
    rect(d, x + 12, 240, w - 30, 1, hx('#0a0614'))
    for i in range(4):
        lx = x + 20 + i * 22
        rect(d, lx, 241, 1, 7, hx('#0a0614'))
        m2_lantern(layer, lx, 258, 8, '#ff8a2a', '#8a3a1a')
    # 门头小横牌
    m2_board_h(layer, x + 14, 202, w - 70, 24, 'IZAKAYA', 14, board='#160a12',
               border='#ff8a2a', txt='#ffd23f', core='#fff3c8', border_w=1, latin=True, spill=0.25)
    # 木格栅（暖光透出）
    gx, gy, gw, gh = x + 14, 274, w - 76, 54
    rect(d, gx, gy, gw, gh, hx('#221012'))
    rect(d, gx, gy, gw, gh, hx('#2e1a16'))
    for xx in range(gx + 2, gx + gw - 2, 5):
        rect(d, xx, gy + 1, 3, gh - 2, hx('#4a2a1a'))
        rect(d, xx, gy + 1, 1, gh - 2, hx('#6a3a20'))
    # 门帘 + 门
    m2_noren(layer, rng, gx + 8, gy - 2, gw - 16, 20, '#1a2444')
    m2_shop_window(layer, rng, gx, gy, gw, gh, '#ffb066', kind='bar')
    m2_door(layer, rng, x + w - 58, 300, 24, 34, '#ffb066')
    layer.spills.append((gx - 10, gy + gh, gw + 20, '#ff8a2a', 0.35))
    # 墙面菜单木牌
    for i in range(2):
        mx = x + 12 + i * 18
        rect(d, mx, 250 + i * 4, 14, 18, hx('#2a1c14'))
        rect(d, mx, 250 + i * 4, 14, 1, hx('#4a3420'))
        rect(d, mx + 2, 254 + i * 4, 10, 1, hx('#c9a13a'))
        rect(d, mx + 2, 257 + i * 4, 8, 1, hx('#c9a13a'))
        rect(d, mx + 2, 260 + i * 4, 10, 1, hx('#8a6a20'))
    m2_pipe_v(d, x + w - 8, top + 10, 300, 2)


def m2_bld_shutter(layer, rng, x, w, top, gtag=True):
    info = m2_facade(layer, rng, x, w, top, style='grid', lit_prob=0.1,
                     tone=rng.choice(['#1d112e', '#21142f', '#191028']))
    m2_roof(layer, rng, x, w, top, kind=rng.choice(['ac', 'rail', 'vent']))
    # 上层小窗 / 海报
    m2_poster(layer, rng, x + rng.randint(4, max(6, w - 20)), rng.randint(190, 236), 14, 18)
    # 卷帘门
    sh_y = 252
    m2_shutter(layer, rng, x + 10, sh_y, w - 20, 78, gtag)
    # 卷帘门上沿的霓虹小招牌
    if rng.random() < 0.7:
        m2_board_h(layer, x + 20, 218, w - 40, 24, 'OPEN', 14, board='#120a16',
                   border=CYAN_D, txt=CYAN, core='#ddffff', border_w=1, latin=True, spill=0.2)
    # 电表箱 / 小广告
    rect(layer.d, x + w - 20, 258, 12, 16, hx('#1f1730'))
    rect(layer.d, x + w - 19, 260, 10, 6, hx('#0d0919'))
    rect(layer.d, x + w - 19, 268, 10, 4, hx('#0d0919'))
    rect(layer.d, x + 4, 292, 10, 26, hx('#1a1228'))
    layer.sd.line([(x + 4, 292), (x + 14, 292)], fill=hx(MAGENTA, 110))
    m2_pipe_v(layer.d, x + w - 6, 200, 330, 3)
    # 竖排霓虹「薬」招牌（平衡画面右侧）
    m2_board_v(layer, x + w - 30, 172, 20, 74, '薬', 18, board='#0d1a16',
               border=YELLOW, txt=YELLOW, core='#fff8d0', border_w=2, spill=0.45)
    # 卷帘门上方的霓虹灯管
    layer.sd.line([(x + 12, 246), (x + w - 12, 246)], fill=hx(MAGENTA, 180), width=1)
    for k in range(4):
        glow_dot(layer, x + 22 + k * (w - 44) // 3, 243, 1, MAGENTA, '#ffe0ef')


def m2_bld_service(layer, rng, x, w, top):
    """低矮的杂物/设备房：屋顶设备剪影 + 管线 + 铁网门，让天际线喘口气。"""
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='grid', lit_prob=0.12, tone='#1b1530',
                     bay_w=30, win_w=9, win_h=9, floor_h=20,
                     theme=('#c9a13a', '#7a5a20', '#3a2a10'))
    # 屋顶一串设备剪影（低楼，天空可见）
    m2_roof(layer, rng, x, w, top, kind='tank')
    m2_roof(layer, rng, x + 24, w - 48, top + 4, kind='vent')
    # 屋顶天线
    ax = x + 12
    rect(d, ax, top - 44, 2, 36, hx('#0a0616'))
    rect(d, ax - 6, top - 34, 14, 1, hx('#0a0616'))
    rect(d, ax - 4, top - 26, 10, 1, hx('#0a0616'))
    glow_dot(layer, ax + 1, top - 45, 1, RED, '#ffd9e0')
    # 横向大通风管
    rect(d, x + 6, 196, w - 12, 16, hx('#241c38'))
    rect(d, x + 6, 196, w - 12, 2, hx('#3a2f52'))
    rect(d, x + 6, 210, w - 12, 2, hx('#0d0a18'))
    for xx in range(x + 10, x + w - 12, 22):
        rect(d, xx, 198, 2, 14, hx('#0d0a18'))
    # 侧面排风罩
    rect(d, x + 18, 232, 30, 22, hx('#0c0818'))
    for i in range(4):
        rect(d, x + 20 + i * 7, 234, 4, 18, hx('#2a2140'))
    # 立面管道
    m2_pipe_v(d, x + 8, 152, 330, 4)
    m2_pipe_v(d, x + w - 16, 176, 330, 3)
    m2_pipe_v(d, x + w // 2 + 20, 216, 330, 2)
    # 消防梯（斜向上，部分出画）
    fx = x + w - 52
    for i in range(5):
        yy = 240 + i * 22
        rect(d, fx - i * 3, yy, 30, 2, hx('#0d0919'))
        rect(d, fx - i * 3, yy, 1, 22, hx('#0d0919'))
        rect(d, fx - i * 3 + 29, yy, 1, 22, hx('#0d0919'))
    # 涂鸦 / 广告
    m2_poster(layer, rng, x + 8, 258, 13, 17)
    m2_poster(layer, rng, x + 24, 262, 13, 17)
    # 铁网门 + 暖光门洞
    gx = x + 56
    rect(d, gx - 2, 300, 40, 44, hx('#0a0616'))
    for xx in range(gx, gx + 38, 4):
        rect(d, xx, 300, 1, 42, hx('#241c3a'))
    for yy in range(302, 342, 6):
        rect(d, gx, yy, 38, 1, hx('#241c3a'))
    rect(d, gx, 298, 38, 2, hx('#33284a'))
    rect(d, gx + 24, 312, 10, 30, hx('#3a2a1e'))
    glow_dot(layer, gx + 29, 314, 2, '#ffd23f', '#fff4cc')
    # 空调外机
    m2_ac(layer, rng, x + w - 40, 260)
    # 蒸汽
    def steam(od):
        for i in range(20):
            yy = 250 - i * 3
            rr = 1 + i // 6
            od.ellipse([x + 33 - rr, yy - rr, x + 33 + rr, yy + rr],
                       fill=(200, 220, 255, max(0, 20 - i)))
    layer.overlay(steam)
    # 屋顶后面的远景霓虹（借用 signs 层强化天际线）
    m2_roof(layer, rng, x + w - 60, 46, top + 2, kind='neon')
    # 小霓虹箭头
    layer.sd.line([(x + w // 2 + 2, 224), (x + w // 2 + 20, 224)], fill=hx(CYAN), width=2)
    layer.sd.polygon([(x + w // 2 + 18, 218), (x + w // 2 + 27, 224), (x + w // 2 + 18, 230)],
                     fill=hx(CYAN))


def m2_bld_arcade(layer, rng, x, w, top):
    """街机厅：青霓虹大招牌 + 明亮橱窗 + 门口光斑。"""
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='grid', lit_prob=0.14,
                     tone='#17202e', bay_w=32, win_w=10, win_h=12,
                     theme=('#a8dcea', '#3f7e90', '#1a3a46'))
    m2_roof(layer, rng, x, w, top, kind=rng.choice(['neon', 'antenna', 'ac']))
    # 大招牌
    m2_board_h(layer, x + 12, 148, w - 24, 48, '电玩', 30, board='#0c1a26',
               border=CYAN, txt=CYAN, core='#e8ffff', border_w=2, spill=0.55)
    # 竖排 GAME
    m2_board_v(layer, x + w - 28, 208, 18, 82, 'GAME', 12, board='#120a1a',
               border=MAGENTA, txt=MAGENTA, core='#ffd9ec', border_w=1, latin=True, spill=0.3)
    # 明亮橱窗（街机厅）
    m2_shop_window(layer, rng, x + 14, 210, w - 58, 112, '#4fb0c8', kind='arcade')
    # 门口
    m2_door(layer, rng, x + w - 38, 288, 24, 46, '#4fb0c8')
    # 外墙霓虹灯管
    layer.sd.line([(x + 4, 200), (x + 4, 326)], fill=hx(CYAN_D), width=1)
    # 屋顶招牌「24H」
    m2_board_h(layer, x + w - 62, 84, 46, 18, '24H', 12, board='#0c1420',
               border=ORANGE, txt=ORANGE, core='#fff0d8', border_w=1, latin=True, spill=0.0)
    m2_poster(layer, rng, x + 6, 254, 13, 17)


def m2_bld_ktv(layer, rng, x, w, top):
    """KTV：高塔玻璃幕墙 + 品红霓虹。"""
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='tower', lit_prob=0.16,
                     tone='#1e1130', win_w=9, win_h=11, floor_h=20,
                     theme=('#ff9ac8', '#a11856', '#4a1030'))
    m2_roof(layer, rng, x, w, top, kind=rng.choice(['antenna', 'neon']))
    # 竖招牌 KTV
    m2_board_v(layer, x + 10, 128, 26, 84, 'KTV', 13, board='#1a0a1e',
               border=MAGENTA, txt=MAGENTA, core='#ffe0f0', border_w=2, latin=True, spill=0.55)
    # 门头横招牌
    m2_board_h(layer, x + 42, 214, w - 54, 26, 'KTV', 15, board='#120a16',
               border=CYAN, txt=CYAN, core='#e6ffff', border_w=1, latin=True, spill=0.25)
    # 品红霓虹竖管
    layer.sd.line([(x + w - 8, 170), (x + w - 8, 330)], fill=hx(MAGENTA, 190), width=2)
    for k in range(6):
        layer.sd.line([(x + w - 10, 180 + k * 24), (x + w - 6, 180 + k * 24)],
                      fill=hx('#ffffff', 160))
    # 底层玻璃门 + 粉光
    m2_shop_window(layer, rng, x + 12, 296, w - 30, 34, '#c86a94', kind='ktv')
    m2_door(layer, rng, x + w - 34, 300, 20, 34, '#c86a94')
    m2_poster(layer, rng, x + 4, 250, 12, 16)


def m2_bld_bar(layer, rng, x, w, top):
    """小酒吧：雨棚 + BAR 霓虹 + 暖光吧台。"""
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='grid', lit_prob=0.2,
                     tone='#241a2c', bay_w=30, win_w=9, win_h=11,
                     theme=('#ffb066', '#a14a1a', '#4a2010'))
    m2_roof(layer, rng, x, w, top, kind=rng.choice(['rail', 'tank', 'ac']))
    # BAR 霓虹
    m2_board_h(layer, x + 20, 188, w - 40, 32, 'BAR', 16, board='#120a18',
               border=CYAN, txt=CYAN, core='#e8ffff', border_w=2, latin=True, spill=0.4)
    # 鸡尾酒霓虹图标
    gx, gy = x + w - 42, 244
    layer.sd.polygon([(gx - 10, gy - 10), (gx + 10, gy - 10), (gx, gy + 4)], outline=hx(MAGENTA))
    layer.sd.line([(gx, gy + 4), (gx, gy + 12)], fill=hx(MAGENTA), width=2)
    layer.sd.line([(gx - 6, gy + 13), (gx + 6, gy + 13)], fill=hx(MAGENTA), width=2)
    layer.sd.ellipse([gx + 2, gy - 16, gx + 8, gy - 10], outline=hx(YELLOW))
    # 雨棚
    m2_awning(layer, rng, x + 12, 244, w - 24, '#4a2434', '#2a1220', trim='#ff8a2a')
    # 吧台橱窗
    m2_shop_window(layer, rng, x + 18, 282, w - 70, 48, '#ffb066', kind='bar')
    m2_door(layer, rng, x + w - 48, 292, 24, 38, '#ffb066')
    # 门口灯
    glow_dot(layer, x + w - 56, 288, 2, '#ffd23f', '#fff4cc')
    glow_dot(layer, x + w - 36, 288, 2, '#ffd23f', '#fff4cc')
    # 小竖牌
    m2_board_v(layer, x + w - 20, 286, 14, 42, '酒', 13, board='#1a0d14',
               border=YELLOW, txt=YELLOW, core='#fff6cc', border_w=1, spill=0.2)
    m2_poster(layer, rng, x + 6, 206, 12, 16)


def m2_bld_dojo(layer, rng, x, w, top):
    """Boss 区：铁面道场（巨大屋檐 + 巨幅竖幡 + 铁门 + 射灯）。"""
    d = layer.d
    # 主体（用 tower 立面但只在上半部，下半被门/幡覆盖）
    rect(d, x, top + 26, w, 344 - top - 26, hx('#160c22'))
    rect(d, x, top + 26, 3, 344 - top - 26, hx('#2b1740'))
    rect(d, x + w - 4, top + 26, 4, 344 - top - 26, hx('#090512'))
    # 主体楼板/木构
    for yy in range(top + 40, 340, 22):
        rect(d, x + 2, yy, w - 4, 1, hx('#1d1230'))
    for _ in range(w // 60):
        px_ = x + rng.randint(10, max(12, w - 12))
        rect(d, px_, top + 40, 2, 220, hx('#211434'))
    # 屋檐（3 层瓦 + 翘角）
    for i in range(3):
        yy = top + 4 + i * 8
        rect(d, x - 8, yy, w + 16, 8, hx(['#1f1234', '#1a0f2c', '#150b25'][i]))
        rect(d, x - 8, yy, w + 16, 1, hx('#3a2456'))
        for xx in range(x - 8, x + w + 8, 14):
            rect(d, xx, yy + 1, 1, 7, hx('#100a1e'))
    rect(d, x - 12, top - 2, w + 24, 6, hx('#0b0716'))
    rect(d, x - 12, top - 4, w + 24, 2, hx('#3d1a5c'))
    d.polygon([(x - 18, top - 1), (x - 4, top - 10), (x + 4, top - 1)], fill=hx('#0b0716'))
    d.polygon([(x + w + 14, top - 1), (x + w - 2, top - 10), (x + w - 8, top - 1)], fill=hx('#0b0716'))
    # 檐口霓虹
    layer.sd.line([(x - 14, top - 5), (x + w + 14, top - 5)], fill=hx(MAGENTA), width=2)
    for k in range(4):
        glow_dot(layer, x + 20 + k * (w - 40) // 3, top + 16, 2, YELLOW, '#fffde0')
    # 大灯笼一对
    for lx in (x + 22, x + w - 23):
        rect(d, lx, top + 18, 1, 42, hx('#0a0614'))
        m2_lantern(layer, lx, 90, 11, '#ff3b5c', '#8a1a34')
    # 巨幅竖幡「铁面」
    bw, bh = 66, 196
    bx, by = x + w // 2 - bw // 2, 62
    rect(d, bx - 3, by - 3, bw + 6, bh + 6, hx('#07040e'))
    rect(d, bx, by, bw, bh, hx('#5a1220'))
    rect(d, bx, by, bw, 5, hx('#7a1a2c'))
    rect(d, bx, by, 4, bh, hx('#7a1a2c'))
    rect(d, bx + bw - 4, by, 4, bh, hx('#3a0812'))
    rect(d, bx, by + bh - 5, bw, 5, hx('#3a0812'))
    rect(d, bx + 4, by + 4, bw - 8, 1, hx('#a02838'))
    m = text_mask('铁面', 40, vertical=True, gap=12)
    stamp(layer.img, m, bx + (bw - m.width) // 2, by + 16, hx('#f7e9d7'))
    # 幡的暖色描边
    layer.sd.rectangle([bx - 5, by - 5, bx + bw + 4, by + bh + 4], outline=hx('#ff8a2a', 170))
    layer.spills.append((bx - 10, by + bh, bw + 20, '#ff3b5c', 0.45))
    # 墙面龙纹剪影
    def dragon(od):
        pts = []
        for i in range(30):
            t = i / 29.0
            pts.append((x + 24 + t * (w - 48), 176 + math.sin(t * 7.5 + 1.2) * 18 + t * 62))
        od.line(pts, fill=hx('#2a1a44', 170), width=3)
        for i in range(7):
            t = i / 6.0
            cx = x + 24 + t * (w - 48)
            cy = 176 + math.sin(t * 7.5 + 1.2) * 18 + t * 62
            od.line([(cx, cy), (cx - 7, cy - 9)], fill=hx('#2a1a44', 160), width=2)
            od.line([(cx, cy), (cx + 6, cy + 7)], fill=hx('#2a1a44', 120), width=1)
    layer.overlay(dragon)
    # 铁门
    gx, gy, gw, gh = x + 26, 254, w - 52, 86
    rect(d, gx - 4, gy - 4, gw + 8, gh + 8, hx('#07040e'))
    rect(d, gx, gy, gw, gh, hx('#1d1830'))
    half = (gw - 4) // 2
    for side in range(2):
        bx0 = gx + side * (half + 4)
        rect(d, bx0, gy, half, gh, hx('#221d36' if side == 0 else '#1b1730'))
        for xx in range(bx0 + 4, bx0 + half - 3, 10):
            rect(d, xx, gy + 4, 1, gh - 8, hx('#2c2744'))
        rect(d, bx0 + 2, gy + 4, half - 4, 1, hx('#2c2744'))
        rect(d, bx0 + 2, gy + gh - 5, half - 4, 1, hx('#0d0a18'))
        rect(d, bx0 + 2, gy + 4, 1, gh - 8, hx('#0d0a18'))
        for yy in range(gy + 9, gy + gh - 9, 13):
            rect(d, bx0 + 7, yy, 2, 2, hx('#4a4368'))
            rect(d, bx0 + half - 10, yy, 2, 2, hx('#4a4368'))
    # 门缝红光
    rect(d, gx + half + 1, gy + 2, 2, gh - 4, hx('#7a1030'))
    # 警示条
    for xx in range(gx, gx + gw, 12):
        d.polygon([(xx, gy + gh + 4), (xx + 6, gy + gh + 4), (xx + 9, 343), (xx + 3, 343)],
                  fill=hx('#b8912a'))
        d.polygon([(xx + 6, gy + gh + 4), (xx + 12, gy + gh + 4), (xx + 15, 343), (xx + 9, 343)],
                  fill=hx('#141021'))
    # 门框霓虹
    layer.sd.line([(gx - 6, gy - 6), (gx + gw + 5, gy - 6)], fill=hx(CYAN), width=2)
    layer.sd.line([(gx - 6, gy - 6), (gx - 6, 338)], fill=hx(CYAN_D), width=1)
    layer.sd.line([(gx + gw + 5, gy - 6), (gx + gw + 5, 338)], fill=hx(CYAN_D), width=1)
    # 门楣小匾「極」
    m2_board_h(layer, x + w // 2 - 24, 232, 48, 20, '極', 14, board='#1a0d10',
               border=YELLOW, txt=YELLOW, core='#fff6cc', border_w=1, spill=0.0)
    # 射灯（屋檐下）
    for sx_ in (x + 36, x + w - 40):
        rect(d, sx_ - 4, top + 22, 9, 5, hx('#241a36'))
        rect(d, sx_ - 3, top + 23, 7, 3, hx('#c9a13a'))
        glow_dot(layer, sx_ + 1, top + 26, 2, '#ffd23f', '#fffde0')
    # 底部红光
    def redlight(od):
        for yy in range(300, 344):
            od.line([(gx, yy), (gx + gw, yy)], fill=(255, 59, 92, 20))
    layer.overlay(redlight)


def m2_bld_billboard(layer, rng, x, w, top):
    """巨幅霓虹广告牌「霓虹」——Boss 区地标。"""
    d = layer.d
    # 底部楼体
    m2_facade(layer, rng, x, w, top, style='grid', lit_prob=0.12, tone='#150e24',
              bay_w=30, win_w=9, win_h=10)
    # 广告牌支架
    bw, bh = w - 34, 168
    bx, by = x + 17, 26
    for lx in (bx + 6, bx + bw // 2 - 2, bx + bw - 12):
        rect(d, lx, by + bh, 4, 344 - by - bh, hx('#0c0817'))
        rect(d, lx + 1, by + bh, 1, 344 - by - bh, hx('#241a3c'))
        for yy in range(by + bh + 10, 340, 26):
            rect(d, lx - 3, yy, 10, 1, hx('#0a0616'))
    # 牌面
    rect(d, bx - 3, by - 3, bw + 6, bh + 6, hx('#06030c'))
    rect(d, bx, by, bw, bh, hx('#0e0920'))
    rect(d, bx + 4, by + 4, bw - 8, bh - 8, hx('#180f2e'))
    # 背景斜线速度感
    for i in range(9):
        yy = by + 16 + i * 18
        d.polygon([(bx + 10, yy), (bx + bw - 10, yy - 10), (bx + bw - 10, yy - 6), (bx + 10, yy + 4)],
                  fill=hx('#221440'))
    # 大竖字「霓虹」
    m_neon = text_mask('霓', 62, block=2)
    m_hong = text_mask('虹', 62, block=2)
    m_all = text_mask('霓虹', 62, block=2, vertical=True, gap=8)
    tx = bx + (bw - m_all.width) // 2
    ty = by + (bh - m_all.height) // 2
    stamp(layer.img, m_all.filter(ImageFilter.MaxFilter(3)), tx - 2, ty - 2, hx('#0a0614'))
    y2 = ty + m_neon.height + 8
    stamp(layer.signs, m_neon, tx + (m_all.width - m_neon.width) // 2, ty, hx(MAGENTA))
    stamp(layer.signs, m_neon.filter(ImageFilter.MinFilter(3)),
          tx + (m_all.width - m_neon.width) // 2, ty, hx('#ffe0ef'), 225)
    stamp(layer.signs, m_hong, tx + (m_all.width - m_hong.width) // 2, y2, hx(CYAN))
    stamp(layer.signs, m_hong.filter(ImageFilter.MinFilter(3)),
          tx + (m_all.width - m_hong.width) // 2, y2, hx('#e8ffff'), 225)
    # 霓虹牌框
    layer.sd.rectangle([bx, by, bx + bw - 1, by + bh - 1], outline=hx(PURPLE), width=2)
    layer.sd.rectangle([bx + 4, by + 4, bx + bw - 5, by + bh - 5], outline=hx(CYAN_D, 170))
    for (cx, cy) in [(bx, by), (bx + bw - 1, by), (bx, by + bh - 1), (bx + bw - 1, by + bh - 1)]:
        glow_dot(layer, cx, cy, 2, YELLOW, '#fffde0')
    # 射灯
    for sx_ in (bx + 18, bx + bw - 20):
        rect(d, sx_ - 4, by - 10, 9, 8, hx('#241a36'))
        rect(d, sx_ - 3, by - 9, 7, 5, hx('#c9a13a'))
        glow_dot(layer, sx_ + 1, by - 11, 2, '#ffd23f', '#fffde0')
    # 牌下管线
    rect(d, bx + 6, by + bh + 3, bw - 12, 2, hx('#0a0616'))
    # 底部店面（卷帘 + 霓虹）
    m2_shutter(layer, rng, x + 22, 286, w - 44, 44, gtag=True)
    layer.spills.append((bx, by + bh, bw, '#7a3cff', 0.35))
    glow_dot(layer, x + w // 2, 280, 2, MAGENTA, '#ffd9ec')


def m2_bld_residential(layer, rng, x, w, top):
    """老式住宅：阳台晒衣 + 空调 + 暖窗。"""
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='balcony', lit_prob=0.28,
                     tone='#221830', bay_w=34, win_w=10, win_h=12,
                     theme=('#ffb066', '#a14a1a', '#4a2010'))
    m2_roof(layer, rng, x, w, top, kind=rng.choice(['tank', 'antenna', 'rail']))
    # 晒衣线
    for i, fy in enumerate(info['floor_ys']):
        if i % 2 == 1:
            continue
        ly = fy + info['win_h'] + 3
        rect(d, x + 8, ly, w - 16, 1, hx('#2a2140'))
        for k in range(rng.randint(2, 4)):
            cx = x + 16 + k * rng.randint(18, 34)
            if cx + 8 > x + w - 12:
                break
            hh = rng.randint(6, 12)
            rect(d, cx, ly, 7, hh, hx(rng.choice(['#2a1a3a', '#1a2440', '#3a2a28', '#203040'])))
            rect(d, cx, ly, 7, 1, hx('#3a2f52'))
    # 空调
    for _ in range(rng.randint(1, 3)):
        m2_ac(layer, rng, x + rng.randint(8, max(10, w - 30)), rng.randint(top + 30, max(top + 34, 280)))
    # 底层：小卖部或门洞
    m2_door(layer, rng, x + w // 2 - 12, 304, 24, 32, '#ffd9a0')
    m2_shop_window(layer, rng, x + 14, 300, 30, 36, '#c9a13a', kind='bar')
    m2_poster(layer, rng, x + w - 26, 258, 13, 17)
    m2_pipe_v(d, x + 6, top + 20, 330, 2)


def m2_bld_industrial(layer, rng, x, w, top):
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='strip', lit_prob=0.08,
                     tone='#191227', win_w=8, win_h=8, floor_h=18,
                     theme=('#8fe8c8', '#2a7a6a', '#123a34'))
    m2_roof(layer, rng, x, w, top, kind=rng.choice(['vent', 'ac', 'antenna']))
    # 大排风管
    for i in range(2):
        yy = 186 + i * 62
        rect(d, x + 8, yy, w - 16, 15, hx('#221a34'))
        rect(d, x + 8, yy, w - 16, 2, hx('#352a50'))
        rect(d, x + 8, yy + 13, w - 16, 2, hx('#0d0918'))
        for xx in range(x + 12, x + w - 14, 20):
            rect(d, xx, yy + 1, 2, 13, hx('#0d0918'))
    m2_pipe_v(d, x + 14, top + 18, 330, 4)
    m2_pipe_v(d, x + w - 18, 200, 330, 3)
    # 工业警示牌
    rect(d, x + w // 2 - 13, 250, 26, 18, hx('#b8912a'))
    rect(d, x + w // 2 - 11, 252, 22, 14, hx('#141021'))
    d.polygon([(x + w // 2, 254), (x + w // 2 + 6, 263), (x + w // 2 - 6, 263)], fill=hx('#b8912a'))
    glow_dot(layer, x + 12, 206, 2, '#ffd23f', '#fff6cc')
    m2_shutter(layer, rng, x + 12, 290, w - 24, 38, gtag=False)
    layer.spills.append((x + 4, 206, 16, '#ffd23f', 0.15))


def m2_bld_service2(layer, rng, x, w, top):
    d = layer.d
    info = m2_facade(layer, rng, x, w, top, style='grid', lit_prob=0.16, tone='#181126',
                     bay_w=30, win_w=9, win_h=10)
    m2_roof(layer, rng, x, w, top, kind=rng.choice(['rail', 'ac', 'vent']))
    # 铁网围栏
    for xx in range(x + 6, x + w - 6, 6):
        rect(d, xx, 296, 1, 44, hx('#1f1830'))
    for yy in range(298, 340, 8):
        rect(d, x + 6, yy, w - 12, 1, hx('#1f1830'))
    rect(d, x + 6, 294, w - 12, 2, hx('#2a2044'))
    m2_ac(layer, rng, x + 10, 246)
    rect(d, x + w - 44, 314, 20, 26, hx('#151022'))
    rect(d, x + w - 42, 312, 16, 3, hx('#241a36'))
    m2_board_v(layer, x + w - 26, 176, 16, 44, '酒', 13, board='#180b14',
               border=YELLOW, txt=YELLOW, core='#fff6cc', border_w=1, spill=0.3)
    def steam(od):
        for i in range(16):
            yy = 300 - i * 4
            rr = 1 + i // 5
            od.ellipse([x + w - 32 - rr, yy - rr, x + w - 32 + rr, yy + rr],
                       fill=(200, 220, 255, max(0, 18 - i)))
    layer.overlay(steam)


def m2_alley(layer, rng, ax0, ax1):
    """两楼之间的窄巷：透过它看到远景天际线 + 铁网 + 蒸汽。"""
    d = layer.d
    aw = ax1 - ax0
    # 两侧墙的厚度阴影（不透明，强化纵深）
    rect(d, ax0, 140, 5, 204, hx('#0a0616'))
    rect(d, ax1 - 5, 120, 5, 224, hx('#0a0616'))
    # 巷内远处地面（微亮，比两侧暗）
    rect(d, ax0 + 5, 306, aw - 10, 38, hx('#1a1228'))
    rect(d, ax0 + 5, 306, aw - 10, 2, hx('#2c2044'))
    for yy in range(312, 344, 8):
        rect(d, ax0 + 5, yy, aw - 10, 1, hx('#100b1c'))
    # 铁网门（线条，背后透出远景）
    for xx in range(ax0 + 6, ax1 - 5, 4):
        rect(d, xx, 246, 1, 98, hx('#241c3a'))
    for yy in range(250, 344, 6):
        rect(d, ax0 + 5, yy, aw - 10, 1, hx('#241c3a'))
    for yy in range(250, 344, 30):
        rect(d, ax0 + 4, yy, aw - 8, 2, hx('#2e2348'))
    rect(d, ax0 + 5, 244, aw - 10, 3, hx('#2e2348'))
    # 巷内一盏远处霓虹
    rect(d, ax0 + 18, 246, 10, 6, hx('#140a18'))
    layer.sd.rect if False else None
    layer.sd.ellipse([ax1 - 20, 258, ax1 - 12, 266], fill=hx(MAGENTA))
    layer.sd.ellipse([ax1 - 18, 260, ax1 - 14, 264], fill=hx('#ffe0ef'))
    layer.spills.append((ax0 + 6, 306, aw - 12, MAGENTA, 0.22))
    # 蒸汽从巷口涌出
    def steam(od):
        for i in range(40):
            t = i / 39.0
            cx = ax0 + aw * 0.55 + math.sin(t * 4.2) * 9
            cy = 330 - t * 130
            rr = int(3 + t * 13)
            a = int(26 * (1 - t) ** 1.3)
            if a > 1:
                od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(180, 200, 235, a))
    layer.overlay(steam)
    # 巷口上方挂的小灯
    glow_dot(layer, ax0 + 14, 238, 2, CYAN, '#ffffff')


def m2_sky_cables(layer, rng):
    """楼与楼之间的细电缆（1px，增加纵深与赛博感）。"""
    d = layer.d
    spans = [(40, 120, 780, 150), (420, 96, 1220, 70), (940, 118, 1700, 96),
             (1260, 60, 1980, 84), (1500, 110, 2240, 90), (1800, 60, 2520, 74),
             (2200, 100, 2960, 70), (2600, 80, 3150, 100)]
    def paint(od):
        for (x0, y0, x1, y1) in spans:
            catenary(od, x0, y0, x1, y1, 14, hx('#0a0616', 210), 1)
            catenary(od, x0, y0 + 6, x1, y1 + 6, 18, hx('#0a0616', 160), 1)
        # 悬挂的小灯
        for (lx, ly) in [(800, 154), (1740, 112), (2280, 104)]:
            od.line([(lx, ly - 10), (lx, ly)], fill=hx('#0a0616'), width=1)
            od.ellipse([lx - 3, ly, lx + 3, ly + 6], fill=hx('#0a0616'))
    layer.overlay(paint)


def m2_ambient(layer):
    """全局大气：底部城市辉光 + 楼体接触阴影 + 顶部薄雾。"""
    def paint(od):
        # 楼体靠近街面的阴影（压暗，让角色区更干净）
        for yy in range(296, 344):
            t = (yy - 296) / 47.0
            od.line([(0, yy), (W, yy)], fill=(6, 4, 13, int(66 * t ** 1.2)))
        # 地平线暖/品红城市光
        for yy in range(280, 344):
            t = (yy - 280) / 63.0
            od.line([(0, yy), (W, yy)], fill=(255, 80, 150, int(5 + 6 * t)))
        # 顶部薄雾
        for yy in range(0, 120):
            t = 1 - yy / 120.0
            od.line([(0, yy), (W, yy)], fill=(36, 22, 66, int(16 * t)))
    layer.overlay(paint)


def m2_spills(layer):
    if not layer.spills:
        return
    def paint(od):
        for (x, y, w, color, strength) in layer.spills:
            col = color if isinstance(color, str) else color
            for yy in range(int(y), min(344, int(y) + 74)):
                t = (yy - y) / 74.0
                a = int(58 * strength * (1 - t) ** 1.7)
                if a < 1:
                    continue
                od.line([(int(x + 2), yy), (int(x + w - 3), yy)], fill=hx(col, a))
    layer.overlay(paint)


def gen_mid():
    """中景：沿街楼体 + 拉面店 / 居酒屋 / 街机厅 / KTV / 酒吧 / 铁面道场 / 霓虹广告牌。"""
    rng = random.Random(19880808)
    layer = Layer(W, H)
    d = layer.d
    # ---- 后排楼群（叠在楼顶轮廓与巷口后的深色楼影） ----
    backs = [(-140, 300, 86), (240, 220, -20), (480, 200, 158), (660, 160, 62),
             (860, 220, 146), (1120, 240, -30), (1400, 200, 74), (1640, 220, 34),
             (1900, 220, 118), (2150, 240, -10), (2400, 200, 56),
             (2650, 240, 148), (2900, 200, 30), (3080, 220, 96)]
    for (bx, bw, btop) in backs:
        tone = rng.choice(['#1a1230', '#1d1435', '#17102b', '#201636'])
        rect(d, bx, btop, bw, 344 - btop, hx(tone))
        rect(d, bx, btop, bw, 2, hx('#2c1e4c'))
        rect(d, bx, btop, 2, 344 - btop, hx('#241a40'))
        rect(d, bx + bw - 3, btop, 3, 344 - btop, hx('#0a0616'))
        # 规则窗格（远处，低对比）
        cols = max(1, (bw - 16) // 13)
        rows = max(1, (330 - btop - 20) // 16)
        for rr in range(rows):
            for cc in range(cols):
                wx = bx + 8 + cc * 13
                wy = btop + 16 + rr * 16
                if wy + 5 > 332:
                    continue
                if rng.random() < 0.30:
                    rect(d, wx, wy, 4, 5, hx(rng.choice(['#8a6a20', '#22606c', '#7a2250',
                                                        '#9fb6c8', '#a87a28'])))
                else:
                    rect(d, wx, wy, 4, 5, hx('#0d0818'))
        # 楼顶设备剪影
        if rng.random() < 0.8:
            tx = bx + rng.randint(8, max(10, bw - 34))
            kind = rng.random()
            if kind < 0.4:
                rect(d, tx, btop - 16, 16, 16, hx(tone))
                rect(d, tx, btop - 16, 16, 1, hx('#342456'))
                rect(d, tx + 12, btop - 26, 2, 26, hx('#0a0616'))
            elif kind < 0.7:
                hh = rng.randint(20, 46)
                rect(d, tx, btop - hh, 2, hh, hx('#0a0616'))
                for k in range(3):
                    rect(d, tx - 5, btop - hh + 6 + k * 8, 12, 1, hx('#0a0616'))
                glow_dot(layer, tx + 1, btop - hh, 1, RED, '#ffd9e0')
            else:
                rect(d, tx, btop - 12, 24, 12, hx(tone))
                rect(d, tx, btop - 12, 24, 1, hx('#342456'))
                rect(d, tx + 3, btop - 10, 8, 5, hx('#0d0818'))
    # 后排雾气（拉开层次，压住「黑板」感）
    def back_haze(od):
        for yy in range(60, 344):
            t = clamp((yy - 60) / 284.0, 0, 1)
            od.line([(0, yy), (W, yy)], fill=(46, 30, 82, int(16 + 18 * t)))
    layer.overlay(back_haze)
    # ---- 前排建筑 ----
    specs = [
        (-80, 300, 20, m2_bld_apartment),
        (220, 220, 138, m2_bld_ramen),
        (440, 180, 10, m2_bld_izakaya),
        (620, 150, 176, m2_bld_shutter),
        (770, 120, 232, m2_bld_service),
        (940, 210, 60, m2_bld_arcade),
        (1150, 140, -10, m2_bld_ktv),
        (1290, 180, 130, m2_bld_bar),
        (1470, 230, 26, m2_bld_dojo),
        (1700, 240, -20, m2_bld_billboard),
        (1940, 180, 100, m2_bld_industrial),
        (2120, 240, 60, m2_bld_residential),
        (2360, 200, 140, m2_bld_apartment),
        (2560, 240, 30, m2_bld_shutter),
        (2800, 200, 110, m2_bld_apartment),
        (3000, 240, 40, m2_bld_ktv),
    ]
    for (x, w, top, fn) in specs:
        fn(layer, rng, x, w, top)
    # ---- 巷口 ----
    m2_alley(layer, rng, 890, 940)
    # ---- 楼间电缆 ----
    m2_sky_cables(layer, rng)
    # ---- 招牌光斑 / 大气 ----
    m2_spills(layer)
    m2_ambient(layer)
    layer.finish(radius=10.0, gain=1.15, tight=2.4, tight_gain=0.62)
    print('  mid  :', W, H)
    return layer


def wet_streaks(layer, rng, specs):
    """湿地面霓虹倒影（竖向拖影）。specs: (cx, y0, y1, half_w, color, strength, seed)"""
    def paint(od):
        for (cx, y0, y1, half_w, color, strength, seed) in specs:
            for y in range(int(y0), int(y1)):
                t = (y - y0) / max(1.0, (y1 - y0))
                a = int(255 * strength * (1.0 - 0.8 * t))
                if a <= 1:
                    continue
                ww = max(1, int(round(half_w * (0.5 + 0.5 * (1 - t)))))
                off = int(round(math.sin(t * 6.5 + seed) * half_w * 0.7))
                if rng.random() < 0.18:
                    continue
                od.line([(cx + off - ww, y), (cx + off + ww, y)],
                        fill=hx(color, min(70, a)))
    layer.overlay(paint)


def light_pool(layer, cx, cy, rx, ry, color, strength=1.0):
    def paint(od):
        for i in range(5):
            t = i / 4.0
            r = int(28 * strength * (1 - t * 0.6))
            od.ellipse([cx - rx * (1 - t * 0.5), cy - ry * (1 - t * 0.5),
                        cx + rx * (1 - t * 0.5), cy + ry * (1 - t * 0.5)],
                       fill=hx(color, int(7 + t * 9)))
    layer.overlay(paint)


def ellipse_pts(cx, cy, rx, ry, n=30, jitter=0.0, rng=None):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        j = 1.0
        if rng is not None and jitter:
            j = 1.0 + rng.uniform(-jitter, jitter)
        pts.append((cx + math.cos(a) * rx * j, cy + math.sin(a) * ry * j))
    return pts


def puddle(layer, rng, cx, cy, rx, ry, colors, depth=0.62):
    pts = ellipse_pts(cx, cy, rx, ry, 34, 0.14, rng)
    mask = Image.new('L', (layer.w, layer.h), 0)
    ImageDraw.Draw(mask).polygon([(int(x), int(y)) for x, y in pts], fill=255)
    ov = Image.new('RGBA', (layer.w, layer.h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.polygon([(int(x), int(y)) for x, y in pts], fill=hx('#0a0714', 200))
    # 水洼里的倒影
    for (col, off, hw) in colors:
        for y in range(int(cy - ry * 0.8), int(cy + ry * 0.8)):
            t = (y - (cy - ry * 0.8)) / max(1.0, ry * 1.6)
            a = int(58 * depth * (1 - t * 0.65))
            if a < 2 or rng.random() < 0.3:
                continue
            ww = max(1, int(hw * (0.5 + 0.5 * (1 - t))))
            od.line([(cx + off - ww, y), (cx + off + ww, y)], fill=hx(col, a))
    # 波纹
    for _ in range(rng.randint(2, 4)):
        wy = cy + rng.randint(-int(ry * 0.5), int(ry * 0.5))
        ww = rng.randint(4, max(6, int(rx * 0.45)))
        wx = cx + rng.randint(-int(rx * 0.5), int(rx * 0.5))
        od.line([(wx - ww, wy), (wx + ww, wy)], fill=hx('#8fb6d8', rng.randint(16, 34)))
    a = ov.getchannel('A')
    ov.putalpha(ImageChops.multiply(a, mask))
    layer.img.alpha_composite(ov)
    # 水洼亮边
    def rim(od):
        od.line([(int(x), int(y)) for x, y in pts] + [(int(pts[0][0]), int(pts[0][1]))],
                fill=hx('#7f9fc8', 44))
    layer.overlay(rim)


def draw_pole(layer, x, top_y, seed):
    rng = random.Random(seed)
    d = layer.d
    # 混凝土基座
    rect(d, x - 16, 326, 32, 28, hx('#1a1426'))
    rect(d, x - 16, 326, 32, 2, hx('#2c2140'))
    rect(d, x - 13, 350, 26, 4, hx('#0d0918'))
    rect(d, x - 15, 330, 2, 22, hx('#241a38'))
    # 杆身
    rect(d, x - 4, top_y, 9, 330 - top_y, hx('#130d1f'))
    rect(d, x - 4, top_y, 2, 330 - top_y, hx('#2a2040'))
    rect(d, x + 3, top_y, 2, 330 - top_y, hx('#080410'))
    # 横担 + 绝缘子
    for k, (ay, aw) in enumerate([(top_y + 18, 56), (top_y + 44, 44)]):
        rect(d, x - aw // 2, ay, aw, 2, hx('#0e0918'))
        rect(d, x - aw // 2, ay, aw, 1, hx('#241a38'))
        for ix in range(-aw // 2 + 6, aw // 2 - 3, 16):
            rect(d, x + ix, ay - 4, 2, 4, hx('#3a2e52'))
    # 变压器
    ty = top_y + 66
    rect(d, x + 6, ty, 18, 30, hx('#1e1830'))
    rect(d, x + 6, ty, 18, 2, hx('#33284c'))
    rect(d, x + 6, ty + 28, 18, 2, hx('#0b0716'))
    rect(d, x + 9, ty + 4, 1, 22, hx('#2a2140'))
    rect(d, x + 20, ty + 4, 1, 22, hx('#0b0716'))
    # 电缆支架 / 挂件
    rect(d, x - 10, top_y + 96, 20, 2, hx('#120c1e'))
    for i in range(3):
        rect(d, x - 8 + i * 7, top_y + 98, 2, 5, hx('#120c1e'))
    # 杆上小广告牌（近景的电杆招牌）
    if rng.random() < 0.7:
        sx, sy = x - 26, top_y + 110
        rect(d, sx - 2, sy - 2, 30, 20, hx('#07040e'))
        rect(d, sx, sy, 26, 16, hx('#14202c'))
        layer.sd.rectangle([sx, sy, sx + 25, sy + 15], outline=hx(CYAN_D, 210))
        m = text_mask('电', 10)
        stamp(layer.signs, m, sx + (26 - m.width) // 2, sy + (16 - m.height) // 2, hx(CYAN))
    # 底部反光
    layer.sd.ellipse([x - 12, 346, x + 12, 354], outline=hx('#3df3ff', 40))


def catenary(d, x0, y0, x1, y1, sag, color, width=1):
    n = max(6, int(abs(x1 - x0) / 6))
    pts = []
    for i in range(n + 1):
        t = i / n
        xx = x0 + (x1 - x0) * t
        yy = y0 + (y1 - y0) * t + sag * 4 * t * (1 - t)
        pts.append((xx, yy))
    line(d, pts, color, width)


def draw_vending(layer, rng, x, base_y=352, w=46, h=76):
    """发光自动贩卖机（近景光源）。"""
    d = layer.d
    top = base_y - h
    rect(d, x - 2, top - 2, w + 4, h + 4, hx('#07040e'))
    rect(d, x, top, w, h, hx('#142430'))
    rect(d, x, top, w, 4, hx('#2a4a5c'))
    rect(d, x, top, 3, h, hx('#2f5a6c'))
    rect(d, x + w - 3, top, 3, h, hx('#0b1520'))
    # 发光面板
    px0, py0, pw, ph = x + 5, top + 7, w - 10, 44
    rect(d, px0, py0, pw, ph, hx('#d8f4ff'))
    layer.sd.rectangle([px0, py0, px0 + pw - 1, py0 + ph - 1], fill=hx('#e8ffff'))
    # 商品
    for r in range(3):
        for c in range(4):
            cx = px0 + 3 + c * 9
            cy = py0 + 3 + r * 14
            rect(d, cx, cy, 7, 10, hx(rng.choice(['#ff3b5c', '#3df3ff', '#ffd23f', '#8dff5a', '#ff8a2a'])))
            rect(d, cx, cy, 7, 2, hx('#e8f6ff'))
    # 出货口 / 投币
    rect(d, x + 6, top + h - 20, w - 12, 12, hx('#0b1520'))
    rect(d, x + 8, top + h - 18, w - 16, 8, hx('#060a10'))
    rect(d, x + (w - 14) // 2, top + h - 8, 14, 4, hx('#2a4a5c'))
    rect(d, x + w - 14, top + 8, 8, 4, hx('#ffd23f'))
    # 灯管
    layer.sd.line([(x + 1, top + 2), (x + 1, base_y - 2)], fill=hx(CYAN, 160), width=1)
    # 地面反光
    light_pool(layer, x + w // 2, base_y + 16, 44, 18, '#7fe8ff', 1.0)


def draw_hydrant(layer, x, base_y=352):
    d = layer.d
    col = '#c23b4e'
    rect(d, x - 6, base_y - 22, 12, 22, hx(col))
    rect(d, x - 6, base_y - 22, 2, 22, hx('#e0606e'))
    rect(d, x + 4, base_y - 22, 2, 22, hx('#7a2030'))
    # 顶部
    rect(d, x - 8, base_y - 26, 16, 4, hx(col))
    rect(d, x - 5, base_y - 31, 10, 5, hx('#d8455a'))
    rect(d, x - 3, base_y - 34, 6, 3, hx('#e0606e'))
    # 侧口
    rect(d, x - 10, base_y - 18, 4, 6, hx('#8a2836'))
    rect(d, x + 6, base_y - 18, 4, 6, hx('#8a2836'))
    # 底座法兰
    rect(d, x - 8, base_y - 3, 16, 3, hx('#5a1824'))
    # 描边
    d.rectangle([x - 9, base_y - 35, x + 8, base_y - 1], outline=hx('#150b22'))
    # 小标签
    rect(d, x - 3, base_y - 17, 6, 4, hx('#2f9aa8'))
    # 地面阴影/反光
    layer.sd.ellipse([x - 10, base_y + 1, x + 10, base_y + 5], outline=hx('#7f9fc8', 50))


def draw_trash(layer, rng, x, base_y=352):
    d = layer.d
    for i in range(rng.randint(2, 3)):
        cx = x + rng.randint(-12, 12)
        rw = rng.randint(12, 18)
        rh = rng.randint(10, 16)
        top = base_y - rh
        pts = [(cx - rw, base_y), (cx - rw + 2, top + 3), (cx - rw // 2, top),
               (cx + rw // 2, top + 2), (cx + rw, top + 5), (cx + rw - 1, base_y)]
        d.polygon(pts, fill=hx('#1c1626'))
        d.line([(cx - rw // 2, top + 3), (cx + rw // 2, top + 4)], fill=hx('#332a44'))
        d.line([(cx - rw + 3, base_y - 3), (cx + rw - 4, base_y - 4)], fill=hx('#0e0a16'))
        if rng.random() < 0.5:
            rect(d, cx - 2, top + 2, 6, 2, hx('#3a2e52'))


def draw_crates(layer, rng, x, base_y=352):
    d = layer.d
    bw, bh = 22, 18
    rect(d, x, base_y - bh, bw, bh, hx('#251a2c'))
    rect(d, x, base_y - bh, bw, 2, hx('#3a2a42'))
    d.line([(x, base_y - bh, ), (x + bw - 1, base_y - 1)], fill=hx('#160f1c'))
    d.line([(x + bw - 1, base_y - bh), (x, base_y - 1)], fill=hx('#160f1c'))
    rect(d, x + 2, base_y - bh - 13, 17, 13, hx('#2a1e2e'))
    rect(d, x + 2, base_y - bh - 13, 17, 2, hx('#3f2f46'))
    rect(d, x + 7, base_y - bh - 8, 7, 3, hx('#4a3a52'))


def draw_manhole(layer, cx, cy, rx=26, ry=9):
    d = layer.d
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=hx('#161022'))
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=hx('#2c2240'))
    d.ellipse([cx - rx + 3, cy - ry + 2, cx + rx - 3, cy + ry - 2], outline=hx('#211a32'))
    for i in range(-2, 3):
        d.line([(cx - rx + 6, cy + i * 3), (cx + rx - 6, cy + i * 3)], fill=hx('#1d1629'))
    d.line([(cx - 4, cy - 4), (cx + 3, cy + 4)], fill=hx('#2c2240'))


def draw_drain(layer, x, y=524, w=54, h=16, rng=None):
    d = layer.d
    rect(d, x - 2, y - 2, w + 4, h + 4, hx('#070410'))
    rect(d, x, y, w, h, hx('#100c1a'))
    for xx in range(x + 3, x + w - 2, 5):
        rect(d, xx, y + 2, 2, h - 4, hx('#241a32'))
    rect(d, x, y, w, 1, hx('#33284a'))
    if rng is not None:
        # 积水微光
        for _ in range(4):
            gx = x + rng.randint(4, max(6, w - 8))
            rect(d, gx, y + rng.randint(3, max(4, h - 4)), rng.randint(2, 5), 1,
                 hx(rng.choice([CYAN, MAGENTA, '#7f9fc8']), rng.randint(30, 70)))


def draw_bollard(layer, x, base_y=356, col='#b8912a'):
    d = layer.d
    rect(d, x - 4, base_y - 20, 8, 20, hx('#231a2a'))
    rect(d, x - 4, base_y - 20, 8, 2, hx(col))
    rect(d, x - 4, base_y - 14, 8, 2, hx(col))
    rect(d, x - 4, base_y - 8, 8, 2, hx(col))
    d.ellipse([x - 4, base_y - 23, x + 4, base_y - 17], fill=hx('#231a2a'))
    d.ellipse([x - 4, base_y - 23, x + 4, base_y - 17], outline=hx('#0d0918'))
    rect(d, x - 5, base_y - 1, 10, 2, hx('#0d0918'))


def gen_near():
    rng = random.Random(20770401)
    arr = np.zeros((H, W, 4), np.float32)
    # 人行道平面
    banded(arr, WALK_TOP, GROUND_TOP, SIDEWALK_PAL, 0, W, gamma=0.8)
    # 路缘石
    for yy in range(GROUND_TOP, STREET_TOP):
        t = (yy - GROUND_TOP) / float(STREET_TOP - GROUND_TOP)
        col = mix(rgb3(CURB_TOP), rgb3(CURB_FACE), min(1.0, t * 1.8))
        arr[yy, :, :3] = np.array(col, np.float32)
        arr[yy, :, 3] = 255
    arr[GROUND_TOP, :, :3] = np.array(rgb3(CURB_TOP), np.float32)
    arr[GROUND_TOP + 1, :, :3] = np.array(rgb3('#5d4a7a'), np.float32)
    arr[STREET_TOP - 1, :, :3] = np.array(rgb3(CURB_BOT), np.float32)
    # 街面
    banded(arr, STREET_TOP, H, STREET_PAL, 0, W, gamma=0.85)
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    layer = Layer(W, H, base=base)
    d = layer.d
    # ---- 人行道砖缝（透视：越近行距越大） ----
    rows = [330, 334, 339, 345, 352]
    for i, yy in enumerate(rows):
        rect(d, 0, yy, W, 1, hx('#1c1430'))
        rect(d, 0, yy + 1, W, 1, hx('#382a58'))
        # 竖缝（逐行错位，近处间距更大）
        step = 18 + i * 8
        off = (i * 11) % step
        for xx in range(-off, W, step):
            rect(d, xx, yy, 1, (rows[i + 1] if i + 1 < len(rows) else GROUND_TOP) - yy,
                 hx('#221a36'))
    # 人行道上的湿反光
    def walk_wet(od):
        for cx in range(0, W, 137):
            rx = 26 + (cx * 13) % 38
            cy = 338 + (cx * 7) % 14
            od.ellipse([cx - rx, cy - 4, cx + rx, cy + 4], fill=(120, 160, 220, 12))
    layer.overlay(walk_wet)
    # 墙根阴影
    rect(d, 0, WALK_TOP, W, 4, hx('#0a0714'))
    rect(d, 0, WALK_TOP + 4, W, 2, hx('#1c142c'))
    # ---- 街面湿沥青质感 ----
    # 大块明暗斑
    def asphalt(od):
        for _ in range(90):
            cx = rng.randrange(W)
            cy = rng.randrange(STREET_TOP + 8, H)
            rw = rng.randint(20, 90)
            rh = rng.randint(4, 14)
            c = rng.choice(['#241c38', '#0f0b19', '#1b1429'])
            od.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=hx(c, rng.randint(14, 34)))
    layer.overlay(asphalt)
    # 裂纹 / 沥青接缝
    def cracks(od):
        for _ in range(26):
            x0 = rng.randrange(W)
            y0 = rng.randrange(STREET_TOP + 20, H - 10)
            pts = [(x0, y0)]
            for k in range(rng.randint(2, 5)):
                x0 += rng.randint(-26, 26)
                y0 += rng.randint(1, 7)
                pts.append((x0, y0))
            od.line(pts, fill=hx('#080510', rng.randint(90, 150)), width=1)
        # 横向接缝
        for yy in [386, 404, 429, 462, 500, 524]:
            for _ in range(6):
                x0 = rng.randrange(-100, W)
                od.line([(x0, yy + rng.randint(-1, 1)), (x0 + rng.randint(80, 300), yy)],
                        fill=hx('#0a0714', rng.randint(26, 52)))
    layer.overlay(cracks)
    # 街面细颗粒
    def grain(od):
        for _ in range(2600):
            x = rng.randrange(W)
            y = rng.randrange(STREET_TOP, H)
            c = rng.choice(['#2a2140', '#0b0714', '#241c38', '#3a2f52'])
            od.point((x, y), fill=hx(c, rng.randint(30, 80)))
    layer.overlay(grain)
    # ---- 霓虹倒影 ----
    streaks = [
        (250, 380, 500, 16, '#ffd23f', 0.30, 0.1),
        (420, 370, 512, 13, MAGENTA, 0.34, 1.2),
        (905, 380, 520, 18, CYAN, 0.30, 2.3),
        (1225, 370, 505, 12, MAGENTA, 0.28, 3.1),
        (1450, 366, 522, 20, '#bfefff', 0.36, 4.0),
        (1610, 380, 500, 11, '#ff8a2a', 0.24, 5.2),
        (1800, 372, 510, 14, YELLOW, 0.26, 6.4),
        (2140, 380, 520, 16, PURPLE, 0.26, 7.1),
        (2500, 370, 515, 18, MAGENTA, 0.32, 8.3),
        (2740, 380, 500, 12, ORANGE, 0.22, 9.0),
        (2870, 368, 522, 20, '#7fe8ff', 0.34, 9.8),
        (3050, 380, 512, 14, CYAN, 0.28, 10.5),
        (118, 380, 498, 12, CYAN, 0.22, 11.2),
        (620, 384, 496, 10, '#ff3b5c', 0.20, 12.0),
        (1990, 382, 505, 12, '#ff5aa6', 0.22, 12.9),
    ]
    wet_streaks(layer, rng, streaks)
    # 霓虹光池
    light_pool(layer, 1420, 386, 52, 20, '#7fe8ff', 1.0)
    light_pool(layer, 300, 382, 40, 14, '#ffd9a0', 0.8)
    light_pool(layer, 905, 390, 44, 16, '#8fe8ff', 0.8)
    light_pool(layer, 2500, 392, 48, 16, '#ff9ac8', 0.8)
    light_pool(layer, 2870, 386, 48, 16, '#9ff0ff', 0.8)
    # ---- 前景水洼 ----
    puddle(layer, rng, 640, 512, 120, 26, [('#ffd23f', -30, 8), (MAGENTA, 20, 9), (CYAN, -70, 6)])
    puddle(layer, rng, 1520, 522, 160, 30, [(CYAN, -40, 10), ('#e8ffff', 26, 8)])
    puddle(layer, rng, 2250, 508, 100, 22, [(MAGENTA, -20, 7), (CYAN, 30, 6)])
    puddle(layer, rng, 2770, 524, 190, 34, [('#ff9ac8', -50, 12), (CYAN, 40, 10), (YELLOW, 0, 6)])
    puddle(layer, rng, 3100, 512, 110, 26, [(CYAN, -20, 8), (ORANGE, 26, 6)])
    # 角色活动带里的小水洼（低对比）
    puddle(layer, rng, 1000, 430, 40, 9, [(CYAN, 0, 5), (MAGENTA, 10, 4)], depth=0.32)
    puddle(layer, rng, 2050, 470, 56, 12, [(MAGENTA, -8, 6)], depth=0.3)
    # ---- 排水沟 / 井盖 ----
    for xx in [340, 1060, 1980, 2980]:
        draw_drain(layer, xx, 520, 54, 16, rng)
    draw_manhole(layer, 1780, 486)
    draw_manhole(layer, 2680, 480)
    draw_manhole(layer, 660, 470, 20, 7)
    # 底部前景：沟槽湿光
    def gutter(od):
        for yy in range(528, H):
            a = int(10 + (yy - 528) * 2.4)
            od.line([(0, yy), (W, yy)], fill=(150, 200, 255, min(46, a)))
    layer.overlay(gutter)
    # ---- 人行道道具 ----
    draw_hydrant(layer, 520)
    draw_hydrant(layer, 2960)
    draw_trash(layer, rng, 760)
    draw_trash(layer, rng, 2320)
    draw_trash(layer, rng, 2900)
    draw_crates(layer, rng, 1180)
    draw_crates(layer, rng, 2560)
    draw_bollard(layer, 1244)
    draw_bollard(layer, 1258)
    draw_bollard(layer, 2100, 352)
    # 自动贩卖机
    draw_vending(layer, rng, 1420, 352)
    draw_vending(layer, rng, 2860, 352)
    # 电杆 + 电缆
    poles = [(90, 34), (880, 58), (1660, 12), (2440, 42), (3020, 26)]
    for (px_, ptop) in poles:
        draw_pole(layer, px_, ptop, 1000 + px_)
    def wires(od):
        for i in range(len(poles) - 1):
            x0, t0 = poles[i]
            x1, t1 = poles[i + 1]
            for k, dy in enumerate([18, 26, 34]):
                catenary(od, x0 - 26, t0 + dy, x1 - 26, t1 + dy, 12 + k * 3,
                         hx('#0a0614', 220), 1)
            catenary(od, x0 + 24, t0 + 20, x1 + 24, t1 + 20, 18, hx('#0a0614', 180), 1)
        # 最右侧再牵一条出画
        catenary(od, poles[-1][0] - 26, poles[-1][1] + 18, W + 60, 40, 6, hx('#0a0614', 200), 1)
    layer.overlay(wires)
    # 地面细节（角色活动带保持低对比：只放极弱的小杂物）
    def litter(od):
        for _ in range(120):
            x = rng.randrange(W)
            y = rng.randrange(STREET_TOP + 6, H - 4)
            if GROUND_TOP < y < GROUND_BOTTOM:
                a = rng.randint(18, 40)
            else:
                a = rng.randint(40, 90)
            c = rng.choice(['#3a2e52', '#7f9fc8', '#5a4a72', '#c9a53e'])
            rect(od, x, y, rng.randint(1, 3), 1, hx(c, a))
    layer.overlay(litter)
    # 贩卖机/招牌在地面上的彩色反光（覆盖斑）
    def spill(od):
        for (cx, col) in [(1420, '#7fe8ff'), (2860, '#9ff0ff'), (905, '#3df3ff'),
                          (2500, '#ff2f8e'), (300, '#ffd23f')]:
            for yy in range(360, 430):
                t = (yy - 360) / 70.0
                od.line([(cx - 30 - t * 20, yy), (cx + 30 + t * 20, yy)],
                        fill=hx(col, int(10 * (1 - t) ** 1.5)))
    layer.overlay(spill)
    layer.finish(radius=6.0, gain=0.9, tight=1.6, tight_gain=0.5)
    print('  near :', W, H)
    return layer


# ----------------------------------------------------------------------------
# 5. 前景 bg_fg（透明）
# ----------------------------------------------------------------------------
def fg_cables(layer, rng):
    d = layer.d
    # 顶部电线束（横跨世界）
    def wires(od):
        spans = [(0, 44), (620, 52), (1300, 38), (2040, 50), (2760, 40), (3200, 46)]
        for i in range(len(spans) - 1):
            x0, y0 = spans[i]
            x1, y1 = spans[i + 1]
            for k, dy in enumerate([0, 6, 13, 21]):
                catenary(od, x0, y0 + dy, x1, y1 + dy, 16 + k * 4,
                         hx('#05030c', 235), 2 if k < 2 else 1)
        # 斜拉的通讯线
        catenary(od, 120, 70, 900, 240, 20, hx('#05030c', 190), 1)
        catenary(od, 2050, 70, 2900, 250, 20, hx('#05030c', 190), 1)
        # 垂落线头
        for (x, y, ln) in [(560, 58, 40), (1580, 44, 54), (2620, 52, 36)]:
            od.line([(x, y), (x + 4, y + ln)], fill=hx('#05030c', 220), width=1)
            rect(od, x + 2, y + ln, 4, 5, hx('#0a0616'))
    layer.overlay(wires)


def fg_awnings(layer, rng):
    d = layer.d
    # 顶部的近景雨棚边缘（只出现在画面顶部）
    for (x, w) in [(150, 320), (1500, 300), (2680, 340)]:
        rect(d, x, 0, w, 34, hx('#05030c'))
        rect(d, x, 0, w, 10, hx('#0a0616'))
        # 波浪形下沿
        for i in range(0, w, 16):
            d.ellipse([x + i, 30, x + i + 18, 42], fill=hx('#05030c'))
        # 霓虹下沿
        layer.sd.line([(x, 40), (x + w, 40)], fill=hx(CYAN_D, 150), width=1)
        for i in range(0, w, 16):
            layer.sd.arc([x + i, 30, x + i + 18, 42], 0, 180, fill=hx(CYAN_D, 120))
        # 支架
        rect(d, x + 6, 42, 3, 26, hx('#05030c'))
        rect(d, x + w - 9, 42, 3, 22, hx('#05030c'))


def fg_signs(layer, rng):
    d = layer.d
    # 悬挂的小霓虹箭头 + 吊灯
    sx, sy = 820, 44
    rect(d, sx, 0, 2, sy, hx('#05030c'))
    rect(d, sx - 2, sy, 6, 2, hx('#05030c'))
    rect(d, sx - 26, sy + 2, 54, 30, hx('#05030c'))
    rect(d, sx - 24, sy + 4, 50, 26, hx('#0a0714'))
    layer.sd.polygon([(sx - 16, sy + 12), (sx + 12, sy + 12), (sx + 12, sy + 18),
                      (sx + 22, sy + 17), (sx + 12, sy + 22), (sx + 12, sy + 24),
                      (sx - 16, sy + 24)], outline=hx(CYAN))
    layer.sd.line([(sx - 16, sy + 12), (sx + 12, sy + 12)], fill=hx('#ffffff'), width=1)
    # 吊灯
    lx, ly = 1980, 96
    rect(d, lx, 0, 2, ly, hx('#05030c'))
    d.polygon([(lx - 14, ly + 20), (lx + 16, ly + 20), (lx + 10, ly + 6), (lx - 8, ly + 6)],
              fill=hx('#05030c'))
    rect(d, lx - 8, ly + 6, 18, 3, hx('#0a0616'))
    glow_dot(layer, lx + 1, ly + 21, 4, '#ffd23f', '#fff8d8')
    rect(d, lx - 1, ly, 4, 6, hx('#05030c'))


def fg_pipes(layer, rng):
    d = layer.d
    # 左下角蒸汽管（沿画面底边）
    pts = [(0, 512), (240, 512), (260, 524), (760, 524), (780, 508), (1180, 508)]
    line(d, pts, hx('#05030c'), 9)
    for (x, y) in [(240, 512), (760, 524), (1180, 508)]:
        rect(d, x - 4, y - 8, 10, 16, hx('#05030c'))
        rect(d, x - 6, y - 2, 14, 4, hx('#0a0616'))
    # 管上高光
    line(d, [(0, 509), (240, 509)], hx('#1a2438'), 1)
    line(d, [(262, 521), (758, 521)], hx('#1a2438'), 1)
    # 右侧下角管道
    pts2 = [(2100, 540), (2120, 500), (2500, 500), (2520, 540)]
    line(d, pts2, hx('#05030c'), 8)
    line(d, [(2110, 540), (2128, 503), (2495, 503)], hx('#1a2438'), 1)
    # 竖直排水管
    rect(d, 1310, 0, 8, 190, hx('#05030c'))
    rect(d, 1312, 0, 2, 190, hx('#141c2c'))
    for yy in range(30, 190, 40):
        rect(d, 1308, yy, 12, 3, hx('#0a0616'))
    rect(d, 1306, 186, 16, 6, hx('#05030c'))


def fg_junk(layer, rng):
    d = layer.d
    # 底部前景垃圾 / 箱子剪影
    groups = [(300, 560), (1450, 1750), (2480, 2820)]
    for (x0, x1) in groups:
        for _ in range(rng.randint(3, 6)):
            bw = rng.randint(26, 58)
            bh = rng.randint(22, 40)
            bx = rng.randint(x0, x1)
            by = 540 - rng.randint(0, 6)
            rect(d, bx, by - bh, bw, bh, hx('#05030c'))
            rect(d, bx, by - bh, bw, 2, hx('#111a2a'))
            if rng.random() < 0.6:
                rect(d, bx, by - bh, 2, bh, hx('#0f1826'))
            # 箱面细节
            if rng.random() < 0.5:
                rect(d, bx + 4, by - bh + 6, bw - 8, 2, hx('#0b121e'))
                rect(d, bx + 4, by - bh + 12, bw - 14, 2, hx('#0b121e'))
        # 铁链栏杆
        if rng.random() < 0.8:
            fy = 500 + rng.randint(0, 8)
            for xx in range(x0, x1, 22):
                rect(d, xx, fy, 2, 40, hx('#05030c'))
            rect(d, x0, fy, x1 - x0, 2, hx('#05030c'))
            rect(d, x0, fy + 8, x1 - x0, 1, hx('#0c1420'))
    # 小猫剪影（彩蛋）
    cx, cy = 1560, 512
    d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=hx('#05030c'))
    d.ellipse([cx - 7, cy - 16, cx + 3, cy - 6], fill=hx('#05030c'))
    d.polygon([(cx - 7, cy - 14), (cx - 4, cy - 20), (cx - 2, cy - 13)], fill=hx('#05030c'))
    d.polygon([(cx - 2, cy - 14), (cx + 2, cy - 19), (cx + 3, cy - 12)], fill=hx('#05030c'))
    rect(d, cx - 5, cy - 11, 2, 1, hx('#3df3ff', 200))
    rect(d, cx + 1, cy - 11, 2, 1, hx('#3df3ff', 200))
    line(d, [(cx + 6, cy - 2), (cx + 14, cy - 10), (cx + 13, cy - 18)], hx('#05030c'), 2)


def fg_glints(layer, rng):
    """底部湿地面上的高光碎片（少量）。"""
    def paint(od):
        for _ in range(70):
            x = rng.randrange(W)
            y = rng.randrange(496, H - 2)
            ln = rng.randint(2, 7)
            c = rng.choice([CYAN, MAGENTA, '#e8ffff', YELLOW, ORANGE])
            od.line([(x, y), (x + ln, y)], fill=hx(c, rng.randint(20, 70)))
    layer.overlay(paint)


def gen_fg():
    rng = random.Random(424242)
    layer = Layer(W, H)
    fg_cables(layer, rng)
    fg_awnings(layer, rng)
    fg_signs(layer, rng)
    fg_pipes(layer, rng)
    fg_junk(layer, rng)
    fg_glints(layer, rng)
    # 左侧近景铁网门（开场画面左缘的框架）
    d = layer.d
    for xx in range(0, 90, 7):
        rect(d, xx, 160, 2, 380, hx('#05030c'))
    for yy in range(164, 540, 9):
        rect(d, 0, yy, 90, 2, hx('#05030c'))
    rect(d, 88, 150, 6, 390, hx('#05030c'))
    # 右侧边缘框架（世界末端 / Boss 区可能出现在画面右侧时）
    for xx in range(3130, 3200, 7):
        rect(d, xx, 120, 2, 420, hx('#05030c'))
    for yy in range(124, 540, 10):
        rect(d, 3130, yy, 70, 2, hx('#05030c'))
    rect(d, 3122, 110, 6, 430, hx('#05030c'))
    layer.finish(radius=5.0, gain=0.85, tight=1.4, tight_gain=0.4)
    print('  fg   :', W, H)
    return layer


# ----------------------------------------------------------------------------
# 6. 标题 Logo
# ----------------------------------------------------------------------------
# ============================================================================
# 4b. 近景 —— 第二代：更暗的湿沥青 / 人行道 / 道具 / 倒影（覆盖旧版 gen_near）
# ============================================================================
NEAR_STREET_PAL = ['#1b1528', '#181223', '#150f1f', '#120d1b', '#100a18',
                   '#0d0914', '#0a0711', '#080510']
NEAR_WALK_PAL = ['#2b2142', '#281e3d', '#251c38', '#221932', '#1f172d', '#1b1428']


def n2_overlay(layer, fn):
    layer.overlay(fn)


def n2_reflections(layer, rng, specs, y0=364, y1=539):
    """湿沥青上的霓虹拖影：竖向、抖动、低透明，越靠近画面底部越明显。"""
    def paint(od):
        for (cx, color, strength, width, seed) in specs:
            for y in range(y0, y1):
                t = (y - y0) / float(y1 - y0)
                a = int(strength * (8.0 + 64.0 * t * t))
                if a < 2:
                    continue
                if rng.random() < 0.20:
                    continue
                off = int(round(math.sin(y * 0.115 + seed) * (1.0 + t * 2.2) +
                                math.sin(y * 0.031 + seed * 2.3) * (1.5 + t * 2.5)))
                ww = max(1, int(width * (0.6 + 0.7 * t)))
                od.line([(cx + off - ww, y), (cx + off + ww, y)], fill=hx(color, a))
    layer.overlay(paint)


def n2_light_pool2(layer, cx, cy, rx, ry, color, strength=1.0):
    def paint(od):
        for i in range(6):
            t = i / 5.0
            k = (1 - t * 0.72)
            od.ellipse([cx - rx * k, cy - ry * k, cx + rx * k, cy + ry * k],
                       fill=hx(color, int(4 + t * 7 * strength)))
    layer.overlay(paint)


def n2_curb(layer, rng):
    d = layer.d
    # 路缘石顶部高光 + 立面积水阴影
    rect(d, 0, GROUND_TOP, W, 1, hx('#4a3b63'))
    rect(d, 0, GROUND_TOP + 1, W, 1, hx('#5d4a7a'))
    rect(d, 0, GROUND_TOP + 2, W, 4, hx('#181226'))
    rect(d, 0, GROUND_TOP + 6, W, 2, hx('#0b0714'))
    # 路缘石分块接缝 + 局部缺口/坡道
    for xx in range(0, W, 46):
        rect(d, xx, GROUND_TOP + 1, 1, 6, hx('#0d0918'))
        rect(d, xx + 1, GROUND_TOP + 1, 1, 6, hx('#3a2d58'))
    for cx in (640, 1210, 1910, 2720):
        # 下坡道（缺口）
        d.polygon([(cx - 16, GROUND_TOP + 2), (cx + 16, GROUND_TOP + 2),
                   (cx + 22, STREET_TOP), (cx - 22, STREET_TOP)], fill=hx('#231a36'))
        d.polygon([(cx - 16, GROUND_TOP + 2), (cx + 16, GROUND_TOP + 2),
                   (cx + 17, GROUND_TOP + 4), (cx - 17, GROUND_TOP + 4)], fill=hx('#3f315e'))
        rect(d, cx - 18, GROUND_TOP + 2, 36, 2, hx('#150f22'))
    # 雨水冲刷的深色痕迹
    def wash(od):
        for _ in range(40):
            x = rng.randrange(W)
            od.line([(x, GROUND_TOP + 2), (x + rng.randint(-2, 2), GROUND_TOP + 9)],
                    fill=(8, 5, 14, rng.randint(30, 80)))
    layer.overlay(wash)


def n2_sidewalk(layer, rng):
    d = layer.d
    # 砖缝（透视：越近行距越大）
    rows = [331, 335, 340, 346, 352]
    for i, yy in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else GROUND_TOP
        rect(d, 0, yy, W, 1, hx('#161026'))
        rect(d, 0, yy + 1, W, 1, hx('#372b56'))
        step = 16 + i * 9
        off = (i * 13) % step
        for xx in range(-off, W, step):
            rect(d, xx, yy, 1, nxt - yy, hx('#1e1732'))
    # 砖面色差
    def var(od):
        for _ in range(120):
            x = rng.randrange(W)
            y = rng.randrange(332, GROUND_TOP)
            ww = rng.randint(10, 26)
            hh = rng.randint(2, 5)
            od.rectangle([x, y, x + ww, y + hh],
                         fill=hx(rng.choice(['#332748', '#241c39', '#2f2444']), rng.randint(14, 30)))
    layer.overlay(var)
    # 人行道湿反光（店铺灯光在地面）
    def wet(od):
        for (cx, col, rr) in [(300, '#ffd9a0', 60), (470, '#ff9a6a', 46), (1000, '#8fe8ff', 54),
                              (1400, '#cfeeff', 44), (2020, '#ff8ab0', 46), (2500, '#ff9ac8', 52),
                              (2860, '#cfefff', 46), (3080, '#8fe8ff', 40)]:
            for i in range(4):
                k = 1 - i * 0.2
                od.ellipse([cx - rr * k, 338 - 5 * k, cx + rr * k, 338 + 6 * k],
                           fill=hx(col, 7 + i * 3))
    layer.overlay(wet)
    # 墙根阴影
    rect(d, 0, WALK_TOP, W, 3, hx('#0a0714'))
    rect(d, 0, WALK_TOP + 3, W, 2, hx('#1b1329'))
    # 人行道边缘高光
    rect(d, 0, GROUND_TOP - 1, W, 1, hx('#3d2f5c'))


def n2_street_texture(layer, rng):
    d = layer.d
    # 沥青明暗斑
    def asphalt(od):
        for _ in range(150):
            cx = rng.randrange(W)
            cy = rng.randrange(STREET_TOP + 4, H)
            rw = rng.randint(16, 110)
            rh = rng.randint(3, 16)
            c = rng.choice(['#241d38', '#0d0916', '#1b1429', '#07040e'])
            od.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=hx(c, rng.randint(10, 28)))
    layer.overlay(asphalt)
    # 水平透视接缝（断续、低对比）
    def seams(od):
        for yy in [372, 384, 399, 417, 439, 466, 498, 534]:
            x = rng.randrange(-200, 200)
            while x < W:
                seg = rng.randint(90, 340)
                if rng.random() < 0.8:
                    od.line([(x, yy), (x + seg, yy + rng.randint(-1, 1))],
                            fill=(6, 4, 11, rng.randint(22, 46)))
                x += seg + rng.randint(60, 240)
        # 长裂纹
        for _ in range(22):
            x = rng.randrange(W)
            y = rng.randrange(STREET_TOP + 10, H - 6)
            pts = [(x, y)]
            for _k in range(rng.randint(2, 5)):
                x += rng.randint(-34, 34)
                y += rng.randint(1, 8)
                pts.append((x, y))
            od.line(pts, fill=(5, 3, 10, rng.randint(70, 130)), width=1)
    layer.overlay(seams)
    # 沥青颗粒
    def grain(od):
        for _ in range(3200):
            x = rng.randrange(W)
            y = rng.randrange(STREET_TOP, H)
            a = rng.randint(10, 34) if y < GROUND_BOTTOM else rng.randint(20, 52)
            c = rng.choice(['#2a2140', '#0a0714', '#241c38', '#3a2f52', '#1d2430'])
            od.point((x, y), fill=hx(c, a))
    layer.overlay(grain)
    # 大面积湿反光条纹（非常轻，主要在近处）
    def sheen(od):
        for yy in range(STREET_TOP, H, 3):
            t = (yy - STREET_TOP) / float(H - STREET_TOP)
            a = int(3 + 9 * t * t)
            od.line([(0, yy), (W, yy)], fill=(120, 150, 210, a))
    layer.overlay(sheen)
    # 路缘旁的褪色黄线
    def paint(od):
        yy = 369
        x = 0
        while x < W:
            seg = rng.randint(34, 70)
            if rng.random() < 0.72:
                od.line([(x, yy), (x + seg, yy)], fill=(150, 120, 40, rng.randint(26, 54)))
                od.line([(x, yy + 1), (x + seg, yy + 1)], fill=(90, 74, 30, rng.randint(18, 36)))
            x += seg + rng.randint(40, 120)
    layer.overlay(paint)
    # 褪色路面箭头 / 井盖标记
    def arrow(od):
        ay = 414
        for ax in (1150, 2350):
            od.line([(ax, ay), (ax + 26, ay)], fill=(150, 160, 180, 30), width=3)
            od.line([(ax + 16, ay - 7), (ax + 26, ay), (ax + 16, ay + 7)],
                    fill=(150, 160, 180, 30), width=2)
        for (mx, my) in [(1780, 470), (2680, 464)]:
            od.ellipse([mx - 34, my - 13, mx + 34, my + 13], outline=(140, 150, 175, 18))
    layer.overlay(arrow)
    # 沿路缘的排水沟盖板
    def channel(od):
        y = 373
        x = 40
        while x < W:
            ln = rng.randint(90, 220)
            od.line([(x, y), (x + ln, y)], fill=(6, 4, 10, 32))
            for gx in range(x, x + ln, 7):
                od.line([(gx, y - 1), (gx, y + 2)], fill=(24, 18, 36, 26))
            x += ln + rng.randint(160, 420)
    layer.overlay(channel)
    # 大范围霓虹湿光（低频，角色带内极淡）
    def glowspill(od):
        for (cx, col, ww, st) in [(140, CYAN, 50, 1.0), (300, '#ffd23f', 70, 0.9),
                                  (520, MAGENTA, 60, 0.8), (900, CYAN, 70, 1.0),
                                  (1150, ORANGE, 50, 0.7), (1420, '#bfefff', 80, 1.2),
                                  (1800, YELLOW, 50, 0.8), (2150, PURPLE, 60, 0.8),
                                  (2500, MAGENTA, 70, 0.9), (2860, '#bfefff', 80, 1.2),
                                  (3080, CYAN, 60, 0.8)]:
            for y in range(370, 540, 2):
                t = (y - 370) / 170.0
                a = int(8 * st * (0.3 + t * 1.5))
                if a < 1:
                    continue
                w2 = int(ww * (0.5 + t * 0.8))
                od.line([(cx - w2, y), (cx + w2, y)], fill=hx(col, a))
    layer.overlay(glowspill)
    # 透视斜缝（很淡，帮助读地面平面）
    def persp(od):
        for i in range(0, 24):
            x_top = i * 150 - 100
            for xa, xb in [(x_top, x_top - 260), (x_top + 2, x_top - 258)]:
                od.line([(xa, GROUND_TOP + 8), (xb, H)],
                        fill=(90, 100, 140, 12 if xa % 2 else 18))
    layer.overlay(persp)


_RADIAL_MASK = None


def soft_patch(layer, cx, cy, rx, ry, color, alpha, power=1.6):
    """柔和的椭圆光斑（用于湿地面的招牌光晕，避免生硬的矩形光柱）。"""
    global _RADIAL_MASK
    if _RADIAL_MASK is None:
        m = Image.new('L', (64, 64), 0)
        md = ImageDraw.Draw(m)
        for i in range(18):
            t = i / 17.0
            a = int(255 * (1 - t) ** 1.5)
            md.ellipse([32 - 32 * t, 32 - 32 * t, 32 + 32 * t, 32 + 32 * t], fill=a)
        _RADIAL_MASK = m
    w, h = max(2, int(rx * 2)), max(2, int(ry * 2))
    mask = _RADIAL_MASK.resize((w, h), Image.BILINEAR)
    col = Image.new('RGBA', (w, h), hx(color, alpha))
    col.putalpha(ImageChops.multiply(col.getchannel('A'), mask))
    layer.img.alpha_composite(col, (int(cx - rx), int(cy - ry)))


def n2_ground_glow(layer, rng):
    """湿地面上的柔光 / 光池：用软椭圆避免生硬条带。"""
    # 招牌落在地面的光池
    for (cx, cy, rx, ry, col, a) in [
        (300, 398, 84, 26, '#ffd23f', 40), (520, 390, 56, 18, '#ff3b5c', 26),
        (905, 402, 92, 28, '#3df3ff', 40), (1420, 408, 96, 28, '#bfefff', 42),
        (1800, 396, 64, 20, '#ffd23f', 28), (2150, 392, 58, 18, '#7a3cff', 26),
        (2500, 402, 90, 26, '#ff2f8e', 36), (2860, 408, 96, 28, '#bfefff', 42),
        (3080, 398, 76, 24, '#3df3ff', 34)]:
        soft_patch(layer, cx, cy, rx, ry, col, a)
    # 竖向柔光拖影（越靠近画面底部越强）
    for (cx, col, st) in [(150, '#3df3ff', 1.0), (300, '#ffd23f', 1.2), (760, '#ff3b5c', 0.8),
                          (905, '#3df3ff', 1.2), (1150, '#ff8a2a', 0.8), (1420, '#bfefff', 1.4),
                          (1800, '#ffd23f', 0.9), (2150, '#7a3cff', 0.9), (2500, '#ff2f8e', 1.2),
                          (2860, '#bfefff', 1.4), (3080, '#3df3ff', 1.0)]:
        for k in range(4):
            cy = 430 + k * 34
            soft_patch(layer, cx, cy, max(10, 40 - k * 7), 44, col, int(9 * st))
    # 底部大面积暖/冷混合反光
    soft_patch(layer, 480, 528, 260, 30, '#ff8a4a', 12)
    soft_patch(layer, 2300, 530, 240, 28, '#ff2f8e', 10)
    soft_patch(layer, 1600, 530, 300, 30, '#3df3ff', 9)


def n2_puddle(layer, rng, cx, cy, rx, ry, colors, depth=1.0):
    """水洼：暗色水面 + 内部霓虹倒影 + 顶部亮边 + 波纹。"""
    pts = []
    n = 40
    for i in range(n):
        a = 2 * math.pi * i / n
        j = 1.0 + rng.uniform(-0.10, 0.10)
        pts.append((int(cx + math.cos(a) * rx * j), int(cy + math.sin(a) * ry * j)))
    mask = Image.new('L', (layer.w, layer.h), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    ov = Image.new('RGBA', (layer.w, layer.h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.polygon(pts, fill=hx('#0b1220', 190))
    # 水面内的倒影
    for (col, off, hw, st) in colors:
        for y in range(int(cy - ry * 0.9), int(cy + ry * 0.95)):
            t = (y - (cy - ry)) / max(1.0, ry * 2.0)
            if y < cy - ry or y > cy + ry:
                continue
            a = int(64 * depth * st * (1 - abs(t - 0.5) * 1.15))
            if a < 3:
                continue
            if rng.random() < 0.30:
                continue
            ww = max(1, int(hw * (0.5 + 0.5 * (1 - t))))
            xoff = off + int(math.sin(y * 0.35 + off) * 2)
            if rng.random() < 0.35:
                ww = max(1, ww // 2)
            od.line([(cx + xoff - ww, y), (cx + xoff + ww, y)], fill=hx(col, a))
    # 天空反光（水面上部的冷色微光）
    od.ellipse([cx - rx * 0.7, cy - ry * 0.85, cx + rx * 0.7, cy + ry * 0.1],
               fill=(120, 170, 220, int(16 * depth)))
    # 波纹
    for _ in range(rng.randint(2, 4)):
        wy = cy + rng.randint(-int(ry * 0.6), int(ry * 0.6))
        ww = rng.randint(4, max(6, int(rx * 0.5)))
        wx = cx + rng.randint(-int(rx * 0.4), int(rx * 0.4))
        od.line([(wx - ww, wy), (wx + ww, wy)], fill=hx('#9fc6e8', rng.randint(18, 40)))
    a = ov.getchannel('A')
    ov.putalpha(ImageChops.multiply(a, mask))
    layer.img.alpha_composite(ov)
    # 顶部亮边 + 底部暗边
    top_pts = [p for p in pts if p[1] <= cy]
    if len(top_pts) > 2:
        top_pts.sort()
        layer.overlay(lambda od: od.line(top_pts, fill=hx('#7f9fc8', 40)))


def n2_props(layer, rng):
    """人行道上的道具（绘制在角色之后 = 角色会盖住它们，属于「身后」层）。"""
    d = layer.d
    # --- 自动贩卖机（近景光源）---
    def vending(x, base=354):
        w, h = 48, 82
        top = base - h
        rect(d, x - 3, top - 3, w + 6, h + 6, hx('#07040e'))
        rect(d, x, top, w, h, hx('#132430'))
        rect(d, x, top, w, 5, hx('#2a4a5c'))
        rect(d, x, top, 4, h, hx('#2f5a6c'))
        rect(d, x + w - 4, top, 4, h, hx('#0a1420'))
        # 发光面板
        px0, py0, pw, ph = x + 6, top + 9, w - 12, 46
        rect(d, px0 - 2, py0 - 2, pw + 4, ph + 4, hx('#0a1822'))
        rect(d, px0, py0, pw, ph, hx('#6fb8cc'))
        rect(d, px0, py0, pw, 3, hx('#bfe8f2'))
        row_cols = ['#ff3b5c', '#3df3ff', '#ffd23f', '#8dff5a', '#ff8a2a', '#7a3cff']
        for r in range(3):
            for c in range(4):
                cx = px0 + 3 + c * 8
                cy = py0 + 4 + r * 14
                rect(d, cx, cy, 6, 10, hx(rng.choice(row_cols)))
                rect(d, cx, cy, 6, 2, hx('#f0fbff'))
                rect(d, cx, cy + 8, 6, 1, hx('#7fb0c0'))
        # 出货口 / 按钮
        rect(d, x + 7, top + h - 22, w - 14, 13, hx('#0a1420'))
        rect(d, x + 9, top + h - 20, w - 18, 9, hx('#05090f'))
        rect(d, x + (w - 16) // 2, top + h - 8, 16, 4, hx('#2a4a5c'))
        rect(d, x + w - 15, top + 10, 9, 5, hx('#ffd23f'))
        rect(d, x + w - 15, top + 18, 9, 3, hx('#3df3ff'))
        # 顶部小招牌
        rect(d, x + 2, top - 12, w - 4, 9, hx('#0c1a22'))
        m = pixel_mask('DRINK', 1)
        stamp(layer.signs, m, x + (w - m.width) // 2, top - 11, hx('#8fe8ff'), 220)
        # 灯光
        layer.sd.rectangle([px0, py0, px0 + pw - 1, py0 + ph - 1], fill=hx('#8fd8e8'))
        layer.sd.line([(x + 1, top + 4), (x + 1, base - 2)], fill=hx(CYAN, 150),
                      width=1)
        n2_light_pool2(layer, x + w // 2, base + 18, 54, 22, '#7fe8ff', 1.0)
        layer.spills.append((x + w // 2 - 26, base + 6, 52, '#7fe8ff', 0.0))
    vending(1420)
    vending(2860)
    # --- 消防栓 ---
    def hydrant(x, base=354):
        rect(d, x - 9, base - 1, 18, 3, hx('#0d0918'))
        rect(d, x - 6, base - 24, 12, 23, hx('#b8354a'))
        rect(d, x - 6, base - 24, 2, 23, hx('#d8556a'))
        rect(d, x + 4, base - 24, 2, 23, hx('#7a2030'))
        rect(d, x - 9, base - 28, 18, 4, hx('#c23b4e'))
        rect(d, x - 5, base - 34, 10, 6, hx('#d8455a'))
        rect(d, x - 3, base - 37, 6, 3, hx('#e0606e'))
        rect(d, x - 11, base - 20, 4, 7, hx('#8a2836'))
        rect(d, x + 7, base - 20, 4, 7, hx('#8a2836'))
        rect(d, x - 3, base - 18, 6, 4, hx('#2f9aa8'))
        d.rectangle([x - 7, base - 38, x + 6, base - 1], outline=hx('#150b22'))
        n2_light_pool2(layer, x, base + 4, 20, 8, '#c23b4e', 0.5)
    hydrant(520)
    hydrant(2300)
    hydrant(2960)
    # --- 垃圾袋 ---
    def trash(x, base=354):
        for i in range(rng.randint(2, 3)):
            cx = x + rng.randint(-14, 14)
            rw = rng.randint(12, 18)
            rh = rng.randint(10, 17)
            top = base - rh
            d.polygon([(cx - rw, base), (cx - rw + 2, top + 4), (cx - rw // 2, top),
                       (cx + rw // 2, top + 2), (cx + rw, top + 5), (cx + rw - 1, base)],
                      fill=hx('#1b1626'))
            d.line([(cx - rw // 2, top + 3), (cx + rw // 2, top + 4)], fill=hx('#3a3050'))
            d.line([(cx - rw + 3, base - 3), (cx + rw - 4, base - 4)], fill=hx('#0d0a14'))
            if rng.random() < 0.5:
                rect(d, cx - 2, top + 2, 6, 2, hx('#2f2844'))
    trash(380)
    trash(760)
    trash(1150)
    trash(1900)
    trash(2320)
    trash(2900)
    trash(3100)
    # --- 纸箱堆 ---
    def crates(x, base=354):
        bw, bh = 24, 19
        rect(d, x, base - bh, bw, bh, hx('#2a1e2c'))
        rect(d, x, base - bh, bw, 2, hx('#3f2f42'))
        d.line([(x, base - bh), (x + bw - 1, base - 1)], fill=hx('#160f1c'))
        d.line([(x + bw - 1, base - bh), (x, base - 1)], fill=hx('#160f1c'))
        rect(d, x + 2, base - bh - 14, 18, 14, hx('#301f2c'))
        rect(d, x + 2, base - bh - 14, 18, 2, hx('#46303e'))
        rect(d, x + 7, base - bh - 9, 8, 3, hx('#5a4050'))
        m = pixel_mask('拳', 1)
    crates(880)
    crates(1180)
    crates(2400)
    crates(2560)
    # --- 护栏柱 ---
    for bx in (1244, 1258, 2100, 3060):
        rect(d, bx - 4, 334, 8, 20, hx('#221a2a'))
        for k in range(3):
            rect(d, bx - 4, 335 + k * 6, 8, 2, hx('#b8912a'))
        d.ellipse([bx - 5, 331, bx + 5, 338], fill=hx('#221a2a'))
        d.ellipse([bx - 5, 331, bx + 5, 338], outline=hx('#0d0918'))
    # --- 立式灯箱 / A 字招牌 ---
    def aboard(x, base=354):
        rect(d, x, base - 30, 26, 30, hx('#0f0a18'))
        rect(d, x + 2, base - 27, 22, 24, hx('#2a1720'))
        layer.sd.rectangle([x + 2, base - 27, x + 23, base - 3], outline=hx('#ffd23f', 170))
        m = text_mask('酒', 13)
        stamp(layer.signs, m, x + 13 - m.width // 2, base - 26, hx('#ffd23f'))
        rect(d, x - 1, base - 1, 28, 2, hx('#0a0614'))
    aboard(252)
    aboard(960)
    aboard(1960)
    aboard(2190)
    aboard(3040)
    # --- 垃圾桶 / 木箱 ---
    def drum(x, base=354):
        rect(d, x - 10, base - 26, 20, 26, hx('#1b2030'))
        rect(d, x - 10, base - 26, 20, 2, hx('#2c3450'))
        rect(d, x - 10, base - 26, 3, 26, hx('#2c3450'))
        for yy in range(base - 22, base - 2, 6):
            rect(d, x - 9, yy, 18, 1, hx('#131826'))
            rect(d, x - 9, yy + 1, 18, 1, hx('#2c3450'))
        d.ellipse([x - 10, base - 30, x + 10, base - 22], fill=hx('#1b2030'))
        d.ellipse([x - 10, base - 30, x + 10, base - 22], outline=hx('#2c3450'))
    drum(680)
    drum(1540)
    drum(1940)
    drum(2640)
    drum(2800)
    # --- 电线杆 + 电缆 ---
    def pole(x, top_y, rseed):
        rr = random.Random(rseed)
        rect(d, x - 18, 326, 36, 30, hx('#1c1628'))
        rect(d, x - 18, 326, 36, 2, hx('#2f2548'))
        rect(d, x - 15, 352, 30, 4, hx('#0d0918'))
        rect(d, x - 16, 330, 2, 24, hx('#281e3c'))
        # 杆身（带左右轮廓光）
        rect(d, x - 4, top_y, 10, 332 - top_y, hx('#120c1e'))
        rect(d, x - 4, top_y, 2, 332 - top_y, hx('#1f4a5c'))
        rect(d, x + 4, top_y, 2, 332 - top_y, hx('#4a1830'))
        rect(d, x - 2, top_y, 2, 332 - top_y, hx('#241a38'))
        # 横担
        for (ay, aw) in [(top_y + 20, 62), (top_y + 48, 48)]:
            rect(d, x - aw // 2, ay, aw, 2, hx('#0e0918'))
            rect(d, x - aw // 2, ay, aw, 1, hx('#241a38'))
            for ix in range(-aw // 2 + 6, aw // 2 - 4, 16):
                rect(d, x + ix, ay - 5, 2, 5, hx('#3a2e52'))
                rect(d, x + ix, ay - 5, 1, 2, hx('#5a4a78'))
        # 变压器
        ty = top_y + 72
        rect(d, x + 7, ty, 20, 32, hx('#1d1830'))
        rect(d, x + 7, ty, 20, 2, hx('#33284c'))
        rect(d, x + 7, ty + 30, 20, 2, hx('#0b0716'))
        rect(d, x + 10, ty + 4, 1, 24, hx('#2a2140'))
        rect(d, x + 23, ty + 4, 1, 24, hx('#0b0716'))
        for k in range(3):
            rect(d, x + 12 + k * 4, ty - 3, 1, 3, hx('#0b0716'))
        # 杆号牌 + 小广告
        if rr.random() < 0.8:
            sx, sy = x - 28, top_y + 118
            rect(d, sx - 2, sy - 2, 34, 22, hx('#07040e'))
            rect(d, sx, sy, 30, 18, hx('#12202c'))
            layer.sd.rectangle([sx, sy, sx + 29, sy + 17], outline=hx(CYAN_D, 190))
            m = text_mask('电', 11)
            stamp(layer.signs, m, sx + (30 - m.width) // 2, sy + (18 - m.height) // 2, hx(CYAN))
        # 底部反光
        layer.sd.ellipse([x - 14, 348, x + 14, 355], outline=hx('#3df3ff', 45))
        return (x, top_y)
    poles = [pole(150, 30, 501), pole(980, 52, 502), pole(1780, 8, 503),
             pole(2570, 40, 504), pole(3080, 24, 505)]
    # 电缆（3-4 根 + 下垂）
    def wires(od):
        for i in range(len(poles) - 1):
            x0, t0 = poles[i]
            x1, t1 = poles[i + 1]
            for k, dy in enumerate([18, 25, 32, 40]):
                catenary(od, x0 - 31, t0 + dy, x1 - 31, t1 + dy, 10 + k * 4,
                         hx('#0a0614', 225), 1)
            catenary(od, x0 + 31, t0 + 22, x1 + 31, t1 + 22, 20, hx('#0a0614', 170), 1)
        catenary(od, poles[-1][0] - 31, poles[-1][1] + 18, W + 80, 30, 5, hx('#0a0614', 180), 1)
        catenary(od, -80, 40, poles[0][0] - 31, poles[0][1] + 18, 5, hx('#0a0614', 180), 1)
    layer.overlay(wires)
    # --- 排水沟 / 井盖 ---
    for xx in [320, 1040, 1960, 2960]:
        rect(d, xx - 28, 522, 56, 16, hx('#080510'))
        rect(d, xx - 26, 524, 52, 12, hx('#0e0a16'))
        for gx in range(xx - 23, xx + 25, 5):
            rect(d, gx, 526, 2, 8, hx('#241a32'))
        rect(d, xx - 26, 524, 52, 1, hx('#33284a'))
    for (mx, my, rx, ry) in [(1780, 486, 28, 10), (2680, 480, 24, 9), (660, 470, 18, 7)]:
        d.ellipse([mx - rx, my - ry, mx + rx, my + ry], fill=hx('#120d1c'))
        d.ellipse([mx - rx, my - ry, mx + rx, my + ry], outline=hx('#2c2240'))
        d.ellipse([mx - rx + 3, my - ry + 2, mx + rx - 3, my + ry - 2], outline=hx('#201a30'))
        for k in range(-2, 3):
            d.line([(mx - rx + 6, my + k * 3), (mx + rx - 6, my + k * 3)], fill=hx('#1a1426'))
    # --- 井盖蒸汽（极淡）---
    def msteam(od):
        for i in range(26):
            t = i / 25.0
            cy = 480 - t * 70
            rr = int(2 + t * 10)
            a = int(14 * (1 - t) ** 1.4)
            if a > 1:
                od.ellipse([1780 - rr, cy - rr, 1780 + rr, cy + rr], fill=(180, 200, 235, a))
    layer.overlay(msteam)


def gen_near():
    rng = random.Random(20770401)
    arr = np.zeros((H, W, 4), np.float32)
    # 人行道
    banded(arr, WALK_TOP, GROUND_TOP, NEAR_WALK_PAL, 0, W, gamma=0.75)
    # 路缘石
    for yy in range(GROUND_TOP, STREET_TOP):
        t = (yy - GROUND_TOP) / float(STREET_TOP - GROUND_TOP)
        col = mix(rgb3(CURB_TOP), rgb3(CURB_FACE), min(1.0, t * 1.7))
        arr[yy, :, :3] = np.array(col, np.float32)
        arr[yy, :, 3] = 255
    # 街面（更暗，地平线附近略亮）
    banded(arr, STREET_TOP, H, NEAR_STREET_PAL, 0, W, gamma=0.9)
    # 街面上沿受店铺光影响的微弱提亮
    for yy in range(STREET_TOP, STREET_TOP + 26):
        arr[yy, :, :3] += np.array([6, 4, 10], np.float32) * (1 - (yy - STREET_TOP) / 26.0)
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    layer = Layer(W, H, base=base)
    d = layer.d
    n2_sidewalk(layer, rng)
    n2_curb(layer, rng)
    n2_street_texture(layer, rng)
    # 霓虹倒影（低对比，角色活动带克制）
    refl = [
        (118, CYAN, 0.42, 7, 0.4),
        (252, '#ffd23f', 0.40, 9, 1.1),
        (470, ORANGE, 0.36, 8, 1.9),
        (640, MAGENTA, 0.42, 8, 2.6),
        (905, CYAN, 0.40, 10, 3.3),
        (1000, '#8fe8ff', 0.34, 8, 4.1),
        (1230, MAGENTA, 0.32, 7, 4.8),
        (1420, '#bfefff', 0.46, 12, 5.5),
        (1610, '#ff8a2a', 0.30, 7, 6.2),
        (1800, YELLOW, 0.34, 8, 6.9),
        (2020, '#ff7ab0', 0.32, 8, 7.6),
        (2190, YELLOW, 0.28, 6, 8.3),
        (2500, MAGENTA, 0.38, 9, 9.0),
        (2700, ORANGE, 0.26, 7, 9.7),
        (2860, '#9ff0ff', 0.46, 12, 10.4),
        (3060, CYAN, 0.36, 9, 11.1),
    ]
    n2_reflections(layer, rng, refl)
    n2_ground_glow(layer, rng)
    # 底部霓虹光斑
    n2_light_pool2(layer, 1420, 516, 92, 30, '#7fe8ff', 1.2)
    n2_light_pool2(layer, 2860, 520, 92, 30, '#9ff0ff', 1.2)
    n2_light_pool2(layer, 2500, 512, 76, 26, '#ff2f8e', 0.9)
    n2_light_pool2(layer, 300, 386, 40, 14, '#ffd9a0', 0.7)
    n2_light_pool2(layer, 905, 392, 44, 16, '#8fe8ff', 0.7)
    # 水洼（近处大、角色带小且淡）
    n2_puddle(layer, rng, 640, 516, 130, 28, [('#ffd23f', -30, 8, 1.0), (MAGENTA, 22, 10, 0.9),
                                               (CYAN, -72, 6, 0.8)])
    n2_puddle(layer, rng, 1520, 524, 170, 32, [(CYAN, -44, 11, 1.0), ('#e8ffff', 28, 8, 0.9)])
    n2_puddle(layer, rng, 2250, 510, 104, 24, [(MAGENTA, -20, 7, 0.9), (CYAN, 30, 6, 0.8)])
    n2_puddle(layer, rng, 2770, 526, 190, 34, [('#ff9ac8', -54, 12, 1.0), (CYAN, 42, 10, 0.9),
                                               (YELLOW, 0, 6, 0.7)])
    n2_puddle(layer, rng, 3120, 514, 120, 26, [(CYAN, -20, 8, 0.9), (ORANGE, 26, 6, 0.7)])
    n2_puddle(layer, rng, 1000, 430, 44, 10, [(CYAN, 0, 5, 0.5), (MAGENTA, 10, 4, 0.4)], depth=0.5)
    n2_puddle(layer, rng, 2050, 466, 58, 12, [(MAGENTA, -8, 6, 0.5)], depth=0.45)
    n2_puddle(layer, rng, 900, 450, 66, 13, [(CYAN, -10, 7, 0.7), ('#e8ffff', 12, 5, 0.6)], depth=0.55)
    n2_puddle(layer, rng, 1660, 462, 74, 14, [(MAGENTA, -16, 8, 0.6), (YELLOW, 14, 5, 0.5)], depth=0.5)
    n2_puddle(layer, rng, 2210, 444, 56, 11, [(PURPLE, -8, 6, 0.6)], depth=0.5)
    _ = d
    # 道具（含电线杆 / 电缆）
    n2_props(layer, rng)
    # 角色活动带内极少量低对比杂物
    def litter(od):
        for _ in range(70):
            x = rng.randrange(W)
            y = rng.randrange(GROUND_TOP + 4, H - 4)
            if y < GROUND_BOTTOM:
                a = rng.randint(12, 30)
            else:
                a = rng.randint(30, 66)
            c = rng.choice(['#3a2e52', '#7f9fc8', '#5a4a72', '#c9a53e', '#4a3a5c'])
            od.rectangle([x, y, x + rng.randint(0, 2), y], fill=hx(c, a))
    layer.overlay(litter)
    # 底部湿沟高光
    def gutter(od):
        for yy in range(528, H):
            a = int(8 + (yy - 528) * 2.0)
            od.line([(0, yy), (W, yy)], fill=(150, 200, 255, min(40, a)))
    layer.overlay(gutter)
    # 底部压暗（把视线留在角色带，同时增加前景重量）
    def bottom_shade(od):
        for yy in range(H - 22, H):
            t = (yy - (H - 22)) / 22.0
            od.line([(0, yy), (W, yy)], fill=(4, 2, 8, int(30 * t)))
    layer.overlay(bottom_shade)
    layer.finish(radius=6.0, gain=0.95, tight=1.8, tight_gain=0.5)
    print('  near :', W, H)
    return layer


# ============================================================================
# 5b. 前景 —— 第二代：只保留顶部 / 底部的剪影，保证画面中央角色可读
# ============================================================================
def f2_cables(layer, rng):
    """头顶电缆束（只在画面上部，不遮挡角色脸）。"""
    d = layer.d

    def paint(od):
        spans = [(-40, 40), (330, 52), (760, 36), (1180, 48), (1600, 30),
                 (2010, 46), (2440, 34), (2820, 50), (3240, 38)]
        for i in range(len(spans) - 1):
            x0, y0 = spans[i]
            x1, y1 = spans[i + 1]
            for k, dy in enumerate([0, 7, 15, 24]):
                catenary(od, x0, y0 + dy, x1, y1 + dy, 14 + k * 4,
                         (5, 3, 12, 240), 2 if k == 0 else 1)
                # 极暗的轮廓光
                if k == 0:
                    catenary(od, x0, y0 + dy - 1, x1, y1 + dy - 1, 14 + k * 4,
                             (32, 52, 74, 90), 1)
        # 垂落线头 / 小绝缘子
        for (x, y, ln) in [(520, 54, 34), (1500, 40, 46), (2350, 50, 30), (2980, 44, 40)]:
            od.line([(x, y), (x + 3, y + ln)], fill=(5, 3, 12, 230), width=1)
            od.rectangle([x + 1, y + ln, x + 6, y + ln + 5], fill=(8, 5, 16, 255))
            od.point((x + 3, y + ln), fill=(120, 220, 240, 120))
    layer.overlay(paint)


def f2_top_structures(layer, rng):
    """顶部的雨棚 / 招牌背面剪影，只在 y<110 的区域。"""
    d = layer.d
    # 三组雨棚（波浪下沿 + 冷色轮廓光）
    for (x, w, hh) in [(90, 300, 32), (1160, 260, 26), (2100, 320, 34), (2880, 260, 28)]:
        rect(d, x, 0, w, hh, (5, 3, 12, 255))
        rect(d, x, 0, w, 8, (10, 7, 18, 255))
        for i in range(0, w - 4, 14):
            d.ellipse([x + i, hh - 7, x + i + 16, hh + 6], fill=(5, 3, 12, 255))
        # 轮廓光
        layer.sd.line([(x + 1, hh + 3), (x + w - 2, hh + 3)], fill=hx(CYAN_D, 90), width=1)
        # 支撑杆
        rect(d, x + 5, hh + 4, 3, 22, (5, 3, 12, 255))
        rect(d, x + w - 8, hh + 4, 3, 18, (5, 3, 12, 255))
    # 悬挂招牌（小，只在 y<115 区域，不遮挡角色）
    def hanging_board(x, y, w, h, text, color):
        # 吊链
        for cx0 in (x + 4, x + w - 5):
            rect(d, cx0, 0, 1, y - 2, (5, 3, 12, 255))
            d.line([(cx0, y - 4), (cx0 + 2, y - 8)], fill=(8, 6, 16, 255))
        rect(d, x - 2, y - 2, w + 4, h + 4, (5, 3, 12, 255))
        rect(d, x, y, w, h, (12, 9, 20, 255))
        rect(d, x, y, w, 2, (26, 34, 52, 255))
        rect(d, x, y + h - 2, w, 2, (8, 6, 14, 255))
        rect(d, x, y, 2, h, (18, 26, 38, 255))
        rect(d, x + w - 2, y, 2, h, (6, 5, 12, 255))
        layer.sd.rectangle([x, y, x + w - 1, y + h - 1], outline=hx(color, 215), width=2)
        m = text_mask(text, min(16, h - 10), vertical=True)
        stamp(layer.signs, m, x + (w - m.width) // 2, y + (h - m.height) // 2, hx(color))
        stamp(layer.signs, m.filter(ImageFilter.MinFilter(3)),
              x + (w - m.width) // 2, y + (h - m.height) // 2, hx('#ffffff'), 210)
        glow_dot(layer, x + w // 2, y - 4, 1, color, '#ffffff')

    def hanging_lamp(x, y):
        rect(d, x, 0, 2, y, (5, 3, 12, 255))
        rect(d, x - 2, y - 3, 6, 4, (8, 6, 16, 255))
        d.polygon([(x - 14, y + 20), (x + 16, y + 20), (x + 9, y + 4), (x - 7, y + 4)],
                  fill=(5, 3, 12, 255))
        rect(d, x - 7, y + 3, 16, 3, (12, 9, 20, 255))
        rect(d, x - 8, y + 19, 18, 3, (14, 11, 22, 255))
        n2_light_pool2(layer, x + 1, y + 26, 34, 14, '#ffd23f', 0.9)
        glow_dot(layer, x + 1, y + 22, 3, '#ffd23f', '#fff8d8')

    hanging_board(760, 34, 34, 56, '拳', CYAN)
    hanging_lamp(1560, 26)
    hanging_board(2420, 40, 32, 50, '酒', MAGENTA)
    hanging_board(3020, 30, 36, 54, '電', CYAN)


def f2_bottom_band(layer, rng):
    """画面底部的前景剪影：木箱 / 铁桶 / 铁网 / 蒸汽管 / 猫。"""
    d = layer.d
    # 横贯底部的蒸汽管（分段，避免太整齐）
    def pipe(od):
        pts = [(-20, 536), (300, 536), (320, 524), (740, 524), (760, 537),
               (1060, 537), (1080, 528), (1500, 528)]
        od.line([(int(x), int(y)) for x, y in pts], fill=(5, 3, 12, 255), width=9)
        od.line([(int(x), int(y - 3)) for x, y in pts], fill=(24, 36, 52, 160), width=1)
        for (x, y) in [(320, 524), (760, 537), (1080, 528)]:
            od.rectangle([x - 5, y - 9, x + 5, y + 7], fill=(5, 3, 12, 255))
            od.rectangle([x - 7, y - 3, x + 7, y + 1], fill=(12, 9, 20, 255))
        # 阀轮
        od.ellipse([472, 512, 490, 530], outline=(5, 3, 12, 255), width=2)
        od.line([(481, 512), (481, 530)], fill=(5, 3, 12, 255))
        od.line([(472, 521), (490, 521)], fill=(5, 3, 12, 255))
    layer.overlay(pipe)

    def junk_cluster(x0, x1, force_fence=False):
        # 铁网栏杆（限制在画面最底部，避免遮挡角色脚部 y<=502）
        if force_fence or rng.random() < 0.7:
            fy = 516 + rng.randint(0, 6)
            for xx in range(x0, x1, 18):
                rect(d, xx, fy, 2, 540 - fy, (5, 3, 12, 255))
            rect(d, x0, fy, x1 - x0, 2, (5, 3, 12, 255))
            rect(d, x0, fy + 10, x1 - x0, 1, (14, 22, 34, 220))
            for xx in range(x0 + 4, x1, 12):
                for yy in range(fy + 4, 540, 10):
                    d.point((xx, yy), fill=(8, 14, 22, 200))
        # 箱子 / 桶（只露出底部一截）
        for _ in range(rng.randint(2, 4)):
            bw = rng.randint(28, 54)
            bh = rng.randint(12, 24)
            bx = rng.randint(x0, max(x0, x1 - bw))
            by = 540 + rng.randint(-3, 3)
            rect(d, bx, by - bh, bw, bh, (5, 3, 12, 255))
            rect(d, bx, by - bh, bw, 2, (20, 30, 44, 255))
            rect(d, bx, by - bh, 2, bh, (12, 18, 28, 255))
            if rng.random() < 0.6:
                rect(d, bx + 4, by - bh + 5, bw - 8, 1, (16, 24, 36, 255))
                rect(d, bx + 4, by - bh + 10, bw - 14, 1, (12, 18, 28, 255))
        # 铁桶
        if rng.random() < 0.6:
            bx = rng.randint(x0, x1 - 24)
            bh = rng.randint(18, 26)
            rect(d, bx, 540 - bh, 24, bh, (5, 3, 12, 255))
            d.ellipse([bx, 540 - bh - 7, bx + 24, 540 - bh + 3], fill=(5, 3, 12, 255))
            rect(d, bx, 540 - bh + 8, 24, 2, (22, 32, 46, 255))
            rect(d, bx, 540 - bh + 15, 24, 2, (18, 26, 38, 255))
    junk_cluster(180, 640)
    junk_cluster(1180, 1640, force_fence=True)
    junk_cluster(2050, 2520)
    junk_cluster(2860, 3180)
    # 底部水洼镜面高光碎片
    def glints(od):
        for _ in range(90):
            x = rng.randrange(W)
            y = rng.randrange(512, H - 2)
            ln = rng.randint(2, 8)
            c = rng.choice([CYAN, MAGENTA, '#e8ffff', YELLOW, ORANGE])
            od.line([(x, y), (x + ln, y)], fill=hx(c, rng.randint(16, 56)))
        for _ in range(30):
            x = rng.randrange(W)
            y = rng.randrange(508, H - 2)
            od.line([(x, y), (x + rng.randint(1, 4), y)], fill=hx('#7f9fc8', rng.randint(14, 40)))
    layer.overlay(glints)
    # 小猫彩蛋（贴在画面底边）
    def cat(cx, cy):
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=(5, 3, 12, 255))
        d.ellipse([cx - 8, cy - 18, cx + 4, cy - 6], fill=(5, 3, 12, 255))
        d.polygon([(cx - 8, cy - 15), (cx - 5, cy - 22), (cx - 2, cy - 14)], fill=(5, 3, 12, 255))
        d.polygon([(cx - 3, cy - 15), (cx + 2, cy - 21), (cx + 3, cy - 13)], fill=(5, 3, 12, 255))
        rect(d, cx - 6, cy - 12, 2, 1, (61, 243, 255, 255))
        rect(d, cx + 1, cy - 12, 2, 1, (61, 243, 255, 255))
        d.line([(cx + 7, cy - 2), (cx + 16, cy - 11), (cx + 15, cy - 20)],
               fill=(5, 3, 12, 255), width=2)
        d.line([(cx + 16, cy - 11), (cx + 20, cy - 13)], fill=(5, 3, 12, 255), width=1)
    cat(1524, 524)


def gen_fg():
    rng = random.Random(424242)
    layer = Layer(W, H)
    f2_cables(layer, rng)
    f2_top_structures(layer, rng)
    f2_bottom_band(layer, rng)
    layer.finish(radius=5.0, gain=0.9, tight=1.5, tight_gain=0.4)
    print('  fg   :', W, H)
    return layer


def logo_neon_outline(canvas, mask, color, width=2, alpha=210):
    pass


def gen_logo():
    LW, LH = 760, 240
    img = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    glow = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    d = ImageDraw.Draw(img)

    # ---- 背景霓虹速度条 / 装饰 ----
    deco = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    # 两侧斜切速度条
    for i, col in enumerate([CYAN_D, MAGENTA_D, PURPLE]):
        y = 58 + i * 14
        dd.polygon([(40, y), (150, y - 6), (150, y - 2), (40, y + 4)], fill=hx(col, 80))
        dd.polygon([(720, y), (610, y - 6), (610, y - 2), (720, y + 4)], fill=hx(col, 80))
    # 标题背后的暗色斜切底板（提高可读性）
    dd.polygon([(96, 34), (664, 34), (696, 78), (696, 150), (664, 176), (96, 176), (64, 150), (64, 78)],
               fill=hx('#0a0614', 110))
    dd.line([(96, 34), (664, 34)], fill=hx(CYAN_D, 90), width=1)
    dd.line([(96, 176), (664, 176)], fill=hx(MAGENTA_D, 90), width=1)
    img.alpha_composite(deco)

    # ---- 中文标题「霓虹拳魂」----
    title = '霓虹拳魂'
    px_h = 108
    block = 3
    masks = [char_mask(ch, px_h, block) for ch in title]
    masks = [m for m in masks if m is not None]
    gap = 7
    total_w = sum(m.width for m in masks) + gap * (len(masks) - 1)
    x0 = (LW - total_w) // 2
    # 字符错落（拱形）与独立颜色
    offs = [2, -6, -6, 2]
    ybase = 30
    # 1) 外发光（品红 + 青）
    glow_layer = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    gdr = ImageDraw.Draw(glow_layer)
    xx = x0
    for i, m in enumerate(masks):
        yy = ybase + offs[i]
        # 品红底辉光
        inflated = m.filter(ImageFilter.MaxFilter(5))
        stamp(glow_layer, inflated, xx - 4, yy - 4, hx(MAGENTA, 210))
        inflated2 = m.filter(ImageFilter.MaxFilter(9))
        stamp(glow_layer, inflated2, xx - 6, yy - 6, hx(MAGENTA, 90))
        # 青侧光
        stamp(glow_layer, inflated, xx - 5, yy - 5, hx(CYAN, 70))
        xx += m.width + gap
    blurred = glow_layer.filter(ImageFilter.GaussianBlur(6))
    img.alpha_composite(blurred)
    img.alpha_composite(glow_layer)

    # 2) 硬边：深色描边 + 铬金属填充 + 霓虹勾边
    xx = x0
    for i, m in enumerate(masks):
        yy = ybase + offs[i]
        mw, mh = m.size
        # 深色粗描边
        for off in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
            stamp(img, m, xx + off[0], yy + off[1], hx('#100818'))
        # 铬渐变（黄金 / 琥珀，配合品红描边）
        chrome = [
            (0.00, '#fff6d0'), (0.10, '#ffe9a0'), (0.22, '#ffd23f'),
            (0.36, '#ffb02e'), (0.44, '#b84a1e'), (0.50, '#5a1a24'),
            (0.56, '#ff8a2a'), (0.68, '#ffd23f'), (0.80, '#ffe98a'),
            (0.90, '#ffd23f'), (1.00, '#a86a12'),
        ]
        for row in range(mh):
            t = row / max(1, mh - 1)
            col = chrome[0][1]
            for (pt, cc) in chrome:
                if t >= pt:
                    col = cc
            row_mask = m.crop((0, row, mw, row + 1))
            stamp(img, row_mask, xx, yy + row, hx(col))
        # 斜向高光（左上）
        hl = Image.new('L', (mw, mh), 0)
        hl = m.copy()
        # 只保留左上游离边缘的 1 格
        er = m.filter(ImageFilter.MinFilter(3))
        edge = ImageChops.subtract(m, er)
        img.paste(Image.new('RGBA', (mw, mh), hx('#fffbe8', 190)), (xx, yy),
                  ImageChops.multiply(edge, _diag_mask(mw, mh, True)))
        # 底部霓虹边（品红）
        img.paste(Image.new('RGBA', (mw, mh), hx(MAGENTA, 200)), (xx, yy),
                  ImageChops.multiply(edge, _diag_mask(mw, mh, False)))
        xx += mw + gap

    # ---- 英文副标题「NEON FIST SOUL」----
    sub = 'NEON FIST SOUL'
    scale = 5
    pm = pixel_mask(sub, scale, gap=2)
    # 字距：用额外间隔重排
    letters = [pixel_mask(ch, scale, gap=1) for ch in sub]
    sp = 7
    total = sum(l.width for l in letters) + sp * (len(letters) - 1)
    sx = (LW - total) // 2
    sy = 152
    # 阴影 / 描边
    for off in [(2, 3), (-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
        xx = sx
        for m in letters:
            stamp(img, m, xx + off[0], sy + off[1], hx('#100818'))
            xx += m.width + sp
    # 品红底边 + 青色填充渐变
    xx = sx
    for m in letters:
        mw, mh = m.size
        for row in range(mh):
            t = row / max(1, mh - 1)
            if t < 0.18:
                cc = '#eaffff'
            elif t < 0.5:
                cc = CYAN
            elif t < 0.78:
                cc = '#24c4e8'
            else:
                cc = '#156a9a'
            stamp(img, m.crop((0, row, mw, row + 1)), xx, sy + row, hx(cc))
        # 顶部亮线
        stamp(img, m.crop((0, 0, mw, 2)), xx, sy, hx('#ffffff', 220))
        xx += mw + sp
    # 副标题外辉光（青色）
    sub_glow = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    xx = sx
    for m in letters:
        stamp(sub_glow, m.filter(ImageFilter.MaxFilter(3)), xx - 2, sy - 2, hx(CYAN, 120))
        xx += m.width + sp
    img.alpha_composite(sub_glow.filter(ImageFilter.GaussianBlur(4)))
    img.alpha_composite(sub_glow)

    # ---- 底部装饰：霓虹双线 + 菱形 ----
    dy = 196
    d.line([(188, dy), (572, dy)], fill=hx('#100818'), width=2)
    d.line([(200, dy - 1), (560, dy - 1)], fill=hx(CYAN, 210), width=1)
    d.line([(214, dy + 2), (546, dy + 2)], fill=hx(MAGENTA, 150), width=1)
    for cx in (376, 196, 556):
        d.polygon([(cx, dy - 5), (cx + 5, dy), (cx, dy + 5), (cx - 5, dy)], fill=hx('#100818'))
        d.polygon([(cx, dy - 3), (cx + 3, dy), (cx, dy + 3), (cx - 3, dy)], fill=hx(YELLOW))
        gd.polygon([(cx, dy - 3), (cx + 3, dy), (cx, dy + 3), (cx - 3, dy)], fill=hx(YELLOW, 200))
    # 两侧箭头装饰
    for (ax, sign) in [(150, 1), (610, -1)]:
        d.polygon([(ax, dy - 14), (ax + sign * 26, dy), (ax, dy + 14), (ax + sign * 10, dy)],
                  fill=hx('#0a0614', 200))
        d.line([(ax, dy - 14), (ax + sign * 26, dy), (ax, dy + 14)], fill=hx(CYAN, 170), width=1)
    # 顶部小星芒
    for (sx_, sy_, r, cc) in [(120, 22, 7, YELLOW), (646, 30, 5, CYAN), (90, 130, 4, MAGENTA),
                              (676, 122, 6, YELLOW)]:
        d.line([(sx_ - r, sy_), (sx_ + r, sy_)], fill=hx(cc, 220), width=1)
        d.line([(sx_, sy_ - r), (sx_, sy_ + r)], fill=hx(cc, 220), width=1)
        gd.line([(sx_ - r, sy_), (sx_ + r, sy_)], fill=hx(cc, 160), width=1)
        gd.line([(sx_, sy_ - r), (sx_, sy_ + r)], fill=hx(cc, 160), width=1)
    # 整体辉光合成
    big = glow.filter(ImageFilter.GaussianBlur(9))
    img.alpha_composite(big)
    img.alpha_composite(glow)
    img.save(os.path.join(UI_DIR, 'logo.png'), optimize=True)
    print('  logo :', LW, LH)
    return img


def _diag_mask(w, h, upper=True):
    m = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(m)
    for y in range(h):
        for x in range(w):
            v = (x + y) if upper else (x - y)
            if (upper and y < h * 0.4) or ((not upper) and y > h * 0.62):
                d.point((x, y), fill=255)
    return m


# ----------------------------------------------------------------------------
# 7. manifest / 预览
# ----------------------------------------------------------------------------
def gen_logo():
    """标题 Logo v2：黄金铬字 + 品红霓虹勾边 + 青色轮廓光 + 像素英文副标题。"""
    LW, LH = 760, 240
    img = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    accent = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    ad = ImageDraw.Draw(accent)
    # ---- 背景装饰：斜切速度条 + 星芒（不挡字） ----
    for i, col in enumerate([CYAN_D, MAGENTA_D, PURPLE, CYAN_D]):
        y = 64 + i * 12
        ad.polygon([(26, y), (128, y - 6), (128, y - 2), (26, y + 4)], fill=hx(col, 90))
        ad.polygon([(734, y), (632, y - 6), (632, y - 2), (734, y + 4)], fill=hx(col, 90))
    img.alpha_composite(accent)
    glow = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)

    # ---- 中文标题「霓虹拳魂」 ----
    title = '霓虹拳魂'
    px_h = 112
    block = 3
    masks = [m for m in (char_mask(ch, px_h, block) for ch in title) if m is not None]
    gap = 11
    total_w = sum(m.width for m in masks) + gap * (len(masks) - 1)
    x0 = (LW - total_w) // 2
    offs = [3, -5, -5, 3]
    ybase = 24
    # 1) 深色投影（让字在复杂背景上仍然清晰）
    for i, m in enumerate(masks):
        xx = x0 + sum(mm.width + gap for mm in masks[:i])
        yy = ybase + offs[i]
        stamp(img, m, xx + 6, yy + 8, hx('#0b0410', 200))
    # 2) 霓虹外辉光：品红外圈 + 青内侧
    g1 = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    g2 = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    for i, m in enumerate(masks):
        xx = x0 + sum(mm.width + gap for mm in masks[:i])
        yy = ybase + offs[i]
        stamp(g1, m.filter(ImageFilter.MaxFilter(7)), xx - 4, yy - 4, hx(MAGENTA, 235))
        stamp(g2, m.filter(ImageFilter.MaxFilter(5)), xx - 3, yy - 3, hx(CYAN, 120))
    img.alpha_composite(g1.filter(ImageFilter.GaussianBlur(9)))
    img.alpha_composite(g1.filter(ImageFilter.GaussianBlur(3)))
    img.alpha_composite(g2.filter(ImageFilter.GaussianBlur(5)))
    # 3) 硬边深色描边 + 铬金渐变 + 轮廓光
    for i, m in enumerate(masks):
        xx = x0 + sum(mm.width + gap for mm in masks[:i])
        yy = ybase + offs[i]
        mw, mh = m.size
        # 深色描边（3 个像素块厚，硬边）
        stamp(img, m.filter(ImageFilter.MaxFilter(7)), xx - 2, yy - 2, hx('#0d0616'))
        # 铬金渐变
        chrome = [
            (0.00, '#ffe9a0'), (0.06, '#ffd23f'), (0.16, '#ffb02e'),
            (0.30, '#ff8a2a'), (0.40, '#c2451a'), (0.47, '#5a1418'),
            (0.53, '#9a2a12'), (0.62, '#ff8a2a'), (0.74, '#ffd23f'),
            (0.85, '#ffe9a0'), (1.00, '#ffb02e'),
        ]
        for row in range(mh):
            t = row / max(1, mh - 1)
            col = chrome[0][1]
            for (pt, cc) in chrome:
                if t >= pt:
                    col = cc
            stamp(img, m.crop((0, row, mw, row + 1)), xx, yy + row, hx(col))
        # 上沿高光 / 下沿暗边
        top_mask = m.crop((0, 0, mw, max(2, mh // 22)))
        stamp(img, top_mask, xx, yy, hx('#fff4c8'))
        bot_mask = m.crop((0, mh - max(2, mh // 12), mw, mh))
        stamp(img, bot_mask, xx, yy + mh - max(2, mh // 12), hx('#4a1a06'))
        # 边缘轮廓光：左上青 / 右下品红
        er = m.filter(ImageFilter.MinFilter(3))
        edge = ImageChops.subtract(m, er)
        diag_ul = _diag_mask(mw, mh, True)
        diag_br = _diag_mask(mw, mh, False)
        img.paste(Image.new('RGBA', (mw, mh), hx(CYAN)), (xx, yy),
                  ImageChops.multiply(edge, diag_ul))
        img.paste(Image.new('RGBA', (mw, mh), hx(MAGENTA)), (xx, yy),
                  ImageChops.multiply(edge, diag_br))

    # ---- 英文副标题「NEON FIST SOUL」 ----
    sub = 'NEON FIST SOUL'
    scale = 5
    sp = 8
    letters = [pixel_mask(ch, scale, gap=1) for ch in sub]
    total = sum(l.width for l in letters) + sp * (len(letters) - 1)
    sx = (LW - total) // 2
    sy = 150
    # 品红投影
    xx = sx
    for m in letters:
        stamp(img, m, xx + 4, sy + 5, hx('#8a0f44', 170))
        xx += m.width + sp
    # 深色描边（十字扩展）
    for off in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
        xx = sx
        for m in letters:
            stamp(img, m, xx + off[0], sy + off[1], hx('#0d0616'))
            xx += m.width + sp
    # 青白渐变填充
    xx = sx
    for m in letters:
        mw, mh = m.size
        bands = [(0.0, '#f2ffff'), (0.16, '#d8fbff'), (0.28, '#5df0ff'),
                 (0.62, '#22c8e6'), (0.82, '#1a8ca8'), (1.0, '#0d5568')]
        for row in range(mh):
            t = row / max(1, mh - 1)
            col = bands[0][1]
            for (pt, cc) in bands:
                if t >= pt:
                    col = cc
            stamp(img, m.crop((0, row, mw, row + 1)), xx, sy + row, hx(col))
        stamp(img, m.crop((0, 0, mw, 2)), xx, sy, hx('#ffffff', 240))
        xx += m.width + sp
    # 青色外辉光
    sub_glow = Image.new('RGBA', (LW, LH), (0, 0, 0, 0))
    xx = sx
    for m in letters:
        stamp(sub_glow, m.filter(ImageFilter.MaxFilter(5)), xx - 2, sy - 2, hx(CYAN, 120))
        xx += m.width + sp
    img.alpha_composite(sub_glow.filter(ImageFilter.GaussianBlur(6)))
    img.alpha_composite(sub_glow.filter(ImageFilter.GaussianBlur(2)))

    # ---- 底部装饰：霓虹双线 + 菱形 + 两侧箭头 ----
    dy = 198
    ad = ImageDraw.Draw(img)
    ad.line([(176, dy), (584, dy)], fill=hx('#0d0616'), width=2)
    ad.line([(192, dy - 1), (568, dy - 1)], fill=hx(CYAN, 220), width=1)
    ad.line([(206, dy + 2), (554, dy + 2)], fill=hx(MAGENTA, 170), width=1)
    for cx in (380, 200, 560):
        ad.polygon([(cx, dy - 6), (cx + 6, dy), (cx, dy + 6), (cx - 6, dy)], fill=hx('#0d0616'))
        ad.polygon([(cx, dy - 3), (cx + 3, dy), (cx, dy + 3), (cx - 3, dy)], fill=hx(YELLOW))
        gd.polygon([(cx, dy - 4), (cx + 4, dy), (cx, dy + 4), (cx - 4, dy)], fill=hx(YELLOW, 200))
    # 两侧向内箭头（霓虹三点）
    for (ax, sign) in [(138, 1), (622, -1)]:
        for k in range(3):
            x1 = ax + sign * (k * 8)
            y1 = 104 - k * 8
            ad.line([(x1, y1 - 8), (x1 + sign * 12, y1), (x1, y1 + 8)], fill=hx(CYAN, 200), width=1)
            gd.line([(x1, y1 - 8), (x1 + sign * 12, y1), (x1, y1 + 8)], fill=hx(CYAN, 140), width=1)
    # 星芒
    for (sx_, sy_, r, cc) in [(96, 30, 8, YELLOW), (662, 26, 6, CYAN), (66, 140, 5, MAGENTA),
                              (694, 132, 7, YELLOW), (700, 56, 4, MAGENTA), (60, 64, 4, CYAN)]:
        ad.line([(sx_ - r, sy_), (sx_ + r, sy_)], fill=hx(cc, 230), width=1)
        ad.line([(sx_, sy_ - r), (sx_, sy_ + r)], fill=hx(cc, 230), width=1)
        gd.line([(sx_ - r, sy_), (sx_ + r, sy_)], fill=hx(cc, 160), width=1)
        gd.line([(sx_, sy_ - r), (sx_, sy_ + r)], fill=hx(cc, 160), width=1)
    # 整体辉光合成
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
    img.alpha_composite(glow)
    img.save(os.path.join(UI_DIR, 'logo.png'), optimize=True)
    print('  logo :', LW, LH)
    return img


def gen_logo_old():
    pass


def write_manifest():
    os.makedirs(WORLD_DIR, exist_ok=True)
    content = """/* 霓虹拳魂 NEON FIST SOUL — 场景 / UI 资源清单
 * 由 tools/gen_world.py 生成，可安全手工微调（不会自动覆盖时请重跑 gen_world.py）。
 * 视差系数：far 0.12(横向平铺) / mid 0.45 / near 1.0 / fg 1.12
 */
window.NF = window.NF || {};
(function () {
  if (!NF.registerWorld) {
    console.error('[NEON] NF.registerWorld 未定义：请检查脚本加载顺序（assets.js 必须在 world/manifest.js 之前）');
    return;
  }
  NF.registerWorld({
    stageW: 3200,
    layers: {
      far:  { file: 'world/bg_far.png',  factor: 0.12, y: 0, tile: true },
      mid:  { file: 'world/bg_mid.png',  factor: 0.45, y: 0 },
      near: { file: 'world/bg_near.png', factor: 1.0,  y: 0 },
      fg:   { file: 'world/bg_fg.png',   factor: 1.12, y: 0, alpha: 1 }
    },
    ui: {
      logo: 'ui/logo.png'
    }
  });
})();
"""
    path = os.path.join(WORLD_DIR, 'manifest.js')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print('  manifest:', path)


def load_layer(name):
    p = os.path.join(WORLD_DIR, 'bg_%s.png' % name)
    if not os.path.exists(p):
        return None
    return Image.open(p).convert('RGBA')


def blit(out, im, dx, dy=0):
    tmp = Image.new('RGBA', out.size, (0, 0, 0, 0))
    tmp.paste(im, (int(dx), int(dy)))
    out.alpha_composite(tmp)


def tile_start(x, width, cam):
    start = x % width
    if start > 0:
        start -= width
    while start > cam:
        start -= width
    return start


def compose_view(cam, layers, chars=False):
    out = Image.new('RGBA', (VIEW_W, VIEW_H), (6, 4, 13, 255))
    order = [('far', 0.12, True), ('mid', 0.45, False), ('near', 1.0, False)]
    for name, factor, tile in order:
        im = layers.get(name)
        if im is None:
            continue
        x = int(round(cam * (1 - factor)))
        if tile:
            start = tile_start(x, im.width, cam)
            xx = start
            while xx < cam + VIEW_W + im.width:
                blit(out, im, xx - cam, 0)
                xx += im.width
        else:
            blit(out, im, x - cam, 0)
    if chars:
        draw_preview_chars(out, cam)
    fg = layers.get('fg')
    if fg is not None:
        x = int(round(cam * (1 - 1.12)))
        blit(out, fg, x - cam, 0)
    return out


def _hero_frame0():
    """读取主角 idle 第一帧用于预览（存在则用真实美术判断场景比例/可读性）。"""
    p = os.path.join(ROOT, 'assets', 'chars', 'hero', 'idle.png')
    if not os.path.exists(p):
        return None
    try:
        im = Image.open(p).convert('RGBA')
        fw = im.height
        return im.crop((0, 0, fw, fw))
    except Exception:
        return None


def draw_preview_chars(out, cam):
    """预览用角色：优先贴真实 hero idle 帧，缺图时画比例正确的剪影。"""
    d = ImageDraw.Draw(out)
    hero = _hero_frame0()

    def place_hero(wx, foot_y):
        sx = int(wx - cam)
        if hero is not None:
            blit(out, hero, sx - 120, foot_y - 222)
        else:
            dummy(sx, foot_y, 186)

    def dummy(sx, foot_y, height, boss=False):
        col = (30, 28, 50, 255) if not boss else (40, 26, 46, 255)
        head_r = int(height * 0.075)
        head_y = foot_y - height + head_r
        neck = head_y + head_r
        shoulder = int(height * 0.17)
        hip_y = foot_y - int(height * 0.42)
        d.ellipse([sx - height * 0.2, foot_y - 5, sx + height * 0.2, foot_y + 5], fill=(0, 0, 0, 80))
        # 腿 + 靴子
        for sgn in (-1, 1):
            lx = sx + sgn * int(height * 0.08)
            d.polygon([(lx - int(height * 0.06), hip_y), (lx + int(height * 0.06), hip_y),
                       (lx + int(height * 0.05), foot_y - 4), (lx - int(height * 0.045), foot_y - 4)], fill=col)
            d.rectangle([lx - int(height * 0.055), foot_y - 6, lx + int(height * 0.055), foot_y],
                        fill=(18, 16, 30, 255))
        # 躯干（肩宽腰窄）
        d.polygon([(sx - shoulder, neck), (sx + shoulder, neck),
                   (sx + int(height * 0.13), hip_y), (sx - int(height * 0.13), hip_y)], fill=col)
        # 手臂 + 拳头
        for sgn in (-1, 1):
            ax0 = sx + sgn * shoulder
            ax1 = sx + sgn * int(height * 0.22)
            d.polygon([(ax0, neck + 8), (ax1, neck + int(height * 0.09)),
                       (ax1 - sgn * 3, hip_y - 6), (ax0 - sgn * 6, hip_y - 10)], fill=col)
            d.ellipse([ax1 - 6, hip_y - 20, ax1 + 6, hip_y - 8], fill=(30, 28, 50, 255))
        # 头 + 头发
        d.ellipse([sx - head_r, head_y - head_r, sx + head_r, head_y + head_r], fill=col)
        d.rectangle([sx - head_r, head_y - head_r - 2, sx + head_r, head_y - head_r + 4], fill=(20, 18, 34, 255))
        # 脸部
        d.rectangle([sx - int(head_r * 0.6), head_y - int(head_r * 0.35),
                     sx + int(head_r * 0.7), head_y + int(head_r * 0.2)],
                    fill=(232, 186, 146, 255))
        # 轮廓光（短边，而不是贯穿全身的长线）
        d.line([(sx - shoulder, neck + 2), (sx - int(height * 0.13), hip_y)], fill=(61, 243, 255, 170), width=2)
        d.line([(sx + shoulder, neck + 2), (sx + int(height * 0.13), hip_y)], fill=(255, 47, 142, 170), width=2)
        d.arc([sx - head_r, head_y - head_r, sx + head_r, head_y + head_r], 110, 250,
              fill=(61, 243, 255, 190), width=2)
        d.arc([sx - head_r, head_y - head_r, sx + head_r, head_y + head_r], -70, 70,
              fill=(255, 47, 142, 190), width=2)

    # 主角（近处）+ 敌人剪影（纵深不同位置）
    place_hero(300, 470)
    place_hero(430, 410)
    dummy(600 - cam, 400, 176)
    dummy(690 - cam, 356, 176)
    dummy(760 - cam, 470, 216)
    dummy(830 - cam, 356, 250, boss=True)


def save_contact_sheet(layers):
    scale = 0.22
    rows = []
    for name in ['far', 'mid', 'near', 'fg']:
        im = layers.get(name)
        if im is None:
            continue
        rows.append((name, im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                                     Image.NEAREST)))
    pad = 12
    label_h = 18
    sheet_w = max(r[1].width for r in rows) + pad * 2
    sheet_h = sum(r[1].height + label_h + pad for r in rows) + pad
    sheet = Image.new('RGB', (sheet_w, sheet_h), (18, 14, 28))
    # 棋盘格底（显示透明）
    chk = Image.new('RGB', (sheet_w, sheet_h), (30, 26, 44))
    cd = ImageDraw.Draw(chk)
    for y in range(0, sheet_h, 16):
        for x in range(0, sheet_w, 16):
            if ((x // 16) + (y // 16)) % 2 == 0:
                cd.rectangle([x, y, x + 15, y + 15], fill=(22, 18, 34))
    sheet.paste(chk, (0, 0))
    font = ImageFont.load_default()
    yy = pad
    sd = ImageDraw.Draw(sheet)
    for name, im in rows:
        sd.text((pad, yy), '%s.png  %dx%d' % (name, im.width, im.height), fill=(140, 230, 255), font=font)
        yy += label_h
        sheet.paste(im, (pad, yy))
        yy += im.height + pad
    path = os.path.join(SHOTS_DIR, 'world_layers.png')
    sheet.save(path)
    print('  sheet:', path)


def save_seam_check(layers):
    far = layers.get('far')
    if far is None:
        return
    tiled = Image.new('RGBA', (far.width * 2, far.height), (0, 0, 0, 255))
    tiled.alpha_composite(far, (0, 0))
    tiled.alpha_composite(far, (far.width, 0))
    small = tiled.resize((far.width, far.height // 2), Image.LANCZOS)
    path = os.path.join(SHOTS_DIR, 'world_far_tiled.png')
    small.save(path)
    # 接缝量化检查：拼缝两侧相邻列的颜色差 vs 图内相邻列的平均差
    arr = np.asarray(far).astype(np.float32)[..., :3]
    seam_a = arr[:, -1]
    seam_b = arr[:, 0]
    seam = np.abs(seam_a - seam_b).mean()
    inner = np.abs(arr[:, 1:] - arr[:, :-1]).mean()
    print('  seam : mean |col1599-col0| = %.3f, mean |col_i-col_i+1| = %.3f' % (seam, inner))
    print('  seam :', path)


def save_previews(layers):
    os.makedirs(SHOTS_DIR, exist_ok=True)
    for cam in [0, 800, 1600, 2240]:
        out = compose_view(cam, layers, chars=True)
        path = os.path.join(SHOTS_DIR, 'world_preview_cam%04d.png' % cam)
        out.convert('RGB').save(path)
        print('  preview:', path)
    # Logo 在游戏背景上的效果预览（模拟标题画面压暗背景）
    logo_path = os.path.join(UI_DIR, 'logo.png')
    if os.path.exists(logo_path):
        bg = compose_view(0, layers, chars=False).convert('RGBA')
        bg.alpha_composite(Image.new('RGBA', bg.size, (0, 0, 0, 150)))
        logo = Image.open(logo_path).convert('RGBA')
        bg.alpha_composite(logo, ((VIEW_W - logo.width) // 2, 36))
        bg.convert('RGB').save(os.path.join(SHOTS_DIR, 'world_logo_mock.png'))
        print('  logo mock:', os.path.join(SHOTS_DIR, 'world_logo_mock.png'))
    save_contact_sheet(layers)
    save_seam_check(layers)


# ----------------------------------------------------------------------------
# 8. main
# ----------------------------------------------------------------------------
def gen_all():
    os.makedirs(WORLD_DIR, exist_ok=True)
    os.makedirs(UI_DIR, exist_ok=True)
    os.makedirs(SHOTS_DIR, exist_ok=True)
    gen_far().save(os.path.join(WORLD_DIR, 'bg_far.png'))
    gen_mid().save(os.path.join(WORLD_DIR, 'bg_mid.png'))
    gen_near().save(os.path.join(WORLD_DIR, 'bg_near.png'))
    gen_fg().save(os.path.join(WORLD_DIR, 'bg_fg.png'))


def main(argv):
    targets = argv[1:] or ['all']
    if 'all' in targets or 'far' in targets:
        os.makedirs(WORLD_DIR, exist_ok=True)
        gen_far().save(os.path.join(WORLD_DIR, 'bg_far.png'))
    if 'all' in targets or 'mid' in targets:
        os.makedirs(WORLD_DIR, exist_ok=True)
        gen_mid().save(os.path.join(WORLD_DIR, 'bg_mid.png'))
    if 'all' in targets or 'near' in targets:
        os.makedirs(WORLD_DIR, exist_ok=True)
        gen_near().save(os.path.join(WORLD_DIR, 'bg_near.png'))
    if 'all' in targets or 'fg' in targets:
        os.makedirs(WORLD_DIR, exist_ok=True)
        gen_fg().save(os.path.join(WORLD_DIR, 'bg_fg.png'))
    if 'all' in targets or 'logo' in targets:
        os.makedirs(UI_DIR, exist_ok=True)
        gen_logo()
    if 'all' in targets or 'manifest' in targets:
        write_manifest()
    if 'all' in targets or 'preview' in targets:
        layers = {n: load_layer(n) for n in ['far', 'mid', 'near', 'fg']}
        layers = {k: v for k, v in layers.items() if v is not None}
        if layers:
            save_previews(layers)
    print('done.')


if __name__ == '__main__':
    main(sys.argv)
