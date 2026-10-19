#!/usr/bin/env python3
"""ADR-0015 的实测表：眼牙三格在真夹具上的一手读数。

只走公开入口（geometry → refine → enhance_np），把判据要用到的数拿出来：
每子功能的几何格数 / 门后格数、门后区域的抬升幅度（LSB）、掩膜外是否逐字节不变、
v 是否只升不降、255 是否不增、每帧逐点乘加的耗时。数字要能复算，所以脚本进仓。
"""
import json
import time

import numpy as np
from PIL import Image

from lumaretouch_engine import face as face_mod
from lumaretouch_engine.ops.enhance import SUBS, build_field, enhance_np

FIXTURES = {
    "露齿": "engine/tests/fixtures/portrait-smile-1024x1280.jpg",
    "露齿+眼镜": "engine/tests/fixtures/portrait-glasses-smile-1024x1280.jpg",
    "深肤色露齿": "engine/tests/fixtures/portrait-deep-skin-smile-1024x1280.jpg",
}


def probe(tag, path):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    h, w = rgb.shape[:2]
    pc = face_mod.build("mediapipe")(rgb)
    lm = np.asarray(pc.landmarks, dtype=np.float64)
    src = rgb.astype(np.float64) / 255.0

    window, weight, info, facts = build_field(lm, h, w, src)
    y0, x0, fh, fw = window
    win = src[y0:y0 + fh, x0:x0 + fw]

    rows = []
    for sub in SUBS:
        a = {k: (1.0 if k == sub else 0.0) for k in SUBS}
        t0 = time.perf_counter()
        out = enhance_np(win, weight, a)
        ms = (time.perf_counter() - t0) * 1000.0
        d = np.abs(out - win).max(axis=-1) * 255.0
        lit = weight[SUBS.index(sub)] > 0.5
        moved = d > 0.5
        rows.append({
            "sub": sub,
            "geom_px": facts[sub]["geom_px"],
            "gated_px": facts[sub]["gated_px"],
            "dropped_px": facts[sub]["dropped_px"],
            "reason": facts[sub]["reason"],
            "field_max": facts[sub]["field_max"],
            "lit_px": int(lit.sum()),
            "moved_px": int(moved.sum()),
            "mean_lsb": round(float(d[lit].mean()), 2) if lit.any() else 0.0,
            "max_lsb": round(float(d[lit].max()), 2) if lit.any() else 0.0,
            "outside_lit_moved": int((moved & ~lit).sum()),
            "np_ms": round(ms, 2),
        })

    # 全档一起开：窗口外必须逐字节不变
    a_all = {k: 1.0 for k in SUBS}
    out_all = enhance_np(win, weight, a_all)
    full = src.copy()
    full[y0:y0 + fh, x0:x0 + fw] = out_all
    outside = (full[:y0] != src[:y0]).sum() + (full[y0 + fh:] != src[y0 + fh:]).sum()
    outside += (full[y0:y0 + fh, :x0] != src[y0:y0 + fh, :x0]).sum()
    outside += (full[y0:y0 + fh, x0 + fw:] != src[y0:y0 + fh, x0 + fw:]).sum()

    # 中性档（全 0）必须逐字节等于输入
    neutral = enhance_np(win, weight, {k: 0.0 for k in SUBS})
    neutral_same = bool(np.array_equal(neutral, win))

    # 过曝护栏：满档后 v 不许比原片低，也不许在已经到 255 的格上再挤出 255
    from lumaretouch_engine.ops.grade import rgb_to_hsv_np

    v_in = rgb_to_hsv_np(np.clip(win, 0.0, 1.0))[..., 2]
    v_out = rgb_to_hsv_np(np.clip(out_all, 0.0, 1.0))[..., 2]
    darkened = int((v_out < v_in - 1e-9).sum())
    q_in = np.rint(win * 255.0).astype(np.uint8)
    q_out = np.rint(out_all * 255.0).astype(np.uint8)
    new_clipped = int(((q_out >= 255) & (q_in < 255)).any(axis=-1).sum())

    print(json.dumps({
        "fixture": tag, "path": path, "size": [w, h],
        "num_faces": pc.num_faces, "window": [y0, x0, fh, fw],
        "backend": getattr(pc, "backend", None),
        "mouth": info.get("mouth"), "eyes": info.get("eyes"),
        "subs": rows,
        "outside_window_changed_px": int(outside),
        "neutral_is_byte_identical": neutral_same,
        "darkened_px": darkened,
        "new_clipped_px": new_clipped,
    }, ensure_ascii=False, indent=1))


for tag, p in FIXTURES.items():
    probe(tag, p)
