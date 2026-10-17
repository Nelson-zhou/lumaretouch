#!/usr/bin/env python3
"""生成 DNG 试验靶：把一张已知 RGB 按规范的**正向**模型写成一张合规 DNG。

为什么仓库里放一个「写」侧而不是直接收几张相机 RAW：
* 真实相机 RAW 要么带真人、要么带第三方许可，都不能入库（与 portrait fixture 同一条
  规矩）；而这一版的判据是「读侧的数学对不对」，它需要的是**知道答案**的输入。
* 程序化生成还能覆盖真机样本给不全的组合：4 色排阵、瓦片、Deflate、Predictor 2、
  双份相机档案、EXIF 摆正——这些用真照片一个都测不到。

三件事分开看，别把第一条当成全部（这是本仓「自产自读是循环论证」那条老教训）：
1. **写侧的符合性由第三方证明**：判据脚本会把生成的 DNG 交给系统里的 LibRaw
   （ImageMagick 的 DNG delegate）解一遍；它解得开、尺寸对得上，才说明标签号、
   类型/计数、ActiveArea 顺序这些事实写对了。
2. **读侧的地面真值由往返证明**：已知 RGB → 正向 → 写盘 → 引擎读回。误差归因到
   容器、线性化、demosaic 三处。色彩那条式子**不在**这里的证明范围里（写侧就是按
   读侧的逆写的，错了也会一起错）。
3. **色彩的对外符合性由 LibRaw 对账证明**：同一个文件，我们渲染的与 LibRaw 渲染的
   必须同向（逐通道相关 + 均值不跑偏）。少了这一臂，往返再准也只是自证。

正向模型 = raw.py 渲染链的解析逆：
    rgb(sRGB) → linear → XYZ(D65) → XYZ(D50) → 相机值 c → raw = c·(white−max_black)+black
其中 c→XYZ 用的是 `camera_to_xyz_matrix` 那份矩阵，所以「恒等」不是假设而是构造。
"""
from __future__ import annotations

import argparse
import os
import struct
import zlib
from fractions import Fraction

import numpy as np
from PIL import Image

# 与 raw.py 同一套标签号（这里是写侧，故意各自写一份数字而不是 import 引擎：
# 测试资产依赖被测代码的常量，就等于让被测代码给自己出题）
TAGS = dict(new_subfile=0x00FE, width=0x0100, length=0x0101, bps=0x0102,
            compression=0x0103, photometric=0x0106, make=0x010F, model=0x0110,
            strip_offsets=0x0111, orientation=0x0112, spp=0x0115, rows_per_strip=0x0116,
            strip_counts=0x0117, planar=0x011C, predictor=0x013D, tile_w=0x0142,
            tile_h=0x0143, tile_offsets=0x0144, tile_counts=0x0145, sub_ifds=0x014A,
            sample_format=0x0153, cfa_dim=0x828D, cfa_pattern=0x828E,
            dng_version=0xC612, dng_backward=0xC613, unique_model=0xC614,
            color_planes=0xC615, cfa_plane_color=0xC616, cfa_layout=0xC617,
            linearization=0xC618, black_repeat=0xC619, black=0xC61A,
            black_delta_h=0xC61B, black_delta_v=0xC61C, white=0xC61D,
            crop_origin=0xC61F, crop_size=0xC620, cm1=0xC621, cm2=0xC622,
            cc1=0xC623, cc2=0xC624, rm1=0xC625, rm2=0xC626, analog=0xC627,
            neutral=0xC628, baseline_exposure=0xC62A, illum1=0xC65A, illum2=0xC65B,
            active_area=0xC68D, fm1=0xC714, fm2=0xC715, preview_color_space=0xC71A)

T_BYTE, T_ASCII, T_SHORT, T_LONG, T_RATIONAL, T_UNDEFINED, T_SLONG, T_SRATIONAL = \
    1, 2, 3, 4, 5, 7, 9, 10
TYPE_SIZE = {T_BYTE: 1, T_ASCII: 1, T_SHORT: 2, T_LONG: 4, T_RATIONAL: 8,
             T_UNDEFINED: 1, T_SLONG: 4, T_SRATIONAL: 8}

# 与 raw.py 同一条渲染链要用到的公开常数（写侧自己复制一份，理由见模块 docstring）
XYZ_D50 = np.array([0.964220, 1.0, 0.824890])
XYZ_D65 = np.array([0.950470, 1.0, 1.088830])
XYZ_TO_SRGB = np.array([[3.2407091, -1.5372984, -0.4986282],
                        [-0.9692581, 1.8759676, 0.0415561],
                        [0.0556340, -0.2039118, 1.0572660]])
