"""真实图 → 预览代理帧：解码 + 按字节预算降采样。

两条从实测里长出来的规矩：
1. **代理档按像素总数定，不按长边定。** 预算决定每帧字节（RGBA 每像素 4 字节），
   构图只改长宽比；按"长边 N"缩会让同一套代码在横竖构图下落进不同的字节区间，
   那是最难查的一类抖动。
2. **降采样在解码侧做，不把全尺寸图灌进显存再缩。** 12 MP 的 RGBA 是 51 MB/帧，shm 与
   D2H 都会当场被吃掉；预览要的是代理帧，精帧只在松手后按需出。
   产品档预算是 4K UHD（8_294_400 像素，≈33.2 MB/帧）：1.11.0 起这就是默认值，
   此前 960×600 是跑靶预算，装到大屏上满幅拉伸就是一层马赛克。
"""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

# 产品档代理预算 = 4K UHD（3840×2160）。1.11.0 起这是默认值：大图只降到这一档，
# 再往上双缓冲要吃掉超过 66 MB tmpfs、每一帧都要拷满，收益只在放大到 200% 时才看得见。
# （960×600 是旧跑靶预算，产品路径已不再使用。）
PROXY_PIXELS = 8_294_400        # ≈33.2 MB/帧（RGBA），双缓冲 66 MB
# 预算的上/下限：这个值直接决定 /dev/shm 大小与显存分配量，不能由调用方任意抬。
# shm 写满 tmpfs 是 SIGBUS 硬死，不是可报错的异常。
MIN_BUDGET = 64 * 64
# 上限与产品档同一个数：预算由 UI 的 maxPx 传进来，而 maxPx 的出厂值就是 4K UHD。
# 此前写 8_000_000 会让 UI 的 8_294_400 直接吃到"越界"那条错。
MAX_BUDGET = 8_294_400          # ≈33.2 MB/帧（RGBA），双缓冲 66 MB
ALIGN = 8                       # 缩放后边长取 8 的倍数：对齐纹理块，也避开奇数边的半像素
EXIF_ORIENTATION = 0x0112
SWAPPED_ORIENTATIONS = {5, 6, 7, 8}     # 这几个方向值会把宽高对调


def clamp_budget(budget: int) -> int:
    """把外部传进来的像素预算接到合理区间（超限直接报错，不默默夹——夹了就不诚实）。"""
    b = int(budget)
    if not (MIN_BUDGET <= b <= MAX_BUDGET):
        raise ValueError(f"代理预算 {b} 越界（允许 {MIN_BUDGET}~{MAX_BUDGET} 像素）")
    return b


