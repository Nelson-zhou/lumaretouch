"""共享内存裸帧通路的正确性测试。"""

from __future__ import annotations

import os

import numpy as np
import pytest

from lumaretouch_engine.shm import (GLOBAL_HDR, MAGIC, SLOT_HDR, VERSION, FrameShm,
                                    monotonic_ns, shm_name)

HERE_CWD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_byte_layout_is_pinned():
    """跨语言结构体布局契约（Rust 读端按下标直读，这里钉死）。"""
    px = 640 * 480 * 4
    slot_size = SLOT_HDR.size + px
    buf = bytearray(64)
    GLOBAL_HDR.pack_into(buf, 0, MAGIC, VERSION, 2, 640, 480, px, slot_size,
                         GLOBAL_HDR.size + 2 * slot_size, b"")

    def u32(o):
        return int.from_bytes(buf[o:o + 4], "little")

    assert bytes(buf[0:4]) == b"LRSH"
    assert (u32(4), u32(8), u32(12), u32(16)) == (2, 2, 640, 480)
    assert (u32(20), u32(24), u32(28)) == (px, slot_size, 64 + 2 * slot_size)

    s = bytearray(64)
    seq, t_ns = 7, 1_234_567_890_123  # 大于 2^32 的纳秒时间戳
    SLOT_HDR.pack_into(s, 0, seq, t_ns, 640, 480, 0, b"")
    assert int.from_bytes(s[0:8], "little") == seq
    assert int.from_bytes(s[8:16], "little") == t_ns, "t_ns 必须占 8 字节"
    assert int.from_bytes(s[16:20], "little") == 640
    assert int.from_bytes(s[20:24], "little") == 480


@pytest.fixture
def shm(request):
    name = f"lrt-test-{os.getpid()}-{request.node.name}"[:60]
    buf = FrameShm(shm_name(name), 64, 32, slots=2, create=True)
    yield buf
    buf.close()
    buf.unlink()


def test_struct_sizes_are_64():
    assert GLOBAL_HDR.size == 64
    assert SLOT_HDR.size == 64


def test_layout_math(shm):
    assert shm.pixel_size == 64 * 32 * 4
    assert shm.slot_size == SLOT_HDR.size + shm.pixel_size
    assert shm.total == GLOBAL_HDR.size + shm.slot_size * 2
    assert os.path.getsize(shm.path) == shm.total


def test_roundtrip_pixels(shm):
    frame = np.arange(shm.pixel_size, dtype=np.uint8).reshape(32, 64, 4)
    seq, t_ns, slot = shm.write_frame(frame.tobytes())
    assert seq == 1
    assert slot == 0
    assert np.frombuffer(shm.read_pixels(slot), np.uint8).tolist() == frame.reshape(-1).tolist()
    assert shm.meta_of(slot)[:4] == (seq, t_ns, 64, 32)


def test_write_frame_accepts_ndarray_without_tobytes(shm):
    """跑靶/生产通路直接交 numpy 缓冲：省掉每帧一次 tobytes() 的全帧拷贝。"""
    frame = np.arange(shm.pixel_size, dtype=np.uint8).reshape(32, 64, 4)
    seq, _, slot = shm.write_frame(frame)
    assert seq == 1
    assert shm.read_pixels(slot) == frame.tobytes()
    # 长度不符必须拒，不能把半帧当成完整帧提交
    with pytest.raises(ValueError):
        shm.write_frame(np.zeros(shm.pixel_size - 4, np.uint8))
    # 非连续内存必须拒：长度对得上，但缓冲协议会静默交出错位的字节
    with pytest.raises((TypeError, ValueError)):
        shm.write_frame(np.transpose(frame, (1, 0, 2)))


def test_slots_alternate_and_unwritten_slot_keeps_previous_frame(shm):
    a = np.zeros(shm.pixel_size, np.uint8)
    b = np.full(shm.pixel_size, 255, np.uint8)
    _, _, s0 = shm.write_frame(a.tobytes())
    _, _, s1 = shm.write_frame(b.tobytes())
    assert (s0, s1) == (0, 1)
    # 第 3 帧覆盖 slot0 之前，slot1 的最新提交内容必须仍然可读且完整
    _, _, s2 = shm.write_frame(a.tobytes())
    assert s2 == 0
    assert shm.read_pixels(1) == b.tobytes()


def test_freshest_tracks_last_commit(shm):
    z = np.zeros(shm.pixel_size, np.uint8)
    shm.write_frame(z.tobytes())
    seq2, _, _ = shm.write_frame(z.tobytes())
    fresh = shm.freshest()
    assert fresh is not None
    assert fresh[0] == seq2
    assert fresh[5] == 1


def test_second_opener_reads_header_and_matches(shm):
    peer = FrameShm(shm.name)
    try:
        assert (peer.w, peer.h) == (64, 32)
        assert peer.pixel_size == shm.pixel_size
        assert peer.slot_size == shm.slot_size
    finally:
        peer.close()


def test_rejects_wrong_frame_size(shm):
    with pytest.raises(ValueError):
        shm.write_frame(b"\x00" * 123)


def test_rejects_corrupt_header(shm):
    shm._buf[0:4] = b"XXXX"
    with pytest.raises(ValueError):
        FrameShm(shm.name)


def test_written_frame_is_visible_to_a_second_process():
    """直接盯住 MAP_SHARED：同进程里互相看得见不算数。"""
    import subprocess
    import sys

    pixels = bytes(range(256)) * (32 * 64 * 4 // 256)
    seq, t_ns, slot = None, None, None
    buf = FrameShm(shm_name(f"xproc-{os.getpid()}"), 64, 32, create=True)
    try:
        seq, t_ns, slot = buf.write_frame(pixels)
        code = (
            "import sys;sys.path.insert(0, 'src');"
            "from lumaretouch_engine.shm import FrameShm;"
            f"p=FrameShm({buf.name!r});"
            f"m=p.meta_of({slot});print(m[0], m[1], len(p.read_pixels({slot})), "
            "p.read_pixels(%d)[:16] == bytes(range(16)))" % slot
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           cwd=HERE_CWD)
        assert r.returncode == 0, r.stderr[-400:]
        got_seq, got_t, got_len, ok = r.stdout.split()
        assert int(got_seq) == seq and int(got_t) == t_ns
        assert int(got_len) == buf.pixel_size
        assert ok == "True", "子进程看不到写入的像素 → 不是共享映射"
    finally:
        buf.close()
        buf.unlink()


def test_monotonic_ns_is_cross_process_comparable():
    """跨进程时间戳必须同基且真的是纳秒整数，否则延迟数据全部作废。"""
    import subprocess
    import sys

    code = "import time;print(time.clock_gettime_ns(time.CLOCK_MONOTONIC))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout
    child = int(out.strip())
    parent = monotonic_ns()
    assert isinstance(parent, int), "monotonic_ns 必须返回整数纳秒"
    assert parent > 1_000_000_000, "量级不像纳秒（怀疑用了 clock_gettime 秒浮点）"
    assert abs(parent - child) < 1_000_000_000, "跨进程时间戳不同基，端到端延迟数据不可信"
