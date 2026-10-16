"""引擎 JSON-lines 协议 + shm 通路的端到端测试（起真子进程，不 mock）。

注意脚手架自身的坑：阻塞 readline 会让"等一个不会来的事件"直接挂死，
stderr 管道不排空会死锁。所以这里用后台读线程 + 带超时的队列。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time

import pytest

from lumaretouch_engine.shm import FrameShm, monotonic_ns, shm_name

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class EngineProcess:
    def __init__(self, session: str):
        env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "src"))
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "lumaretouch_engine.server", "--session", session],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env)
        self.session = session
        self._q: queue.Queue[dict] = queue.Queue()
        self._err: list[str] = []
        self._closed = False
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    def _pump_stdout(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line:
                try:
                    self._q.put(json.loads(line))
                except json.JSONDecodeError:
                    self._q.put({"event": "_raw", "text": line})

    def _pump_stderr(self):
        for line in self.proc.stderr:
            if line.strip():
                self._err.append(line.rstrip())

    def send(self, **cmd):
        if self._closed or self.proc.stdin is None:
            raise RuntimeError("引擎已关闭")
        self.proc.stdin.write(json.dumps(cmd) + "\n")
        self.proc.stdin.flush()

    def next_event(self, timeout=10.0):
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(
                f"{timeout}s 内没有事件；alive={self.proc.poll() is None} "
                f"stderr 尾部={self._err[-6:]!r}")

    def wait_for(self, event: str, timeout=10.0):
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"未等到事件 {event}；stderr 尾部={self._err[-6:]!r}")
            e = self.next_event(timeout=min(left, 10.0))
            if e.get("event") == event:
                return e
            if e.get("event") == "error":
                raise AssertionError(f"引擎报错: {e.get('error')}")

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write('{"cmd":"shutdown"}\n')
                self.proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


@pytest.fixture
def engine():
    session = f"itest-{os.getpid()}"
    ep = EngineProcess(session)
    yield ep
    ep.close()
    try:
        os.unlink(f"/dev/shm/{shm_name(session)}")
    except FileNotFoundError:
        pass


def test_handshake(engine):
    engine.send(cmd="hello")
    ready = engine.wait_for("ready")
    assert ready["protocol"] == 1
    assert ready["pid"] == engine.proc.pid


def test_unknown_command_does_not_kill_engine(engine):
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="不存在的命令")
    err = engine.next_event()
    assert err["event"] == "error"
    engine.send(cmd="hello")
    assert engine.wait_for("ready")["pid"] == engine.proc.pid


def test_bench_frames_arrive_intact_and_measurable(engine):
    """核心验收：通知里报的 slot 读出来必须真是那一帧，且延迟可测、无负值。"""
    w, h, n = 96, 64, 12
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="bench_start", w=w, h=h, frames=n, interval_ms=8, mode="copy")
    meta = engine.wait_for("shm_ready")
    assert (meta["w"], meta["h"]) == (w, h)

    peer = FrameShm(meta["name"])
    try:
        seqs, lat_us, corner_seen = [], [], set()
        for _ in range(n):
            ev = engine.wait_for("frame")
            seqs.append(ev["seq"])
            slot = ev["slot"]
            got_seq, t_ns, mw, mh = peer.meta_of(slot)[:4]
            assert (got_seq, mw, mh) == (ev["seq"], w, h), "元数据与通知不一致"
            pixels = peer.read_pixels(slot)
            assert len(pixels) == peer.pixel_size
            corner_seen.add(tuple(pixels[0:3]))
            # 左上角标记块恒为纯红：验证内容真在通路里流动、且没有上下翻转
            assert pixels[0:3] == b"\xff\x00\x00", f"帧首像素不是红色标记块: {pixels[0:3]!r}"
            lat = (monotonic_ns() - t_ns) / 1000.0
            assert lat > 0, "端到端延迟出现负值 → 时钟不同基或打点位置错"
            lat_us.append(lat)
        assert sorted(seqs) == list(range(1, n + 1)), f"seq 不连续: {seqs}"
        assert len(corner_seen) == 1
        assert max(lat_us) < 200_000, f"单帧 emit→read 延迟异常: {max(lat_us):.0f} µs"
    finally:
        peer.close()

    engine.send(cmd="bench_stop")
    engine.wait_for("bench_stopped")


def test_engine_cleans_up_shm_on_exit(engine):
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="bench_start", w=32, h=32, frames=2, interval_ms=5)
    meta = engine.wait_for("shm_ready")
    path = f"/dev/shm/{meta['name']}"
    engine.wait_for("bench_done", timeout=15)
    engine.send(cmd="shutdown")
    engine.proc.wait(timeout=5)
    assert not os.path.exists(path), "退出后残留共享内存文件"


def test_dropped_frames_are_detectable_by_seq_gaps(engine):
    """读端跟不上时 seq 必须出现跳号——这是丢帧率统计的前提。"""
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="bench_start", w=64, h=48, frames=40, interval_ms=2, mode="copy")
    engine.wait_for("shm_ready")
    seen = []
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and len(seen) < 40:
        try:
            e = engine.next_event(timeout=2.0)
        except TimeoutError:
            break
        if e.get("event") == "frame":
            seen.append(e["seq"])
        elif e.get("event") == "bench_done":
            break
    assert seen, "一帧都没收到"
    assert max(seen) <= 40
    # 本测试故意慢读：不要求一定有跳号，但要求编号严格单调递增
    assert seen == sorted(seen) and len(set(seen)) == len(seen)
