#!/usr/bin/env python3
"""生成多人（两张脸）固定测试图：SCOPE-001 的输入，来源零风险、可复现、可进仓库。

为什么不能拿现成单人夹具凑数：SCOPE-001 验的是"**探到两张脸时**引擎不替你选哪一张"，
判据落在 `precompute` 报出来的 `num_faces` 上。拿一张只有一张脸的图去测，代码分支
根本进不去，测试会"通过"而什么都没验——所以这张图必须让**真的 MediaPipe 检测器**
在同一帧里认出两张脸，而不是在测试里塞一个假后端谎报 num_faces（假后端 = 假验收）。

做法（完全可复现，无外部素材）：把 `portrait-1024x1280.png`（本仓程序化正脸，见
make-test-portrait.py）等比缩到 760×950，左格原样、右格水平镜像再压暗 8%，贴到
按原图采样出的背景色上。两张脸在代理档（引擎 `PROXY_PIXELS`=576000）下各自约
200 px 宽，实测 MediaPipe FaceLandmarker 报 num_faces=2。

许可：派生自本仓自有夹具（程序化生成，CC0 定位见 NOTICE），不含任何真人肖像或
第三方素材；产物与 sha256 一起写进 fixtures/，测试只认指纹不认"我记得长这样"。
"""
from __future__ import annotations

import argparse
import hashlib
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CELL_W, CELL_H = 760, 950
GAP = 50
DARKEN, LIFT = 0.92, 6.0


def bg_color(src_arr: np.ndarray) -> tuple[int, int, int]:
    """背景色：取原图采样均值。单独开一个函数是为了让台账里写的那三个数
    与贴上去的那三个数是**同一个表达式算出来的**，不是我事后编的。"""
    return tuple(int(v) for v in src_arr.reshape(-1, 3)[::997].mean(axis=0))


def build(src_path: str) -> Image.Image:
    src = Image.open(src_path).convert("RGB")
    left = src.resize((CELL_W, CELL_H), Image.LANCZOS)
    right = left.transpose(Image.FLIP_LEFT_RIGHT)
    a = np.asarray(right).astype(np.float32)
    right = Image.fromarray(np.clip(a * DARKEN + LIFT, 0, 255).astype(np.uint8))
    canvas = Image.new("RGB", (CELL_W * 2 + GAP, CELL_H), bg_color(np.asarray(src)))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (CELL_W + GAP, 0))
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=os.path.join(HERE, "..", "engine", "tests", "fixtures",
                                                  "portrait-1024x1280.png"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "engine", "tests", "fixtures"))
    args = ap.parse_args()

    img = build(args.src)
    path = os.path.join(args.out, f"portrait-dual-{img.width}x{img.height}.jpg")
    img.save(path, quality=95, subsampling=2)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    note = os.path.join(args.out, "portrait-dual.sha256.txt")
    with open(note, "w", encoding="utf-8") as fh:
        fh.write(
            "# LumaRetouch 多人测试图（SCOPE-001 输入）\n"
            f"{digest}  {os.path.basename(path)}\n"
            f"尺寸：{img.width}x{img.height}（两格 {CELL_W}x{CELL_H}，间隔 {GAP}px，"
            f"背景取原图采样均值 {bg_color(np.asarray(Image.open(args.src).convert('RGB')))}）\n"
            f"派生自：{os.path.relpath(args.src, os.path.dirname(note))}（程序化正脸，见 make-test-portrait.py）\n"
            f"变换：等比 LANCZOS 缩放 + 右格水平镜像 + 亮度 x{DARKEN}+{LIFT}\n"
            "检测事实：引擎代理档（PROXY_PIXELS=576000，本图解出 968x584）下 "
            "mediapipe FaceLandmarker 实测 num_faces=2（该数字由本仓测试 "
            "test_multi_face_photo_blocks_reshaping_but_keeps_global_edits 直接拿真后端重验，"
            "不是这里写死了就算数）\n"
            "许可：派生自本仓自有夹具，无真人肖像、无第三方素材\n")
    print(f"✓ {path}\n  sha256 {digest}\n  note {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
