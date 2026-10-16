#!/usr/bin/env python3
"""生成 M1-3a 的固定测试人像：程序化正脸，来源零风险、可复现、可写进仓库。

为什么要它：真实照片要么带真人隐私，要么带第三方许可，都不能进仓库；而 M1-3a 要量的
三件事（真图解码耗时、代理档持续帧率、strength=0 逐字节保真）只依赖"这是一张有纹理、
有边缘、有高频细节的图"，不依赖"这是某个人的脸"。

已知边界（说清楚，不留到后面才发现）：这张图是几何画出来的，MediaPipe 的 478 点检测
不保证认它。M1-3b 开工前要补一张真实正脸（总工放入 fixtures/，或届时 ImageGen 额度恢复
后生成），届时这张程序化图继续负责通路回归，那张负责检测回归。

产出（默认写 engine/tests/fixtures/）：
  portrait-1024x1280.jpg   JPEG q95 带 chroma subsampling → 量真实解码路径
  portrait-1024x1280.png   无损 → 量「解码 → 代理 → 上屏」的逐字节可复现性
  portrait-1024x1280.sha256.txt   两款 sha256 与来源说明
"""
from __future__ import annotations

import argparse
import hashlib
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1024, 1280
CX = W // 2                     # 正面构图，脸在水平中线
SEED = 20261016
SKIN = (226, 178, 152)


def draw_structure() -> Image.Image:
    """影棚背景 + 头颈肩 + 五官，纯几何，一次一样。"""
    # 背景：上深下浅的渐变。纯色背景会让"画面真的在动"和低频层都失去区分度
    bg = np.tile(np.linspace(188, 208, H, dtype=np.float32)[:, None], (1, W))
    img = Image.fromarray(np.dstack([bg] * 3).astype(np.uint8))
    d = ImageDraw.Draw(img)

    d.polygon([(CX - 430, H), (CX - 300, 1010), (CX + 300, 1010), (CX + 430, H)],
              fill=(168, 172, 180))                          # 肩
    d.rectangle((CX - 130, 880, CX + 130, 1050), fill=(196, 150, 126))   # 颈
    d.ellipse((CX - 300, 170, CX + 300, 900), fill=SKIN)                  # 头
    d.ellipse((CX - 322, 470, CX - 282, 570), fill=(214, 166, 140))       # 耳
    d.ellipse((CX + 282, 470, CX + 322, 570), fill=(214, 166, 140))
    d.pieslice((CX - 330, 120, CX + 330, 640), 180, 360, fill=(58, 42, 36))
    d.rectangle((CX - 330, 300, CX - 250, 620), fill=(58, 42, 36))        # 头发两侧
    d.rectangle((CX + 250, 300, CX + 330, 620), fill=(58, 42, 36))

    for sx in (-1, 1):                                      # 眉 / 眼白 / 虹膜 / 瞳孔 / 高光
        ex = CX + sx * 112
        d.arc((ex - 74, 434, ex + 74, 500), 200, 340, fill=(72, 52, 44), width=16)
        d.ellipse((ex - 54, 496, ex + 54, 548), fill=(246, 244, 240))
        d.ellipse((ex - 24, 498, ex + 24, 546), fill=(96, 68, 52))
        d.ellipse((ex - 11, 505, ex + 11, 539), fill=(20, 14, 12))
        d.ellipse((ex + 2, 506, ex + 12, 516), fill=(252, 252, 252))
    d.polygon([(CX - 16, 540), (CX + 16, 540), (CX + 30, 686), (CX - 30, 686)],
              fill=(212, 162, 136))                          # 鼻
    d.ellipse((CX - 34, 676, CX - 8, 700), fill=(150, 104, 88))           # 鼻孔
    d.ellipse((CX + 8, 676, CX + 34, 700), fill=(150, 104, 88))
    d.ellipse((CX - 88, 742, CX + 88, 812), fill=(186, 108, 100))         # 唇
    d.line((CX - 84, 778, CX + 84, 778), fill=(120, 66, 62), width=6)
    return img


