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
        # M2-a 把这条的断言方向改了。原话是“磨皮应当削高频”——那恰好是 M2-a
        # 要避免的东西：把肌理一并削掉就是“塑料脸”的数值定义。现在卡的是
        # **皮肤区的细带必须留住**（毛孔还在），同时画面真的改了、但改幅在合理区间。
        # “去斑”那一半不靠这条测：整幅图的频带比例被发丝/眼睛/背景边缘占着，
        # 那些东西本来就不该动（导向滤波保边），拿它当“磨皮在干活”的证据只会得到 0.94
        # 这种看不出东西的数。去斑的量在 test_guided 的已知成分回归与 m2-skin-bench 里卡。
        from lumaretouch_engine.ops.guided import _box_np

        def _fine_u8(a):
            x = np.ascontiguousarray(a.astype(np.float32).transpose(2, 0, 1)[None]) / 255.0
            f = x - _box_np(x, 4)
            return float(f.std())

        keep = _fine_u8(got2[:, :, :3]) / max(_fine_u8(got[:, :, :3]), 1e-9)
        assert 0.95 <= keep <= 1.15, \
            f"上屏细带能量变了 {keep:.3f} 倍：纹理被抹掉了（偏低）或被增强了（偏高）"
        mean_delta = float(np.abs(got2[:, :, :3].astype(np.int16)
                                  - got[:, :, :3].astype(np.int16)).mean())
        assert 0.0 < mean_delta < 20.0, f"强度 0.75 的平均改动 {mean_delta:.2f} LSB 不合常理"
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



# ------------------------------------------------------- M1-3b：导入期预计算的协议与生命周期
def _expect_error(ep, contains: str, timeout: float = 30.0) -> dict:
    """等一条 error 事件并校验内容。

    不能复用 wait_for：它对 error 直接抛 AssertionError。这里要验的恰恰是
    「引擎按我们要求报了错」，所以得自己收事件。

    超时不能报成“没事件”了事：得把期间看到的事件种类与计数贴出来，否则
    「该拒绝却没拒」看起来与「跑靶根本没开起来」完全一样。
    """
    deadline = time.monotonic() + timeout
    seen: dict[str, int] = {}
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise AssertionError(
                f"{timeout}s 内没有 error 事件（期望包含 {contains!r}）；期间收到事件 {seen}")
        try:
            e = ep.next_event(timeout=min(left, 10.0))
        except TimeoutError:
            raise AssertionError(
                f"等 error({contains!r}) 超 10s 无声；期间收到事件 {seen}") from None
        kinds = e.get("event") or "?"
        seen[kinds] = seen.get(kinds, 0) + 1
        if e.get("event") == "error":
            assert contains in str(e.get("error", "")), f"报错内容不对：{e}"
            return e


