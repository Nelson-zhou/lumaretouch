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
import importlib.util

import numpy as np
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


def test_unknown_bench_mode_is_rejected(engine):
    """模式名写错不能默默当成 copy 跑：那样会得到一份「管线根本没跑」但看上去完全正常的数据。"""
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="bench_start", w=32, h=32, frames=2, interval_ms=5, mode="pipeline_residentd")
    ev = engine.next_event()
    assert ev["event"] == "error", f"预期报错，实际收到 {ev}"
    assert "模式" in ev["error"]


def test_resident_mode_runs_and_emits_varying_frames(engine):
    """M1-2 的常驻模式必须在真子进程里跑通，且帧内容真的在换。

    GPU 上的数值一致性由 test_vram 的 GPU 用例覆盖；这里只验协议与分段计时结构，
    所以固定跑 CPU 后端，不依赖本机有没有显卡——但仍依赖 torch 本身存在。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻模式要 torch；CI 的 CPU job 只装 numpy+pytest（子进程用的是同一个解释器）")
    w, h, n = 96, 64, 6
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    engine.send(cmd="bench_start", w=w, h=h, frames=n, interval_ms=8, mode="pipeline_resident")
    meta = engine.wait_for("shm_ready")
    peer = FrameShm(meta["name"])
    stamps = []
    try:
        for _ in range(n):
            ev = engine.wait_for("frame", timeout=30)
            assert ev["mode"] == "pipeline_resident"
            assert peer.meta_of(ev["slot"])[0] == ev["seq"], "元数据与通知不一致"
            arr = np.frombuffer(peer.read_pixels(ev["slot"]), np.uint8).reshape(h, w, 4)
            stamps.append(int(arr[16, 16, 2]))
            assert int(arr[0, 0, 3]) == 255, "常驻帧缓冲的 alpha 被洗掉了"
        done = engine.wait_for("bench_done", timeout=30)
        assert not done.get("failed"), f"跑靶线程报错了: {done}"
        # 只断言能稳住在微秒以上的量：96×64 的回读在 CPU 上不到 3 µs，6 帧均值会舍入成 0.0
        assert done["kernel"] > 0, "常驻路径的滤波内核没真跑"
        assert done["pre"] == 0 and done["cpu_post"] == 0, "常驻路径不该还有逐帧搬运段"
        assert done["synth"] == 0, "常驻路径不该每帧重算源图"
    finally:
        peer.close()
    assert len(set(stamps)) == n, f"序号指纹没有逐帧变化: {stamps}"


FIXTURE = os.path.join(HERE, "tests", "fixtures", "portrait-1024x1280.jpg")


@pytest.mark.skipif(not os.path.isfile(FIXTURE),
                    reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_load_image_and_drag_stream_real_photo(engine):
    """M1-3a 端到端：真图导入 → 代理档 → 常驻显存 → shm 里的帧能被独立读出来比对。

    这同时是验收口径③的端到端版本：strength=0 时 shm 帧的 RGB 必须与测试进程
    独立解码出的代理图逐字节一致；拖一下滑块之后帧必须真的变了。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    from lumaretouch_engine.decode import load_rgb

    ref = load_rgb(FIXTURE)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0)
    shm_meta = engine.wait_for("shm_ready", timeout=60)
    assert (shm_meta["w"], shm_meta["h"]) == (ref.w, ref.h), "shm 没按代理档开"
    engine.wait_for("vram_ready", timeout=60)
    ready = engine.wait_for("image_ready", timeout=60)
    assert (ready["src_w"], ready["src_h"]) == (1024, 1280)
    assert ready["decode_ms"] > 0 and ready["total_ms"] >= ready["decode_ms"]
    assert ready["bytes_per_frame"] <= 960 * 600 * 4, "代理档越了字节预算"

    peer = FrameShm(shm_meta["name"])
    try:
        ev = engine.wait_for("frame", timeout=30)
        got = np.frombuffer(peer.read_pixels(ev["slot"]), np.uint8).reshape(ref.h, ref.w, 4)
        assert (got[:, :, 3] == 255).all()
        d = np.abs(got[:, :, :3].astype(np.int16) - ref.rgb.astype(np.int16))
        assert d.max() == 0, f"strength=0 上屏帧与解码原图差 {int(d.max())} LSB"

        engine.send(cmd="set_strength", value=0.75)
        engine.wait_for("params_set", timeout=30)
        ev2 = engine.wait_for("frame", timeout=30)
        assert ev2["seq"] > ev["seq"], "拖滑块没发新帧"
        got2 = np.frombuffer(peer.read_pixels(ev2["slot"]), np.uint8).reshape(ref.h, ref.w, 4)
        moved = int((np.abs(got2[:, :, :3].astype(np.int16) - got[:, :, :3].astype(np.int16)) > 0).sum())
        assert moved > 0, "strength 从 0 拉到 0.75 画面一点没变"
        # 磨皮应当削高频而不是抹平结构：横向一阶差的能量必须降下来
        def hf(a):
            return float(np.abs(np.diff(a.astype(np.float32), axis=1)).mean())
        assert hf(got2[:, :, 0]) < hf(got[:, :, 0]), "磨皮没在削高频，管线可能根本没接上"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE),
                    reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_set_device_migrates_resident_session(engine):
    """换设备得把已建立的常驻会话一起带走，而且上报必须说真话。

    F 轮第一轮的坑：先 load_image（此时引擎还是默认的 cpu）再 set_device cuda，
    旧张量静静留在 CPU 上跑了 600 帧（91 ms/帧），bench_done 照旧报 cuda:true。
    这种数据内部完全自洽，只有拿「真正跑了这些帧的设备」 against 声明值才能看见，
    所以这个字段进了协议，这条用例就是它的锁。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    import torch

    has_cuda = torch.cuda.is_available()
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0)
    shm_meta = engine.wait_for("shm_ready", timeout=60)
    v0 = engine.wait_for("vram_ready", timeout=60)
    assert v0["device"] == "cpu", f"默认设备下不该建在 {v0['device']} 上"
    engine.wait_for("image_ready", timeout=60)

    # 先切回同一个设备：会话没动，不该重建（拿这个区分「真迁移」和「每次调用都重连」）
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    # 再切到目标设备
    engine.send(cmd="set_device", device="cuda")
    engine.wait_for("device_set", timeout=30)
    if has_cuda:
        v1 = engine.wait_for("vram_ready", timeout=60)
        assert v1["device"].startswith("cuda"), f"切了 cuda 但会话还在 {v1['device']}"
        assert (v1["w"], v1["h"]) == (v0["w"], v0["h"]), "迁移后代理档尺寸变了"

    # 最后拿 bench_done 的 pipe_device 兜底：这才是跑靶表里该信的那个字段
    engine.send(cmd="bench_start", w=shm_meta["w"], h=shm_meta["h"], frames=12,
                interval_ms=1.0, mode="image_stream")
    done = engine.wait_for("bench_done", timeout=90)
    assert not done.get("failed"), f"bench 没跑成：{done}"
    expect = "cuda" if has_cuda else "cpu"
    got = (done.get("pipe_device") or "").split(":")[0]
    assert got == expect, f"声明 cuda 但真正跑帧的设备是 {done.get('pipe_device')}"

