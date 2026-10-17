#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NEON FIST SOUL — 主角「凯 KAI」像素美术生成器。

纯程序化（Python 3 + Pillow + numpy），无外部图片/字体依赖。
输出：
  assets/chars/hero/<anim>.png   横向精灵表，帧 240x240，锚点 (120,224)
  assets/chars/hero/portrait.png 192x192 头肩特写
  assets/chars/hero/manifest.js  NF.registerChar('hero', ...)
  assets/chars/hero/preview.png  contact sheet（不参与游戏加载）

用法：
  python tools/gen_hero.py                # 全部烘焙
  python tools/gen_hero.py --only idle    # 只烘焙某段动画
  python tools/gen_hero.py --wip          # 生成 shots/hero_*.png 自检预览
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERO_DIR = os.path.join(ROOT, 'assets', 'chars', 'hero')
SHOTS_DIR = os.path.join(ROOT, 'shots')

FW = FH = 240
AX, AY = 120, 224
S = 4  # 精灵超采样倍率


# --------------------------------------------------------------------------
# 调色板（每个材质 5 阶：高光→亮→基础→暗→最深）
# --------------------------------------------------------------------------
def hx(s):
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def ramp(*cols):
    return np.array([hx(c) for c in cols], dtype=np.uint8)


SKIN = ramp('#ffe0bd', '#f2c49b', '#d99a72', '#b2735a', '#7c4640')
HAIR = ramp('#3c4f8f', '#232e63', '#141a3f', '#0b0f28', '#070a1a')
JACKET = ramp('#a5fbff', '#4fe4f2', '#1fb4cb', '#0e7890', '#095465')
PANTS = ramp('#7c86b0', '#5d6790', '#454d70', '#2e3450', '#1c2135')
SHIRT = ramp('#41395e', '#2c2743', '#1b1830', '#100d1f', '#0a0816')
GLOVE = ramp('#493c63', '#302748', '#1e1833', '#120e22', '#0a0714')
SHOERED = ramp('#ff8490', '#ef4257', '#b52545', '#741730', '#430c1e')
SHOEWHITE = ramp('#f6f1ff', '#d9cff0', '#a99fc7', '#77709a', '#4c476b')
STEEL = ramp('#eef4ff', '#a2afd0', '#65749b', '#3a4463', '#232a42')
CYAN = ramp('#d6feff', '#8ffbff', '#3df3ff', '#1a8ca8', '#0d566a')
MAGENTA = ramp('#ffb6dc', '#ff74b8', '#ff2f8e', '#a11856', '#5f0d33')

INK = hx('#150b22')
INK2 = hx('#241338')
MOUTH_DARK = hx('#3a1424')
TOOTH = hx('#f6f1ff')
PALE = hx('#f4c6b0')  # 刀疤

LIGHT = np.array([-0.46, -0.89])
LIGHT = LIGHT / np.linalg.norm(LIGHT)

HEAD_GROUP = 'head'
HAIR_GROUP = 'hair'


# --------------------------------------------------------------------------
# 几何工具
# --------------------------------------------------------------------------
def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1])


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def vmul(a, k):
    return (a[0] * k, a[1] * k)


def vlen(a):
    return math.hypot(a[0], a[1])


def vnorm(a):
    l = math.hypot(a[0], a[1])
    return (a[0] / l, a[1] / l) if l > 1e-9 else (0.0, 0.0)


def cap(a, b, ra, rb=None, seg=10):
    """锥形胶囊轮廓点列。"""
    if rb is None:
        rb = ra
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return ellipse_pts(ax, ay, ra, ra)
    ang = math.atan2(dy, dx)
    pts = []
    for i in range(seg + 1):
        t = -math.pi / 2 + math.pi * i / seg
        pts.append((bx + rb * math.cos(ang + t), by + rb * math.sin(ang + t)))
    for i in range(seg + 1):
        t = math.pi / 2 + math.pi * i / seg
        pts.append((ax + ra * math.cos(ang + t), ay + ra * math.sin(ang + t)))
    return pts


def ellipse_pts(cx, cy, rx, ry, ang=0.0, seg=20):
    ca = math.cos(ang)
    sa = math.sin(ang)
    pts = []
    for i in range(seg):
        t = 2 * math.pi * i / seg
        x = rx * math.cos(t)
        y = ry * math.sin(t)
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return pts


def strip(p0, p1, w):
    """两点之间宽度 w 的矩形条。"""
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return [p0]
    nx = -dy / L * w * 0.5
    ny = dx / L * w * 0.5
    return [(p0[0] + nx, p0[1] + ny), (p1[0] + nx, p1[1] + ny),
            (p1[0] - nx, p1[1] - ny), (p0[0] - nx, p0[1] - ny)]


def rot_pts(pts, ang_deg, origin):
    r = math.radians(ang_deg)
    c, s = math.cos(r), math.sin(r)
    ox, oy = origin
    out = []
    for x, y in pts:
        out.append((ox + x * c - y * s, oy + x * s + y * c))
    return out


