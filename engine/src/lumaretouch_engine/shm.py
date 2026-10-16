"""共享内存裸帧通路。

布局（单块 POSIX 共享内存，双槽 ping-pong）：

  偏移 0    全局头 64B   magic/version/slot 数/尺寸
  偏移 64   槽 0：元数据 64B + 像素 w*h*4
            槽 1：元数据 64B + 像素 w*h*4

提交语义：**先写像素、最后写元数据**，元数据里的 seq 即提交标记。
读取方轮询两个槽的 seq，取更大的那个——写入方永远在另一个槽上，
因此读者不会读到写一半的帧。

内存序说明（M0 已知简化）：Python 侧依赖 CPython 的 GIL 与 memcpy 完成
后再 pack_into，实测足够；正式实现需在 Rust 侧用原子/栅栏替换 seq 写入。

跨进程时间戳统一 CLOCK_MONOTONIC 纳秒：引擎在“帧可读”时刻打 t_emit，
UI 侧在收到绘制回执时打 t_ack，同基直接相减即端到端延迟，无需时钟校准。
"""

from __future__ import annotations

import mmap
import os
import struct
import time

MAGIC = b"LRSH"
VERSION = 1

# 4s + 7*I + 32s = 4 + 28 + 32 = 64
GLOBAL_HDR = struct.Struct("<4sIIIIIII32s")
# seq(Q) + t_ns(Q) + w(I) + h(I) + fourcc(I) + 保留 36s = 8+8+4+4+4+36 = 64
# t_ns 必须是 64 位：开机的 ns 数早已超过 2^32（约 4.3 秒）
SLOT_HDR = struct.Struct("<QQIII36s")

HEADER_SIZE = GLOBAL_HDR.size
SLOT_META_SIZE = SLOT_HDR.size
FOURCC_RGBA8 = 0x41424752  # 'RGBA'


def monotonic_ns() -> int:
    # 必须用 clock_gettime_ns：clock_gettime 返回秒浮点，相减会错六个数量级
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


class FrameShm:
    """引擎侧写端 / UI 侧读端共享的同一块缓冲。"""

    def __init__(self, name: str, width: int = 0, height: int = 0,
                 slots: int = 2, create: bool = False):
        self.name = name
        self.path = f"/dev/shm/{name}"
        self.slots = slots
        self._seq = 0
        self._slot = 0

        if create:
            if width <= 0 or height <= 0:
                raise ValueError("创建模式必须给出 width/height")
            self.w, self.h = width, height
            self.pixel_size = width * height * 4
            self.slot_size = SLOT_META_SIZE + self.pixel_size
            self.total = HEADER_SIZE + self.slot_size * slots
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_TRUNC, 0o600)
            try:
                os.ftruncate(fd, self.total)
            except OSError:
                os.close(fd)
                raise
            self._fd = fd
            # 跨进程共享必须显式 MAP_SHARED；默认值因版本而异，不能赌
            self._buf = mmap.mmap(fd, self.total, flags=mmap.MAP_SHARED,
                                  access=mmap.ACCESS_WRITE)
            self._write_global()
        else:
            self._fd = os.open(self.path, os.O_RDWR)
            self._buf = mmap.mmap(self._fd, 0, flags=mmap.MAP_SHARED,
                                  access=mmap.ACCESS_WRITE)
            self.total = self._buf.size()
            magic, version, slots, w, h, pixel_size, slot_size, _total, _rsv = self.read_global()
            if magic != MAGIC or version != VERSION:
                raise ValueError(f"共享内存头不匹配: magic={magic!r} version={version}")
            self.slots, self.w, self.h = slots, w, h
            self.pixel_size, self.slot_size = pixel_size, slot_size

    # ---- 全局头 ----------------------------------------------------------
    def _write_global(self) -> None:
        # 绑定方法签名：pack_into(buffer, offset, *values)
        GLOBAL_HDR.pack_into(self._buf, 0, MAGIC, VERSION, self.slots, self.w, self.h,
                             self.pixel_size, self.slot_size, self.total, b"")

    def read_global(self):
        return GLOBAL_HDR.unpack_from(self._buf, 0)

    # ---- 槽位 ------------------------------------------------------------
    def _slot_offset(self, i: int) -> int:
        return HEADER_SIZE + i * self.slot_size

    def write_frame(self, pixels, fourcc: int = FOURCC_RGBA8,
                    t_ns: int | None = None) -> tuple[int, int, int]:
        """写入一帧，返回 (seq, t_emit_ns, slot)。t_emit 在像素落地后打点。

        pixels 可以是 bytes，也可以是 C 连续的 numpy 数组：后者直接走缓冲协议，
        省掉一次 tobytes() 的全帧分配和拷贝（1280x800 就是 4 MB/帧）。
        """
        mv = memoryview(pixels).cast("B")
        if mv.nbytes != self.pixel_size:
            raise ValueError(f"像素长度 {mv.nbytes} != 期望 {self.pixel_size}")
        i = self._slot
        self._slot = (self._slot + 1) % self.slots
        off = self._slot_offset(i)
        # 1) 像素
        self._buf[off + SLOT_META_SIZE:off + self.slot_size] = mv
        # 2) 提交标记 + 打点
        self._seq += 1
        seq = self._seq
        t = t_ns if t_ns is not None else monotonic_ns()
        SLOT_HDR.pack_into(self._buf, off, seq, t, self.w, self.h, fourcc, b"")
        return seq, t, i

    def meta_of(self, slot: int) -> tuple[int, int, int, int, int]:
        return SLOT_HDR.unpack_from(self._buf, self._slot_offset(slot))[:5]

    def freshest(self) -> tuple[int, int, int, int, int, int] | None:
        """返回 (seq, t_ns, w, h, fourcc, slot)：seq 最大的已提交槽。"""
        best = None
        for i in range(self.slots):
            m = self.meta_of(i)
            if m[0] and (best is None or m[0] > best[0]):
                best = (m[0], m[1], m[2], m[3], m[4], i)
        return best

    def pixel_slice(self, slot: int) -> tuple[int, int]:
        off = self._slot_offset(slot) + SLOT_META_SIZE
        return off, off + self.pixel_size

    def read_pixels(self, slot: int) -> bytes:
        a, b = self.pixel_slice(slot)
        return self._buf[a:b]

    def close(self) -> None:
        self._buf.close()
        os.close(self._fd)

    def unlink(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass


def shm_name(session: str) -> str:
    return f"lumaretouch-{session}"
