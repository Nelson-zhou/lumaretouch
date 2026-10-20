#!/usr/bin/env python3
"""CPU 端到端视觉自证：拿真测试人像走引擎实际导出路径（export_image, device=cpu），
产出 before / after 对照图供人眼核对——不是 mock、不是"文件生成即通过"，是真实算法像素输出。

为什么单列：GPU 满载跑测受"整机 BACO 冻结"限制须留受控窗口；但导出算法在 CPU 上跑的是
同一条产品通路（vram cuda→cpu 回退，test_no_gpu_path 已证），所以像素级结构正确性
（磨皮是否只在肤色窗内、边缘/身份/背景有没有被带跑、调色是否越界）可以在 CPU 上出图自证，
把"代码存在"往前推成"看得见的输出对"。

诚实边界：夹具是 make-test-portrait.py 合成的矢量脸 + 颗粒噪声，验的是**窗口化/保边/作用域**
这类结构正确性，不是真实客片的肤质观感；真实照片的观感复核与交互帧率仍属 GPU 窗口那一轮。

跑法（仓库根，需运行时 venv 的 numpy/PIL/torch）：
    CUDA_VISIBLE_DEVICES="" PYTHONPATH=engine/src python packaging/cpu-visual-accept.py
产物写到独立目录 build/cpu-visual/（不覆盖 fixtures）：before.png / after_skin.png /
after_grade.png / compare_before_vs_skin.png / compare_before_vs_grade.png。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import torch  # noqa: F401  导出通路需要 torch；缺失即说明没装任一变体

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "engine", "src"))

from lumaretouch_engine.decode import load_rgb               # noqa: E402
from lumaretouch_engine.export import ExportSpec, export_image  # noqa: E402
from lumaretouch_engine.ops.deform import analytic_frontal_landmarks  # noqa: E402

FIXTURE = os.path.join(ROOT, "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
OUT_DIR = os.environ.get("LRT_OUT", os.path.join(ROOT, "build", "cpu-visual"))


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print(f"缺测试人像 {FIXTURE}，先跑 packaging/make-test-portrait.py")
        return 2
    os.makedirs(OUT_DIR, exist_ok=True)
    d = load_rgb(FIXTURE)
    src = np.ascontiguousarray(d.rgb)                         # (H,W,3) uint8
    print(f"fixture {d.w}x{d.h} dtype={src.dtype}")

    def save(arr, name):
        p = os.path.join(OUT_DIR, name)
        from PIL import Image
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(p)
        return p

    failures: list[str] = []

    # A) 恒等位：什么都没开 → 导出必须逐字节等于解码原图（引擎既有承诺，这里当自证基线）
    out_id, st_id = export_image(src, ExportSpec(strength=0.0, light=[]), device="cpu", tile=512)
    if not np.array_equal(out_id, src):
        failures.append("恒等位导出与原图不逐字节相等——导出通路的'什么都没开=原样'承诺破了")
    print(f"[identity] tiles={st_id.get('tiles')} 逐字节==原图: {np.array_equal(out_id, src)}")

    # B) 质感磨皮：肤色窗内应改动、窗外（背景）应基本不动
    out_skin, st_s = export_image(
        src, ExportSpec(strength=1.0, radius=8, texture_radius=3, light=[]), device="cpu", tile=512)
    delta_skin = np.abs(out_skin.astype(np.int16) - src.astype(np.int16)).mean()
    print(f"[skin s=1.0] tiles={st_s.get('tiles')} 平均改动={delta_skin:.3f} LSB")
    if float(delta_skin) <= 0.05:
        failures.append(f"磨皮 s=1.0 平均改动仅 {delta_skin:.3f} LSB，几乎没动像素——配方没进导出")

    # C) 肤色定向调色：动了像素且不越界（check() 已挡非法值，这里验确有作用）
    out_grade, _ = export_image(
        src, ExportSpec(strength=0.0, light=[], grade=(0.03, 0.10, 0.12, 1.0)), device="cpu", tile=512)
    delta_grade = np.abs(out_grade.astype(np.int16) - src.astype(np.int16)).mean()
    print(f"[grade] 平均改动={delta_grade:.3f} LSB")
    if float(delta_grade) <= 0.05:
        failures.append(f"肤色定向 grade 平均改动仅 {delta_grade:.3f} LSB，调色没进导出")

    # D) 换底入导出（P1-2）：旧 bug 是换底只活在预览、盘上没换。给一张前景椭圆遮罩 + 醒目背景色，
    #    导出必须真的把遮罩外（背景角）换成该色、遮罩内（主体中心）保留原图。
    #    export 层遮罩语义（composite_t: a*fg+(1-a)*bg）：matte=1→前景保留、0→背景替换。
    H, W = src.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    fg = (((xx - W * 0.5) / (W * 0.30)) ** 2 + ((yy - H * 0.5) / (H * 0.42)) ** 2) <= 1.0
    matte = np.where(fg, 255, 0).astype(np.uint8)
    BG = (0.90, 0.10, 0.90)                       # 醒目品红，与灰背景/肤色都不撞
    out_bg, _ = export_image(src, ExportSpec(strength=0.0, light=[], bg_matte=matte, bg_ref=BG),
                             device="cpu", tile=512)
    corner = out_bg[5, 5].astype(np.float64)      # 左上角：遮罩外，应为背景色
    expect = np.array(BG) * 255.0
    corner_ok = float(np.abs(corner - expect).max()) < 40
    center_ok = float(np.abs(out_bg[H // 2, W // 2].astype(np.int16)
                             - src[H // 2, W // 2].astype(np.int16)).mean()) < 30
    print(f"[bg swap] 背景角≈设定色: {corner_ok} (角={corner.round(0)} 期望≈{expect.round(0)})；"
          f"主体中心≈原图: {center_ok}")
    if not corner_ok:
        failures.append("换底导出：背景角没变成设定背景色——换底可能没进导出（P1-2 回归）")
    if not center_ok:
        failures.append("换底导出：主体中心被改动——遮罩极性可能反了")

    # E) 脸部形变进导出（核心工作流"脸部形变" + 验收"检查边缘和背景变形"）：给一个强形变（slim_face），
    #    导出必须真的 warp 面部、远处背景逐字节不动、无 NaN。用解析正面关键点（与居中人脸大致对齐）。
    lm = analytic_frontal_landmarks()
    out_def, _ = export_image(
        src, ExportSpec(strength=0.0, light=[], deform_amounts={"slim_face": 1.0}, landmarks=lm),
        device="cpu", tile=512)
    if not np.isfinite(out_def.astype(np.float64)).all():
        failures.append("形变导出含非有限值")
    delta_def = float(np.abs(out_def.astype(np.int16) - src.astype(np.int16)).mean())
    corner_def_ok = bool(np.array_equal(out_def[3, 3], src[3, 3]))   # 顶角远离面部影响半径，应不动
    print(f"[deform slim_face=1.0] 全图平均改动={delta_def:.3f} LSB；远处顶角逐字节不动: {corner_def_ok}")
    if delta_def <= 0.02:
        failures.append("形变导出：全图几乎没动——形变没进导出")
    if not corner_def_ok:
        failures.append("形变导出：远处顶角被改动——形变影响半径越界（背景被带跑）")

    sep = np.full((src.shape[0], 4, 3), 255, np.uint8)
    files = [
        save(src, "before.png"),
        save(out_skin, "after_skin.png"),
        save(out_grade, "after_grade.png"),
        save(out_bg, "after_bg.png"),
        save(out_def, "after_deform.png"),
        save(np.concatenate([src, sep, out_skin], axis=1), "compare_before_vs_skin.png"),
        save(np.concatenate([src, sep, out_grade], axis=1), "compare_before_vs_grade.png"),
        save(np.concatenate([src, sep, out_bg], axis=1), "compare_before_vs_bg.png"),
        save(np.concatenate([src, sep, out_def], axis=1), "compare_before_vs_deform.png"),
    ]
    print("产物：")
    for p in files:
        print("  ", p)

    if failures:
        print("\nVERDICT=FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nVERDICT=PASS  （恒等位逐字节=原图；磨皮/调色确有像素作用；对照图已出，供人眼核对窗口化与保边）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
