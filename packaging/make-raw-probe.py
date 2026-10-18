#!/usr/bin/env python3
"""生成 ctypes 自检用的探针 DNG 与它的真值 sidecar —— 落进引擎包，不是 tests 目录。

为什么要有这一件（ops/libraw.py 的 self_check 拿它对账）：偏移表是在开发机上按**那份真头**
生成的，装机件跑的却是别人机器上那块 .so。表与库对不上时不会抛异常，只会读到一堆看着像
数据的垃圾（尺寸读成 0、机型名读成随机字节、预览指针指到别人的缓冲）——那种读数在报表上
与真数据长得一样，正是本仓拦过多次的「内部自洽的假数据」。

答案从哪来：写盘时就知道（build() 的调用参数 + 我们自己从 JPEG SOF 段算出的尺寸/sha256），
**不是问 LibRaw 要**。拿一个库的输出验这个库自己，只能证明自洽，证明不了符合。

为什么放 engine/src/.../data 而不是 tests/fixtures：packaging/stage-engine.sh 只把
engine/src 打进装机件，机器上没有 tests 目录；自检跑在装机件第一次处理 RAW 之前，材料
必须跟着包走。

可重复：源图是纯算术生成的梯度与色块，不取时钟、不读仓库里的照片。JPEG 由 Pillow 编码，
不同 Pillow 版本可能给出不同字节——所以这份 .dng 与 .json 必须**同一次生成**一起提交
（sidecar 里记了 .dng 的 sha256，两份不同步时 self_check 直接拒），而测试要验的是语义
事实（尺寸/机型/预览宽高），不是拿重新生成的文件去比字节。

跑法：python3 packaging/make-raw-probe.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "..", "engine", "src")))

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "engine", "src",
                                       "lumaretouch_engine", "data"))
W, H = 128, 96          # 满幅输出尺寸（写侧的真值，也是 self_check 对账的那一对）
PW, PH = 40, 32        # 内嵌预览尺寸：小到不值得当代理，够大到能把 thumbnail 的偏移钉死

_spec = importlib.util.spec_from_file_location("make_test_dng", os.path.join(HERE, "make-test-dng.py"))
mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt)


def _src(h: int = H, w: int = W) -> np.ndarray:
    """纯算术源图：三个通道各自的斜率不同，取值范围铺满 0..255。

    字节序那一臂靠的是「16-bit 右移 8 位要等于同档 8-bit 输出」，平坦区两种解释都过，
    所以这张图必须有足够的梯度把唯一解顶出来——斜率互质是为了别让某一通道退化成常数。
    """
    yy, xx = np.meshgrid(np.arange(h), np.arange(w))
    return np.dstack([
        ((xx * 7 + yy * 3) % 256).astype(np.uint8),
        ((xx * 13 + yy * 61) % 256).astype(np.uint8),
        ((xx * 29 + yy * 11) % 251).astype(np.uint8),
    ]).transpose(1, 0, 2)


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    dng = os.path.join(OUT_DIR, "raw-probe.dng")
    side = os.path.join(OUT_DIR, "raw-probe.json")

    src = _src()
    preview = _src(h=PH, w=PW)
    blob = mt._jpeg_bytes(preview)          # 先自己编好：build() 原样嵌进去，答案就是我们手上这份
    pw, ph = mt._jpeg_size(blob)
    # 拍摄参数写成正规 EXIF 子 IFD（与真相机同一种摆位）：Exif 面板的 ISO/快门/光圈
    # 要在有真值的材料上验，不能等客户拿真照片来当第一个试错对象
    exif = (200, 0.005, 2.8, 35.0)          # iso, shutter(=1/200), aperture, focal
    info = mt.build(dng, src, preview=blob, exif_ifd=exif, rows_per_strip=32)

    with open(dng, "rb") as f:
        dng_bytes = f.read()
    truth = {
        "_note": "packaging/make-raw-probe.py 生成的自检真值；与 raw-probe.dng 同一次生成，改一件必须改两件",
        "built_by": "packaging/make-raw-probe.py",
        "i_w": int(info["size"][0]), "i_h": int(info["size"][1]),
        "make": "LumaRetouch", "model": "TestCam",
        "white": float(info["white"]), "black": float(info["black"]),
        "pattern": [int(v) for v in info["pattern"]],
        "preview": {"w": int(pw), "h": int(ph), "bytes": len(blob),
                    "sha256": hashlib.sha256(blob).hexdigest()},
        # 写进去的拍摄参数（不是 LibRaw 读出的）：自检拿它对 libraw_imgother_t 那几个偏移。
        # 实测这份 LibRaw 不从我们的探针里取 ISO（子 IFD 与影像 IFD 两种摆位都试过），
        # 所以 iso 只报不判——理由与回归锁在 test_raw 那条用例里。
        "exif": {"iso": exif[0], "shutter": exif[1], "aperture": exif[2], "focal_len": exif[3]},
        "dng_sha256": hashlib.sha256(dng_bytes).hexdigest(),
        "dng_bytes": len(dng_bytes),
    }
    # 先确认自研读侧也认出同一件事：它报的尺寸与写侧的 info 必须一致。这条不是给
    # LibRaw 用的（那是 self_check 的活），是防止探针写歪了却两份 sidecar 一起歪。
    from lumaretouch_engine import raw as R
    got = R.load_raw(dng, reference=True)["meta"]
    if (got.w, got.h) != (truth["i_w"], truth["i_h"]):
        raise SystemExit(f"× 探针不合格：写侧认为 {truth['i_w']}x{truth['i_h']}，"
                         f"自研读侧读出 {got.w}x{got.h}——材料本身就对不上，拿去对账只会两头错")

    with open(side, "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"✓ {os.path.relpath(dng, HERE)}：{truth['i_w']}x{truth['i_h']} {truth['dng_bytes']} 字节，"
          f"预览 {pw}x{ph} {len(blob)} 字节")
    print(f"✓ {os.path.relpath(side, HERE)}：dng_sha256={truth['dng_sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
