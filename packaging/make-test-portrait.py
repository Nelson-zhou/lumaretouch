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
# PORTRAIT-009 的三条给定样本（冻结件 given：含眼镜/遮挡/低光/深肤色和露齿样本）。
# 低光那一臂不单独出图：它是同一张图乘一个系数，写成图只会多一份要审计的哈希。
SKIN_DEEP = (122, 80, 58)        # 深肤色：整张图的皮肤与唇都跟着换，不是叠一层灰
TEETH = (247, 245, 241)
CAVITY = (38, 22, 24)
# 变体专用的“待修”色调：自然牙不是白的，是发黄的 (232,222,196)→v≈0.91；眼白也一样。
# 为什么要改：夹具直接画成 0.97 的自牙与自眼白，过曝护栏会正确地判定“不能再亮”，
# 于是这一层在测试图上几乎没活可干——那会把“效果为零”伪装成“护栏生效”。
TEETH_WARM = (232, 222, 196)
SCLERA_WARM = (233, 228, 215)


def draw_structure(mouth: str = "closed", skin: tuple = SKIN, glasses: bool = False,
                   sclera: tuple = (246, 244, 240), teeth: tuple = TEETH) -> Image.Image:
    """影棚背景 + 头颈肩 + 五官，纯几何，一次一样。

    `mouth="open"` 画的是**有地面的真相**的露齿：口腔暗腔 + 一排牙齿（每颗之间留一条
    比牙暗的缝）+ 下排牙。这样 test_enhance 才能拿"掩膜落在画上去的牙上、唇面一格没动"
    当判据，而不是只看"效果顺眼"。
    """
    # 背景：上深下浅的渐变。纯色背景会让"画面真的在动"和低频层都失去区分度
    bg = np.tile(np.linspace(188, 208, H, dtype=np.float32)[:, None], (1, W))
    img = Image.fromarray(np.dstack([bg] * 3).astype(np.uint8))
    d = ImageDraw.Draw(img)

    lip = tuple(int(c * 0.62) for c in (186, 108, 100)) if skin is SKIN_DEEP \
        else (186, 108, 100)
    d.polygon([(CX - 430, H), (CX - 300, 1010), (CX + 300, 1010), (CX + 430, H)],
              fill=(168, 172, 180))                          # 肩
    d.rectangle((CX - 130, 880, CX + 130, 1050),
                fill=tuple(int(c * 0.66) for c in (196, 150, 126)) if skin is SKIN_DEEP
                else (196, 150, 126))                        # 颈
    d.ellipse((CX - 300, 170, CX + 300, 900), fill=skin)                    # 头
    d.ellipse((CX - 322, 470, CX - 282, 570),
              fill=tuple(int(c * 0.72) for c in skin))                       # 耳
    d.ellipse((CX + 282, 470, CX + 322, 570),
              fill=tuple(int(c * 0.72) for c in skin))
    d.pieslice((CX - 330, 120, CX + 330, 640), 180, 360, fill=(58, 42, 36))
    d.rectangle((CX - 330, 300, CX - 250, 620), fill=(58, 42, 36))        # 头发两侧
    d.rectangle((CX + 250, 300, CX + 330, 620), fill=(58, 42, 36))

    for sx in (-1, 1):                                      # 眉 / 眼白 / 虹膜 / 瞳孔 / 高光
        ex = CX + sx * 112
        d.arc((ex - 74, 434, ex + 74, 500), 200, 340, fill=(72, 52, 44), width=16)
        d.ellipse((ex - 54, 496, ex + 54, 548),
                  fill=(238, 234, 226) if skin is SKIN_DEEP else sclera)
        d.ellipse((ex - 24, 498, ex + 24, 546), fill=(74, 50, 38) if skin is SKIN_DEEP
                  else (96, 68, 52))
        d.ellipse((ex - 11, 505, ex + 11, 539), fill=(20, 14, 12))
        d.ellipse((ex + 2, 506, ex + 12, 516), fill=(252, 252, 252))
    d.polygon([(CX - 16, 540), (CX + 16, 540), (CX + 30, 686), (CX - 30, 686)],
              fill=tuple(int(c * 0.94) for c in skin))                      # 鼻
    d.ellipse((CX - 34, 676, CX - 8, 700), fill=tuple(int(c * 0.7) for c in skin))  # 鼻孔
    d.ellipse((CX + 8, 676, CX + 34, 700), fill=tuple(int(c * 0.7) for c in skin))
    if mouth == "closed":
        d.ellipse((CX - 88, 742, CX + 88, 812), fill=lip)
        d.line((CX - 84, 778, CX + 84, 778), fill=(120, 66, 62), width=6)
    else:
        # 露齿：唇外圈 → 暗腔 → 上排牙（6 颗，缝比牙暗）→ 下排牙（4 颗）
        d.ellipse((CX - 96, 726, CX + 96, 830), fill=lip)                   # 唇
        d.ellipse((CX - 78, 748, CX + 78, 808), fill=CAVITY)                # 口腔
        d.rounded_rectangle((CX - 70, 748, CX + 70, 776), radius=6, fill=teeth)
        for i in range(1, 6):
            x = CX - 70 + i * (140 // 6)
            d.line((x, 750, x, 774), fill=(196, 192, 186), width=2)         # 牙缝
        d.line((CX - 68, 774, CX + 68, 774), fill=(52, 34, 34), width=3)    # 龈缘
        d.rounded_rectangle((CX - 46, 788, CX + 46, 806), radius=5, fill=teeth)
        for i in range(1, 4):
            x = CX - 46 + i * (92 // 4)
            d.line((x, 790, x, 804), fill=(196, 192, 186), width=2)
    if glasses:
        # 眼镜：中性灰的横梁与镜圈（s≈0）。这一臂要证的是虹膜门不把中性物当成眼睛，
        # 所以故意把横梁压在虹膜盘上，而不是绕开它。
        d.rectangle((CX - 190, 512, CX + 190, 528), fill=(150, 150, 150))
        for sx in (-1, 1):
            d.ellipse((CX + sx * 112 - 66, 480, CX + sx * 112 + 66, 566),
                      outline=(150, 150, 150), width=7)
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


def build(mouth: str = "closed", skin: tuple = SKIN, glasses: bool = False,
          sclera: tuple = (246, 244, 240), teeth: tuple = TEETH) -> Image.Image:
    return add_skin_detail(draw_structure(mouth=mouth, skin=skin, glasses=glasses,
                                          sclera=sclera, teeth=teeth))


# 变体表：名字 → (文件名, 参数)。每一件都对应冻结件 PORTRAIT-009 的 given 中的一格。
# 低光不单独出图：它是同一张图乘一个系数，写成图只会多一份要审计的哈希。
WARM = dict(sclera=SCLERA_WARM, teeth=TEETH_WARM)
VARIANTS = {
    "smile": ("portrait-smile-1024x1280.jpg", dict(mouth="open", **WARM)),
    "glasses": ("portrait-glasses-smile-1024x1280.jpg",
                dict(mouth="open", glasses=True, **WARM)),
    "deep": ("portrait-deep-skin-smile-1024x1280.jpg",
             dict(mouth="open", skin=SKIN_DEEP, sclera=(224, 218, 205), teeth=TEETH_WARM)),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "..", "engine", "tests", "fixtures"))
    ap.add_argument("--skip-base", action="store_true",
                    help="只重生 PORTRAIT-009 的变体，不动已经归档哈希的那两张")
    ap.add_argument("--variant", action="append", choices=sorted(VARIANTS), default=None)
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    wanted = args.variant or sorted(VARIANTS)
    files = []
    if not args.skip_base:
        img = build()
        jpg = os.path.join(out, "portrait-1024x1280.jpg")
        png = os.path.join(out, "portrait-1024x1280.png")
        img.save(jpg, quality=95, subsampling=1, optimize=True)
        img.save(png, optimize=True)
        files.append(jpg)
        files.append((png, img))
        base_img = img
    else:
        base_img = None
    for name in wanted:
        fname, kw = VARIANTS[name]
        p = os.path.join(out, fname)
        build(**kw).save(p, quality=95, subsampling=1, optimize=True)
        files.append(p)

    lines = ["# 来源：packaging/make-test-portrait.py 程序化生成——非真实人物，无第三方许可，无隐私",
             f"# 种子 SEED={SEED}；下迹 sha256 是**变更审计线索**，不是跨环境可复现承诺：",
             "#   JPEG/PNG 字节取决于 Pillow/libjpeg-turbo 构建，重跑得到不同哈希属正常，",
             "#   要换资产请连本文件一起重生成并同步更新测试（engine/tests/test_decode.py 会比对哈希）。",
             "# 用途：M1-3a 真图解码/代理档/数值保真回归；M1-3b 的人脸检测回归需另备真实正脸",
             "# PORTRAIT-009 变体（露齿/眼镜/深肤色）：同一段代码的参数分支，因此同一批拓扑；",
             "#   牙齿与口腔的位置是**画上去的**，所以 test_enhance 能拿它当接地真相。"]
    for item in files:
        p = item[0] if isinstance(item, tuple) else item
        raw = open(p, "rb").read()
        lines.append(f"{hashlib.sha256(raw).hexdigest()}  {os.path.basename(p)}")
        print(f"{os.path.basename(p):40s} {len(raw) / 1e6:6.2f} MB")

    # 结构自检：既要能看出"这是张脸"（低频对比），也要有可磨的高频，否则管线测不出东西
    img = base_img if base_img is not None else build()
    gray = np.asarray(img.convert("L"))
    a = gray.astype(np.float32) / 255.0
    hi = a - np.asarray(img.convert("L").filter(ImageFilter.GaussianBlur(6)), np.float32) / 255.0
    sat = float((gray >= 255).mean())
    print(f"亮度 std={a.std():.4f}  高频能量 std={hi.std():.5f}  高频均值={hi.mean():+.5f}  饱和比例={sat:.4f}")
    assert a.std() > 0.05, "对比度不足：这张图对管线没有区分度"
    assert hi.std() > 0.002, "高频几乎为 0：磨皮类管线在这张图上等价于恒等，测不出问题"
    assert sat < 0.05, f"{sat:.1%} 的像素贴在 255：纹理被 clip 掉了"

    with open(os.path.join(out, "portrait-1024x1280.sha256.txt"),
              "a" if args.skip_base else "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
