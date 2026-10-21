"""共享内存裸帧通路。

布局（单块 POSIX 共享内存，双槽 ping-pong）：

  偏移 0    全局头 64B   magic/version/slot 数/尺寸
  偏移 64   槽 0：元数据 64B + 像素 w*h*4
            槽 1：元数据 64B + 像素 w*h*4

提交语义：先写像素、最后写元数据；整个写入持有 flock 排他锁。读端必须在
同一共享锁内选择帧并复制像素。双槽本身不能防止慢读者被两帧后的写入覆盖；
CPython GIL 也不保护另一个进程。协议 v2 拒绝没有锁契约的旧读端。

跨进程时间戳统一 CLOCK_MONOTONIC 纳秒：引擎在“帧可读”时刻打 t_emit，
UI 侧在收到绘制回执时打 t_ack，同基直接相减即端到端延迟，无需时钟校准。
"""

from __future__ import annotations

import mmap
import fcntl
import threading
from contextlib import contextmanager
import os
import struct
import time
import uuid

MAGIC = b"LRSH"
VERSION = 2
IDENTITY_TAG = b"LRI1"

def frame_identity(reserved):
    if len(reserved)!=32 or reserved[:4]!=IDENTITY_TAG or any(reserved[20:]):return None
    value=reserved[4:20]
    return value if any(value) else None

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
        self._thread_lock = threading.RLock()
        self.name = name
        self.path = f"/dev/shm/{name}"
        self.slots = slots
        self._seq = 0
        self._slot = 0
        self.instance_id = uuid.uuid4().bytes if create else None

        if not isinstance(name, str) or not name or "/" in name or "\0" in name:
            raise ValueError("invalid shared-memory name")
        if create:
            if width <= 0 or height <= 0 or slots <= 0:
                raise ValueError("创建模式必须给出正 width/height/slots")
            self.w, self.h = width, height
            self.pixel_size = width * height * 4
            self.slot_size = SLOT_META_SIZE + self.pixel_size
            self.total = HEADER_SIZE + self.slot_size * slots
            if self.total > 0xffffffff:
                raise ValueError("shared-memory layout exceeds uint32 protocol limit")
        self._fd = os.open(self.path, os.O_CREAT | os.O_RDWR if create else os.O_RDWR, 0o600)
        self._buf = None
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX if create else fcntl.LOCK_SH)
            try:
                if create:
                    # Truncation must also respect active readers, not happen in open().
                    os.ftruncate(self._fd, self.total)
                else:
                    self.total = os.fstat(self._fd).st_size
                    if self.total < HEADER_SIZE:
                        raise ValueError("shared-memory header truncated")
                self._buf = mmap.mmap(self._fd, self.total, flags=mmap.MAP_SHARED,
                                      access=mmap.ACCESS_WRITE)
                if create:
                    # Same-size ftruncate preserves old bytes. A new instance must
                    # not inherit nonzero commit sequences from the old producer.
                    for slot in range(self.slots):
                        off = self._slot_offset(slot)
                        self._buf[off:off + SLOT_META_SIZE] = bytes(SLOT_META_SIZE)
                    self._write_global()
                else:
                    magic, version, slots, w, h, pixels, stride, total, _rsv = self.read_global()
                    if magic != MAGIC or version != VERSION:
                        raise ValueError(f"共享内存头不匹配: magic={magic!r} version={version}")
                    if (slots <= 0 or w <= 0 or h <= 0 or pixels != w*h*4
                            or stride != SLOT_META_SIZE+pixels
                            or total != HEADER_SIZE+slots*stride or total != self.total):
                        raise ValueError("shared-memory layout is inconsistent")
                    self.slots, self.w, self.h = slots, w, h
                    self.pixel_size, self.slot_size = pixels, stride
                    self.instance_id = frame_identity(_rsv)
            finally:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        except BaseException:
            if self._buf is not None: self._buf.close()
            os.close(self._fd)
            raise

    # ---- 全局头 ----------------------------------------------------------
    def _write_global(self) -> None:
        # 绑定方法签名：pack_into(buffer, offset, *values)
        GLOBAL_HDR.pack_into(self._buf, 0, MAGIC, VERSION, self.slots, self.w, self.h,
                             self.pixel_size, self.slot_size, self.total, IDENTITY_TAG+self.instance_id+b"\0"*12)

    def read_global(self):
        return GLOBAL_HDR.unpack_from(self._buf, 0)

    # ---- 槽位 ------------------------------------------------------------
    def _slot_offset(self, i: int) -> int:
        return HEADER_SIZE + i * self.slot_size

    def write_frame(self, pixels, fourcc: int = FOURCC_RGBA8,
                    t_ns: int | None = None, *, presentation=None) -> tuple[int, int, int]:
        """写入一帧，返回 (seq, t_emit_ns, slot)。t_emit 在像素落地后打点。

        pixels 可以是 bytes，也可以是 C 连续的 numpy 数组：后者直接走缓冲协议，
        省掉一次 tobytes() 的全帧分配和拷贝（1280x800 就是 4 MB/帧）。
        """
        reserved = presentation.pack() if presentation is not None else bytes(36)
        mv = memoryview(pixels).cast("B")
        if mv.nbytes != self.pixel_size:
            raise ValueError(f"像素长度 {mv.nbytes} != 期望 {self.pixel_size}")
        with self.frame_lock(exclusive=True):
            i = self._slot
            self._slot = (self._slot + 1) % self.slots
            off = self._slot_offset(i)
            # 1) 像素
            self._buf[off + SLOT_META_SIZE:off + self.slot_size] = mv
            # 2) 提交标记 + 打点
            self._seq += 1
            seq = self._seq
            t = t_ns if t_ns is not None else monotonic_ns()
            SLOT_HDR.pack_into(self._buf, off, seq, t, self.w, self.h, fourcc, reserved)
            return seq, t, i

    @contextmanager
    def frame_lock(self, *, exclusive=False):
        """One lock spans metadata selection AND the entire pixel copy."""
        with self._thread_lock:
            fcntl.flock(self._fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                if os.fstat(self._fd).st_size != self.total:
                    raise ValueError("shared-memory size changed; reopen after shm_ready")
                if frame_identity(self.read_global()[-1]) != self.instance_id:
                    raise ValueError("shared-memory instance changed; reopen after shm_ready")
                yield
            finally:
                fcntl.flock(self._fd, fcntl.LOCK_UN)

    def read_snapshot(self, slot=None, expected_seq=None):
        """Return (metadata-with-slot, copied bytes), or None for a stale event.

        Notifications can legitimately outlive their two-slot frame. Never label
        newer pixels with the old notification's sequence number.
        """
        with self.frame_lock():
            if slot is None:
                meta = self.freshest()
            else:
                if not isinstance(slot, int) or not 0 <= slot < self.slots:
                    raise ValueError('invalid frame slot')
                meta = (*self.meta_of(slot), slot)
            if meta is None or not meta[0] or (expected_seq is not None and meta[0] != expected_seq):
                return None
            return meta, self.read_pixels(meta[-1])

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