SRGB_TO_XYZ = np.linalg.inv(XYZ_TO_SRGB)
BRADFORD = np.array([[0.8951, 0.7502, 0.0380],
                     [-0.7502, 1.0126, 0.0609],
                     [0.0380, -0.0609, 0.1111]])
DEFAULT_CM1 = np.array([[0.5814, -0.1552, -0.0362],
                        [-0.2744, 1.0194, 0.0483],
                        [0.0237, -0.3234, 1.2538]])
DEFAULT_CM2 = np.array([[0.6596, -0.2078, -0.0562],
                        [-0.3028, 1.1382, 0.0628],
                        [0.0572, -0.4006, 1.4200]])


def bradford(src, dst):
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    s = BRADFORD @ (src / src[1])
    d = BRADFORD @ (dst / dst[1])
    return np.linalg.inv(BRADFORD) @ np.diag(d / s) @ BRADFORD


def srgb_decode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def render_matrix(cm, neutral, ab=None, cc=None):
    """raw.camera_to_xyz_matrix 的同一份式子（写侧要它的逆，所以必须逐字一致）。"""
    n = cm.shape[0]
    ab = np.ones(n) if ab is None else ab
    cc = np.eye(n) if cc is None else cc
    xyz_to_cam = np.diag(ab) @ cc @ cm
    k = np.linalg.inv(xyz_to_cam)
    white = k @ neutral
    k = k / float(white[1])
    return bradford(k @ neutral, XYZ_D50) @ k


def quad_lut(white: float) -> np.ndarray:
    """一个真的非线性 LinearizationTable：lut[v] = v²/white（在 0..white 上单调）。

    为什么要真曲线而不是恒等表：恒等表只能证明「读了那张表」，证不了「按表
    把值映回去了」；而上一版试过拿 4096 格的恒等表配 16383 的白电平，结果所有高光
    都被“越界取最后一格”压平（往返 mean|Δ| 从 2.8 跳到 15.4）——那其实是读侧按规范做
    对了，错的是造靶的人。
    """
    v = np.arange(int(white) + 1, dtype=np.float64)
    return np.rint(v * v / white).astype(np.uint16)


def rgb_to_mosaic(rgb_u8: np.ndarray, pattern=(0, 1, 1, 2), dims=(2, 2),
                  cm1=DEFAULT_CM1, neutral=None, black=256.0, white=16383.0,
                  reduction=None, headroom=1.0, nonlinear=None) -> dict:
    """已知 RGB → (mosaic uint16, 这套 mosaic 所依据的加工参数)。"""
    n = int(max(pattern)) + 1
    if neutral is None:
        cand = cm1 @ XYZ_D50
        neutral = cand / cand.max()
    neutral = np.asarray(neutral, dtype=np.float64)
    if n > 3 and reduction is None:
        # 四色：第四通道按 reduction 的第四列取「不参与」，即 RM=[I3|0]。这样 4→3
        # 降色是精确的，往返误差不掺降色误差（ReductionMatrix 本身另有专测）
        reduction = np.hstack([np.eye(3), np.zeros((3, 1))])
    lin = srgb_decode(rgb_u8.astype(np.float64) / 255.0)
    xyz_d65 = lin @ SRGB_TO_XYZ.T
    to_d50 = np.linalg.inv(bradford(XYZ_D50, XYZ_D65))
    xyz_d50 = xyz_d65 @ to_d50.T
    scale_t = render_matrix(cm1, neutral)
    cam = xyz_d50 @ np.linalg.inv(scale_t).T * headroom
    if n > 3:
        cam4 = np.zeros(cam.shape[:2] + (n,), dtype=np.float64)
        cam4[..., :3] = cam
        cam = cam4
    clip_neg = float((cam < 0).mean())
    clip_over = float((cam > 1.0).mean())
    cam = np.clip(cam, 0.0, 1.0)
    scale = white - black
    raw_vals = cam * scale + black
    lut = None
    if nonlinear == "quad":
        lut = quad_lut(white)
        # 存的是“逆表”：读侧先过 lut 再减黑，所以要 lut[stored] == raw_vals
        raw_vals = np.sqrt(np.clip(raw_vals, 0.0, None) * white)
    lin16 = np.rint(raw_vals).astype(np.uint16)
    ph, pw = dims
    p = np.array(pattern, dtype=np.uint8).reshape(ph, pw)
    h, w = lin16.shape[:2]
    mosaic = np.zeros((h, w), dtype=np.uint16)
    for color in range(n):
        for (dr, dc) in np.argwhere(p == color):
            mosaic[dr::ph, dc::pw] = lin16[dr::ph, dc::pw, color]
    return {"mosaic": mosaic, "neutral": neutral, "cm1": cm1, "reduction": reduction,
            "linearization": lut,
            "clip_neg": clip_neg, "clip_over": clip_over, "black": black,
            "white": white, "pattern": tuple(pattern), "dims": tuple(dims)}


