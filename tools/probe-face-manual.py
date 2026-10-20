#!/usr/bin/env python3
"""ADR-0017 的实测表探针：人工纠正那一套数字从哪来（一手读数，可复算）。

跑法（运行时 venv，要 torch 与 mediapipe）：
    PYTHONPATH=engine/src ~/.local/share/LumaRetouch/engine/venv/bin/python \\
        tools/probe-face-manual.py

这里量四件事，全部是**决策的输入**而不是结果的复述：
① `MANUAL_IOU_MIN=0.5`：同一个人被 mediapipe 与 template 两个后端框出来的盒，IoU 到底
   有多大；以及两个后端对同一张图里不同人的盒 IoU 又能重叠到多少（下限要卡在两者之间）；
② `REGION_MIN_SIDE_PX=48`：把窗一路缩小，看后端从哪一格开始报"没有脸"；
③ `REGION_PAD_RATIO=0.30`：只框五官（内缩一圈）时，补 0% / 15% / 30% / 45% 上下文各拿回
   多大的 IoU 与多少点位——补多少才够是这一格定的；
④ `REGION_IOU_MIN=0.20`：邻座与用户框的 IoU 有多大（那条"不拿邻座冒充"的下限要卡在
   它下面还是上面）。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIX = os.path.join(REPO, "engine", "tests", "fixtures")

from lumaretouch_engine import face as face_mod          # noqa: E402
from lumaretouch_engine.face import box_iou, detect_region  # noqa: E402

OUT = {}


def _load_rgb(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def _proxy(rgb: np.ndarray, max_px: int = 207360) -> np.ndarray:
    h, w = rgb.shape[:2]
    s = min(1.0, (max_px / float(h * w)) ** 0.5)
    if s < 1.0:
        nh, nw = max(1, int(h * s)), max(1, int(w * s))
        rgb = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.LANCZOS), dtype=np.uint8)
    return np.ascontiguousarray(rgb)


def main() -> int:
    mp = face_mod.build("mediapipe")
    tpl = face_mod.build("template")
    dual = _proxy(_load_rgb(os.path.join(FIX, "portrait-dual-1570x950.jpg")))
    single = _proxy(_load_rgb(os.path.join(FIX, "portrait-1024x1280.jpg")))

    # ① 两个后端对同一个人的盒差多少（这决定 MANUAL_IOU_MIN 的下限）
    pc_mp = mp(dual)
    pc_tpl = tpl(dual)
    rows = []
    for f in pc_mp.faces():
        best = max(((box_iou(f["box"], g["box"]), g["index"]) for g in pc_tpl.faces()),
                   key=lambda x: x[0])
        rows.append({"who": f["index"], "best_iou_vs_template": round(best[0], 4),
                     "against": best[1]})
    cross = sorted({round(box_iou(a["box"], b["box"]), 4)
                    for a in pc_mp.faces() for b in pc_tpl.faces()})
    OUT["iou_model_switch"] = {"per_person": rows, "all_pairs_sorted": cross,
                               "dual_proxy_shape": list(dual.shape[:2])}

    # ② 窗缩小到多少像素时后端开始报"没有脸"
    pc1 = mp(single)
    box = pc1.faces()[0]["box"]
    h, w = single.shape[:2]
    shrink_rows = []
    for shrink in (0.0, 0.15, 0.3, 0.45, 0.6):
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        hx, hy = (box[2] - box[0]) / 2 * (1 - shrink), (box[3] - box[1]) / 2 * (1 - shrink)
        rect = (cx - hx, cy - hy, cx + hx, cy + hy)
        px = int(min(rect[2] - rect[0], rect[3] - rect[1]) * min(w, h))
        try:
            lm, info = detect_region(mp, single, rect)
            shrink_rows.append({"shrink": shrink, "rect_px": px, "ok": True,
                                "min_side_after_pad": int(min(info["crop_px"])),
                                "iou_rect_vs_box": info["iou"],
                                "faces_in_window": info["faces_in_window"],
                                "t_detect_ms": info["t_detect_ms"]})
        except Exception as e:                        # noqa: BLE001
            shrink_rows.append({"shrink": shrink, "rect_px": px, "ok": False,
                                "reason": f"{type(e).__name__}: {e}"[:150]})
    OUT["region_shrink_and_min_side"] = {"single_proxy_shape": [int(h), int(w)],
                                         "detected_box": [round(float(v), 4) for v in box],
                                         "rows": shrink_rows,
                                         "REGION_MIN_SIDE_PX": face_mod.REGION_MIN_SIDE_PX,
                                         "REGION_PAD_RATIO": face_mod.REGION_PAD_RATIO}

    # ③ 只框五官时补上下文的比例：0 / 0.15 / 0.30 / 0.45 各拿回什么
    #    这里直接改模块常量再恢复——探针要量的是实现真正会走的那条路，不是另写一份数学
    pad_rows = []
    features_rect = (box[0] + (box[2] - box[0]) * 0.18, box[1] + (box[3] - box[1]) * 0.10,
           box[2] - (box[2] - box[0]) * 0.18, box[3] - (box[3] - box[1]) * 0.22)
    for ratio in (0.0, 0.15, 0.30, 0.45):
        old = face_mod.REGION_PAD_RATIO
        face_mod.REGION_PAD_RATIO = ratio
        try:
            lm, info = detect_region(mp, single, features_rect)
            pad_rows.append({"pad": ratio, "ok": True, "iou": info["iou"],
                             "window": info["window"], "crop_px": info["crop_px"],
                             "box": info["box"]})
        except Exception as e:                        # noqa: BLE001
            pad_rows.append({"pad": ratio, "ok": False, "reason": f"{type(e).__name__}: {e}"[:150]})
        finally:
            face_mod.REGION_PAD_RATIO = old
    OUT["region_pad_sweep"] = {"rect": [round(float(v), 4) for v in features_rect],
                                "rows": pad_rows}

    # ④ 邻座与用户框的 IoU：那条"不拿邻座冒充"的下限要卡在什么数字下面
    neigh = []
    for f in pc_mp.faces():
        for g in pc_mp.faces():
            if f["index"] != g["index"]:
                neigh.append({"a": f["index"], "b": g["index"],
                              "iou": round(box_iou(f["box"], g["box"]), 5)})
    OUT["neighbour_iou"] = {"pairs": neigh, "REGION_IOU_MIN": face_mod.REGION_IOU_MIN,
                            "MANUAL_IOU_MIN": __import__("lumaretouch_engine.server", fromlist=["Engine"]).Engine.MANUAL_IOU_MIN}

    # ⑤ 三格图：检测器按定义漏掉的那一位，区域检测能不能把他拿回来
    sys.path.insert(0, os.path.join(REPO, "packaging"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "make_test_dual", os.path.join(REPO, "packaging", "make-test-dual-portrait.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    img = gen.build(os.path.join(FIX, "portrait-1024x1280.png"), cells=3)
    tri = _proxy(np.asarray(img.convert("RGB"), dtype=np.uint8))
    pctp = mp(tri)
    CW, CH, GAP, TS = gen.CELL_W, gen.CELL_H, gen.GAP, gen.THIRD_SCALE
    total_w = CW * 3 + GAP * 2
    start_x, start_y = 2 * (CW + GAP), int(CH * (1 - TS))
    ref = min(pctp.faces(), key=lambda f: f["box"][0] + f["box"][2])["box"]
    u0, u1 = ref[0] * total_w / CW, ref[2] * total_w / CW
    rect3 = ((start_x + u0 * CW * TS) / total_w, start_y / CH + ref[1] * TS,
             (start_x + u1 * CW * TS) / total_w, start_y / CH + ref[3] * TS)
    th, tw = tri.shape[:2]
    row = {"roster": len(pctp.faces()), "num_faces": int(pctp.num_faces),
           "rect3": [round(v, 5) for v in rect3],
           "max_iou_vs_roster": round(max(box_iou(rect3, f["box"]) for f in pctp.faces()), 5)}
    try:
        lm, info = detect_region(mp, tri, rect3)
        row.update({"ok": True, "iou": info["iou"], "faces_in_window": info["faces_in_window"],
                    "t_detect_ms": info["t_detect_ms"], "box": info["box"],
                    "box_vs_rect3": round(box_iou(info["box"], rect3), 5)})
    except Exception as e:                            # noqa: BLE001
        row.update({"ok": False, "reason": f"{type(e).__name__}: {e}"[:200]})
    OUT["triple_missed_person"] = {"proxy_shape": [int(th), int(tw)], **row}

    # ⑥ 拒绝路径的一手读数：背景框拿到的是什么话
    try:
        detect_region(mp, tri, [0.30, 0.01, 0.36, 0.09])
        OUT["background_rect"] = {"ok": True, "note": "背景框居然拿到了脸（判据要改）"}
    except Exception as e:                            # noqa: BLE001
        OUT["background_rect"] = {"ok": False, "reason": f"{type(e).__name__}: {e}"[:220]}

    print(json.dumps(OUT, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
