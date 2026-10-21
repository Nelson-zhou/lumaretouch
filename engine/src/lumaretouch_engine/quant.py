"""float → uint8 的唯一量化口径。

为什么单独立一个文件：M2-a2 的 D&B 探针量到 GPU 与 CPU 参考之间有 **−0.686 LSB 的
平均偏移**（68.6% 像素差 1 级，连续域只差 3e-07）。平均偏移不是噪声——噪声的均值是 0。
根因是收尾那一步用的是**向零截断**（`x.to(torch.uint8)` / `astype(np.uint8)`），
任何非格点值都被系统性压到下一档：实测 ×0.9875 偏暗 0.4786 LSB、×1.0125 偏暗 0.4494 LSB，
而四舍五入是 0.0000。

这个偏差为什么藏了四个里程碑：截断与舍入只在"值不在格点上"时才有区别，而以往所有
对拍都是**两臂用同一个截断**，偏差在相减里抵消了；恒等路径（strength=0）又恰好落在
格点上，两者一致。于是"最大 1 LSB 之内"这条验收口径永远绿，而全图其实一直偏暗半级。
D&B 是第一个把 gain≈1 的输出精确送回格点的算子，才把这笔账顶出来。

所以这里只留一个出处：产品、CPU 参考、跑靶、测试都调它。各处自己写一份 `*255→uint8`
就是下一次同构坑的起点。
"""

from __future__ import annotations

import numpy as np

from .optional_dependencies import optional_module

torch = optional_module("torch")


def quantize_np(a: np.ndarray) -> np.ndarray:
    """[0,1] 浮点 → uint8，四舍五入（.5 取偶，与 torch.round 同一条 IEEE 语义），越界夹端点。

    升 float64 再算：float32 下 `x*255` 的舍入会把“恰好半档”的边界往任一边推，
    而 CPU 参考的职责就是当那个不受生产精度影响的基准。这一步只在非热路径上跑
    （对照臂、测试、导出收尾）；GPU 侧不升 float64——消费级卡的 f64 吞吐是 1/32。
    """
    x = np.asarray(a, dtype=np.float64) if np.asarray(a).dtype != np.float64 else np.asarray(a)
    return np.clip(np.rint(np.clip(x, 0.0, 1.0) * 255.0), 0.0, 255.0).astype(np.uint8)


def quantize_t(t):
    """[0,1] 显存张量 → uint8，与 quantize_np 同语义（两边都是 IEEE 取偶舍入）。

    先 round 再 to(uint8)：torch 的 `.to(uint8)` 是向零截断，与 numpy 的 astype 同病。
    用非就地 clamp：入参可能是常驻缓存，改了就等于把缓存本身刷掉一档。
    """
    return (t.clamp(0.0, 1.0) * 255.0).round().to(torch.uint8)


def dequantize(u8: np.ndarray, dtype=np.float32) -> np.ndarray:
    """uint8 → [0,1] 浮点。正向口径，测试与跑靶都靠它跟 quantize_* 对齐。"""
    return np.asarray(u8).astype(dtype) / dtype(255.0)


def quantize16_np(a: np.ndarray, *, chunk_pixels: int = 1 << 18) -> np.ndarray:
    """Normalized floating RGB -> RGB16, one final nearest-even quantization.

    Bound float64 temporaries by image tiles; preserve the input array and reject
    nonfinite values instead of letting a cast turn NaNs into plausible pixels.
    """
    a = np.asarray(a)
    if a.ndim != 3 or a.shape[2] != 3 or a.dtype.kind != "f":
        raise ValueError("quantize16_np requires floating (H,W,3) RGB")
    h, w = a.shape[:2]
    budget = int(chunk_pixels)
    if budget <= 0 or not h or not w:
        raise ValueError("image and quantization budget must be positive")
    columns = min(w, budget)
    rows = max(1, budget // columns)
    out = np.empty(a.shape, dtype=np.uint16)
    for y in range(0, h, rows):
        for x in range(0, w, columns):
            block = np.asarray(a[y:y + rows, x:x + columns], dtype=np.float64)
            if not np.isfinite(block).all():
                raise ValueError("nonfinite RGB cannot be quantized")
            out[y:y + rows, x:x + columns] = np.clip(
                np.rint(np.clip(block, 0, 1) * 65535), 0, 65535).astype(np.uint16)
    return out
