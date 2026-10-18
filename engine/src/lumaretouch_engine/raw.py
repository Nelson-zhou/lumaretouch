"""DNG 读侧：自己解析 TIFF/EP 容器，按公开规范做线性化与色彩变换。

为什么这一层自研而不把 LibRaw 放进基线（两件分开的事）：
* 计划里 RAW 的选型是 LibRaw（LGPL/CDDL 双许可、动态链接），但它的**许可问题还没
  裁完**：pip 上的 rawpy 把 LibRaw 静态链进 wheel，而静态链接的 LGPL 义务与动态链接
  不是同一回事。所以 LibRaw 走 `engine/requirements-libraw.txt` 那条可选插件通道
  （与 mediapipe 同构），基线里只留零第三方代码的通路。
* DNG 是**公开规范**：容器结构、标签号、第 5/6 章的加工模型都是公开事实。未压缩与
  Deflate 的线性数据不需要任何第三方解码器就能读——这一块自研是干净的，也是今晚能
  拿出证据的那一块。
* 覆盖不到的（lossless JPEG 编码的 CR2/NEF/ARW、packed 10/12/14-bit、float RAW、
  BigTIFF）一律 `UnsupportedRaw` 说清卡在哪个字段、出路是什么。静默换成别的渲染就
  是把"用真解码器解出来的图"写成假证据。

规范里三个坑都在这个文件里踩过，注释跟着写：
1. **ActiveArea 的分量顺序是 Top, Left, Bottom, Right**（不是常见的左上下右）。写反
   就报出一个比画面还高的有效区，第三方实现照着它读会冲到文件尾后面（LibRaw 的
   unpack 直接报 Unexpected end of file）。
2. **ColorMatrix 的方向是 XYZ → 相机**，所以相机 → XYZ 要乘逆矩阵；而曝光归一因子是
   「那块 as-shot 白的 Y」，不是「再除一次 AsShotNeutral」。搞错的表现是一个通道整片
   被裁到 0，而相关性还有 0.95——只有逐通道均值守得住。
3. **少一次 sRGB 编码**（把 scene-linear 当显示值用）整张图暗一档：真图往返 mean|Δ|
   从 4.1 LSB 变成 75.9 LSB。
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

# ---------------------------------------------------------------- 光度与压缩码
PHOTOMETRIC_BLACK_IS_ZERO, PHOTOMETRIC_RGB, PHOTOMETRIC_YCBCR = 1, 2, 6
PHOTOMETRIC_CFA, PHOTOMETRIC_LINEAR_RAW = 32803, 34892
COMPRESSION_NONE, COMPRESSION_BASELINE_JPEG, COMPRESSION_DEFLATE = 1, 6, 8
COMPRESSION_JPEG, COMPRESSION_LOSSY_JPEG, COMPRESSION_PKZIP_DEFLATE = 7, 34892, 32941
SUPPORTED_COMPRESSION = (COMPRESSION_NONE, COMPRESSION_DEFLATE, COMPRESSION_PKZIP_DEFLATE)

# ---------------------------------------------------------------- 标签号（公开事实）
TAG_NEW_SUBFILE_TYPE, TAG_IMAGE_WIDTH, TAG_IMAGE_LENGTH = 0x00FE, 0x0100, 0x0101
TAG_BITS_PER_SAMPLE, TAG_COMPRESSION, TAG_PHOTOMETRIC = 0x0102, 0x0103, 0x0106
TAG_MAKE, TAG_MODEL = 0x010F, 0x0110
TAG_STRIP_OFFSETS, TAG_ORIENTATION = 0x0111, 0x0112
TAG_SAMPLES_PER_PIXEL, TAG_ROWS_PER_STRIP = 0x0115, 0x0116
TAG_STRIP_BYTE_COUNTS, TAG_PLANAR_CONFIG = 0x0117, 0x011C
TAG_PREDICTOR, TAG_TILE_WIDTH, TAG_TILE_LENGTH = 0x013D, 0x0142, 0x0143
TAG_TILE_OFFSETS, TAG_TILE_BYTE_COUNTS = 0x0144, 0x0145
TAG_SUB_IFDS, TAG_SAMPLE_FORMAT = 0x014A, 0x0153
TAG_CFA_REPEAT_PATTERN_DIM, TAG_CFA_PATTERN = 0x828D, 0x828E
TAG_DNG_VERSION, TAG_DNG_BACKWARD_VERSION = 0xC612, 0xC613
TAG_UNIQUE_CAMERA_MODEL, TAG_COLOR_PLANES = 0xC614, 0xC615
TAG_CFA_PLANE_COLOR, TAG_CFA_LAYOUT = 0xC616, 0xC617
TAG_LINEARIZATION_TABLE, TAG_BLACK_LEVEL_REPEAT_DIM = 0xC618, 0xC619
TAG_BLACK_LEVEL, TAG_BLACK_LEVEL_DELTA_H = 0xC61A, 0xC61B
TAG_BLACK_LEVEL_DELTA_V, TAG_WHITE_LEVEL = 0xC61C, 0xC61D
TAG_DEFAULT_CROP_ORIGIN, TAG_DEFAULT_CROP_SIZE = 0xC61F, 0xC620
TAG_COLOR_MATRIX1, TAG_COLOR_MATRIX2 = 0xC621, 0xC622
TAG_CAMERA_CALIBRATION1, TAG_CAMERA_CALIBRATION2 = 0xC623, 0xC624
TAG_REDUCTION_MATRIX1, TAG_REDUCTION_MATRIX2 = 0xC625, 0xC626
TAG_ANALOG_BALANCE, TAG_ASSHOT_NEUTRAL = 0xC627, 0xC628
TAG_ASSHOT_WHITE_XY, TAG_BASELINE_EXPOSURE = 0xC629, 0xC62A
TAG_CALIBRATION_ILLUMINANT1, TAG_CALIBRATION_ILLUMINANT2 = 0xC65A, 0xC65B
TAG_ACTIVE_AREA = 0xC68D
TAG_FORWARD_MATRIX1, TAG_FORWARD_MATRIX2 = 0xC714, 0xC715

# EXIF LightSource 号 → CIE 标准照明体 XYZ（Y 归一）。ColorMatrix1/2 各自绑定一个
# 校准照明体，两份之间按倒数色温线性插值，所以这里既要有号也要有值。
ILLUMINANT_XYZ = {
    17: (1.098466, 1.0, 0.355823),      # Standard A
    18: (0.990928, 1.0, 0.592921),      # Standard B
    19: (0.980705, 1.0, 0.719358),      # Standard C
    20: (0.956827, 1.0, 0.921397),      # D55
    21: (0.950470, 1.0, 1.088830),      # D65
    22: (0.949726, 1.0, 1.226381),      # D75
    23: (0.992085, 1.0, 0.640956),      # F2
    24: (0.968558, 1.0, 0.785328),      # F4
    25: (0.955849, 1.0, 0.885905),      # F5
    26: (0.948418, 1.0, 0.954471),      # F6
    27: (0.948384, 1.0, 1.002073),      # F7
    28: (0.940040, 1.0, 1.048358),      # F8
    29: (0.940005, 1.0, 1.067895),      # F9
    30: (0.926774, 1.0, 1.133099),      # F11
    31: (0.927553, 1.0, 1.146753),      # F12
    32: (0.964220, 1.0, 0.824890),      # D50
}
XYZ_D50 = np.array(ILLUMINANT_XYZ[32])
XYZ_D65 = np.array(ILLUMINANT_XYZ[21])
XYZ_TO_SRGB = np.array([[3.2407091, -1.5372984, -0.4986282],
                        [-0.9692581, 1.8759676, 0.0415561],
                        [0.0556340, -0.2039118, 1.0572660]])
SRGB_TO_XYZ = np.linalg.inv(XYZ_TO_SRGB)
BRADFORD = np.array([[0.8951000, 0.7502000, 0.0380000],
                     [-0.7502000, 1.0126000, 0.0609000],
                     [0.0380000, -0.0609000, 0.1111000]])
SWAPPED_ORIENTATIONS = {5, 6, 7, 8}

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


class UnsupportedRaw(RuntimeError):
    """这一版解不了这张 RAW。`what` 说清卡在哪个字段，`hint` 给出路。"""

    def __init__(self, what: str, hint: str = ""):
        self.what = what
        self.hint = hint
        super().__init__(what + (f"（出路：{hint}）" if hint else ""))


# ------------------------------------------------------------------ IFD 容器
@dataclass
class Ifd:
    """一个 IFD：tag → (类型, 值元组)。值一律按元组存，标量也 for 得动。"""
    pos: int
    bo: str
    tags: dict

    def has(self, tag: int) -> bool:
        return tag in self.tags

    def vals(self, tag: int) -> tuple | None:
        got = self.tags.get(tag)
        return None if got is None else got[1]

    def scalar(self, tag: int, default=None):
        v = self.vals(tag)
        if not v:
            return default
        return v[0]

    def as_int(self, tag: int, default: int = 0) -> int:
        v = self.scalar(tag, None)
        return default if v is None else int(v)

    def as_floats(self, tag: int) -> np.ndarray:
        v = self.vals(tag)
        if not v:
            return np.zeros(0, dtype=np.float64)
        return np.array([float(x) if isinstance(x, Fraction) else x for x in v],
                        dtype=np.float64)

    def text(self, tag: int) -> str:
        v = self.scalar(tag, "")
        return str(v)


def _decode_value(bo: str, typ: int, count: int, raw: bytes):
    if typ == 2:                                 # ASCII（含结尾 NUL）
        return (raw.split(b"\x00")[0].decode("utf-8", "replace"),)
    if typ in (1, 7):                            # BYTE / UNDEFINED
        return tuple(raw[:count])
    if typ == 3:
        return struct.unpack(bo + "H" * count, raw[:2 * count])
    if typ == 4:
        return struct.unpack(bo + "I" * count, raw[:4 * count])
    if typ == 9:
        return struct.unpack(bo + "i" * count, raw[:4 * count])
    if typ in (5, 10):                           # RATIONAL / SRATIONAL
        s = "I" if typ == 5 else "i"             # RATIONAL 分子无符号，SRATIONAL 有
        out = []
        for i in range(count):
            num, den = struct.unpack(bo + s + "I", raw[8 * i:8 * i + 8])
            out.append(Fraction(int(num), int(den)) if den else Fraction(0))
        return tuple(out)
    raise UnsupportedRaw(f"标签类型 {typ} 不认识")


def _read_ifd_at(buf: bytes, off: int, bo: str) -> Ifd:
    """读一个 IFD（含越界与截断检查）。溢出值区按偏移从 buf 里取。"""
    if off + 2 > len(buf):
        raise UnsupportedRaw("IFD 偏移越界（文件被截断）")
    n = struct.unpack(bo + "H", buf[off:off + 2])[0]
    if off + 2 + 12 * n + 4 > len(buf):
        raise UnsupportedRaw(f"IFD 声明 {n} 项，文件里没有那么多字节")
    tags = {}
    for i in range(n):
        e = buf[off + 2 + 12 * i: off + 2 + 12 * i + 12]
        tag, typ, count = struct.unpack(bo + "HHI", e[:8])
        size = TYPE_SIZE.get(typ, 0) * count
        if typ not in TYPE_SIZE:
            continue                             # 不认识的类型：留着别的标签能用
        if size > 4:
            p = struct.unpack(bo + "I", e[8:12])[0]
            if p + size > len(buf):
                raise UnsupportedRaw(f"标签 0x{tag:04X} 的值区越界")
            raw = buf[p:p + size]
        else:
            raw = e[8:8 + max(size, 1)]
        tags[tag] = (typ, _decode_value(bo, typ, count, raw))
    return Ifd(pos=off, bo=bo, tags=tags)


def parse_tiff(buf: bytes) -> list[Ifd]:
    """classic TIFF 头 + IFD 链（SubIFD 由 all_ifds 展开）。"""
    if len(buf) < 8:
        raise UnsupportedRaw("文件不足 8 字节，不是 TIFF/EP")
    if buf[:2] == b"II":
        bo = "<"
    elif buf[:2] == b"MM":
        bo = ">"
    else:
        raise UnsupportedRaw(f"字节序标记 {buf[:2]!r} 不是 II/MM")
    magic = struct.unpack(bo + "H", buf[2:4])[0]
    if magic != 42:
        raise UnsupportedRaw(f"TIFF magic 是 {magic}：这一版只解 classic TIFF(42)",
                             hint="BigTIFF(43) 多见于超大 DNG 与新版转换器，需 libraw 插件")
    ifds, off, seen = [], struct.unpack(bo + "I", buf[4:8])[0], set()
    while off and off not in seen:
        seen.add(off)
        ifd = _read_ifd_at(buf, off, bo)
        ifds.append(ifd)
        off = _next_ifd(buf, ifd, bo)
    return ifds


def _next_ifd(buf: bytes, ifd: Ifd, bo: str) -> int:
    """下一层 IFD 的偏移：项数按实际写入的条数算（未知类型会被跳过，不能拿 len(tags)）。"""
    n = struct.unpack(bo + "H", buf[ifd.pos:ifd.pos + 2])[0]
    p = ifd.pos + 2 + 12 * n
    return struct.unpack(bo + "I", buf[p:p + 4])[0] if p + 4 <= len(buf) else 0


def all_ifds(buf: bytes) -> list[Ifd]:
    """IFD 链 + 每层的 SubIFDs(330) 展开；去环、限制深度。"""
    bo = "<" if buf[:2] == b"II" else ">"
    roots = parse_tiff(buf)
    out, frontier = list(roots), list(roots)
    seen = {f.pos for f in out}
    while frontier:
        parent = frontier.pop(0)
        for off in (parent.vals(TAG_SUB_IFDS) or ()):
            off = int(off)
            if off in seen:
                continue
            seen.add(off)
            try:
                child = _read_ifd_at(buf, off, bo)
            except UnsupportedRaw:
                continue                  # 深度图/语义掩膜那类枝杈解不开不影响主通路
            out.append(child)
            frontier.append(child)
    return out


def _ifd_skeleton(f, off: int, bo: str):
    """只跳读一个 IFD 的骨架：每项 (tag, typ, count, 4字节值域) + 尾部下一 IFD 偏移。

    不解析溢出值区——嗅探只需要 PhotometricInterpretation（一个内联 SHORT），
    所以在大文件里也只吃几 KB，而不是为了判类型先读下 60 MB。
    """
    f.seek(off)
    hdr = f.read(2)
    if len(hdr) < 2:
        return None
    n = struct.unpack(bo + "H", hdr)[0]
    body = f.read(12 * n + 4)
    if len(body) < 12 * n + 4:
        return None
    entries = []
    for i in range(n):
        e = body[12 * i:12 * i + 12]
        tag, typ, count = struct.unpack(bo + "HHI", e[:8])
        entries.append((tag, typ, count, e[8:12]))
    nxt = struct.unpack(bo + "I", body[12 * n:12 * n + 4])[0]
    return entries, nxt


def _inline_short(bo, typ, count, field):
    # PhotometricInterpretation 规范上是 SHORT(3)，但部分写入器把它存成 LONG(4)；
    # 嗅探要跟读侧 as_int 一样宽容，不然真值在、类型写错的 DNG 会被当坏图（#9）。
    if count == 1 and typ == 3:
        return struct.unpack(bo + "H", field[:2])[0]
    if count == 1 and typ in (4, 9):        # LONG / SLONG
        return struct.unpack(bo + "I", field[:4])[0]
    return None


def _subifd_offsets(f, bo, typ, count, field):
    if typ != 4 or count <= 0:                    # SUB_IFDS 是 LONG 数组
        return []
    if count == 1:                                 # ≤4 字节：内联
        return [struct.unpack(bo + "I", field[:4])[0]]
    p = struct.unpack(bo + "I", field)[0]           # 溢出：值域里是指针
    f.seek(p)
    raw = f.read(4 * count)
    return list(struct.unpack(bo + "I" * count, raw)) if len(raw) >= 4 * count else []


def has_raw_ifd(path: str) -> bool:
    """这是一张含 raw IFD 的 TIFF/EP 吗？只跳读 IFD 骨架，不为判类型吃下整幅。

    为什么不能只读头部：DNG 常把像素放前面、IFD 放文件尾，一张 24 MP 的 DNG 前
    256 KB 里根本没有 IFD——早期嗅探只读头部，就会把大 DNG 当坏图甩给 Pillow。
    """
    import os
    try:
        if not os.path.isfile(path):
            return False
        with open(path, "rb") as f:
            head = f.read(8)
            if len(head) < 8 or head[:2] not in (b"II", b"MM"):
                return False                        # JPEG/PNG/WebP/BMP 在这步就廉价地返 False
            bo = "<" if head[:2] == b"II" else ">"
            magic = struct.unpack(bo + "H", head[2:4])[0]
            if magic == 43:
                return True                         # BigTIFF：交给 load_raw 如实拒绝
            if magic != 42:
                return False
            frontier = [struct.unpack(bo + "I", head[4:8])[0]]
            seen = set()
            while frontier:
                off = frontier.pop(0)
                if not off or off in seen:
                    continue
                seen.add(off)
                sk = _ifd_skeleton(f, off, bo)
                if sk is None:
                    continue
                entries, nxt = sk
                for tag, typ, count, field in entries:
                    if tag == TAG_PHOTOMETRIC:
                        v = _inline_short(bo, typ, count, field)
                        if v in (PHOTOMETRIC_CFA, PHOTOMETRIC_LINEAR_RAW):
                            return True
                    elif tag == TAG_SUB_IFDS:
                        frontier.extend(_subifd_offsets(f, bo, typ, count, field))
                if nxt:
                    frontier.append(nxt)
        return False
    except Exception:
        return False


def pick_raw_ifd(ifds: list[Ifd]) -> Ifd | None:
    """raw IFD：PhotometricInterpretation 为 CFA/LinearRaw 的那个；多个候选取像素最多者。

    取最多而不是取第一个：DNG 允许同一份文件里有全尺寸与缩小分辨率两份 raw，而预览
    另有 pick_preview_ifd 负责，两件事不混。
    """
    cands = [f for f in ifds
             if f.as_int(TAG_PHOTOMETRIC) in (PHOTOMETRIC_CFA, PHOTOMETRIC_LINEAR_RAW)]
    if not cands:
        return None
    return max(cands, key=lambda f: f.as_int(TAG_IMAGE_WIDTH) * f.as_int(TAG_IMAGE_LENGTH))


def pick_preview_ifd(ifds: list[Ifd]) -> Ifd | None:
    """内嵌预览（相机 JPEG 渲染图）：RGB/YCbCr/BlackIsZero。有它就省一次 demosaic。"""
    cands = [f for f in ifds
             if f.as_int(TAG_PHOTOMETRIC) in (PHOTOMETRIC_RGB, PHOTOMETRIC_YCBCR,
                                              PHOTOMETRIC_BLACK_IS_ZERO)
             and f.as_int(TAG_IMAGE_WIDTH) * f.as_int(TAG_IMAGE_LENGTH) > 0]
    if not cands:
        return None
    return max(cands, key=lambda f: f.as_int(TAG_IMAGE_WIDTH) * f.as_int(TAG_IMAGE_LENGTH))


# ------------------------------------------------------------------ 像素抽取
def _check_supported(ifd: Ifd) -> tuple[int, int, int, int, np.dtype]:
    """把基线覆盖不到的组合当场说破，不猜、不静默降质。返回 (w,h,bits,spp,dtype)。"""
    w, h = ifd.as_int(TAG_IMAGE_WIDTH), ifd.as_int(TAG_IMAGE_LENGTH)
    bits = ifd.as_int(TAG_BITS_PER_SAMPLE, 8)
    spp = ifd.as_int(TAG_SAMPLES_PER_PIXEL, 1)
    comp = ifd.as_int(TAG_COMPRESSION, COMPRESSION_NONE)
    fmt = ifd.as_int(TAG_SAMPLE_FORMAT, 1)
    predictor = ifd.as_int(TAG_PREDICTOR, 1)
    if not w or not h:
        raise UnsupportedRaw("ImageWidth/ImageLength 为 0，容器坏了")
    if bits not in (8, 16):
        raise UnsupportedRaw(f"位深 {bits} 不在基线里（只解 8/16）",
                             hint="10/12/14-bit packed 与 float RAW 需 libraw 插件："
                                  "engine/requirements-libraw.txt")
    if fmt != 1:
        raise UnsupportedRaw(f"SampleFormat {fmt} 不在基线里（1=无符号整数）",
                             hint="float RAW 属 DNG 1.4+，需插件")
    if comp not in SUPPORTED_COMPRESSION:
        if comp in (COMPRESSION_BASELINE_JPEG, COMPRESSION_JPEG, COMPRESSION_LOSSY_JPEG):
            raise UnsupportedRaw(
                f"压缩码 {comp}：JPEG（含 lossless JPEG）编码的 RAW，也就是 CR2/NEF/ARW "
                "与 Adobe 转换器默认压缩那一路",
                hint="需要 libraw 可选插件：engine/requirements-libraw.txt")
        raise UnsupportedRaw(f"压缩码 {comp} 不在基线里（1=未压缩、8/32941=Deflate）")
    if predictor not in (1, 2):
        raise UnsupportedRaw(f"Predictor {predictor} 不在基线里（1=无、2=水平差分）",
                             hint="3=浮点预测器、34892/34893=X2/X4 差分，多见于新版转换器")
    return w, h, bits, spp, np.dtype(f"{ifd.bo}u{bits // 8}")


def _decode_block(buf: bytes, ifd: Ifd, offset: int, count: int, bits: int,
                  row_samples: int, predictor: int, cap_samples: int) -> np.ndarray:
    """一块（条带或瓦片）→ 二维样本数组，压缩与预测器都在这里还原。

    `cap_samples` 是这一块“最多应有多少个样本”（读侧按行宽×声明行数算，给边缘块留一份）：
    解压必须拿它当上限——不然几 KB 的畸形 Deflate 流能炸出任意大的内存（Pillow 那条路
    靠 MAX_IMAGE_PIXELS 拦解压炸弹，RAW 分支自己得拦）。
    """
    if offset < 0 or count < 0:
        raise UnsupportedRaw(f"条带/瓦片偏移为负（offset={offset}, count={count}）：容器坏了")
    chunk = buf[offset:offset + count]
    if len(chunk) < count:
        raise UnsupportedRaw("条带/瓦片偏移越界（文件截断）")
    comp = ifd.as_int(TAG_COMPRESSION, COMPRESSION_NONE)
    item = bits // 8
    if comp == COMPRESSION_NONE:
        data = chunk
    else:
        max_bytes = max(cap_samples, 1) * item
        # DNG 码 8（Adobe Deflate）规范上是带 zlib 头的 RFC1950 流；旧的 32941/PKZIP 一路
        # 常写成裸 deflate（无头）。之前读写都按裸 deflate 互为镜像，自产自读能过、
        # 却读不进任何第三方写入器（#11）。读侧先按主格式解，失败再退回另一种：
        # code 8 以 zlib 头为主，32941 以裸 deflate 为主。
        order = (15, -15) if comp == COMPRESSION_DEFLATE else (-15, 15)
        err: Exception | None = None
        for wb in order:
            try:
                d = zlib.decompressobj(wb)
                cand = d.decompress(chunk, max_bytes)
            except zlib.error as e:
                err = e
                continue
            if not d.eof and len(cand) >= max_bytes:
                raise UnsupportedRaw(
                    f"Deflate 解压超出块上限（{max_bytes} 字节）：可能是伪造数据")
            data = cand
            break
        else:
            raise UnsupportedRaw(f"Deflate 数据解不开：{err}") from err
    dtype = np.dtype(f"{ifd.bo}u{item}")
    n = len(data) // dtype.itemsize
    if n > cap_samples:
        raise UnsupportedRaw(f"块内 {n} 个样本超过声明上限 {cap_samples}：容器与实际不符")
    a = np.frombuffer(data[:n * dtype.itemsize], dtype=dtype)
    if a.size % row_samples:
        raise UnsupportedRaw(f"块内 {a.size} 个样本不是行宽 {row_samples} 的整数倍")
    a = a.reshape(-1, row_samples)
    if predictor == 2:                    # 水平差分：逐行累加回去，按位宽取模
        wide = np.uint32 if bits == 16 else np.uint16
        a = np.cumsum(a.astype(wide), axis=1, dtype=wide).astype(dtype)
    return a


def read_pixels(buf: bytes, ifd: Ifd) -> np.ndarray:
    """返回 (H, W, S) 整型数组。条带/瓦片、PlanarConfiguration 1/2、8/16-bit 都走这一条。

    planar=1 与 planar=2 的区别只在「块怎么排」：交错时一个块含一行的全部样本，
    按面分块时同一平面先排完再排下一个平面。所以先把**每个平面的块数**算出来
    （交错 = 总块数，分面 = 总块数 ÷ 样本数），网格按每面块数铺，读块时用
    `k = 面序 × 每面块数 + 带序` 回到正确的偏移。早期版本把网格按总块数铺、
    又把 per_plane 取成网格长度，planar=2 时那个自洽校验永远不成立——一个多平面
    线性 RAW（Photometric=LinearRaw、SamplesPerPixel=3）根本读不进来。
    """
    w, h, bits, spp, dtype = _check_supported(ifd)
    predictor = ifd.as_int(TAG_PREDICTOR, 1)
    planar = ifd.as_int(TAG_PLANAR_CONFIG, 1)
    if planar not in (1, 2):
        raise UnsupportedRaw(f"PlanarConfiguration={planar} 不认识（1=逐行交错、2=按面分块）")
    tiled = ifd.has(TAG_TILE_WIDTH)
    # 像素预算对账：畸形的 .dng 会声明一个巨大的 W×H 只为在 canvas 上炸出几 GB 分配
    # （紧接 linearize 的 float64 副本又是 ×4、demosaic 输出再 ×3×8）。未压缩时数据本就
    # 在 buf 里（need≈字节数），Deflate 也就小几倍；拿文件字节数乘一个高比做上限，既能放
    # 下真图又拦住“几百字节的文件报 60000×60000”。Pillow 那条路的 MAX_IMAGE_PIXELS 护不到 RAW。
    need_bytes = h * w * spp * (bits // 8)
    if need_bytes > len(buf) * 64 + (1 << 20):
        raise UnsupportedRaw(f"声明 {w}×{h}×{spp} 需 {need_bytes} 字节，文件只有 "
                             f"{len(buf)} 字节：像素数与文件大小对不上")
    canvas = np.zeros((h, w, spp), dtype=dtype)
    n_planes = spp if planar == 2 else 1
    if tiled:
        tw, th = ifd.as_int(TAG_TILE_WIDTH), ifd.as_int(TAG_TILE_LENGTH)
        cols, rows = int(np.ceil(w / tw)), int(np.ceil(h / th))
        offsets = ifd.vals(TAG_TILE_OFFSETS) or ()
        counts = ifd.vals(TAG_TILE_BYTE_COUNTS) or ()
        per_plane = rows * cols
        expect = per_plane * n_planes
        if len(offsets) != expect or len(counts) != len(offsets):
            raise UnsupportedRaw(f"瓦片数 {len(offsets)} 与 {expect}（网格 {rows}×{cols}"
                                 f"{f'×{spp} 面' if planar == 2 else ''}）不符，"
                                 "或 ByteCounts 对不上")
        # 存的是像素坐标（不是瓦片序号）：下面直接拿去切画布，少乘一次尺寸就是整幅错位
        grid = [(ry * th, rx * tw, min(th, h - ry * th), min(tw, w - rx * tw))
                for i in range(per_plane) for ry, rx in [divmod(i, cols)]]
    else:
        rps = ifd.as_int(TAG_ROWS_PER_STRIP, h) or h
        offsets = ifd.vals(TAG_STRIP_OFFSETS) or ()
        counts = ifd.vals(TAG_STRIP_BYTE_COUNTS) or ()
        if not offsets:
            raise UnsupportedRaw("既没有瓦片也没有条带标签，无法定位像素数据")
        if len(counts) != len(offsets):
            raise UnsupportedRaw(f"StripOffsets {len(offsets)} 项而 StripByteCounts "
                                 f"{len(counts)} 项")
        per_plane = int(np.ceil(h / rps))
        expect = per_plane * n_planes
        if len(offsets) != expect:
            raise UnsupportedRaw(f"条带数 {len(offsets)} 与 {expect}（每面 {per_plane} 条"
                                 f"{f'×{spp} 面' if planar == 2 else ''}）不符")
        grid = [(i * rps, 0, min(rps, h - i * rps), w) for i in range(per_plane)]
    # 块内的行宽：条带是整幅宽 w，瓦片是瓦片宽 tw（边缘瓦片右边填的是补零，不进画布）。
    # 拿裁短后的 bw 当行宽会把整个瓦片网格列错位——写侧要按 tw 存，读侧也必须按 tw 解。
    stride = w if not tiled else ifd.as_int(TAG_TILE_WIDTH)
    row_width_samples = stride * (1 if planar == 2 else spp)
    tile_h = ifd.as_int(TAG_TILE_LENGTH) if tiled else 0
    for i, (y0, x0, bh, bw) in enumerate(grid):
        cap_rows = (tile_h if tiled else bh) or bh
        cap_samples = row_width_samples * cap_rows
        for p in range(spp):
            k = p * per_plane + i if planar == 2 else i
            a = _decode_block(buf, ifd, int(offsets[k]), int(counts[k]), bits,
                              row_width_samples, predictor, cap_samples)
            # 块解出来的行数不得少于声明行数：否则缺的那几行会留在零 canvas 上 = 一圈黑带，
            # 而一个事件也不报——这与“绝不留半截图”的自述直接相违。
            if a.shape[0] < bh:
                raise UnsupportedRaw(f"第 {i} 块只解出 {a.shape[0]} 行，声明要 {bh} 行"
                                     "（数据被截断）")
            take_h = bh
            take_w = min(bw, stride, w - x0)
            if planar == 2:
                canvas[y0:y0 + take_h, x0:x0 + take_w, p] = a[:take_h, :take_w]
            else:
                arr = (a[:take_h].reshape(take_h, stride, spp) if spp > 1
                       else a[:take_h, :stride, None])
                canvas[y0:y0 + take_h, x0:x0 + take_w, :] = arr[:, :take_w, :]
    return canvas


# ------------------------------------------------------------------ 加工模型的字段
@dataclass
class RawMeta:
    w: int = 0
    h: int = 0
    src_w: int = 0                 # raw IFD 的全幅尺寸（裁剪前、摆正前）
    src_h: int = 0
    fmt: str = "DNG"
    camera: str = ""
    make: str = ""
    model: str = ""
    pattern: tuple = (0, 1, 1, 2)
    pattern_dims: tuple = (2, 2)
    cfa_layout: int = 1
    color_planes: int = 3
    bits: int = 16
    black: np.ndarray = field(default_factory=lambda: np.zeros((1, 1)))
    black_delta_h: np.ndarray = field(default_factory=lambda: np.zeros(0))
    black_delta_v: np.ndarray = field(default_factory=lambda: np.zeros(0))
    white: float = 65535.0
    neutral: np.ndarray = field(default_factory=lambda: np.ones(3))
    cm: np.ndarray = field(default_factory=lambda: np.eye(3))
    calibration: np.ndarray = field(default_factory=lambda: np.eye(3))
    analog: np.ndarray = field(default_factory=lambda: np.ones(3))
    reduction: np.ndarray | None = None
    forward: np.ndarray | None = None
    profile_weight: float = 0.0
    linearization: np.ndarray | None = None
    exposure_ev: float = 0.0
    orientation: int = 1
    crop_box: tuple = (0, 0, 0, 0)         # (y0, x0, h, w)；(0,0,0,0) = 不裁
    pattern_phase: tuple = (0, 0)          # 裁片 (0,0) 落在排阵的哪一格 (行, 列)
    used_preview: str = ""
    notes: list = field(default_factory=list)


def _reshape_tag(vals: np.ndarray, n: int, cols: int) -> np.ndarray | None:
    return vals.reshape(n, cols) if vals.size == n * cols else None


def as_shot_xyz(m: RawMeta, xyz_to_cam: np.ndarray) -> np.ndarray:
    """as-shot 白在矩阵空间里的 XYZ（插值权重与不变量断言都用它）。"""
    inv = np.linalg.pinv(xyz_to_cam) if m.color_planes > 3 else np.linalg.inv(xyz_to_cam)
    return inv @ m.neutral


def cct_from_xy(x: float, y: float) -> float:
    """McCamy 近似色温（公开公式）。"""
    n = (x - 0.3320) / (y - 0.1788)
    return 449.0 * n ** 3 + 3525.0 * n ** 2 + 6823.3 * n + 5520.33


def illuminant_cct(illum_id: int) -> float | None:
    xyz = ILLUMINANT_XYZ.get(int(illum_id))
    if xyz is None:
        return None
    total = float(sum(xyz))
    return cct_from_xy(xyz[0] / total, xyz[1] / total)


def blend_two(a: np.ndarray, b: np.ndarray | None, w: float) -> np.ndarray:
    if b is None or b.shape != a.shape:
        return a
    return a * (1.0 - w) + b * w


def build_meta(raw_ifd: Ifd, ifd0: Ifd, n_planes: int | None = None) -> RawMeta:
    """raw IFD + IFD0 合成一份加工模型。

    相机档案类标签（ColorMatrix/ForwardMatrix/AnalogBalance/CameraCalibration/
    AsShotNeutral）按规范写在 **IFD0**，而黑电平/CFA/裁剪类写在 **raw IFD**：两边都
    要读。多份相机档案（ExtraCameraProfiles）不在基线里，只用 IFD0 那一份。
    """
    m = RawMeta()
    m.bits = raw_ifd.as_int(TAG_BITS_PER_SAMPLE, 8)
    spp = raw_ifd.as_int(TAG_SAMPLES_PER_PIXEL, 1)
    m.camera = raw_ifd.text(TAG_UNIQUE_CAMERA_MODEL) or ifd0.text(TAG_UNIQUE_CAMERA_MODEL)
    m.make, m.model = ifd0.text(TAG_MAKE), ifd0.text(TAG_MODEL)
    m.orientation = int(ifd0.scalar(TAG_ORIENTATION, 1) or 1)
    dims = raw_ifd.vals(TAG_CFA_REPEAT_PATTERN_DIM) or (2, 2)
    m.pattern_dims = (int(dims[0]), int(dims[1]))
    m.pattern = tuple(int(v) for v in (raw_ifd.vals(TAG_CFA_PATTERN) or (0, 1, 1, 2)))
    m.cfa_layout = int(raw_ifd.scalar(TAG_CFA_LAYOUT, 1) or 1)
    planes = int(ifd0.scalar(TAG_COLOR_PLANES,
                             raw_ifd.scalar(TAG_COLOR_PLANES, 0) or 0) or 0)
    if planes <= 0:
        # 规范：CFA 图像若没写 ColorPlanes，按 CFAPattern 里出现的不同颜色数推
        planes = max(len(set(m.pattern)), 3) if raw_ifd.has(TAG_CFA_PATTERN) else max(spp, 3)
    m.color_planes = int(n_planes or planes)
    # 入口校验（#8）：畸形的 CFARepeatPatternDim=0 会在算相位时抛 ZeroDivision，
    # CFAPattern 长度与排阵积不符会在 site_map reshape 抛 ValueError。这些必须是
    # UnsupportedRaw（对外语义是“这张 RAW 不支持”，带 hint），不能是裸异常把 load 线程打挂。
    if min(m.pattern_dims) <= 0:
        raise UnsupportedRaw(f"CFARepeatPatternDim={m.pattern_dims} 非法（每维必须 > 0）")
    if raw_ifd.as_int(TAG_PHOTOMETRIC) == PHOTOMETRIC_CFA and raw_ifd.has(TAG_CFA_PATTERN):
        want = m.pattern_dims[0] * m.pattern_dims[1]
        if len(m.pattern) != want:
            raise UnsupportedRaw(f"CFAPattern 有 {len(m.pattern)} 项，排阵 "
                                 f"{m.pattern_dims[0]}×{m.pattern_dims[1]} 应有 {want} 项")
        if any(v < 0 for v in m.pattern):
            raise UnsupportedRaw(f"CFAPattern 含负色索引 {list(m.pattern)}")
        if max(m.pattern) + 1 != m.color_planes:
            raise UnsupportedRaw(f"CFAPattern 最大色索引 {max(m.pattern)}+1 与 ColorPlanes "
                                 f"{m.color_planes} 不符（规范：色平面数 = 最大索引 + 1）")
    n = m.color_planes
    # ---- 黑电平（repeat dim × samples）与逐行逐列的 delta
    br = bc = 1
    if raw_ifd.has(TAG_BLACK_LEVEL_REPEAT_DIM):
        d = raw_ifd.vals(TAG_BLACK_LEVEL_REPEAT_DIM)
        br, bc = int(d[0]), int(d[1])
    bl = raw_ifd.as_floats(TAG_BLACK_LEVEL)
    if bl.size == br * bc * spp and spp > 1:
        m.black = bl.reshape(br, bc, spp)
    elif bl.size == br * bc:
        m.black = bl.reshape(br, bc)
    elif bl.size:
        m.black = bl.reshape(1, -1)
        bc = m.black.shape[1]
    else:
        m.black = np.zeros((1, 1))
    m.black_delta_h = raw_ifd.as_floats(TAG_BLACK_LEVEL_DELTA_H)
    m.black_delta_v = raw_ifd.as_floats(TAG_BLACK_LEVEL_DELTA_V)
    wl = raw_ifd.as_floats(TAG_WHITE_LEVEL)
    m.white = float(wl[0]) if wl.size else float(2 ** m.bits - 1)
    if raw_ifd.has(TAG_LINEARIZATION_TABLE):
        lut = raw_ifd.as_floats(TAG_LINEARIZATION_TABLE)
        m.linearization = lut if lut.size else None
    # ---- 中性值：AsShotNeutral 与 AsShotWhiteXY 互斥
    if ifd0.has(TAG_ASSHOT_NEUTRAL):
        neu = ifd0.as_floats(TAG_ASSHOT_NEUTRAL)
        m.neutral = neu[:n] if neu.size >= n else np.pad(neu, (0, n - neu.size),
                                                         constant_values=1.0)
        m.notes.append(f"AsShotNeutral={np.round(m.neutral, 4).tolist()}")
    ab = ifd0.as_floats(TAG_ANALOG_BALANCE)
    m.analog = ab[:n] if ab.size >= n else np.ones(n)
    # ---- 相机档案：ColorMatrix1(+2) 按倒数色温线性插值（DNG 1.2 起规定）
    cm1 = _reshape_tag(ifd0.as_floats(TAG_COLOR_MATRIX1), n, 3)
    cm2 = _reshape_tag(ifd0.as_floats(TAG_COLOR_MATRIX2), n, 3)
    if cm1 is None:
        raise UnsupportedRaw("缺 ColorMatrix1：非单色的 DNG 必须有它（规范硬性要求）")
    cc1 = _reshape_tag(ifd0.as_floats(TAG_CAMERA_CALIBRATION1), n, n)
    cc2 = _reshape_tag(ifd0.as_floats(TAG_CAMERA_CALIBRATION2), n, n)
    fm1 = _reshape_tag(ifd0.as_floats(TAG_FORWARD_MATRIX1), 3, n)
    fm2 = _reshape_tag(ifd0.as_floats(TAG_FORWARD_MATRIX2), 3, n)
    rm1 = _reshape_tag(ifd0.as_floats(TAG_REDUCTION_MATRIX1), 3, n)
    rm2 = _reshape_tag(ifd0.as_floats(TAG_REDUCTION_MATRIX2), 3, n)
    w = profile_weight(ifd0, m, cm1, cc1, ab)
    m.profile_weight = w
    m.cm = blend_two(cm1, cm2, w)
    m.calibration = blend_two(cc1, cc2, w) if cc1 is not None else np.eye(n)
    if fm1 is not None:
        m.forward = blend_two(fm1, fm2, w)
    if rm1 is not None and n > 3:
        m.reduction = blend_two(rm1, rm2, w)
    elif n > 3:
        raise UnsupportedRaw(f"{n} 色相机却没给 ReductionMatrix，无法降到三色")
    be = ifd0.scalar(TAG_BASELINE_EXPOSURE)
    m.exposure_ev = float(be) if be is not None else 0.0
    # ---- 裁剪：ActiveArea 先框掉光学黑边，DefaultCrop* 再在其内部裁
    full_w = raw_ifd.as_int(TAG_IMAGE_WIDTH)
    full_h = raw_ifd.as_int(TAG_IMAGE_LENGTH)
    x0 = y0 = 0
    rw, rh = full_w, full_h
    aa = raw_ifd.vals(TAG_ACTIVE_AREA)
    if aa and len(aa) == 4:
        top, left, bottom, right = (int(v) for v in aa)
        x0, y0 = max(0, left), max(0, top)
        rw = max(1, min(right, full_w) - x0)
        rh = max(1, min(bottom, full_h) - y0)
    origin = raw_ifd.vals(TAG_DEFAULT_CROP_ORIGIN)
    size = raw_ifd.vals(TAG_DEFAULT_CROP_SIZE)
    if origin and len(origin) == 2:
        ox, oy = int(origin[0]), int(origin[1])
        # 上界钳制：畸形的 DefaultCropOrigin 不能把裁片原点推出有效区，否则
        # crop_pixels 会越界报断言（#6）。原点钉在幅内，尺寸跟着剩余宽度收。
        x0 = min(x0 + ox, max(0, full_w - 1))
        y0 = min(y0 + oy, max(0, full_h - 1))
        rw = max(1, min(rw - ox, full_w - x0))
        rh = max(1, min(rh - oy, full_h - y0))
    if size and len(size) == 2:
        rw = max(1, min(int(size[0]), full_w - x0))
        rh = max(1, min(int(size[1]), full_h - y0))
    m.crop_box = (y0, x0, rh, rw)
    # CFA 排阵原点在全幅 raw 数据的左上角（规范写死），裁片却从 (y0,x0) 起：那裁片的
    # (0,0) 不再是排阵起始色。相位 = 裁片原点相对排阵的偏移，丢它就是红蓝错位
    # （真机量到 mean|Δ| 53、逐通道 ±100 的均值偏移）。
    m.pattern_phase = (y0 % m.pattern_dims[0], x0 % m.pattern_dims[1])
    # 对外报的源尺寸得与 JPEG/Pillow 那一路同口径：取裁片（去掉光学黑边）后的尺寸，
    # 并按 EXIF 方向摆正（5/6/7/8 对调宽高）。写死 full_w×full_h 会把光学黑边算进去，
    # 还会与导出的 im.size 对不上（导出尺寸一致性断言会挂，#10）。
    if m.orientation in (5, 6, 7, 8):
        m.src_w, m.src_h = rh, rw
    else:
        m.src_w, m.src_h = rw, rh
    m.w, m.h = rw, rh
    if (rw, rh) != (full_w, full_h):
        m.notes.append(f"按 ActiveArea/DefaultCrop 裁到 {rw}×{rh}（全幅 {full_w}×{full_h}）")
    if m.cfa_layout != 1:
        raise UnsupportedRaw(f"CFALayout={m.cfa_layout}（交错排阵）不在基线里",
                             hint="富士 SuperCCD 那一类，需 libraw 插件")
    return m


def profile_weight(ifd0: Ifd, m: RawMeta, cm1: np.ndarray, cc1: np.ndarray | None,
                   ab: np.ndarray) -> float:
    """两份相机档案之间的插值权重（规范第 6 章：倒数色温线性插值，越界取最近）。"""
    if not ifd0.has(TAG_COLOR_MATRIX2):
        return 0.0
    t1 = illuminant_cct(ifd0.as_int(TAG_CALIBRATION_ILLUMINANT1, 21))
    t2 = illuminant_cct(ifd0.as_int(TAG_CALIBRATION_ILLUMINANT2, 21))
    if t1 is None or t2 is None or t1 == t2:
        return 0.0
    xyz_to_cam = np.diag(ab) @ (cc1 if cc1 is not None else np.eye(m.color_planes)) @ cm1
    white = as_shot_xyz(m, xyz_to_cam)
    if white.sum() <= 0 or white[1] <= 0:
        return 0.0
    ta = cct_from_xy(white[0] / white.sum(), white[1] / white.sum())
    lo, hi = min(t1, t2), max(t1, t2)
    if lo <= ta <= hi:
        w = (1.0 / ta - 1.0 / t1) / (1.0 / t2 - 1.0 / t1)
        return float(min(1.0, max(0.0, w)))
    return 0.0 if abs(ta - t1) <= abs(ta - t2) else 1.0


# ------------------------------------------------------------------ 第 5 章：raw → 线性参考值
def linearize(pixels: np.ndarray, m: RawMeta) -> np.ndarray:
    """Linearization → 减黑（含 DeltaH/V）→ 按白电平缩放 → 裁剪。返回 float64 [0,1]。

    入参是 read_pixels 的 (H, W, S)；BlackLevel 的计数按规范是 repeat_rows×repeat_cols
    ×SamplesPerPixel，所以它可能是二维（单样本）也可能是三维。
    """
    if pixels.ndim != 3:
        raise UnsupportedRaw(f"像素布局应为 (H,W,S)，得到 {pixels.shape}")
    x = pixels.astype(np.float64)
    if m.linearization is not None and m.linearization.size:
        lut = m.linearization
        x = lut[np.clip(np.rint(x).astype(np.int64), 0, lut.size - 1)]
    h, w, s = x.shape
    y0, x0 = m.crop_box[0], m.crop_box[1]
    black = np.asarray(m.black, dtype=np.float64)
    if black.ndim == 2:
        black = black[:, :, None]
    br, bc, bs = black.shape
    if bs == 1 and s > 1:
        black = np.broadcast_to(black, (br, bc, s))
    elif bs != s:
        raise UnsupportedRaw(f"BlackLevel 有 {bs} 个样本分量，像素却有 {s} 个通道")
    # 黑电平重复图样定义在整幅 raw 的左上角（与 CFA 排阵同一个原点），裁片却从
    # (y0,x0) 起。图样得按裁片原点回移一个相位，DeltaH/V 也从 x0/y0 切起，否则
    # 裁掉光学黑边那一圈后逐列/逐行暗电流偏移会整体错位（#7）。
    off_r, off_c = y0 % br, x0 % bc
    full = np.tile(black, (int(np.ceil((h + off_r) / br)), int(np.ceil((w + off_c) / bc)),
                           int(np.ceil(s / bs))))[off_r:off_r + h, off_c:off_c + w, :s]
    if m.black_delta_h.size >= x0 + w:              # 逐列偏移：按裁片原点切片
        full = full + m.black_delta_h[x0:x0 + w].reshape(1, w, 1)
    if m.black_delta_v.size >= y0 + h:              # 逐行的
        full = full + m.black_delta_v[y0:y0 + h].reshape(h, 1, 1)
    x = x - full
    max_black = float(np.max(np.asarray(m.black)))
    scale = m.white - max_black
    if scale <= 0:
        raise UnsupportedRaw(f"白电平 {m.white} 不高于黑电平 {max_black}，无法归一")
    return np.clip(x / scale, 0.0, 1.0)


def crop_pixels(pixels: np.ndarray, m: RawMeta) -> np.ndarray:
    """按 ActiveArea/DefaultCrop 算出的框裁掉光学黑边与无效像素。"""
    y0, x0, ch, cw = m.crop_box
    if (ch, cw) == (0, 0):
        return pixels
    assert pixels.shape[0] >= y0 + ch and pixels.shape[1] >= x0 + cw, \
        f"裁剪框 {m.crop_box} 超出像素 {pixels.shape[:2]}"
    return pixels[y0:y0 + ch, x0:x0 + cw]


# ------------------------------------------------------------------ 第 6 章：相机色 → XYZ → sRGB
def bradford(src, dst) -> np.ndarray:
    """把 src 白映到 dst 白的色适应矩阵（规范推荐的 linear Bradford）。

    方向不能写反：锥状响应是 `B · XYZ`，所以 XYZ → 缩放 → XYZ 是
    `B⁻¹ · diag(dst/s) · B`。拿 `B · diag · B⁻¹` 去乘，在 src==dst（恒等）时看不出错，
    而 D50→D65 那一步就是非常数缩放——错了就是一个看不出来的色偏。
    不变量由测试钉住：`bradford(src, dst) @ src == src_y · dst`。
    """
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    s = BRADFORD @ (src / src[1])
    d = BRADFORD @ (dst / dst[1])
    return np.linalg.inv(BRADFORD) @ np.diag(d / s) @ BRADFORD


def camera_to_xyz_matrix(m: RawMeta) -> np.ndarray:
    """3×n 的「相机（已白平衡）→ XYZ(D50)」矩阵。

    有 ForwardMatrix 走规范推荐的那条：白平衡在相机坐标里做（`D = diag(1/Reference
    Neutral)`），不去动 XYZ 的色适应；没有就 inv(AB·CC·CM) 再加一次适应。两条都保证
    as-shot 白落回 D50 白，因此互相对得上——测试就钉这个不变量。
    """
    n = m.color_planes
    ab = np.diag(m.analog[:n])
    cc = m.calibration if m.calibration.shape == (n, n) else np.eye(n)
    cm = m.cm if m.cm.shape == (n, 3) else np.eye(n, 3) if n != 3 else np.eye(3)
    ab_cc = ab @ cc
    neutral = m.neutral[:n]
    if m.forward is not None and m.forward.shape == (3, n):
        ref = np.linalg.solve(ab_cc, neutral)
        if np.any(ref <= 0):
            raise UnsupportedRaw("ForwardMatrix 路径下 ReferenceNeutral 出现非正值")
        k = m.forward @ np.diag(1.0 / ref) @ np.linalg.inv(ab_cc)
    else:
        xyz_to_cam = ab_cc @ cm
        if n > 3 and m.reduction is not None:
            # 规范原话：CameraToXYZ = Inverse(RM · XYZtoCamera) · RM。降色不是前置的
            # 独立一步，而是折叠进这个 3×n 矩阵：先单独降到三色再乘 3×n 形状就对不上
            rm = m.reduction if m.reduction.shape == (3, n) else np.eye(3, n)
            k = np.linalg.inv(rm @ xyz_to_cam) @ rm
        elif n > 3:
            k = np.linalg.pinv(xyz_to_cam)
        else:
            k = np.linalg.inv(xyz_to_cam)
    white = k @ neutral
    if white[1] <= 0:
        raise UnsupportedRaw("as-shot 白反解出的 XYZ 的 Y 非正，色矩阵不可用")
    k = k / float(white[1])
    # 色适应的起点是**那块 as-shot 白**（k@neutral），不是 (1,1,1)：只有 ForwardMatrix 分支里
    # 单位向量才被定义为参考白（规范原话）。拿 ones 当白点会多插一次适应，
    # 结果是正向模型大面积撞负值（写侧实测 32.7% 像素为负）。
    return bradford(k @ neutral, XYZ_D50) @ k


def xyz_to_linear_srgb(xyz: np.ndarray) -> np.ndarray:
    """XYZ(D50) → 线性 sRGB(D65)。行向量约定：先适应到 D65，再乘原色矩阵。"""
    return xyz @ (XYZ_TO_SRGB @ bradford(XYZ_D50, XYZ_D65)).T


def srgb_encode(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)


def srgb_decode(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def exposure_scale(ev: float) -> float:
    """BaselineExposure 是 EV 偏移：乘回去就是 2^EV（规范里它是负数表示要加曝光）。"""
    return float(2.0 ** float(ev))


# ------------------------------------------------------------------ 端到端渲染入口
ORIENT_OPS = {
    1: (), 2: ("flip_lr",), 3: ("rot180",), 4: ("flip_tb",),
    5: ("transpose",), 6: ("rot_cw",), 7: ("antitranspose",), 8: ("rot_ccw",),
}


def apply_orientation(img: np.ndarray, code: int) -> np.ndarray:
    """按 EXIF Orientation 摆正（与 decode.load_rgb 用 ImageOps.exif_transpose 同语义）。

    这里自己写而不是交给 Pillow：RAW 那一侧从头到尾不该让 Pillow 碰 mosaic 数据
    （它见到 CFA TIFF 会直接报 UnidentifiedImageError，而摆正的是**渲染完**的 RGB）。
    """
    for op in ORIENT_OPS.get(int(code), ()):
        if op == "flip_lr":
            img = img[:, ::-1]
        elif op == "flip_tb":
            img = img[::-1]
        elif op == "rot180":
            img = img[::-1, ::-1]
        elif op == "rot_cw":
            img = np.rot90(img, -1)
        elif op == "rot_ccw":
            img = np.rot90(img, 1)
        elif op == "transpose":
            img = np.swapaxes(img, 0, 1)
        elif op == "antitranspose":
            img = np.swapaxes(img[::-1, ::-1], 0, 1)
    return np.ascontiguousarray(img)


def _finish_rgb_float(lin_rgb: np.ndarray) -> np.ndarray:
    """scene-linear [0,1] → 显示值 uint8：先裁剪再 sRGB 编码，量化只走 quant 那一个口径。"""
    from .quant import quantize_np
    return quantize_np(srgb_encode(np.clip(lin_rgb, 0.0, 1.0)))


def _target_size(m: RawMeta, budget: int | None) -> tuple[int, int]:
    """代理档目标尺寸。按**摆正后**的宽高算——与 decode.load_rgb 同一条口径，
    否则竖拍的 RAW 会在「解码说的尺寸」和「上屏的尺寸」之间差一次转置。"""
    from .decode import proxy_size
    w, h = (m.h, m.w) if m.orientation in SWAPPED_ORIENTATIONS else (m.w, m.h)
    return proxy_size(w, h, budget) if budget else (w, h)


def _decimate_factor(m: RawMeta, target: tuple[int, int]) -> int:
    """块降采样因子：不超过目标档的最大整数，封顶 8，并**取偶数**。

    偶数不是审美：2×2 的 Bayer 只有按偶数分块时，每个块里的 R/G/B 计数才相同；
    奇数因子会让相邻块的三色配比不同，输出出现周期性色偏条纹——那是解码器造出来的
    条纹，不是照片里的。
    """
    f = int(min(m.h // max(target[1], 1), m.w // max(target[0], 1)))
    f = max(1, min(f, 8))
    if f > 1 and f % 2:
        f -= 1
    return max(f, 1)


def _srgb_encode_t(t):
    """与 srgb_encode 同一条式子的 torch 版（生产路在卡上编码，不回到 CPU 再算）。"""
    import torch
    x = t.clamp(0.0, 1.0)
    return torch.where(x <= 0.0031308, 12.92 * x, 1.055 * torch.pow(x.clamp_min(1e-12), 1.0 / 2.4) - 0.055)


def load_raw(path: str, budget: int | None = None, device: str | None = None,
             reference: bool = False) -> dict:
    """一张 DNG → 可直接上屏/常驻显存的 uint8 RGB + 加工模型字段 + 分段耗时。

    三条路共用同一份数学，只在「谁算」上分叉：
    * 给了 `device`（生产）：整型 mosaic 上传 → 卡上线性化、demosaic、色彩、编码。
    * `reference=True` 或没有设备：numpy float64 参考实现，跑靶与语义对拍用它。
    * 给了 `budget`：先按 f×f 块做**每色均值**降采样（不插值），再补一次 LANCZOS 到
      代理档。不这么做的话，看一张 24 MP 的 RAW 就得先跑一遍全幅 demosaic。

    不用内嵌预览当代理：预览是相机自己的渲染，而导出走我们的链路——预览与出片不同路
    正是 M3-b 修过的那一类缺陷。预览的存在只在 meta.used_preview 里报出来。
    """
    import os
    import time
    if not os.path.isfile(path):
        raise FileNotFoundError(f"RAW 不存在或不是普通文件: {path}")
    ms: dict[str, float] = {}
    t0 = time.perf_counter()
    with open(path, "rb") as f:
        buf = f.read()
    ifds = all_ifds(buf)
    raw_ifd = pick_raw_ifd(ifds)
    if raw_ifd is None:
        raise UnsupportedRaw("这张 TIFF 里没有 CFA/LinearRaw 的 raw IFD",
                             hint="厂商专有容器（CR2/NEF/ARW/RW2/RAF）需 libraw 可选插件："
                                  "engine/requirements-libraw.txt")
    m = build_meta(raw_ifd, ifds[0])
    m.used_preview = "有" if pick_preview_ifd(ifds) is not None else ""
    ms["container_ms"] = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    pixels = crop_pixels(read_pixels(buf, raw_ifd), m)
    ms["pixels_ms"] = (time.perf_counter() - t1) * 1000.0

    is_cfa = raw_ifd.as_int(TAG_PHOTOMETRIC) == PHOTOMETRIC_CFA
    scale_t = camera_to_xyz_matrix(m)
    expo = exposure_scale(m.exposure_ev)
    to_srgb = XYZ_TO_SRGB @ bradford(XYZ_D50, XYZ_D65)
    target = _target_size(m, budget)
    f = _decimate_factor(m, target) if (budget and is_cfa) else 1

    t2 = time.perf_counter()
    if device and not reference:
        rgb = _render_torch(pixels, m, is_cfa, scale_t, expo, to_srgb, device, f)
    else:
        from .ops.demosaic import decimate_np, demosaic_np
        lin = linearize(pixels, m)                        # (H,W,S) float64 [0,1]
        if is_cfa:
            cam = decimate_np(lin, m.pattern, m.pattern_dims, f,
                              phase=m.pattern_phase) if f > 1 else \
                demosaic_np(lin, m.pattern, m.pattern_dims, phase=m.pattern_phase)
        else:
            cam = lin
        # 通道数必须等于色平面数：ColorPlanes 说 4 色而排阵只出 3 色，就是元数据与
        # 像素对不上，往下乘只会乘出一个形状对、内容错的结果
        if cam.shape[-1] != m.color_planes:
            raise UnsupportedRaw(f"demosaic 出了 {cam.shape[-1]} 色，ColorPlanes 却说 "
                                 f"{m.color_planes} 色")
        cam = cam * expo
        xyz = np.clip(cam @ scale_t.T, 0.0, 1.0)
        rgb = _finish_rgb_float(np.clip(xyz @ to_srgb.T, 0.0, 1.0))
    ms["render_ms"] = (time.perf_counter() - t2) * 1000.0

    t3 = time.perf_counter()
    rgb = apply_orientation(rgb, m.orientation)
    if budget and (rgb.shape[1], rgb.shape[0]) != target:
        from PIL import Image
        rgb = np.ascontiguousarray(np.asarray(
            Image.fromarray(rgb).resize(target, Image.LANCZOS)))
    ms["encode_ms"] = (time.perf_counter() - t3) * 1000.0
    ms["total_ms"] = round(sum(ms.values()), 3)
    m.w, m.h = int(rgb.shape[1]), int(rgb.shape[0])
    if m.used_preview:
        m.notes.append("文件里有内嵌预览，但代理帧与导出都走我们自己的渲染（两路同一条链）")
    return {"rgb": rgb, "meta": m, "ms": ms}


def _render_torch(pixels, m: RawMeta, is_cfa: bool, scale_t, expo: float,
                  to_srgb, device: str, f: int) -> np.ndarray:
    """GPU 生产路：与 numpy 参考同一串式子，只是全程 float32 在卡上算、在卡上编码。"""
    import torch

    from .ops.demosaic import decimate_t, demosaic_t
    from .quant import quantize_t

    x = torch.from_numpy(np.ascontiguousarray(pixels)).to(device)   # (H,W,S) 整型
    x = x.to(torch.float32).permute(2, 0, 1)[None]                  # (B,S,H,W)
    if m.linearization is not None and m.linearization.size:
        lut = torch.tensor(np.asarray(m.linearization, dtype=np.float64),
                           dtype=torch.float32, device=device)
        x = lut[torch.clamp(x.round().long(), 0, lut.numel() - 1)]
    black = np.asarray(m.black, dtype=np.float64)
    if black.ndim == 2:
        black = black[:, :, None]
    br, bc, bs = black.shape
    s = int(x.shape[1])
    if bs == 1 and s > 1:
        black = np.broadcast_to(black, (br, bc, s))
    elif bs != s:
        raise UnsupportedRaw(f"BlackLevel 有 {bs} 个样本分量，像素却有 {s} 个通道")
    full = torch.tensor(np.ascontiguousarray(np.transpose(black, (2, 0, 1)))[None],
                        dtype=torch.float32, device=device)          # (1,bs,br,bc)
    full = full.repeat_interleave(int(np.ceil(s / bs)), dim=1) if bs != s else full
    # 与 numpy 参考同相位：黑电平图样按裁片原点 (y0,x0) 回移，DeltaH/V 也从 x0/y0 切。
    y0, x0 = m.crop_box[0], m.crop_box[1]
    Hh, Ww = int(x.shape[2]), int(x.shape[3])
    off_r, off_c = y0 % br, x0 % bc
    full = torch.tile(full, (1, 1, int(np.ceil((Hh + off_r) / br)), int(np.ceil((Ww + off_c) / bc))))
    full = full[:, :s, off_r:off_r + Hh, off_c:off_c + Ww]
    if m.black_delta_h.size >= x0 + Ww:
        full = full + torch.tensor(m.black_delta_h[x0:x0 + Ww], dtype=torch.float32,
                                   device=device).reshape(1, 1, 1, -1)
    if m.black_delta_v.size >= y0 + Hh:
        full = full + torch.tensor(m.black_delta_v[y0:y0 + Hh], dtype=torch.float32,
                                   device=device).reshape(1, 1, -1, 1)
    scale = float(m.white) - float(np.max(np.asarray(m.black)))
    if scale <= 0:
        raise UnsupportedRaw(f"白电平 {m.white} 不高于黑电平，无法归一")
    lin = torch.clamp((x - full) / scale, 0.0, 1.0)
    if is_cfa:
        cam = decimate_t(lin, m.pattern, m.pattern_dims, f,
                         phase=m.pattern_phase) if f > 1 else \
            demosaic_t(lin, m.pattern, m.pattern_dims, phase=m.pattern_phase)
    else:
        cam = lin
    if cam.shape[1] != m.color_planes:
        raise UnsupportedRaw(f"demosaic 出了 {cam.shape[1]} 色，ColorPlanes 却说 "
                             f"{m.color_planes} 色")
    mat = torch.tensor(np.asarray(scale_t, dtype=np.float64), dtype=torch.float32, device=device)
    xyz = torch.einsum("dc,bchw->bdhw", mat, cam * float(expo))
    # 与 numpy 参考同一串式子：先夹 XYZ 到 [0,1] 再进第二段矩阵。少这一步，GPU 会把
    # 负三色分量留着往下乘，saturated 图的真值对拍就会出现 GPU/CPU 分岔（#3）。
    xyz = torch.clamp(xyz, 0.0, 1.0)
    mat2 = torch.tensor(np.asarray(to_srgb, dtype=np.float64), dtype=torch.float32, device=device)
    rgb = torch.clamp(torch.einsum("dc,bchw->bdhw", mat2, xyz), 0.0, 1.0)
    enc = quantize_t(_srgb_encode_t(rgb))
    return enc[0].permute(1, 2, 0).cpu().numpy().astype(np.uint8)


def plugin_installed() -> bool:
    """真解码后端到底在不在。

    这一位曾经只查 `rawpy` 那个 Python 包（只用 find_spec，不 import：基线不许因为
    「探测」而去链接一个 LGPL 库）。但 M9-c 起真解码走的是裸 ctypes 绑系统
    `libraw_r.so.23`，rawpy 从来没装、也不该装——多一个 Python 依赖换不来任何能力。
    于是装机件明明解得开 CR2，ready 却报「插件未装、一律如实拒绝」：往低报也是谎报，
    而且它把 M9-h 刚立的口径在用户面前说反了。现在报的是**那个库加载得到吗**，
    判据来自 ops.libraw 的自检（含偏移表核对），不是某个包名在不在 site-packages 里。
    """
    from .ops import libraw as LR
    return LR.available()


def raw_backends() -> dict:
    """这一版能读什么、读不了什么、出路在哪——由引擎说，前端不刻一份。

    写清「基线只覆盖 DNG 的未压缩线性数据」而不是「支持 RAW」：后者会把
    「解不开一台相机的 CR2」这件事写成已通过。Deflate 单独列一条并标清它只与我们
    自己的编码器自洽——真机量过：系统 LibRaw 读不进我们的条带 Deflate DNG（要瓦片 Deflate，
    而写侧不产），拿它当“已与第三方交叉验证”就是假指标。
    """
    return {
        "baseline": ["DNG（未压缩条带/瓦片，已与系统 LibRaw 交叉验证）"],
        "self_verified_only": ["DNG（Deflate，Predictor 1/2）：我方读侧对地面真值逐字节自洽，"
                                "但未获第三方解码器验证（LibRaw 拒读条带 Deflate）"],
        # ---- M9-h 定稿口径：把"我们验过的"与"依赖别人实现但没样张的"分成两栏 ----
        # 这一条界线是软件诚信的核心：装上门机型录不进库，一句"支持 CR2"就是假指标。
        "suffixes": [".dng"],
        "suffixes_verified": [".dng"],
        "verified_full_chain": [
            "DNG：读侧（自研三臂对拍 + 系统 LibRaw 交叉验证）、写侧（make-test-dng / "
            "make-raw-probe 的地面真值）、内嵌预览通道、16-bit 母档直通导出（落盘逐字节 "
            "0 差异）全部由本仓用例自证"],
        "vendor_suffixes": [".cr2", ".cr3", ".nef", ".arw", ".rw2", ".raf", ".orf"],
        "vendor_status": ("依赖系统 LibRaw 插件的厂商解码；本仓未搭载任何实机样张，"
                          "这些格式的状态是「未经实机样张认证」，不是「已支持」。"
                          "仓库里能验的只有路由与真解码臂那一半（把基线读侧蒙上眼睛后，"
                          "厂商后缀确实交到了 LibRaw 手上）"),
        "sample_certified": {".dng": True, "vendor": False},
        "needs_plugin": ["lossless JPEG 编码的 RAW（DNG 默认压缩、CR2/NEF/ARW/RW2/RAF）",
                         "packed 位深（10/12/14-bit）", "float RAW（DNG 1.4+）",
                         "BigTIFF（magic 43）", "CFALayout≠1 的交错排阵"],
        "plugin": "rawpy（LibRaw，LGPL-2.1/CDDL-1.0 双许可）——"
                  "engine/requirements-libraw.txt，未装则上面那些一律如实拒绝",
        "plugin_installed": plugin_installed(),
    }