def _load(engine, **kw):
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    # strength 可由调用方覆盖（M1-3c 的用例要从指定强度起步），默认仍是 0.0
    engine.send(cmd="load_image", path=FIXTURE, **{"strength": 0.0, **kw})
    meta = engine.wait_for("shm_ready", timeout=60)
    engine.wait_for("vram_ready", timeout=60)
    engine.wait_for("image_ready", timeout=60)
    return meta


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_precompute_contract_over_ipc(engine):
    """预计算回报的字段就是 M1-3c 要消费的契约：478 点 + 通道名 + 常驻设备 + 分段耗时。"""
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    meta = _load(engine)
    engine.send(cmd="precompute", backend="auto")
    ev = engine.wait_for("precompute_ready", timeout=60)
    assert ev["num_landmarks"] == 478, f"关键点数量不是 478：{ev['landmark_shape']}"
    assert ev["landmark_shape"] == [478, 3]
    assert ev["mask_channels"] and all(isinstance(c, str) for c in ev["mask_channels"])
    assert ev["mask_shape"][1:] == [meta["h"], meta["w"]], "掩膜必须对得上代理帧尺寸"
    assert ev["mask_bytes"] > 0 and ev["landmark_bytes"] > 0
    assert ev["resident_device"].split(":")[0] == "cpu"
    # 三种成本分开报；全塞一个总数就分不出该优化谁
    for k in ("build_ms", "infer_ms", "attach_ms"):
        assert ev[k] >= 0
    assert ev["total_ms"] >= ev["infer_ms"] > 0


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_precompute_requires_image_first(engine):
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="precompute", backend="auto")
    _expect_error(engine, "load_image")


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_explicit_missing_backend_is_an_error_not_a_quiet_substitute(engine):
    """点名要 mediapipe 就必须要么真跑、要么报错；不许退 synthetic 还说成功。

    这条守的是「废数据自洽」那个坑的另一半：如果 precompute_ready 里 backend 写着
    synthetic 而请求是 mediapipe，报表上就会出现一次"用真模型跑的预计算"，全是假的。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    _load(engine)
    engine.send(cmd="precompute", backend="mediapipe")
    _expect_error(engine, "后端不可用")
    # 拒绝之后不能留下半截状态：再来一次 auto 必须正常成功
    engine.send(cmd="precompute", backend="auto")
    ev = engine.wait_for("precompute_ready", timeout=60)
    assert ev["backend"] in ("synthetic", "mediapipe")


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_channel_selects_resident_mask_and_rejects_unknown(engine):
    """拖滑块指到掩膜通道：只换张量引用；不认识的通道名必须被拒。"""
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    _load(engine)
    engine.send(cmd="precompute", backend="auto")
    ev = engine.wait_for("precompute_ready", timeout=60)
    channel = ev["mask_channels"][0]
    engine.send(cmd="set_strength", value=0.6, channel=channel)
    ps = engine.wait_for("params_set", timeout=30)
    assert ps["channel"] == channel, "params_set 没回显生效通道，报表分不清是掩膜还是全图"
    engine.wait_for("frame", timeout=30)
    engine.send(cmd="set_strength", value=0.6, channel="hair")
    _expect_error(engine, "没有掩膜通道")


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_new_image_invalidates_previous_masks(engine):
    """换图必须清掉上一张的掩膜：拿别人的脸磨自己的皮，比没有掩膜更糟。"""
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    _load(engine)
    engine.send(cmd="precompute", backend="auto")
    engine.wait_for("precompute_ready", timeout=60)
    # 换一张完全不同尺寸的图（预算调大 → 代理档变），旧掩膜尺寸就对不上了
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0, max_px=1310720)
    engine.wait_for("image_ready", timeout=60)
    engine.send(cmd="set_strength", value=0.5, channel="skin")
    _expect_error(engine, "没有掩膜通道")


def _read_frame(engine, peer, h, w):
    ev = engine.wait_for("frame", timeout=30)
    return np.frombuffer(peer.read_pixels(ev["slot"]), np.uint8).reshape(h, w, 4)[:, :, :3].astype(np.int16)


def _nudge_frame(engine, strength):
    """发一条会出帧的命令，把“当前画面上到底是不是这个状态”变成一个能读的东西。

    precompute_ready 不出帧：刚经 precompute 就调 _read_frame 会空等 10 s（本轮就是这么
    错的）。而直接拿 shm 里旧帧当基线又不对：旧帧是 load_image 那一瞬的，中间只要
    有任何一条改图层的命令被丢弃，基线就与上报对不上。走一遍 set_strength 才是产品
    出帧的那条路。
    """
    engine.send(cmd="set_strength", strength=strength)
    return engine.wait_for("params_set", timeout=30)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_device_switch_keeps_the_active_channel_on_the_frame_it_emits(engine):
    """换设备补发的最后一帧必须仍按当前通道渲染。

    坑的形状：cmd_precompute 把 active_channel 照抄进 precompute_ready，可迁移路径里
    补发那帧的 render 没带 channel——于是报表写着「正在用皮肤掩膜」，屏幕上给的是全图
    磨皮。这跟「会话在 CPU 上跑却标 cuda」是同一个错误类别：上报字段没被实际执行路径
    约束过。所以这里不用事件字段作证据，直接读 shm 里的像素。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    import torch
    if not torch.cuda.is_available():
        pytest.skip("没有 GPU，验不了跨设备重挂")

    meta = _load(engine)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        _ = _read_frame(engine, peer, h, w)          # 先吃掉 load_image 那张，别让它混进对照
        engine.send(cmd="precompute", backend="auto")
        ev = engine.wait_for("precompute_ready", timeout=60)
        channel = ev["mask_channels"][0]

        # 同一系数下分别取「掩膜渲染」与「全图渲染」，两者必须不同，否则本用例没有鉴别力
        engine.send(cmd="set_strength", value=0.9, channel=channel)
        engine.wait_for("params_set", timeout=30)
        masked = _read_frame(engine, peer, h, w)
        engine.send(cmd="set_strength", value=0.9, channel=None)
        engine.wait_for("params_set", timeout=30)
        full = _read_frame(engine, peer, h, w)
        diff = np.abs(masked - full).mean(axis=-1)
        assert diff.max() >= 4, f"掩膜与全图渲染逐字节相同（{diff.max()} LSB），这条用例证不了任何事"
        gate = diff >= 1                       # 只有被门控区参与判定，避免拿全图噪声充数
        assert gate.mean() > 0.02, f"门控区只占 {gate.mean():.3f}，样本太小判不出方向"

        # 回到掩膜模式，然后换设备：迁移后补发的那一帧才是被测对象
        engine.send(cmd="set_strength", value=0.9, channel=channel)
        engine.wait_for("params_set", timeout=30)
        _ = _read_frame(engine, peer, h, w)
        engine.send(cmd="set_device", device="cuda")
        engine.wait_for("device_set", timeout=30)
        engine.wait_for("vram_ready", timeout=60)
        ev2 = engine.wait_for("precompute_ready", timeout=60)
        assert ev2["active_channel"] == channel, "重挂事件里的通道丢了"
        got = _read_frame(engine, peer, h, w)

        d_masked = float(np.abs(got - masked)[gate].mean())
        d_full = float(np.abs(got - full)[gate].mean())
        assert d_masked < d_full, (
            f"迁移后补发的帧走的是全图渲染（离掩膜 {d_masked:.2f} LSB / 离全图 {d_full:.2f} LSB），"
            f"而报表仍说 active_channel={ev2['active_channel']}")
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_set_strength_is_refused_while_bench_running(engine):
    """跑靶进行中必须拒绝拖滑块：两条线程都在写同一个常驻帧缓冲。

    `_wlock` 只护住「写 shm」那一步，护不到 `frame_gpu`：跑靶线程是
    pack(frame_gpu) → read_back() → 锁内写 shm，而 set_strength 的 render 也写同一个
    frame_gpu。落在跑靶那两个动作之间，跑靶就会把拖滑块的像素当成自己那一帧存——
    seq/slot 仍是配得上的，但「引擎侧那一帧」的证据从此对不上人。
    预计算/换图/换设备三条都早就有这条互斥，set_strength 是漏掉的那一个。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    # 用小代理档 + 长间隔：要的是“跑靶还活着”这段可控窗口，不是 CPU 上渲 200 帧
    meta = _load(engine, max_px=207360)
    engine.send(cmd="bench_start", w=meta["w"], h=meta["h"], frames=40,
                interval_ms=100.0, mode="image_stream")
    engine.wait_for("bench_started", timeout=30)
    engine.send(cmd="set_strength", value=0.5)
    _expect_error(engine, "跑靶进行中", timeout=20.0)
    # 拒绝不能把跑靶本身弄挂：跑完仍是正常一份数据
    engine.send(cmd="bench_stop")
    done = engine.wait_for("bench_done", timeout=90)
    assert not done.get("failed"), f"一次被拒的 set_strength 把跑靶带崩了：{done}"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_failed_precompute_leaves_no_resident_masks(engine):
    """失败的预计算不许留下「可用但没人知道」的掩膜。

    坑的形状：通道名校验放在 load_face 之后，失败时掩膜已经常驻、`_precompute` 已赋值，
    但 `precompute_ready` 没发过。于是宿主端只收到一个 error，下次换设备却突然收到一个
    replayed_for 事件——它从未见过初始状态；而 UI 报「没掩膜」的同一时刻，引擎里那张掩膜
    是可用且真的在参与渲染的。修法是把校验提到做任何改动之前。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    _load(engine)
    engine.send(cmd="precompute", backend="auto", channel="hair")     # 不存在的通道
    _expect_error(engine, "没有掩膜通道")
    # 上一句失败后，这张图的掩膜必须真的不在：否则 skin 会照常渲染成功
    engine.send(cmd="set_strength", value=0.5, channel="skin")
    _expect_error(engine, "没有掩膜通道")
    # 而且得能重新来过：一次拒绝不能把这个会话卡死
    engine.send(cmd="precompute", backend="auto", channel="skin")
    ev = engine.wait_for("precompute_ready", timeout=60)
    assert ev["active_channel"] == "skin", "重试后通道没生效"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_device_switch_replays_precompute(engine):
    """换设备重建会话后，预计算产物必须跟着重挂，否则下一次带通道的渲染会读到旧设备显存。"""
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    import torch
    if not torch.cuda.is_available():
        pytest.skip("没有 GPU，验不了跨设备重挂")
    _load(engine)
    engine.send(cmd="precompute", backend="auto")
    ev = engine.wait_for("precompute_ready", timeout=60)
    assert ev["resident_device"].startswith("cpu")
    engine.send(cmd="set_device", device="cuda")
    engine.wait_for("device_set", timeout=30)
    engine.wait_for("vram_ready", timeout=60)
    ev2 = engine.wait_for("precompute_ready", timeout=60)
    assert ev2.get("replayed_for") == "device_switch"
    assert ev2["resident_device"].startswith("cuda"), f"迁移后掩膜还在 {ev2['resident_device']}"
    assert ev2["mask_bytes"] == ev["mask_bytes"], "重挂的掩膜换了尺寸"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_drag_stream_refilters_nothing(engine):
    """M1-3c 的端到端主张：整场拖拽流里滤波一次都不重算。

    为什么必须在 IPC 层测：缓存写在常驻会话上，单元测试里手动调 retouch() 只能证明
    "传了参数会重算"，证明不了产品通路（跑靶的 warmup、参数默认值、会话归属）也把
    重算吃干净。这里读的是引擎自己上报的 refilter_frames，不是测试进程的推断。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")

    meta = _load(engine, max_px=207360, strength=0.5)
    engine.send(cmd="bench_start", mode="image_stream", frames=6, interval_ms=20,
                  w=meta["w"], h=meta["h"])
    engine.wait_for("bench_started", timeout=30)
    done = engine.wait_for("bench_done", timeout=90)
    assert not done.get("failed"), f"跑靶失败：{done}"
    assert done["refilter_frames"] == 0, \
        f"拖拽流里重算了 {done['refilter_frames']} 次滤波，零推理没成立"
    assert done["refilter_ms_total"] == 0.0, f"filter 段合计不为 0：{done['refilter_ms_total']}"
    # 参数必须随事件说清楚，否则"没重算"也可能只是"没真的跑滤波"。
    # M2-a 起把默认值当字面量写在这里：改了默认不算改产品，这条就是要能红。
    assert done["params"] == {"radius": 12, "eps": 6e-4, "texture_radius": 4,
                              "broad_gain": 0.0, "mid_gain": 0.0, "detail_gain": 1.0}, \
        done["params"]
    # 这里**不**卡逐帧时长：bench_done 的各段是“总时间 ÷ 帧数”的均值，6 帧的均值
    # 被一次调度抖动顶过 1 ms 是完全可能的（全套用例里真就这么红过一次，单跑又绿）。
    # 时序预算归 m1-drag-bench：那里是 60 帧×9 次交错取中位，量得起。协议测试只管契约。


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_filter_param_change_recomputes_once_and_reaches_the_pixels(engine):
    """改半径要重算一次，而且必须真的改到像素上。

    只回显参数而画面不动是这一类字段最常见的假绿：params_set 里 radius 变了、
    filter_ms 也 >0，看着一切正常，但渲染根本没接收这个参数。所以第二帧要和第一帧
    在像素上真的不同，而且下一次纯改 strength 要回到 filter_ms=0。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    from lumaretouch_engine.shm import FrameShm

    meta = _load(engine, max_px=207360, strength=0.6)
    peer = FrameShm(meta["name"])
    try:
        engine.send(cmd="set_strength", value=0.6)
        ev = engine.wait_for("params_set", timeout=30)
        assert ev["filter_ms"] == 0.0, f"纯拖强度也重算了滤波：{ev['filter_ms']} ms"
        assert ev["bands_ms"] == 0.0, f"纯拖强度连分带都重跑了：{ev['bands_ms']} ms"

        before = _read_frame(engine, peer, meta["h"], meta["w"])
        engine.send(cmd="set_strength", value=0.6, radius=18)
        ev2 = engine.wait_for("params_set", timeout=30)
        assert ev2["radius"] == 18, f"参数没回显：{ev2}"
        assert ev2["filter_ms"] > 0.0, "改了半径却没重算滤波——缓存键没含参数"
        assert ev2["bands_ms"] > 0.0, "改了半径却没重跑分带：分带键没算半径"
        after = _read_frame(engine, peer, meta["h"], meta["w"])
        changed = int((np.abs(after - before) > 0).sum())
        assert changed > 0, "半径从 12 改到 18，画面一个子像素都没动：参数只是回显了"

        # M2-a 第 2 层缓存：只改三个增益时，贵的分带一次也不重跑
        engine.send(cmd="set_strength", value=0.6, mid_gain=0.45, broad_gain=0.3)
        ev4 = engine.wait_for("params_set", timeout=30)
        assert ev4["filter_ms"] > 0.0, "改增益没重组：重组那一层没接上参数"
        assert ev4["bands_ms"] == 0.0, \
            f"只改增益却重跑了分带（{ev4['bands_ms']} ms）：两层缓存白拆了"
        gain_frame = _read_frame(engine, peer, meta["h"], meta["w"])
        assert int((np.abs(gain_frame - after) > 0).sum()) > 0, "增益改了画面不动"

        engine.send(cmd="set_strength", value=0.9)
        ev3 = engine.wait_for("params_set", timeout=30)
        assert ev3["radius"] == 18, f"新参数没记住：{ev3}"
        assert ev3["filter_ms"] == 0.0, f"同参数下又重算了：{ev3['filter_ms']} ms"
        assert ev3["bands_ms"] == 0.0, f"同参数下连分带都重跑了：{ev3['bands_ms']} ms"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_out_of_range_filter_params_are_refused_wholly(engine):
    """越界参数要当场拒绝，而且不能半应用。

    半径直接决定 reflect pad 之后的分配量（积分图窗口越大中间张量越大），一个
    radius=100000 就是一次显存爆炸；写进 self._params 但被渲染忽略更糟——报表说
    半径是 100000，屏幕上是 12。拒绝之后会话必须还能继续用。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")

    _load(engine, max_px=207360, strength=0.5)
    for kw in ({"radius": 100000}, {"radius": -3}, {"eps": -1.0}, {"detail_gain": 99.0},
               {"texture_radius": 64}, {"texture_radius": 0}, {"mid_gain": -0.1},
               {"broad_gain": 2.5}):
        engine.send(cmd="set_strength", value=0.5, **kw)
        err = _expect_error(engine, "超出范围")
        assert err["event"] == "error", err
        # 拒绝必须整条拒绝：值不能已经写进会话
        engine.send(cmd="set_strength", value=0.55)
        ev = engine.wait_for("params_set", timeout=30)
        for k, v in kw.items():
            assert ev[k] != v, f"{k}={v} 被拒绝了却写进了会话：{ev}"

    # 被拒绝之后通路仍然是活的（不是一次性错误把会话打死）
    assert ev["render_ms"] > 0


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_import_reports_the_one_time_filter_cost_separately(engine):
    """首帧里的一次性滤波必须单独上报，同时报出它换来的显存代价。

    坑的形状：M1-3c 之后 first_frame_ms 仍含那 4.5 ms，而拖拽期一帧只要 0.1 ms。
    只报一个 first_frame_ms，下一个人就会把它当成逐帧成本，或者把"导入变快了"当成
    "渲染变快了"。反过来，零推理不是免费的：多常驻一张 float RGB，不报字节数就是
    只报收益不报成本。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    from lumaretouch_engine.decode import load_rgb

    ref = load_rgb(FIXTURE)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cuda")
    engine.wait_for("device_set")
    engine.send(cmd="load_image", path=FIXTURE, strength=0.5)
    engine.wait_for("shm_ready", timeout=60)
    engine.wait_for("vram_ready", timeout=60)
    r = engine.wait_for("image_ready", timeout=60)
    expect_filter = ref.w * ref.h * 3 * 4
    assert r["bytes_filter"] == expect_filter, \
        f"滤波常驻字节数 {r['bytes_filter']} != 一张 float RGB {expect_filter}（{ref.w}x{ref.h}×3×4）"
    assert r["first_frame_filter_ms"] > 0, "首帧没报出一次性滤波成本，first_frame_ms 会被误读成逐帧成本"
    assert r["first_frame_ms"] >= r["first_frame_filter_ms"], \
        f"分段不自洽：整帧 {r['first_frame_ms']} 比它包含的滤波 {r['first_frame_filter_ms']} 还小"
    # 纯拖强度不应再付这笔：filter_ms=0 而首帧那次 >0，两个数一起才说明"只算了一次"
    engine.send(cmd="set_strength", value=0.7)
    ev = engine.wait_for("params_set", timeout=30)
    assert ev["filter_ms"] == 0.0, f"拖强度重算了滤波：{ev}"
    assert ev["cached"] is True, f"缓存没建立却说 cached：{ev}"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_eps_zero_is_refused_because_it_poisons_the_resident_cache(engine):
    """eps=0 必须当场拒绝：它会把 NaN 写进常驻缓存，并把 strength=0 的恒等打穿。

    实测（产品档 672×848，本轮取证）：radius=12/eps=0 时 `a = var/(var+eps)` 在平坦皮区
    0/0 → NaN，402795 个子像素为 NaN；缓存一旦收下这份结果，`(1-0)*img + 0*NaN` 也是 NaN
    （IEEE 里 0×NaN = NaN），pack 的 clamp 对 NaN 无定义，落到 uint8 后与解码原图差 255 LSB。
    也就是：一条合法形状的 set_strength 就能让"零强度=原图"这条验收口径整段会话失效。
    radius=0 同样是空滑块（s=0.5 与原图 0 处不同），一并卡下界。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    from lumaretouch_engine.decode import load_rgb
    from lumaretouch_engine.shm import FrameShm

    ref = load_rgb(FIXTURE)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cuda")
    engine.wait_for("device_set")
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0)
    meta = engine.wait_for("shm_ready", timeout=60)
    engine.wait_for("image_ready", timeout=60)

    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, ref.h, ref.w)
        assert np.abs(base - ref.rgb.astype(np.int16)).max() == 0, "起点就不是原图"
        for kw in ({"eps": 0.0}, {"radius": 0}, {"eps": 0.0, "radius": 0}):
            engine.send(cmd="set_strength", value=0.5, **kw)
            _expect_error(engine, "超出范围")
            engine.send(cmd="set_strength", value=0.0)
            ev = engine.wait_for("params_set", timeout=30)
            got = _read_frame(engine, peer, ref.h, ref.w)
            d = int(np.abs(got - ref.rgb.astype(np.int16)).max())
            assert d == 0, f"{kw} 被拒绝之后，strength=0 的帧仍与原图差 {d} LSB——非法值已写进缓存"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_rejected_set_strength_leaves_no_half_applied_state(engine):
    """被拒绝的那条命令一个字段都不能留下。

    坑的形状：cmd_set_strength 原来先提交 strength/channel，再校验磨皮参数；参数越界时
    直接 emit error 返回，但 self._strength 已经改成这条"没执行"的命令里的值。下一条
    不带 value 的 set_strength 会拿这个泄漏值出帧——用户看到的是"我拒绝了，画面却变了"。
    上一轮那条越界用例每条都显式带了 value，正好把这个洞盖住，所以这里刻意**不带** value。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")

    _load(engine, max_px=207360, strength=0.4)
    engine.send(cmd="set_strength", value=0.8, channel="skin")   # 没有掩膜，channel 也要被拒
    _expect_error(engine, "没有掩膜通道")
    engine.send(cmd="set_strength", value=0.9, radius=100000)    # 参数越界
    _expect_error(engine, "超出范围")
    # 现在发一条"什么都不改"的命令：回显必须还是导入时的 0.4 与全图，而不是 0.8/0.9/skin
    engine.send(cmd="set_strength")
    ev = engine.wait_for("params_set", timeout=30)
    assert ev["strength"] == 0.4, f"被拒绝的 value 泄漏进了会话：回显 {ev['strength']}，应为导入时的 0.4"
    assert ev["channel"] is None, f"被拒绝的 channel 泄漏进了会话：{ev['channel']}"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_cached_field_discriminates_recompute_from_reuse(engine):
    """`cached` 必须能区分"这一帧重算了没"，不能是个恒真的说法。

    原来是 `"cached": retouched is not None`：只要 render 成功它就必然 True，
    于是"缓存被无声绕过"这种最坏情况仍会报出一句"已缓存"。所以这里要求它在
    改参那一帧为 False、在纯拖强度那一帧为 True——两个值都出现过，字段才算被执行路径钉住。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")

    _load(engine, max_px=207360, strength=0.5)
    engine.send(cmd="set_strength", value=0.5, radius=18)
    ev1 = engine.wait_for("params_set", timeout=30)
    assert ev1["filter_ms"] > 0.0 and ev1["cached"] is False, f"重算帧却报 cached=True：{ev1}"
    engine.send(cmd="set_strength", value=0.7)
    ev2 = engine.wait_for("params_set", timeout=30)
    assert ev2["filter_ms"] == 0.0 and ev2["cached"] is True, f"复用帧却报 cached=False：{ev2}"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_set_device_is_refused_while_bench_running(engine):
    """跑靶进行中不许换设备：会话留在旧设备上，但 self._cuda 会翻，分段计时随之失真。

    `_sync()` 按 `self._cuda` 决定是否 synchronize。cuda→cpu 翻转后跑靶线程的 kernel 段
    只剩"入队时间"，滤波/混合看起来突然变快；而 device_set 已经宣告切换成功，只有
    bench_done.pipe_device 才看得出真相。与 load_image/precompute/set_strength 同一条规矩：
    整条拒绝，所以既不能有 error 之外的任何 device_set，跑靶也不能因此失败。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻管线要 torch")
    import torch
    if not torch.cuda.is_available():
        pytest.skip("无 GPU：迁移路径与 pipe_device 都无从谈起")

    # 注意：_load 之后再 set_device 只做"会话迁移"，不会重发 shm_ready——同尺寸的
    # _ensure_shm 命中已有缓冲时压根不创建新块。这里复用 _load 拿到的 w/h，别等第二个 shm_ready。
    meta = _load(engine, max_px=207360, strength=0.5)
    engine.send(cmd="set_device", device="cuda")
    engine.wait_for("device_set", timeout=30)
    engine.send(cmd="bench_start", mode="image_stream", frames=40, interval_ms=100,
                w=meta["w"], h=meta["h"])
    engine.wait_for("bench_started", timeout=30)

    engine.send(cmd="set_device", device="cpu")
    seen = []
    err = None
    while err is None and len(seen) < 60:
        ev = engine.next_event(timeout=20)
        if ev.get("event") == "error":
            err = ev
        else:
            seen.append(ev.get("event"))
            assert ev.get("event") != "device_set", \
                f"拒绝不彻底：跑靶进行中的 set_device 仍发出了 device_set（{ev}）"
    assert "跑靶进行中" in (err or {}).get("error", ""), f"没等到预期的拒绝：{err}，期间收到 {seen}"

    engine.send(cmd="bench_stop")
    done = engine.wait_for("bench_done", timeout=60)
    assert not done.get("failed"), f"跑靶被这次拒绝弄挂了：{done}"
    assert str(done.get("pipe_device")).startswith("cuda"), \
        f"会话被换走了：pipe_device={done.get('pipe_device')}，应当仍是 cuda"


