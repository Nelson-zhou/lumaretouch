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
# 第三格相对前两格的缩放。它同时是 PORTRAIT-006 那条端到端反算「漏掉的那一位在哪」
# 的唯一出处：测试自己再写一个 0.9 就是双出处，改这里而测试还在按旧数字算，会得到一条
# 空掩膜上的断言（本仓为这件事写过一整段注释）
THIRD_SCALE = 0.9


def bg_color(src_arr: np.ndarray) -> tuple[int, int, int]:
    """背景色：取原图采样均值。单独开一个函数是为了让台账里写的那三个数
    与贴上去的那三个数是**同一个表达式算出来的**，不是我事后编的。"""
    return tuple(int(v) for v in src_arr.reshape(-1, 3)[::997].mean(axis=0))


def build(src_path: str, cells: int = 2) -> Image.Image:
    """把同一张程序化正脸贴 N 格（默认 2 格 = 历史行为，逐字节不变）。

    为什么开这个口子（而不是再写一份 triple 脚本）：PORTRAIT-006 的「人工补上漏检的那
    一张」需要一张**检测器按定义会漏人**的照片——引擎只探 `SCOPE_MAX_FACES=2` 张，于是
    三格图上必然有一位不在名单里，而那一位的坐标是**本函数算出来的**（不是猜的）。
    再写一份脚本就会让两格的贴法漂成两套几何，那正是本仓反复防止的“双出处”。
    """
    if cells not in (2, 3):
        raise SystemExit(f"cells 只准备了 2（SCOPE-001）与 3（PORTRAIT-006 漏检臂），得到 {cells}")
    src = Image.open(src_path).convert("RGB")
    left = src.resize((CELL_W, CELL_H), Image.LANCZOS)
    right = left.transpose(Image.FLIP_LEFT_RIGHT)
    a = np.asarray(right).astype(np.float32)
    right = Image.fromarray(np.clip(a * DARKEN + LIFT, 0, 255).astype(np.uint8))
    # 第三格：左侧那位缩小一档再贴。缩放是为了让它与另两位在检测得分上拉开距离
    # （探 2 张时它几乎总是被裁掉的那一个），而不是为了好看
    third = left.resize((int(CELL_W * THIRD_SCALE), int(CELL_H * THIRD_SCALE)), Image.LANCZOS)
    canvas = Image.new("RGB", (CELL_W * cells + GAP * (cells - 1), CELL_H),
                       bg_color(np.asarray(src)))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (CELL_W + GAP, 0))
    if cells == 3:
        canvas.paste(third, (2 * (CELL_W + GAP), CELL_H - third.height))
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=os.path.join(HERE, "..", "engine", "tests", "fixtures",
                                                  "portrait-1024x1280.png"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "engine", "tests", "fixtures"))
    ap.add_argument("--cells", type=int, default=2, choices=(2, 3),
                    help="2 = SCOPE-001 多人图；3 = PORTRAIT-006 的漏检臂（只打到 stdout，"
                         "不覆盖台账里那两张双人格产物）")
    args = ap.parse_args()

    img = build(args.src, cells=args.cells)
    if args.cells != 2:
        # 三格是测试现算的临时输入（派生自已进台账的两格配方），不进 fixtures/：
        # 台账里每多一张图都要多一份 sha256 与一句“谁验过这个数字”，不该白占
        out = os.path.join(args.out, f"portrait-triple-{img.width}x{img.height}.jpg")
        img.save(out, quality=95, subsampling=2)
        print(f"✓ {out}\n  sha256 {hashlib.sha256(open(out, 'rb').read()).hexdigest()}")
        return 0
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
