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
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0, **kw)
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