# ================================================================ 消除笔（M1-4）
def _needs_torch():
    if importlib.util.find_spec("torch") is None:
        pytest.skip("常驻修补图层要 torch")


def _brush_rle(h, w, cy, cx, r, value=255):
    """圆形画笔 → 行程编码（与 UI 侧的采集方式同构：逐行一段）。"""
    rle = []
    for y in range(max(0, cy - r), min(h, cy + r + 1)):
        dy = y - cy
        dx = int((r * r - dy * dy) ** 0.5)
        x0, x1 = max(0, cx - dx), min(w, cx + dx + 1)
        if x1 > x0:
            rle.append([y, x0, x1 - x0, value])
    assert rle, "画笔跑到图外了，这条用例就没有意义"
    return rle


def _brush_mask(h, w, rle):
    from lumaretouch_engine.ops.inpaint import feather_np, mask_from_rle

    return feather_np(mask_from_rle(rle, h, w), 2)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_inpaint_changes_only_the_pixels_under_the_brush(engine):
    """端到端的第一条主张：消除笔只改画笔覆盖到的地方，没盖到的逐字节不动。

    拿上屏字节比而不是引擎内部张量：shm 里那一帧才是用户看到的东西，
    clamp/量化/pack 这一路上的任何一步把“只改笔内”弄漏了，这里会红。

    “笔内”按**羽化后的支撑**（覆盖度 > 0）算而不是按硬圆算：羽化的本意就是
    在边界环上小幅度改，拿 0.5 等值线当“笔外”会把一个正确行为测成缺陷（实测差 2 LSB）。
    所以这里同时卡两头：支撑外逐字节不动，支撑内的改动幅度随覆盖度递降。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        before = _read_frame(engine, peer, h, w)
        rle = _brush_rle(h, w, h // 2, w // 2, 7)
        engine.send(cmd="inpaint", action="add", rle=rle, feather=2)
        done = engine.wait_for("inpaint_done", timeout=60)
        assert done["action"] == "add" and done["ops"] == 1 and done["applied"] == 1, done
        assert done["repair_ms"] > 0.0, f"加了一笔却没算修补：{done}"
        assert str(done["device"]).startswith(("cuda", "cpu")), done["device"]
        after = _read_frame(engine, peer, h, w)
        cover = _brush_mask(h, w, rle)
        assert float((cover > 0).sum()) > float((cover > 0.5).sum()), "羽化环是空的，这条就没在验羽化"
        untouched = cover == 0
        d_out = np.abs(after[untouched] - before[untouched])
        assert int(d_out.max()) == 0, f"笔外像素被改了 {int(d_out.max())} LSB——写回越界了"
        delta = np.abs(after - before).max(axis=2)
        core = cover > 0.5
        ring = (cover > 0) & (cover <= 0.5)
        assert float(delta[core].mean()) > 0.5, "笔心一点没改，消除笔空转"
        assert float(delta[ring].max()) <= float(delta[core].max()), \
            f"羽化环比笔心改得还多（{delta[ring].max()} vs {delta[core].max()}）：覆盖度没起作用"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_drag_stream_after_inpaint_still_refilters_nothing(engine):
    """修补不能把 M1-3c 的零推理弄掉：事件算一次，之后拖滑块仍是 0 次重算。

    这里是两条主张的交点：滤波缓存的键必须包底图版本（不然拖滑块会拿旧底图的
    滤波结果磨新底图），而重建只在事件里发生（不然拖拽热路径又付一次 4 ms）。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.5)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="inpaint", action="add", rle=_brush_rle(h, w, 30, 30, 5), feather=2)
    done = engine.wait_for("inpaint_done", timeout=60)
    assert done["filter_ms"] > 0.0, "底图变了但滤波没重算：下一帧会拿旧图的结果磨新图"
    assert done["cached"] is False, done
    # 多笔叠上去才是产品用法：零重算不能只在“只有一笔”下成立。逐笔重放各自四周的裁块，
    # 图层数与落图数必须一个个对得上，否则报表上看不出漏了哪笔。
    for i, (cy, cx, r) in enumerate(((h // 2, w // 2, 6), (h - 40, 30, 4)), start=2):
        engine.send(cmd="inpaint", action="add", rle=_brush_rle(h, w, cy, cx, r), feather=2)
        more = engine.wait_for("inpaint_done", timeout=60)
        assert more["ops"] == i and more["applied"] == i, f"第 {i} 笔没逐笔落图：{more}"
        assert more["repair_ms"] > 0.0, f"第 {i} 笔报称重算了图层却没花任何时间：{more}"
    engine.send(cmd="bench_start", mode="image_stream", frames=6, interval_ms=20,
                w=w, h=h)
    engine.wait_for("bench_started", timeout=30)
    b = engine.wait_for("bench_done", timeout=90)
    assert not b.get("failed"), f"跑靶失败：{b}"
    assert b["refilter_frames"] == 0, \
        f"拖拽流里重算了 {b['refilter_frames']} 次滤波：修补把零推理弄丢了"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_inpaint_undo_restores_exact_previous_frame_bytes(engine):
    """撤销不是“重新算一遍相近的结果”，而是逐字节回到上一帧。

    只存画笔不存结果因此必须能做到：重放是确定性的。哪天引入“结果缓存”
    并把旧缓存回挂了，这条会红。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        rle = _brush_rle(h, w, h // 3, w // 3, 6)
        engine.send(cmd="inpaint", action="add", rle=rle, feather=2)
        engine.wait_for("inpaint_done", timeout=60)
        repaired = _read_frame(engine, peer, h, w)
        assert np.abs(repaired - base).max() > 0
        engine.send(cmd="inpaint", action="undo")
        done = engine.wait_for("inpaint_done", timeout=60)
        assert done["ops"] == 0 and done["redo_pending"] == 1, done
        back = _read_frame(engine, peer, h, w)
        assert np.array_equal(back, base), f"撤销后差了 {int(np.abs(back - base).max())} LSB"
        engine.send(cmd="inpaint", action="redo")
        done = engine.wait_for("inpaint_done", timeout=60)
        assert done["ops"] == 1, done
        again = _read_frame(engine, peer, h, w)
        assert np.array_equal(again, repaired), "重做没逐字节复现那一笔"
        engine.send(cmd="inpaint", action="undo")
        engine.wait_for("inpaint_done", timeout=60)
        engine.send(cmd="inpaint", action="undo")
        _expect_error(engine, "没有可撤销")
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_bad_inpaint_commands_leave_no_trace(engine):
    """被拒绝的一笔必须整条不留痕：图层没加、强度没改、下一帧还是原样。

    与 cmd_set_strength 同一条铁律。上一轮就是“报错了但全局量已被改走”，
    下一条正常命令会拿那个泄漏值出帧：用户看到的是“我拒绝了，画面却变了”。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.4)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        before = _read_frame(engine, peer, h, w)
        good = _brush_rle(h, w, 20, 20, 4)
        bad_rle = [list(r) for r in good]
        bad_rle[0][2] = w + 99                        # 行内越界
        engine.send(cmd="inpaint", action="add", rle=bad_rle, feather=2)
        _expect_error(engine, "rle 非法")
        engine.send(cmd="inpaint", action="add", rle=good, feather=99)
        _expect_error(engine, "feather")
        engine.send(cmd="inpaint", action="add", rle=good, refine_iters=999)
        _expect_error(engine, "refine_iters")
        engine.send(cmd="inpaint", action="add", rle=[], feather=2)
        _expect_error(engine, "rle 为空")
        engine.send(cmd="inpaint", action="nope")
        _expect_error(engine, "未知 inpaint action")
        # 拒绝之后：撤销应当说“没有可撤销”，而不是默默撤掉一条不存在的图层
        engine.send(cmd="inpaint", action="undo")
        _expect_error(engine, "没有可撤销")
        # 强度也不能被“没执行”的命令改走
        engine.send(cmd="set_strength")
        ps = engine.wait_for("params_set", timeout=30)
        assert ps["strength"] == 0.4, f"失败的 inpaint 把 strength 改走了：{ps['strength']}"
        after = _read_frame(engine, peer, h, w)
        assert np.array_equal(after, before), "被拒绝的命令仍然改动了画面"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_inpaint_lama_backend_is_refused_loudly(engine):
    """没权重时请求生成式后端必须报错说清缺什么，而不是“退成内置然后报成功”。

    静默降级是本仓反复出现的那一类错：两条证据强度完全不同的路径在报表上会长成一个数。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="inpaint", action="add", rle=_brush_rle(meta["h"], meta["w"], 20, 20, 4),
                backend="lama")
    e = _expect_error(engine, "不可用")
    assert "权重" in e["error"] and "builtin" in e["error"], e["error"]
    engine.send(cmd="inpaint", action="undo")
    _expect_error(engine, "没有可撤销")


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_inpaint_is_refused_while_bench_running(engine):
    """跑靶进行中不许改图层：两条路径写同一块 frame_gpu（与 set_strength 同一条守卫）。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.5)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="bench_start", mode="image_stream", frames=40, interval_ms=100, w=w, h=h)
    engine.wait_for("bench_started", timeout=30)
    engine.send(cmd="inpaint", action="add", rle=_brush_rle(h, w, 20, 20, 4))
    _expect_error(engine, "跑靶进行中")
    engine.send(cmd="bench_stop")
    done = engine.wait_for("bench_done", timeout=60)
    assert not done.get("failed"), f"这次拒绝把跑靶弄挂了：{done}"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_new_image_drops_previous_brush_strokes(engine):
    """换图必须丢画笔：旧坐标对新图没有任何意义（与旧掩膜同一条规矩）。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="inpaint", action="add", rle=_brush_rle(h, w, h // 2, w // 2, 6), feather=2)
    engine.wait_for("inpaint_done", timeout=60)
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0, max_px=207360)
    # 第二张与第一张同尺寸 → _ensure_shm 不重建也不重发 shm_ready（已知行为，
    # 写在这是为了下次不要再当 bug 查）：这里只等真正会重发的那两个事件
    engine.wait_for("vram_ready", timeout=60)
    ready2 = engine.wait_for("image_ready", timeout=60)
    assert ready2["strength"] == 0.0
    engine.send(cmd="inpaint", action="undo")
    _expect_error(engine, "没有可撤销")


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_gpu_warm_up_takes_the_cold_cost_off_the_first_import(engine):
    """预热必须真的把首图的冷价挪走，而不是只在日志里说一句"预热了"。

    F 轮实测：冷进程首图 ~299 ms、稳态 ~35 ms，那 265 ms 与图尺寸无关（上下文建立 +
    内核模块首次加载）。它挂在用户第一次点"导入"上，所以引擎起进程时就该付掉。
    判据取 `max(150 ms, 第二张 × 3)`：没预热时是 8.5 倍、299 ms，两条都会撞线。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("GPU 预热只在有 torch 的会话里有意义")
    import torch

    if not torch.cuda.is_available():
        pytest.skip("本机没有可用的 cuda 设备")
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cuda")
    d = engine.wait_for("device_set")
    assert d["cuda"] is True, d
    warm = engine.next_event(timeout=120.0)
    assert warm.get("event") == "engine_warm", f"device_set 之后没等到预热回报，拿到的是：{warm}"
    assert warm["warm_ms"] > 0.0 and warm["device"] == "cuda", warm
    for _ in range(2):
        engine.send(cmd="load_image", path=FIXTURE, max_px=576000, strength=0.0)
    first = engine.wait_for("image_ready", timeout=120)
    second = engine.wait_for("image_ready", timeout=120)
    line = max(150.0, second["import_ms"] * 3.0)
    assert first["import_ms"] <= line, (
        f"预热后首图仍要 {first['import_ms']} ms（第二张 {second['import_ms']} ms，判据 {line:.1f}）："
        "预热没盖住真实内核，或者冷价根本挪不走")


