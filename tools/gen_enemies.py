#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
霓虹拳魂 NEON FIST SOUL — 敌人与 Boss 像素美术生成器
=====================================================
程序化绘制并烘焙三种敌人（punk 混混 / brute 壮汉 / boss 铁面 IRON MASK）的
全套像素精灵、160x160 头像与 contact sheet。

设计：
  * 纯 Pillow + numpy，非抗锯齿，1px 深色描边（#150b22 系）。
  * 小型骨骼/姿态渲染器：头、躯干、四肢分层，按关节角度 FK 合成；
    每个部件独立描边 → 肢体交叠处自然形成 1px 分隔线。
  * 每个材质 3 色阶（base/dark/light）+ 左右霓虹轮廓光（左青右品红）。
  * 统一骨架参数，按角色替换比例、部件形状与配色。
  * 帧内肢体不越界；脚底锚点由“支撑脚落地”自动校正。

用法（在项目根目录）：
    python tools/gen_enemies.py            # 生成全部资源 + manifest + 预览
    python tools/gen_enemies.py --wip      # 仅生成开发自查图（_wip_*.png）
    python tools/gen_enemies.py --wip punk # 只生成 punk 的调试图
    python tools/gen_enemies.py --check    # 校验已生成 PNG 的尺寸/帧数/越界
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'assets', 'chars', 'enemies')
SHOTS_DIR = os.path.join(ROOT, 'shots')
WIP_DIR = OUT_DIR

# ============================================================================
# 颜色工具
# ============================================================================

INK = (21, 11, 34)          # #150b22 描边
INK_DEEP = (14, 7, 24)
CYAN = (61, 243, 255)
CYAN_D = (26, 140, 168)
MAGENTA = (255, 47, 142)
MAGENTA_D = (161, 24, 86)
LAVENDER = (168, 152, 255)


def hx(s):
    """'#rrggbb' -> (r, g, b)"""
    if isinstance(s, tuple):
        return s[:3]
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def rgba(c, a=255):
    c = hx(c)
    return (c[0], c[1], c[2], a)


def mix(a, b, t):
    """线性混色，a,b 为 (r,g,b)"""
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))


def shade(c, f):
    return tuple(max(0, min(255, int(round(v * f)))) for v in c)


def mk(base, dark, light):
    """材质：base/dark/light 三色阶"""
    return {'b': hx(base), 'd': hx(dark), 'l': hx(light)}


def mat_far(m, f=0.76, tint=(34, 18, 50), t=0.30):
    """远景/后侧肢体材质：压暗并偏向紫蓝"""
    return {
        'b': mix(shade(m['b'], f), tint, t),
        'd': mix(shade(m['d'], f), tint, t * 0.7),
        'l': mix(shade(m['l'], f * 0.92), tint, t * 0.8),
    }


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_pt(p, q, t):
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def interp_chain(pts, widths, n):
    """在折线上按弧长取 n 个采样点（用于平滑肢体）"""
    if len(pts) == 2:
        return ([lerp_pt(pts[0], pts[1], i / (n - 1)) for i in range(n)],
                [lerp(widths[0], widths[1], i / (n - 1)) for i in range(n)])
    return pts, widths


def rot_pt(p, ang_deg, about=(0.0, 0.0)):
    """屏幕坐标（y 向下）旋转；正角 = 顺时针"""
    a = math.radians(ang_deg)
    x, y = p[0] - about[0], p[1] - about[1]
    return (about[0] + x * math.cos(a) - y * math.sin(a),
            about[1] + x * math.sin(a) + y * math.cos(a))


# ============================================================================
# 掩膜工具（全部二值、无抗锯齿）
# ============================================================================

def new_mask(size):
    return Image.new('L', size, 0)


def shift_mask(m, dx, dy):
    out = new_mask(m.size)
    out.paste(m, (int(round(dx)), int(round(dy))))
    return out


def and_m(a, b):
    return ImageChops.multiply(a, b)


def andnot_m(a, b):
    return ImageChops.subtract(a, b)


def or_m(a, b):
    return ImageChops.lighter(a, b)


def dilate1(m):
    return m.filter(ImageFilter.MaxFilter(3))


def erode1(m):
    return m.filter(ImageFilter.MinFilter(3))


def dir_band(mask, dx, dy, n=1):
    """朝 (dx,dy) 反方向的内侧 n px 边缘带（dx,dy 为外法线方向）"""
    er = mask
    for _ in range(n):
        er = and_m(er, shift_mask(er, dx, dy))
    return andnot_m(mask, er)


def outline_mask(mask, n=1):
    """外侧 n px 描边圈"""
    d = mask
    for _ in range(n):
        d = dilate1(d)
    return andnot_m(d, mask)


def m_poly(size, pts):
    m = new_mask(size)
    if len(pts) < 3:
        return m
    ImageDraw.Draw(m).polygon([(float(x), float(y)) for x, y in pts], fill=255)
    return m


def m_ellipse(size, cx, cy, rx, ry):
    m = new_mask(size)
    ImageDraw.Draw(m).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    return m


def m_rect(size, x0, y0, x1, y1):
    m = new_mask(size)
    ImageDraw.Draw(m).rectangle([x0, y0, x1, y1], fill=255)
    return m


def m_chain(size, pts, widths):
    """变宽肢体：折线 + 每段四边形 + 关节圆头；pts/widths 用 float"""
    m = new_mask(size)
    d = ImageDraw.Draw(m)
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        w0, w1 = widths[i] * 0.5, widths[i + 1] * 0.5
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        nx, ny = -dy / L, dx / L
        poly = [(x0 + nx * w0, y0 + ny * w0), (x1 + nx * w1, y1 + ny * w1),
                (x1 - nx * w1, y1 - ny * w1), (x0 - nx * w0, y0 - ny * w0)]
        d.polygon(poly, fill=255)
    for (x, y), w in zip(pts, widths):
        r = w * 0.5
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return m


def m_chain_flat(size, pts, widths):
    """变宽肢体，但两端不画圆头（用于躯干等）"""
    m = new_mask(size)
    d = ImageDraw.Draw(m)
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        w0, w1 = widths[i] * 0.5, widths[i + 1] * 0.5
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        nx, ny = -dy / L, dx / L
        d.polygon([(x0 + nx * w0, y0 + ny * w0), (x1 + nx * w1, y1 + ny * w1),
                   (x1 - nx * w1, y1 - ny * w1), (x0 - nx * w0, y0 - ny * w0)], fill=255)
    return m


def smooth_chain(pts, n_per_seg=4):
    """折线加密（Catmull-Rom 近似），让肢体转折圆润"""
    if len(pts) < 3:
        return [lerp_pt(pts[0], pts[1], i / n_per_seg) for i in range(n_per_seg + 1)]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        for k in range(1, n_per_seg + 1):
            t = k / n_per_seg
            # 二次贝塞尔近似
            a = lerp_pt(p0, p1, t)
            b = lerp_pt(p1, p2, t)
            out.append(lerp_pt(a, b, t))
    out.append(pts[-1])
    return out


