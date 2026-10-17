# -*- coding: utf-8 -*-
"""霓虹拳魂 — 资源完整性校验：manifest 中引用的图片是否存在、尺寸/帧数是否匹配。"""
import os
import re
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return f.read()


def check_chars(manifest_path):
    src = read(manifest_path)
    fw = fh = None
    problems = []
    checked = 0
    for block in re.finditer(r"registerChar\(\s*'([^']+)'\s*,\s*\{(.*?)\n\s*\}\);", src, re.S):
        name, body = block.group(1), block.group(2)
        fw = int(re.search(r'frameW:\s*(\d+)', body).group(1))
        fh = int(re.search(r'frameH:\s*(\d+)', body).group(1))
        for am in re.finditer(r"(\w+):\s*\{\s*file:\s*'([^']+)',\s*frames:\s*(\d+),", body):
            anim, rel, frames = am.group(1), am.group(2), int(am.group(3))
            path = os.path.join(ROOT, 'assets', rel)
            if not os.path.exists(path):
                problems.append(f'{name}.{anim}: 文件缺失 {rel}')
                continue
            w, h = Image.open(path).size
            if (w, h) != (fw * frames, fh):
                problems.append(f'{name}.{anim}: 尺寸 {w}x{h} != 期望 {fw * frames}x{fh}')
            else:
                checked += 1
        pm = re.search(r"portrait:\s*'([^']+)'", body)
        if pm:
            path = os.path.join(ROOT, 'assets', pm.group(1))
            if not os.path.exists(path):
                problems.append(f'{name}.portrait: 文件缺失 {pm.group(1)}')
            else:
                checked += 1
    return checked, problems


def check_world(manifest_path):
    src = read(manifest_path)
    problems = []
    checked = 0
    expected = {
        'world/bg_far.png': (1600, 540),
        'world/bg_mid.png': (3200, 540),
        'world/bg_near.png': (3200, 540),
        'world/bg_fg.png': (3200, 540),
        'ui/logo.png': (760, 240)
    }
    for rel in expected:
        if rel not in src:
            problems.append(f'manifest 未引用 {rel}')
            continue
        path = os.path.join(ROOT, 'assets', rel)
        if not os.path.exists(path):
            problems.append(f'文件缺失 {rel}')
            continue
        size = Image.open(path).size
        if size != expected[rel]:
            problems.append(f'{rel}: 尺寸 {size} != 期望 {expected[rel]}')
        else:
            checked += 1
    return checked, problems


def main():
    checked = 0
    problems = []
    for mf in ('assets/chars/hero/manifest.js', 'assets/chars/enemies/manifest.js'):
        c, p = check_chars(mf)
        checked += c
        problems += p
    c, p = check_world('assets/world/manifest.js')
    checked += c
    problems += p
    print(f'资源校验通过: {checked} 项')
    if problems:
        print('问题:')
        for p in problems:
            print(' -', p)
        return 1
    print('全部 manifest 引用的图片存在且尺寸/帧数一致。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