# ================================================== 修容笔（M2-a2）走完整 IPC
def _dilate(mask: np.ndarray, k: int) -> np.ndarray:
    """切比雪夫（L∞）膨胀 k 次：给出“离覆盖区不超过 k 像素”的那一圈。

    必须是 8 邻域。上一版只并了上下左右四个移位，得到的是 L1 菱形：对角方向上
    L∞=8 的点需要 16 步才能膨胀到，于是“笔触外”在对角上侵进了真实影响区，
    把一帧正确的修容测成“越界 2 LSB”。盒式滤波的支撑是方形窗口，就得用方形膨胀去套。
    """
    m = mask.copy()
    for _ in range(k):
        p = np.pad(m, 1)
        m = (m | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
             | p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:])
    return m


def _lin_light(a: np.ndarray) -> np.ndarray:
    """int16 的 [0,255] 帧 → 线性光。判"往哪个方向动了多少档"要用它，不能用编码值。"""
    x = np.clip(a.astype(np.float64) / 255.0, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_light_moves_exposure_in_the_direction_the_sign_says(engine):
    """协议层的 sign 直通：减淡必须提亮、加深必须压暗，而且是在**线性光**下按档数。

    方向接反是最典型的接线错误，而字节比对完全看不出来（两边都"改了"）。
    所以这里不看字节，看线性光均值的移动方向与档数。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    rle = _brush_rle(h, w, h // 2, w // 2, 10)
    cover = _brush_mask(h, w, rle) > 0
    base_lin = None
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        base_lin = _lin_light(base)
        for sign, want_up in ((1, True), (-1, False)):
            engine.send(cmd="light", action="clear")
            engine.wait_for("light_done", timeout=60)
            engine.send(cmd="light", action="add", rle=rle, feather=2, sign=sign,
                        exposure=0.6, radius=6)
            done = engine.wait_for("light_done", timeout=60)
            assert done["ops"] == 1 and done["lit"] is True, done
            assert done["sign"] == sign, f"sign 没过 Rust/协议：{done}"
            # 参数也得真的落进去：上一版 add 带了 radius=6 而被静默忽略（上报仍是 24），
            # 整个事件看上去完全正常——静默吞参数比拒命令难查得多，所以这里直接卡上报值
            assert done["radius"] == 6 and done["exposure"] == 0.6, f"add 带的参数没生效：{done}"
            shot = _read_frame(engine, peer, h, w)
            got = _lin_light(shot)[cover].mean() / base_lin[cover].mean()
            stops = float(np.log2(got))
            if want_up:
                assert stops > 0.25, f"减淡笔只动了 {stops:+.3f} 档：方向接反或强度丢了"
            else:
                assert stops < -0.25, f"加深笔只动了 {stops:+.3f} 档：方向接反或强度丢了"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_light_leaves_pixels_beyond_the_band_limit_untouched(engine):
    """带限半径 r 就是影响半径：r 之外必须逐字节不动。

    这条同时在产品通路上验了 gamma 往返恒等——笔外那些像素走的是
    `srgb(linear(img))`，量化只要偏用截断就会整片掉 1 级（M2-a2 就是这么把
    产品级量化缺陷顶出来的）。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    rle = _brush_rle(h, w, h // 2, w // 2, 9)
    cover = _brush_mask(h, w, rle) > 0
    radius = 6
    peer = FrameShm(meta["name"])
    try:
        before = _read_frame(engine, peer, h, w)
        engine.send(cmd="light", action="add", rle=rle, feather=2, sign=1,
                    exposure=0.6, radius=radius)
        engine.wait_for("light_done", timeout=60)
        after = _read_frame(engine, peer, h, w)
        # 图边缘留一圈：reflect pad 会把边界值镜像进来，那不是越界（留够 r+4）
        far = ~_dilate(cover, radius + 3)
        edge = radius + 4
        far[:edge] = far[-edge:] = far[:, :edge] = far[:, -edge:] = False
        assert float(far.mean()) > 0.5, "远离笔触的区域太小，这条判据是空的"
        d = int(np.abs(after - before)[far].max())
        assert d == 0, f"笔触外 {d} LSB——修容的影响半径超出了带限半径"
        assert int(np.abs(after - before)[cover].max()) > 0, "笔心里一点没改，修容空转"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_drag_stream_after_light_relights_and_refilters_nothing(engine):
    """M2-a2 的核心产品判据：画完修容再拖滑块，db 与滤波都必须一次都不重算。

    修容层设计成"对两个混合操作数各存一份结果"就是为了这条。relight_frames
    不为 0 就说明 db 缓存键算错了，热路径被拖回每帧 4 ms。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.5)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="light", action="add", rle=_brush_rle(h, w, 30, 30, 5),
                feather=2, sign=1, radius=6)
    done = engine.wait_for("light_done", timeout=60)
    assert done["lit"] is True and done["light_ms"] >= 0.0, done
    for i, (cy, cx, s) in enumerate(((h // 2, w // 2, 1), (h - 40, 40, -1)), start=2):
        engine.send(cmd="light", action="add", rle=_brush_rle(h, w, cy, cx, 6),
                    feather=2, sign=s, radius=6)
        more = engine.wait_for("light_done", timeout=60)
        assert more["ops"] == i, f"第 {i} 笔没进图层：{more}"
        assert more["bands_ms"] == 0.0, f"只画修容却重跑了分带：{more}"
    engine.send(cmd="bench_start", mode="image_stream", frames=6, interval_ms=20,
                w=w, h=h)
    engine.wait_for("bench_started", timeout=30)
    b = engine.wait_for("bench_done", timeout=90)
    assert not b.get("failed"), f"跑靶失败：{b}"
    assert b["refilter_frames"] == 0, f"拖拽流里重算了 {b['refilter_frames']} 次滤波"
    assert b["relight_frames"] == 0, \
        f"拖拽流里重算了 {b['relight_frames']} 次修容：db 常驻没生效，热路径被拖回重算"
    assert b["light"] == 0.0, f"每帧修容均值 {b['light']} ms 不为 0"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_light_undo_restores_exact_previous_frame_bytes(engine):
    """修容也是"只存输入"：撤销/重做必须逐字节复现，与消除笔同一条非破坏原则。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="light", action="add", rle=_brush_rle(h, w, h // 3, w // 3, 8),
                    feather=2, sign=1, radius=6)
        engine.wait_for("light_done", timeout=60)
        lit = _read_frame(engine, peer, h, w)
        assert np.abs(lit - base).max() > 0
        engine.send(cmd="light", action="undo")
        done = engine.wait_for("light_done", timeout=60)
        assert done["ops"] == 0 and done["redo_pending"] == 1 and done["lit"] is False, done
        back = _read_frame(engine, peer, h, w)
        assert np.array_equal(back, base), f"撤销后差了 {int(np.abs(back - base).max())} LSB"
        engine.send(cmd="light", action="redo")
        done = engine.wait_for("light_done", timeout=60)
        assert done["ops"] == 1 and done["lit"] is True, done
        again = _read_frame(engine, peer, h, w)
        assert np.array_equal(again, lit), "重做没逐字节复现那一笔"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_bad_light_commands_leave_no_trace(engine):
    """被拒绝的修容命令整条不留痕：图层没加、层参数没改、帧还是原样。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.4)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        before = _read_frame(engine, peer, h, w)
        good = _brush_rle(h, w, 20, 20, 4)
        engine.send(cmd="light", action="nope")
        _expect_error(engine, "未知 light action")
        engine.send(cmd="light", action="add", rle=[], sign=1)
        _expect_error(engine, "缺 rle")
        bad_rle = [list(r) for r in good]
        bad_rle[0][2] = w + 99
        engine.send(cmd="light", action="add", rle=bad_rle, sign=1)
        _expect_error(engine, "rle 非法")
        engine.send(cmd="light", action="add", rle=good, sign=0)
        _expect_error(engine, "sign=0")
        engine.send(cmd="light", action="add", rle=good, sign=7)
        _expect_error(engine, "sign=7")
        engine.send(cmd="light", action="add", rle=good, sign=1, feather=99)
        _expect_error(engine, "feather")
        engine.send(cmd="light", action="params", exposure=9.0)
        _expect_error(engine, "exposure")
        engine.send(cmd="light", action="params", radius=-3)
        _expect_error(engine, "radius")
        engine.send(cmd="light", action="params")
        _expect_error(engine, "什么也没给")
        # 拒绝之后图层与参数都应当是干净的
        engine.send(cmd="light", action="undo")
        _expect_error(engine, "没有可撤销的修容笔")
        # 被拒的命令不发帧，所以拿一条正常 params 把帧取回来比对：无修容层时
        # exposure 不影响画面，这一帧必须与导入时逐字节相同
        engine.send(cmd="light", action="params", exposure=0.6)
        done = engine.wait_for("light_done", timeout=60)
        assert done["exposure"] == 0.6, done
        assert done["radius"] == 24, f"被拒的 radius 泄漏进了层参数：{done}"
        assert done["lit"] is False, f"一笔也没画但上报说层生效了：{done}"
        after = _read_frame(engine, peer, h, w)
        assert np.array_equal(after, before), \
            f"被拒绝的命令改了画面（最大 {int(np.abs(after - before).max())} LSB）"
        # add 也能带参数，而且越界一样得整条拒绝
        engine.send(cmd="light", action="add", rle=good, sign=1, radius=9999)
        _expect_error(engine, "radius")
        engine.send(cmd="light", action="undo")
        _expect_error(engine, "没有可撤销的修容笔")
    finally:
        peer.close()


# ============================================================ M2-b 五官微调
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_deform_requires_precompute_first(engine):
    """没有 478 点关键点就不许形变：它不是“没得形变”而是“不知道把哪里搬到哪里”。"""
    _needs_torch()
    _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.5})
    _expect_error(engine, "需要先 precompute")


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_deform_refuses_synthetic_placeholder_landmarks(engine):
    """synthetic 后端给的是网格占位几何，形变必须整条拒。

    不拒的话它会“成功”：点号 234 在点阵里落在某个格子中心，拿它当“左脸轮廓”
    会推到完全不相关的像素上，而画面真的在动、事件真的成功——看不出错。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="precompute", backend="synthetic")
    pc = engine.wait_for("precompute_ready", timeout=60)
    assert pc["backend"] == "synthetic", pc
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.5})
    _expect_error(engine, "synthetic")


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_deform_on_template_backend_moves_the_frame_and_clear_restores_it(engine):
    """端到端：模板后端 → 建层 → 拖滑块改画面 → clear 逐字节回原。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="precompute", backend="template")
    pc = engine.wait_for("precompute_ready", timeout=60)
    assert pc["backend"] == "template" and pc["num_landmarks"] == 478, pc
    peer = FrameShm(meta["name"])
    try:
        _nudge_frame(engine, 0.0)
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="deform", action="set", amounts={"slim_face": 0.9})
        done = engine.wait_for("deform_done", timeout=60)
        assert done["built"] is True and done["lit"] is True, done
        assert done["landmark_backend"] == "template", done
        assert done["build"]["deform_builds"] == 1, done
        assert done["bytes_deform"] > 0, "建了单却没上报常驻字节"
        lit = _read_frame(engine, peer, h, w)
        assert np.abs(lit - base).max() > 0, "瘦脸 0.9 没改到画面"
        # 只改一个滑块，另两个必须停在 0（先校验后提交不得“顺手清零”）
        assert done["amounts"] == {"slim_face": 0.9, "big_eye": 0.0, "small_chin": 0.0}, done
        engine.send(cmd="deform", action="set", amounts={"slim_face": 0.45})
        half = engine.wait_for("deform_done", timeout=60)
        assert "build" not in half, "第二次 set 不应当重建"
        engine.send(cmd="deform", action="clear")
        back = engine.wait_for("deform_done", timeout=60)
        assert back["lit"] is False and back["bytes_deform"] == 0, back
        again = _read_frame(engine, peer, h, w)
        assert np.array_equal(again, base), f"clear 后差了 {int(np.abs(again - base).max())} LSB"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_bad_deform_commands_leave_no_trace(engine):
    """被拒的形变命令整条不留痕：不建层、不改滑块、不改画面。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.3)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="precompute", backend="template")
    engine.wait_for("precompute_ready", timeout=60)
    peer = FrameShm(meta["name"])
    try:
        _nudge_frame(engine, 0.3)
        before = _read_frame(engine, peer, h, w)
        engine.send(cmd="deform", action="nope", amounts={"slim_face": 0.5})
        _expect_error(engine, "未知 deform action")
        engine.send(cmd="deform", action="set", amounts={"nose": 0.5})
        _expect_error(engine, "未知形变类型")
        engine.send(cmd="deform", action="set", amounts={"slim_face": 3.0})
        _expect_error(engine, "形变量非法")
        engine.send(cmd="deform", action="set", amounts={})
        _expect_error(engine, "至少要给一个")
        engine.send(cmd="deform", action="set")
        _expect_error(engine, "至少要给一个")
        # 越界值不得先触发建层：报错之后图层应当还是空的
        engine.send(cmd="deform", action="set", amounts={"big_eye": 0.8})
        done = engine.wait_for("deform_done", timeout=60)
        assert done["build"]["deform_builds"] == 1, "拒绝的命令把建层也做了"
        after = _read_frame(engine, peer, h, w)
        assert np.abs(after - before).max() > 0, "最后一条合法命令应当生效"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_drag_stream_with_deform_lit_builds_nothing(engine):
    """M2-b 的核心产品判据：开着形变拖 600 帧滑块，一次 TPS 也不许解。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.5)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="precompute", backend="template")
    engine.wait_for("precompute_ready", timeout=60)
    engine.send(cmd="deform", action="set",
                amounts={"slim_face": 0.6, "big_eye": 0.3, "small_chin": 0.4})
    done = engine.wait_for("deform_done", timeout=60)
    assert done["lit"] is True, done
    engine.send(cmd="bench_start", mode="image_stream", frames=6, interval_ms=20,
                w=w, h=h)
    engine.wait_for("bench_started", timeout=30)
    b = engine.wait_for("bench_done", timeout=90)
    assert not b.get("failed"), f"跑靶失败：{b}"
    assert b["refilter_frames"] == 0, f"拖拽流里重算了滤波：{b['refilter_frames']}"
    assert b["relight_frames"] == 0, f"拖拽流里重算了修容：{b['relight_frames']}"
    assert b["deform_builds"] == 0, \
        f"拖拽流里重解了 {b['deform_builds']} 次 TPS，零推理失效"
    assert b["deform"] > 0, "开着形变却一帧都没跑 grid_sample，这条判据退化了"
    # 本用例跑在 CPU 会话上（_load 固定 set_device cpu），4 ms 是 CPU 上 grid_sample +
    # 零位移保留那两步的量。GPU 产品档的每帧预算由 packaging/m2-face-bench.py 钉（~1 ms），
    # 不在这里拿 CPU 数字冒充 GPU 结论。
    assert b["deform"] < 8.0, f"每帧形变均值 {b['deform']} ms 超预算"
    assert b["deform_state"]["amounts"]["slim_face"] == 0.6, \
        f"bench_done 里的形变状态与实际跑的不一个数：{b['deform_state']}"
    # 上报里“每帧分段”与“图层状态”不能共用一个名字：字典字面量后写的会静默覆盖先写的，
    # 于是其中一个永远送不出来而报表看着仍自洽。这两条就是在钉它俩确实是两个字段。
    assert isinstance(b["deform"], float) and isinstance(b["deform_state"], dict), \
        "deform 每帧 ms 与 deform_state 图层状态必须分得开"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_deform_is_refused_while_bench_running(engine):
    """跑靶进行中不许改图层：与 light/inpaint 同一条互斥，不然 600 帧混进一次解算。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.5)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="precompute", backend="template")
    engine.wait_for("precompute_ready", timeout=60)
    engine.send(cmd="bench_start", mode="image_stream", frames=40, interval_ms=25,
                w=w, h=h)
    engine.wait_for("bench_started", timeout=30)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.5})
    _expect_error(engine, "跑靶进行中")
    engine.send(cmd="bench_stop")
    engine.wait_for("bench_done", timeout=90)