# ------------------------------------------------------------------ IFD 编码
def _enc(typ, val):
    if typ == T_ASCII:
        b = (val.encode("utf-8") if isinstance(val, str) else bytes(val))
        if not b.endswith(b"\x00"):
            b += b"\x00"
        return b, len(b)
    if typ in (T_BYTE, T_UNDEFINED):
        b = bytes(bytearray(val))
        return b + b"\x00" * ((-len(b)) % 2), len(b)
    vs = val if isinstance(val, (tuple, list)) else (val,)
    if typ == T_SHORT:
        return b"".join(struct.pack("<H", int(v)) for v in vs), len(vs)
    if typ == T_LONG:
        return b"".join(struct.pack("<I", int(v)) for v in vs), len(vs)
    if typ == T_SLONG:
        return b"".join(struct.pack("<i", int(v)) for v in vs), len(vs)
    if typ in (T_RATIONAL, T_SRATIONAL):
        fl = [Fraction(float(v)).limit_denominator(100000) for v in vs]
        pack = "<II" if typ == T_RATIONAL else "<ii"
        return b"".join(struct.pack(pack, f.numerator, f.denominator) for f in fl), len(fl)
    raise ValueError(f"未知类型 {typ}")


class IfdWriter:
    """把「一堆标签 + 一块像素区」编成一段 TIFF IFD（小端、按标签升序）。"""

    def __init__(self):
        self.entries: list[tuple[int, int, bytes, int]] = []

    def put(self, tag: int, typ: int, val) -> "IfdWriter":
        raw, count = _enc(typ, val)
        self.entries.append((tag, typ, raw, count))
        return self

    def bytes_for(self, base: int, patch: dict | None = None) -> tuple[bytes, bytes, int]:
        """返回 (IFD 字节, 溢出值字节, 占用总长)。`patch` 把某个标签的值换成新值
        （只用于 SubIFD 偏移那种「先占位、算完长度再回填」的情况：项数不变，
        所以溢出区的偏移不会抖）。"""
        entries = []
        for tag, typ, raw, count in self.entries:
            if patch and tag in patch:
                raw, count = _enc(typ, patch[tag])
            entries.append((tag, typ, raw, count))
        entries.sort(key=lambda e: e[0])
        n = len(entries)
        here = base + 2 + 12 * n + 4
        body = bytearray()
        rows = bytearray(struct.pack("<H", n))
        for tag, typ, raw, count in entries:
            if len(raw) <= 4:
                field = raw + b"\x00" * (4 - len(raw))
            else:
                here += len(body) % 2
                field = struct.pack("<I", here)
                body += raw + b"\x00" * ((-len(raw)) % 2)
                here += len(raw) + ((-len(raw)) % 2)
            rows += struct.pack("<HHI4s", tag, typ, count, field)
        rows += struct.pack("<I", 0)
        return bytes(rows), bytes(body), here - base


