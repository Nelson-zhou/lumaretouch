"""Original Rust CUBE boundary; missing binary is an explicit error, never fallback."""
from __future__ import annotations
import ctypes as C
from functools import lru_cache
from pathlib import Path
import threading
import numpy as np
MAX_BYTES = 32 * 1024 * 1024
CHUNK = 262144
MAX_OUTPUT_BYTES = 256 * 1024 * 1024
P = C.POINTER(C.c_double)

@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / "bin/liblrt_custom_lut.so"
    if not path.is_file():
        raise RuntimeError("自定义 LUT Rust 核心未安装，未应用滤镜")
    lib = C.CDLL(str(path))
    lib.lrt_custom_lut_abi.argtypes = []
    lib.lrt_custom_lut_abi.restype = C.c_uint32
    if lib.lrt_custom_lut_abi() != 1: raise RuntimeError("自定义 LUT ABI 不兼容")
    lib.lrt_custom_lut_parse.argtypes = [C.c_void_p, C.c_size_t, C.c_void_p, C.c_size_t]
    lib.lrt_custom_lut_parse.restype = C.c_void_p
    lib.lrt_custom_lut_metadata.argtypes = [C.c_void_p, P]
    lib.lrt_custom_lut_metadata.restype = C.c_int
    lib.lrt_custom_lut_free.argtypes = [C.c_void_p]
    lib.lrt_custom_lut_free.restype = None
    lib.lrt_custom_lut_apply.argtypes = [C.c_void_p, P, P, C.c_size_t, C.c_double]
    lib.lrt_custom_lut_apply.restype = C.c_int
    return lib

class ParsedCube:
    def __init__(self, content: bytes):
        if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
            raise ValueError("CUBE 文件须为 1 字节至 32 MiB")
        self._lock = threading.RLock()
        self._lib = native()
        error = C.create_string_buffer(1024)
        buffer = C.create_string_buffer(content)
        self._handle = self._lib.lrt_custom_lut_parse(buffer, len(content), error, len(error))
        if not self._handle:
            raise ValueError(error.value.decode("utf-8", errors="replace"))

    def metadata(self):
        with self._lock:
            out = (C.c_double * 8)()
            if not self._handle or self._lib.lrt_custom_lut_metadata(self._handle, out): raise ValueError("LUT 元数据不可用")
            return tuple(out)

    def close(self):
        with self._lock:
            if self._handle:
                self._lib.lrt_custom_lut_free(self._handle)
                self._handle = None

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def apply(self, rgb, amount: float, cancelled=lambda: False):
        """Display-encoded sRGB float input. RGB16 stays float until final exporter.

        Active LUT clamps its lookup coordinates only, never table outputs. No
        log/RAW/ICC inference. Never changes input or commits partially processed output.
        """
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not np.isfinite(amount) or not 0 <= amount <= 1:
            raise ValueError("滤镜强度须为 0–1 的有限数")
        if not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype not in (np.float32, np.float64):
            raise ValueError("自定义 LUT 需要 H×W×3 浮点 sRGB")
        if not 0 < rgb.nbytes <= MAX_OUTPUT_BYTES:
            raise ValueError("图像超出自定义 LUT 预算")
        if cancelled(): raise InterruptedError("LUT 已取消")
        if amount == 0: return rgb
        # One output image and bounded float64 scratch, no full-image float64 copy.
        out = np.empty_like(rgb)
        with self._lock:
            if not self._handle: raise RuntimeError("LUT 已关闭")
            width = rgb.shape[1]
            for y in range(rgb.shape[0]):
                for x in range(0, width, CHUNK):
                    if cancelled(): raise InterruptedError("LUT 已取消")
                    src = np.ascontiguousarray(rgb[y, x:x+CHUNK], dtype=np.float64)
                    dst = np.empty_like(src)
                    code = self._lib.lrt_custom_lut_apply(self._handle, src.ctypes.data_as(P), dst.ctypes.data_as(P), len(src), amount)
                    if code: raise ValueError(f"Rust LUT 拒绝像素：{code}")
                    # Float32 conversion can overflow for a pathological HDR input.
                    if np.any(np.abs(dst) > np.finfo(rgb.dtype).max): raise ValueError("LUT 输出超出图像浮点范围")
                    out[y, x:x+CHUNK] = dst
        if cancelled(): raise InterruptedError("LUT 已取消")
        return out
