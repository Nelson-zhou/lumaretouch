#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""挑图度量的标定台：把 `picks.py` 那几个阈值从"我估的"变成"这张图上量的"。

为什么要有这个脚本（而不是直接在 picks.py 里写数）：挑图的阈值是**判据**，判据要能被
任何人复算。写死三个小数而没人能说出它们是从哪张图、什么操作量出来的，那就与"假滤镜"
只差一句注释。这里做的事：

· 在真夹具上量一遍全部读数（清晰度、曝光裁剪、dHash、眼睑睁开比）；
· 造**已知方向**的对照变体（高斯模糊 / 整体压暗 / 提亮 / 轻调色近似 / 涂平眼区），
  只要求读数按方向排开——阈值取在两组实测值之间的空档里，而不是取一个"看起来合理"的数；
· 把每一档敏感度（弱/标准/强）与该空档一起打出来，picks.py 的注释引用这份输出。

跑法（运行时 venv，眼睑那一档要真 FaceMesh）：
    PYTHONPATH=engine/src ~/.local/share/LumaRetouch/engine/venv/bin/python \
        packaging/pick-calibrate.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine", "src"))

from lumaretouch_engine import face as face_mod          # noqa: E402
from lumaretouch_engine import picks as PK               # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(REPO, "engine/tests/fixtures/portrait-1024x1280.jpg")
DUAL = os.path.join(REPO, "engine/tests/fixtures/portrait-dual-1570x950.jpg")