def mask_spread_chain(pts, widths, n=5):
    """把两点/多点折线加密并插值宽度"""
    dense = smooth_chain(pts, n)
    # 按参数重新采样宽度
    Ls = [0.0]
    for i in range(len(pts) - 1):
        Ls.append(Ls[-1] + math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
    total = Ls[-1] or 1.0
    wd = []
    for p in dense:
        best = 0.0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            seg = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
            t = max(0.0, min(1.0, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / (seg * seg)))
            d = math.hypot(p[0] - (a[0] + (b[0] - a[0]) * t), p[1] - (a[1] + (b[1] - a[1]) * t))
            best = max(best, t if d < seg * 0.75 else 0.0)
            if d < seg * 0.75:
                best = max(best, (Ls[i] + seg * t) / total)
        wd.append(lerp(widths[0], widths[-1], best))
    return dense, wd


# ============================================================================
# 画布：分层部件 + 描边 + 3 色阶 + 霓虹轮廓光
# ============================================================================

class Canv:
    def __init__(self, size):
        self.size = size
        self.img = Image.new('RGBA', size, (0, 0, 0, 0))
        self.sil = new_mask(size)

    # ---- 基础填充 ----
    def fill(self, mask, color, track=True):
        solid = Image.new('RGBA', self.size, rgba(color))
        self.img.paste(solid, (0, 0), mask)
        if track:
            self.sil = or_m(self.sil, mask)

    def poly(self, pts, color=None, mask=None, track=False):
        m = m_poly(self.size, pts)
        if mask is not None:
            m = and_m(m, mask)
        if color is not None:
            self.fill(m, color, track=track)
        return m

    def rect(self, x0, y0, x1, y1, color=None, mask=None, track=False):
        m = m_rect(self.size, x0, y0, x1, y1)
        if mask is not None:
            m = and_m(m, mask)
        if color is not None:
            self.fill(m, color, track=track)
        return m

    def px(self, x, y, color):
        self.rect(int(round(x)), int(round(y)), int(round(x)), int(round(y)), color)

    def ellipse(self, cx, cy, rx, ry, color=None, mask=None, track=False):
        m = m_ellipse(self.size, cx, cy, rx, ry)
        if mask is not None:
            m = and_m(m, mask)
        if color is not None:
            self.fill(m, color, track=track)
        return m

    # ---- 标准部件：描边 + 材质 + 明暗 ----
    def part(self, mask, mat, outline=True, band=1, hi=None, sh=None):
        """加入一个部件：外侧描边、底色、左上亮边、右下暗边"""
        if mask.getbbox() is None:
            return
        if outline:
            self.fill(outline_mask(mask), INK, track=False)
        self.fill(mask, mat['b'], track=True)
        if band > 0:
            self.fill(dir_band(mask, 1, 1, band), hi or mat['l'], track=False)
            self.fill(dir_band(mask, -1, -1, band), sh or mat['d'], track=False)

    def limb(self, pts, widths, mat, outline=True, band=1, smooth=3):
        """变宽肢体（自动加密 / 宽度插值）"""
        if len(widths) == 2 and len(pts) > 2:
            widths = [lerp(widths[0], widths[1], i / (len(pts) - 1.0))
                      for i in range(len(pts))]
        if smooth > 0 and len(pts) == 2 and len(widths) == 2:
            n = smooth
            pts = [lerp_pt(pts[0], pts[1], i / n) for i in range(n + 1)]
            widths = [lerp(widths[0], widths[1], i / n) for i in range(n + 1)]
        self.part(m_chain(self.size, pts, widths), mat, outline=outline, band=band)

    # ---- 精灵贴片 ----
    def sprite(self, im, pos):
        self.img.alpha_composite(im, (int(round(pos[0])), int(round(pos[1]))))

    # ---- 霓虹轮廓光 ----
    def neon_rim(self, exclude=None, left=0.58, right=0.58, top=0.42, bottom=0.55, glow=None):
        sil = np.array(self.sil, dtype=bool)
        if exclude is not None:
            ex = np.array(exclude, dtype=np.uint8) > 8
            sil = sil & ~ex
        if not sil.any():
            return

        def shifted(a, dx, dy):
            out = np.zeros_like(a)
            h, w = a.shape
            xs = slice(max(0, -dx), w - max(0, dx))
            ys = slice(max(0, -dy), h - max(0, dy))
            xd = slice(max(0, dx), w - max(0, -dx))
            yd = slice(max(0, dy), h - max(0, -dy))
            out[yd, xd] = a[ys, xs]
            return out

        left_e = sil & ~shifted(sil, 1, 0)
        right_e = sil & ~shifted(sil, -1, 0)
        top_e = sil & ~shifted(sil, 0, 1) & ~left_e & ~right_e
        bottom_e = sil & ~shifted(sil, 0, -1) & ~left_e & ~right_e

        arr = np.array(self.img, dtype=np.uint8)
        cols = arr[..., :3].astype(np.int16)

        def blend(sel, target, strength):
            if not sel.any():
                return
            t = np.array(target, dtype=np.float32)
            c = cols[sel].astype(np.float32)
            cols[sel] = np.clip(c * (1 - strength) + t * strength, 0, 255).astype(np.int16)

        blend(left_e, CYAN, left)
        blend(right_e, MAGENTA, right)
        blend(top_e, (150, 205, 255), top)
        blend(bottom_e, (30, 18, 56), bottom)
        arr[..., :3] = cols.astype(np.uint8)
        self.img = Image.fromarray(arr, 'RGBA')


# ============================================================================
# 骨骼 / 姿态（FK）
# ============================================================================

POSE_DEFAULT = dict(
    lean=6.0,                 # 躯干前倾角（度，+ 朝面向）
    fa=(24.0, 92.0),          # 前臂：肩角、肘相对角（0=垂直向下，+朝前）
    ra=(14.0, 84.0),          # 后臂
    fl=(7.0, -9.0, 0.0),      # 前腿：髋角、膝相对角、脚绝对角（0=脚掌水平）
    rl=(-7.0, -10.0, 0.0),    # 后腿
    head_dx=0.0, head_dy=0.0, head_rot=0,
    expr='idle',
    grounded=True,
    hip_dx=0.0, pelvis_dy=0.0,
    root_rot=0.0, root_dx=0.0, root_dy=0.0,
    fa_open=False, ra_open=False,
    weapon=None,
)


def mk_pose(spec, **kw):
    p = dict(POSE_DEFAULT)
    p.update(spec.get('stance', {}))
    p.update(kw)
    return p


def fk(spec, pose):
    """返回局部坐标（脚底为原点，y 向下为负）的所有关节位置"""
    pr = spec['prop']
    pel = [pose['hip_dx'], -pr['leg_len']]

    lean = math.radians(pose['lean'])
    tdir = (math.sin(lean), -math.cos(lean))
    perp = (-tdir[1], tdir[0])  # 身体“右”向（站立时朝 +x）

    sh = [pel[0] + tdir[0] * pr['torso'], pel[1] + tdir[1] * pr['torso']]
    neck = [sh[0] + tdir[0] * pr['neck'], sh[1] + tdir[1] * pr['neck']]
    hc = [neck[0] + tdir[0] * (pr['head_h'] * 0.44) + pose['head_dx'],
          neck[1] + tdir[1] * (pr['head_h'] * 0.44) + pose['head_dy']]

    def two_chain(origin, a1, a2, L1, L2):
        r1 = math.radians(a1)
        e = [origin[0] + math.sin(r1) * L1, origin[1] + math.cos(r1) * L1]
        r2 = math.radians(a1 + a2)
        h = [e[0] + math.sin(r2) * L2, e[1] + math.cos(r2) * L2]
        return e, h

    sep = pr.get('shoulder_sep', 5)
    fa_sh = [sh[0] + perp[0] * sep, sh[1] + perp[1] * sep]
    ra_sh = [sh[0] - perp[0] * sep, sh[1] - perp[1] * sep]
    fa_el, fa_hand = two_chain(fa_sh, pose['fa'][0], pose['fa'][1], pr['upper'], pr['fore'])
    ra_el, ra_hand = two_chain(ra_sh, pose['ra'][0], pose['ra'][1], pr['upper'], pr['fore'])

    hs = pr.get('hip_sep', 4)
    fl_hip = [pel[0] + perp[0] * hs, pel[1] + perp[1] * hs]
    rl_hip = [pel[0] - perp[0] * hs, pel[1] - perp[1] * hs]
    fl_knee, fl_ankle = two_chain(fl_hip, pose['fl'][0], pose['fl'][1], pr['thigh'], pr['shin'])
    rl_knee, rl_ankle = two_chain(rl_hip, pose['rl'][0], pose['rl'][1], pr['thigh'], pr['shin'])

    P = {
        'pelvis': pel, 'shoulder': sh, 'neck': neck, 'head': hc,
        'fa_shoulder': fa_sh, 'fa_elbow': fa_el, 'fa_hand': fa_hand,
        'ra_shoulder': ra_sh, 'ra_elbow': ra_el, 'ra_hand': ra_hand,
        'fl_hip': fl_hip, 'fl_knee': fl_knee, 'fl_ankle': fl_ankle,
        'rl_hip': rl_hip, 'rl_knee': rl_knee, 'rl_ankle': rl_ankle,
        'fl_foot': pose['fl'][2], 'rl_foot': pose['rl'][2],
    }

    # 支撑脚落地校正（自动锚点）：取较低的那只脚作为支撑脚
    if pose['grounded']:
        support = max(P['fl_ankle'][1], P['rl_ankle'][1])
        dy = -pr['ankle_h'] - support
        for v in P.values():
            if isinstance(v, list):
                v[1] += dy
    else:
        dy = pose['pelvis_dy']
        for v in P.values():
            if isinstance(v, list):
                v[1] += dy

    # 整体旋转（KO 倒地等）
    if abs(pose['root_rot']) > 0.01 or pose['root_dx'] or pose['root_dy']:
        about = tuple(P['pelvis'])
        for k, v in P.items():
            if isinstance(v, list):
                r = rot_pt((v[0], v[1]), pose['root_rot'], about)
                v[0] = r[0] + pose['root_dx']
                v[1] = r[1] + pose['root_dy']
        # 脚部角度也跟随整体旋转
        P['fl_foot'] += pose['root_rot']
        P['rl_foot'] += pose['root_rot']

    # 兜底：倒地/腾空帧不得穿透地面（保证最后一行像素留出余量）
    max_y = max(v[1] for v in P.values() if isinstance(v, list))
    if max_y > -3.0:
        dy = -3.0 - max_y
        for v in P.values():
            if isinstance(v, list):
                v[1] += dy

    return P


def body_frame(P):
    """躯干坐标系：原点骨盆，t 沿躯干向上，s 指向身体右侧"""
    pel = P['pelvis']
    sh = P['shoulder']
    dx, dy = sh[0] - pel[0], sh[1] - pel[1]
    L = math.hypot(dx, dy) or 1.0
    tdir = (dx / L, dy / L)
    perp = (-tdir[1], tdir[0])
    return pel, tdir, perp, L


def bp(P, along, side):
    """躯干坐标系取点：along=沿躯干向上距离(px)，side=横向偏移(+为面向)"""
    pel, tdir, perp, L = body_frame(P)
    return (pel[0] + tdir[0] * along + perp[0] * side,
            pel[1] + tdir[1] * along + perp[1] * side)


def bp_pts(P, seq):
    return [bp(P, a, s) for a, s in seq]


# ============================================================================
# 敌方通用工具
# ============================================================================

def foot_poly(ankle, ang, pts_local):
    """脚部多边形：pts_local 以脚踝为原点 (u 朝前, v 朝下)"""
    return [rot_pt((ankle[0] + u, ankle[1] + v), ang, about=ankle) for u, v in pts_local]


def fist(canv, at, ang, r, mat, open_hand=False, outline=True):
    """拳头或张开的手"""
    cx, cy = at
    if open_hand:
        m = m_ellipse(canv.size, cx, cy, r * 0.8, r * 0.95)
        canv.part(m, mat, outline=outline, band=1)
        # 三根手指
        for k in (-0.55, 0.0, 0.55):
            tip = rot_pt((cx + r * 1.6, cy + r * 0.9 * k), ang, about=(cx, cy))
            canv.part(m_chain(canv.size, [(cx, cy + r * 0.5 * k), tip], [r * 0.62, r * 0.5]),
                      mat, outline=outline, band=0)
    else:
        m = m_ellipse(canv.size, cx, cy, r * 1.06, r * 0.94)
        canv.part(m, mat, outline=outline, band=1)
        # 指节高光
        kn = rot_pt((cx + r * 0.55, cy - r * 0.2), ang, about=(cx, cy))
        canv.px(kn[0], kn[1], mat['l'])
        kn2 = rot_pt((cx + r * 0.55, cy + r * 0.35), ang, about=(cx, cy))
        canv.px(kn2[0], kn2[1], mat['l'])


def make_head_fn(char_name):
    """头部渲染函数分发"""
    if char_name == 'punk':
        return render_head_punk
    if char_name == 'brute':
        return render_head_brute
    if char_name == 'boss':
        return render_head_boss
    raise KeyError(char_name)


def get_head(spec, pose, cache):
    expr = pose.get('expr', 'idle')
    rot = pose.get('head_rot', 0)
    key = (spec['name'], expr, rot)
    if key not in cache:
        fn = make_head_fn(spec['name'])
        cache[key] = fn(expr, rot)
    return cache[key]


def rotate_sprite(im, origin, ang):
    """按 90 度倍数旋转精灵（保持像素锐利），返回新图与新原点"""
    if not ang:
        return im, origin
    ang = int(round(ang / 90.0)) * 90 % 360
    if ang == 0:
        return im, origin
    rot = im.rotate(ang, resample=Image.Resampling.NEAREST, expand=True)
    marker = Image.new('RGBA', im.size, (0, 0, 0, 0))
    md = ImageDraw.Draw(marker)
    md.rectangle([origin[0], origin[1], origin[0] + 1, origin[1] + 1], fill=(255, 0, 0, 255))
    mk = marker.rotate(ang, resample=Image.Resampling.NEAREST, expand=True)
    bbox = mk.getbbox()
    no = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
    return rot, no


# ============================================================================
# PUNK 混混 —— 比例、材质、姿态
# ============================================================================

PUNK = {
    'name': 'punk',
    'frame': (220, 220),
    'anchor': (110, 206),
    'bodyHeight': 176,
    'prop': dict(
        leg_len=74.0, thigh=36.0, shin=32.0, ankle_h=6.0,
        torso=44.0, neck=4.0, head_h=42.0, head_w=32.0,
        shoulder_w=40.0, waist_w=26.0, chest_w=34.0, hip_w=28.0,
        upper=27.0, fore=25.0, hand_r=4.8,
        shoulder_sep=5.5, hip_sep=4.5,
        head_canvas=76, head_origin=38,
    ),
    'stance': dict(
        lean=9.0, fa=(26.0, 96.0), ra=(14.0, 88.0),
        fl=(8.0, -10.0, 0.0), rl=(-8.0, -11.0, 0.0),
        expr='idle',
    ),
}

PM = {
    'skin':    mk('#e8bb95', '#b0775c', '#f8d6b0'),
    'skin_d':  mk('#c98f70', '#96604f', '#e8bb95'),
    'skin_dd': mk('#a26953', '#744440', '#c98f70'),
    'hollow':  mk('#b07a5e', '#835044', '#c98f70'),
    'hair':    mk('#2e1c40', '#1a0f28', '#4c2e64'),
    'mohawk':  mk('#ff2f8e', '#8f1048', '#ff6aa8'),
    'mohawk2': mk('#c81e78', '#5c0c2c', '#ff4d97'),
    'leather': mk('#3a2a4c', '#231630', '#584270'),
    'leather2': mk('#241a32', '#150f20', '#3a2a4c'),
    'denim':   mk('#4e568a', '#2e3158', '#707ab2'),
    'denim2':  mk('#3a406e', '#23264a', '#4e568a'),
    'boot':    mk('#33223c', '#1e1426', '#503862'),
    'steel':   mk('#9aa7c7', '#5d6b8f', '#d7e2f7'),
    'steel2':  mk('#6a7694', '#3c4664', '#9aa7c7'),
    'chain':   mk('#b8c4e0', '#6a7694', '#e8f0ff'),
    'belt':    mk('#3c2a34', '#241820', '#5a4050'),
    'yellow':  mk('#ffd23f', '#a87a18', '#fff0a0'),
    'cyan':    mk('#3df3ff', '#1a8ca8', '#b8fbff'),
    'magenta': mk('#ff2f8e', '#a11856', '#ff8ab8'),
    'teeth':   mk('#e8e4dc', '#a8a49c', '#fffef4'),
    'white':   mk('#f2f0ff', '#a8a4c0', '#ffffff'),
    'iris':    mk('#ff7ac0', '#a11856', '#ffd0ea'),
    'mouth':   hx('#4a1226'),
    'mouth2':  hx('#7a2440'),
    'tongue':  hx('#c03a5e'),
    'scar':    hx('#8a3a4a'),
    'glint':   hx('#eaffff'),
}


def punk_leg(canv, P, pose, side):
    far = (side == 'rear')
    prefix = 'rl' if far else 'fl'
    denim = mat_far(PM['denim']) if far else PM['denim']
    denim2 = mat_far(PM['denim2']) if far else PM['denim2']
    boot = mat_far(PM['boot']) if far else PM['boot']
    skin = mat_far(PM['skin'], 0.8) if far else PM['skin']
    hip = P[prefix + '_hip']
    knee = P[prefix + '_knee']
    ankle = P[prefix + '_ankle']
    foot_ang = P['fl_foot'] if side == 'front' else P['rl_foot']

    # 大腿 + 小腿（牛仔裤）
    canv.limb([hip, lerp_pt(hip, knee, 0.55), knee], [16.0, 14.0, 12.0], denim, band=2)
    canv.limb([knee, lerp_pt(knee, ankle, 0.5), ankle], [12.0, 10.5, 9.0], denim, band=2)

    # 膝盖补丁 / 破洞（近侧腿）
    if not far:
        kx, ky = knee
        canv.part(m_ellipse(canv.size, kx + 1, ky - 1, 4.2, 4.6), skin, outline=True, band=0)
        # 破洞边缘的毛边
        for dx, dy in ((-5, -2), (5, -3), (-4, 4), (5, 2), (0, 5)):
            canv.px(kx + dx, ky + dy, denim2['d'])
        canv.poly([(kx - 3, ky + 2), (kx + 2, ky + 3), (kx + 1, ky + 4), (kx - 3, ky + 4)], PM['skin_dd']['d'])

    # 裤脚
    ax, ay = ankle
    canv.part(m_chain(canv.size, [lerp_pt(knee, ankle, 0.82), ankle], [10.5, 10.0]), denim2,
              outline=False, band=0)

    # 尖头皮靴
    boot_pts = [(-7, -3), (4, -3), (8, 0), (12, 1), (16, 5), (12, 7), (-7, 7), (-9, 3)]
    bm = m_poly(canv.size, foot_poly(ankle, foot_ang, boot_pts))
    canv.part(bm, boot, outline=True, band=1)
    # 鞋头钢片 + 鞋底
    tip = foot_poly(ankle, foot_ang, [(8, 1), (12, 1.5), (15.5, 5), (11, 6), (8.5, 5)])
    canv.part(m_poly(canv.size, tip), mat_far(PM['steel'], 1.0) if far else PM['steel'],
              outline=False, band=0)
    sole = foot_poly(ankle, foot_ang, [(-8, 6), (12, 6), (12, 7), (-8, 7.2)])
    canv.poly(sole, INK)
    # 靴面亮边
    cuff = foot_poly(ankle, foot_ang, [(-6.5, -2), (3.5, -2), (3.5, -1), (-6.5, -1)])
    canv.poly(cuff, boot['l'])


def punk_arm(canv, P, pose, side):
    far = (side == 'rear')
    prefix = 'ra' if far else 'fa'
    skin = mat_far(PM['skin'], 0.78) if far else PM['skin']
    skin_d = mat_far(PM['skin_d'], 0.78) if far else PM['skin_d']
    sh = P[prefix + '_shoulder']
    el = P[prefix + '_elbow']
    hand = P[prefix + '_hand']
    open_hand = pose['ra_open'] if far else pose['fa_open']

    # 上臂（露肩，背心）+ 前臂
    canv.limb([sh, lerp_pt(sh, el, 0.5), el], [11.0, 9.5, 8.0], skin, band=1)
    canv.limb([el, lerp_pt(el, hand, 0.5), hand], [8.0, 7.2, 6.4], skin, band=1)
    # 肘部阴影
    canv.part(m_ellipse(canv.size, el[0], el[1], 3.6, 3.6), skin_d, outline=False, band=0)
    # 手
    ang = math.degrees(math.atan2(hand[0] - el[0], hand[1] - el[1]))
    fist(canv, hand, ang, PUNK['prop']['hand_r'], skin, open_hand=open_hand)
    # 护腕（近侧）
    if not far:
        wdir = (hand[0] - el[0], hand[1] - el[1])
        L = math.hypot(*wdir) or 1.0
        wdir = (wdir[0] / L, wdir[1] / L)
        cx, cy = hand[0] - wdir[0] * 7.0, hand[1] - wdir[1] * 7.0
        nrm = (-wdir[1], wdir[0])
        band = m_chain(canv.size, [(cx - nrm[0] * 1.5, cy - nrm[1] * 1.5),
                                   (cx + nrm[0] * 1.5, cy + nrm[1] * 1.5)],
                       [9.0, 9.0])
        canv.part(band, PM['leather2'], outline=True, band=0)
        canv.poly([(cx - nrm[0] * 1.5 + wdir[0] * 2.2, cy - nrm[1] * 1.5 + wdir[1] * 2.2),
                   (cx + nrm[0] * 1.5 + wdir[0] * 2.2, cy + nrm[1] * 1.5 + wdir[1] * 2.2),
                   (cx + nrm[0] * 1.5 + wdir[0] * 3.0, cy + nrm[1] * 1.5 + wdir[1] * 3.0),
                   (cx - nrm[0] * 1.5 + wdir[0] * 3.0, cy - nrm[1] * 1.5 + wdir[1] * 3.0)], PM['cyan']['b'])
        # 腕钉
        for s in (-1, 1):
            sx = cx + nrm[0] * 4.6 * s
            sy = cy + nrm[1] * 4.6 * s
            canv.px(sx, sy, PM['steel']['l'])
            canv.px(sx + wdir[0], sy + wdir[1], PM['steel']['b'])


def punk_torso(canv, P, pose):
    pel = P['pelvis']
    sh = P['shoulder']
    prop = PUNK['prop']
    skin = PM['skin']
    # 骨盆 / 裤子
    pel_up = bp(P, 4, 0)
    pel_dn = bp(P, -10, 0)
    canv.limb([pel_up, lerp_pt(pel_up, pel_dn, 0.5), pel_dn], [28.0, 28.0, 25.0], PM['denim'], band=2)

    # 腰带
    b1 = bp(P, 2.5, 0)
    b2 = bp(P, -2.5, 0)
    canv.limb([b1, b2], [29.0, 29.0], PM['belt'], outline=False, band=0)
    # 皮带扣
    buck = bp(P, 0.5, 7.0)
    canv.rect(buck[0] - 2, buck[1] - 1, buck[0] + 2, buck[1] + 2, PM['steel']['b'])
    canv.rect(buck[0] - 1, buck[1], buck[0] + 1, buck[1] + 1, PM['yellow']['b'])

    # 躯干裸肤（背心开襟露出）
    torso_pts = bp_pts(P, [(0, 0), (20, 0), (34, 0), (47, 0)])
    torso_w = [25.0, 27.0, 30.0, 33.0]
    torso_m = m_chain_flat(canv.size, torso_pts, torso_w)
    # 肩部圆化
    torso_m = or_m(torso_m, m_ellipse(canv.size, sh[0], sh[1], 17.0, 9.0))
    canv.part(torso_m, skin, band=2)
    # 胸腹阴影（肋骨、腹肌）
    canv.poly([bp(P, 40, 2), bp(P, 36, 13), bp(P, 33, 12), bp(P, 38, 1)], PM['skin_d']['d'])
    canv.poly([bp(P, 30, 6), bp(P, 26, 13), bp(P, 24, 12), bp(P, 28, 6)], PM['skin_d']['d'])
    canv.poly([bp(P, 22, 7), bp(P, 19, 12), bp(P, 17.5, 11), bp(P, 20.5, 6)], PM['skin_d']['d'])
    # 腹部中线高光
    canv.poly([bp(P, 30, 2), bp(P, 22, 1.5), bp(P, 21, 0), bp(P, 29, 0.5)], PM['skin']['l'])

    # 皮背心（躯干轮廓 - 胸口 V 形开口）
    opening = m_poly(canv.size, bp_pts(P, [(49, 7), (44, 12), (36, 13), (30, 10), (27, 3),
                                           (33, -2), (43, 0), (47, 2)]))
    vest = andnot_m(torso_m, opening)
    canv.part(vest, PM['leather'], band=2)
    # 背心翻领
    lapel = m_poly(canv.size, bp_pts(P, [(47.5, 3), (43, 0.5), (42.5, 11), (46, 8)]))
    canv.part(lapel, PM['leather2'], outline=True, band=1)
    # 铆钉
    for a, s in ((44, 15), (46, 17.5), (43, 18.5), (37, 16.5)):
        q = bp(P, a, s)
        canv.px(q[0], q[1], PM['steel']['l'])
        canv.px(q[0] + 1, q[1], PM['steel']['b'])
    # 链条项链
    chain = [(49, -9), (47, -5), (45, 0), (43, 3), (41, 5), (39, 6)]
    for i in range(len(chain) - 1):
        a = bp(P, *chain[i])
        b = bp(P, *chain[i + 1])
        canv.px(a[0], a[1], PM['chain']['l'] if i % 2 == 0 else PM['chain']['b'])
        canv.px((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, PM['chain']['b'])
    pend = bp(P, 37, 5)
    canv.rect(pend[0] - 1, pend[1], pend[0] + 1, pend[1] + 2, PM['yellow']['b'])
    # 脖子
    neck_a = bp(P, 47, 0)
    neck_b = bp(P, 53, -1)
    canv.limb([neck_a, neck_b], [15.0, 13.0], PM['skin_d'], band=1)


def punk_after_legs(canv, P, pose):
    # 背心下摆的破边
    for i, (a, s) in enumerate(((6, -12), (4, -10), (3, 12), (5, 14))):
        q = bp(P, a, s)
        canv.px(q[0], q[1], PM['leather2']['d'])


def punk_header(canv, P, pose):
    pass


def punk_front_extra(canv, P, pose):
    """匕首（攻击时前手）"""
    if pose.get('weapon') != 'dagger':
        return
    hand = P['fa_hand']
    el = P['fa_elbow']
    ang = math.atan2(hand[0] - el[0], hand[1] - el[1])  # 屏幕角（y 下）
    # 沿前臂延长方向
    dx, dy = math.sin(ang), math.cos(ang)
    nx, ny = -dy, dx

    def q(u, v):
        return (hand[0] + dx * u + nx * v, hand[1] + dy * u + ny * v)

    # 刀柄
    canv.part(m_chain(canv.size, [q(-4, 0), q(4, 0)], [4.2, 4.6]), PM['leather2'], band=0)
    # 护手
    canv.part(m_chain(canv.size, [q(5, -5.5), q(5, 5.5)], [2.6, 2.6]), PM['steel2'], band=0)
    # 刀身
    blade = [q(6, -2.4), q(20, -2.2), q(28, -1.0), q(20, 2.2), q(6, 2.2)]
    canv.part(m_poly(canv.size, blade), PM['steel'], outline=True, band=0)
    # 刃口高光 + 血槽
    canv.poly([q(7, -2), q(26, -1.3), q(26, -0.6), q(7, -1.2)], PM['steel']['l'])
    canv.poly([q(8, 0.4), q(24, 0.2), q(24, 0.8), q(8, 1.0)], PM['steel2']['d'])
    # 刀尖霓虹反光
    canv.px(q(27.5, -1.0)[0], q(27.5, -1.0)[1], PM['glint'])


# ---------------------------------------------------------------------------
# PUNK 头部（76x76，中心 38,38）—— 3/4 侧脸朝右
#   头顶 -22 / 眉 -13 / 眼 -9..-2 / 鼻尖 0..2 / 嘴 6..12 / 下巴 19
#   高对比像素脸：墨线眼框 + 白牙 + 硬鼻底阴影；避免大面积浅色块
# ---------------------------------------------------------------------------

PUNK_SKULL = [(-8, -21), (-1, -22), (5, -21), (9, -18), (11, -13), (12, -8),
              (12.5, -5), (14, -2), (15.5, 0), (15.5, 2), (14, 3.5),
              (13, 6), (12.5, 9), (11, 12), (9, 15), (6, 17.5), (2, 19),
              (-2, 18), (-6, 16), (-9, 13), (-11, 10), (-13, 6), (-13.5, 1),
              (-13, -5), (-12, -11), (-11, -16)]

PUNK_MOHAWK = [(9, -17), (10.5, -27), (7, -23), (5, -33), (2, -24), (0, -36),
               (-3, -24.5), (-6.5, -32), (-9.5, -23), (-12.5, -28), (-14.5, -14),
               (-12.5, -19), (-8, -21), (-2, -22), (4, -21), (7.5, -19)]

PUNK_TAIL = [(-14, -13), (-18, -16), (-20, -6), (-19, 4), (-16, 10), (-13.5, 9), (-14, 0)]

PUNK_SHAVE = [(-12.5, -14), (-9, -19), (-4, -20), (-5, -17), (-9.5, -15),
              (-12, -10), (-13.5, -5), (-13.5, 0), (-13, -6)]


def render_head_punk(expr='idle', rot=0):
    C = Canv((76, 76))
    ox = oy = 38

    def h(x, y):
        return (ox + x, oy + y)

    def hp(seq):
        return [h(x, y) for x, y in seq]

    def pxx(x, y, col):
        C.px(ox + x, oy + y, col)

    def hline(x0, x1, y, col):
        for x in range(int(round(x0)), int(round(x1)) + 1):
            pxx(x, y, col)

    # ================= 脖子 + 铆钉项圈 =================
    C.limb([h(0, 16), h(-0.5, 33)], [12.0, 14.0], PM['skin_d'], band=1)
    C.poly(hp([(-5, 17), (0, 17.5), (4, 16), (5, 20), (-5, 20)]), PM['skin_dd']['d'])
    C.poly(hp([(-5, 21), (3, 21.5), (2, 23), (-5, 22.5)]), PM['skin_dd']['b'])
    C.poly(hp([(-5.5, 19), (-6, 29), (-4.8, 30), (-4.8, 19)]), PM['skin']['l'])
    C.part(m_chain(C.size, [h(-6.5, 22), h(4.5, 21.5)], [5.5, 5.0]), PM['leather2'], band=0)
    for sx in (-4.5, -1.5, 1.5, 4):
        pxx(sx, 20.6, PM['steel']['l'])
        pxx(sx, 21.6, PM['steel']['b'])

    # ================= 莫西干 =================
    C.part(m_poly(C.size, hp(PUNK_TAIL)), PM['mohawk2'], band=1)
    C.part(m_poly(C.size, hp(PUNK_MOHAWK)), PM['mohawk'], band=1)
    C.poly(hp([(-13, -13), (-9, -18), (-4, -20), (2, -20), (7, -18), (8, -16),
               (3, -17.5), (-2, -18), (-8, -16.5)]), PM['mohawk2']['d'])
    spikes = [((10.5, -27), (8.2, -18)), ((5, -33), (3.4, -19)), ((0, -36), (-1.2, -20)),
              ((-6.5, -32), (-7.8, -19)), ((-12.5, -28), (-13.2, -16))]
    for (tip, base) in spikes:
        steps = 11
        for i in range(steps):
            t = i / (steps - 1.0)
            x = lerp(tip[0], base[0], t) - 0.7
            y = lerp(tip[1], base[1], t)
            C.px(ox + x, oy + y, PM['mohawk']['l'])
            C.px(ox + x + 2.4, oy + y, PM['mohawk2']['d'])
    for (x, y) in ((10, -25), (5, -31), (0, -34), (-6.5, -30), (-12, -26)):
        pxx(x, y, PM['mohawk']['l'])
    for (x, y) in ((9, -22), (4, -28), (-1, -32), (-7.5, -27), (-12.5, -23)):
        pxx(x, y, PM['mohawk2']['l'])

    # ================= 头骨 =================
    skull_m = m_poly(C.size, hp(PUNK_SKULL))
    C.part(skull_m, PM['skin'], band=2)

    # ================= 侧剃 + 发根 + 鬓角 =================
    C.poly(hp(PUNK_SHAVE), PM['hair']['b'])
    C.poly(hp([(-12, -12), (-8.5, -17.5), (-4.5, -19.5), (-6, -16), (-9.5, -13),
               (-12, -6)]), PM['hair']['l'])
    for (x, y) in ((-12.5, -8), (-11.5, -4), (-13, -2), (-10.5, -12), (-9, -10),
                   (-13.5, -6)):
        pxx(x, y, PM['hair']['d'])
    C.poly(hp([(4.5, -20), (8.5, -18), (8, -16.5), (4, -18.5)]), PM['hair']['b'])
    for (x, y) in ((6.5, -18.8), (4, -18.3), (2.5, -19)):
        pxx(x, y, PM['hair']['d'])
    C.poly(hp([(-12.5, -4), (-11.5, 2), (-11, 4.5), (-12.5, 3.5), (-13, 0)]),
           PM['hair']['b'])

    # ================= 耳朵 / 耳钉 =================
    C.part(m_ellipse(C.size, ox - 11.4, oy + 2.4, 2.5, 4.4), PM['skin_d'], band=1)
    C.poly(hp([(-12, 0.5), (-11.2, 2), (-11.2, 4.4), (-12.6, 3.2)]), PM['skin_dd']['d'])
    pxx(-11.2, 7.4, INK)
    pxx(-10.8, 7.8, PM['yellow']['b'])
    pxx(-11.6, -0.6, PM['steel']['l'])
    pxx(-12.1, -1.2, PM['steel']['b'])

    wide = (expr == 'shout')
    shut = (expr in ('hurt', 'ko'))

    # ================= 眼窝（薄阴影） =================
    C.poly(hp([(3.4, -9.6), (12.6, -10.4), (12.9, -1.8), (3.6, -1.4)]),
           PM['skin_d']['b'])
    C.poly(hp([(-6.8, -8.2), (-1.2, -7.8), (-0.8, -2.0), (-6.8, -2.4)]),
           PM['skin_d']['d'])

    # ================= 眼睛（墨线框 + 白眼 + 品红虹膜） =================
    if not shut:
        # 近眼
        C.poly(hp([(3.2, -8.6), (12.4, -9.6), (12.9, -2.0), (3.0, -1.4)]), INK)
        C.poly(hp([(4.0, -7.8), (11.8, -8.8), (12.2, -2.9), (4.0, -2.4)]),
               PM['white']['b'])
        C.rect(ox + 7.4, oy - 7.1, ox + 10.4, oy - 3.2, PM['iris']['b'])
        C.rect(ox + 8.6, oy - 6.3, ox + 10.4, oy - 4.2, INK)
        pxx(7.5, -6.6, PM['iris']['l'])
        pxx(8.2, -3.6, PM['iris']['d'])
        C.poly(hp([(2.6, -8.9), (11.8, -10.0), (12.7, -8.0), (3.2, -7.2)]), INK)
        pxx(2.0, -8.2, INK)
        pxx(1.4, -7.5, INK)
        pxx(13.1, -8.8, INK)
        hline(4.8, 11.4, -1.5, PM['skin_dd']['d'])
        # 远眼
        C.poly(hp([(-7.2, -7.2), (-0.9, -8.1), (-0.6, -1.9), (-6.6, -1.3)]), INK)
        C.poly(hp([(-6.4, -6.6), (-1.6, -7.2), (-1.4, -2.4), (-6.0, -2.0)]),
               PM['white']['d'])
        C.rect(ox - 4.4, oy - 6.0, ox - 2.8, oy - 3.4, PM['iris']['d'])
        pxx(-3.6, -5.2, INK)
        pxx(-4.6, -3.9, PM['iris']['l'])
        pxx(-4.6, -8.9, INK)
    else:
        if expr == 'hurt':
            C.poly(hp([(3.0, -6.4), (4.4, -2.0), (12.8, -2.6), (11.4, -7.0)]), INK)
            C.poly(hp([(-6.8, -6.0), (-1.0, -6.8), (-1.2, -2.0), (-6.6, -1.4)]), INK)
            pxx(8.6, -1.2, PM['skin_dd']['b'])
        else:
            C.poly(hp([(3.2, -4.8), (12.4, -5.4), (12.4, -3.4), (3.2, -2.8)]), INK)
            C.poly(hp([(-6.6, -4.4), (-1.2, -5.0), (-1.2, -3.0), (-6.6, -2.4)]), INK)
            pxx(4.2, -5.8, PM['white']['b'])
            pxx(5.8, -5.8, PM['white']['b'])

    # ================= 眉毛 =================
    if expr == 'hurt':
        C.poly(hp([(1.6, -13.2), (13.2, -11.2), (13.2, -9.2), (1.6, -11.2)]), INK)
        C.poly(hp([(-7.4, -10.4), (-1.2, -12.2), (-1.2, -10.4), (-7.4, -8.8)]), INK)
    elif expr == 'ko':
        C.poly(hp([(2.0, -12.4), (12.8, -10.8), (12.8, -9.8), (2.0, -11.4)]), INK)
        C.poly(hp([(-7.2, -10.0), (-1.4, -11.0), (-1.4, -9.4), (-7.2, -8.4)]), INK)
    elif wide:
        C.poly(hp([(1.6, -14.0), (13.4, -11.8), (13.4, -9.6), (1.6, -11.8)]), INK)
        C.poly(hp([(-7.8, -12.0), (-1.0, -13.4), (-1.0, -11.2), (-7.8, -10.0)]), INK)
    else:  # 狞笑：内压外挑
        C.poly(hp([(1.6, -12.8), (13.6, -10.4), (13.6, -8.4), (1.6, -10.6)]), INK)
        C.poly(hp([(-7.4, -10.8), (-1.2, -9.8), (-1.2, -8.0), (-7.4, -9.2)]), INK)
        pxx(0.6, -10.8, INK)
        pxx(-0.4, -9.8, INK)

    # ================= 鼻子（鼻梁影 + 小鼻头 + 硬鼻底） =================
    C.poly(hp([(10.0, -6.4), (13.2, -2.8), (14.6, -0.4), (13.4, 0.2), (10.6, -3.2),
               (9.8, -5.6)]), PM['skin_d']['b'])
    pxx(12.0, -3.4, PM['skin_dd']['b'])
    C.poly(hp([(10.4, -5.8), (12.8, -2.6), (14.2, -0.4), (13.6, -0.4), (11.0, -3.0)]),
           PM['skin']['l'])
    C.rect(ox + 12.8, oy + 0.6, ox + 14.7, oy + 1.8, PM['skin']['l'])
    pxx(13.8, 2.4, INK)
    pxx(14.6, 2.6, INK)
    C.rect(ox + 9.4, oy + 3.0, ox + 14.0, oy + 3.6, PM['skin_dd']['d'])
    C.rect(ox + 10.2, oy + 4.0, ox + 14.0, oy + 4.6, PM['hollow']['d'])
    pxx(15.0, 2.2, PM['skin_dd']['b'])

    # ================= 颧骨 / 颊窝 =================
    C.poly(hp([(3.8, 2.0), (7.6, 3.6), (8.0, 6.4), (4.4, 5.0)]), PM['hollow']['b'])
    C.poly(hp([(4.8, 6.6), (8.0, 7.6), (7.6, 9.4), (4.8, 8.4)]), PM['hollow']['d'])
    C.poly(hp([(12.4, 4.6), (13.4, 6.4), (12.8, 8.0), (11.6, 6.6)]), PM['hollow']['b'])
    C.rect(ox + 6.4, oy - 1.4, ox + 9.4, oy - 0.8, PM['skin']['l'])

    # ================= 嘴（高对比：墨线口腔 + 白牙） =================
    if expr == 'shout':
        C.poly(hp([(0.8, 5.6), (12.4, 4.2), (13.4, 9.2), (2.0, 11.8)]), INK)
        C.poly(hp([(1.6, 5.8), (12.0, 4.8), (12.2, 6.6), (2.0, 7.6)]), PM['teeth']['b'])
        C.poly(hp([(2.4, 9.6), (12.2, 8.6), (12.4, 10.4), (2.6, 11.2)]), PM['teeth']['b'])
        for tx in (4.4, 7.2, 10.0):
            pxx(tx, 5.4, PM['teeth']['d'])
            pxx(tx, 6.2, PM['teeth']['d'])
            pxx(tx, 9.8, PM['teeth']['d'])
            pxx(tx, 10.6, PM['teeth']['d'])
        C.poly(hp([(4.0, 7.9), (10.2, 7.0), (9.6, 9.2), (4.6, 9.8)]), PM['tongue'])
        C.poly(hp([(3.4, 6.8), (4.2, 9.0), (2.8, 8.6)]), PM['teeth']['l'])
        C.poly(hp([(10.6, 6.6), (11.4, 8.8), (9.9, 8.5)]), PM['teeth']['l'])
        pxx(0.8, 5.6, INK)
        pxx(13.4, 9.2, INK)
    elif expr == 'hurt':
        C.poly(hp([(1.6, 6.2), (12.4, 5.0), (13.0, 9.4), (3.0, 11.4)]), INK)
        C.poly(hp([(2.2, 6.4), (12.0, 5.4), (12.2, 7.2), (2.6, 8.2)]), PM['teeth']['b'])
        for tx in (4.4, 7.2, 10.0):
            C.rect(ox + tx, oy + 5.6, ox + tx, oy + 8.2, PM['teeth']['d'])
        C.poly(hp([(2.8, 9.2), (11.8, 8.2), (11.8, 9.4), (3.0, 10.4)]), PM['teeth']['b'])
        pxx(1.6, 6.2, INK)
        pxx(13.0, 9.4, INK)
    elif expr == 'ko':
        C.poly(hp([(2.2, 7.8), (10.6, 7.0), (11.2, 10.4), (3.2, 11.4)]), INK)
        C.poly(hp([(3.0, 7.9), (9.8, 7.4), (9.8, 8.8), (3.2, 9.4)]), PM['teeth']['b'])
        C.poly(hp([(5.2, 9.2), (8.6, 9.0), (8.0, 10.0), (5.8, 10.2)]), PM['tongue'])
        pxx(2.2, 7.8, INK)
    else:  # 狞笑露牙（idle / attack）：右嘴角上挑，整体靠前
        # 鼻翼到嘴角的狞笑褶皱
        pxx(12.0, 4.0, PM['skin_dd']['b'])
        pxx(12.7, 4.9, PM['skin_dd']['b'])
        pxx(13.1, 5.6, PM['skin_dd']['b'])
        # 墨线口腔
        C.poly(hp([(4.2, 10.4), (12.6, 7.0), (13.0, 9.4), (5.2, 12.0)]), INK)
        # 上排白牙（2px）
        C.poly(hp([(4.8, 10.0), (12.4, 7.2), (12.6, 8.8), (5.2, 11.2)]),
               PM['teeth']['b'])
        for tx in (6.6, 8.8, 10.8):
            C.rect(ox + tx, oy + 7.4, ox + tx, oy + 10.8, PM['teeth']['d'])
        C.rect(ox + 10.4, oy + 7.5, ox + 11.4, oy + 8.6, PM['yellow']['b'])
        # 下唇
        C.poly(hp([(5.2, 11.4), (12.9, 8.8), (13.3, 10.0), (6.0, 12.4)]),
               PM['skin_d']['b'])
        pxx(13.2, 8.2, PM['skin_dd']['b'])
        pxx(13.5, 7.2, PM['skin_dd']['b'])
        pxx(4.2, 10.4, INK)
        pxx(13.0, 9.4, INK)
        pxx(12.6, 7.0, PM['skin']['l'])
        pxx(11.6, 6.4, PM['skin_dd']['b'])

    # ================= 下巴 / 下颌 =================
    C.rect(ox + 4.0, oy + 14.4, ox + 8.4, oy + 15.6, PM['skin']['l'])
    C.poly(hp([(3.6, 13.2), (9.4, 13.4), (9.8, 14.2), (3.8, 14.0)]), PM['hollow']['d'])
    C.poly(hp([(0.4, 17.6), (3.0, 18.4), (7.0, 17.8), (10.6, 13.6), (10.9, 14.8),
               (7.2, 18.8), (2.6, 19.2), (0.2, 18.2)]), PM['skin_d']['d'])
    pxx(10.4, 11.0, PM['skin_dd']['d'])
    pxx(9.4, 13.0, PM['skin_dd']['d'])
    for (tx, ty) in ((-1.6, 15.6), (0.8, 16.8), (3.2, 17.4), (5.8, 16.6),
                     (7.8, 14.8), (-3.6, 13.8), (2, 12.8)):
        pxx(tx, ty, PM['hair']['b'])
    # 刀疤 + 缝线
    for (tx, ty) in ((9.4, 1.2), (8.9, 2.2), (8.4, 3.2), (7.9, 4.2)):
        pxx(tx, ty, PM['scar'])
    pxx(10.2, 1.8, PM['skin']['l'])
    pxx(8.2, 3.6, PM['skin_dd']['d'])
    # 额头高光（窄）
    C.poly(hp([(-6, -16), (-2, -19.5), (2, -19), (3.2, -17.4), (-1.6, -17.8),
               (-4.6, -15)]), PM['skin']['l'])
    # 眼下青色刺青
    for (tx, ty) in ((-4.6, 0.4), (-3.6, 1.4), (-2.6, 2.4)):
        pxx(tx, ty, PM['cyan']['b'])
    pxx(-3.6, 0.4, PM['cyan']['d'])
    # 污渍
    pxx(5.4, 2.4, PM['skin_dd']['b'])
    pxx(-2.2, 4.6, PM['skin_dd']['b'])

    C.neon_rim(left=0.5, right=0.55, top=0.3, bottom=0.45)

    img, origin = C.img, (ox, oy)
    if rot:
        img, origin = rotate_sprite(img, origin, rot)
    return img, origin


# ============================================================================
# PUNK 帧合成
# ============================================================================

def head_exclude_mask(C, head_img, pos):
    """把已经贴上的头部区域从轮廓光计算中排除（头部自带轮廓光）"""
    m = new_mask(C.size)
    alpha = head_img.getchannel('A').point(lambda v: 255 if v > 96 else 0)
    m.paste(alpha, (int(round(pos[0])), int(round(pos[1]))))
    return m


def render_frame(spec, pose, heads, debug_bbox=False):
    fw, fh = spec['frame']
    ax, ay = spec['anchor']
    P = fk(spec, pose)

    # 转成帧内坐标
    PF = {}
    for k, v in P.items():
        if isinstance(v, list):
            PF[k] = (ax + v[0], ay + v[1])
        else:
            PF[k] = v

    C = Canv((fw, fh))
    spec['draw_back'](C, PF, pose) if spec.get('draw_back') else None
    spec['draw_leg'](C, PF, pose, 'rear')
    spec['draw_arm'](C, PF, pose, 'rear')
    spec['draw_torso'](C, PF, pose)

    spec['draw_leg'](C, PF, pose, 'front')
    if spec.get('draw_after_legs'):
        spec['draw_after_legs'](C, PF, pose)

    # 头部
    head_img, horg = get_head(spec, pose, heads)
    hpos = (PF['head'][0] - horg[0], PF['head'][1] - horg[1])
    C.sprite(head_img, hpos)
    ex = head_exclude_mask(C, head_img, hpos)

    spec['draw_arm'](C, PF, pose, 'front')
    if spec.get('draw_arm_decor'):
        spec['draw_arm_decor'](C, PF, pose)

    # 霓虹轮廓光（排除头部，头部自带）
    rim = spec.get('rim', (0.52, 0.55, 0.30, 0.45))
    C.neon_rim(exclude=ex, left=rim[0], right=rim[1], top=rim[2], bottom=rim[3])

    if spec.get('front_extra'):
        spec['front_extra'](C, PF, pose)

    return C.img


# ============================================================================
# 动画数据
# ============================================================================

PUNK_ANIMS = {
    'idle': dict(fps=6, loop=True, frames=[
        dict(lean=8, fa=(26, 96), ra=(14, 88), fl=(8, -10, 0), rl=(-8, -11, 0), head_dy=0),
        dict(lean=9, fa=(27, 99), ra=(15, 91), fl=(9, -13, 0), rl=(-9, -13, 0), head_dy=-1),
        dict(lean=8.5, fa=(25, 95), ra=(13, 87), fl=(8, -11, 0), rl=(-8, -12, 0), head_dy=-0.5),
        dict(lean=7.5, fa=(24, 92), ra=(13, 85), fl=(7.5, -9, 0), rl=(-7.5, -10, 0), head_dy=0),
    ]),
    'walk': dict(fps=10, loop=True, frames=[
        dict(lean=10, fa=(-16, 42), ra=(30, 52), fl=(26, -8, -6), rl=(-24, -28, 14)),
        dict(lean=9, fa=(-6, 48), ra=(24, 46), fl=(22, -26, 0), rl=(-16, -40, 20)),
        dict(lean=8, fa=(6, 60), ra=(16, 50), fl=(8, -36, 0), rl=(2, -30, 6)),
        dict(lean=10, fa=(30, 52), ra=(-16, 42), fl=(-24, -28, 14), rl=(26, -8, -6)),
        dict(lean=9, fa=(24, 46), ra=(-6, 48), fl=(-16, -40, 20), rl=(22, -26, 0)),
        dict(lean=8, fa=(16, 50), ra=(6, 60), fl=(2, -30, 6), rl=(8, -36, 0)),
    ]),
    'attack': dict(fps=10, loop=False, frames=[
        dict(lean=-4, fa=(-38, 30), ra=(-20, 60), fl=(14, -18, 0), rl=(-16, -20, 0),
             expr='attack', weapon='dagger'),
        dict(lean=16, fa=(72, 16), ra=(-30, 40), fl=(30, -14, 0), rl=(-24, -16, 0),
             expr='attack', weapon='dagger'),
        dict(lean=20, fa=(92, 4), ra=(-34, 34), fl=(34, -8, 0), rl=(-28, -10, 0),
             expr='attack', weapon='dagger'),
        dict(lean=8, fa=(40, 60), ra=(-6, 62), fl=(16, -18, 0), rl=(-14, -20, 0),
             expr='attack', weapon='dagger'),
    ]),
    'hurt': dict(fps=10, loop=False, frames=[
        dict(lean=-20, fa=(-10, 64), ra=(42, 50), fl=(10, -22, 0), rl=(-22, -25, 0),
             head_dx=-2, head_dy=-1, expr='hurt'),
        dict(lean=-26, fa=(-22, 56), ra=(52, 44), fl=(6, -30, 0), rl=(-28, -30, 0),
             head_dx=-4, head_dy=-1, expr='hurt'),
    ]),
    'ko': dict(fps=8, loop=False, frames=[
        dict(lean=-24, fa=(-30, 40), ra=(56, 40), fl=(10, -18, 0), rl=(-14, -22, 0),
             head_dx=-4, head_dy=-3, expr='ko'),
        dict(lean=-40, fa=(-70, 30), ra=(80, 30), fl=(4, -36, -10), rl=(-6, -34, 6),
             grounded=False, pelvis_dy=14, hip_dx=-4, root_rot=-24, head_dx=-2, head_dy=-4, expr='ko'),
        dict(lean=-30, fa=(-80, 30), ra=(90, 20), fl=(-40, -50, -20), rl=(-50, -50, 10),
             grounded=False, pelvis_dy=48, hip_dx=4, root_rot=-62, head_rot=-90, expr='ko'),
        dict(lean=-6, fa=(-60, 40), ra=(60, 40), fl=(-68, -40, -20), rl=(-76, -40, 6),
             grounded=False, pelvis_dy=62, hip_dx=12, root_rot=-88, head_rot=-90, expr='ko'),
    ]),
}


# ============================================================================
# 调试预览
# ============================================================================

def checker_bg(w, h, cell=8, c1=(11, 7, 22), c2=(16, 11, 30)):
    a = np.zeros((h, w, 3), dtype=np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    chk = ((xx // cell + yy // cell) % 2).astype(bool)
    a[chk] = c1
    a[~chk] = c2
    return Image.fromarray(a, 'RGB').convert('RGBA')


def upscale(im, n):
    return im.resize((im.width * n, im.height * n), Image.Resampling.NEAREST)


def save_wip_char(spec, anims, heads, name):
    """生成单角色自查图：每个动画一行（2x），下方头部表情 3x + 单帧 3x"""
    fw, fh = spec['frame']
    rows = []
    for an, ad in anims.items():
        frames = [render_frame(spec, mk_pose(spec, **fr), heads) for fr in ad['frames']]
        strip = Image.new('RGBA', (fw * len(frames), fh), (0, 0, 0, 0))
        for i, im in enumerate(frames):
            strip.paste(im, (i * fw, 0))
        rows.append((an, strip, frames))
    head_imgs = []
    for expr in ('idle', 'attack', 'shout', 'hurt', 'ko'):
        hi, _ = make_head_fn(spec['name'])(expr)
        head_imgs.append((expr, hi))

    width = max(fw * max(len(ad['frames']) for ad in anims.values()) * 2, 1200) + 24
    height = sum(fh * 2 + 8 for _ in rows) + 60 + 3 * 66 * 3 + 40
    img = checker_bg(width, height)
    y = 20
    for an, strip, frames in rows:
        img.alpha_composite(upscale(strip, 2), (8, y))
        y += fh * 2 + 8

    # 头部表情 3x
    hx0, hy0 = 8, y
    for expr, hi in head_imgs:
        img.alpha_composite(upscale(hi, 3), (hx0, hy0))
        hx0 += hi.width * 3 + 10

    # 关键单帧 3x（idle 第 0 帧、attack 第 2 帧、ko 最后一帧）
    zx = hx0 + 16
    picks = [('idle', 0), ('attack', min(2, len(anims['attack']['frames']) - 1)),
             ('ko', len(anims['ko']['frames']) - 1)]
    zy = hy0
    for an, idx in picks:
        fr = render_frame(spec, mk_pose(spec, **anims[an]['frames'][idx]), heads)
        img.alpha_composite(upscale(fr, 3), (zx, zy))
        zx += fw * 3 + 10
        if zx > width - fw * 3:
            zx = 8
            zy += fh * 3 + 10

    path = os.path.join(WIP_DIR, '_wip_%s.png' % name)
    img.convert('RGB').save(path)
    print('WIP:', path)
    return path


# ============================================================================
# BRUTE 壮汉 —— 比例、材质、姿态
# ============================================================================

BRUTE = {
    'name': 'brute',
    'frame': (280, 280),
    'anchor': (140, 264),
    'bodyHeight': 216,
    'prop': dict(
        leg_len=84.0, thigh=40.0, shin=36.0, ankle_h=8.0,
        torso=86.0, neck=8.0, head_h=40.0, head_w=38.0,
        shoulder_w=88.0, waist_w=66.0, chest_w=82.0, hip_w=58.0,
        upper=32.0, fore=30.0, hand_r=8.5,
        shoulder_sep=17.0, hip_sep=17.0,
        head_canvas=84, head_origin=42,
    ),
    'stance': dict(
        lean=8.0, fa=(16.0, 20.0), ra=(-8.0, 26.0),
        fl=(14.0, -12.0, 0.0), rl=(-14.0, -13.0, 0.0),
        expr='idle',
    ),
}

BM = {
    'skin':    mk('#d8a06e', '#9c6848', '#f2c696'),
    'skin_d':  mk('#b8815c', '#7c5240', '#d8a06e'),
    'skin_dd': mk('#8f5f47', '#5e3a30', '#b8815c'),
    'hollow':  mk('#a87450', '#7a4a38', '#c48e66'),
    'beard':   mk('#4a3638', '#2a1d20', '#6c5252'),
    'stubble': mk('#6a4e48', '#46312f', '#8a6c60'),
    'tank':    mk('#8f8776', '#5e5a4c', '#b8b09a'),
    'tank2':   mk('#6d6658', '#484438', '#8f8776'),
    'pants':   mk('#6c6a4e', '#484634', '#8e8a68'),
    'pants2':  mk('#52503a', '#34321f', '#6c6a4e'),
    'boot':    mk('#3c3238', '#241e26', '#584c56'),
    'leather': mk('#6e4830', '#48301e', '#906440'),
    'steel':   mk('#9aa7c7', '#5d6b8f', '#d7e2f7'),
    'steel2':  mk('#6a7694', '#3c4664', '#9aa7c7'),
    'tattoo':  mk('#2c2232', '#18111e', '#443648'),
    'orange':  mk('#ff8a2a', '#a85a14', '#ffb060'),
    'yellow':  mk('#ffd23f', '#a87a18', '#fff0a0'),
    'white':   mk('#f2efe8', '#aaa6b8', '#ffffff'),
    'iris':    mk('#ffd23f', '#a8841a', '#fff6c0'),
    'teeth':   mk('#ddd8cc', '#9a968a', '#f6f2e6'),
    'mouth':   hx('#3c1420'),
    'mouth2':  hx('#64202c'),
    'tongue':  hx('#c03a4e'),
    'scar':    hx('#a04050'),
    'blood':   hx('#b0283c'),
    'band':    mk('#d8d2c0', '#9a9484', '#f0ecdc'),
}

B_SKULL = [(-11, -20), (-3, -21), (5, -20), (11, -17), (14, -13), (15, -8),
           (15, -4), (16, -1), (16.5, 1), (15, 3), (14, 5), (13, 8),
           (11, 11), (9, 14), (6, 16.5), (2, 18), (-2, 17), (-6, 15),
           (-10, 12), (-13, 9), (-16, 5), (-17, 1), (-16, -4), (-15, -10),
           (-14, -15), (-13, -18)]


def render_head_brute(expr='idle', rot=0):
    C = Canv((84, 84))
    ox = oy = 42

    def h(x, y):
        return (ox + x, oy + y)

    def hp(seq):
        return [h(x, y) for x, y in seq]

    def pxx(x, y, col):
        C.px(ox + x, oy + y, col)

    # 粗脖子 + 斜方肌
    C.limb([h(0, 13), h(-1, 30)], [21.0, 26.0], BM['skin_d'], band=1)
    C.poly(hp([(-11, 16), (11, 16), (13, 24), (-13, 24)]), BM['skin_d']['d'])
    C.poly(hp([(-10, 18), (2, 19), (1, 22), (-11, 21)]), BM['skin_dd']['d'])
    C.poly(hp([(-9, 14), (-10, 27), (-7, 29), (-7, 14)]), BM['skin']['l'])

    # 头骨
    skull_m = m_poly(C.size, hp(B_SKULL))
    C.part(skull_m, BM['skin'], band=2)

    # 光头：顶部高光 + 两侧刮青
    C.poly(hp([(-12, -12), (-6, -18), (2, -20), (9, -18), (11, -15), (3, -16),
               (-4, -15), (-10, -10)]), BM['skin']['l'])
    C.poly(hp([(-16, -3), (-14, -12), (-10, -17), (-6, -18), (-8, -14), (-12, -8),
               (-14, 0), (-15, 3)]), BM['stubble']['b'])
    C.poly(hp([(12, -12), (13, -3), (12, 4), (10, -5)]), BM['stubble']['d'])
    for (x, y) in ((-15, -6), (-14, -2), (-13, 2), (-12, -10), (12, -6), (13, 1), (4, -19)):
        pxx(x, y, BM['stubble']['d'])
    # 抬头纹
    C.rect(ox - 8, oy - 14, ox + 5, oy - 14, BM['skin_d']['d'])
    C.rect(ox - 7, oy - 12, ox + 6, oy - 12, BM['skin_d']['b'])
    C.rect(ox + 1, oy - 15, ox + 4, oy - 15, BM['skin_d']['b'])

    # 耳朵
    C.part(m_ellipse(C.size, ox - 15.0, oy + 3.0, 2.6, 4.2), BM['skin_d'], band=1)
    C.poly(hp([(-15.6, 1), (-14.8, 2.5), (-14.8, 4.8), (-16.2, 3.6)]), BM['skin_dd']['d'])

    wide = (expr == 'shout')
    shut = (expr in ('hurt', 'ko'))

    # 眼窝阴影（深）
    C.poly(hp([(3, -9), (12.5, -9.5), (13, -1), (3.5, -0.5)]), BM['skin_d']['d'])
    C.poly(hp([(-7, -8), (-1, -7.6), (-0.6, -1.4), (-7, -1.8)]), BM['skin_dd']['b'])

    # 眉毛（粗、压眼）
    if expr == 'hurt':
        C.poly(hp([(1.5, -12), (13, -10), (13, -8), (1.5, -10)]), INK)
        C.poly(hp([(-7.5, -9.5), (-0.8, -11), (-0.8, -9), (-7.5, -7.5)]), INK)
    elif expr == 'ko':
        C.poly(hp([(2, -11), (12.5, -9.6), (12.5, -8.6), (2, -10)]), INK)
        C.poly(hp([(-7.2, -9), (-0.8, -10), (-0.8, -8.4), (-7.2, -7.4)]), INK)
    else:
        C.poly(hp([(1.5, -11.5), (13.6, -9.2), (13.6, -7.0), (1.5, -9.2)]), INK)
        C.poly(hp([(-7.6, -9.6), (-0.8, -8.8), (-0.8, -7.0), (-7.6, -7.8)]), INK)
        pxx(0.4, -8.2, INK)

    # 眼睛（小而凶）
    if shut:
        if expr == 'hurt':
            C.poly(hp([(3.4, -5.4), (11.8, -4.2), (11.8, -3.0), (3.4, -4.2)]), INK)
            C.poly(hp([(-6.4, -4.4), (-1.4, -3.4), (-1.4, -2.2), (-6.4, -3.2)]), INK)
            pxx(8.8, -1.4, BM['skin_dd']['b'])
        else:
            C.poly(hp([(3.6, -4.6), (11.6, -4.2), (11.6, -3.2), (3.6, -3.6)]), INK)
            C.poly(hp([(-6.2, -4.0), (-1.4, -3.6), (-1.4, -2.6), (-6.2, -3.0)]), INK)
    else:
        C.poly(hp([(3.8, -7.0), (11.8, -7.6), (12.0, -2.6), (3.8, -2.2)]), INK)
        C.poly(hp([(4.4, -6.6), (11.4, -7.1), (11.6, -3.2), (4.4, -2.9)]), BM['white']['b'])
        C.rect(ox + 7.4, oy - 6.0, ox + 9.8, oy - 3.6, BM['iris']['b'])
        C.rect(ox + 8.2, oy - 5.4, ox + 9.8, oy - 4.0, INK)
        pxx(7.5, -5.9, BM['iris']['l'])
        C.poly(hp([(-6.8, -6.2), (-1.2, -6.8), (-1.0, -2.4), (-6.4, -2.0)]), INK)
        C.poly(hp([(-6.0, -5.8), (-1.8, -6.3), (-1.6, -2.9), (-5.6, -2.5)]),
               BM['white']['d'])
        C.rect(ox - 4.2, oy - 5.4, ox - 2.8, oy - 3.4, BM['iris']['d'])
        pxx(-3.4, -4.8, INK)

    # 断鼻（歪、塌）
    C.poly(hp([(8.6, -6), (12.4, -2.4), (14.6, 0.6), (13.2, 1.6), (9.4, -2.2)]),
           BM['skin_d']['b'])
    C.poly(hp([(9.2, -5.4), (12.2, -2.2), (14.0, 0.10), (13.2, 0.1), (10.0, -2.6)]),
           BM['skin']['l'])
    # 鼻头（扁平、宽）
    C.rect(ox + 12.4, oy + 0.8, ox + 15.4, oy + 2.2, BM['skin']['l'])
    pxx(13.0, 2.8, INK)
    pxx(14.4, 2.8, INK)
    C.rect(ox + 8.8, oy + 3.2, ox + 14.4, oy + 3.8, BM['skin_dd']['d'])
    C.rect(ox + 9.4, oy + 4.2, ox + 14.0, oy + 4.8, BM['hollow']['d'])
    # 鼻梁上的旧伤（歪鼻）
    pxx(11.0, -2.6, BM['blood'])
    pxx(11.4, -2.0, BM['blood'])
    pxx(10.6, -1.8, BM['scar'])
    # 鼻梁偏折产生的阴影
    C.rect(ox + 7.4, oy + 0.2, ox + 9.2, oy + 2.0, BM['hollow']['b'])

    # 胡茬络腮（实心深色 + 短竖线纹理，不是抖动噪点）
    C.poly(hp([(11, 6), (9.5, 11), (6.5, 14.5), (2, 16.5), (-2, 16), (-6, 14),
               (-9.5, 10.5), (-11.5, 7), (-10.5, 4), (-8, 8), (-4, 11.5), (0, 13),
               (5, 12.5), (8.5, 9.5), (9.8, 6.4)]), BM['stubble']['b'])
    for (x, y) in ((8.6, 8), (6.6, 10), (4.6, 11.4), (2.2, 12.4), (-0.4, 12.8),
                   (-3, 12.2), (-5.6, 11), (-7.8, 9.2), (-9.2, 7.4)):
        pxx(x, y, BM['stubble']['d'])
        pxx(x + 0.6, y - 1.4, BM['beard']['b'])
    # 下巴浓密胡
    C.poly(hp([(6.5, 13.5), (4, 16.6), (0, 17.8), (-4, 16.8), (-7.5, 13.8),
               (-5, 13.2), (-1, 14.6), (3.5, 14.4)]), BM['beard']['b'])
    for (x, y) in ((3.4, 15.2), (1.4, 15.8), (-0.8, 15.6), (-3, 14.8), (4.6, 14.8)):
        pxx(x, y, BM['beard']['d'])
    # 上唇胡
    C.poly(hp([(1.6, 6.4), (11.6, 5.4), (12, 6.8), (2, 8.2)]), BM['beard']['b'])
    for x in (3, 5.2, 7.4, 9.6):
        pxx(x, 6.6, BM['beard']['d'])
    # 刀疤（左眉）
    for (x, y) in ((-6.4, -12), (-5.6, -10.4), (-4.8, -8.8), (-4.2, -7.6)):
        pxx(x, y, BM['scar'])
    pxx(-5.0, -9.6, BM['skin']['l'])

    # 嘴（吼叫 / 咬牙 / 闭合）
    if expr == 'shout':
        C.poly(hp([(1.0, 6.0), (12.2, 4.6), (13.2, 9.6), (2.2, 11.8)]), INK)
        C.poly(hp([(1.8, 6.2), (11.8, 5.2), (12.0, 7.0), (2.2, 8.0)]), BM['teeth']['b'])
        C.poly(hp([(2.6, 10.0), (12.0, 8.8), (12.2, 10.6), (2.8, 11.4)]), BM['teeth']['b'])
        C.poly(hp([(3.8, 8.0), (10.4, 7.2), (9.6, 9.6), (4.6, 10.0)]), BM['tongue'])
        for tx in (4.2, 6.8, 9.4):
            pxx(tx, 5.8, BM['teeth']['d'])
            pxx(tx, 6.6, BM['teeth']['d'])
            pxx(tx, 9.8, BM['teeth']['d'])
            pxx(tx, 10.4, BM['teeth']['d'])
        pxx(1.0, 6.0, INK)
        pxx(13.2, 9.6, INK)
    elif expr == 'hurt':
        C.poly(hp([(1.8, 6.8), (11.8, 5.8), (12.2, 9.0), (3.0, 10.8)]), INK)
        C.poly(hp([(2.4, 7.0), (11.4, 6.2), (11.4, 8.0), (2.8, 9.2)]), BM['teeth']['b'])
        for tx in (4.4, 7.2, 9.8):
            C.rect(ox + tx, oy + 6.4, ox + tx, oy + 8.6, BM['teeth']['d'])
    elif expr == 'ko':
        C.poly(hp([(2.6, 8.0), (10.4, 7.4), (11.0, 10.4), (3.4, 11.2)]), INK)
        C.poly(hp([(3.4, 8.2), (9.6, 7.8), (9.6, 9.2), (3.6, 9.8)]), BM['teeth']['b'])
        C.poly(hp([(5.4, 9.4), (8.8, 9.2), (8.2, 10.2), (6.0, 10.4)]), BM['tongue'])
    else:  # idle：咬牙切齿
        C.poly(hp([(2.2, 7.0), (11.8, 6.2), (12.2, 9.2), (3.0, 10.2)]), INK)
        C.poly(hp([(2.8, 7.2), (11.4, 6.6), (11.6, 8.4), (3.0, 9.2)]), BM['teeth']['b'])
        for tx in (4.4, 6.8, 9.2):
            C.rect(ox + tx, oy + 6.8, ox + tx, oy + 8.8, BM['teeth']['d'])
        pxx(12.4, 9.2, INK)
        pxx(2.2, 7.0, INK)
        # 下唇 + 下巴
        C.poly(hp([(3.0, 9.8), (11.8, 8.6), (12.0, 9.8), (3.4, 10.6)]),
               BM['skin_d']['d'])

    # 下巴 / 下颌
    C.poly(hp([(5.0, 15.8), (9.0, 16.0), (7.6, 17.6), (4.4, 17.2)]), BM['skin']['l'])
    C.poly(hp([(0, 16.6), (5, 17.4), (10.6, 12.4), (10.8, 14.2), (6.4, 18.2), (0, 18) ]),
           BM['skin_dd']['d'])
    pxx(10.2, 11.6, BM['skin_dd']['d'])
    pxx(9.0, 14.4, BM['skin_dd']['d'])

    C.neon_rim(left=0.5, right=0.55, top=0.3, bottom=0.45)

    img, origin = C.img, (ox, oy)
    if rot:
        img, origin = rotate_sprite(img, origin, rot)
    return img, origin


# ---------------------------------------------------------------------------
# BRUTE 身体
# ---------------------------------------------------------------------------

def brute_leg(canv, P, pose, side):
    far = (side == 'rear')
    prefix = 'rl' if far else 'fl'
    pants = mat_far(BM['pants'], 0.72) if far else BM['pants']
    pants2 = mat_far(BM['pants2'], 0.72) if far else BM['pants2']
    boot = mat_far(BM['boot'], 0.72) if far else BM['boot']
    steel = mat_far(BM['steel'], 0.8) if far else BM['steel']
    hip, knee, ankle = P[prefix + '_hip'], P[prefix + '_knee'], P[prefix + '_ankle']
    foot_ang = P['fl_foot'] if side == 'front' else P['rl_foot']

    canv.limb([hip, lerp_pt(hip, knee, 0.55), knee], [30.0, 27.0, 23.0], pants, band=2)
    canv.limb([knee, lerp_pt(knee, ankle, 0.5), ankle], [23.0, 20.0, 17.0], pants, band=2)
    # 侧袋 / 补丁
    if not far:
        px, py = lerp_pt(hip, knee, 0.55)
        canv.part(m_ellipse(canv.size, px - 6, py, 6.0, 7.0), pants2, outline=True, band=1)
        canv.rect(px - 9, py - 2, px - 3, py - 1, pants2['l'])
    # 护膝
    canv.part(m_ellipse(canv.size, knee[0], knee[1], 7.0, 6.0), BM['leather'], band=1)
    canv.poly([(knee[0] - 6, knee[1] - 2), (knee[0] + 6, knee[1] - 2),
               (knee[0] + 5, knee[1] + 2), (knee[0] - 7, knee[1] + 2)], BM['leather']['l'])
    # 裤脚翻边
    canv.limb([lerp_pt(knee, ankle, 0.84), ankle], [19.0, 18.0], pants2, outline=False, band=0)
    # 大头皮靴（铁头）
    boot_pts = [(-9, -4), (5, -4), (10, -1), (15, 0), (17, 4), (13, 7), (-9, 7), (-11, 3)]
    bmask = m_poly(canv.size, foot_poly(ankle, foot_ang, boot_pts))
    canv.part(bmask, boot, band=1)
    toe = foot_poly(ankle, foot_ang, [(9, -1), (15, 0), (17, 4), (13, 6), (10, 4)])
    canv.part(m_poly(canv.size, toe), steel, outline=False, band=0)
    sole = foot_poly(ankle, foot_ang, [(-9, 6), (13, 7), (13, 8.4), (-9, 7.4)])
    canv.poly(sole, INK)
    # 靴带
    for yy in (0.5, 2.2):
        strap = foot_poly(ankle, foot_ang, [(-6, yy), (6, yy - 1), (6.5, yy + 0.6), (-6, yy + 1.4)])
        canv.poly(strap, BM['steel2']['d'])


def brute_arm(canv, P, pose, side):
    far = (side == 'rear')
    prefix = 'ra' if far else 'fa'
    skin = mat_far(BM['skin'], 0.74) if far else BM['skin']
    skin_d = mat_far(BM['skin_d'], 0.74) if far else BM['skin_d']
    tattoo = mat_far(BM['tattoo'], 0.8) if far else BM['tattoo']
    sh, el, hand = P[prefix + '_shoulder'], P[prefix + '_elbow'], P[prefix + '_hand']
    open_hand = pose['ra_open'] if far else pose['fa_open']

    # 肱二头肌 / 前臂（粗壮）
    canv.limb([sh, lerp_pt(sh, el, 0.5), el], [28.0, 25.0, 22.0], skin, band=2)
    canv.limb([el, lerp_pt(el, hand, 0.5), hand], [21.0, 19.0, 17.0], skin, band=2)
    canv.part(m_ellipse(canv.size, el[0], el[1], 10.0, 10.0), skin_d, outline=False, band=0)
    # 虎纹刺青（近侧上臂）
    if not far:
        dx = el[0] - sh[0]
        dy = el[1] - sh[1]
        L = math.hypot(dx, dy) or 1
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        for i in (0.30, 0.48, 0.66):
            cx, cy = sh[0] + dx * i, sh[1] + dy * i
            canv.poly([(cx - nx * 7, cy - ny * 7),
                       (cx - nx * 7 + ux * 2.5, cy - ny * 7 + uy * 2.5),
                       (cx + nx * 7 + ux * 2.0, cy + ny * 7 + uy * 2.0),
                       (cx + nx * 7, cy + ny * 7)], tattoo['b'])
        # 虎纹橙色点缀
        for i in (0.33, 0.51):
            cx, cy = sh[0] + dx * i, sh[1] + dy * i
            canv.px(cx + nx * 4 + ux * 1.5, cy + ny * 4 + uy * 1.5, BM['orange']['d'])
    # 护腕绑带
    wdir = (hand[0] - el[0], hand[1] - el[1])
    L = math.hypot(*wdir) or 1.0
    wdir = (wdir[0] / L, wdir[1] / L)
    nrm = (-wdir[1], wdir[0])
    for t in (0.62, 0.78):
        cx, cy = el[0] + (hand[0] - el[0]) * t, el[1] + (hand[1] - el[1]) * t
        m = m_chain(canv.size, [(cx - nrm[0] * 2, cy - nrm[1] * 2),
                                (cx + nrm[0] * 2, cy + nrm[1] * 2)], [20.0, 20.0])
        canv.part(m, BM['band'], outline=False, band=0)
    # 拳
    ang = math.degrees(math.atan2(hand[0] - el[0], hand[1] - el[1]))
    fist(canv, hand, ang, BRUTE['prop']['hand_r'], skin, open_hand=open_hand)
    # 指节绑带
    kx = hand[0] + wdir[0] * 3
    ky = hand[1] + wdir[1] * 3
    canv.px(kx - nrm[0] * 3 + wdir[0] * 1.5, ky - nrm[1] * 3 + wdir[1] * 1.5, BM['band']['b'])
    canv.px(kx + nrm[0] * 3 + wdir[0] * 1.5, ky + nrm[1] * 3 + wdir[1] * 1.5, BM['band']['b'])


def brute_torso(canv, P, pose):
    prop = BRUTE['prop']
    pel = P['pelvis']
    sh = P['shoulder']
    # 骨盆 / 工装裤
    canv.limb([bp(P, 6, 0), bp(P, -12, 0)], [60.0, 56.0], BM['pants'], band=2)
    # 大皮带
    canv.limb([bp(P, 4, 0), bp(P, -2, 0)], [62.0, 62.0], BM['leather'], outline=False, band=0)
    buckle = bp(P, 1, 8)
    canv.part(m_rect(canv.size, buckle[0] - 5, buckle[1] - 4, buckle[0] + 5, buckle[1] + 4),
              BM['steel'], band=1)
    canv.rect(buckle[0] - 2, buckle[1] - 2, buckle[0] + 2, buckle[1] + 2, BM['yellow']['b'])

    # 斜方肌 / 肩部皮肤
    canv.part(m_poly(canv.size, bp_pts(P, [(46, -20), (50, -12), (52, 0), (54, 12),
                                          (52, 20), (48, 14), (44, 0), (44, -10)])),
              BM['skin_d'], band=2)
    # 背心躯干（大肚）
    torso_pts = bp_pts(P, [(0, 0), (18, 0), (34, 0), (48, 0), (55, 0)])
    torso_w = [56.0, 62.0, 68.0, 76.0, 70.0]
    torso_m = m_chain_flat(canv.size, torso_pts, torso_w)
    canv.part(torso_m, BM['tank'], band=2)
    # 背心领口 / 肩带
    strap = m_poly(canv.size, bp_pts(P, [(55, 4), (52, 12), (50, 24), (36, 26),
                                        (34, 18), (40, 8), (48, 2)]))
    canv.part(strap, BM['tank2'], outline=True, band=1)
    # 领口皮肤
    C_neck = bp(P, 54, 0)
    canv.part(m_ellipse(canv.size, C_neck[0], C_neck[1], 13.0, 6.0), BM['skin_d'], band=1)
    # 背心褶皱 + 污渍
    canv.poly(bp_pts(P, [(30, -10), (34, 10), (32, 14), (28, -8)]), BM['tank2']['d'])
    canv.poly(bp_pts(P, [(18, -8), (22, 8), (20, 12), (16, -6)]), BM['tank2']['b'])
    for (a, s) in ((20, 6), (26, -4), (38, 8), (14, -12)):
        q = bp(P, a, s)
        canv.px(q[0], q[1], BM['tank2']['d'])
    # 大肚轮廓高光
    canv.poly(bp_pts(P, [(8, 18), (20, 26), (30, 24), (26, 18), (14, 14)]), BM['tank']['l'])
    # 脖子
    canv.limb([bp(P, 52, 0), bp(P, 64, -1)], [20.0, 18.0], BM['skin_d'], band=1)
    # 背部/斜方肌隆起（从后颈到双肩的厚实三角肌群）
    canv.part(m_poly(canv.size, bp_pts(P, [(66, -16), (64, 6), (58, 16), (52, 12),
                                          (54, -2), (58, -12)])), BM['skin_d'], band=2)
    canv.part(m_poly(canv.size, bp_pts(P, [(66, 16), (64, -4), (58, -14), (53, -10),
                                          (55, 4), (58, 14)])), BM['skin_d'], band=2)


def brute_after_legs(canv, P, pose):
    # 背心下摆
    for (a, s) in ((0, -30), (-1, -20), (-1, 20), (0, 30)):
        q = bp(P, a, s)
        canv.px(q[0], q[1], BM['tank2']['d'])


def brute_front_extra(canv, P, pose):
    pass


BRUTE_ANIMS = {
    'idle': dict(fps=5, loop=True, frames=[
        dict(lean=10, fa=(34, 34), ra=(22, 30), fl=(10, -12, 0), rl=(-10, -13, 0), expr='idle'),
        dict(lean=12, fa=(36, 38), ra=(24, 33), fl=(11, -15, 0), rl=(-11, -15, 0), head_dy=-1),
        dict(lean=11, fa=(35, 36), ra=(23, 31), fl=(10.5, -13.5, 0), rl=(-10.5, -14, 0), head_dy=-0.5),
        dict(lean=9, fa=(33, 32), ra=(21, 28), fl=(9.5, -11, 0), rl=(-9.5, -12, 0), head_dy=0),
    ]),
    'walk': dict(fps=8, loop=True, frames=[
        dict(lean=12, fa=(-8, 34), ra=(46, 30), fl=(30, -10, 0), rl=(-28, -30, 0), expr='idle'),
        dict(lean=11, fa=(2, 40), ra=(38, 26), fl=(24, -28, 0), rl=(-18, -42, 0)),
        dict(lean=10, fa=(14, 44), ra=(28, 26), fl=(8, -38, 0), rl=(0, -34, 0)),
        dict(lean=12, fa=(46, 30), ra=(-8, 34), fl=(-28, -30, 0), rl=(30, -10, 0)),
        dict(lean=11, fa=(38, 26), ra=(2, 40), fl=(-18, -42, 0), rl=(24, -28, 0)),
        dict(lean=10, fa=(28, 26), ra=(14, 44), fl=(0, -34, 0), rl=(8, -38, 0)),
    ]),
    'attack': dict(fps=9, loop=False, frames=[
        dict(lean=-8, fa=(-34, 48), ra=(58, 40), fl=(6, -18, 0), rl=(-18, -22, 0), expr='shout'),
        dict(lean=10, fa=(10, 62), ra=(40, 44), fl=(24, -16, 0), rl=(-24, -18, 0), expr='shout'),
        dict(lean=22, fa=(86, 8), ra=(-24, 40), fl=(34, -10, 0), rl=(-30, -12, 0), expr='shout'),
        dict(lean=24, fa=(104, 4), ra=(-32, 34), fl=(36, -8, 0), rl=(-32, -10, 0), expr='shout'),
        dict(lean=12, fa=(52, 40), ra=(-6, 46), fl=(18, -20, 0), rl=(-18, -22, 0), expr='idle'),
    ]),
    'hurt': dict(fps=8, loop=False, frames=[
        dict(lean=-18, fa=(-6, 58), ra=(46, 44), fl=(12, -24, 0), rl=(-24, -26, 0),
             head_dx=-2, head_dy=-1, expr='hurt'),
        dict(lean=-24, fa=(-16, 52), ra=(56, 38), fl=(8, -30, 0), rl=(-30, -30, 0),
             head_dx=-4, head_dy=-1, expr='hurt'),
    ]),
    'ko': dict(fps=7, loop=False, frames=[
        dict(lean=-22, fa=(-24, 46), ra=(58, 40), fl=(10, -18, 0), rl=(-16, -24, 0),
             head_dx=-4, head_dy=-2, expr='ko'),
        dict(lean=-38, fa=(-60, 34), ra=(80, 30), fl=(4, -34, -8), rl=(-8, -32, 4),
             grounded=False, pelvis_dy=16, hip_dx=-6, root_rot=-26, head_dx=-2, head_dy=-4,
             expr='ko'),
        dict(lean=-28, fa=(-72, 30), ra=(92, 22), fl=(-38, -52, -16), rl=(-48, -52, 8),
             grounded=False, pelvis_dy=56, hip_dx=20, root_rot=-64, head_rot=-90, expr='ko'),
        dict(lean=-4, fa=(-58, 40), ra=(62, 40), fl=(-72, -44, -18), rl=(-80, -44, 6),
             grounded=False, pelvis_dy=74, hip_dx=28, root_rot=-88, head_rot=-90, expr='ko'),
    ]),
}

# ============================================================================
# BOSS 铁面 IRON MASK —— 鬼面铁面具 + 黑红大衣 + 机械义肢
# ============================================================================

BOSS = {
    'name': 'boss',
    'frame': (340, 340),
    'anchor': (170, 322),
    'bodyHeight': 250,
    'prop': dict(
        leg_len=102.0, thigh=47.0, shin=45.0, ankle_h=10.0,
        torso=100.0, neck=5.0, head_h=42.0, head_w=40.0,
        shoulder_w=76.0, waist_w=64.0, chest_w=74.0, hip_w=60.0,
        upper=40.0, fore=38.0, hand_r=8.0,
        shoulder_sep=8.0, hip_sep=6.0,
        head_canvas=84, head_origin=42,
    ),
    'stance': dict(
        lean=4.0, fa=(20.0, 64.0), ra=(12.0, 54.0),
        fl=(6.0, -8.0, 0.0), rl=(-6.0, -9.0, 0.0),
        expr='idle',
    ),
}

XM = {
    'coat':    mk('#52263f', '#321528', '#74385a'),
    'coat2':   mk('#3c1a30', '#22101e', '#52263f'),
    'lining':  mk('#e02a52', '#8a1434', '#ff5f80'),
    'steel':   mk('#8a9cbe', '#56648a', '#c8d6ee'),
    'steel_l': mk('#c8d6ee', '#8a9cbe', '#eef4ff'),
    'steel_d': mk('#56648a', '#333c5c', '#8a9cbe'),
    'dark':    mk('#3a3852', '#221f34', '#5a5878'),
    'mask':    mk('#d6cdc0', '#968a7c', '#f6eee2'),
    'mask_d':  mk('#968a7c', '#645a50', '#bcb2a4'),
    'rust':    mk('#8a4a3a', '#5a2a24', '#b06a4a'),
    'red':     mk('#ff4a68', '#b01e5e', '#ffab80'),
    'red_d':   mk('#c02040', '#70102a', '#ff3b5c'),
    'human':   mk('#c99a7a', '#8a5c50', '#eec0a0'),
    'human_d': mk('#8a5c50', '#5e3a36', '#c99a7a'),
    'cyan':    mk('#3df3ff', '#1a8ca8', '#b8fbff'),
    'magenta': mk('#ff2f8e', '#a11856', '#ff8ab8'),
    'gold':    mk('#ffd23f', '#a87a18', '#fff0a0'),
    'white':   mk('#f2efe8', '#aaa6b8', '#ffffff'),
    'glow_red': hx('#ff2f4a'),
    'glow_hot': hx('#ffb070'),
    'white_hot': hx('#fff2d8'),
    'sigil':   hx('#ff3058'),
    'sigil_hi': hx('#ff8a90'),
    'crack':   hx('#3a2c30'),
    'mouth':   hx('#2a0e16'),
}

X_MASK = [(-11, -21), (-3, -22), (4, -21), (10, -18), (14, -14), (16, -9),
          (17, -4), (17, 1), (16, 5), (15, 8), (13, 11), (11, 14),
          (8, 16), (5, 17.5), (1, 18.5), (-2, 18), (-5, 16), (-8, 13),
          (-11, 10), (-14, 7), (-16, 3), (-17, -2), (-16, -8), (-15, -13),
          (-14, -17), (-13, -20)]

X_HORN_FAR = [(-13, -17), (-19, -20), (-24, -25), (-25, -23), (-21, -19), (-15, -14)]
X_HORN_NEAR = [(8, -19), (13, -22), (16, -25), (17, -23), (14, -20), (11, -16)]

X_COLLAR_L = [(-20, 8), (-17, -2), (-10, -7), (-8, 4), (-10, 20), (-20, 22), (-19, 14)]
X_COLLAR_R = [(13, 9), (15, -3), (9, -8), (7, 3), (9, 20), (15, 22)]


def render_head_boss(expr='idle', rot=0):
    C = Canv((84, 84))
    ox = oy = 42

    def h(x, y):
        return (ox + x, oy + y)

    def hp(seq):
        return [h(x, y) for x, y in seq]

    def pxx(x, y, col):
        C.px(ox + x, oy + y, col)

    wide = (expr == 'shout')
    shut = (expr in ('hurt', 'ko'))

    # ================= 立领（大衣后领） =================
    C.part(m_poly(C.size, hp(X_COLLAR_L)), XM['coat'], band=1)
    C.part(m_poly(C.size, hp(X_COLLAR_R)), XM['coat'], band=1)
    C.poly(hp([(-19, 4), (-17, -1), (-11, -5), (-11, 2), (-15, 10), (-18, 16)]),
           XM['lining']['b'])
    C.poly(hp([(12, 5), (13.5, -1), (9, -5), (8.5, 1), (11, 10)]), XM['lining']['b'])
    for (x, y) in ((-16, 8), (-14, 14), (11, 12)):
        pxx(x, y, XM['steel']['b'])

    # ================= 脖子（面具下的颈部护甲） =================
    C.limb([h(0, 14), h(-0.5, 32)], [20.0, 24.0], XM['dark'], band=1)
    C.poly(hp([(-8, 15), (8, 15), (9, 21), (-8, 21)]), XM['dark']['d'])
    for (x, y) in ((-5, 19), (0, 19), (5, 19)):
        pxx(x, y, XM['steel_d']['b'])

    # ================= 犄角 =================
    C.part(m_poly(C.size, hp(X_HORN_FAR)), XM['mask_d'], band=1)
    C.poly(hp([(-20, -21), (-24, -24), (-24.5, -23), (-21, -20)]), XM['mask']['l'])
    # 面具
    C.part(m_poly(C.size, hp(X_MASK)), XM['mask'], band=3)
    C.part(m_poly(C.size, hp(X_HORN_NEAR)), XM['mask'], band=1)
    C.poly(hp([(12, -22), (15, -24), (15.5, -23), (13, -21)]), XM['mask']['l'])
    # 角上的红色裂纹
    for (x, y) in ((-20, -20), (-19, -19), (-18, -18), (12, -20), (13, -19)):
        pxx(x, y, XM['sigil'])

    # 面具暗部（右侧阴影）
    C.poly(hp([(11, -18), (16, -11), (17, -4), (15, 6), (12, 12), (8, 16), (5, 18),
               (9, 14), (13, 9), (15, 3), (16, -4), (14, -12)]), XM['mask_d']['b'])
    C.poly(hp([(-16, -8), (-13, -17), (-8, -20), (-10, -15), (-14, -8), (-15, 2)]),
           XM['mask_d']['d'])

    # ================= 额头纹样（红色鬼纹 + 青点） =================
    C.poly(hp([(-6, -19), (-4, -19), (-4, -12), (-6, -12)]), XM['sigil'])
    C.poly(hp([(-2, -19), (0, -19), (0, -12.5), (-2, -12.5)]), XM['sigil'])
    C.poly(hp([(2, -18), (3.5, -18), (3.5, -13), (2, -13)]), XM['sigil'])
    C.rect(ox - 7, oy - 16, ox + 4, oy - 15, XM['sigil'])
    C.rect(ox - 6, oy - 18.5, ox - 4, oy - 17.5, XM['sigil_hi'])
    pxx(5, -16, XM['cyan']['b'])
    pxx(5, -14.5, XM['cyan']['d'])

    # ================= 眼部（发光红眼） =================
    # 眼窝（深）
    C.poly(hp([(3, -10.5), (14, -11), (14.5, -3.5), (4, -3)]), XM['crack'])
    C.poly(hp([(-13, -9.5), (-2, -10), (-1.6, -3.5), (-12.6, -3)]), XM['crack'])
    if not shut:
        # 近眼（右）红焰
        C.poly(hp([(5, -9), (13, -9.5), (13.5, -5), (5.5, -4.5)]), XM['red']['b'])
        C.poly(hp([(6.5, -8.5), (12, -8.8), (12.4, -5.6), (7, -5.4)]), XM['glow_hot'])
        C.rect(ox + 8, oy - 7.5, ox + 10.6, oy - 6, XM['white_hot'])
        pxx(11.4, -7.6, XM['white_hot'])
        pxx(12.2, -6.6, XM['glow_hot'])
        # 远眼（左）
        C.poly(hp([(-12, -8.6), (-3, -9), (-2.8, -5), (-11.6, -4.6)]), XM['red_d']['b'])
        C.poly(hp([(-10.6, -8.2), (-4, -8.4), (-3.8, -5.6), (-10.2, -5.4)]),
               XM['red']['b'])
        C.rect(ox - 8, oy - 7.6, ox - 5.4, oy - 6.4, XM['glow_hot'])
        pxx(-5.2, -7, XM['white_hot'])
    else:
        # 熄灭/断续的眼神
        C.rect(ox + 5.5, oy - 6.5, ox + 12.5, oy - 5, XM['crack'])
        C.rect(ox - 11.5, oy - 6.2, ox - 3, oy - 5, XM['crack'])
        pxx(8.4, -6.2, XM['red_d']['b'])
        if expr == 'ko':
            pxx(9.6, -6.4, XM['red_d']['d'])
        else:
            pxx(9.6, -6.4, XM['red']['d'])

    # 眉骨（棱线）
    C.poly(hp([(2, -12.5), (15, -13), (15, -11), (2, -10.8)]), XM['mask_d']['d'])
    C.poly(hp([(-14, -11), (-1.5, -12), (-1.5, -10), (-14, -9.5)]), XM['mask_d']['d'])
    C.poly(hp([(2, -12), (14, -12.4), (14, -11.8), (2, -11.4)]), XM['mask']['l'])
    C.poly(hp([(-13, -10.6), (-2, -11.4), (-2, -10.9), (-13, -10.1)]), XM['mask']['l'])

    # ================= 鼻梁护甲 =================
    C.poly(hp([(7.5, -6), (11, -1), (12.4, 3), (10.6, 3.4), (7.4, -1.6)]),
           XM['mask_d']['b'])
    C.poly(hp([(8.4, -6), (11.2, -1.6), (12.2, 2), (11.4, 2), (8.8, -2)]),
           XM['mask']['l'])
    pxx(12.6, 3.2, XM['steel_d']['b'])
    pxx(6.6, 2.8, XM['mask_d']['d'])

    # ================= 面颊护板 + 铆钉 + 裂纹 =================
    for (x, y) in ((12, 5), (13, 8), (10, 11), (-12, 5), (-10, 9)):
        pxx(x, y, XM['steel']['l'])
        pxx(x + 1, y + 1, XM['steel_d']['d'])
    # 裂纹
    for (x, y) in ((13, -3), (14, 0), (13.4, 3), (12.6, 6)):
        pxx(x, y, XM['crack'])
    for (x, y) in ((1.6, -20), (2.4, -17), (1.2, -14)):
        pxx(x, y, XM['crack'])
    for (x, y) in ((-9, 6), (-8, 8), (-9.6, 10)):
        pxx(x, y, XM['crack'])
    # 锈斑
    for (x, y) in ((-6, 2), (-5, 4), (-13, -2), (5, -15), (-14, 8)):
        pxx(x, y, XM['rust']['b'])
    pxx(-5.6, 4.8, XM['rust']['l'])

    # ================= 嘴部铁栅 / 獠牙（獠牙是面具的一部分） =================
    if expr in ('shout', 'roar'):
        # 咆哮：张开的铁口，红光
        C.poly(hp([(0.5, 6.0), (12.6, 5.2), (13.2, 12.6), (1.6, 13.4)]), INK)
        C.poly(hp([(1.6, 6.6), (12.0, 5.8), (12.4, 11.8), (2.4, 12.6)]), XM['mouth'])
        C.poly(hp([(2.4, 7.4), (11.6, 6.8), (11.8, 10.8), (3.0, 11.4)]),
               XM['red_d']['d'])
        # 上獠牙
        for tx in (2.6, 5.6, 8.6, 11.2):
            C.poly(hp([(tx, 6.4), (tx + 1.4, 6.4), (tx + 0.6, 9.8)]), XM['mask']['l'])
            pxx(tx + 2, 6.6, XM['mask_d']['d'])
        # 下牙
        for tx in (4.0, 7.0, 10.0):
            pxx(tx, 11.6, XM['mask']['l'])
            pxx(tx + 1, 11.6, XM['mask_d']['l'])
        # 口腔亮光
        C.rect(ox + 4, oy + 9.4, ox + 9, oy + 10.2, XM['glow_hot'])
    else:
        # 闭合：横向铁栅 + 小獠牙
        C.rect(ox + 2, oy + 8, ox + 12.6, oy + 9.4, INK)
        C.rect(ox + 2.6, oy + 8.2, ox + 12.0, oy + 8.9, XM['mask_d']['d'])
        for tx in (3.4, 6.0, 8.6, 11.0):
            pxx(tx, 8.6, XM['mask_d']['l'])
        for (x, y) in ((4.2, 9.4), (8.2, 9.4)):
            pxx(x, y, XM['mask']['l'])
            pxx(x, y + 0.6, XM['mask_d']['l'])
        C.poly(hp([(1.4, 7.4), (12.8, 7.2), (12.8, 8.0), (1.4, 8.2)]),
               XM['mask_d']['b'])
        if expr == 'hurt':
            for (x, y) in ((5, 7.6), (9, 7.8), (11, 7.4)):
                pxx(x, y, XM['crack'])
        elif expr == 'ko':
            C.rect(ox + 4, oy + 8.4, ox + 10, oy + 9.6, XM['mouth'])
            pxx(6.6, 9.0, XM['mask']['l'])

    # ================= 面具下的人类下颌 + 伤疤 =================
    C.part(m_poly(C.size, hp([(2.5, 16.5), (8.5, 15.5), (10.5, 17), (9.0, 20), (5.0, 21), (1.5, 19.5)])), XM['human'], band=1)
    C.poly(hp([(2.5, 16.5), (8.5, 15.5), (7.8, 16.6), (2.9, 17.6)]), XM['human_d']['b'])
    C.poly(hp([(5.0, 19.2), (9.0, 17.8), (9.4, 18.6), (5.6, 20.0)]), XM['human']['l'])
    # 面具下缘的暗边
    C.poly(hp([(1.0, 16.2), (10.0, 14.8), (10.6, 15.6), (1.4, 17.2)]), INK)
    # 下巴伤疤
    for (x, y) in ((6.2, 17.6), (7.0, 18.4), (7.8, 19.2)):
        pxx(x, y, XM['sigil'])
    pxx(8.6, 18.0, XM['human']['l'])

    # 面具边缘高光 / 暗边
    C.poly(hp([(-13, -17), (-8, -20), (-3, -21), (-9, -18.5), (-13.5, -15)]),
           XM['mask']['l'])
    C.poly(hp([(-15, -6), (-16, 1), (-15, 5), (-13.8, 2), (-14, -4)]), XM['mask']['l'])

    C.neon_rim(left=0.45, right=0.5, top=0.26, bottom=0.38)

    # ================= 眼部 / 口腔辉光（叠加，不参与描边） =================
    glow = Image.new('RGBA', C.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    if not shut:
        gd.ellipse([ox + 4, oy - 12, ox + 16, oy - 2], fill=rgba(XM['glow_red'], 60))
        gd.ellipse([ox - 15, oy - 11, ox - 1, oy - 2], fill=rgba(XM['glow_red'], 44))
        gd.ellipse([ox + 6, oy - 9.5, ox + 13, oy - 4], fill=rgba(XM['glow_hot'], 70))
    if expr in ('shout', 'roar'):
        gd.ellipse([ox - 2, oy + 3, ox + 17, oy + 17], fill=rgba(XM['glow_red'], 80))
        gd.ellipse([ox + 1, oy + 6, ox + 13, oy + 14], fill=rgba(XM['glow_hot'], 90))
        # 向外喷出的红光射线
        rays = [(-6, 17), (4, 20), (14, 19), (20, 12), (22, 2), (-14, 13), (-18, 5)]
        for i, (tx, ty) in enumerate(rays):
            gd.rectangle([ox + tx, oy + ty, ox + tx + 1, oy + ty + 4],
                         fill=rgba(XM['glow_red'], max(30, 110 - i * 12)))
    C.img.alpha_composite(glow)

    img, origin = C.img, (ox, oy)
    if rot:
        img, origin = rotate_sprite(img, origin, rot)
    return img, origin


# ---------------------------------------------------------------------------
# BOSS 身体
# ---------------------------------------------------------------------------

def boss_back(canv, P, pose):
    """大衣后摆（画在腿后面）"""
    coat = pose.get('coat', 0.0)
    pel = P['pelvis']
    # 后摆主片（向左后方拖）
    tail = [(pel[0] - 8, pel[1] - 4),
            (pel[0] - 38 - coat * 2, pel[1] + 26),
            (pel[0] - 72 - coat * 3, pel[1] + 50 - coat),
            (pel[0] - 82 - coat * 4, pel[1] + 76 - coat),
            (pel[0] - 50 - coat * 2, pel[1] + 88 - coat * 2),
            (pel[0] - 14, pel[1] + 66),
            (pel[0] - 2, pel[1] + 20)]
    canv.part(m_poly(canv.size, tail), XM['coat'], band=3)
    # 内衬（红）
    lining = [(pel[0] - 12, pel[1] + 10), (pel[0] - 44 - coat * 2, pel[1] + 48),
              (pel[0] - 64 - coat * 3, pel[1] + 68), (pel[0] - 34, pel[1] + 72),
              (pel[0] - 8, pel[1] + 44)]
    canv.part(m_poly(canv.size, lining), XM['lining'], outline=True, band=1)
    # 下摆青色霓虹镶边
    trim = [(pel[0] - 38 - coat * 2, pel[1] + 26), (pel[0] - 72 - coat * 3, pel[1] + 50 - coat),
            (pel[0] - 82 - coat * 4, pel[1] + 76 - coat), (pel[0] - 50 - coat * 2, pel[1] + 88 - coat * 2)]
    canv.limb(trim, [2.4, 2.4], XM['cyan'], outline=False, band=0)
    # 第二条后摆
    tail2 = [(pel[0] + 4, pel[1] + 2), (pel[0] - 16, pel[1] + 40), (pel[0] - 22, pel[1] + 78),
             (pel[0] + 10, pel[1] + 74), (pel[0] + 22, pel[1] + 50), (pel[0] + 16, pel[1] + 20)]
    canv.part(m_poly(canv.size, tail2), XM['coat2'], band=2)


def boss_leg(canv, P, pose, side):
    far = (side == 'rear')
    prefix = 'rl' if far else 'fl'
    dark = mat_far(XM['dark'], 0.72) if far else XM['dark']
    steel = mat_far(XM['steel_d'], 0.75) if far else XM['steel_d']
    boot = mat_far(XM['dark'], 0.68) if far else XM['dark']
    hip, knee, ankle = P[prefix + '_hip'], P[prefix + '_knee'], P[prefix + '_ankle']
    foot_ang = P['fl_foot'] if side == 'front' else P['rl_foot']

    canv.limb([hip, lerp_pt(hip, knee, 0.55), knee], [30.0, 27.0, 23.0], dark, band=2)
    canv.limb([knee, lerp_pt(knee, ankle, 0.5), ankle], [23.0, 20.0, 17.0], dark, band=2)
    # 护膝铁板
    canv.part(m_poly(canv.size, [(knee[0] - 8, knee[1] - 6), (knee[0] + 7, knee[1] - 7),
                                 (knee[0] + 9, knee[1] + 2), (knee[0] - 8, knee[1] + 3)]),
              steel, band=1)
    canv.px(knee[0] - 4, knee[1] - 2, XM['steel']['l'])
    # 胫甲
    shin = m_poly(canv.size, [(knee[0] - 6, knee[1] + 4), (knee[0] + 7, knee[1] + 2),
                              (ankle[0] + 6, ankle[1] - 2), (ankle[0] - 8, ankle[1]),
                              (ankle[0] - 7, ankle[1] + 4), (knee[0] - 5, knee[1] + 10)])
    canv.part(shin, XM['steel_d'], band=1)
    # 靴（铁靴 + 红边）
    boot_pts = [(-12, -6), (7, -6), (12, -2), (20, 0), (23, 5), (17, 9), (-12, 9), (-14, 4)]
    bmask = m_poly(canv.size, foot_poly(ankle, foot_ang, boot_pts))
    canv.part(bmask, boot, band=1)
    toe = foot_poly(ankle, foot_ang, [(11, -2), (20, 0), (23, 5), (16, 8), (12, 6)])
    canv.part(m_poly(canv.size, toe), steel, outline=False, band=0)
    sole = foot_poly(ankle, foot_ang, [(-12, 8), (17, 9), (17, 10.4), (-12, 9.4)])
    canv.poly(sole, INK)
    # 红边 / 发光缝
    redline = foot_poly(ankle, foot_ang, [(-12, 5.6), (12, 6.2), (12, 7), (-12, 6.4)])
    canv.poly(redline, XM['red_d']['b'])
    seam = foot_poly(ankle, foot_ang, [(-2, -5.4), (7, -5.4), (7, -4.8), (-2, -4.8)])
    canv.poly(seam, XM['red']['d'])


def boss_arm(canv, P, pose, side):
    far = (side == 'rear')
    prefix = 'ra' if far else 'fa'
    sh, el, hand = P[prefix + '_shoulder'], P[prefix + '_elbow'], P[prefix + '_hand']
    open_hand = pose['ra_open'] if far else pose['fa_open']
    ang = math.degrees(math.atan2(hand[0] - el[0], hand[1] - el[1]))

    if far:
        # 后臂：大衣袖 + 铁手
        coat = mat_far(XM['coat'], 0.72)
        canv.limb([sh, lerp_pt(sh, el, 0.5), el], [26.0, 23.0, 19.0], coat, band=2)
        canv.limb([el, lerp_pt(el, hand, 0.5), hand], [18.0, 16.0, 14.0], coat, band=2)
        canv.poly([(el[0] - 6, el[1] - 2), (el[0] + 5, el[1] - 4), (el[0] + 6, el[1] + 1),
                   (el[0] - 5, el[1] + 3)], XM['lining']['d'])
        fist(canv, hand, ang, BOSS['prop']['hand_r'], mat_far(XM['steel_d'], 0.8),
             open_hand=open_hand)
    else:
        # 前臂：机械义肢
        canv.limb([sh, lerp_pt(sh, el, 0.5), el], [27.0, 25.0, 22.0], XM['dark'], band=2)
        # 电动肌肉束
        for t in (0.28, 0.5, 0.72):
            cx = lerp(sh[0], el[0], t)
            cy = lerp(sh[1], el[1], t)
            canv.px(cx, cy, XM['red']['d'])
        # 肘关节
        canv.part(m_ellipse(canv.size, el[0], el[1], 10.0, 10.0), XM['steel_d'], band=1)
        canv.px(el[0] - 2, el[1] - 2, XM['steel_l']['b'])
        # 巨型护腕（前臂）
        canv.limb([el, lerp_pt(el, hand, 0.45), lerp_pt(el, hand, 0.82)],
                  [26.0, 27.0, 23.0], XM['steel_d'], band=2)
        # 护腕上的红甲片 + 发光缝
        dx = hand[0] - el[0]
        dy = hand[1] - el[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        for t in (0.32, 0.56, 0.80):
            cx, cy = el[0] + dx * t, el[1] + dy * t
            canv.poly([(cx - nx * 10, cy - ny * 10), (cx + nx * 10, cy + ny * 10),
                       (cx + nx * 10 + ux * 3, cy + ny * 10 + uy * 3),
                       (cx - nx * 10 + ux * 3, cy - ny * 10 + uy * 3)], XM['steel']['d'])
            canv.poly([(cx - nx * 7.6 + ux * 1, cy - ny * 7.6 + uy * 1),
                       (cx + nx * 7.6 + ux * 1, cy + ny * 7.6 + uy * 1),
                       (cx + nx * 7.6 + ux * 2, cy + ny * 7.6 + uy * 2),
                       (cx - nx * 7.6 + ux * 2, cy - ny * 7.6 + uy * 2)], XM['red']['d'])
        # 手：铁爪
        canv.part(m_ellipse(canv.size, hand[0], hand[1], 8.5, 7.5), XM['steel_d'], band=1)
        for k in (-1.0, 0.0, 1.0):
            tip = (hand[0] + ux * 9 + nx * 4.0 * k, hand[1] + uy * 9 + ny * 4.0 * k)
            canv.limb([hand, tip], [5.5, 3.2], XM['steel'], band=1)
        canv.px(hand[0] - nx * 3, hand[1] - ny * 3, XM['red']['b'])
        if pose.get('glow_fist'):
            canv.px(hand[0] + ux * 2, hand[1] + uy * 2, XM['glow_hot'])


def boss_torso(canv, P, pose):
    pel = P['pelvis']
    sh = P['shoulder']
    # 骨盆
    canv.limb([bp(P, 6, 0), bp(P, -10, 0)], [60.0, 56.0], XM['dark'], band=2)
    # 大衣躯干
    torso_pts = bp_pts(P, [(0, 0), (20, 0), (38, 0), (52, 0), (60, 0)])
    torso_w = [58.0, 62.0, 68.0, 74.0, 76.0]
    torso_m = m_chain_flat(canv.size, torso_pts, torso_w)
    canv.part(torso_m, XM['coat'], band=3)
    # 前襟红色内衬（V 形）
    lining = m_poly(canv.size, bp_pts(P, [(60, 2), (52, 10), (36, 14), (12, 10), (4, 4),
                                          (10, -6), (26, -8), (44, -2)]))
    canv.part(lining, XM['lining'], outline=True, band=2)
    # 左襟（大衣前片）
    lapel_l = m_poly(canv.size, bp_pts(P, [(62, -22), (58, -8), (48, 2), (44, 12),
                                           (40, 22), (34, 18), (40, 4), (48, -10), (54, -20)]))
    canv.part(lapel_l, XM['coat2'], band=2)
    # 右襟
    lapel_r = m_poly(canv.size, bp_pts(P, [(62, 2), (56, 14), (46, 22), (28, 22),
                                           (30, 14), (42, 12), (50, 4)]))
    canv.part(lapel_r, XM['coat2'], band=2)
    # 霓虹镶边（青色 1px）
    trim_l = [(62, -22), (58, -8), (48, 2), (44, 12), (40, 22)]
    trim_r = [(62, 2), (56, 14), (46, 22), (28, 22)]
    canv.limb(bp_pts(P, trim_l), [2.0, 2.0], XM['cyan'], outline=False, band=0)
    canv.limb(bp_pts(P, trim_r), [2.0, 2.0], XM['cyan'], outline=False, band=0)
    # 大衣褶皱
    for (a, s0, s1) in ((26, -34, -22), (14, -30, -20), (30, 24, 34)):
        canv.poly(bp_pts(P, [(a, s0), (a + 10, s0 + 2), (a + 10, s0 + 5), (a, s0 + 3)]),
                  XM['coat2']['d'])
    # 腰带 + 红宝石扣
    canv.limb([bp(P, 2, 0), bp(P, -4, 0)], [64.0, 64.0], XM['dark'], outline=False, band=0)
    buck = bp(P, -1, 4)
    canv.part(m_rect(canv.size, buck[0] - 6, buck[1] - 5, buck[0] + 6, buck[1] + 5),
              XM['steel_d'], band=1)
    canv.rect(buck[0] - 2, buck[1] - 2, buck[0] + 2, buck[1] + 2, XM['red']['b'])
    canv.px(buck[0] - 1, buck[1] - 1, XM['glow_hot'])
    # 高领
    collar = m_poly(canv.size, bp_pts(P, [(68, -14), (64, -22), (58, -24), (54, -14),
                                          (52, -2), (58, -6), (64, -10), (68, -8)]))
    canv.part(collar, XM['coat2'], band=2)
    canv.limb(bp_pts(P, [(66, -12), (60, -20), (56, -20)]), [2.0, 2.0], XM['cyan'],
              outline=False, band=0)
    # 脖子（护甲）
    canv.limb([bp(P, 60, 2), bp(P, 70, 0)], [26.0, 24.0], XM['dark'], band=1)


def boss_after_legs(canv, P, pose):
    coat = pose.get('coat', 0.0)
    pel = P['pelvis']
    # 前襟下摆（覆盖大腿，两片）
    near_panel = [(pel[0] + 14, pel[1] + 4),
                  (pel[0] + 50 + coat, pel[1] + 24),
                  (pel[0] + 52 + coat, pel[1] + 62),
                  (pel[0] + 14, pel[1] + 70),
                  (pel[0] + 2, pel[1] + 36)]
    canv.part(m_poly(canv.size, near_panel), XM['coat'], band=3)
    # 红色衬边
    canv.part(m_chain(canv.size, [(pel[0] + 8, pel[1] + 20), (pel[0] + 14, pel[1] + 68)],
                      [3.4, 3.4]), XM['lining'], outline=True, band=1)
    # 青边
    canv.limb([(pel[0] + 50 + coat, pel[1] + 24), (pel[0] + 52 + coat, pel[1] + 62),
               (pel[0] + 14, pel[1] + 70)], [2.2, 2.2], XM['cyan'], outline=False, band=0)
    # 远侧摆片
    far_panel = [(pel[0] - 26, pel[1] + 10),
                 (pel[0] - 46, pel[1] + 42),
                 (pel[0] - 38, pel[1] + 74),
                 (pel[0] - 10, pel[1] + 68),
                 (pel[0] - 20, pel[1] + 36)]
    canv.part(m_poly(canv.size, far_panel), XM['coat2'], band=2)
    canv.limb([(pel[0] - 46, pel[1] + 42), (pel[0] - 38, pel[1] + 74)], [2.0, 2.0],
              XM['cyan'], outline=False, band=0)

    # 肩甲（近 / 远）
    for side, scale in (('ra', 0.92), ('fa', 1.0)):
        sx, sy = P[side + '_shoulder']
        pw = 22 * scale
        ang = -0.25
        plate = [(sx - pw * 0.7, sy - 16 * scale), (sx + pw * 0.9, sy - 20 * scale),
                 (sx + pw * 1.25, sy - 6 * scale), (sx + pw * 0.95, sy + 10 * scale),
                 (sx - pw * 0.6, sy + 8 * scale), (sx - pw * 0.95, sy - 6 * scale)]
        canv.part(m_poly(canv.size, plate), XM['steel_d'], band=2)
        # 层叠铁片
        canv.poly([(sx - pw * 0.5, sy - 4 * scale), (sx + pw * 0.9, sy - 6 * scale),
                   (sx + pw * 0.85, sy + 2 * scale), (sx - pw * 0.55, sy + 3 * scale)],
                  XM['steel']['b'])
        canv.poly([(sx - pw * 0.4, sy + 4 * scale), (sx + pw * 0.8, sy + 2 * scale),
                   (sx + pw * 0.75, sy + 8 * scale), (sx - pw * 0.45, sy + 9 * scale)],
                  XM['dark']['b'])
        # 尖刺
        for k in (0.0, 0.6, 1.1):
            bx = sx + pw * (0.15 + k * 0.55)
            by = sy - 14 * scale + k * 3
            canv.part(m_poly(canv.size, [(bx - 3, by + 5), (bx + 3, by + 5), (bx + k * 2 - 1, by - 9)]),
                      XM['steel'], band=1)
        # 红发光缝
        canv.limb([(sx + pw * 0.1, sy - 9 * scale), (sx + pw * 0.95, sy - 4 * scale)],
                  [2.0, 2.0], XM['red_d'], outline=False, band=0)
    # 肩甲上的铆钉
    sx, sy = P['fa_shoulder']
    for k in (-8, 0, 8):
        canv.px(sx + k, sy - 12, XM['steel_l']['b'])


def boss_front_extra(canv, P, pose):
    """蓄力冲拳的光 / 咆哮时的红光喷发"""
    gf = pose.get('glow_fist', 0)
    if gf:
        h = P['fa_hand']
        glow = Image.new('RGBA', canv.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        r = 12 + gf * 3
        gd.ellipse([h[0] - r, h[1] - r, h[0] + r, h[1] + r], fill=rgba(XM['glow_red'], 40 + gf * 18))
        gd.ellipse([h[0] - r * 0.55, h[1] - r * 0.55, h[0] + r * 0.55, h[1] + r * 0.55],
                   fill=rgba(XM['glow_hot'], 60 + gf * 20))
        canv.img.alpha_composite(glow)
        canv.px(h[0], h[1], XM['white_hot'])
        for (dx, dy) in ((-6, -2), (7, -1), (-3, 7), (3, -7), (8, 4)):
            canv.px(h[0] + dx, h[1] + dy, XM['glow_red'])
    if pose.get('roar_rays'):
        hc = P['head']
        glow = Image.new('RGBA', canv.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for i, (dx, dy) in enumerate(((-30, -18), (-36, 2), (26, -22), (34, -2), (0, -34),
                                      (-24, 14), (24, 16))):
            gd.rectangle([hc[0] + dx, hc[1] + dy, hc[0] + dx + 2, hc[1] + dy + 9],
                         fill=rgba(XM['glow_red'], max(24, 90 - i * 10)))
        gd.ellipse([hc[0] - 34, hc[1] - 34, hc[0] + 34, hc[1] + 34],
                   fill=rgba(XM['glow_red'], 26))
        canv.img.alpha_composite(glow)


BOSS_ANIMS = {
    'idle': dict(fps=5, loop=True, frames=[
        dict(lean=4, fa=(20, 64), ra=(12, 54), fl=(6, -8, 0), rl=(-6, -9, 0), coat=0, expr='idle'),
        dict(lean=5, fa=(22, 68), ra=(13, 58), fl=(7, -11, 0), rl=(-7, -12, 0), coat=2,
             head_dy=-1),
        dict(lean=4.5, fa=(21, 66), ra=(12.5, 56), fl=(6.5, -9.5, 0), rl=(-6.5, -10.5, 0),
             coat=1, head_dy=-0.5),
        dict(lean=3.5, fa=(19, 62), ra=(11, 52), fl=(5.5, -7, 0), rl=(-5.5, -8, 0), coat=0),
    ]),
    'walk': dict(fps=8, loop=True, frames=[
        dict(lean=6, fa=(10, 60), ra=(20, 52), fl=(24, -10, 0), rl=(-22, -26, 0), coat=-2),
        dict(lean=5, fa=(14, 62), ra=(16, 54), fl=(18, -24, 0), rl=(-14, -34, 0), coat=0),
        dict(lean=4, fa=(18, 64), ra=(12, 56), fl=(6, -34, 0), rl=(-2, -28, 0), coat=2),
        dict(lean=6, fa=(20, 52), ra=(10, 60), fl=(-22, -26, 0), rl=(24, -10, 0), coat=2),
        dict(lean=5, fa=(16, 54), ra=(14, 62), fl=(-14, -34, 0), rl=(18, -24, 0), coat=0),
        dict(lean=4, fa=(12, 56), ra=(18, 64), fl=(-2, -28, 0), rl=(6, -34, 0), coat=-2),
    ]),
    'attack1': dict(fps=9, loop=False, frames=[
        dict(lean=-8, fa=(-26, 44), ra=(44, 40), fl=(8, -14, 0), rl=(-18, -20, 0),
             coat=-2, head_dy=-1, expr='idle'),
        dict(lean=6, fa=(18, 30), ra=(34, 42), fl=(22, -12, 0), rl=(-24, -14, 0),
             coat=2, expr='attack'),
        dict(lean=18, fa=(92, 6), ra=(-22, 32), fl=(30, -8, 0), rl=(-30, -10, 0),
             coat=6, expr='attack'),
        dict(lean=20, fa=(112, 4), ra=(-30, 26), fl=(32, -10, 0), rl=(-32, -12, 0),
             coat=7, expr='attack'),
        dict(lean=10, fa=(48, 36), ra=(-2, 42), fl=(16, -16, 0), rl=(-18, -18, 0),
             coat=3, expr='idle'),
    ]),
    'attack2': dict(fps=9, loop=False, frames=[
        dict(lean=-12, fa=(-38, 72), ra=(52, 40), fl=(16, -24, 0), rl=(-26, -26, 0),
             coat=-3, head_dy=-2, glow_fist=1, expr='attack'),
        dict(lean=-16, fa=(-48, 84), ra=(60, 34), fl=(18, -30, 0), rl=(-30, -30, 0),
             coat=-4, head_dy=-2, glow_fist=2, expr='attack'),
        dict(lean=24, fa=(96, 2), ra=(-34, 30), fl=(34, -12, 0), rl=(-34, -12, 0),
             coat=6, glow_fist=2, expr='attack'),
        dict(lean=22, fa=(98, 4), ra=(-30, 34), fl=(32, -14, 0), rl=(-32, -14, 0),
             coat=5, glow_fist=1, expr='attack'),
        dict(lean=10, fa=(52, 40), ra=(-6, 44), fl=(16, -20, 0), rl=(-20, -22, 0),
             coat=2, expr='idle'),
    ]),
    'roar': dict(fps=8, loop=False, frames=[
        dict(lean=-4, fa=(-16, 60), ra=(-12, 54), fl=(8, -14, 0), rl=(-10, -16, 0),
             coat=-1, head_dy=-2, expr='roar'),
        dict(lean=-9, fa=(-78, 26), ra=(-74, 26), fl=(10, -18, 0), rl=(-12, -20, 0),
             coat=-3, head_dy=-4, roar_rays=True, expr='roar'),
        dict(lean=-12, fa=(-112, 18), ra=(-108, 18), fl=(12, -22, 0), rl=(-14, -24, 0),
             coat=-4, head_dy=-5, roar_rays=True, expr='roar'),
        dict(lean=-11, fa=(-116, 16), ra=(-112, 16), fl=(11, -21, 0), rl=(-13, -23, 0),
             head_dx=1, head_dy=-5, roar_rays=True, expr='roar'),
        dict(lean=-12, fa=(-112, 18), ra=(-108, 18), fl=(12, -22, 0), rl=(-14, -24, 0),
             head_dx=-1, head_dy=-5, roar_rays=True, expr='roar'),
        dict(lean=-2, fa=(-30, 50), ra=(-26, 48), fl=(8, -12, 0), rl=(-8, -14, 0),
             coat=0, expr='idle'),
    ]),
    'hurt': dict(fps=8, loop=False, frames=[
        dict(lean=-10, fa=(-4, 70), ra=(30, 50), fl=(10, -18, 0), rl=(-16, -20, 0),
             head_dx=-2, head_dy=-1, expr='hurt'),
        dict(lean=-14, fa=(-12, 66), ra=(38, 44), fl=(8, -22, 0), rl=(-20, -24, 0),
             head_dx=-4, head_dy=-1, expr='hurt'),
    ]),
    'ko': dict(fps=6, loop=False, frames=[
        dict(lean=-16, fa=(-20, 56), ra=(46, 44), fl=(10, -18, 0), rl=(-16, -22, 0),
             head_dx=-3, head_dy=-2, expr='ko'),
        dict(lean=-26, fa=(-46, 42), ra=(66, 36), fl=(6, -30, -6), rl=(-12, -30, 4),
             grounded=False, pelvis_dy=20, hip_dx=-6, root_rot=-24, head_dx=-2,
             head_dy=-3, expr='ko'),
        dict(lean=-20, fa=(-64, 34), ra=(84, 26), fl=(-30, -46, -14), rl=(-42, -46, 8),
             grounded=False, pelvis_dy=44, hip_dx=0, root_rot=-48, expr='ko'),
        dict(lean=-10, fa=(-74, 30), ra=(94, 22), fl=(-52, -44, -16), rl=(-62, -44, 6),
             grounded=False, pelvis_dy=66, hip_dx=10, root_rot=-72, head_rot=-90,
             expr='ko'),
        dict(lean=-4, fa=(-64, 34), ra=(84, 26), fl=(-66, -40, -16), rl=(-74, -40, 6),
             grounded=False, pelvis_dy=78, hip_dx=18, root_rot=-88, head_rot=-90,
             expr='ko'),
        dict(lean=-2, fa=(-58, 38), ra=(78, 28), fl=(-70, -36, -14), rl=(-78, -36, 6),
             grounded=False, pelvis_dy=80, hip_dx=20, root_rot=-90, head_rot=-90,
             expr='ko'),
    ]),
}

# ============================================================================
# 头像（160x160）
# ============================================================================

PORTRAIT_SIZE = 160


def portrait_shoulders(name, C):
    """在 84x84 画布上画头肩像的肩部（之后整体 2x 放大成 160）"""
    S = 84
    if name == 'punk':
        # 脖子 / 锁骨
        C.limb([(42, 62), (42, 84)], [18.0, 22.0], PM['skin_d'], band=1)
        C.poly([(28, 62), (38, 64), (56, 63), (52, 70), (30, 71)], PM['skin']['b'])
        # 皮背心双肩
        C.part(m_poly(C.size, [(6, 84), (10, 68), (22, 60), (34, 61), (30, 72),
                               (26, 84)]), PM['leather'], band=2)
        C.part(m_poly(C.size, [(78, 84), (74, 68), (62, 60), (50, 61), (54, 72),
                               (58, 84)]), PM['leather'], band=2)
        # 背心领口翻边
        C.part(m_poly(C.size, [(22, 62), (32, 61), (30, 70), (24, 70)]), PM['leather2'],
               band=1)
        C.part(m_poly(C.size, [(62, 61), (52, 62), (54, 70), (60, 70)]), PM['leather2'],
               band=1)
        # 链条
        for i in range(6):
            x = 30 + i * 4.6
            y = 66 + math.sin(i * 0.9) * 2.2
            C.px(x, y, PM['chain']['l'] if i % 2 == 0 else PM['chain']['b'])
        C.rect(41, 70, 42, 72, PM['yellow']['b'])
        # 铆钉
        for (x, y) in ((14, 76), (20, 66), (70, 66), (64, 76)):
            C.px(x, y, PM['steel']['l'])
        # 露出的胸口皮肤阴影
        C.poly([(34, 72), (50, 73), (48, 84), (36, 84)], PM['skin']['b'])
        C.poly([(40, 75), (44, 78), (42, 82), (38, 79)], PM['skin']['d'])
    elif name == 'brute':
        # 巨大斜方肌 / 肩
        C.limb([(42, 58), (42, 84)], [30.0, 40.0], BM['skin_d'], band=1)
        C.part(m_ellipse(C.size, 18, 78, 22.0, 18.0), BM['skin'], band=2)
        C.part(m_ellipse(C.size, 66, 78, 22.0, 18.0), BM['skin'], band=2)
        C.poly([(14, 66), (30, 56), (42, 54), (54, 56), (70, 66), (66, 84), (18, 84)],
               BM['skin']['b'])
        # 背心（脏）
        C.part(m_poly(C.size, [(26, 84), (28, 66), (36, 58), (48, 58), (56, 66),
                               (58, 84)]), BM['tank'], band=2)
        # 肩带
        C.part(m_poly(C.size, [(27, 66), (34, 58), (38, 60), (31, 68), (30, 84), (25, 84)]),
               BM['tank2'], band=1)
        C.part(m_poly(C.size, [(57, 66), (50, 58), (46, 60), (53, 68), (54, 84), (59, 84)]),
               BM['tank2'], band=1)
        # 胸口污渍
        C.poly([(34, 72), (42, 70), (44, 76), (36, 78)], BM['tank2']['d'])
        # 虎纹刺青（左肩）
        for i, (x, y, w) in enumerate(((10, 70, 6), (14, 63, 5), (20, 58, 4))):
            C.poly([(x, y), (x + w, y - 2), (x + w + 2, y + 2), (x + 2, y + 3)], BM['tattoo']['b'])
        C.px(18, 72, BM['orange']['d'])
        C.px(24, 65, BM['orange']['d'])
    else:  # boss
        # 大衣立领（在头后面）
        C.part(m_poly(C.size, [(10, 84), (6, 48), (16, 28), (26, 30), (20, 62), (24, 84)]),
               XM['coat'], band=2)
        C.part(m_poly(C.size, [(74, 84), (78, 48), (68, 28), (58, 30), (64, 62), (60, 84)]),
               XM['coat'], band=2)
        C.poly([(12, 50), (16, 34), (22, 34), (18, 58), (18, 80), (12, 80)],
               XM['lining']['b'])
        C.poly([(72, 50), (68, 34), (62, 34), (66, 58), (66, 80), (72, 80)],
               XM['lining']['b'])
        # 肩甲（左右下角）
        C.part(m_poly(C.size, [(0, 84), (4, 62), (18, 54), (34, 58), (30, 70), (24, 84)]),
               XM['steel_d'], band=2)
        C.part(m_poly(C.size, [(84, 84), (80, 62), (66, 54), (50, 58), (54, 70), (60, 84)]),
               XM['steel_d'], band=2)
        C.poly([(6, 64), (16, 58), (30, 62), (26, 66), (12, 66)], XM['steel']['b'])
        C.poly([(78, 64), (68, 58), (54, 62), (58, 66), (72, 66)], XM['steel']['b'])
        # 肩甲尖刺
        C.part(m_poly(C.size, [(2, 62), (8, 56), (10, 62)]), XM['steel'], band=1)
        C.part(m_poly(C.size, [(82, 62), (76, 56), (74, 62)]), XM['steel'], band=1)
        # 红发光缝
        C.poly([(8, 74), (24, 64), (26, 66), (10, 76)], XM['red_d']['b'])
        C.poly([(76, 74), (60, 64), (58, 66), (74, 76)], XM['red_d']['b'])
        # 胸口护甲
        C.part(m_poly(C.size, [(30, 84), (34, 74), (42, 70), (50, 74), (54, 84)]),
               XM['dark'], band=1)
        C.rect(40, 76, 44, 80, XM['steel_d']['b'])


def make_portrait(name):
    fn = make_head_fn(name)
    C = Canv((84, 84))
    portrait_shoulders(name, C)
    # 肩部轮廓光（头部之后会有自己的轮廓光，先算身体）
    C.neon_rim(exclude=None, left=0.5, right=0.55, top=0.3, bottom=0.4)
    head_img, horg = fn('idle')
    # 头部放在画布中央偏上
    pos = (42 - horg[0], 45 - horg[1])
    C.sprite(head_img, pos)
    big = upscale(C.img, 2)
    out = Image.new('RGBA', (PORTRAIT_SIZE, PORTRAIT_SIZE), (0, 0, 0, 0))
    out.alpha_composite(big, ((PORTRAIT_SIZE - big.width) // 2,
                              (PORTRAIT_SIZE - big.height) // 2))
    return out


# ============================================================================
# 烘焙、清单、预览
# ============================================================================

def init_specs():
    PUNK['draw_back'] = None
    PUNK['draw_leg'] = punk_leg
    PUNK['draw_arm'] = punk_arm
    PUNK['draw_torso'] = punk_torso
    PUNK['draw_after_legs'] = punk_after_legs
    PUNK['front_extra'] = punk_front_extra
    PUNK['rim'] = (0.54, 0.56, 0.30, 0.45)

    BRUTE['draw_back'] = None
    BRUTE['draw_leg'] = brute_leg
    BRUTE['draw_arm'] = brute_arm
    BRUTE['draw_torso'] = brute_torso
    BRUTE['draw_after_legs'] = brute_after_legs
    BRUTE['front_extra'] = brute_front_extra
    BRUTE['rim'] = (0.56, 0.58, 0.32, 0.46)

    BOSS['draw_back'] = boss_back
    BOSS['draw_leg'] = boss_leg
    BOSS['draw_arm'] = boss_arm
    BOSS['draw_torso'] = boss_torso
    BOSS['draw_after_legs'] = boss_after_legs
    BOSS['front_extra'] = boss_front_extra
    BOSS['rim'] = (0.62, 0.64, 0.36, 0.50)

    return {'punk': PUNK, 'brute': BRUTE, 'boss': BOSS}


SPECS = init_specs()
ANIMS = {'punk': PUNK_ANIMS, 'brute': BRUTE_ANIMS, 'boss': BOSS_ANIMS}
CHAR_ORDER = ['punk', 'brute', 'boss']
DISPLAY = {'punk': 'PUNK', 'brute': 'BRUTE', 'boss': 'BOSS IRON MASK'}


def bake_char(name, heads, report):
    spec = SPECS[name]
    fw, fh = spec['frame']
    ax, ay = spec['anchor']
    outdir = os.path.join(OUT_DIR, name)
    os.makedirs(outdir, exist_ok=True)
    n_frames = 0
    for an, ad in ANIMS[name].items():
        frames = []
        for fi, fr in enumerate(ad['frames']):
            pose = mk_pose(spec, **fr)
            im = render_frame(spec, pose, heads)
            bbox = im.getbbox()
            if bbox is None:
                report.append('  !! %s/%s[%d] 空帧' % (name, an, fi))
            else:
                x0, y0, x1, y1 = bbox
                if x0 < 0 or y0 < 0 or x1 > fw or y1 > fh:
                    report.append('  !! %s/%s[%d] 越界 bbox=%s' % (name, an, fi, bbox))
                h = ay - y1
                if an in ('idle', 'walk', 'attack', 'attack1', 'attack2', 'roar', 'hurt'):
                    if abs((ay - y0) - spec['bodyHeight']) > 12 and abs(y1 - ay) > 12:
                        report.append('  ~ %s/%s[%d] 高度异常 bbox=%s' % (name, an, fi, bbox))
            frames.append(im)
        sheet = Image.new('RGBA', (fw * len(frames), fh), (0, 0, 0, 0))
        for i, im in enumerate(frames):
            sheet.paste(im, (i * fw, 0))
        sheet.save(os.path.join(outdir, an + '.png'))
        n_frames += len(frames)
    portrait = make_portrait(name)
    portrait.save(os.path.join(outdir, 'portrait.png'))
    return n_frames


def write_manifest():
    lines = []
    lines.append('/* 霓虹拳魂 NEON FIST SOUL — 敌人与 Boss 资源清单')
    lines.append(' * 由 tools/gen_enemies.py 自动生成，请勿手改。')
    lines.append(' * 敌人：punk 混混 / brute 壮汉 / boss 铁面 IRON MASK')
    lines.append(' */')
    lines.append('(function () {')
    lines.append("  var NF = window.NF;")
    lines.append("  if (!NF || !NF.registerChar) return;")
    for name in CHAR_ORDER:
        spec = SPECS[name]
        fw, fh = spec['frame']
        ax, ay = spec['anchor']
        lines.append('')
        lines.append("  NF.registerChar('%s', {" % name)
        lines.append('    frameW: %d, frameH: %d, anchorX: %d, anchorY: %d,' % (fw, fh, ax, ay))
        lines.append('    bodyHeight: %d,' % spec['bodyHeight'])
        lines.append("    portrait: 'chars/enemies/%s/portrait.png'," % name)
        lines.append('    animations: {')
        items = list(ANIMS[name].items())
        for i, (an, ad) in enumerate(items):
            comma = ',' if i < len(items) - 1 else ''
            lines.append("      %s: { file: 'chars/enemies/%s/%s.png', frames: %d, fps: %g, loop: %s }%s"
                         % (an, name, an, len(ad['frames']), ad['fps'],
                            'true' if ad['loop'] else 'false', comma))
        lines.append('    }')
        lines.append('  });')
    lines.append('})();')
    txt = '\n'.join(lines) + '\n'
    path = os.path.join(OUT_DIR, 'manifest.js')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt)
    return path


def make_preview():
    pad = 12
    label_w = 96
    sections = []
    for name in CHAR_ORDER:
        spec = SPECS[name]
        fw, fh = spec['frame']
        anims = ANIMS[name]
        max_frames = max(len(ad['frames']) for ad in anims.values())
        row_w = label_w + max_frames * fw
        rows_h = sum(fh + 8 for _ in anims)
        sec_w = 340 + pad + row_w
        sec_h = max(340, rows_h) + 40
        sections.append((name, sec_w, sec_h))
    W = max(s[1] for s in sections) + pad * 2
    H = sum(s[2] + pad for s in sections) + pad
    img = checker_bg(W, H, cell=8)
    font = ImageFont.load_default(size=20)
    font_small = ImageFont.load_default(size=14)
    y = pad
    for (name, sec_w, sec_h) in sections:
        spec = SPECS[name]
        fw, fh = spec['frame']
        x0 = pad
        # 区域背景
        panel = Image.new('RGBA', (sec_w, sec_h), (10, 6, 20, 200))
        img.alpha_composite(panel, (x0, y))
        d = ImageDraw.Draw(img)
        d.text((x0 + 10, y + 8), '%s  frame %dx%d  H=%d' %
               (DISPLAY[name], fw, fh, spec['bodyHeight']), font=font,
               fill=(180, 240, 255, 255))
        # 头像 2x
        pp = Image.open(os.path.join(OUT_DIR, name, 'portrait.png'))
        img.alpha_composite(upscale(pp, 2), (x0 + 10, y + 40))
        d.text((x0 + 10, y + 372), 'portrait 160x160', font=font_small,
               fill=(160, 200, 220, 255))
        # 动画行
        ry = y + 40
        rx = x0 + 340 + pad
        for an, ad in ANIMS[name].items():
            d.text((rx, ry), '%s  %d frames @%gfps %s' %
                   (an, len(ad['frames']), ad['fps'], 'loop' if ad['loop'] else 'once'),
                   font=font_small, fill=(150, 220, 240, 255))
            sheet = Image.open(os.path.join(OUT_DIR, name, an + '.png')).convert('RGBA')
            img.alpha_composite(sheet, (rx, ry + 18))
            ry += fh + 8 + 18
        y += sec_h + pad
    path = os.path.join(OUT_DIR, 'preview.png')
    img.convert('RGB').save(path)
    try:
        os.makedirs(SHOTS_DIR, exist_ok=True)
        img.convert('RGB').save(os.path.join(SHOTS_DIR, 'enemy_contact.png'))
    except Exception as e:  # noqa: BLE001
        print('shots 预览写入失败:', e)
    return path


def bake_all():
    heads = {}
    report = []
    total = 0
    for name in CHAR_ORDER:
        n = bake_char(name, heads, report)
        total += n
        print('%s: %d frames' % (name, n))
    path = write_manifest()
    print('manifest:', path)
    prev = make_preview()
    print('preview:', prev)
    if report:
        print('\n'.join(report))
    else:
        print('帧边界检查：全部通过')
    print('总帧数：', total)
    return report


def check_outputs():
    ok = True
    total = 0
    for name in CHAR_ORDER:
        spec = SPECS[name]
        fw, fh = spec['frame']
        outdir = os.path.join(OUT_DIR, name)
        for an, ad in ANIMS[name].items():
            p = os.path.join(outdir, an + '.png')
            if not os.path.exists(p):
                print('缺失:', p)
                ok = False
                continue
            im = Image.open(p)
            want = (fw * len(ad['frames']), fh)
            if im.size != want or im.mode != 'RGBA':
                print('尺寸错误:', p, im.size, '期望', want, im.mode)
                ok = False
            total += 1
        pp = os.path.join(outdir, 'portrait.png')
        if not os.path.exists(pp):
            print('缺失头像:', pp)
            ok = False
        else:
            im = Image.open(pp)
            if im.size != (PORTRAIT_SIZE, PORTRAIT_SIZE) or im.mode != 'RGBA':
                print('头像尺寸错误:', pp, im.size, im.mode)
                ok = False
    mp = os.path.join(OUT_DIR, 'manifest.js')
    if not os.path.exists(mp):
        print('缺失 manifest:', mp)
        ok = False
    print('校验%s，动画表 %d 个' % ('通过' if ok else '失败', total))
    return 0 if ok else 1


def save_wip_char2(spec, anims, heads, name):
    """生成单角色自查图（兼容任意动画名）"""
    fw, fh = spec['frame']
    rows = []
    for an, ad in anims.items():
        frames = [render_frame(spec, mk_pose(spec, **fr), heads) for fr in ad['frames']]
        strip = Image.new('RGBA', (fw * len(frames), fh), (0, 0, 0, 0))
        for i, im in enumerate(frames):
            strip.paste(im, (i * fw, 0))
        rows.append((an, strip))
    head_imgs = []
    for expr in ('idle', 'shout', 'hurt', 'ko'):
        hi, _ = make_head_fn(spec['name'])(expr)
        head_imgs.append((expr, hi))
    max_frames = max(len(ad['frames']) for ad in anims.values())
    width = max(fw * max_frames * 2, 1200) + 24
    height = sum(fh * 2 + 8 for _ in rows) + 40 + 76 * 3 + 40
    img = checker_bg(width, height)
    y = 20
    for an, strip in rows:
        img.alpha_composite(upscale(strip, 2), (8, y))
        y += fh * 2 + 8
    hx0, hy0 = 8, y
    for expr, hi in head_imgs:
        img.alpha_composite(upscale(hi, 3), (hx0, hy0))
        hx0 += hi.width * 3 + 10
    # 关键单帧 3x
    pick_anim = 'attack' if 'attack' in anims else 'attack1'
    picks = [('idle', 0), (pick_anim, min(2, len(anims[pick_anim]['frames']) - 1)),
             ('ko', len(anims['ko']['frames']) - 1)]
    zx, zy = hx0 + 16, hy0
    for an, idx in picks:
        fr = render_frame(spec, mk_pose(spec, **anims[an]['frames'][idx]), heads)
        img.alpha_composite(upscale(fr, 3), (zx, zy))
        zx += fw * 3 + 10
        if zx > width - fw * 3:
            zx = 8
            zy += fh * 3 + 10
    path = os.path.join(WIP_DIR, '_wip_%s.png' % spec['name'])
    img.convert('RGB').save(path)
    print('WIP:', path)
    return path


def main(argv):
    heads = {}
    if '--check' in argv:
        return check_outputs()
    if '--head' in argv:
        which = [a for a in argv[1:] if not a.startswith('--')]
        for name in (which or CHAR_ORDER):
            save_head_debug(name)
        return 0
    if '--wip' in argv:
        which = [a for a in argv[1:] if not a.startswith('--')]
        for name in (which or CHAR_ORDER):
            save_wip_char2(SPECS[name], ANIMS[name], heads, name)
        return 0
    if '--punk' in argv:
        report = []
        n = bake_char('punk', heads, report)
        write_manifest()
        make_preview()
        print('punk: %d frames' % n)
        if report:
            print('\n'.join(report))
        return 0
    bake_all()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