def proxy_size(w: int, h: int, budget: int = PROXY_PIXELS) -> tuple[int, int]:
    """保持长宽比缩到 budget 像素以内。小图原样返回（不放大、不重采样）。

    向下取整到 ALIGN 的倍数，所以 ow·oh ≤ (w·k)(h·k) = budget，天然不会越预算，
    不需要"超了就退一步"的循环。
    """
    if w <= 0 or h <= 0:
        raise ValueError(f"非法尺寸 {w}x{h}")
    if w * h <= budget:
        return w, h
    k = (budget / float(w * h)) ** 0.5
    ow = max(ALIGN, int(w * k) // ALIGN * ALIGN)
    oh = max(ALIGN, int(h * k) // ALIGN * ALIGN)
    if ow * oh > budget:        # 只可能在极小图 + 极小预算的组合下出现，兜底一次
        ow = max(ALIGN, ow - ALIGN)
        oh = max(ALIGN, oh - ALIGN)
    return ow, oh


@dataclass
class Decoded:
    """一次导入的产物：代理尺寸 RGB 与逐项耗时（ms）。"""
    rgb: np.ndarray                 # (h, w, 3) uint8，连续
    src_w: int                      # 已按 EXIF 方向摆正的源尺寸
    src_h: int
    fmt: str
    t_open_ms: float
    t_decode_ms: float
    t_orient_ms: float
    t_scale_ms: float
    t_total_ms: float
    draft_used: bool = False
    draft_size: tuple[int, int] | None = None
    # 源图每通道真实位深（P0：16-bit TIFF 导入不能静默降为 8-bit）。默认 8；
    # 预览代理把高位深源降到 8-bit 显示时，这一位必须报出真实源位深 + notes 里写清，
    # 让“看的是 8-bit 代理、母档/出片走 16-bit 直通”这件事可审计，而不是静默丢高位。
    src_bits: int = 8
    notes: list[str] = field(default_factory=list)
    raw: dict | None = None          # 解的是相机 RAW 时的加工模型读数（位深/排阵/黑白电平/分段耗时）
    # 源文件自带的颜色档与元数据。COLOR-001/002/003 要的不是“能嵌一个 ICC”，而是
    # “知道源文件自己是什么假设”：output_profile=source 与“带 GPS”这两个开关都得
    # 从这一层拿到真东西，不能在导出层拿“没有”当默认。“没有”与“没提取”是两件事，
    # 所以 RAW 那两支下面会写进 notes。不放进 meta()：那是过 JSON 通道的，字节过不了。
    source_icc: bytes | None = None
    source_exif: bytes | None = None
    # Full-decoder evidence for frozen Original-format header agreement.
    source_orientation: int = 1

    @property
    def w(self) -> int:
        return int(self.rgb.shape[1])

    @property
    def h(self) -> int:
        return int(self.rgb.shape[0])

    def meta(self) -> dict:
        return {
            "src_w": self.src_w, "src_h": self.src_h, "w": self.w, "h": self.h,
            "format": self.fmt, "draft": self.draft_used, "draft_size": list(self.draft_size) if self.draft_size else None,
            "open_ms": round(self.t_open_ms, 2), "decode_ms": round(self.t_decode_ms, 2),
            "orient_ms": round(self.t_orient_ms, 2), "scale_ms": round(self.t_scale_ms, 2),
            "total_ms": round(self.t_total_ms, 2),
            "bytes_per_frame": self.w * self.h * 4, "notes": self.notes,
            # 源位深：>8 时预览这一帧仍是 8-bit 代理，UI/报表据此显式标注“非静默降位”。
            "src_bits": self.src_bits,
            # RAW 的那一叠字段只在解的是 RAW 时存在（位深/排阵/黑白电平/渲染分段耗时）。
            # 平时是 None 而不是缺键：报表与真窗口取帧都按同一个形状读，缺键就是 undefined。
            "raw": self.raw,
        }


def sniff_raw(path: str) -> bool:
    """这是一张我们能解的相机 RAW 吗？必须先于 Pillow 判。

    Pillow 见到 CFA TIFF 会报 UnidentifiedImageError（而不是崩），但普通 .tif 照片
    与 DNG 用的是同一个 `II/MM + 42` 头——区分靠的是有没有 CFA/LinearRaw 的 raw IFD。
    让 Pillow 去猜，就会把相机 RAW 当坏图拒掉。嗅探只跳读 IFD 骨架（见
    raw.has_raw_ifd）：大 DNG 的 IFD 在文件尾，只读头部会漏判。
    """
    from . import raw as raw_mod
    return raw_mod.has_raw_ifd(path)


def _decoded_from_raw(res: dict, budget: int | None) -> "Decoded":
    """raw.load_raw 的结果 → Decoded（两条路共用同一个对外形状，不另发明一套字段）。"""
    rgb, m, ms = res["rgb"], res["meta"], res["ms"]
    h, w = rgb.shape[:2]
    d = Decoded(rgb=rgb, src_w=m.src_w, src_h=m.src_h, fmt=m.fmt,
                t_open_ms=ms["container_ms"], t_decode_ms=ms["pixels_ms"] + ms["render_ms"],
                t_orient_ms=0.0, t_scale_ms=ms["encode_ms"], t_total_ms=ms["total_ms"],
                draft_used=False, draft_size=None)
    d.raw = {"camera": m.camera, "bits": m.bits, "pattern": list(m.pattern),
             "pattern_dims": list(m.pattern_dims), "color_planes": m.color_planes,
             "black": float(np.max(np.asarray(m.black))), "white": m.white,
             "neutral": [round(float(v), 4) for v in m.neutral],
             "profile_weight": round(m.profile_weight, 4),
             "forward_matrix": m.forward is not None, "has_preview": bool(m.used_preview),
             # has_preview 是「文件里有没有预览」（raw.py 那个字段存的是“有”/“”），
             # used_preview 才是「这一帧像素是不是从预览来的」。两个分开写：把
             # “有”当成“用了”就是这一层最不能留的那种歧义——看着同一字段两种意思。
             # source 是“这一帧像素是谁解出来的”，全仓三个值：self_dng（自研读侧）、
             # libraw（系统库的真解码）、libraw_preview（相机内嵌预览）。上一版只有
             # libraw 那两支带名字、自研这支是 None，于是上报里“没名字”与“不是预览”
             # 两件事看起来一样：拿 source 做判据的人只能靠反推。名字补齐了才分得出
             # “哪个后端解的”，这也就是导出与能力上报需要的那个事实。
             "source": "self_dng",
             # 三条臂都报这一位：自研读侧没有半幅这条捷径，写死 False 而不是缺键——
             # 拿 .get("half_size") 的人分不清"没有这个概念"与"这一次没走半幅"
             "half_size": False,
             "used_preview": False,
             "container_ms": round(ms["container_ms"], 2), "pixels_ms": round(ms["pixels_ms"], 2),
             "render_ms": round(ms["render_ms"], 2), "encode_ms": round(ms["encode_ms"], 2),
             "notes": list(m.notes)}
    d.notes.extend(m.notes)
    d.notes.append(f"DNG：{m.bits}-bit CFA 解出 {w}×{h}（相机 {m.camera or '未报'}）")
    _note_no_source_metadata(d, "自研 DNG 读侧")
    if budget:
        d.notes.append("代理档走块内每色均值降采样 + LANCZOS，不抄内嵌预览")
    return d


def load_rgb(path: str, budget: int = PROXY_PIXELS, device: str | None = None,
             *, allow_preview: bool = False) -> Decoded:
    """真实图 → 代理帧。PNG16 走真 uint16 codec；其它位图走 Pillow。

    RAW 那条分支在最前面就分掉：它需要自己的位深/摆正/缩放口径，而把这些塞进
    Pillow 那段只会让两条路都变成“有点像”的路径（load_full 的注释里记着同一课）。
    """
    budget = clamp_budget(budget)
    from .png16_source import source_header
    png = source_header(path)
    if png is not None and png.bits == 16:
        return _png16_working_8bit(_load_16bit_png_full(path, MAX_EXPORT_PIXELS), budget=budget)
    if allow_preview:
        # 这个开关只属于浏览那一条通道（见下面那段分界规则）：默认关着，
        # 因为 load_rgb 的产物是要进常驻层被编辑的，而预览不是我们渲的图
        d = load_preview(path, budget)
        if d is not None:
            return d
    if is_raw(path):
        return _load_rgb_raw(path, budget, device, browse=allow_preview)
    return _load_rgb_pillow(path, budget)


# ---------------------------------------------------------------- RAW 的两条通道
#
# 需求上写的是「RAW 秒开走相机内嵌预览，出片走真去马赛克」，这两句必须同时成立，
# 而它们天生冲突：预览是相机自己渲的，出片是我们渲的。M3-b 修过的那一类缺陷就是
# 「预览与出片不同路」——所以分界在这一层钉成一条规则，改代码的人得先看见它：
#
#   内嵌预览只填**浏览/缩略图**那一个槽位。凡是要进常驻层、要被滑块吃、要被导出
#   拿走的像素，必须来自真解码（自研 DNG 读侧，或 LibRaw 的 dcraw_process）。
#
# 落在代码上的形状：`allow_preview` 默认 False，全仓只在**浏览那两个槽位**显式打开——
# session.make_thumb（底片条那一格）与 server._pick_measure_one（挑图读数，它同样只服务
# 浏览判断，并把 `decoded_from=camera_preview` 原样报进事件，RAW 的糊度读数属于相机预览
# 而不是母档这件事必须看得见）。视口要秒开，是调用方自己先把 load_preview 的帧推进 shm，
# 然后再走 load_rgb 默认
# 那条把真解码的常驻层装回来——把预览直接做成 load_rgb 的默认返回，等于让编辑读一张
# 别人渲好的图而账单上一个字都不提。
LIBRAW_EXTS = {".arw", ".cr2", ".cr3", ".nef", ".raf", ".orf", ".rw2"}
RAW_EXTS = LIBRAW_EXTS | {".dng"}


def raw_ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_raw(path: str) -> bool:
    """值不值得走 RAW 那条分支：后缀在 RAW 名单里，或 sniff 闻出 TIFF 骨架里有 raw IFD。

    sniff 只覆盖 DNG 那一族（TIFF 头 + CFA 标签）；厂商容器的 magic 根本不长那样（CR2 是
    "CR "），光靠 sniff 会把它们漏给 Pillow，然后报一句“不是图片”。后缀在这里不是猜
    格式，只决定进不进 RAW 分支——进去以后解不开照样如实抛，不静默换成别的渲染。
    """
    from . import raw as raw_mod
    if raw_ext(path) in RAW_EXTS:
        # These signatures select existing bitmap decoders, not a new decoder
        # or a successful payload claim. A JPEG/WebP/PNG named .dng/.nef must
        # not be sent to LibRaw after content-authenticated Original admission.
        with open(path, 'rb') as stream:
            head = stream.read(12)
        if head.startswith(b"\xff\xd8") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
            return False
        from .png16_source import source_header
        if source_header(path) is not None:
            return False
    if raw_mod.vendor_raw_family(path) is not None:
        # ORF/RW2 use TIFF byte-order markers with vendor magic, not TIFF42/43.
        # Preserve their established genuine LibRaw route without claiming a
        # bitmap or making strict Original-format metadata admission eligible.
        return True
    inspected = raw_mod.inspect_tiff(path)
    if inspected['source_kind'] == 'unknown' and inspected['reason'] != 'not_tiff':
        raise raw_mod.UnsupportedRaw('TIFF 类型不明确，不能按扩展名猜测 RAW 或位图: ' + inspected['reason'])
    if inspected['is_tiff']:
        return inspected['source_kind'] == 'raw'
    return raw_ext(path) in RAW_EXTS


def load_preview(path: str, budget: int = PROXY_PIXELS) -> "Decoded | None":
    """相机内嵌预览 → 代理尺寸 RGB。浏览/缩略图专用；拿不到就返 None，不自己画一张。

    只走 LibRaw 的 unpack_thumb：它搬的是文件里已经躺着的那张 JPEG，不碰传感器数据，
    所以是毫秒级（本机探针稳态 0.06 ms 量级）。返 None 的两种情由必须分开看：没有库
    （整条通道不可用）与这张没有预览——调用方都该 fallback 到真解码，而不是当解码失败。
    """
    from .ops import libraw as LR
    t0 = time.perf_counter()
    try:
        got = LR.extract_thumb(path)
    except (LR.LibRawUnavailable, LR.LibRawError, OSError):
        return None
    t_thumb = time.perf_counter()
    im = Image.open(io.BytesIO(got["jpeg"]))
    orient = int(im.getexif().get(EXIF_ORIENTATION, 1) or 1)
    if orient != 1:                                  # 预览 JPEG 自己带了方向就照它摆
        im = ImageOps.exif_transpose(im)
    im.load()
    pw, ph = im.size
    t_dec = time.perf_counter()
    ow, oh = proxy_size(pw, ph, clamp_budget(budget))
    if (ow, oh) != (pw, ph):
        im = im.resize((ow, oh), Image.LANCZOS)
    rgb = np.ascontiguousarray(np.asarray(im.convert("RGB"), dtype=np.uint8))
    t_scale = time.perf_counter()
    meta = got["meta"]
    src_w, src_h = int(meta["i_w"] or pw), int(meta["i_h"] or ph)
    d = Decoded(rgb=rgb, src_w=src_w, src_h=src_h, fmt=(raw_ext(path).lstrip(".").upper() or "RAW"),
                t_open_ms=(t_thumb - t0) * 1000.0, t_decode_ms=(t_dec - t_thumb) * 1000.0,
                t_orient_ms=0.0, t_scale_ms=(t_scale - t_dec) * 1000.0,
                t_total_ms=(t_scale - t0) * 1000.0,
                draft_used=True, draft_size=(pw, ph))
    d.raw = {"camera": " ".join(x for x in (meta["make"], meta["model"]) if x),
             "source": "libraw_preview", "bits": 8, "has_preview": True, "used_preview": True,
             "preview_w": pw, "preview_h": ph, "preview_bytes": got["bytes"],
             "thumb_ms": got["t_ms"]}
    d.notes.append(f"相机内嵌预览 {pw}×{ph}（仅浏览/首屏）：编辑与出片走真解码")
    if orient != 1:
        d.notes.append(f"预览按它自己的 EXIF orientation={orient} 摆正")
    return d


def _carry_metadata(im) -> tuple[bytes | None, bytes | None]:
    """在 exif_transpose 之前把源自带的 ICC 与 EXIF 取成字节带走。

    两个时机都是必要的：`ImageOps.exif_transpose` 返的是一张新图，它的 info 里没有
    原文件的 icc_profile；而 `with Image.open(...)`一退出，im.info 就成了无源之水。
    EXIF 当场序列化成 bytes 而不是递对象：Decoded 会被缓存、传递、甚至存进快照，
    拿着一个引用已关闭文件的 Exif 比拿 None 更坑。

    取不到就给 None（并在调用方的 notes 里能说清“没档”与“没提取”的区别），
    不烘一份“看起来像”的代替——COLOR-002 要的就是这个口径。
    """
    try:
        icc = im.info.get("icc_profile")
        icc = bytes(icc) if icc else None
    except Exception:
        icc = None
    try:
        ex = im.getexif()
        exif = bytes(ex.tobytes()) if len(ex) else None
    except Exception:
        exif = None
    return icc, exif


def _note_no_source_metadata(d: "Decoded", who: str) -> None:
    """RAW 那两支不产出 source_icc/source_exif，必须让上游看得见“没提取”而不是“源里没有”。

    这一句是给 UI 的禁用理由用的：output_profile=source 与“含 GPS”对 RAW 源现在
    根本不可用，不说清就只能要么默默报错、要么留一个按下去不响的开关（DoD-3 禁的就是这个）。
    两者在口径上是不同的：前者“接不了”，后者“这个源本来就没带”。
    """
    d.notes.append(f"{who}不提取源 ICC/EXIF：该源的“用源ICC”与“含 GPS”两项当前不可用"
                    "（不是源里没带，是这一条通道没读元数据）")


def _libraw_matrix(path: str, *, output_bps: int = 8, half_size: bool = False) -> tuple:
    """真去马赛克那一臂的入口：返回 (H,W,3) 矩阵与 LibRaw 的账单。

    `output_bps=8` 给预览与常驻代理层用；16-bit 母档归导出通路（M9-e），那里才需要
    把每一档线性值都留住。两个档位同一个函数出，不分叉实现。

    `half_size` 是 CFA 上 2×2 合并（binning）后再去马赛克：像素数 ÷4，**仍然是一次真
    解码**，不是抄相机渲好的那张预览。它只许用在浏览那一格（理由与实测数字写在
    `_load_rgb_raw` 里）。半幅时 LibRaw 的 iio 报的是半幅尺寸，账单里的 `half_size` 才是
    这一臂的真实形状。
    """
    from .ops import libraw as LR
    return LR.process(path, output_bps=int(output_bps), half_size=bool(half_size))


def _decoded_from_libraw(path: str, arr, info: dict, budget: int | None,
                         *, why: "Exception | str | None" = None, full: bool = False,
                         half: bool = False) -> "Decoded":
    """LibRaw 真解码的结果 → Decoded（与自研那条共用同一个对外形状）。"""
    h, w = int(arr.shape[0]), int(arr.shape[1])
    t0 = time.perf_counter()
    if full or (w * h <= (budget or 0)):
        rgb = np.ascontiguousarray(arr[:, :, :3])
        ow, oh = w, h
        t_scale = t0
    else:
        ow, oh = proxy_size(w, h, clamp_budget(budget))
        im = Image.fromarray(arr[:, :, :3]).resize((ow, oh), Image.LANCZOS)
        rgb = np.ascontiguousarray(np.asarray(im, dtype=np.uint8))
        t_scale = time.perf_counter()
    m = info["meta"]
    # 半幅那一臂 iio 报的是解出来的那一半，源图的尺寸必须是它的 2 倍（实测这张
    # 3024×2268 的靶在 half_size 下 iio 给 1512×1134）——把半幅当源幅报出去，
    # 底片条与导出对账时看到的就是一张小了一号的图，而这个错在 UI 上完全看不出来。
    src_w = int(m["i_w"] or w) * 2 if half else int(m["i_w"] or w)
    src_h = int(m["i_h"] or h) * 2 if half else int(m["i_h"] or h)
    d = Decoded(rgb=rgb, src_w=src_w, src_h=src_h,
                fmt=(raw_ext(path).lstrip(".").upper() or "RAW"),
                t_open_ms=info["set_ms"] + info["unpack_ms"], t_decode_ms=info["process_ms"],
                t_orient_ms=0.0, t_scale_ms=(t_scale - t0) * 1000.0,
                t_total_ms=info["total_ms"] + (t_scale - t0) * 1000.0,
                draft_used=False, draft_size=None)
    d.raw = {"camera": " ".join(x for x in (m["make"], m["model"]) if x),
             "source": "libraw", "bits": int(info["bits"]), "used_preview": False,
             "output_color_space": info.get("output_color_space"),
             "output_gamma": info.get("output_gamma"),
             # half_size 单独报出来：浏览那一格允许 binning，编辑与导出永远不许。
             # 这一位不给，"这张图是谁解的"就答不完整（同一帧像素，来路有两种）。
             "half_size": bool(half),
             "color_maximum": int(m["color_maximum"]), "cdesc": m["cdesc"],
             "dng_version": int(m["dng_version"]),
             "container_ms": round(info["set_ms"] + info["unpack_ms"], 2),
             "pixels_ms": round(info["process_ms"], 2),
             "render_ms": round(info["mem_ms"], 2), "encode_ms": 0.0,
             "demosaic_ms": round(info["process_ms"], 2)}
    cam = d.raw["camera"] or "未报机型"
    d.notes.append(f"LibRaw 真去马赛克：{w}×{h} {info['bits']}-bit（相机 {cam}）")
    d.notes.append("LibRaw输出显式使用sRGB原色及传递曲线（1/2.4，toe=12.92）")
    _note_no_source_metadata(d, "LibRaw 通道")
    if why is not None:
        # 换了后端必须看得见：基线读侧为什么解不开、这一臂用的是另一套实现，
        # 这两件事不能只在异常栈里，导出对账时它们是解释差异的唯一线索
        # 异常那一支的措辞是用例的锚点（"基线读侧没解开"），别改：改一个字，
        # "换了后端必须看得见"这句话就在 test_raw 那两条断言上静默失效
        d.notes.append(f"基线读侧没解开（{type(why).__name__}: {why}），这一张由 LibRaw 解码"
                       if not isinstance(why, str) else f"这一张走 LibRaw：{why}")
    if half:
        d.notes.append(f"半幅解码（CFA 2×2 合并，{w}×{h}）：仍是真去马赛克，只用于浏览那一格")
    if budget and (ow, oh) != (w, h) and not full:
        d.notes.append(f"代理档缩到 {ow}×{oh}（真解码之后重采样，不抄内嵌预览）")
    return d


# 浏览那一格允许用半幅解的前提：要的那一格的长边不足源图短边的 1/4。
# 4 这个数不是拍脑袋：半幅输出的长边是源图的 1/2，要求它至少是目标格子的 2 倍，
# binning 丢掉的那一半线性细节才落不到用户眼睛里。真尺寸那的那笔账（6.86 MP、无内嵌预览，
# gpuspike/m9f-bench.py，LibRaw 0.21.5）：全幅 264 ms、半幅 68 ms（0.26×），而 make_thumb(160)
# 现状每张要 228 ms。取舍取决于这个数，不取决于"半幅看起来差不多"那句话。
BROWSE_HALF_MIN_RATIO = 4


def _load_rgb_raw(path: str, budget: int, device: str | None, *, browse: bool = False) -> Decoded:
    """RAW 的代理帧：先试自研 DNG 读侧（基线，三臂证据那条路），解不开再转 LibRaw。

    `browse=True` 就是"这一帧只进浏览槽位"（与 allow_preview 同一个开关，全仓只有
    session.make_thumb 与 server._pick_measure_one 打开，两处都不进常驻层）。它多允许一件事：源图比目标格子大得多时用半幅解码，把每张
    228 ms 的账压到 68 ms 量级。编辑与导出走的仍然是全幅那一臂 —— 分界规则里"要进常驻层、
    要被滑块吃、要被导出拿走"的那一层一个字都不动，因为 2×2 合并确实会改像素（实测同一格
    160×160 缩略图与全幅解的最差 28 LSB、均值 0.43 LSB、超过 8 LSB 的像素 0.39%）：这点差别
    在浏览那一格看不见，在出片里就是不可接受的静默改图。
    """
    from . import raw as raw_mod
    why = None
    if browse:
        # 决定要在解码之前做：半幅那一臂只有在"目标格子的长边不足源图短边 1/4"时才允许，
        # 而要知道源图尺寸不用先解一次（identify 只读头，实测二十几毫秒）。
        from .ops import libraw as LR
        dims = LR.identify(path)
        if dims is not None:
            ow, oh = proxy_size(dims["w"], dims["h"], budget)
            if min(dims["w"], dims["h"]) >= BROWSE_HALF_MIN_RATIO * max(ow, oh):
                arr, info = _libraw_matrix(path, output_bps=8, half_size=True)
                return _decoded_from_libraw(path, arr, info, budget, why=why, half=True)
    if raw_mod.has_raw_ifd(path):
        try:
            return _decoded_from_raw(raw_mod.load_raw(path, budget=budget, device=device), budget)
        except raw_mod.UnsupportedRaw as e:
            why = e            # lossless JPEG / packed 位深 / float / BigTIFF / CFALayout≠1
    return _decoded_from_libraw(path, *_libraw_matrix(path, output_bps=8), budget, why=why)


def _refuse_multipage(im, path: str) -> None:
    """多页容器（多帧 TIFF / APNG / 动图 GIF）一律明拒，不静默取第 0 页（FORMAT-002）。

    “只解第一页”在这条产品线上是最坏的一种失败：文件写出来了、名字对、尺寸对，
    而它是那一叠里的第一页——用户直到打印才发现少了后面几页。这一版没有多页编辑
    也没有多页落盘（注册表里没有这一格），所以把不支持说清楚，而不是假装支持。
    与 sniff_raw/is_raw 同一条纪律：宁缺不假。
    """
    try:
        frames = int(getattr(im, "n_frames", 1) or 1)
    except (NotImplementedError, ValueError, AttributeError, TypeError):
        frames = 1              # 不支持多帧的格式报 NotImplementedError：按单页看
    if frames > 1:
        raise ValueError(f"{im.format or '?'} 容器有 {frames} 页：这一版只处理单页图像，"
                         f"不会拿第 0 页代替整件（{os.path.basename(path)}）；"
                         "需要逐页编辑请先拆成单页")


def _source_bits(im) -> int:
    """报源图每通道真实位深（只用于“不能静默降位”的可见性，不拿它把预览升到 16-bit）。

    TIFF 读 BitsPerSample(258)，文件型 PNG 读真实 IHDR（RGB 模式不能证明是 8-bit），
    Pillow 的单通道 16-bit 模式（I;16*）按 16；
    拿不到就当 8。这不是为了在预览里保留高位——工作层就是 8-bit RGBA 代理——而是让
    “一张 16-bit 源正被当作 8-bit 显示”这件事从静默变成可审计（P0 首版验收项①）。
    """
    if getattr(im, "format", None) == "PNG" and getattr(im, "filename", None):
        from .png16_source import source_header
        header = source_header(im.filename)
        if header is None or (header.width, header.height) != im.size:
            raise ValueError("PNG header 与已打开源图的尺寸或格式不一致")
        return header.bits
    try:
        bps = im.tag_v2.get(258) if hasattr(im, "tag_v2") else None
    except Exception:
        bps = None
    if isinstance(bps, (tuple, list)) and bps:
        return int(max(bps))
    if isinstance(bps, int) and bps > 0:
        return int(bps)
    if im.mode in ("I;16", "I;16B", "I;16L", "I;16N"):
        return 16
    bits = im.info.get("bits")
    if isinstance(bits, int) and bits > 0:
        return bits
    if isinstance(bits, (tuple, list)) and bits:
        try:
            return int(max(bits))
        except (TypeError, ValueError):
            pass
    return 8


def _load_16bit_png_full(path: str, max_px: int) -> Decoded:
    """Original PNG16 pixels remain source-encoded, matching the TIFF16 contract."""
    from .png16_source import load_opaque_rgb16
    source = load_opaque_rgb16(path, max_px=max_px)
    h, w = source.rgb.shape[:2]
    d = Decoded(rgb=source.rgb, src_w=w, src_h=h, fmt="PNG",
                t_open_ms=source.open_ms, t_decode_ms=source.decode_ms,
                t_orient_ms=source.orient_ms, t_scale_ms=0.0,
                t_total_ms=source.total_ms, src_bits=16,
                source_icc=source.source_icc, source_exif=source.source_exif,
                source_orientation=source.orientation)
    d.raw = {"source": "png16", "bits": 16, "used_preview": False, "half_size": False}
    d.notes.append(f"16-bit PNG 真解码：{w}×{h} uint16（已有 imagecodecs/libpng），低位未降位")
    if source.source_icc:
        d.notes.append("保留源 ICC 与源编码 uint16；进入工作空间时用 16-bit ICC 转换，不经 RGB8")
    elif source.colour_hint == "srgb":
        d.notes.append("PNG 明确声明普通 SDR sRGB 编码")
    else:
        d.notes.append("PNG 没有 ICC 或其它非 sRGB/HDR 声明：按普通 SDR sRGB 输入假设处理")
    if source.orientation != 1:
        d.notes.append(f"16-bit 像素按 PNG EXIF orientation={source.orientation} 无损摆正")
    return d


def _png16_working_8bit(d: Decoded, *, budget: int | None = None) -> Decoded:
    """ICC first, optional existing LANCZOS second, display quantization last.

    The retained ICC still describes the source file, not these already-sRGB
    uint8 pixels. Consumers must not apply it a second time to this output.
    """
    started = time.perf_counter()
    working = d.rgb
    if d.source_icc:
        from .color16 import convert_rgb16
        from .export import _srgb_bytes
        working = convert_rgb16(working, d.source_icc, _srgb_bytes())
        d.notes.append("源 ICC 已在真实 16-bit 像素上转换至 sRGB 工作空间，再生成 RGB8")
    size = proxy_size(d.src_w, d.src_h, budget) if budget is not None else (d.src_w, d.src_h)
    out = np.empty((size[1], size[0], 3), dtype=np.uint8)
    # Stage one float plane at a time, never an RGB8 image for ICC/resampling.
    # Float32 represents every uint16 integer exactly; any interpolation remains
    # display-only, and the genuine full-source path above is never mutated.
    for channel in range(3):
        if size == (d.src_w, d.src_h):
            values = working[:, :, channel].astype(np.uint32)
            out[:, :, channel] = ((values + 128) // 257).astype(np.uint8)
        else:
            with Image.fromarray(working[:, :, channel].astype(np.float32)) as plane:
                with plane.resize(size, Image.LANCZOS) as resized:
                    values = np.asarray(resized, dtype=np.float32)
                    out[:, :, channel] = np.clip(np.rint(values / 257.0), 0, 255).astype(np.uint8)
    elapsed = (time.perf_counter() - started) * 1000.0
    d.rgb = out
    d.t_scale_ms += elapsed
    d.t_total_ms += elapsed
    d.notes.append("源为 16-bit，工作 sRGB 转换后量化为 8-bit 显示/出片（非静默降位）；原件仍是真 uint16")
    if budget is None:
        d.notes.append("满幅解码（8-bit 输出，不缩放）")
    else:
        d.notes.append("源图已在代理档以内，未缩放" if size == (d.src_w, d.src_h)
                       else "代理使用已转换工作 sRGB 的高精度通道 LANCZOS 缩放后再量化")
    return d


def _load_16bit_tiff_full(path: str, max_px: int) -> Decoded:
    """Read true uint16 RGB TIFF using the upstream TIFF codec, then orient losslessly.

    Supports strips/tiles, separate/contiguous RGB, either endian and BigTIFF.
    Never convert through Pillow RGB or pad 8-bit data to impersonate 16-bit.
    """
    import tifffile
    t0 = time.perf_counter()
    try:
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            if len(tf.pages) != 1:
                raise ValueError("16-bit 多页 TIFF 尚需显式选页，不能静默丢弃其它页")
            if (page.dtype.kind != "u" or page.dtype.itemsize != 2
                    or int(page.photometric) != 2 or page.samplesperpixel != 3):
                raise ValueError("16-bit TIFF 导入需要真实 uint16 RGB 三通道；不静默降位或丢弃通道")
            w, h = int(page.imagewidth), int(page.imagelength)
            if w * h > int(max_px):
                raise ValueError(f"导出尺寸 {w}x{h} = {w*h/1e6:.0f} Mpx 超过上限 {int(max_px)/1e6:.0f} Mpx")
            orientation_tag = page.tags.get(274)
            orientation = int(orientation_tag.value) if orientation_tag else 1
            icc_tag = page.tags.get(34675)
            source_icc = bytes(icc_tag.value) if icc_tag else None
            opened = time.perf_counter()
            arr = page.asarray()
            if int(page.planarconfig) == 2:
                arr = arr.transpose(1, 2, 0)
            if arr.shape != (h, w, 3):
                raise ValueError(f"16-bit TIFF 像素形状异常：{arr.shape}")
            arr = arr.astype(np.uint16, copy=False)
            decoded = time.perf_counter()
    except (tifffile.TiffFileError, OSError, ValueError, IndexError) as exc:
        raise ValueError(f"无法读取真实 16-bit TIFF：{exc}") from exc
    if orientation not in range(1, 9):
        raise ValueError(f"TIFF orientation 非法：{orientation}")
    if orientation == 2:
        arr = arr[:, ::-1]
    elif orientation == 3:
        arr = arr[::-1, ::-1]
    elif orientation == 4:
        arr = arr[::-1]
    elif orientation == 5:
        arr = arr.transpose(1, 0, 2)
    elif orientation == 6:
        arr = np.rot90(arr, -1)
    elif orientation == 7:
        arr = arr.transpose(1, 0, 2)[::-1, ::-1]
    elif orientation == 8:
        arr = np.rot90(arr, 1)
    h, w = int(arr.shape[0]), int(arr.shape[1])
    if w * h > int(max_px):
        raise ValueError(f"导出尺寸 {w}x{h} = {w * h / 1e6:.0f} Mpx 超过上限 {int(max_px) / 1e6:.0f} Mpx")
    t1 = time.perf_counter()
    ms = lambda a, b: (b - a) * 1000.0      # noqa: E731
    d = Decoded(rgb=np.ascontiguousarray(arr), src_w=w, src_h=h, fmt="TIFF",
                t_open_ms=ms(t0, opened), t_decode_ms=ms(opened, decoded),
                t_orient_ms=ms(decoded, t1), t_scale_ms=0.0,
                t_total_ms=ms(t0, t1), draft_used=False, draft_size=None, src_bits=16)
    # source 报 "tiff16"：与 RAW 那三支（self_dng/libraw/libraw_preview）并列，让“这一帧谁解的”答得完整
    d.raw = {"source": "tiff16", "bits": 16, "used_preview": False, "half_size": False}
    d.source_icc = source_icc
    d.source_orientation = orientation
    if orientation != 1:
        d.notes.append(f"16-bit 像素按 TIFF orientation={orientation} 无损摆正")
    d.notes.append(f"16-bit TIFF 直通：读到 {w}×{h} 真实 uint16 像素（tifffile），未降位")
    return d


def _to_working_srgb(im, icc: bytes | None):
    """Convert embedded source encodings before any RGB editing or resampling.

    Keep the original ICC separately for output_profile=source. A mode conversion
    alone is not color management. Invalid profiles must not silently become sRGB.
    """
    if not icc:
        return im if im.mode == "RGB" else im.convert("RGB")
    from PIL import ImageCms
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        # Palette/alpha RGB images carry RGB profiles; CMYK, L and LAB need their
        # original modes so littleCMS sees the correct channel encoding.
        mode = im.mode if im.mode in ("RGB", "CMYK", "L", "LAB") else "RGB"
        source = im if im.mode == mode else im.convert(mode)
        return ImageCms.profileToProfile(
            source, src, ImageCms.createProfile("sRGB"), outputMode="RGB",
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
    except (ImageCms.PyCMSError, OSError, ValueError, TypeError) as exc:
        raise ValueError(f"输入 ICC 无法转换到 sRGB：{exc}") from exc


def _load_rgb_pillow(path: str, budget: int) -> Decoded:
    """解码 Pillow 认得的位图族（JPEG/PNG/WebP/BMP/TIFF），返回代理尺寸 RGB。

    两个容易踩的点，都在这函数里处理掉了：
    * **EXIF 方向**：手机竖拍常常是「横图 + orientation=6」，不转就会横着上屏。方向值
      要先读出来，才能算对代理档的宽高，也才能给 libjpeg 正确的 draft 目标。
    * **不禁用解压炸弹保护**：Pillow 的 MAX_IMAGE_PIXELS 保持默认，超大像素数会抛
      DecompressionBombError，这是我们要的行为。
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图片不存在或不是普通文件: {path}")
    ms = lambda a, b: (b - a) * 1000.0
    t0 = time.perf_counter()
    with Image.open(path) as im:
        fmt = im.format or "?"
        raw_w, raw_h = im.size
        _refuse_multipage(im, path)
        src_bits = _source_bits(im)
        orient = int(im.getexif().get(EXIF_ORIENTATION, 1) or 1)
        swap = orient in SWAPPED_ORIENTATIONS
        src_w, src_h = (raw_h, raw_w) if swap else (raw_w, raw_h)   # 摆正后的尺寸
        pw, ph = proxy_size(src_w, src_h, budget)
        # JPEG 的 DCT 缩放：libjpeg 能直接解出 1/2、1/4、1/8 尺寸。候选档是按**存储态**
        # 宽高算的（要两维都 ≥ 目标才选那一档），所以目标尺寸必须传回存储态方向：
        # 拿摆正后的 (pw,ph) 去请求竖构图，会把可用档拉低一级。实测 4000×3000 + orientation=6：
        # 传 (656,872) 只降到 1/2（解码 12.07 ms），传 (872,656) 能降到 1/4（6.43 ms）。
        draft_to = im.draft("RGB", (ph, pw) if swap else (pw, ph)) if fmt == "JPEG" else None
        icc, exif = _carry_metadata(im)
        t_d = time.perf_counter()
        im.load()
        t_o = time.perf_counter()
        if orient != 1:
            im = ImageOps.exif_transpose(im)          # 无 EXIF 时是空操作
        t_s = time.perf_counter()
        # These original-retouch decoders return RGB only. Do not discard actual
        # coverage before any portrait consumer can inspect it. Native high-bit
        # branches have already routed separately; creative RGBA asset import
        # retains its own alpha and does not pass through these two decoders.
        from .full_source_working import require_opaque_8bit
        require_opaque_8bit(im)
        im = _to_working_srgb(im, icc)
        if im.size != (pw, ph):                       # draft 只能给到近似尺寸，补最后一步
            im = im.resize((pw, ph), Image.LANCZOS)
        arr = np.ascontiguousarray(np.asarray(im, dtype=np.uint8))
    t1 = time.perf_counter()
    assert arr.shape == (ph, pw, 3) and arr.dtype == np.uint8, "解码输出布局不符约定"
    # im.draft() 返的是 (mode, (x0, y0, x1, y1))，不是尺寸元组。把它直接和 (raw_w, raw_h)
    # 比会永远“不等”→ draft_used 恒为 True，报表上每一张都写着“已吃到 DCT 缩放”。
    # 真缩放与否只能看返回 box 的实际宽高。
    draft_size: tuple[int, int] | None = None
    if isinstance(draft_to, tuple) and len(draft_to) == 2 and isinstance(draft_to[1], (tuple, list)):
        x0, y0, x1, y1 = draft_to[1]
        draft_size = (int(round(x1 - x0)), int(round(y1 - y0)))
    d = Decoded(rgb=arr, src_w=src_w, src_h=src_h, fmt=fmt,
                t_open_ms=ms(t0, t_d), t_decode_ms=ms(t_d, t_o), t_orient_ms=ms(t_o, t_s),
                t_scale_ms=ms(t_s, t1), t_total_ms=ms(t0, t1),
                draft_used=bool(draft_size and draft_size != (raw_w, raw_h)),
                draft_size=draft_size,
                src_bits=src_bits,
                source_icc=icc, source_exif=exif, source_orientation=orient)
    d.notes.append("输入嵌入 ICC 已转换至 sRGB 工作空间" if icc
                   else "源图没有 ICC：按 sRGB 输入假设处理")
    if d.draft_used:
        d.notes.append(f"libjpeg DCT 预缩到 {draft_size[0]}×{draft_size[1]}")
    if src_bits > 8:
        d.notes.append(f"源为 {src_bits}-bit，预览代理降到 8-bit 显示（非静默降位）；"
                       "出片/母档请走 16-bit 直通")
    if (src_w, src_h) == (pw, ph):
        d.notes.append("源图已在代理档以内，未缩放")
    if swap:
        d.notes.append(f"按 EXIF orientation={orient} 摆正过宽高")
    return d


# 导出的像素上限。不是"机器装不下"——分块导出本来就能把显存按住——而是"这已经不是
# 一张照片了"：Pillow 的解压炸弹保护默认到 1.78 亿像素就报，而真到那一级单张解码要几十秒
# 与几 GB 内存。超过这道线当场拒，比默默跑三十秒然后被 OOM killer 挑掉诚实。
MAX_EXPORT_PIXELS = 120_000_000


def load_full(path: str, max_px: int = MAX_EXPORT_PIXELS, device: str | None = None,
              *, want_bits: int = 8) -> Decoded:
    """满幅解码（不缩放）：PNG16 用真 codec，普通位图 Pillow，RAW 用真解码臂。

    `want_bits=16` 用于母档及高位深编辑导出：`rgb` 的 dtype 是 uint16。
    显示代理独立走 8-bit；高位深出片不能反过来读取该显示缓冲。

    16-bit 这一臂**不能拿自研读侧那支**：它只渲染 8-bit（实测 source=self_dng 回的是
    uint8）。上一版这里把 want_bits 透传给 `_libraw_matrix` 却仍然先走基线那一支，于是
    “要 16-bit”被悄悄退成“拿到 8-bit”——导出层只能拿它左移补零，而上报里写的还是 16。
    现在的形状：want_bits=16 就只进 LibRaw 那一支（它没装就报错，而不是降级）；基线
    那一支负责 8-bit 与代理档。两个理由都写进 notes，因为拿不到 16-bit 的人需要知道是谁拦的。
    """
    from . import raw as raw_mod
    want = int(want_bits)
    if want not in (8, 16):
        raise ValueError(f"want_bits 只认 8 或 16（收到 {want_bits!r}）")
    from .png16_source import source_header
    png = source_header(path)
    if png is not None and png.bits == 16:
        decoded = _load_16bit_png_full(path, max_px)
        return decoded if want == 16 else _png16_working_8bit(decoded)
    if is_raw(path):
        why = None
        if raw_mod.has_raw_ifd(path) and want == 8:
            try:
                res = raw_mod.load_raw(path, budget=None, device=device)
                m = res["meta"]
                if m.w * m.h > int(max_px):
                    raise ValueError(f"导出尺寸 {m.w}x{m.h} = {m.w * m.h / 1e6:.0f} Mpx "
                                     f"超过上限 {int(max_px) / 1e6:.0f} Mpx")
                return _decoded_from_raw(res, None)
            except raw_mod.UnsupportedRaw as e:
                why = e
        if want == 16 and raw_mod.has_raw_ifd(path):
            why = ("16-bit 母档走系统 LibRaw：自研读侧只渲染 8-bit，拿它凑 16-bit 就是左移补零")
        arr, info = _libraw_matrix(path, output_bps=want)
        if int(info["w"]) * int(info["h"]) > int(max_px):
            raise ValueError(f"导出尺寸 {info['w']}x{info['h']} = "
                             f"{int(info['w']) * int(info['h']) / 1e6:.0f} Mpx 超过上限 "
                             f"{int(max_px) / 1e6:.0f} Mpx")
        return _decoded_from_libraw(path, arr, info, None, why=why, full=True)
    if want == 16:
        ext = os.path.splitext(path)[1].lower()
        inspected = raw_mod.inspect_tiff(path)
        if inspected['is_tiff']:
            # Container content, not a suffix, selects native TIFF16. A JPEG
            # named .tif is not TIFF; a real TIFF named .jpg retains its samples.
            if (inspected['source_kind'] != 'bitmap' or not inspected.get('single_frame')
                    or inspected.get('precision') != 16 or inspected.get('photometric') != 2
                    or inspected.get('samples') != 3 or inspected.get('planar') not in (1, 2)):
                raise ValueError('16-bit TIFF 元数据不是受支持的单幅真实 RGB16 位图；不降位或猜测 RAW')
            return _load_16bit_tiff_full(path, max_px)
        raise ValueError(f"16-bit 直通只对相机 RAW、16bpc RGB TIFF 或真实 PNG16 成立"
                         f"（这张是 {ext or '无后缀'}）：普通 JPEG/8-bit PNG 里没有 16-bit 母档可直通，"
                         "不拿 8-bit 左移补零冒充。要 8-bit 出片请用常规导出。")
    return _load_full_pillow(path, max_px)


def _load_full_pillow(path: str, max_px: int = MAX_EXPORT_PIXELS) -> Decoded:
    """满幅解码（不缩放）：导出通路用。EXIF 方向与 load_rgb 同一条处理。

    为什么不走 `load_rgb(path, budget=像素数)`：那条路的预算被 clamp_budget 夹在
    800 万（预览帧的尺寸，与 shm 大小绑死），而且它会把边长往下取到 8 的倍数——
    导出要的就是源图那一个像素，取整就是改用户的构图。两边各自把该做的事写清楚，
    比共用一个“有点像”的路径诚实。
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图片不存在或不是普通文件: {path}")
    ms = lambda a, b: (b - a) * 1000.0         # noqa: E731  与 load_rgb 同一条计时口径
    t0 = time.perf_counter()
    with Image.open(path) as im:
        fmt = im.format or "?"
        raw_w, raw_h = im.size
        _refuse_multipage(im, path)
        src_bits = _source_bits(im)
        orient = int(im.getexif().get(EXIF_ORIENTATION, 1) or 1)
        swap = orient in SWAPPED_ORIENTATIONS
        src_w, src_h = (raw_h, raw_w) if swap else (raw_w, raw_h)
        if src_w * src_h > int(max_px):
            raise ValueError(f"导出尺寸 {src_w}x{src_h} = {src_w * src_h / 1e6:.0f} Mpx "
                             f"超过上限 {int(max_px) / 1e6:.0f} Mpx")
        icc, exif = _carry_metadata(im)
        t_d = time.perf_counter()
        im.load()
        t_o = time.perf_counter()
        if orient != 1:
            im = ImageOps.exif_transpose(im)
        if im.size != (src_w, src_h):          # 方向处理后的尺寸必须与报出去的一致
            raise ValueError(f"摆正后尺寸 {im.size} 与报出去的 {src_w}x{src_h} 不一致")
        t_s = time.perf_counter()
        # These original-retouch decoders return RGB only. Do not discard actual
        # coverage before any portrait consumer can inspect it. Native high-bit
        # branches have already routed separately; creative RGBA asset import
        # retains its own alpha and does not pass through these two decoders.
        from .full_source_working import require_opaque_8bit
        require_opaque_8bit(im)
        im = _to_working_srgb(im, icc)
        arr = np.ascontiguousarray(np.asarray(im, dtype=np.uint8))
    t1 = time.perf_counter()
    assert arr.shape == (src_h, src_w, 3) and arr.dtype == np.uint8, "满幅解码输出布局不符约定"
    d = Decoded(rgb=arr, src_w=src_w, src_h=src_h, fmt=fmt,
                t_open_ms=ms(t0, t_d), t_decode_ms=ms(t_d, t_o), t_orient_ms=ms(t_o, t_s),
                t_scale_ms=0.0, t_total_ms=ms(t0, t1), draft_used=False, draft_size=None,
                src_bits=src_bits,
                source_icc=icc, source_exif=exif, source_orientation=orient)
    d.notes.append("输入嵌入 ICC 已转换至 sRGB 工作空间" if icc
                   else "源图没有 ICC：按 sRGB 输入假设处理")
    d.notes.append("满幅解码（导出通路，不缩放）")
    if src_bits > 8:
        d.notes.append(f"源为 {src_bits}-bit：本路径按 8-bit 落盘（Pillow 会把高位截掉）；"
                       "要保 16-bit 请用 want_bits=16 的直通导出")
    if swap:
        d.notes.append(f"按 EXIF orientation={orient} 摆正过宽高")
    return d