def load(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def measures(rgb: np.ndarray, label: str, landmarks=None) -> dict:
    under, over = PK.exposure_shares(rgb)
    cl = PK.clarity(rgb)
    m = {"label": label, "sharp": cl["lapvar"], "ratio": cl["ratio"],
         "contrast": cl["contrast"], "under": under, "over": over,
         "dhash": PK.dhash64(rgb)}
    # 睁开比按**像素**量（归一化坐标横竖分母不同，直接 hypot 会把量纲搞错——
    # 这条理由写在 picks.eye_openness 的文档里，标定台这里只是把它用对）
    m["eye"] = (PK.eye_openness(landmarks, image_size=(int(rgb.shape[1]), int(rgb.shape[0])))
                if landmarks is not None else None)
    return m


def show(rows: list[dict], title: str) -> None:
    print(f"\n== {title}")
    for r in rows:
        eye = "—" if r["eye"] is None else f"{r['eye']:.4f}"
        print(f"  {r['label']:<22} sharp={r['sharp']:.6f}  ratio={r['ratio']:.4f} "
              f"contrast={r['contrast']:.5f}  under={r['under']:.5f} "
              f"over={r['over']:.5f}  eye={eye}  dhash={r['dhash']:016x}")


def eye_landmarks(rgb: np.ndarray) -> list:
    fn = face_mod.build("mediapipe")
    pc = fn(rgb)
    return list(pc.all_landmarks or [pc.landmarks])


def paint_eyes(rgb: np.ndarray, lm) -> np.ndarray:
    """把两只眼的眼裂区域按**周围肤色**涂平：这是"闭眼"的最小可复算替身。

    它不是真闭眼（真闭眼有睫毛与眼睑 curvature），但它把上下睑点拉到同一条线上，
    于是"睁开比"这个**几何量**必然塌下去——我们要标的就是这个量能不能分辨，而不是
    训练一个闭眼分类器（那才是 DoD 禁止的伪装）。
    """
    out = rgb.copy()
    h, w = out.shape[:2]
    pts = np.asarray(lm, dtype=np.float32)
    for eye in (PK.EYE_LEFT, PK.EYE_RIGHT):
        ring = [eye["outer"], eye["inner"], eye["upper"], eye["lower"]]
        sub = pts[ring, :2] * [w, h]
        x0, y0 = np.floor(sub.min(axis=0)).astype(int)
        x1, y1 = np.ceil(sub.max(axis=0)).astype(int)
        # 肤色取眼下 8 px 那一条带的均值（不从别处抄常数）
        band = out[min(y1 + 6, h - 1):min(y1 + 12, h), max(x0, 0):max(x1, 1)]
        tone = (band.reshape(-1, 3).mean(axis=0).astype(np.uint8) if band.size
                else np.array([200, 170, 150], dtype=np.uint8))
        out[max(y0, 0):min(y1, h), max(x0, 0):min(x1, w)] = tone
    return out


def main() -> int:
    missing = [p for p in (FIXTURE, DUAL) if not os.path.isfile(p)]
    if missing:
        print(f"缺夹具：{missing}（先生成：packaging/make-test-portrait.py / "
              "make-test-dual-portrait.py）")
        return 2
    base = load(FIXTURE)
    rows = [measures(base, "真图 fixture")]
    rows.append(measures(np.asarray(Image.fromarray(base).filter(
        ImageFilter.GaussianBlur(1.2)), dtype=np.uint8), "轻糊 r=1.2"))
    rows.append(measures(np.asarray(Image.fromarray(base).filter(
        ImageFilter.GaussianBlur(3.0)), dtype=np.uint8), "明显糊 r=3.0"))
    dark = np.clip(base.astype(np.float32) * 0.35, 0, 255).astype(np.uint8)
    bright = np.clip(base.astype(np.float32) * 2.6 + 12, 0, 255).astype(np.uint8)
    rows.append(measures(dark, "压暗 0.35x"))
    rows.append(measures(bright, "提亮 2.6x"))
    near = np.clip(base.astype(np.int16) + 2, 0, 255).astype(np.uint8)
    rows.append(measures(near, "近似（+2 偏置）"))
    crop = base[6:1006, 4:1024]
    rows.append(measures(crop, "近似（裁 6px）"))
    show(rows, "像素类度量（清晰度 / 曝光 / dHash）")

    hs = [r["sharp"] for r in rows[:3]]
    print(f"  清晰度空档（绝对能量）：真图 {hs[0]:.6f} → 轻糊 {hs[1]:.6f} → 明显糊 {hs[2]:.6f}")
    rs = [r["ratio"] for r in rows[:3]]
    print(f"  清晰度空档（相对自身对比度）：真图 {rs[0]:.4f} → 轻糊 {rs[1]:.4f} → "
          f"明显糊 {rs[2]:.4f}")
    print(f"  整体压暗 0.35×：绝对 {rows[3]['sharp']:.6f}（比明显糊还低）而比值 "
          f"{rows[3]['ratio']:.4f}（与真图同一格）→ 只看绝对值就会把暗图冤枉成糊图，"
          f"这就是 clarity() 两格一起用的全部理由")
    print(f"  提亮 2.6×：比值 {rows[4]['ratio']:.4f}（死白把对比度顶掉了，与糊不同源），"
          f"这一格由曝光判据负责报，清晰度判据不重复报")
    med = float(np.median([r["ratio"] for r in rows]))
    print(f"  批内中位数比值：{med:.4f}（相对线 = 中位数 × 档系数，"
          f"{sorted(PK.BLUR_REL_FACTOR.items())}）")
    for r in rows:
        b = PK.blur_read(PK.Measures(path=r["label"], sharpness=r["sharp"],
                                     ratio=r["ratio"], contrast=r["contrast"],
                                     under=r["under"], over=r["over"]),
                         "standard", med)
        tag = "—" if b is None else f'{b["kind"]}（{b["text"]}）'
        print(f"    blur_read[标准档] {r['label']:<18} → {tag}")
    d = lambda a, b: PK.hamming(rows[a]["dhash"], rows[b]["dhash"])
    print(f"  dHash 距离：同构图+2 偏置 {d(0, 5)} 位 | 糊 r=3 {d(0, 2)} 位 | 压暗 {d(0, 3)} 位 | "
          f"提亮 {d(0, 4)} 位 | 裁掉 6px {d(0, 6)} 位")
    print("  读数说明：前三类是「同一构图的不同张」（连拍/包围曝光），应当进同一组；"
          "裁 6px 给出的是**另一格构图**，哈希远开是 dHash 的定义而不是缺陷——所以分组"
          "只报「像」，绝不写「这两张重复，删一张」（手册 §AI挑图 与 2127 行同一句话）。")

    eye_rows = []

    def pair(rgb: np.ndarray, tag: str) -> None:
        """原图与"涂平眼区后再检测一次"的对照：两组都要**用各自那次检测的关键点**。

        拿原图的关键点去量涂平后的图，读数是恒等的——那等于没做对照。检测器在涂平图上
        给出的新点才是"眼睑塌成一条线"这件事的真实几何。
        """
        try:
            lms = eye_landmarks(rgb)
        except face_mod.MissingBackend as e:
            print(f"  眼睑那一档没量：mediapipe 后端不可用（{e}）——阈值只能沿用注释里的社区常用档")
            return
        for i, lm in enumerate(lms):
            eye_rows.append(measures(rgb, f"{tag} 第 {i} 张脸", lm))
            flat = paint_eyes(rgb, lm)
            try:
                flm = eye_landmarks(flat)
            except face_mod.MissingBackend:
                continue
            if i < len(flm):
                eye_rows.append(measures(flat, f"{tag} 涂平后 {i}", flm[i]))
            else:
                print(f"  {tag}：涂平后第 {i} 张脸没再被检测到（这一格只能报 unavailable，不猜）")

    pair(base, "眼·真图")
    if os.path.isfile(DUAL):
        pair(load(DUAL), "眼·两人")
    if eye_rows:
        show(eye_rows, "眼睑睁开比（FaceMesh 478 点的几何量）")
        op = [r["eye"] for r in eye_rows if r["eye"] is not None and "涂平" not in r["label"]]
        cl = [r["eye"] for r in eye_rows if r["eye"] is not None and "涂平" in r["label"]]
        if op and cl:
            print(f"  睁开组：{min(op):.4f} … {max(op):.4f}")
            print(f"  涂平组：{min(cl):.4f} … {max(cl):.4f}")
            print(f"  档位：{sorted(PK.EYE_SENSITIVITY.items())}——**不取在涂平与睁开的空档里**，"
                  f"因为夹具是画出来的脸、眼裂比真人开得大；阈值取在公开 EAR 文献的真人区间"
                  f"（闭眼 <0.15、睁眼 0.25–0.35）里，这一条只当「要不要复核」的标记")
    print(f"\n判据指纹：{PK.fingerprint()}（算法 {PK.ALGO_VERSION}，尺度 {PK.MEASURE_EDGE}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
