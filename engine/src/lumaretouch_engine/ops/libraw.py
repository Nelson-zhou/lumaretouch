"""LibRaw 后端：ctypes 绑**系统动态库**，只负责三件事——内嵌预览、Exif 元数据、16-bit 母档。

为什么是 ctypes + 系统 .so 而不是 pip 上的 rawpy（2026-10-18 拍板，见
`engine/requirements-libraw.txt` 的许可审计那一节）：
* rawpy 的 wheel 把 LibRaw **静态链接**进去，静态链接的 LGPL 义务与动态链接不是同一回事，
  而且它的依赖树从未逐包复核过；系统 `libraw_r.so.23` 由发行版打包，用户可自行替换 .so，
  义务最轻，也正是当初计划里写的「LibRaw，动态链接」那一条。
* 装机件因此在裸机上不需要任何 pip 网络动作：库在就开，库不在就如实拒绝。

三条硬纪律（与 lama / birefnet / realesrgan 同规，一条都不松）：
1. **加载失败 = 整条后端不可用**，绝不静默退回自研 DNG 读侧冒充「全格式已支持」。
2. **偏移表只许生成，不许手抄**：`libraw_layout.LAYOUT` 由编译器按真头文件算出；
   本模块在第一次用之前跑一次 `self_check()`——拿我们自己写的 DNG（`data/raw-probe.*`），
   按这张表读出尺寸、机型、内嵌预览与拍摄参数，与**写盘时就知道的答案**逐一对账。
   对不上就判定「表与 .so 不一致」并拒绝上线：读错偏移的后果不是报错，而是一堆看着
   像数据的垃圾。
3. **16-bit 的字节序不靠记忆**：`dcraw_make_mem_image` 返回的是 `uchar*`，16-bit 时每
   分量两个字节。字节序由 `_verify_byte_order()` 拿**同一张图的两个档位自洽**钉死：
   dcraw 的 8-bit 输出就是 16-bit 输出右移 8 位，两种解释只有一种能做到逐像素差 0（本机
   实测：直接序 max|Δ|=0，反序 92% 像素差 >1 LSB）。两种都过或都不过都当场拒。

线程安全：用 `libraw_r.so`（reentrant 变体），一次调用一个 handle，不在 handle 上跨线程共享。
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import time

from . import libraw_layout as L

MODEL_FILE_HINT = "libraw_r.so.23"
LIB_ENV = "LRT_LIBRAW_PATH"          # 装机关掉/换版本时的显式覆盖（与 LRT_MODEL_DIR 同风格）

LAYOUT = L.LAYOUT


class LibRawUnavailable(RuntimeError):
    """LibRaw 后端不可用。调用方必须当错误处理：不许退成自研读侧然后报「全格式已支持」。"""


# ---------------------------------------------------------------- 库的载入
def candidate_paths() -> list[str]:
    """候选路径：显式覆盖 → SONAME → soname 搜索 → 无版本号链接（开发机常见）。"""
    out = []
    env = os.environ.get(LIB_ENV, "").strip()
    if env:
        out.append(env)
    for name in ("libraw_r.so.23", "libraw_r.so.22", "libraw_r.so", "libraw.so.23", "libraw.so"):
        out.append(f"/usr/lib/x86_64-linux-gnu/{name}")
        out.append(f"/usr/lib/{name}")
    try:
        import ctypes.util
        for nm in ("raw_r", "raw"):
            p = ctypes.util.find_library(nm)
            if p:
                out.append(p if os.path.isabs(p) else f"/usr/lib/x86_64-linux-gnu/{p}")
    except Exception:      # find_library 在个别裁剪环境里会炸，不该带崩整条探测
        pass
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


_lib: ctypes.CDLL | None = None
_lib_path: str | None = None
_checked: bool = False
_check_error: str | None = None       # 自检败因：记住它，不每个请求重跑一次再报同一个错


def load_lib(force: bool = False) -> ctypes.CDLL:
    """载入 LibRaw 并配上签名。找不到就抛，且把试过哪些路径说清。

    `force=True` 是重探：先把缓存打掉再探。探不到就不能留旧缓存——留着它就是「这块机器
    上没有库，但接口还在报可用」，而接口报出去的那一句是要上能力清单的。
    """
    global _lib, _lib_path, _checked, _check_error
    if _lib is not None and not force:
        return _lib
    if force:
        _lib = _lib_path = None
        _checked = False
        _check_error = None
    tried = []
    lib = None
    for p in candidate_paths():
        if not os.path.exists(p):
            continue
        try:
            lib = ctypes.CDLL(p)
            _lib_path = p
            break
        except OSError as e:
            tried.append(f"{p}: {e}")
    if lib is None:
        raise LibRawUnavailable(
            f"系统 LibRaw 不可用（试过 {MODEL_FILE_HINT} 等 {len(candidate_paths())} 条路径"
            f"{'；失败详情：' + '; '.join(tried[:2]) if tried else '；机器上根本没有这个库'}）。"
            "全格式相机 RAW（CR2/CR3/NEF/ARW/RAF/ORF/RW2 与 packed/float/BigTIFF）依赖它；"
            f"装上系统包（apt install libraw23t64）或设 {LIB_ENV}=<libraw_r.so 绝对路径> 再试。"
            "自研 DNG 读侧仍在位，但那是「未压缩/Deflate 线性 DNG」那一档，不是全格式。")
    _setup_signatures(lib)
    _lib = lib
    _checked = False
    _check_error = None
    return lib


def _arg(lib, name, restype=None, argtypes=None):
    fn = getattr(lib, name)
    fn.restype = restype
    if argtypes is not None:
        fn.argtypes = argtypes
    return fn


def _setup_signatures(lib: ctypes.CDLL) -> None:
    """只绑必需符号；名字全部以 `nm -D` 在这块 .so 上数到的为准（不是凭文档）。

    少一个必需符号就整条后端不可用：宁可在装机关上门口说清，也不要绑一个同名字但
    签不同的函数（那种错在 ctypes 里是段错误或静默垃圾，不会是一条可读的错）。
    """
    H = ctypes.c_void_p
    missing = []

    def need(name, restype=None, argtypes=None):
        if not hasattr(lib, name):
            missing.append(name)
            return
        _arg(lib, name, restype, argtypes)

    need("libraw_version", ctypes.c_char_p)
    need("libraw_versionNumber", ctypes.c_int)
    need("libraw_init", H, [ctypes.c_uint])
    need("libraw_close", None, [H])
    need("libraw_open_file", ctypes.c_int, [H, ctypes.c_char_p])
    need("libraw_unpack", ctypes.c_int, [H])
    need("libraw_unpack_thumb", ctypes.c_int, [H])
    need("libraw_dcraw_process", ctypes.c_int, [H])
    need("libraw_dcraw_make_mem_image", ctypes.c_void_p, [H, ctypes.POINTER(ctypes.c_int)])
    need("libraw_dcraw_clear_mem", None, [ctypes.c_void_p])
    need("libraw_get_raw_height", ctypes.c_int, [H])
    need("libraw_get_raw_width", ctypes.c_int, [H])
    need("libraw_get_iheight", ctypes.c_int, [H])
    need("libraw_get_iwidth", ctypes.c_int, [H])
    need("libraw_get_color_maximum", ctypes.c_int, [H])
    need("libraw_get_iparams", ctypes.c_void_p, [H])
    need("libraw_get_imgother", ctypes.c_void_p, [H])
    if missing:
        raise LibRawUnavailable(
            f"这块 LibRaw 缺必需符号：{', '.join(missing)}（{lib}）。"
            "绑定只按实际导出的 C 接口写，不做同名猜测——绑错一个签名在 ctypes 里是段错误而不是一句错")


def libraw_version() -> str:
    try:
        return load_lib().libraw_version().decode("ascii", "replace")
    except LibRawUnavailable:
        return ""


def available() -> bool:
    try:
        load_lib()
        return True
    except LibRawUnavailable:
        return False


def missing_reason() -> str:
    try:
        load_lib()
        return ""
    except LibRawUnavailable as e:
        return str(e)


def status() -> dict:
    """能力上报要的那一份事实：库在不在、自检过没过、没过是为了什么。

    这里不主动跑自检（上报是高频路径，自检是一次性成本），也不替调用方粉饰：
    `_checked` 为假就是「还没验过」，为真才是「验过了」；两个都不是「可用」的同义词。
    """
    try:
        load_lib()
    except LibRawUnavailable as e:
        return {"installed": False, "checked": False, "version": "", "reason": str(e),
                "lib_path": "", "table_for": L.LIBRAW_VERSION}
    return {"installed": True, "checked": bool(_checked), "version": libraw_version(),
            "reason": _check_error or "", "lib_path": _lib_path or "",
            "table_for": L.LIBRAW_VERSION}


# ---------------------------------------------------------------- handle 的小包装
class Handle:
    """一次一个 handle；with 出去就 close，库里的内部缓冲随之释放。"""

    def __init__(self):
        self.lib = load_lib()
        self.ptr = self.lib.libraw_init(0)
        if not self.ptr:
            raise LibRawUnavailable("libraw_init 返回空句柄（库版本与头表可能不匹配）")

    def __enter__(self) -> "Handle":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self.ptr:
            self.lib.libraw_close(self.ptr)
            self.ptr = None

    # --- 按生成表读字段：所有偏移都来自 LAYOUT，本文件里不出现一个手写的字节位置 ---
    def _off(self, key: str) -> int:
        v = LAYOUT.get(key)
        if v is None:
            raise LibRawUnavailable(f"偏移表里没有 {key}——重跑 packaging/gen-libraw-layout.sh")
        return int(v)

    def _u16(self, base_off: int, field: str) -> int:
        return ctypes.cast(self.ptr + base_off + self._off(field),
                           ctypes.POINTER(ctypes.c_uint16)).contents.value

    def _f32(self, base_off: int, field: str) -> float:
        return ctypes.cast(self.ptr + base_off + self._off(field),
                           ctypes.POINTER(ctypes.c_float)).contents.value

    def _cstr(self, base_off: int, field: str, maxlen: int = 64) -> str:
        raw = ctypes.string_at(self.ptr + base_off + self._off(field), maxlen)
        return raw.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()

    def _ptr_at(self, base_off: int, field: str):
        return ctypes.cast(self.ptr + base_off + self._off(field),
                           ctypes.POINTER(ctypes.c_void_p)).contents.value

    def open_file(self, path: str) -> int:
        rc = self.lib.libraw_open_file(self.ptr, os.fsencode(path))
        if rc != LAYOUT["LIBRAW_SUCCESS"]:
            raise LibRawError(rc, path)
        return rc

    @property
    def sizes_off(self) -> int:
        return self._off("libraw_data_t.sizes")

    @property
    def idata_off(self) -> int:
        return self._off("libraw_data_t.idata")

    @property
    def other_off(self) -> int:
        return self._off("libraw_data_t.other")

    @property
    def thumbnail_off(self) -> int:
        return self._off("libraw_data_t.thumbnail")


class LibRawError(RuntimeError):
    """LibRaw 返回非 0。把错误码翻成人话，但**原码一起带上**——翻错名字比带码更坏。"""

    NAMES = {v: k for k, v in LAYOUT.items() if k.startswith("LIBRAW_") and isinstance(v, int) and v <= 0}

    def __init__(self, rc: int, path: str = ""):
        self.rc = int(rc)
        name = self.NAMES.get(self.rc, "UNKNOWN")
        super().__init__(f"LibRaw 返回 {self.rc}（{name}）：{os.path.basename(path) or path or '(无文件名)'}")


# ---------------------------------------------------------------- 三个能力
def _read_meta(h: "Handle") -> dict:
    """尺寸（raw 与输出）、机型、拍摄参数、色彩上限。尺寸走库自己的访问器，其余走生成表。

    调用时机是语义的一部分，不是实现细节：`color_maximum` 在 open_file 之后就是文件写的
    WhiteLevel（本机探针 16383），而 unpack/dcraw_process 之后再读会变成 dcraw 缩放过的
    内部上限（同一张文件量到 15774）。两个时机的数不是同一件事，别拿其中一个去验另一个。
    """
    lib = h.lib
    ip = h.ptr + h.idata_off

    def i32(base, field):
        return ctypes.cast(base + h._off(field), ctypes.POINTER(ctypes.c_int)).contents.value

    def u32(base, field):
        return ctypes.cast(base + h._off(field), ctypes.POINTER(ctypes.c_uint)).contents.value

    return {
        "raw_w": int(lib.libraw_get_raw_width(h.ptr)), "raw_h": int(lib.libraw_get_raw_height(h.ptr)),
        "i_w": int(lib.libraw_get_iwidth(h.ptr)), "i_h": int(lib.libraw_get_iheight(h.ptr)),
        "make": h._cstr(h.idata_off, "libraw_iparams_t.make"),
        "model": h._cstr(h.idata_off, "libraw_iparams_t.model"),
        "software": h._cstr(h.idata_off, "libraw_iparams_t.software"),
        "cdesc": h._cstr(h.idata_off, "libraw_iparams_t.cdesc", 5),
        "colors": i32(ip, "libraw_iparams_t.colors"),
        "dng_version": u32(ip, "libraw_iparams_t.dng_version"),
        "iso_speed": h._f32(h.other_off, "libraw_imgother_t.iso_speed"),
        "shutter": h._f32(h.other_off, "libraw_imgother_t.shutter"),
        "aperture": h._f32(h.other_off, "libraw_imgother_t.aperture"),
        "focal_len": h._f32(h.other_off, "libraw_imgother_t.focal_len"),
        "color_maximum": int(lib.libraw_get_color_maximum(h.ptr)),
    }


def extract_thumb(path: str) -> dict:
    """浏览与编辑快通道：取相机内嵌预览的 JPEG 字节（不解码、不缩放——那是 decode 层的事）。"""
    ensure_checked()
    with Handle() as h:
        h.open_file(path)
        return _read_thumb(h, path)


def _read_thumb(h: "Handle", path: str) -> dict:
    """真正取预览的那一层（不带自检，所以下面 self_check 能直接用它）。"""
    t0 = time.perf_counter()
    rc = h.lib.libraw_unpack_thumb(h.ptr)
    if rc != LAYOUT["LIBRAW_SUCCESS"]:
        raise LibRawError(rc, path)
    toff = h.thumbnail_off
    tformat = ctypes.cast(h.ptr + toff + h._off("libraw_thumbnail_t.tformat"),
                          ctypes.POINTER(ctypes.c_int)).contents.value
    w = h._u16(toff, "libraw_thumbnail_t.twidth")
    hh = h._u16(toff, "libraw_thumbnail_t.theight")
    length = ctypes.cast(h.ptr + toff + h._off("libraw_thumbnail_t.tlength"),
                         ctypes.POINTER(ctypes.c_uint)).contents.value
    data = h._ptr_at(toff, "libraw_thumbnail_t.thumb")
    jpeg = LAYOUT["LIBRAW_THUMBNAIL_JPEG"]
    if int(tformat) != int(jpeg):
        raise LibRawUnavailable(
            f"内嵌预览不是 JPEG（tformat={tformat}；JPEG={jpeg}）：本通道只搬相机自己写的那张，"
            "不做二次渲染——把位图缩略当照片预览会掩掉真实曝光细节")
    if not data or not length:
        raise LibRawError(LAYOUT["LIBRAW_NO_THUMBNAIL"], path)
    buf = ctypes.string_at(data, int(length))       # handle 一 close 这块就没了，必须此刻复制
    meta = _read_meta(h)
    return {"jpeg": buf, "w": int(w), "h": int(hh), "bytes": len(buf),
            "t_ms": round((time.perf_counter() - t0) * 1000.0, 3), "meta": meta}


# 16-bit 的字节解释：None = 还没用真值钉过；True = 原样读出来必须 byteswap 才对。
# 这个值只由 _verify_byte_order() 写（见下面的自检），不由文档或记忆写死。
_ENDIAN_SWAPPED: bool | None = None


def process(path: str, *, use_camera_wb: bool = True, use_camera_matrix: bool = True,
            output_bps: int = 16, no_auto_bright: bool = True,
            half_size: bool = False, flip: int | None = None) -> tuple:
    """终极导出通道：真去马赛克 → (H,W,3) 的 uint16（或 uint8）RGB 矩阵 + 账单。

    `use_camera_wb` / `use_camera_matrix` 写 params 里那两个字段，bps / 亮度 / 摆正
    同理——偏移全部来自生成表，本文件里不出现一个手写的字节位置。
    出片之前先过一次进程内自检（`ensure_checked`）：偏移与字节序没被真值钉死之前，
    交出去的矩阵来路不明，宁可现在就报错而不是让它在报表上与真数据长得一样。
    返回 (ndarray, info)：info 里有分段耗时、色上限、尺寸与本次用到的开关，导出账单照它写。
    """
    ensure_checked()
    return _decode(load_lib(), path, output_bps=output_bps, use_camera_wb=use_camera_wb,
                   use_camera_matrix=use_camera_matrix, no_auto_bright=no_auto_bright,
                   half_size=half_size, flip=flip)


def _decode(lib: ctypes.CDLL, path: str, *, output_bps: int = 16, use_camera_wb: bool = True,
            use_camera_matrix: bool = True, no_auto_bright: bool = True,
            half_size: bool = False, flip: int | None = None,
            pin_endian: bool = True) -> tuple:
    """open_file → unpack → dcraw_process → make_mem_image 一趟走完，返回 (ndarray, info)。

    `pin_endian=False` 只给字节序自检用：它要比「未经解释的原样数组」在两种读法下各自
    与 8-bit 档是否自洽，所以那一次不许替它 swap。
    """
    import numpy as np
    t0 = time.perf_counter()
    with Handle() as h:
        h.open_file(path)
        base = h.ptr + h._off("libraw_data_t.params")

        def set_int(field, value):
            ctypes.cast(base + h._off(field), ctypes.POINTER(ctypes.c_int)).contents.value = int(value)

        set_int("libraw_output_params_t.use_camera_wb", 1 if use_camera_wb else 0)
        set_int("libraw_output_params_t.use_camera_matrix", 1 if use_camera_matrix else 0)
        set_int("libraw_output_params_t.no_auto_bright", 1 if no_auto_bright else 0)
        set_int("libraw_output_params_t.half_size", 1 if half_size else 0)
        if flip is not None:
            set_int("libraw_output_params_t.user_flip", flip)
        set_int("libraw_output_params_t.output_bps", int(output_bps))
        t_set = time.perf_counter()

        rc = lib.libraw_unpack(h.ptr)
        if rc != LAYOUT["LIBRAW_SUCCESS"]:
            raise LibRawError(rc, path)
        t_unpack = time.perf_counter()
        rc = lib.libraw_dcraw_process(h.ptr)
        if rc != LAYOUT["LIBRAW_SUCCESS"]:
            raise LibRawError(rc, path)
        t_proc = time.perf_counter()
        err = ctypes.c_int(0)
        img = lib.libraw_dcraw_make_mem_image(h.ptr, ctypes.byref(err))
        if not img:
            raise LibRawError(err.value or LAYOUT["LIBRAW_UNSPECIFIED_ERROR"], path)
        try:
            def fld(name, ctype):
                return ctypes.cast(img + h._off(name), ctypes.POINTER(ctype)).contents.value

            ih = fld("libraw_processed_image_t.height", ctypes.c_uint16)
            iw = fld("libraw_processed_image_t.width", ctypes.c_uint16)
            colors = fld("libraw_processed_image_t.colors", ctypes.c_uint16)
            bits = fld("libraw_processed_image_t.bits", ctypes.c_uint16)
            data_size = fld("libraw_processed_image_t.data_size", ctypes.c_uint)
            raw = ctypes.string_at(img + h._off("libraw_processed_image_t.data"), int(data_size))
        finally:
            lib.libraw_dcraw_clear_mem(img)
        meta = _read_meta(h)
    t_bytes = time.perf_counter()
    expect = int(ih) * int(iw) * int(colors) * (2 if int(bits) > 8 else 1)
    if int(data_size) != expect:
        raise LibRawUnavailable(
            f"make_mem_image 的字节数 {data_size} 与 {ih}x{iw}x{colors}x{bits}bit 算出来的 {expect} 不符"
            "——结构假设与这块库不一致，拒绝交付一个来路不明的矩阵")
    dtype = np.uint16 if int(bits) > 8 else np.uint8
    arr = np.frombuffer(raw, dtype=dtype).reshape(int(ih), int(iw), int(colors))
    if dtype is np.uint16 and pin_endian and _ENDIAN_SWAPPED:
        arr = arr.byteswap()
    info = {"w": int(iw), "h": int(ih), "bits": int(bits), "colors": int(colors),
            "bytes": int(data_size),
            "endian_swapped": (bool(_ENDIAN_SWAPPED) if dtype is np.uint16 else None),
            "color_maximum": meta["color_maximum"],
            "set_ms": round((t_set - t0) * 1000, 2), "unpack_ms": round((t_unpack - t_set) * 1000, 2),
            "process_ms": round((t_proc - t_unpack) * 1000, 2),
            "mem_ms": round((t_bytes - t_proc) * 1000, 2),
            "total_ms": round((t_bytes - t0) * 1000, 2),
            "use_camera_wb": int(use_camera_wb), "use_camera_matrix": int(use_camera_matrix),
            "output_bps": int(output_bps), "no_auto_bright": int(no_auto_bright),
            "half_size": int(half_size), "meta": meta}
    return arr, info


# ---------------------------------------------------------------- 运行期真值自检
def _verify_byte_order(path: str) -> dict:
    """16-bit 的字节序用**同一张图两个档位自洽**钉死，不照文档说法写死。

    判据（本机 LibRaw 0.21.5 实测）：dcraw 的 8-bit 输出就是 16-bit 输出右移 8 位——
    直接序逐像素 max|Δ|=0；拿反序去比是 99.09% 像素差 >1 LSB、最大差 255，分得很开。
    只允许恰好一种解释通过：两种都过说明这张材料分不开它们（换材料），两种都不过说明
    这块库的输出不是我们以为的那样（拒绝上线）。拿不准就当不可用，不比交出一个
    乘了 256 的矩阵坏。
    """
    import numpy as np
    global _ENDIAN_SWAPPED
    lib = load_lib()
    a16, _ = _decode(lib, path, output_bps=16, pin_endian=False)
    a8, _ = _decode(lib, path, output_bps=8, pin_endian=False)
    if a16.shape != a8.shape:
        raise LibRawUnavailable(
            f"自检材料不合格：{os.path.basename(path)} 的 16-bit 与 8-bit 输出形状不一致"
            f"（{a16.shape} vs {a8.shape}）——两档不是同一张图，比不出字节序")
    passing: list[bool] = []
    report: dict = {}
    for swap in (False, True):
        cand = a16.byteswap() if swap else a16
        diff = np.abs((cand.astype(np.int64) >> 8) - a8.astype(np.int64))
        over = float((diff > 1).mean())
        report["swapped" if swap else "direct"] = {
            "max_abs_diff": int(diff.max()) if diff.size else -1,
            "frac_over_1lsb": round(over, 6)}
        if diff.size and over == 0.0:
            passing.append(bool(swap))
    if len(passing) != 1:
        raise LibRawUnavailable(
            f"16-bit 字节序无法自证（{os.path.basename(path)}；读数 {report}）："
            + ("两种解释都与同档 8-bit 输出不等" if not passing
               else "两种解释都自洽，这张材料分不开它们")
            + "——拒绝交出一个来路不明的矩阵")
    _ENDIAN_SWAPPED = passing[0]
    return {"endian_swapped": passing[0], **report}


# 自检材料：随引擎包走的一份小 DNG + 它写盘时就知道的答案。
# 为什么放包内而不是 tests/fixtures：stage-engine.sh 只收 engine/src，装机件里没有 tests；
# 而自检要跑在装机件的第一次 RAW 请求上——材料必须在包里，不然只能退成「没对过账就上线」。
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PROBE_DNG = os.path.join(DATA_DIR, "raw-probe.dng")
PROBE_SIDECAR = os.path.join(DATA_DIR, "raw-probe.json")


def _sha256_bytes(buf: bytes) -> str:
    return hashlib.sha256(buf).hexdigest()


def _verify_param_writes(path: str) -> dict:
    """params 那一区是**我们往库里写**的（use_camera_wb / half_size / output_bps）。

    写错偏移不会报错，只会让开关失效——而「按了没反应」在成品上是最难归因的一类错。
    所以拿输出本身当证据：两个白平衡档必须真的不一样，半幅必须真的是半幅。
    """
    import numpy as np
    lib = load_lib()
    a_wb, _ = _decode(lib, path, output_bps=16, use_camera_wb=True)
    a_auto, _ = _decode(lib, path, output_bps=16, use_camera_wb=False)
    split = float(np.abs(a_wb.astype(np.int64) - a_auto.astype(np.int64)).mean())
    if bool(np.array_equal(a_wb, a_auto)):
        raise LibRawUnavailable(
            f"use_camera_wb 写下去与不写输出逐字节相同（{os.path.basename(path)}）——"
            "libraw_output_params_t 的偏移在这块库上不对：开关按了不会有任何反应，"
            "但报表上会写着「已用相机原厂白平衡」")
    half, _ = _decode(lib, path, output_bps=16, half_size=True)
    if (half.shape[0] * 2, half.shape[1] * 2) != (a_wb.shape[0], a_wb.shape[1]):
        raise LibRawUnavailable(
            f"half_size 写下去没有给出半幅（{half.shape[1]}x{half.shape[0]} 对 "
            f"{a_wb.shape[1]}x{a_wb.shape[0]}）——params 那一区的偏移不对")
    return {"wb_vs_auto_mean_diff": round(split, 2), "half_shape": [int(half.shape[0]), int(half.shape[1])]}


def self_check(dng_path: str | None = None, sidecar_path: str | None = None) -> dict:
    """拿一张**我们自己写的** DNG 对账：尺寸、机型、内嵌预览、拍摄参数、开关落点、
    16-bit 字节序。任何一项不符就整条拒。

    为什么必须有一道自检：偏移表是在开发机上按 0.21.5 的头生成的，而装机件跑的是**别人
    机器上那块 .so**。版本一错，读到的不是异常而是垃圾（尺寸 0、机型乱码、预览指到别人的
    缓冲），那种数据在报表上与真数据长得一样。自检不过 → LibRawUnavailable，前端与
    raw_backends 一起说实话。

    真值来自 `data/raw-probe.json`：那是写这张探针时**已经知道的答案**（尺寸、机型、
    内嵌预览的宽高/字节数/sha256），不是 LibRaw 自己报的数——拿库的输出验库自己，
    得到的只是自洽，不是符合。
    """
    global _checked
    lib = load_lib()
    runtime = lib.libraw_version().decode("ascii", "replace")
    dng = dng_path or PROBE_DNG
    sc = sidecar_path or PROBE_SIDECAR
    if not os.path.isfile(dng) or not os.path.isfile(sc):
        raise LibRawUnavailable(
            f"自检材料不齐（{dng} / {sc}）：跑 packaging/make-raw-probe.py 生成 raw-probe 那一件。"
            "没有真值可对账时这条通道宁可不成立，不能拿客户的照片当试错的对象")
    with open(sc, encoding="utf-8") as f:
        truth = json.load(f)
    want_sha = str(truth.get("dng_sha256") or "")
    if want_sha:
        with open(dng, "rb") as f:
            got_sha = _sha256_bytes(f.read())
        if got_sha != want_sha:
            raise LibRawUnavailable(
                f"自检材料与答案不配对：{os.path.basename(dng)} 实算 sha256={got_sha[:12]}…，"
                f"sidecar 记的是 {want_sha[:12]}…——要么材料被改过，要么两份不同步")

    with Handle() as h:
        h.open_file(dng)
        got = _read_meta(h)
        thumb = _read_thumb(h, dng)
    if (got["i_w"], got["i_h"]) != (int(truth["i_w"]), int(truth["i_h"])):
        raise LibRawUnavailable(
            f"偏移表与这块 .so 不一致：写探针时的真值是 {truth['i_w']}x{truth['i_h']}，"
            f"按表读到 {got['i_w']}x{got['i_h']}（表来源 LibRaw {L.LIBRAW_VERSION}，"
            f"实库 {lib.libraw_version().decode('ascii', 'replace')}）")
    for field in ("make", "model"):
        if got[field] != truth[field]:
            raise LibRawUnavailable(
                f"按表读出的 {field} 与写进去的不是同一个（读到 {got[field]!r}，"
                f"真值 {truth[field]!r}）——偏移表过期，拒绝上线")
    # 色彩上限：open_file 之后读到的就是文件声明的 WhiteLevel（时机语义见 _read_meta）
    if float(truth.get("white") or 0) and int(got["color_maximum"]) != int(float(truth["white"])):
        raise LibRawUnavailable(
            f"按表读出的色彩上限与写进去的不是同一个（读到 {got['color_maximum']}，"
            f"真值 {truth['white']}）——尺寸与上限都是库自己的访问器给的，对不上就说明"
            "这块 .so 连自己解出来的元数据都不是我们写进去的那一份")
    pv = truth["preview"]
    if (thumb["w"], thumb["h"], thumb["bytes"]) != (int(pv["w"]), int(pv["h"]), int(pv["bytes"])):
        raise LibRawUnavailable(
            f"按表读出的内嵌预览与写进去的不是同一张（读到 {thumb['w']}x{thumb['h']} "
            f"{thumb['bytes']}B，真值 {pv['w']}x{pv['h']} {pv['bytes']}B）——"
            "thumbnail 那几个字段在这块库上不对，快通道给的全是别人的字节")
    if _sha256_bytes(thumb["jpeg"]) != str(pv["sha256"]):
        raise LibRawUnavailable("预览 JPEG 的 sha256 与真值不符：取到的不是那张图")
    ex = truth.get("exif") or {}
    if ex:
        # 拍摄参数那三个字段在 libraw_imgother_t 里是相邻的 float：偏移错一处，读出来的
        # 就是别人的字节（或是把别人的字节当成自己的）。浮点对账按 float32 的存储精度
        # 放宽容差——0.005 存在库里是 0.00499999988…，那不是错。
        for field in ("shutter", "aperture", "focal_len"):
            want, got_v = float(ex[field]), float(got[field])
            if abs(got_v - want) > max(abs(want) * 1e-3, 1e-3):
                raise LibRawUnavailable(
                    f"按表读出的 {field} 与写进去的不是同一个（读到 {got_v}，真值 {want}）——"
                    "libraw_imgother_t 在这块库上不对，Exif 面板要显示的就是这些字节")
    t_thumb = thumb["t_ms"]
    params = _verify_param_writes(dng)          # 我们往库里写的那几个开关落点不对就拒
    endian = _verify_byte_order(dng)          # 写 _ENDIAN_SWAPPED；分不开/都不过就抛
    _checked = True
    return {"libraw": runtime, "lib_path": _lib_path,
            "table_matches_lib": runtime == L.LIBRAW_VERSION, "table_for": L.LIBRAW_VERSION,
            "probe": os.path.basename(dng), "make": got["make"], "model": got["model"],
            "i_w": got["i_w"], "i_h": got["i_h"], "truth": f"{truth['i_w']}x{truth['i_h']}",
            "preview": f"{thumb['w']}x{thumb['h']}", "thumb_ms": t_thumb,
            "exif": {k: got[k] for k in ("shutter", "aperture", "focal_len", "iso_speed")},
            "iso_speed_truth": (truth.get("exif") or {}).get("iso"),
            "params": params,
            "endian_swapped": _ENDIAN_SWAPPED, "endian_arms": endian,
            "color_maximum": got["color_maximum"]}


def ensure_checked() -> None:
    """进第一次调用前过一次自检；失败就记住原因，不要每个请求重跑一遍然后反复报同一个错。"""
    global _checked, _check_error
    if _checked:
        return
    if _check_error is not None:
        raise LibRawUnavailable(_check_error)
    try:
        self_check()
    except LibRawUnavailable as e:
        _check_error = str(e)
        raise