def add_skin_detail(img: Image.Image) -> Image.Image:
    """叠两层皮肤该有的东西：中等尺度色斑 + 细密颗粒，只加在亮部（头发与暗部不加）。

    这一步不是装饰：磨皮/频域分离管线对纯平涂是恒等映射，没有高频就没有可观测差异，
    「常驻路径与逐帧路径逐字节一致」这种断言会变成永远为真的空话。
    """
    arr = np.asarray(img).astype(np.float32)
    lum = arr.mean(axis=-1)
    light = np.clip((lum - 120.0) / 60.0, 0.0, 1.0)          # 软掩膜：亮处才加纹理

    rng = np.random.default_rng(SEED)
    # 色斑必须绕着 128 抖（中灰），因为下面要减 128 当低频偏移量。写成
    # `normal(128, 26) + 128` 的话均值变成 256，一半样本被 clip 到 255，
    # detail 退化成≈+44 的直流偏移——恰好抹掉了本函数存在的理由。
    raw = rng.normal(128.0, 26.0, size=(H // 4, W // 4))
    # 直接在中间量上把关，不靠成品反推：色斑是低频，写错了最终图的高频/均值/饱和比例
    # 全都看不出来（上一版就是这个状态：高频 std 0.045 照常过自检）。
    clipped = float((raw > 255.0).mean() + (raw < 0.0).mean())
    assert abs(float(raw.mean()) - 128.0) < 5.0, f"色斑均值 {raw.mean():.1f}，不是绕中灰抖"
    assert clipped < 0.01, f"{clipped:.1%} 的色样本被 clip，低频对比已被削平"
    blobs = Image.fromarray(np.clip(raw, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    detail = (np.asarray(blobs, np.float32) - 128.0) * 0.35          # 色斑（低频）
    detail = detail + rng.normal(0.0, 3.2, size=(H, W))              # 颗粒（高频）
    detail *= light
    arr += np.stack([detail] * 3, axis=-1) * np.array([1.0, 0.9, 0.8])[None, None, :]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def build() -> Image.Image:
    return add_skin_detail(draw_structure())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "..", "engine", "tests", "fixtures"))
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    img = build()
    jpg = os.path.join(out, "portrait-1024x1280.jpg")
    png = os.path.join(out, "portrait-1024x1280.png")
    img.save(jpg, quality=95, subsampling=1, optimize=True)
    img.save(png, optimize=True)

    lines = ["# 来源：packaging/make-test-portrait.py 程序化生成——非真实人物，无第三方许可，无隐私",
             f"# 种子 SEED={SEED}；下迹 sha256 是**变更审计线索**，不是跨环境可复现承诺：",
             "#   JPEG/PNG 字节取决于 Pillow/libjpeg-turbo 构建，重跑得到不同哈希属正常，",
             "#   要换资产请连本文件一起重生成并同步更新测试（engine/tests/test_decode.py 会比对哈希）。",
             "# 用途：M1-3a 真图解码/代理档/数值保真回归；M1-3b 的人脸检测回归需另备真实正脸"]
    for p in (jpg, png):
        raw = open(p, "rb").read()
        lines.append(f"{hashlib.sha256(raw).hexdigest()}  {os.path.basename(p)}")
        print(f"{os.path.basename(p):26s} {len(raw) / 1e6:6.2f} MB")

    # 结构自检：既要能看出"这是张脸"（低频对比），也要有可磨的高频，否则管线测不出东西
    gray = np.asarray(img.convert("L"))
    a = gray.astype(np.float32) / 255.0
    hi = a - np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(6)), np.float32) / 255.0
    sat = float((gray >= 255).mean())
    print(f"亮度 std={a.std():.4f}  高频能量 std={hi.std():.5f}  高频均值={hi.mean():+.5f}  饱和比例={sat:.4f}")
    assert a.std() > 0.05, "对比度不足：这张图对管线没有区分度"
    assert hi.std() > 0.002, "高频几乎为 0：磨皮类管线在这张图上等价于恒等，测不出问题"
    assert sat < 0.05, f"{sat:.1%} 的像素贴在 255：纹理被 clip 掉了"

    with open(os.path.join(out, "portrait-1024x1280.sha256.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
