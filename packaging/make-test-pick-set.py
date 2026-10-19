#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""造一份「挑图要判的那四种照片」小集子，给真窗口那一臂（LNX-PICK-001）当输入。

为什么要有这份脚本而不是让 release-check 现写 PIL 代码：那一臂的证据必须能被别人重做。
目录里每一张都写明它要触发哪一条判据，全部由**已提交的夹具**确定性变换而来（同一输入
两次生成的 sha256 相同），所以读数变了就等于判据变了，不会是被生成器悄悄改了。

跑法：
    ~/.local/share/LumaRetouch/engine/venv/bin/python \\
        packaging/make-test-pick-set.py /tmp/pick-set
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageFilter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "engine", "src"))

from lumaretouch_engine import face as face_mod   # noqa: E402
from lumaretouch_engine import picks as PK        # noqa: E402

FIX = os.path.join(REPO, "engine/tests/fixtures/portrait-1024x1280.jpg")

# 这一份集合要触发的四件事，与冻结件 given 的四个词一一对应：
#   重复/近似 → a_base 与 b_near（同构图 +2 偏置，dHash 汉明距离实测 0 位）
#   模糊     → c_soft（高斯糊 6.0，绝对能量与相对对比度双双落在线下）
#   闭眼     → e_closed（按眼下肤色带涂平眼裂；替身成立的直接证据是睁开比塌下去）
#   正常     → a_base（应当没有建议要复核）
KINDS = ("a_base", "b_near", "c_soft", "d_blown", "e_closed")


def build(dst: str) -> int:
    if not os.path.isfile(FIX):
        print(f"缺夹具：{FIX}（先跑 packaging/make-test-portrait.py）")
        return 2
    os.makedirs(dst, exist_ok=True)
    base = np.asarray(Image.open(FIX).convert("RGB"), dtype=np.uint8)
    out = {
        "a_base": base,
        "b_near": np.clip(base.astype(np.int16) + 2, 0, 255).astype(np.uint8),
        "c_soft": np.asarray(Image.fromarray(base).filter(
            ImageFilter.GaussianBlur(6.0)), dtype=np.uint8),
        "d_blown": np.clip(base.astype(np.float32) * 2.6 + 12, 0, 255).astype(np.uint8),
    }
    # 闭眼替身：涂平之后必须**重新检测**再看睁开比塌没塌。拿原图的关键点去量涂平后的图
    # 是恒等的（标定台上先这么错过一次），那等于这一张什么都没造
    try:
        fn = face_mod.build("mediapipe")
        lm = (fn(base).all_landmarks or [None])[0]
        if lm is None:
            raise RuntimeError("夹具里没探到脸")
        h, w = base.shape[:2]
        pts = np.asarray(lm, dtype=np.float32)
        eyes = base.copy()
        for e in (PK.EYE_LEFT, PK.EYE_RIGHT):
            sub = pts[[e["outer"], e["inner"], e["upper"], e["lower"]], :2] * [w, h]
            x0, y0 = np.floor(sub.min(axis=0)).astype(int)
            x1, y1 = np.ceil(sub.max(axis=0)).astype(int)
            band = eyes[min(y1 + 6, h - 1):min(y1 + 12, h), max(x0, 0):max(x1, 1)]
            tone = band.reshape(-1, 3).mean(axis=0).astype(np.uint8)
            eyes[max(y0, 0):min(y1, h), max(x0, 0):min(x1, w)] = tone
        flat = (fn(eyes).all_landmarks or [None])[0]
        open_r = PK.eye_openness(lm, image_size=(w, h))
        flat_r = PK.eye_openness(flat, image_size=(w, h)) if flat is not None else None
        if flat_r is None or open_r is None or flat_r >= open_r:
            print(f"闭眼替身不成立（睁开 {open_r} → 涂平 {flat_r}）：这一张不进集合")
            return 3
        out["e_closed"] = eyes
        print(f"闭眼替身读数：睁开 {open_r:.4f} → 涂平 {flat_r:.4f}")
    except face_mod.MissingBackend as e:
        print(f"没装 mediapipe，闭眼那一张造不出来（{e}）：这一张不进集合")
        return 3
    for name, arr in sorted(out.items()):
        p = os.path.join(dst, f"{name}.png")
        Image.fromarray(arr).save(p, optimize=True)
        print(f"  {name}.png  {arr.shape[1]}×{arr.shape[0]}")
    left = sorted(set(KINDS) - set(out))
    if left:
        print(f"  没生成的：{left}（原因见上面那行，不拿别的图凑数）")
    return 0


if __name__ == "__main__":
    sys.exit(build(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pick-set"))