# --------------------------------------------------------------------------
# 超采样画布
# --------------------------------------------------------------------------
def nb(m, dx, dy):
    """neighbor: out[y,x] = m[y+dy, x+dx]"""
    out = np.zeros_like(m)
    h, w = m.shape[:2]
    x0 = max(0, -dx)
    x1 = min(w, w - dx)
    y0 = max(0, -dy)
    y1 = min(h, h - dy)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = m[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
    return out


def mix(c, t, f):
    return (c.astype(np.float32) * (1 - f) + np.asarray(t, np.float32) * f).astype(np.uint8)


class Canvas:
    def __init__(self, w, h, s, ox=0, oy=0):
        self.w, self.h, self.s = w, h, s
        self.ox, self.oy = ox, oy
        self.W, self.H = w * s, h * s
        self.rgb = np.zeros((self.H, self.W, 3), np.uint8)
        self.alpha = np.zeros((self.H, self.W), bool)
        self.grp = np.full((self.H, self.W), -1, np.int16)
        self.group_names = {}
        self.group_order = {}
        self.order = 0

    def gid(self, name):
        if name not in self.group_names:
            self.group_names[name] = len(self.group_names)
        return self.group_names[name]

    def _mask(self, pts):
        if pts is None or len(pts) < 3:
            return None
        pts = [(x + self.ox, y + self.oy) for x, y in pts]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if not all(math.isfinite(v) for v in xs + ys):
            return None
        x0 = int(math.floor(min(xs) * self.s)) - 1
        x1 = int(math.ceil(max(xs) * self.s)) + 1
        y0 = int(math.floor(min(ys) * self.s)) - 1
        y1 = int(math.ceil(max(ys) * self.s)) + 1
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.W, x1)
        y1 = min(self.H, y1)
        if x1 - x0 < 1 or y1 - y0 < 1:
            return None
        im = Image.new('L', (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(im).polygon(
            [(x * self.s - x0, y * self.s - y0) for x, y in pts], fill=255)
        m = np.array(im) > 127
        if not m.any():
            return None
        return (x0, y0, x1, y1), m

    def _commit(self, box, mask, color, grp):
        x0, y0, x1, y1 = box
        g = self.gid(grp)
        sub = self.rgb[y0:y1, x0:x1]
        if isinstance(color, np.ndarray) and color.ndim == 3:
            sub[mask] = color[mask]
        else:
            sub[mask] = color
        self.alpha[y0:y1, x0:x1][mask] = True
        self.grp[y0:y1, x0:x1][mask] = g
        self.order += 1
        self.group_order[g] = self.order

    def fill(self, pts, color, grp='body'):
        bm = self._mask(pts)
        if bm:
            self._commit(bm[0], bm[1], color, grp)

    def fill_tube(self, a, b, ra, rb, ramp_, grp, bias=0.0):
        pts = cap(a, b, ra, rb)
        bm = self._mask(pts)
        if not bm:
            return
        self._tube_commit(bm, a, b, ra, rb, ramp_, grp, bias)

    def fill_poly_tube(self, pts, a, b, rad, ramp_, grp, bias=0.0):
        bm = self._mask(pts)
        if not bm:
            return
        self._tube_commit(bm, a, b, rad, rad, ramp_, grp, bias)

    def fill_shaded(self, pts, ramp_, grp, center, rx, ry, bias=0.0,
                    th=(0.90, 0.40, 0.02, -0.36), light=( -0.56, -0.48, 0.68)):
        """椭球法线光照：脸上/头发上得到自然的 5 阶色块。"""
        bm = self._mask(pts)
        if not bm:
            return
        box, mask = bm
        x0, y0, x1, y1 = box
        ys, xs = np.nonzero(mask)
        gx = (xs + x0 + 0.5) / self.s
        gy = (ys + y0 + 0.5) / self.s
        nx = (gx - (center[0] + self.ox)) / max(rx, 0.5)
        ny = (gy - (center[1] + self.oy)) / max(ry, 0.5)
        r2 = nx * nx + ny * ny
        nz = np.sqrt(np.maximum(0.0, 1.0 - r2)) * 0.86 + 0.14
        ln = math.sqrt(light[0] ** 2 + light[1] ** 2 + light[2] ** 2)
        lx, ly, lz = light[0] / ln, light[1] / ln, light[2] / ln
        lam = nx * lx + ny * ly + nz * lz + bias
        idx = np.full(lam.shape, 2, np.int8)
        idx[lam >= th[0]] = 0
        idx[lam >= th[1]] = 1
        idx[lam < th[2]] = 3
        idx[lam < th[3]] = 4
        col = np.zeros((y1 - y0, x1 - x0, 3), np.uint8)
        col[mask] = ramp_[idx]
        self._commit(box, mask, col, grp)

    def _tube_commit(self, bm, a, b, ra, rb, ramp_, grp, bias):
        box, mask = bm
        x0, y0, x1, y1 = box
        ys, xs = np.nonzero(mask)
        gx = (xs + x0 + 0.5) / self.s
        gy = (ys + y0 + 0.5) / self.s
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        if L < 1e-6:
            L = 1e-6
        ux, uy = dx / L, dy / L
        px, py = -uy, ux
        if px * LIGHT[0] + py * LIGHT[1] < 0:
            px, py = -px, -py
        relx = gx - ax
        rely = gy - ay
        t = (relx * ux + rely * uy) / L
        rad = ra + (rb - ra) * np.clip(t, 0.0, 1.0)
        lum = (relx * px + rely * py) / np.maximum(rad, 0.6) + bias
        idx = np.full(lum.shape, 2, np.int8)
        idx[lum >= 0.14] = 1
        idx[lum >= 0.56] = 0
        idx[lum < -0.30] = 3
        idx[lum < -0.66] = 4
        col = np.zeros((y1 - y0, x1 - x0, 3), np.uint8)
        col[mask] = ramp_[idx]
        self._commit(box, mask, col, grp)

    def finish(self, rim=True, outline=True):
        o = self.s // 2
        rgb = self.rgb[o::self.s, o::self.s].copy()
        al = self.alpha[o::self.s, o::self.s].copy()
        grp = self.grp[o::self.s, o::self.s].copy()
        H, W = al.shape
        n = max(1, len(self.group_names))
        ordmap = np.zeros(max(512, n + 1), np.int32)
        for g, od in self.group_order.items():
            ordmap[g] = od
        ords = ordmap[np.clip(grp, 0, ordmap.size - 1)]
        ords[grp < 0] = 0

        # 1) 内部 1px 深色分隔线（前层部分）
        ink = np.zeros_like(al)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ng = nb(grp, dx, dy)
            nords = ordmap[np.clip(ng, 0, ordmap.size - 1)]
            nords[ng < 0] = 0
            m = (grp >= 0) & (ng >= 0) & (ng != grp) & (ords > nords)
            ink |= m
        rgb[ink] = INK

        # 2) 轮廓霓虹光（内部轮廓边缘 1px）
        if rim:
            g_head = self.group_names.get(HEAD_GROUP, -1)
            g_hair = self.group_names.get(HAIR_GROUP, -1)
            cyan = al & ((~nb(al, -1, 0)) | (~nb(al, 0, -1)))
            mag = al & (~nb(al, 1, 0))
            mag &= (grp != g_head) & (grp != g_hair)
            rgb[cyan] = mix(rgb[cyan], hx('#7ff6ff'), 0.55)
            rgb[mag] = mix(rgb[mag], hx('#ff74b8'), 0.50)

        # 3) 1px 深色描边
        if outline:
            dil = al.copy()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                dil |= nb(al, dx, dy)
            out = dil & ~al
            rgb[out] = INK
            al = al | out
        return rgb, al


# --------------------------------------------------------------------------
# 骨架 / IK
# --------------------------------------------------------------------------
L_UPARM = 27.5
L_FOREARM = 24.5
L_THIGH = 45.5
L_SHIN = 42.0
HEAD_D = 72.0
NECK_D = 48.0
SHOULDER_D = 44.0
CHEST_D = 30.0
SHOULDER_W = 14.2


def ik2(a, b, l1, l2, hint):
    """两段 IK，返回 (elbow, end)。end 可能被夹到可达范围内。"""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-6:
        d = 1e-6
        dx, dy = 0.0, 1.0
    ux, uy = dx / d, dy / d
    dmax = l1 + l2 - 0.05
    dmin = abs(l1 - l2) + 0.05
    dd = min(max(d, dmin), dmax)
    end = (ax + ux * dd, ay + uy * dd)
    ang = math.atan2(uy, ux)
    ca = (l1 * l1 + dd * dd - l2 * l2) / (2 * l1 * dd)
    ca = max(-1.0, min(1.0, ca))
    alpha = math.acos(ca)
    mid = ((ax + end[0]) / 2.0, (ay + end[1]) / 2.0)
    best = None
    for sgn in (1, -1):
        ex = ax + l1 * math.cos(ang + sgn * alpha)
        ey = ay + l1 * math.sin(ang + sgn * alpha)
        score = (ex - mid[0]) * hint[0] + (ey - mid[1]) * hint[1]
        if best is None or score > best[0]:
            best = (score, (ex, ey))
    return best[1], end


BASE_POSE = dict(
    hip=(0.0, -97.0), lean=3.0, twist=0.0,
    head_tilt=0.0, head_off=(0.4, 0.0),
    wristN=(26.0, -145.0), wristF=(8.0, -148.0),
    ankleN=(12.0, -10.5), faN=0.0,
    ankleF=(-11.5, -11.0), faF=0.0,
    knee_hintN=(1.0, -0.15), knee_hintF=(1.0, -0.15),
    elbow_hintN=(-0.25, 1.0), elbow_hintF=(-0.25, 1.0),
    expr='normal', glow=0.0, far_arm_front=True,
)


def pose(**kw):
    p = dict(BASE_POSE)
    p.update(kw)
    return p


def skeleton(p):
    hip = np.array(p['hip'], float)
    lean = math.radians(p['lean'])
    s = np.array([math.sin(lean), -math.cos(lean)])
    f = np.array([math.cos(lean), math.sin(lean)])
    hipN = tuple(hip + f * 4.6 + s * (-0.5))
    hipF = tuple(hip - f * 4.6 + s * (-0.4))
    chest = tuple(hip + s * CHEST_D + f * 0.8)
    shoulderN = tuple(hip + s * SHOULDER_D + f * (SHOULDER_W + p['twist']))
    shoulderF = tuple(hip + s * (SHOULDER_D - 0.5) + f * (-SHOULDER_W + p['twist']))
    neckbase = tuple(hip + s * NECK_D + f * 0.9)
    headc = tuple(hip + s * HEAD_D + f * 0.9 + np.array(p['head_off'], float))

    elbowN, wristN = ik2(shoulderN, p['wristN'], L_UPARM, L_FOREARM, p['elbow_hintN'])
    elbowF, wristF = ik2(shoulderF, p['wristF'], L_UPARM, L_FOREARM, p['elbow_hintF'])
    kneeN, ankleN = ik2(hipN, p['ankleN'], L_THIGH, L_SHIN, p['knee_hintN'])
    kneeF, ankleF = ik2(hipF, p['ankleF'], L_THIGH, L_SHIN, p['knee_hintF'])

    return dict(
        hip=tuple(hip), hipN=hipN, hipF=hipF, chest=chest,
        shoulderN=shoulderN, shoulderF=shoulderF, neckbase=neckbase,
        headc=headc, elbowN=elbowN, wristN=wristN, elbowF=elbowF, wristF=wristF,
        kneeN=kneeN, ankleN=ankleN, kneeF=kneeF, ankleF=ankleF,
        faN=p['faN'], faF=p['faF'], lean=p['lean'], twist=p['twist'],
    )


def body_pt(sk, d, w):
    hip = np.array(sk['hip'], float)
    lean = math.radians(sk.get('lean', 3.0))
    s = np.array([math.sin(lean), -math.cos(lean)])
    f = np.array([math.cos(lean), math.sin(lean)])
    q = hip + s * d + f * w
    return (float(q[0]), float(q[1]))


# --------------------------------------------------------------------------
# 鞋 / 腿
# --------------------------------------------------------------------------
SHOE_UP = [(-6.8, 7.6), (-7.4, 4.0), (-6.4, 0.6), (-4.4, -2.2), (-1.8, -3.6),
           (1.0, -3.2), (3.4, -2.0), (6.4, -0.8), (10.0, 0.8), (13.6, 2.6),
           (15.6, 5.2), (15.4, 7.4), (-6.4, 7.8)]
SHOE_SOLE = [(-6.8, 6.8), (15.4, 6.6), (15.9, 8.4), (15.2, 10.2), (13.4, 10.6),
             (-5.6, 10.6), (-7.1, 9.7), (-7.3, 8.2)]
SHOE_TOE = [(9.4, 0.2), (13.4, 2.2), (15.4, 5.0), (15.2, 6.8), (9.6, 6.8),
            (8.3, 4.2), (8.6, 1.8)]
SHOE_HEEL = [(-6.9, 6.6), (-7.4, 4.2), (-6.4, 0.8), (-4.8, -1.8), (-3.0, -2.6),
             (-3.4, 1.6), (-4.2, 6.6)]


def draw_shoe(cv, A, fa, grp, far):
    ang = math.radians(fa)
    ca, sa = math.cos(ang), math.sin(ang)

    def X(x, y):
        return (A[0] + x * ca - y * sa, A[1] + x * sa + y * ca)

    def poly(local, color, g=None):
        cv.fill([X(x, y) for x, y in local], color, g or grp)

    def strip_local(a, b, w, color, g=None):
        cv.fill([X(x, y) for x, y in strip(a, b, w)], color, g or grp)

    up = SHOERED[2] if far else SHOERED[1]
    up_hi = SHOERED[1] if far else SHOERED[0]
    up_sh = SHOERED[3] if far else SHOERED[2]
    up_deep = SHOERED[4] if far else SHOERED[3]
    wht = SHOEWHITE[2] if far else SHOEWHITE[1]
    wht_hi = SHOEWHITE[1] if far else SHOEWHITE[0]
    wht_sh = SHOEWHITE[3] if far else SHOEWHITE[2]

    poly(SHOE_UP, up)
    # 鞋身受光/背光
    poly([(-6.2, 2.2), (-4.2, -1.4), (-1.6, -2.8), (1.2, -2.2), (3.6, -0.8),
          (5.6, 0.4), (3.2, 1.4), (-1.0, 0.4), (-4.0, 1.2)], up_hi)
    poly([(-5.8, 5.4), (2.0, 4.6), (10.0, 5.0), (14.6, 6.6), (13.4, 7.4),
          (-6.2, 7.8), (-7.0, 6.6)], up_sh)
    poly(SHOE_HEEL, up_sh)
    poly([(-6.6, 7.0), (-4.6, 3.2), (-3.4, 1.2), (-3.2, 6.8)], up_deep)
    # 鞋头白块
    poly(SHOE_TOE, wht)
    poly([(9.8, 0.8), (13.0, 2.6), (14.6, 4.6), (13.8, 5.4), (10.2, 3.6), (9.4, 1.8)], wht_hi)
    poly([(10.4, 5.2), (14.8, 5.6), (15.0, 6.8), (9.6, 6.8), (9.2, 5.8)], wht_sh)
    # 鞋底
    poly(SHOE_SOLE, wht)
    poly([(-6.9, 9.3), (15.4, 9.0), (15.2, 10.3), (13.4, 10.6), (-5.6, 10.6), (-7.0, 9.9)], wht_sh)
    strip_local((-6.6, 7.35), (15.2, 7.10), 0.9, wht_hi)
    # 霓虹细节
    strip_local((-4.0, 7.6), (13.6, 7.5), 0.8, MAGENTA[2])
    strip_local((1.5, 3.6), (4.0, 4.1), 0.7, CYAN[2])
    # 鞋带
    strip_local((1.2, -1.6), (6.4, 0.2), 0.85, SHOEWHITE[0])
    strip_local((2.4, 0.6), (7.4, 2.3), 0.85, SHOEWHITE[0])
    strip_local((3.6, 2.8), (8.2, 4.2), 0.85, SHOEWHITE[0])
    strip_local((1.6, 0.2), (6.2, 1.8), 0.5, SHOEWHITE[2] if far else SHOEWHITE[3])
    # 鞋舌
    poly([(-0.4, -3.8), (2.6, -3.4), (3.4, -1.4), (-0.2, -2.2)], wht_sh)
    # 鞋口
    poly([(-4.0, -3.4), (-1.4, -4.2), (0.6, -3.6), (-1.2, -2.6), (-3.6, -2.4)], INK2)


def draw_leg(cv, H, K, A, fa, grp, far):
    bias = -0.10 if far else 0.06
    u = vnorm(vsub(A, K))
    p = (-u[1], u[0])
    if p[0] * LIGHT[0] + p[1] * LIGHT[1] < 0:
        p = (-p[0], -p[1])
    # 大腿
    cv.fill_tube(H, K, 10.6, 7.8, PANTS, grp, bias=bias)
    # 受光面
    hi = vadd(vmul(H, 0.35), vmul(K, 0.65))
    cv.fill([vadd(hi, vmul(p, 8.2)), vadd(hi, vmul(p, -2.6)),
             vadd(K, vmul(p, -2.2)), vadd(K, vmul(p, 5.8))],
            PANTS[2] if far else PANTS[1], grp)
    # 膝盖护垫
    ang = math.atan2(u[1], u[0])
    cv.fill(ellipse_pts(K[0], K[1], 7.6, 4.2, ang, 16), PANTS[3] if far else PANTS[2], grp)
    cv.fill(ellipse_pts(K[0] + p[0] * 0.8, K[1] + p[1] * 0.8, 6.0, 2.6, ang, 14),
            PANTS[2] if far else PANTS[1], grp)
    cv.fill(strip((K[0] + p[0] * 6.8, K[1] + p[1] * 6.8),
                  (K[0] - p[0] * 6.8, K[1] - p[1] * 6.8), 0.7),
            PANTS[0] if not far else PANTS[2], grp)
    # 小腿
    cv.fill_tube(K, A, 7.8, 5.4, PANTS, grp, bias=bias)
    hi2 = vadd(vmul(K, 0.35), vmul(A, 0.65))
    cv.fill([vadd(hi2, vmul(p, 6.0)), vadd(hi2, vmul(p, -2.2)),
             vadd(A, vmul(p, -1.6)), vadd(A, vmul(p, 4.0))],
            PANTS[2] if far else PANTS[1], grp)
    # 裤脚
    cuff1 = vsub(A, vmul(u, 4.2))
    cv.fill_tube(cuff1, vsub(A, vmul(u, 0.2)), 6.0, 6.6, PANTS, grp, bias=bias + 0.05)
    cv.fill(strip(vadd(cuff1, vmul(p, 5.8)), vadd(A, vmul(p, 6.4)), 0.8),
            PANTS[0] if not far else PANTS[2], grp)
    # 裤缝线（背面）
    mid = vadd(vmul(H, 0.55), vmul(K, 0.45))
    cv.fill(strip((mid[0] - p[0] * 4.8, mid[1] - p[1] * 4.8),
                  (K[0] - p[0] * 4.2, K[1] - p[1] * 4.2), 0.7),
            PANTS[4], grp)
    # 鞋
    draw_shoe(cv, A, fa, grp + 'Shoe', far)


# --------------------------------------------------------------------------
# 手臂 / 拳
# --------------------------------------------------------------------------
FIST = [(-3.2, -3.2), (-0.4, -4.2), (2.6, -3.8), (4.6, -2.0), (5.4, 0.6),
        (4.8, 2.8), (2.8, 4.2), (-0.6, 4.4), (-3.0, 3.2), (-4.0, 0.4)]


def draw_fist(cv, W, E, grp, far):
    u = vnorm(vsub(W, E))
    ang = math.atan2(u[1], u[0])
    cx = W[0] + u[0] * 2.4
    cy = W[1] + u[1] * 2.4
    ca, sa = math.cos(ang), math.sin(ang)

    def X(x, y):
        return (cx + x * ca - y * sa, cy + x * sa + y * ca)

    def poly(local, color):
        cv.fill([X(x, y) for x, y in local], color, grp)

    def strip_local(a, b, w, color):
        cv.fill([X(x, y) for x, y in strip(a, b, w)], color, grp)

    base = GLOVE[2] if far else GLOVE[1]
    sh = GLOVE[4] if far else GLOVE[2]
    hi = GLOVE[1] if far else GLOVE[0]
    skin = SKIN[2] if far else SKIN[1]
    skin_hi = SKIN[1] if far else SKIN[0]

    poly(FIST, base)
    poly([(-3.0, 2.2), (0.6, 3.6), (3.4, 3.0), (4.6, 1.4), (4.2, 3.0), (1.4, 4.4),
          (-1.6, 3.8), (-3.4, 2.4)], sh)
    poly([(-3.0, -1.2), (-0.8, -3.4), (2.4, -3.2), (4.0, -1.8), (1.8, -0.6),
          (-0.8, 0.0), (-2.8, 0.4)], hi)
    # 露指手套：指关节
    for (fx, fy) in ((3.5, -2.0), (4.3, 0.0), (3.7, 2.0)):
        cv.fill(ellipse_pts(X(fx, fy)[0], X(fx, fy)[1], 1.45, 1.45, 0, 10), skin, grp)
        cv.fill(ellipse_pts(X(fx - 0.3, fy - 0.5)[0], X(fx - 0.3, fy - 0.5)[1], 0.7, 0.7, 0, 8),
                skin_hi, grp)
    # 拇指
    cv.fill(cap(X(-0.4, 1.6), X(2.2, 2.8), 1.5, 1.3), skin if not far else SKIN[3], grp)
    poly([(-2.4, 0.6), (-0.2, 0.2), (-0.4, 1.4), (-2.2, 1.8)], GLOVE[3] if far else GLOVE[2])
    # 指缝
    cv.fill([X(2.4, -1.0), X(3.2, -0.6), X(3.2, 0.2), X(2.2, 0.0)], GLOVE[4] if far else GLOVE[3])
    cv.fill([X(2.3, 1.4), X(3.1, 1.6), X(3.1, 2.4), X(2.2, 2.2)], GLOVE[4] if far else GLOVE[3])
    # 腕带
    poly([(-4.4, -3.0), (-3.2, -3.0), (-3.0, 3.0), (-4.2, 3.0)], GLOVE[2] if far else GLOVE[1])
    strip_local((-3.9, -2.8), (-3.9, 2.8), 0.8, MAGENTA[3] if far else MAGENTA[2])
    # 手背青色小饰线
    strip_local((-1.6, -2.2), (1.2, -1.6), 0.6, CYAN[3] if far else CYAN[2])


def draw_arm(cv, S_, E, W, grp, far):
    bias = -0.15 if far else 0.0
    u = vnorm(vsub(W, E))
    p = (-u[1], u[0])
    if p[0] * LIGHT[0] + p[1] * LIGHT[1] < 0:
        p = (-p[0], -p[1])
    # 上臂（夹克袖）
    cv.fill_tube(S_, E, 7.8, 5.8, JACKET, grp, bias=bias)
    # 三角肌：融入袖子的圆润肩头，不做独立球
    cv.fill_tube(vsub(S_, vmul(u, 4.2)), vadd(S_, vmul(u, 2.2)), 7.4, 7.9, JACKET, grp, bias=bias + 0.04)
    # 肩头/上臂受光
    s0 = vadd(S_, vmul(p, 5.0))
    e0 = vadd(E, vmul(p, 3.4))
    cv.fill([s0, vadd(s0, vmul(u, 6.0)), vadd(e0, vmul(u, 2.4)), e0,
             vadd(e0, vmul(p, -1.4)), vadd(s0, vmul(p, -2.6))],
            JACKET[2] if far else JACKET[1], grp)
    # 袖口
    cuff0 = vsub(E, vmul(u, 1.6))
    cuff1 = vadd(E, vmul(u, 1.6))
    cv.fill_tube(cuff0, cuff1, 6.2, 5.8, JACKET, grp, bias=bias + 0.07)
    cv.fill(strip(vadd(cuff1, vmul(p, 5.6)), vadd(cuff1, vmul(p, -5.6)), 0.8),
            CYAN[2] if not far else CYAN[3], grp)
    # 前臂（皮肤）
    cv.fill_tube(E, W, 5.4, 4.1, SKIN, grp, bias=(0.05 if far else 0.24))
    # 前臂受光
    hi = vadd(vmul(E, 0.4), vmul(W, 0.6))
    cv.fill(strip((hi[0] + p[0] * 3.4, hi[1] + p[1] * 3.4),
                  (W[0] + p[0] * 2.2, W[1] + p[1] * 2.2), 1.2),
            SKIN[1] if far else SKIN[0], grp)
    # 腕带
    w0 = vsub(W, vmul(u, 1.8))
    cv.fill_tube(w0, vadd(W, vmul(u, 0.8)), 4.6, 4.3, GLOVE, grp, bias=bias)
    cv.fill(strip(vadd(W, vmul(u, 0.8) + vmul(p, 4.3)),
                  vadd(W, vmul(u, 0.8) + vmul(p, -4.3)), 0.8), MAGENTA[2] if not far else MAGENTA[3], grp)
    # 拳头
    draw_fist(cv, W, E, grp, far)


# --------------------------------------------------------------------------
# 躯干 / 腰带 / 领子 / 脖子
# --------------------------------------------------------------------------
def draw_pelvis(cv, sk):
    B = lambda d, w: body_pt(sk, d, w)
    c = B(3.0, 0.0)
    cv.fill(ellipse_pts(c[0], c[1], 12.4, 10.6, 0, 20), PANTS[2], 'pelvis')
    cv.fill(ellipse_pts(c[0] + 0.6, c[1] - 1.6, 10.0, 7.6, 0, 18), PANTS[1], 'pelvis')
    cv.fill(ellipse_pts(c[0] - 1.4, c[1] + 2.4, 9.2, 6.2, 0, 16), PANTS[3], 'pelvis')
    # 裆部阴影
    cv.fill([B(-1.6, -4.8), B(-2.6, 2.8), B(2.6, 6.6), B(6.8, 2.6), B(5.2, -3.2)], PANTS[3], 'pelvis')
    cv.fill([B(-3.0, 1.2), B(-1.2, 6.0), B(2.2, 8.0), B(4.2, 5.0), B(2.0, 2.0)], PANTS[4], 'pelvis')
    # 口袋
    cv.fill([B(7.4, -9.4), B(9.8, -7.6), B(8.4, -2.2), B(5.8, -3.8)], PANTS[3], 'pelvis')
    cv.fill(strip(B(9.0, -8.8), B(7.6, -7.2), 0.7), PANTS[0], 'pelvis')


def draw_belt(cv, sk):
    B = lambda d, w: body_pt(sk, d, w)
    band = [B(6.2, -11.6), B(6.2, 11.4), B(10.8, 10.9), B(10.8, -11.0)]
    cv.fill(band, GLOVE[2], 'belt')
    cv.fill([B(6.4, -11.2), B(6.4, 11.0), B(7.8, 10.8), B(7.8, -10.8)], GLOVE[1], 'belt')
    cv.fill([B(9.2, -10.8), B(9.2, 10.6), B(10.6, 10.4), B(10.6, -10.6)], GLOVE[3], 'belt')
    # 钢扣
    cv.fill([B(6.8, 6.8), B(6.8, 10.2), B(10.4, 9.8), B(10.4, 6.4)], STEEL[1], 'belt')
    cv.fill([B(7.2, 7.3), B(7.2, 9.7), B(9.6, 9.3), B(9.6, 7.0)], STEEL[2], 'belt')
    cv.fill([B(7.5, 7.6), B(7.5, 9.0), B(9.0, 8.8), B(9.0, 7.4)], STEEL[3], 'belt')
    # 腰侧挂件
    cv.fill([B(8.4, -10.4), B(8.4, -6.8), B(10.4, -6.6), B(10.4, -10.2)], GLOVE[1], 'belt')
    cv.fill([B(8.7, -9.6), B(8.7, -7.4), B(9.8, -7.3), B(9.8, -9.5)], CYAN[3], 'belt')


def draw_jacket(cv, sk):
    B = lambda d, w: body_pt(sk, d, w)
    torso = [B(11.2, -10.2), B(15.0, -10.9), B(28.0, -14.6), B(43.0, -16.8), B(47.0, -15.2),
             B(50.0, -7.2), B(50.0, 6.2), B(47.0, 15.8), B(43.0, 16.8), B(28.0, 15.0),
             B(15.0, 11.2), B(11.2, 10.4)]
    a = B(0.0, 0.0)
    b = B(44.0, 0.0)
    cv.fill_poly_tube(torso, a, b, 14.8, JACKET, 'jacket')
    # 背部暗面
    cv.fill([B(13.0, -10.6), B(28.0, -14.2), B(43.0, -16.2), B(45.4, -12.4), B(40.0, -11.2),
             B(28.0, -11.0), B(16.0, -8.4), B(13.5, -9.2)], JACKET[3], 'jacket')
    cv.fill([B(15.0, -9.2), B(28.0, -11.8), B(41.0, -12.2), B(43.0, -15.0), B(38.0, -14.6),
             B(26.0, -12.6), B(16.5, -10.0)], JACKET[2], 'jacket')
    # 前胸受光
    cv.fill([B(22.0, 11.4), B(38.0, 12.0), B(45.0, 14.8), B(45.6, 16.6), B(38.0, 17.0),
             B(27.0, 14.8), B(19.0, 11.8)], JACKET[1], 'jacket')
    cv.fill([B(31.0, 13.2), B(40.0, 14.6), B(42.4, 15.8), B(34.0, 15.2), B(29.0, 14.0)], JACKET[0], 'jacket')
    # 内搭
    shirt = [B(44.0, 4.0), B(44.0, 9.8), B(34.0, 10.5), B(20.0, 8.8), B(12.2, 4.7),
             B(13.2, 1.1), B(30.0, 2.1), B(41.0, 2.5)]
    cv.fill(shirt, SHIRT[1], 'shirt')
    cv.fill([B(44.0, 6.8), B(44.0, 9.8), B(34.0, 10.5), B(26.0, 9.4), B(28.0, 6.8), B(38.0, 6.7)], SHIRT[2], 'shirt')
    cv.fill([B(42.0, 3.2), B(30.0, 2.8), B(16.0, 1.9), B(28.0, 4.1), B(40.0, 4.5)], SHIRT[0], 'shirt')
    cv.fill([B(30.0, 8.2), B(20.0, 8.8), B(14.0, 5.6), B(15.6, 4.0), B(24.0, 5.8)], SHIRT[3], 'shirt')
    # 前襟霓虹滚边
    cv.fill(strip(B(43.6, 10.0), B(34.0, 10.7), 0.9), CYAN[2], 'jacket')
    cv.fill(strip(B(34.0, 10.7), B(20.0, 9.0), 0.9), CYAN[2], 'jacket')
    cv.fill(strip(B(20.0, 9.0), B(12.4, 4.8), 0.9), CYAN[2], 'jacket')
    cv.fill(strip(B(43.6, 10.5), B(34.0, 11.2), 0.7), CYAN[1], 'jacket')
    # 拉链 / 扣带
    cv.fill(strip(B(30.0, 1.6), B(14.0, 3.3), 0.7), CYAN[3], 'jacket')
    cv.fill([B(33.0, 4.8), B(33.0, 6.8), B(35.0, 6.6), B(35.0, 4.6)], STEEL[1], 'jacket')
    # 下摆
    cv.fill([B(9.4, -10.4), B(9.4, 10.6), B(12.6, 10.2), B(12.6, -10.2)], JACKET[3], 'jacket')
    cv.fill(strip(B(10.0, -10.2), B(10.0, 10.4), 0.9), MAGENTA[2], 'jacket')
    cv.fill(strip(B(12.2, -10.0), B(12.2, 10.2), 0.6), JACKET[1], 'jacket')
    # 肩部拼块
    cv.fill([B(44.0, 7.8), B(46.2, 12.0), B(48.0, 10.4), B(46.4, 4.6)], JACKET[2], 'jacket')
    # 缝线
    cv.fill(strip(B(38.0, -6.6), B(30.0, -4.6), 0.55), JACKET[4], 'jacket')
    cv.fill(strip(B(27.0, 7.6), B(22.0, 5.6), 0.55), SHIRT[3], 'shirt')


def draw_neck(cv, sk):
    nb = sk['neckbase']
    hc = sk['headc']
    top = (hc[0] - 0.2, hc[1] + 4.0)
    cv.fill_tube(nb, top, 5.4, 4.7, SKIN, 'neck', bias=-0.20)
    cv.fill(strip((nb[0] + 2.2, nb[1]), (top[0] + 1.6, top[1]), 1.2), SKIN[3], 'neck')


def draw_collar(cv, sk):
    nb = sk['neckbase']

    def C(dx, dy):
        return (nb[0] + dx, nb[1] + dy)

    outer = [C(-8.6, 2.6), C(-10.0, -1.6), C(-9.2, -7.2), C(-6.6, -11.4), C(-2.6, -13.0),
             C(1.4, -12.6), C(4.6, -10.2), C(6.2, -6.4), C(6.0, -1.6), C(4.8, 2.4),
             C(3.2, -0.8), C(3.4, -5.0), C(1.8, -7.8), C(-1.6, -8.2), C(-4.4, -6.0),
             C(-5.6, -2.4), C(-5.2, 1.8)]
    cv.fill(outer, JACKET[2], 'collar')
    # 内衬暗面
    cv.fill([C(3.0, -1.0), C(3.2, -5.0), C(1.7, -7.6), C(-1.4, -8.0), C(-2.6, -6.4),
             C(-1.8, -4.0), C(0.6, -3.2), C(2.2, -1.6)], SHIRT[3], 'collar')
    # 背光
    cv.fill([C(-8.4, 1.8), C(-9.8, -1.6), C(-9.0, -6.6), C(-6.8, -10.2), C(-5.2, -9.0),
             C(-7.2, -5.2), C(-7.6, -0.6), C(-6.6, 2.2)], JACKET[3], 'collar')
    # 顶部霓虹边
    cv.fill(strip(C(-9.2, -6.8), C(-6.6, -11.0), 0.9), CYAN[2], 'collar')
    cv.fill(strip(C(-6.6, -11.0), C(-2.6, -12.6), 0.9), CYAN[2], 'collar')
    cv.fill(strip(C(-2.6, -12.6), C(1.2, -12.2), 0.9), CYAN[2], 'collar')
    cv.fill(strip(C(1.2, -12.2), C(4.4, -9.8), 0.9), CYAN[3], 'collar')
    # 前领片
    cv.fill([C(3.0, -0.4), C(3.0, -4.8), C(1.6, -7.4), C(-1.0, -7.8), C(-0.6, -6.0),
             C(0.6, -3.4), C(1.4, -0.8)], JACKET[1], 'collar')
    cv.fill(strip(C(-1.0, -7.4), C(2.9, -4.6), 0.7), CYAN[1], 'collar')


# --------------------------------------------------------------------------
# 头部（基底：皮肤/耳朵/头发；五官由 1x 覆盖层绘制，保证清晰）
# --------------------------------------------------------------------------
HEAD_SKIN = [
    (0.4, -12.5), (3.8, -11.6), (7.0, -9.8), (9.5, -7.4), (10.7, -4.6), (10.8, -1.8),
    (11.6, 0.6), (12.5, 3.2), (12.4, 4.6), (11.3, 5.4), (11.0, 6.6), (11.3, 8.4),
    (10.6, 10.3), (9.0, 12.1), (6.6, 13.5), (3.6, 14.0), (0.7, 13.7), (-2.1, 13.0),
    (-4.9, 11.8), (-7.3, 10.0), (-9.3, 7.6), (-10.7, 5.0), (-11.5, 2.0), (-11.5, -1.5),
    (-10.7, -4.9), (-9.2, -8.1), (-7.0, -10.5), (-4.0, -12.1), (-1.6, -12.6),
]
EAR = [(-11.0, 0.2), (-9.6, -0.7), (-8.1, 0.5), (-8.2, 3.0), (-9.3, 4.9),
       (-10.9, 4.2), (-11.8, 2.2)]
HAIR_CAP = [
    (-12.6, 4.0), (-13.2, 0.4), (-13.0, -3.6), (-12.0, -7.4), (-10.2, -10.6),
    (-7.6, -13.2), (-4.6, -15.0), (-1.2, -15.8), (2.2, -15.2), (5.4, -14.0),
    (8.2, -12.6), (10.2, -10.6), (11.2, -8.6), (11.2, -7.0), (9.6, -7.4),
    (7.2, -8.2), (4.4, -8.8), (1.2, -8.8), (-2.0, -8.2), (-5.0, -7.2),
    (-7.8, -5.8), (-10.0, -3.6), (-11.2, -1.2), (-11.6, 1.6), (-12.0, 3.4),
]
HAIR_SPIKES = [
    [(-12.8, -2.6), (-16.6, -4.8), (-13.2, -6.4), (-11.6, -5.8)],
    [(-12.4, -7.0), (-15.6, -11.8), (-12.8, -10.2), (-10.8, -8.2)],
    [(-10.8, -9.6), (-11.8, -14.8), (-9.2, -12.8), (-8.4, -10.8)],
    [(-8.6, -12.0), (-9.0, -17.0), (-6.2, -14.4), (-6.0, -12.4)],
    [(-5.8, -13.6), (-5.6, -17.0), (-3.0, -15.0), (-2.8, -13.4)],
    [(-2.4, -14.6), (-1.4, -16.8), (0.8, -15.4), (0.8, -13.8)],
    [(1.2, -14.6), (3.2, -16.4), (4.8, -14.2), (3.8, -12.8)],
    [(4.8, -13.8), (7.2, -15.2), (7.8, -12.8), (6.0, -11.6)],
    [(7.6, -12.2), (10.4, -12.8), (10.0, -10.2), (8.2, -10.0)],
    [(9.8, -9.6), (11.6, -7.4), (11.4, -9.8), (10.2, -10.8)],
]
HAIR_FRINGE = [
    [(10.6, -8.2), (10.5, -6.5), (9.3, -7.6)],
    [(9.1, -8.4), (8.2, -6.9), (7.2, -8.2)],
    [(6.9, -8.6), (5.9, -7.1), (4.9, -8.4)],
    [(4.6, -8.6), (3.6, -7.2), (2.5, -8.6)],
    [(2.2, -8.6), (1.3, -7.4), (0.3, -8.6)],
    [(-0.3, -8.4), (-1.4, -7.1), (-2.4, -8.2)],
    [(-2.8, -8.0), (-3.9, -6.7), (-4.9, -7.8)],
    [(-5.3, -7.6), (-6.5, -6.1), (-7.5, -7.2)],
    [(-7.9, -6.8), (-9.1, -5.1), (-9.9, -6.4)],
]
SIDEBURN = [(-11.2, -2.4), (-9.6, -1.0), (-9.6, 2.6), (-10.8, 3.8), (-11.6, 1.6)]
FRONT_LOCK = [(10.4, -9.4), (11.6, -6.8), (10.2, -7.0), (9.8, -9.0)]
HAIR_SHADOW = [
    (-12.6, 4.0), (-13.2, 0.4), (-12.8, -3.4), (-11.6, -6.6), (-10.0, -8.2),
    (-8.2, -9.2), (-6.8, -8.8), (-8.6, -6.2), (-10.4, -2.8), (-11.2, 0.8),
    (-11.4, 3.4),
]
HAIR_HI = [
    ((-11.8, -8.2), (-14.8, -11.2), 0.9),
    ((-10.2, -11.2), (-9.2, -15.8), 0.9),
    ((-8.0, -13.2), (-6.8, -16.2), 0.9),
    ((-5.0, -14.6), (-4.0, -16.4), 0.9),
    ((-2.0, -14.8), (-0.8, -16.0), 0.8),
    ((0.8, -14.8), (2.6, -15.8), 0.8),
    ((3.6, -14.0), (6.4, -14.8), 0.8),
    ((8.2, -12.6), (10.0, -12.8), 0.8),
    ((-12.2, -3.2), (-15.4, -4.4), 0.8),
    ((-2.0, -13.2), (5.0, -13.6), 0.8),
]
CYAN_STREAKS = [
    ((-9.6, -11.0), (-8.4, -15.4), 0.9),
    ((-5.6, -13.8), (-4.6, -15.8), 0.8),
    ((-0.6, -14.2), (1.6, -15.2), 0.8),
    ((6.0, -13.0), (8.6, -12.2), 0.8),
    ((10.2, -8.4), (11.2, -7.2), 0.7),
    ((-10.6, -4.2), (-12.2, -5.0), 0.7),
]
CYAN_TIPS = [
    ((-8.4, -15.4), (-8.0, -16.4), 0.7),
    ((-4.6, -15.8), (-4.2, -16.4), 0.6),
    ((1.6, -15.2), (2.0, -15.8), 0.6),
]
HAIRLINE = [(-9.9, -5.6), (-7.5, -6.7), (-5.3, -7.1), (-2.4, -7.4), (0.3, -7.8),
            (2.5, -7.8), (4.9, -7.6), (7.2, -7.4), (9.3, -7.0), (10.6, -6.6)]


def head_xf(center, tilt, k):
    cx, cy = center
    r = math.radians(tilt)
    c, s = math.cos(r), math.sin(r)

    def T(x, y):
        xx = x * k
        yy = y * k
        return (cx + xx * c - yy * s, cy + xx * s + yy * c)
    return T


def draw_head_base(cv, center, tilt=0.0, k=1.0, portrait=False):
    T = head_xf(center, tilt, k)

    def TP(pts):
        return [T(x, y) for x, y in pts]

    def P(pts, color, grp=HEAD_GROUP):
        cv.fill(TP(pts), color, grp)

    def L(a, b, w, color, grp=HEAD_GROUP):
        cv.fill(TP(strip(a, b, w)), color, grp)

    def SH(pts, ramp_, grp, cen, rx, ry, bias=0.0,
           th=(0.93, 0.40, 0.00, -0.38)):
        cv.fill_shaded(TP(pts), ramp_, grp, center=T(cen[0], cen[1]),
                       rx=rx * k, ry=ry * k, bias=bias, th=th)

    # 皮肤
    if portrait:
        # 头像：平涂 + 手绘明暗（避免椭球色带在大尺寸下出现条纹）
        P(HEAD_SKIN, SKIN[1], HEAD_GROUP)
        P(EAR, SKIN[1], HEAD_GROUP)
        P([(-7.2, -9.4), (0.6, -10.4), (6.8, -8.6), (5.0, -6.0), (-2.0, -6.4),
           (-6.4, -7.4)], SKIN[0])
        P([(9.4, -5.2), (11.0, -1.4), (11.8, 1.8), (10.8, 4.4), (9.6, 4.4),
           (9.9, 1.0), (9.0, -2.2)], SKIN[2])
        P([(5.6, 4.4), (8.8, 5.0), (8.8, 7.0), (6.8, 8.4), (5.2, 7.0), (4.6, 5.4)], SKIN[2])
        P([(0.8, 11.4), (3.4, 12.8), (6.0, 12.4), (7.6, 11.0), (5.4, 10.2), (2.0, 10.4)], SKIN[2])
        P([(1.6, 12.2), (3.4, 13.0), (5.0, 12.7), (3.6, 11.8)], SKIN[3])
        P([(-2.0, 13.0), (1.4, 14.2), (4.8, 14.1), (8.0, 13.0), (6.4, 12.3),
           (3.2, 13.3), (0.4, 12.7)], SKIN[3])
        P([(8.8, 1.4), (9.8, 3.6), (9.4, 4.6), (8.4, 3.2)], SKIN[2])
        P([(3.2, 2.2), (6.0, 1.8), (7.0, 3.4), (4.6, 4.0), (3.2, 3.4)], SKIN[0])
        P([(6.4, 11.0), (9.0, 10.6), (8.6, 12.0), (6.6, 12.3)], SKIN[0])
    else:
        SH(HEAD_SKIN, SKIN, HEAD_GROUP, (-0.6, -0.8), 11.9, 13.9, bias=0.06,
           th=(0.86, 0.25, -0.15, -0.52))
        SH(EAR, SKIN, HEAD_GROUP, (-9.8, 2.2), 2.6, 3.4, bias=-0.04)
        # 下颌阴影（只压在下缘，避免脏脸）
        P([(0.6, 11.8), (3.2, 12.9), (5.6, 12.5), (7.2, 11.4), (5.4, 10.6), (2.2, 10.8)], SKIN[2])
        P([(1.4, 12.4), (3.4, 13.1), (5.0, 12.8), (3.6, 12.0), (2.0, 12.0)], SKIN[3])
        # 颧骨下极轻暗面 / 鼻侧阴影
        P([(7.0, 5.2), (8.8, 5.6), (8.4, 6.8), (7.0, 6.4)], SKIN[2])
        P([(8.9, 1.6), (9.7, 3.6), (9.3, 4.4), (8.5, 3.2)], SKIN[2])
    # 耳朵内部
    P([(-10.4, 1.0), (-9.2, 1.0), (-8.8, 2.4), (-9.6, 3.8), (-10.5, 3.4)], SKIN[2])
    L((-9.8, 1.6), (-9.2, 3.2), 0.8, SKIN[3])
    L((-11.0, 0.4), (-10.6, 2.6), 0.7, SKIN[0])
    # 头发
    hair_polys = [HAIR_CAP] + HAIR_SPIKES + HAIR_FRINGE + [SIDEBURN, FRONT_LOCK]
    for hp in hair_polys:
        P(hp, HAIR[2], HAIR_GROUP)
    P(HAIR_SHADOW, HAIR[3], HAIR_GROUP)
    # 发丝高光 / 青色挑染
    for (a, b, w) in HAIR_HI:
        L(a, b, w, HAIR[1], HAIR_GROUP)
    for (a, b, w) in HAIR_HI[1:3]:
        L(a, b, w * 0.7, HAIR[0], HAIR_GROUP)
    for (a, b, w) in CYAN_STREAKS[:4]:
        L(a, b, w, CYAN[2], HAIR_GROUP)
    for (a, b, w) in CYAN_TIPS[:2]:
        L(a, b, w, CYAN[1], HAIR_GROUP)
    # 发际线暗边
    for i in range(len(HAIRLINE) - 1):
        L(HAIRLINE[i], HAIRLINE[i + 1], 0.9, HAIR[4], HAIR_GROUP)
    # 耳环
    P([(-10.4, 5.2), (-9.6, 5.6), (-9.8, 6.6), (-10.6, 6.2)], CYAN[2], HEAD_GROUP)
    P([(-10.3, 5.4), (-9.9, 5.6), (-10.0, 6.0), (-10.4, 5.8)], CYAN[0], HEAD_GROUP)
    P([(-10.0, 6.6), (-9.6, 6.8), (-9.7, 7.2), (-10.1, 7.0)], MAGENTA[2], HEAD_GROUP)


# --------------------------------------------------------------------------
# 五官（1x 像素覆盖层：保证面部清晰可读）
# --------------------------------------------------------------------------
SCLERA = hx('#fbf7ff')
SCLERA_SH = hx('#cfc4ea')
IRIS_HI = CYAN[1]
IRIS = CYAN[2]
IRIS_D = CYAN[3]
PUPIL = hx('#120b20')
BROW = hx('#1b1433')
BROW_HI = hx('#3d3768')
LIP = hx('#6d3339')
LIP_D = hx('#4a2028')
TONGUE = hx('#7a2c40')


def draw_face_overlay(img, cx, cy, expr='normal', tilt=0.0):
    arr = np.array(img)
    H, W = arr.shape[:2]
    r = math.radians(tilt)
    ca, sa = math.cos(r), math.sin(r)

    def pix(lx, ly, color):
        x = int(round(cx + lx * ca - ly * sa))
        y = int(round(cy + lx * sa + ly * ca))
        if 0 <= x < W and 0 <= y < H and arr[y, x, 3] > 0:
            arr[y, x, :3] = color
            arr[y, x, 3] = 255

    def row(ly, x0, x1, color):
        for lx in range(x0, x1 + 1):
            pix(lx, ly, color)

    def rect(x0, y0, x1, y1, color):
        for ly in range(y0, y1 + 1):
            row(ly, x0, x1, color)

    def brow(rows):
        for ly, xs in rows:
            for lx in xs:
                pix(lx, ly, BROW)
        ly, xs = rows[-1]
        for lx in xs:
            pix(lx, ly - 1, BROW_HI)

    attack = expr in ('attack', 'special')
    hurt = expr == 'hurt'
    ko = expr == 'ko'
    victory = expr == 'victory'
    closed = hurt or ko

    # ---------------- 眼睛 ----------------
    if closed:
        if hurt:
            for (x, y) in ((4, -1), (5, 0), (6, 1), (7, 1), (8, 0), (9, -1)):
                pix(x, y, INK)
            for (x, y) in ((-3, -1), (-2, 0), (-1, 1), (0, 0), (1, -1)):
                pix(x, y, INK)
            pix(2, -3, SKIN[2])
            pix(3, -3, SKIN[2])
        else:
            for (x, y) in ((4, 0), (5, 0), (6, 1), (7, 1), (8, 0), (9, 0)):
                pix(x, y, INK)
            for (x, y) in ((-3, 0), (-2, 0), (-1, 1), (0, 0), (1, 0)):
                pix(x, y, INK)
    else:
        # 近眼（朝向右前方）
        row(-2, 4, 9, INK)
        row(-1, 4, 9, SCLERA)
        pix(4, -1, INK)
        pix(7, -1, IRIS_HI)
        pix(8, -1, IRIS)
        pix(9, -1, INK)
        row(0, 5, 8, SCLERA)
        pix(4, 0, INK)
        pix(7, 0, IRIS)
        pix(8, 0, PUPIL)
        pix(9, 0, INK)
        row(1, 5, 8, SCLERA_SH)
        pix(4, 1, INK)
        pix(5, 1, SCLERA)
        pix(6, 1, IRIS)
        pix(7, 1, IRIS)
        pix(8, 1, PUPIL)
        pix(9, 1, INK)
        pix(4, 2, SCLERA_SH)
        pix(5, 2, SCLERA)
        pix(6, 2, SCLERA)
        pix(7, 2, IRIS_D)
        pix(8, 2, IRIS_D)
        pix(9, 2, INK)
        if attack:
            pix(5, 1, SCLERA_SH)
            pix(6, 2, SCLERA_SH)
        if victory:
            pix(6, 0, hx('#ffffff'))
        # 远眼
        row(-2, -3, 1, INK)
        row(-1, -3, 1, SCLERA)
        pix(-3, -1, INK)
        pix(0, -1, IRIS_HI)
        pix(1, -1, INK)
        row(0, -2, 0, SCLERA)
        pix(-3, 0, INK)
        pix(-2, 0, SCLERA)
        pix(-1, 0, IRIS)
        pix(0, 0, PUPIL)
        pix(1, 0, INK)
        row(1, -2, 0, SCLERA_SH)
        pix(-3, 1, INK)
        pix(-2, 1, SCLERA_SH)
        pix(-1, 1, IRIS_D)
        pix(0, 1, IRIS_D)
        pix(1, 1, INK)
        # 下眼睑
        row(3, 5, 8, SKIN[2])
        pix(-2, 2, SKIN[2])
        pix(-1, 2, SKIN[2])

    # ---------------- 眉毛 ----------------
    if hurt:
        brow([(-6, [3, 4, 5]), (-7, [5, 6, 7]), (-8, [7, 8, 9])])
        brow([(-6, [-3, -2, -1]), (-7, [-1, 0])])
    elif ko:
        row(-5, 3, 9, BROW)
        row(-5, -4, 2, BROW)
    elif attack:
        brow([(-4, [3, 4, 5]), (-5, [5, 6, 7, 8]), (-6, [8, 9, 10])])
        brow([(-4, [-2, -1, 0, 1]), (-5, [-4, -3, -2])])
    elif victory:
        brow([(-4, [3, 4, 5, 6]), (-5, [6, 7, 8, 9])])
        brow([(-4, [-3, -2, -1]), (-5, [-4, -3])])
    else:
        brow([(-4, [3, 4, 5]), (-5, [5, 6, 7, 8]), (-6, [8, 9, 10])])
        brow([(-4, [-1, 0, 1]), (-5, [-3, -2, -1]), (-6, [-4, -3])])

    # ---------------- 刀疤（右眉） ----------------
    for (sx, sy) in ((9, -7), (9, -6), (9, -5), (9, -4), (9, -3)):
        pix(sx, sy, PALE)
    pix(8, -5, PALE)
    pix(8, -4, SKIN[2])

    # ---------------- 鼻子 ----------------
    pix(7, 2, SKIN[2])
    pix(7, 3, SKIN[2])
    pix(8, 3, SKIN[2])
    pix(10, 3, SKIN[0])
    pix(10, 4, SKIN[0])
    pix(11, 4, SKIN[0])
    pix(10, 5, SKIN[2])
    if hurt:
        pix(8, 4, SKIN[3])
        pix(9, 5, INK2)
        pix(10, 5, INK2)
    else:
        pix(9, 5, INK2)
        pix(8, 5, SKIN[3])
        pix(9, 6, SKIN[3])
    row(6, 7, 9, SKIN[2])

    # ---------------- 嘴 ----------------
    if attack:
        row(7, 5, 10, MOUTH_DARK)
        row(7, 5, 9, TOOTH)
        pix(7, 7, INK2)
        pix(9, 7, INK2)
        row(8, 5, 10, MOUTH_DARK)
        row(9, 6, 9, SKIN[0])
        pix(10, 8, LIP_D)
        row(10, 5, 9, SKIN[2])
    elif hurt:
        row(6, 4, 10, MOUTH_DARK)
        row(6, 4, 9, TOOTH)
        pix(6, 6, INK2)
        pix(8, 6, INK2)
        row(7, 4, 10, MOUTH_DARK)
        row(8, 6, 9, TONGUE)
        row(9, 5, 9, SKIN[3])
        row(10, 4, 9, SKIN[2])
    elif ko:
        rect(6, 8, 9, 9, MOUTH_DARK)
        row(10, 6, 9, SKIN[2])
        pix(5, 8, SKIN[2])
        pix(5, 9, SKIN[2])
    elif victory:
        row(8, 4, 9, LIP)
        pix(10, 7, LIP)
        row(9, 6, 9, SKIN[0])
        row(10, 5, 8, SKIN[2])
    else:
        row(8, 5, 9, LIP)
        pix(10, 8, LIP_D)
        pix(4, 8, SKIN[2])
        row(9, 6, 9, SKIN[0])
        row(10, 5, 8, SKIN[2])

    # ---------------- 下颌 / 颧骨 / 耳 ----------------
    row(11, 5, 8, SKIN[2])
    pix(9, 11, SKIN[3])
    pix(6, 12, SKIN[0])
    pix(7, 12, SKIN[0])
    pix(8, 12, SKIN[2])
    pix(3, 4, SKIN[2])
    pix(3, 5, SKIN[2])
    pix(2, 6, SKIN[2])
    pix(-9, 2, SKIN[3])
    pix(-8, 3, SKIN[3])
    pix(-10, 1, SKIN[0])
    if victory:
        pix(8, 2, SKIN[0])
    return Image.fromarray(arr, 'RGBA')


# --------------------------------------------------------------------------
# 人物合成
# --------------------------------------------------------------------------
def draw_figure(cv, p):
    sk = skeleton(p)
    draw_leg(cv, sk['hipF'], sk['kneeF'], sk['ankleF'], sk['faF'], 'legFar', True)
    draw_leg(cv, sk['hipN'], sk['kneeN'], sk['ankleN'], sk['faN'], 'legNear', False)
    far_front = p.get('far_arm_front', True)
    if not far_front:
        draw_arm(cv, sk['shoulderF'], sk['elbowF'], sk['wristF'], 'armFar', True)
    draw_pelvis(cv, sk)
    draw_belt(cv, sk)
    draw_jacket(cv, sk)
    draw_neck(cv, sk)
    draw_collar(cv, sk)
    if far_front:
        draw_arm(cv, sk['shoulderF'], sk['elbowF'], sk['wristF'], 'armFar', True)
    hl = (int(round(sk['headc'][0])), int(round(sk['headc'][1])))
    draw_head_base(cv, hl, p.get('head_tilt', 0.0), 1.0)
    draw_arm(cv, sk['shoulderN'], sk['elbowN'], sk['wristN'], 'armNear', False)
    return dict(head_px=(hl[0] + AX, hl[1] + AY), head_local=hl,
                tilt=p.get('head_tilt', 0.0), expr=p.get('expr', 'normal'), sk=sk)


def dilate(mask, n=1):
    out = mask.copy()
    for _ in range(n):
        cur = out.copy()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            out |= nb(cur, dx, dy)
    return out


def add_glow(img, strength=0.0):
    if strength <= 0.02:
        return img
    arr = np.array(img)
    a = arr[:, :, 3] > 0
    d1 = dilate(a, 1)
    d2 = dilate(a, 2)
    d3 = dilate(a, 3)
    d4 = dilate(a, 4)
    rings = ((d2 & ~d1, 210), (d3 & ~d2, 130), (d4 & ~d3, 70))
    H, W = a.shape
    xs = np.arange(W)[None, :].repeat(H, axis=0)
    for mask, alpha in rings:
        al = int(alpha * strength)
        if al <= 0:
            continue
        cyan_m = mask & (xs < W // 2)
        mag_m = mask & (xs >= W // 2)
        arr[cyan_m, :3] = hx('#3df3ff')
        arr[cyan_m, 3] = al
        arr[mag_m, :3] = hx('#ff2f8e')
        arr[mag_m, 3] = al
    return Image.fromarray(arr, 'RGBA')


def render_frame(p, rim=True, outline=True, face=True):
    cv = Canvas(FW, FH, S, AX, AY)
    info = draw_figure(cv, p)
    rgb, a = cv.finish(rim=rim, outline=outline)
    img = Image.fromarray(np.dstack([rgb, (a.astype(np.uint8) * 255)]), 'RGBA')
    if face:
        img = draw_face_overlay(img, info['head_px'][0], info['head_px'][1],
                                p.get('expr', 'normal'), p.get('head_tilt', 0.0))
    img = add_glow(img, p.get('glow', 0.0))
    return img


# --------------------------------------------------------------------------
# 头像（192x192，头肩特写）
# --------------------------------------------------------------------------
def draw_portrait_face(img, cx, cy, k=4.15):
    arr = np.array(img)
    H, W = arr.shape[:2]

    def M(lx, ly):
        return (cx + lx * k, cy + ly * k)

    def poly(pts, color):
        # 注意：pts 已经是头像像素坐标（调用方用 M() 映射或直接给出），这里不再映射
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0 = int(math.floor(min(xs)))
        x1 = int(math.ceil(max(xs)))
        y0 = int(math.floor(min(ys)))
        y1 = int(math.ceil(max(ys)))
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(W - 1, x1)
        y1 = min(H - 1, y1)
        if x1 < x0 or y1 < y0:
            return
        im = Image.new('L', (x1 - x0 + 1, y1 - y0 + 1), 0)
        ImageDraw.Draw(im).polygon([(p[0] - x0, p[1] - y0) for p in pts], fill=255)
        m = np.array(im) > 127
        sub = arr[y0:y1 + 1, x0:x1 + 1]
        sub[m, :3] = color
        sub[m, 3] = 255

    def line(a, b, w, color):
        p0 = M(a[0], a[1])
        p1 = M(b[0], b[1])
        ww = w * k
        poly(strip(p0, p1, ww), color)

    def ell(lcx, lcy, rx, ry, color, ang=0.0):
        c = M(lcx, lcy)
        pts = ellipse_pts(c[0], c[1], rx * k, ry * k, ang, 28)
        poly(pts, color)

    # ---- 颧骨 / 下颌阴影 ----
    ell(7.0, 4.8, 2.2, 2.6, SKIN[2])
    poly([M(-2.0, 9.6), M(1.6, 11.8), M(5.6, 12.6), M(8.0, 11.0), M(6.0, 9.2),
          M(2.0, 9.0), M(-0.6, 8.2)], SKIN[2])
    poly([M(-1.2, 11.4), M(1.8, 12.6), M(4.8, 12.0), M(3.2, 10.8)], SKIN[3])
    # ---- 耳朵 ----
    ell(-9.5, 2.2, 1.5, 2.4, SKIN[2])
    ell(-9.6, 2.2, 0.9, 1.7, SKIN[3])
    line((-10.4, 0.6), (-10.1, 2.8), 0.28, SKIN[0])
    # ---- 近眼 ----
    # 眼窝
    ell(7.0, 1.4, 3.0, 1.3, SKIN[2])
    # 眼白
    poly([M(4.3, -0.6), M(4.9, -1.5), M(6.1, -1.9), M(7.6, -1.8), M(8.9, -1.2),
          M(9.8, -0.1), M(9.6, 0.9), M(8.6, 1.9), M(7.1, 2.2), M(5.7, 1.9),
          M(4.7, 1.0)], SCLERA)
    poly([M(4.8, 1.0), M(5.9, 1.9), M(7.3, 2.1), M(8.6, 1.6), M(9.2, 0.9),
          M(8.2, 1.4), M(6.9, 1.7), M(5.8, 1.4)], SCLERA_SH)
    # 虹膜
    ell(7.4, 0.2, 1.62, 1.82, IRIS_D)
    ell(7.4, 0.2, 1.34, 1.55, IRIS)
    ell(7.4, 0.2, 0.95, 1.2, IRIS_HI)
    ell(7.4, 0.2, 0.62, 0.82, PUPIL)
    ell(6.9, -0.5, 0.38, 0.4, hx('#ffffff'))
    ell(8.0, 1.1, 0.24, 0.22, CYAN[0])
    # 上眼线 / 睫毛
    line((4.3, 0.0), (4.4, -0.9), 0.4, INK)
    line((4.4, -0.9), (5.4, -1.7), 0.45, INK)
    line((5.4, -1.7), (6.9, -2.1), 0.45, INK)
    line((6.9, -2.1), (8.4, -1.9), 0.45, INK)
    line((8.4, -1.9), (9.6, -1.0), 0.45, INK)
    line((9.6, -1.0), (10.2, 0.1), 0.4, INK)
    line((9.2, -1.3), (10.6, -2.2), 0.34, INK)
    line((9.9, -0.2), (11.1, -0.6), 0.3, INK)
    # 双眼皮
    line((5.2, -2.5), (7.2, -2.9), 0.26, SKIN[2])
    line((7.2, -2.9), (9.2, -2.5), 0.26, SKIN[2])
    # 下眼睑
    line((5.2, 1.9), (7.0, 2.3), 0.24, SKIN[3])
    line((7.0, 2.3), (8.8, 1.9), 0.24, SKIN[3])
    # ---- 远眼 ----
    ell(0.2, 1.0, 2.4, 1.1, SKIN[2])
    poly([M(-2.0, 0.0), M(-1.4, -0.8), M(-0.2, -1.2), M(1.1, -1.0), M(1.9, -0.2),
          M(1.8, 0.8), M(0.8, 1.6), M(-0.6, 1.6), M(-1.8, 0.9)], SCLERA)
    poly([M(-1.6, 0.8), M(-0.5, 1.5), M(0.8, 1.5), M(1.6, 0.9), M(0.7, 1.1),
          M(-0.4, 1.1)], SCLERA_SH)
    ell(0.3, 0.3, 1.15, 1.35, IRIS_D)
    ell(0.3, 0.3, 0.9, 1.1, IRIS)
    ell(0.3, 0.3, 0.62, 0.8, IRIS_HI)
    ell(0.3, 0.3, 0.42, 0.58, PUPIL)
    ell(-0.2, -0.2, 0.26, 0.28, hx('#ffffff'))
    line((-2.0, 0.1), (-1.5, -0.7), 0.36, INK)
    line((-1.5, -0.7), (-0.2, -1.1), 0.4, INK)
    line((-0.2, -1.1), (1.2, -0.9), 0.4, INK)
    line((1.2, -0.9), (2.0, -0.1), 0.34, INK)
    line((-1.4, 1.4), (0.8, 1.6), 0.22, SKIN[3])
    # ---- 眉毛 ----
    poly(strip(M(3.0, -3.4), M(6.4, -4.6), 0.95 * k), BROW)
    poly(strip(M(6.4, -4.6), M(9.9, -5.1), 0.85 * k), BROW)
    line((3.6, -3.8), (6.4, -4.8), 0.3, BROW_HI)
    line((6.6, -5.2), (9.6, -5.5), 0.22, hx('#463f78'))
    poly(strip(M(-4.4, -4.4), M(-1.4, -4.9), 0.65 * k), BROW)
    poly(strip(M(-1.4, -4.9), M(1.6, -4.4), 0.55 * k), BROW)
    line((-4.0, -4.7), (-1.2, -5.1), 0.18, hx('#463f78'))
    # ---- 刀疤 ----
    line((9.7, -6.8), (8.9, -1.4), 0.34, SKIN[3])
    line((9.5, -6.8), (8.7, -1.4), 0.42, PALE)
    line((8.8, -4.9), (9.7, -4.7), 0.24, PALE)
    line((9.0, -3.6), (9.7, -3.4), 0.2, PALE)
    # ---- 鼻子 ----
    line((8.7, -1.6), (9.6, 2.4), 0.44, SKIN[2])
    line((9.6, 2.4), (10.4, 3.4), 0.42, SKIN[2])
    line((9.6, 2.9), (11.6, 3.1), 0.3, SKIN[0])
    ell(11.2, 3.1, 0.55, 0.4, SKIN[0])
    line((8.5, 4.2), (10.8, 3.9), 0.3, SKIN[2])
    ell(10.2, 4.3, 0.5, 0.3, SKIN[3])
    ell(9.9, 4.45, 0.34, 0.2, INK2)
    line((8.2, 5.1), (10.6, 4.9), 0.28, SKIN[2])
    line((6.4, 7.0), (6.6, 7.7), 0.2, SKIN[2])
    # ---- 嘴（自信的坏笑） ----
    line((4.6, 8.7), (7.2, 8.4), 0.4, LIP_D)
    line((7.2, 8.4), (9.8, 8.1), 0.36, LIP)
    line((9.8, 8.1), (10.6, 8.8), 0.24, LIP_D)
    line((9.6, 7.9), (10.3, 7.5), 0.18, LIP_D)
    poly([M(7.0, 8.58), M(8.4, 8.52), M(8.4, 9.0), M(7.0, 9.0)], hx('#e4d8ea'))
    line((7.0, 8.8), (8.4, 8.75), 0.1, hx('#b9aac6'))
    line((5.8, 9.7), (8.8, 9.55), 0.34, SKIN[0])
    line((5.4, 10.2), (9.0, 10.0), 0.3, SKIN[2])
    # ---- 下巴 / 颧骨高光 ----
    ell(7.0, 11.9, 1.3, 0.42, SKIN[0])
    ell(4.9, 3.0, 1.3, 0.6, SKIN[0])
    line((3.4, 12.7), (7.2, 13.2), 0.24, SKIN[3])
    # ---- 耳环 ----
    poly([M(-10.0, 5.0), M(-9.3, 5.4), M(-9.5, 6.3), M(-10.2, 5.9)], CYAN[3])
    poly([M(-9.9, 5.1), M(-9.5, 5.4), M(-9.6, 5.9), M(-10.0, 5.7)], CYAN[1])
    ell(-9.7, 5.6, 0.2, 0.2, CYAN[0])
    poly([M(-9.7, 6.3), M(-9.2, 6.5), M(-9.3, 6.9), M(-9.8, 6.7)], MAGENTA[2])
    return Image.fromarray(arr, 'RGBA')


def render_portrait():
    W = H = 192
    cv = Canvas(W, H, 2)
    cx, cy = 96, 74
    k = 4.15

    def B(lx, ly):
        return (cx + lx * k, cy + ly * k)

    # ---- 夹克主体（肖像：直接使用 192 画布像素） ----
    jacket = [(16, 192), (22, 170), (34, 156), (54, 147), (74, 143),
              (96, 141), (118, 143), (140, 147), (158, 156), (170, 170), (176, 192)]
    cv.fill(jacket, JACKET[2], 'jacket')
    # 左侧受光
    cv.fill([(17, 188), (24, 168), (38, 155), (58, 147), (76, 143), (72, 152),
             (54, 160), (36, 172), (24, 186)], JACKET[1], 'jacket')
    cv.fill([(26, 170), (40, 158), (58, 151), (74, 147), (68, 154), (50, 161),
             (38, 170)], JACKET[0], 'jacket')
    # 右侧背光
    cv.fill([(120, 143), (142, 148), (160, 158), (172, 174), (177, 192), (128, 192),
             (126, 168), (116, 152)], JACKET[3], 'jacket')
    cv.fill([(146, 158), (160, 168), (172, 184), (176, 192), (146, 192), (140, 172)],
            JACKET[4], 'jacket')
    # 内搭（胸口）
    shirt = [(80, 147), (112, 147), (116, 192), (76, 192)]
    cv.fill(shirt, SHIRT[1], 'shirt')
    cv.fill([(80, 147), (92, 147), (92, 192), (76, 192)], SHIRT[2], 'shirt')
    cv.fill([(104, 170), (116, 172), (116, 192), (100, 192)], SHIRT[3], 'shirt')
    cv.fill([(90, 150), (104, 150), (106, 168), (86, 168)], SHIRT[2], 'shirt')
    # 拉链
    cv.fill(strip((96, 150), (96, 192), 3.0), STEEL[2], 'jacket')
    cv.fill(strip((96, 150), (96, 192), 1.2), STEEL[1], 'jacket')
    cv.fill([(92, 152), (100, 152), (100, 158), (92, 158)], STEEL[1], 'jacket')
    # ---- 脖子（覆盖在夹克之上，头部之下） ----
    chin_y = cy + 13.9 * k
    cv.fill_tube((cx - 1, chin_y - 10), (cx - 1, chin_y + 14), 13.0, 17.0, SKIN, 'neck', bias=-0.22)
    cv.fill(strip((cx + 3, chin_y - 6), (cx + 4, chin_y + 14), 5), SKIN[3], 'neck')
    cv.fill(strip((cx - 8, chin_y - 2), (cx - 7, chin_y + 12), 4), SKIN[2], 'neck')
    cv.fill([(cx - 16, chin_y - 9), (cx + 13, chin_y - 9), (cx + 11, chin_y + 1),
             (cx - 14, chin_y + 2)], SKIN[4], 'neck')
    # ---- 领子（高领，贴着脖子两侧） ----
    collarL = [(64, 158), (68, 144), (76, 136), (85, 138), (83, 148), (76, 156)]
    collarR = [(128, 158), (124, 144), (116, 136), (107, 138), (109, 148), (116, 156)]
    cv.fill(collarL, JACKET[3], 'collar')
    cv.fill([(68, 156), (72, 145), (79, 140), (84, 142), (82, 149), (76, 156)], JACKET[2], 'collar')
    cv.fill(collarR, JACKET[2], 'collar')
    cv.fill([(124, 156), (120, 145), (113, 140), (108, 142), (110, 149), (116, 156)], JACKET[1], 'collar')
    # 领口霓虹边
    cv.fill(strip((78, 137), (70, 144), 2.2), CYAN[2], 'collar')
    cv.fill(strip((70, 144), (66, 154), 2.0), CYAN[3], 'collar')
    cv.fill(strip((114, 137), (122, 144), 2.2), CYAN[2], 'collar')
    # 下摆霓虹
    cv.fill(strip((18, 183), (174, 183), 2.2), MAGENTA[2], 'jacket')
    cv.fill(strip((18, 186), (174, 186), 1.2), MAGENTA[3], 'jacket')
    # 肩线 / 缝线
    cv.fill(strip((24, 166), (56, 152), 1.4), JACKET[4], 'jacket')
    cv.fill(strip((136, 152), (166, 166), 1.4), JACKET[4], 'jacket')
    cv.fill(strip((78, 158), (88, 163), 1.2), JACKET[4], 'jacket')
    # ---- 头部 ----
    draw_head_base(cv, (cx, cy), 0.0, k, portrait=True)
    rgb, a = cv.finish()
    img = Image.fromarray(np.dstack([rgb, (a.astype(np.uint8) * 255)]), 'RGBA')
    # 头像：额外发丝细节（在基底之上、脸之下）
    img = draw_portrait_hair_detail(img, cx, cy, k)
    img = draw_portrait_face(img, cx, cy, k)
    return img


def draw_portrait_hair_detail(img, cx, cy, k):
    arr = np.array(img)
    H, W = arr.shape[:2]

    def line(a, b, w, color):
        p0 = (cx + a[0] * k, cy + a[1] * k)
        p1 = (cx + b[0] * k, cy + b[1] * k)
        pts = strip(p0, p1, w * k)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0 = max(0, int(math.floor(min(xs))))
        x1 = min(W - 1, int(math.ceil(max(xs))))
        y0 = max(0, int(math.floor(min(ys))))
        y1 = min(H - 1, int(math.ceil(max(ys))))
        if x1 < x0 or y1 < y0:
            return
        im = Image.new('L', (x1 - x0 + 1, y1 - y0 + 1), 0)
        ImageDraw.Draw(im).polygon([(p[0] - x0, p[1] - y0) for p in pts], fill=255)
        m = np.array(im) > 127
        sub = arr[y0:y1 + 1, x0:x1 + 1]
        sub[m, :3] = color
        sub[m, 3] = 255

    # 细发丝（指向发梢）
    line((-11.6, -8.4), (-14.6, -11.2), 0.22, HAIR[0])
    line((-10.2, -10.6), (-11.2, -14.4), 0.2, HAIR[1])
    line((-9.0, -12.4), (-8.2, -16.2), 0.2, HAIR[1])
    line((-6.4, -13.6), (-5.2, -16.2), 0.2, HAIR[0])
    line((-3.0, -14.4), (-1.6, -16.2), 0.2, HAIR[1])
    line((0.4, -14.6), (2.4, -15.6), 0.2, HAIR[0])
    line((4.4, -13.6), (6.8, -14.6), 0.2, HAIR[1])
    line((8.0, -12.0), (10.0, -12.4), 0.2, HAIR[0])
    line((-12.4, -3.6), (-15.0, -4.8), 0.2, HAIR[1])
    # 青色发光挑染
    line((-9.2, -10.8), (-8.4, -15.2), 0.34, CYAN[2])
    line((-8.4, -15.2), (-8.0, -16.2), 0.26, CYAN[1])
    line((-5.4, -13.4), (-4.6, -15.6), 0.3, CYAN[2])
    line((-0.6, -14.0), (1.8, -15.0), 0.3, CYAN[2])
    line((6.0, -12.8), (8.8, -12.0), 0.28, CYAN[2])
    line((10.0, -8.4), (11.2, -7.2), 0.24, CYAN[1])
    # 刘海阴影线
    line((-9.6, -6.8), (-2.0, -8.2), 0.2, HAIR[4])
    line((-2.0, -8.2), (5.0, -8.4), 0.2, HAIR[4])
    line((5.0, -8.4), (9.6, -7.2), 0.2, HAIR[4])
    return Image.fromarray(arr, 'RGBA')


def render_head_only(p, face=True, rim=True):
    cv = Canvas(80, 80, S, 40, 40)
    draw_head_base(cv, (0, 0), 0.0, 1.0)
    rgb, a = cv.finish(rim=rim)
    img = Image.fromarray(np.dstack([rgb, (a.astype(np.uint8) * 255)]), 'RGBA')
    if face:
        img = draw_face_overlay(img, 40, 40, p.get('expr', 'normal'), 0.0)
    return img


# --------------------------------------------------------------------------
# 动画数据
# --------------------------------------------------------------------------
IDLE = [
    pose(hip=(0.0, -97.0), lean=3.2, twist=0.4, head_off=(0.4, 0.2),
         wristN=(26.5, -145.2), wristF=(8.5, -148.4)),
    pose(hip=(0.2, -97.8), lean=3.6, twist=0.6, head_off=(0.5, -0.5),
         wristN=(26.9, -146.3), wristF=(8.9, -149.4)),
    pose(hip=(0.1, -97.4), lean=3.4, twist=0.5, head_off=(0.4, -0.2),
         wristN=(26.6, -145.7), wristF=(8.6, -148.9)),
    pose(hip=(0.0, -96.9), lean=3.0, twist=0.3, head_off=(0.3, 0.3),
         wristN=(26.1, -144.8), wristF=(8.2, -148.0)),
]


def make_walk():
    out = []
    for i in range(8):
        ph = 2 * math.pi * i / 8
        nfx = 2.0 + 15.0 * math.cos(ph)
        ffx = 2.0 - 15.0 * math.cos(ph)
        nlift = max(0.0, -math.sin(ph))
        flift = max(0.0, math.sin(ph))
        out.append(pose(
            hip=(0.6 * math.sin(2 * ph), -97.0 + 1.3 * math.cos(2 * ph)),
            lean=4.5, twist=1.5 * math.cos(ph),
            head_off=(0.4, -0.35 * math.cos(2 * ph)),
            wristN=(26.0 - 8.0 * math.cos(ph), -141.0 + 2.5 * math.cos(2 * ph)),
            wristF=(9.0 + 7.0 * math.cos(ph), -146.0 + 2.5 * math.cos(2 * ph)),
            ankleN=(nfx, -10.5 - 7.5 * nlift), faN=-4.0 + 20.0 * nlift,
            ankleF=(ffx, -11.0 - 7.5 * flift), faF=-4.0 + 20.0 * flift,
            knee_hintN=(1.0, -0.35), knee_hintF=(1.0, -0.35),
            expr='normal'))
    return out


WALK = make_walk()

PUNCH1 = [
    pose(hip=(-0.8, -96.6), lean=1.6, twist=-1.6,
         wristN=(25.0, -144.0), wristF=(5.5, -146.5),
         ankleN=(13.0, -10.5), ankleF=(-13.5, -11.0), head_off=(0.1, 0.0)),
    pose(hip=(1.4, -96.2), lean=9.0, twist=2.4,
         wristN=(21.0, -143.0), wristF=(38.0, -145.5),
         ankleN=(14.5, -10.5), ankleF=(-15.5, -11.0), faF=6.0,
         head_off=(1.6, 0.2), expr='attack'),
    pose(hip=(1.0, -96.4), lean=6.5, twist=1.2,
         wristN=(23.5, -144.0), wristF=(30.0, -146.0),
         ankleN=(13.5, -10.5), ankleF=(-14.5, -11.0), expr='attack'),
    pose(hip=(0.0, -97.0), lean=3.2, twist=0.4,
         wristN=(26.5, -145.0), wristF=(9.0, -148.0), head_off=(0.4, 0.0)),
]

PUNCH2 = [
    pose(hip=(-1.0, -96.4), lean=3.0, twist=-2.2,
         wristN=(18.0, -140.0), wristF=(6.0, -148.0),
         ankleN=(13.0, -10.5), ankleF=(-13.5, -11.0), head_off=(0.0, 0.0)),
    pose(hip=(2.0, -95.6), lean=13.0, twist=4.2,
         wristN=(43.5, -145.0), wristF=(3.0, -149.5),
         ankleN=(15.5, -10.5), ankleF=(-17.0, -11.0), faF=8.0,
         head_off=(2.2, 0.3), expr='attack'),
    pose(hip=(1.6, -96.0), lean=10.0, twist=3.0,
         wristN=(38.0, -144.5), wristF=(4.5, -149.0),
         ankleN=(14.5, -10.5), ankleF=(-16.0, -11.0), expr='attack'),
    pose(hip=(0.2, -97.0), lean=3.4, twist=0.6,
         wristN=(26.0, -145.0), wristF=(8.5, -148.0), head_off=(0.4, 0.0)),
]

PUNCH3 = [
    pose(hip=(0.0, -95.0), lean=7.0, twist=-1.0,
         wristN=(20.0, -128.0), wristF=(8.0, -147.0),
         ankleN=(14.0, -10.5), ankleF=(-14.0, -11.0), head_off=(-0.2, 0.8)),
    pose(hip=(-1.0, -92.5), lean=9.0, twist=-1.5,
         wristN=(17.5, -123.0), wristF=(6.0, -146.0),
         ankleN=(15.0, -10.5), ankleF=(-15.0, -11.0),
         knee_hintN=(1.0, -0.4), knee_hintF=(1.0, -0.4),
         head_off=(-0.5, 1.2), expr='attack'),
    pose(hip=(2.0, -100.0), lean=-3.0, twist=1.5,
         wristN=(30.0, -160.0), wristF=(4.0, -149.0),
         ankleN=(13.0, -11.0), ankleF=(-16.5, -12.0), faN=-6.0, faF=14.0,
         head_off=(1.0, -0.6), expr='attack'),
    pose(hip=(2.5, -100.5), lean=-5.0, twist=2.0,
         wristN=(33.0, -166.0), wristF=(2.0, -150.0),
         ankleN=(13.0, -11.5), ankleF=(-17.0, -13.0), faN=-8.0, faF=20.0,
         head_off=(1.2, -1.2), expr='attack'),
    pose(hip=(0.5, -97.0), lean=3.4, twist=0.6,
         wristN=(26.0, -145.0), wristF=(8.0, -148.0), head_off=(0.4, 0.0)),
]

KICK = [
    pose(hip=(0.0, -97.0), lean=3.2, twist=0.4,
         wristN=(26.5, -145.0), wristF=(8.5, -148.0)),
    pose(hip=(-2.0, -96.0), lean=-6.0, twist=-1.0,
         ankleN=(16.0, -64.0), faN=-30.0, ankleF=(-12.0, -11.0),
         knee_hintN=(1.0, -0.8),
         wristN=(18.0, -142.0), wristF=(2.0, -150.0),
         head_off=(-1.0, 0.2), expr='attack'),
    pose(hip=(-6.0, -95.0), lean=-16.0, twist=-2.0,
         ankleN=(56.0, -112.0), faN=-24.0, ankleF=(-14.0, -11.0), faF=6.0,
         knee_hintN=(1.0, -0.35),
         wristN=(14.0, -146.0), wristF=(24.0, -152.0),
         head_off=(-3.0, -0.6), expr='attack'),
    pose(hip=(-7.0, -94.5), lean=-18.0, twist=-2.2,
         ankleN=(58.0, -118.0), faN=-28.0, ankleF=(-15.0, -11.0), faF=8.0,
         knee_hintN=(1.0, -0.3),
         wristN=(12.0, -148.0), wristF=(26.0, -150.0),
         head_off=(-3.2, -0.8), expr='attack'),
    pose(hip=(-2.0, -96.5), lean=-4.0, twist=0.0,
         ankleN=(22.0, -52.0), faN=-20.0, ankleF=(-12.0, -11.0),
         knee_hintN=(1.0, -0.7),
         wristN=(22.0, -144.0), wristF=(10.0, -149.0), head_off=(-1.0, 0.0)),
]

JUMP = [
    pose(hip=(0.0, -88.0), lean=8.0, twist=0.0,
         ankleN=(14.0, -10.5), ankleF=(-14.0, -11.0),
         wristN=(16.0, -128.0), wristF=(2.0, -140.0), head_off=(0.0, 1.0),
         knee_hintN=(1.0, -0.3), knee_hintF=(1.0, -0.3), expr='attack'),
    pose(hip=(1.0, -100.0), lean=-2.0, twist=1.0,
         ankleN=(12.0, -10.5), ankleF=(-12.0, -11.0),
         wristN=(22.0, -158.0), wristF=(6.0, -156.0), head_off=(0.5, -0.5), expr='attack'),
    pose(hip=(0.0, -101.0), lean=6.0, twist=0.0,
         ankleN=(20.0, -58.0), faN=-40.0, ankleF=(2.0, -64.0), faF=-40.0,
         knee_hintN=(1.0, -0.8), knee_hintF=(1.0, -0.8),
         wristN=(26.0, -150.0), wristF=(8.0, -146.0), head_off=(0.0, 0.2), expr='attack'),
    pose(hip=(0.0, -99.0), lean=2.0, twist=-0.5,
         ankleN=(18.0, -32.0), faN=-25.0, ankleF=(-4.0, -36.0), faF=-25.0,
         wristN=(32.0, -138.0), wristF=(0.0, -142.0), head_off=(0.4, 0.4)),
]

HURT = [
    pose(hip=(-3.0, -97.0), lean=-12.0, twist=-1.0,
         head_tilt=-7.0, head_off=(-3.0, -1.0),
         wristN=(34.0, -142.0), wristF=(-4.0, -150.0),
         ankleN=(8.0, -10.5), ankleF=(-17.0, -11.0), expr='hurt'),
    pose(hip=(-6.0, -95.5), lean=-20.0, twist=-2.0,
         head_tilt=-13.0, head_off=(-5.0, -2.0),
         wristN=(38.0, -138.0), wristF=(-8.0, -148.0),
         ankleN=(5.0, -10.5), ankleF=(-21.0, -11.0), faF=8.0, expr='hurt'),
]

KO = [
    pose(hip=(-4.0, -96.0), lean=-16.0, twist=-2.0,
         head_tilt=-10.0, head_off=(-4.0, -1.0),
         wristN=(33.0, -140.0), wristF=(-5.0, -149.0),
         ankleN=(7.0, -10.5), ankleF=(-19.0, -11.0),
         expr='hurt', far_arm_front=False),
    pose(hip=(-8.0, -90.0), lean=-28.0, twist=-3.0,
         head_tilt=-16.0, head_off=(-6.0, -3.0),
         wristN=(28.0, -122.0), wristF=(-8.0, -132.0),
         ankleN=(5.0, -10.5), ankleF=(-22.0, -11.0),
         expr='hurt', far_arm_front=False),
    pose(hip=(-11.0, -64.0), lean=-52.0, twist=-3.0,
         head_tilt=-26.0, head_off=(-5.0, -2.0),
         wristN=(16.0, -96.0), wristF=(-18.0, -104.0),
         ankleN=(9.0, -28.0), ankleF=(-8.0, -34.0), faN=-40.0, faF=-40.0,
         knee_hintN=(1.0, -0.8), knee_hintF=(1.0, -0.8),
         expr='hurt', far_arm_front=False),
    pose(hip=(-10.0, -34.0), lean=-74.0, twist=-2.0,
         head_tilt=-60.0, head_off=(0.0, 4.0),
         wristN=(-6.0, -52.0), wristF=(-36.0, -34.0),
         ankleN=(24.0, -40.0), ankleF=(15.0, -46.0), faN=-60.0, faF=-55.0,
         knee_hintN=(1.0, -1.0), knee_hintF=(1.0, -1.0),
         expr='hurt', far_arm_front=False),
    pose(hip=(-10.0, -14.0), lean=-88.0, twist=0.0,
         head_tilt=-80.0, head_off=(-1.0, 4.0),
         wristN=(-30.0, -30.0), wristF=(-58.0, -8.0),
         ankleN=(33.0, -14.0), ankleF=(24.0, -10.0), faN=-85.0, faF=-80.0,
         knee_hintN=(1.0, -1.0), knee_hintF=(1.0, -1.0),
         expr='ko', far_arm_front=False),
]

SPECIAL = [
    pose(hip=(0.0, -93.0), lean=8.0, twist=-1.0, glow=0.15,
         wristN=(14.0, -122.0), wristF=(0.0, -138.0),
         ankleN=(14.0, -10.5), ankleF=(-14.0, -11.0),
         head_off=(-0.5, 1.0), expr='attack'),
    pose(hip=(-1.5, -89.0), lean=11.0, twist=-2.0, glow=0.30,
         wristN=(10.0, -116.0), wristF=(-3.0, -134.0),
         ankleN=(15.5, -10.5), ankleF=(-15.0, -11.0),
         knee_hintN=(1.0, -0.4), knee_hintF=(1.0, -0.4),
         head_off=(-1.0, 1.6), expr='attack'),
    pose(hip=(2.0, -99.0), lean=-2.0, twist=1.0, glow=0.55,
         wristN=(25.0, -158.0), wristF=(2.0, -150.0),
         ankleN=(13.0, -11.0), ankleF=(-15.5, -12.0), faF=10.0,
         head_off=(1.0, -0.5), expr='attack'),
    pose(hip=(3.5, -103.0), lean=-6.0, twist=2.0, glow=0.80,
         wristN=(30.0, -170.0), wristF=(-2.0, -156.0),
         ankleN=(13.0, -12.0), ankleF=(-17.0, -14.0), faN=-8.0, faF=18.0,
         head_off=(1.5, -1.0), expr='attack'),
    pose(hip=(2.0, -108.0), lean=-3.0, twist=1.5, glow=1.00,
         wristN=(22.0, -178.0), wristF=(-6.0, -160.0),
         ankleN=(18.0, -34.0), ankleF=(-2.0, -40.0), faN=-40.0, faF=-40.0,
         knee_hintN=(1.0, -0.9), knee_hintF=(1.0, -0.9),
         head_off=(1.0, -1.4), expr='attack'),
    pose(hip=(0.0, -105.0), lean=1.0, twist=1.0, glow=0.90,
         wristN=(34.0, -156.0), wristF=(0.0, -150.0),
         ankleN=(16.0, -28.0), ankleF=(-6.0, -34.0), faN=-30.0, faF=-30.0,
         knee_hintN=(1.0, -0.9), knee_hintF=(1.0, -0.9),
         head_off=(0.5, -0.8), expr='attack'),
    pose(hip=(1.0, -97.0), lean=7.0, twist=0.0, glow=0.45,
         wristN=(26.0, -140.0), wristF=(8.0, -147.0),
         ankleN=(14.0, -10.5), ankleF=(-14.0, -11.0),
         head_off=(0.2, 0.4), expr='attack'),
    pose(hip=(0.2, -97.0), lean=3.4, twist=0.4, glow=0.15,
         wristN=(26.0, -145.0), wristF=(8.5, -148.0), head_off=(0.4, 0.0)),
]

VICTORY = [
    pose(hip=(0.0, -97.0), lean=2.0, twist=0.5,
         wristN=(26.0, -145.0), wristF=(8.0, -148.0),
         head_off=(0.4, 0.0), expr='victory'),
    pose(hip=(0.0, -98.0), lean=1.0, twist=0.8,
         wristN=(22.0, -166.0), wristF=(5.0, -146.0),
         head_off=(0.2, -0.8), expr='victory'),
    pose(hip=(0.0, -99.0), lean=-2.0, twist=1.0,
         wristN=(24.0, -178.0), wristF=(3.0, -142.0),
         head_off=(0.0, -1.4), expr='victory'),
    pose(hip=(0.0, -98.4), lean=-1.0, twist=0.9,
         wristN=(23.5, -176.0), wristF=(3.5, -143.0),
         head_off=(0.1, -1.1), expr='victory'),
    pose(hip=(0.0, -98.0), lean=0.0, twist=0.8,
         wristN=(23.0, -174.0), wristF=(4.0, -144.0),
         head_off=(0.2, -1.0), expr='victory'),
]

ANIMS = {
    'idle': dict(fps=6, loop=True, poses=IDLE),
    'walk': dict(fps=10, loop=True, poses=WALK),
    'punch1': dict(fps=14, loop=False, poses=PUNCH1),
    'punch2': dict(fps=14, loop=False, poses=PUNCH2),
    'punch3': dict(fps=12, loop=False, poses=PUNCH3),
    'kick': dict(fps=12, loop=False, poses=KICK),
    'jump': dict(fps=10, loop=False, poses=JUMP),
    'hurt': dict(fps=10, loop=False, poses=HURT),
    'ko': dict(fps=8, loop=False, poses=KO),
    'special': dict(fps=12, loop=False, poses=SPECIAL),
    'victory': dict(fps=8, loop=False, poses=VICTORY),
}
ANIM_ORDER = ['idle', 'walk', 'punch1', 'punch2', 'punch3', 'kick', 'jump',
              'hurt', 'ko', 'special', 'victory']


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------
def save_sheet(name, imgs):
    os.makedirs(HERO_DIR, exist_ok=True)
    sheet = Image.new('RGBA', (FW * len(imgs), FH), (0, 0, 0, 0))
    for i, im in enumerate(imgs):
        sheet.paste(im, (i * FW, 0))
    path = os.path.join(HERO_DIR, name + '.png')
    sheet.save(path)
    return path


def checker_bg(w, h, cell=8, base='#0d0820', alt='#120c1c'):
    img = Image.new('RGBA', (w, h), hx(base) + (255,))
    d = ImageDraw.Draw(img)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if ((x // cell) + (y // cell)) % 2 == 0:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=hx(alt) + (255,))
    return img


def build_contact_sheet(baked):
    font = ImageFont.load_default()
    cell_w = FW
    cell_h = FH + 18
    cols = 9
    total = sum(len(baked[n]) for n in ANIM_ORDER)
    rows = (total + cols - 1) // cols
    W = cols * cell_w
    H = rows * cell_h
    sheet = checker_bg(W, H)
    d = ImageDraw.Draw(sheet)
    idx = 0
    for name in ANIM_ORDER:
        imgs = baked[name]
        for i, im in enumerate(imgs):
            c = idx % cols
            r = idx // cols
            x = c * cell_w
            y = r * cell_h
            sheet.alpha_composite(im, (x, y))
            d.rectangle([x, y, x + cell_w - 1, y + FH], outline=(40, 30, 60, 255))
            d.text((x + 4, y + FH + 3), '%s %d' % (name, i),
                   fill=(190, 170, 230, 255), font=font)
            idx += 1
    out = os.path.join(HERO_DIR, 'preview.png')
    sheet.save(out)
    return out


def build_static_preview(baked, portrait):
    W, H = 960, 540
    img = checker_bg(W, H, 20, '#0a0618', '#0d0820')
    d = ImageDraw.Draw(img)
    # 霓虹背景装饰
    for i in range(24):
        x = 40 + i * 38
        d.line([x, 0, x - 200, H], fill=(30, 16, 52, 255), width=1)
    d.rectangle([0, 150, W, 156], fill=(18, 10, 34, 255))
    d.rectangle([0, 150, W, 152], fill=(0x1f, 0x8c, 0xa8, 255))
    idle0 = baked['idle'][0]
    big = idle0.resize((FW * 2, FH * 2), Image.NEAREST)
    img.alpha_composite(big, (60, 30))
    p2 = portrait.resize((192 * 2, 192 * 2), Image.NEAREST)
    img.alpha_composite(p2, (600, 60))
    d = ImageDraw.Draw(img)
    d.text((66, 20), 'KAI  /  HERO  SPRITE  PREVIEW  x2', fill=(0x8f, 0xfb, 0xff, 255))
    d.text((606, 30), 'PORTRAIT 192x192  x2', fill=(0xff, 0x74, 0xb8, 255))
    d.text((66, 130), 'anchor (120,224)  frame 240x240  bodyHeight 186', fill=(180, 160, 220, 255))
    path = os.path.join(SHOTS_DIR, 'hero_static.png')
    img.convert('RGB').save(path)
    return path


def build_wip(baked, portrait):
    os.makedirs(SHOTS_DIR, exist_ok=True)
    imgs = baked['idle']
    scale = 2
    pad = 12
    n = len(imgs)
    w = n * (FW * scale + pad) + pad
    h = FH * scale + pad * 2 + 20
    out = checker_bg(w, h)
    d = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    for i, im in enumerate(imgs):
        big = im.resize((FW * scale, FH * scale), Image.NEAREST)
        x = pad + i * (FW * scale + pad)
        out.alpha_composite(big, (x, pad))
        d.text((x + 4, pad + FH * scale + 3), 'idle f%d' % i,
               fill=(200, 180, 230, 255), font=font)
        d.line([x, pad + AY * scale, x + FW * scale, pad + AY * scale],
               fill=(255, 60, 140, 90))
    out.save(os.path.join(SHOTS_DIR, 'hero_wip.png'))
    # 头部特写（直接裁 idle 第 0 帧）
    sk = skeleton(IDLE[0])
    hx_ = int(round(sk['headc'][0])) + AX
    hy_ = int(round(sk['headc'][1])) + AY
    crop = imgs[0].crop((hx_ - 22, hy_ - 24, hx_ + 26, hy_ + 28))
    z = 10
    zoom = crop.resize((crop.width * z, crop.height * z), Image.NEAREST)
    out2 = checker_bg(zoom.width + 16, zoom.height + 16)
    out2.alpha_composite(zoom, (8, 8))
    out2.save(os.path.join(SHOTS_DIR, 'hero_face_zoom.png'))
    if portrait is not None:
        p2 = portrait.resize((portrait.width * 2, portrait.height * 2), Image.NEAREST)
        out3 = checker_bg(p2.width + 16, p2.height + 16)
        out3.alpha_composite(p2, (8, 8))
        out3.save(os.path.join(SHOTS_DIR, 'hero_portrait_wip.png'))


def write_manifest():
    lines = [
        '/* NEON FIST SOUL — 主角「凯 KAI」像素资源清单。',
        ' * 由 tools/gen_hero.py 程序化生成并烘焙，请勿手改。',
        ' * 帧尺寸 240x240，锚点 (120,224)=双脚落点，默认朝右绘制（引擎水平翻转）。',
        ' */',
        '/* eslint-disable */',
        "NF.registerChar('hero', {",
        '  frameW: 240, frameH: 240, anchorX: 120, anchorY: 224, bodyHeight: 186,',
        "  portrait: 'chars/hero/portrait.png',",
        '  animations: {',
    ]
    for name in ANIM_ORDER:
        ad = ANIMS[name]
        n = len(ad['poses'])
        lines.append("    %s: { file: 'chars/hero/%s.png', frames: %d, fps: %s, loop: %s },"
                     % (name, name, n, _fmt_num(ad['fps']), 'true' if ad['loop'] else 'false'))
    lines.append('  }')
    lines.append('});')
    lines.append('')
    path = os.path.join(HERO_DIR, 'manifest.js')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))
    return path


def _fmt_num(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def check_bounds(img, name, idx):
    a = np.array(img)[:, :, 3]
    bad = []
    if a[0, :].any():
        bad.append('top')
    if a[-1, :].any():
        bad.append('bottom')
    if a[:, 0].any():
        bad.append('left')
    if a[:, -1].any():
        bad.append('right')
    if bad:
        print('  WARN %s[%d] touches border: %s' % (name, idx, ','.join(bad)))
    return bad


def main():
    args = sys.argv[1:]
    only = None
    if '--only' in args:
        only = args[args.index('--only') + 1]
    debug = '--debug' in args
    wip = '--wip' in args or debug
    os.makedirs(HERO_DIR, exist_ok=True)
    os.makedirs(SHOTS_DIR, exist_ok=True)

    if debug:
        p0 = IDLE[0]
        flat = render_frame(p0, rim=False, outline=False, face=False)
        big = flat.resize((FW * 4, FH * 4), Image.NEAREST)
        bg = checker_bg(big.width, big.height)
        bg.alpha_composite(big, (0, 0))
        bg.save(os.path.join(SHOTS_DIR, 'hero_dbg_flat.png'))
        for tag, with_face in (('base', False), ('face', True)):
            him = render_head_only(p0, face=with_face, rim=False)
            crop = him.crop((40 - 22, 40 - 24, 40 + 26, 40 + 28))
            z = 8
            zoom = crop.resize((crop.width * z, crop.height * z), Image.NEAREST)
            hb = checker_bg(zoom.width + 12, zoom.height + 12)
            hb.alpha_composite(zoom, (6, 6))
            hb.save(os.path.join(SHOTS_DIR, 'hero_dbg_head_%s.png' % tag))
        full = render_frame(p0)
        big = full.resize((FW * 3, FH * 3), Image.NEAREST)
        bg = checker_bg(big.width, big.height)
        bg.alpha_composite(big, (0, 0))
        bg.save(os.path.join(SHOTS_DIR, 'hero_dbg_full.png'))
        print('wrote debug shots')
        return

    baked = {}
    names = [only] if only else ANIM_ORDER
    issues = 0
    for name in names:
        ad = ANIMS[name]
        imgs = [render_frame(p) for p in ad['poses']]
        path = save_sheet(name, imgs)
        baked[name] = imgs
        for i, im in enumerate(imgs):
            issues += len(check_bounds(im, name, i))
        # 尺寸校验
        sheet = Image.open(path)
        expect = (FW * len(imgs), FH)
        flag = 'OK' if sheet.size == expect else 'BAD'
        print('%s %-8s frames=%2d sheet=%dx%d %s' % (flag, name, len(imgs), sheet.size[0], sheet.size[1], path))

    portrait = render_portrait()
    ppath = os.path.join(HERO_DIR, 'portrait.png')
    portrait.save(ppath)
    print('OK portrait 192x192 %s' % ppath)

    if not only:
        contact = build_contact_sheet(baked)
        print('OK contact sheet %s' % contact)
        mpath = write_manifest()
        print('OK manifest %s' % mpath)
        static = build_static_preview(baked, portrait)
        print('OK static preview %s' % static)
        import shutil
        shutil.copyfile(contact, os.path.join(SHOTS_DIR, 'hero_contact.png'))
    if wip and baked.get('idle'):
        build_wip(baked, portrait)
        print('OK shots/hero_wip.png shots/hero_face_zoom.png shots/hero_portrait_wip.png')
    print('DONE (border issues: %d)' % issues)


if __name__ == '__main__':
    main()