def build(path: str, rgb_u8: np.ndarray, *, pattern=(0, 1, 1, 2), dims=(2, 2),
          cm1=DEFAULT_CM1, cm2=None, neutral=None, black=256.0, white=16383.0,
          orientation=1, tiles=False, compress=1, predictor=1, preview=None,
          rows_per_strip=64, tile=128, active_area=True, crop=None,
          linearization=None, cfa=True, analog=None, nonlinear=None,
          camera="LumaRetouch TestCam 1.0", baseline_exposure=0.0,
          cfa_layout=1) -> dict:
    """写一张 DNG，返回生成时用的参数（判据脚本拿去算期望值）。

    `preview` 给一张 uint8 RGB 就会挂一个 SubIFD 的 JPEG 预览——用来验证「有预览也不
    许拿预览当代理」这条不变量，不是为了让读侧抄近路。
    """
    fwd = rgb_to_mosaic(rgb_u8, pattern=pattern, dims=dims, cm1=cm1, neutral=neutral,
                        black=black, white=white, nonlinear=nonlinear)
    if fwd["linearization"] is not None:
        linearization = fwd["linearization"]      # 非线性存值必须与表同进退
    mosaic = fwd["mosaic"]
    h, w = mosaic.shape
    n_planes = int(max(pattern)) + 1 if cfa else 3
    reduction = fwd["reduction"]
    header_len = 8
    tags = IfdWriter()

    # 像素区：先按瓦片/条带切成块（记住每块的行宽，Predictor 2 按行差分要用），
    # 再按需做水平差分，最后逐块 Deflate——逐块而不是整幅一个流，是为了让
    # StripOffsets/ByteCounts 与块一一对应（整幅单流就得改 RowsPerStrip，两套语义混在
    # 一个开关里，下一轮改压缩时必错）
    blocks: list[bytes] = []
    row_samples: list[int] = []
    if tiles:
        tw = th = int(tile)
        cols, rows = int(np.ceil(w / tw)), int(np.ceil(h / th))
        for i in range(rows * cols):
            ry, rx = divmod(i, cols)
            blk = np.zeros((th, tw), dtype=np.uint16)
            sub = mosaic[ry * th:min(h, (ry + 1) * th), rx * tw:min(w, (rx + 1) * tw)]
            blk[:sub.shape[0], :sub.shape[1]] = sub
            blocks.append(blk)
            row_samples.append(tw)
    else:
        for y in range(0, h, rows_per_strip):
            sub = np.ascontiguousarray(mosaic[y:y + rows_per_strip])
            blocks.append(sub)
            row_samples.append(w)
    if predictor == 2:
        diffed = []
        for blk, rs in zip(blocks, row_samples):
            a = blk.reshape(-1, rs)
            out = a.copy()
            out[:, 1:] = (a[:, 1:].astype(np.uint32) - a[:, :-1].astype(np.uint32) \
                          ).astype(np.uint16)
            diffed.append(out.reshape(blk.shape))
        blocks = diffed
    if compress in (8, 32941):
        # DNG 码 8（Adobe Deflate）按规范写带 zlib 头的 RFC1950 流，32941/PKZIP 那一路
        # 写裸 deflate。之前 code 8 也写成裸流，只与我们自己读侧互为镜像，第三方
        # 解码器（LibRaw/magick）一律报 corrupted——按规范写才能拿到真第三方证据（#11）。
        wbits = 15 if compress == 8 else -15
        packed = []
        for blk in blocks:
            c = zlib.compressobj(6, zlib.DEFLATED, wbits)
            packed.append(c.compress(np.asarray(blk, dtype="<u2").tobytes()) + c.flush())
        blocks = packed
        n_blocks_note = "单流"
    else:
        packed = [np.asarray(b, dtype="<u2").tobytes() for b in blocks]
        blocks = packed
    if compress in (8, 32941) and tiles:
        raise ValueError("写侧的逐块压缩只配条带；瓦片请按 compress=1 生成")
    block_counts = [len(b) for b in blocks]
    total_pix = sum(block_counts)
    data_start = header_len
    pixel_end = data_start + total_pix + (total_pix % 2)
    ifd_off = pixel_end
    block_offsets = [data_start + sum(block_counts[:i]) for i in range(len(block_counts))]
    out = bytearray(b"II" + struct.pack("<HI", 42, ifd_off))
    for b in blocks:
        out += b
    if len(out) % 2:
        out += b"\x00"
    assert len(out) == ifd_off, f"IFD 偏移漂移：{len(out)} vs {ifd_off}"

    tags.put(TAGS["width"], T_LONG, (w,)).put(TAGS["length"], T_LONG, (h,))
    tags.put(TAGS["bps"], T_SHORT, (16,)).put(TAGS["compression"], T_SHORT, (compress,))
    tags.put(TAGS["photometric"], T_SHORT, (32803 if cfa else 34892))
    tags.put(TAGS["make"], T_ASCII, "LumaRetouch")
    tags.put(TAGS["model"], T_ASCII, "TestCam")
    tags.put(TAGS["orientation"], T_SHORT, (orientation,))
    tags.put(TAGS["spp"], T_SHORT, (1 if cfa else n_planes))
    if tiles:
        tags.put(TAGS["tile_w"], T_LONG, (int(tile),)).put(TAGS["tile_h"], T_LONG, (int(tile),))
        tags.put(TAGS["tile_offsets"], T_LONG, tuple(block_offsets))
        tags.put(TAGS["tile_counts"], T_LONG, tuple(block_counts))
    else:
        tags.put(TAGS["rows_per_strip"], T_LONG, (rows_per_strip,))
        tags.put(TAGS["strip_offsets"], T_LONG, tuple(block_offsets))
        tags.put(TAGS["strip_counts"], T_LONG, tuple(block_counts))
    tags.put(TAGS["planar"], T_SHORT, (1,))
    tags.put(TAGS["predictor"], T_SHORT, (predictor,))
    tags.put(TAGS["sample_format"], T_SHORT, (1,))
    if cfa:
        tags.put(TAGS["cfa_dim"], T_SHORT, tuple(dims))
        tags.put(TAGS["cfa_pattern"], T_BYTE, tuple(pattern))
        if n_planes > 3:
            # 四色必须同时给 ColorPlanes / CFAPlaneColor / ReductionMatrix，并且
            # ColorMatrix1 得摊成 n×3——少一个就是一个“看着能读、其实读错”的文件
            tags.put(TAGS["color_planes"], T_SHORT, (n_planes,))
            tags.put(TAGS["cfa_plane_color"], T_BYTE, (0, 1, 2, 3))
            tags.put(TAGS["rm1"], T_SRATIONAL,
                     list(np.asarray(reduction, dtype=float).reshape(-1)))
    tags.put(TAGS["dng_version"], T_BYTE, (1, 4, 0, 0))
    tags.put(TAGS["dng_backward"], T_BYTE, (1, 1, 0, 0))
    tags.put(TAGS["unique_model"], T_ASCII, camera)
    tags.put(TAGS["cfa_layout"], T_SHORT, (cfa_layout,))
    br = bc = 2 if cfa and dims == (2, 2) else 1
    tags.put(TAGS["black_repeat"], T_SHORT, (br, bc))
    tags.put(TAGS["black"], T_RATIONAL, [black] * (br * bc))
    tags.put(TAGS["white"], T_LONG, (white,))
    if active_area:
        tags.put(TAGS["active_area"], T_LONG, (0, 0, h, w))   # Top,Left,Bottom,Right
    if crop:
        tags.put(TAGS["crop_origin"], T_LONG, crop[:2])
        tags.put(TAGS["crop_size"], T_LONG, crop[2:])
    if linearization is not None:
        tags.put(TAGS["linearization"], T_SHORT, tuple(int(v) for v in linearization))
    tags.put(TAGS["cm1"], T_SRATIONAL,
             list(_pad_rows(np.asarray(cm1, dtype=float), n_planes).reshape(-1)))
    if cm2 is not None:
        tags.put(TAGS["cm2"], T_SRATIONAL,
                 list(_pad_rows(np.asarray(cm2, dtype=float), n_planes).reshape(-1)))
        tags.put(TAGS["illum2"], T_SHORT, (17,))
    tags.put(TAGS["illum1"], T_SHORT, (32,))                  # D50
    tags.put(TAGS["analog"], T_RATIONAL, list(analog if analog is not None
                                              else [1.0] * n_planes))
    tags.put(TAGS["neutral"], T_RATIONAL, list(np.asarray(fwd["neutral"], dtype=float)))
    tags.put(TAGS["baseline_exposure"], T_SRATIONAL, (baseline_exposure,))
    if preview is not None:
        # 先挂一个占位的 SubIFDs 把 IFD0 的项数定下来：回填时只改值不改项数，
        # 溢出区的偏移因此不会抖（抖了就等于整个文件的偏移全错）
        tags.put(TAGS["sub_ifds"], T_LONG, (0,))
    ifd_bytes, body_bytes, _ = tags.bytes_for(ifd_off)
    tail = b""
    if preview is not None:
        blob = preview if isinstance(preview, bytes) else _jpeg_bytes(preview)
        pw, ph = _jpeg_size(blob)
        # 预览的 JPEG 数据紧跟 IFD0 之后；SubIFD 的**结构**在 JPEG 之后。
        # IFD0.SubIFDs 指针必须指结构，而不是指 JPEG 数据——指错了 _read_ifd_at 会把
        # JPEG 的头两字节当成「项数」读出一个荒谬的 IFD（本处曾就是这么埋的雷）。
        blob_off = ifd_off + len(ifd_bytes) + len(body_bytes)
        blob_off += blob_off % 2
        ifd0_pad = blob_off - (ifd_off + len(ifd_bytes) + len(body_bytes))
        assert ifd0_pad in (0, 1), "IFD0 末尾对齐字节超预期"
        sub_off = blob_off + len(blob) + (len(blob) % 2)
        st = IfdWriter()
        st.put(TAGS["new_subfile"], T_LONG, (1,))            # 1 = 缩小分辨率的预览
        st.put(TAGS["width"], T_LONG, (pw,))
        st.put(TAGS["length"], T_LONG, (ph,))
        st.put(TAGS["bps"], T_SHORT, (8, 8, 8))
        st.put(TAGS["compression"], T_SHORT, (6,))           # baseline JPEG
        st.put(TAGS["photometric"], T_SHORT, (6,))           # YCbCr
        st.put(TAGS["strip_offsets"], T_LONG, (blob_off,))    # 预览字节在 blob_off
        st.put(TAGS["rows_per_strip"], T_LONG, (ph,))
        st.put(TAGS["strip_counts"], T_LONG, (len(blob),))
        st.put(TAGS["planar"], T_SHORT, (1,))
        st.put(TAGS["preview_color_space"], T_LONG, (2,))    # sRGB
        # base 用结构真正的位置 sub_off：溢出值区要紧跟结构，偏移才算得对
        sub_bytes, sub_body, _ = st.bytes_for(sub_off)
        ifd_bytes, body_bytes, _ = tags.bytes_for(ifd_off, patch={TAGS["sub_ifds"]: (sub_off,)})
        tail = b"\x00" * ifd0_pad + blob + b"\x00" * (len(blob) % 2) + sub_bytes + sub_body
    with open(path, "wb") as f:
        f.write(bytes(out))
        f.write(ifd_bytes)
        f.write(body_bytes)
        f.write(tail)
    return {"path": path, "mosaic": mosaic, "neutral": fwd["neutral"],
            "clip_neg": fwd["clip_neg"], "clip_over": fwd["clip_over"],
            "black": black, "white": white, "pattern": tuple(pattern),
            "dims": tuple(dims), "cm1": cm1, "reduction": reduction,
            "linearization": linearization is not None,
            "size": (w, h), "bytes": os.path.getsize(path),
            "blocks": len(block_counts), "preview": preview is not None}


def _pad_rows(mat: np.ndarray, n: int) -> np.ndarray:
    """ColorMatrix 要摊成 n×3：三色矩阵遇到四色排阵时，多的那一行给 0。"""
    mat = np.asarray(mat, dtype=np.float64)
    if mat.shape[0] == n or n <= 3:
        return mat
    out = np.zeros((n, mat.shape[1]))
    out[:mat.shape[0]] = mat
    return out


def _jpeg_size(blob: bytes) -> tuple[int, int]:
    """从 JPEG 的 SOF 段读出预览尺寸（不靠 Pillow 猜，免得把写侧的正确性绑在库里）。"""
    i = 2
    while i < len(blob) - 9:
        if blob[i] != 0xFF:
            i += 1
            continue
        marker = blob[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB,
                      0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", blob[i + 5:i + 9])
            return int(w), int(h)
        seg = struct.unpack(">H", blob[i + 2:i + 4])[0] if marker not in (0xD8, 0x01) else 0
        i += 2 + seg
    raise ValueError("预览不是 JPEG（找不到 SOF 段）")


def _jpeg_bytes(rgb_u8: np.ndarray) -> bytes:
    import io
    buf = io.BytesIO()
    Image.fromarray(rgb_u8).save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="src", required=True, help="已知的 RGB 源图")
    ap.add_argument("--out", required=True, help="写出的 .dng 路径")
    ap.add_argument("--edge", type=int, default=384, help="源图裁出的长边")
    args = ap.parse_args()
    im = np.asarray(Image.open(args.src).convert("RGB"))
    h, w = im.shape[:2]
    im = im[h // 4:h // 4 + args.edge * 2 // 3, w // 4:w // 4 + args.edge]
    info = build(args.out, im)
    print(f"写出 {args.out}：{info['size'][0]}×{info['size'][1]} {info['bytes']} 字节，"
          f"裁剪 负向 {info['clip_neg'] * 100:.2f}% 过曝 {info['clip_over'] * 100:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
