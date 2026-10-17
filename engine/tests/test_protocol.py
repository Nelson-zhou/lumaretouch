"""引擎 JSON-lines 协议 + shm 通路的端到端测试（起真子进程，不 mock）。

注意脚手架自身的坑：阻塞 readline 会让"等一个不会来的事件"直接挂死，
stderr 管道不排空会死锁。所以这里用后台读线程 + 带超时的队列。
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import base64
import importlib.util

import numpy as np
import pytest

from lumaretouch_engine import session as S
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
        # 最近一条被 wait_for 顺手丢掉的 frame 事件。M5-b 的 undo 链上 history_state
        # 就发在帧前面，等状态的那个 wait_for 会把画面证据吃掉；像素判据要从这里捡回来。
        self.last_frame: dict | None = None
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
            if e.get("event") == "frame":
                self.last_frame = e
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


def test_ready_reports_the_version_and_runtime_bills(engine):
    """发布自证（M5-c）：ready 必须报版本与这一份运行时包账单。

    这里只证**内部一致性**：引擎报的版本就是它自己代码里那一份 `__version__`。
    “六处版本号写不写在一起”属发布门禁（packaging/release-version.py check），
    不在单测里重做一份：单测拿不到打包配置，写进来只能靠反推路径，那又是一处双出处。
    """
    from lumaretouch_engine import __version__
    from lumaretouch_engine.server import runtime_report

    engine.send(cmd="hello")
    ready = engine.wait_for("ready")
    assert ready["version"] == __version__, "引擎报的版本不是自己代码里那一份"

    rt = ready["runtime"]
    # 键集必须相等：没装的包写 None，不许静默少键——发布校验拿 None 判“运行时不完整”，
    # “这个包没装”与“这一版引擎不报这个键”是两件事，混起来就会把缺依赖的运行时判成健康。
    assert set(rt) == set(runtime_report()), f"ready 的 runtime 键集漂了：{sorted(rt)}"
    assert rt["python"] == ".".join(map(str, sys.version_info[:3]))
    for pkg in ("numpy", "pillow", "torch", "torchvision"):
        assert pkg in rt
        assert rt[pkg] is None or isinstance(rt[pkg], str), f"{pkg} 的版本得是字符串或 None"
    # numpy 是引擎的硬依赖：跑到了这一步还不报版本，说明 ready 里的账单不是现读的
    assert rt["numpy"], "numpy 都没装的话，这份账单不可信"


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


def _load_mtd():
    """把写侧夹具当被测依赖之外的一份工具载进来（不 import 引擎常量）。"""
    path = os.path.join(HERE, "..", "packaging", "make-test-dng.py")
    spec = importlib.util.spec_from_file_location("make_test_dng", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hello_reports_raw_backends(engine):
    """能力清单由引擎自报，前端不刻一份：能读什么、读不了什么、出路在哪。"""
    engine.send(cmd="hello")
    ready = engine.wait_for("ready")
    rb = ready["raw_backends"]
    assert rb["baseline"] and ".dng" in rb["suffixes"]
    assert isinstance(rb["plugin_installed"], bool)
    # needs_plugin 必须非空且不谎称已装——把「解不开 CR2」这件事如实写出来
    assert rb["needs_plugin"] and rb["plugin"]


@pytest.mark.skipif(not os.path.isfile(FIXTURE),
                    reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_load_dng_strength_zero_and_raw_fields(engine, tmp_path):
    """端到端：.dng 导入 → 代理档 → 常驻 → shm 帧能被独立读出；raw 字段随 ready 上报。

    这一张从整幅 fixture 生成（1024×1280 超过代理预算），所以它同时把「块内每色
    均值降采样 + LANCZOS」那条代理支路端到端跑了一遍。strength=0 的逐字节一致是
    两边都走同一份 torch-cpu 渲染，与 GPU↔CPU 的 ≤1 LSB 是两个独立口径。
    """
    if importlib.util.find_spec("torch") is None:
        pytest.skip("DNG 生产路走 torch")
    from PIL import Image
    from lumaretouch_engine.decode import load_rgb

    mt = _load_mtd()
    src = np.asarray(Image.open(FIXTURE).convert("RGB"))
    dng = os.path.join(str(tmp_path), "full.dng")
    mt.build(dng, src, black=256.0, white=16383.0)
    ref = load_rgb(dng, device="cpu")

    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    engine.send(cmd="load_image", path=dng, strength=0.0)
    shm_meta = engine.wait_for("shm_ready", timeout=120)
    assert (shm_meta["w"], shm_meta["h"]) == (ref.w, ref.h)
    engine.wait_for("vram_ready", timeout=120)
    ready = engine.wait_for("image_ready", timeout=120)
    assert ready["format"] == "DNG"
    raw = ready["raw"]
    assert raw["bits"] == 16 and raw["color_planes"] == 3
    assert raw["pattern"] == [0, 1, 1, 2]
    assert raw["white"] == 16383.0
    # 代理帧比源图小：证明真降了档，不是把整幅塞回来（默认代理预算≈ 960×600 个像素）
    assert ref.w * ref.h <= 960 * 600 and (ref.w, ref.h) != (1024, 1280)

    peer = FrameShm(shm_meta["name"])
    try:
        ev = engine.wait_for("frame", timeout=60)
        got = np.frombuffer(peer.read_pixels(ev["slot"]), np.uint8).reshape(ref.h, ref.w, 4)
        d = np.abs(got[:, :, :3].astype(np.int16) - ref.rgb.astype(np.int16))
        assert d.max() <= 1, f"strength=0 上屏帧与独立解码差 {int(d.max())} LSB"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE),
                    reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_unsupported_raw_is_refused_honestly(engine, tmp_path):
    """一张格式良好但基线不认的 DNG（CFALayout≠1）必须报 error 且引擎不死。

    反向门禁：如果哪天把 UnsupportedRaw 吞了、或静默换成 Pillow/预览渲染，这条会红——
    那正是「把没解开的相机 RAW 写成已支持」的假证据来源。
    """
    from PIL import Image
    mt = _load_mtd()
    src = np.asarray(Image.open(FIXTURE).convert("RGB"))[:128, :128]
    dng = os.path.join(str(tmp_path), "交错.dng")
    mt.build(dng, src, cfa_layout=2, black=256.0, white=16383.0)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    engine.send(cmd="load_image", path=dng, strength=0.0)
    err = engine.wait_for("error", timeout=30)
    assert "导入失败" in err["error"] and "CFALayout" in err["error"], err["error"]
    # 引擎还活着：拒绝一张坏 RAW 不许把服务进程带下去
    engine.send(cmd="hello")
    assert engine.wait_for("ready")["pid"] == engine.proc.pid


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


def _other_image(tmp_path):
    """另一张真图（同尺寸、内容不同）：测「换图」就得用**另一张**，不能拿同一个文件导两遍。

    M5-a 之前「同一个文件导两遍」与「换一张图」在引擎里是同一件事，所以那几个用例都
    图省事复用了 FIXTURE。有了底片条之后两者不再是一件事：重开同一张文档**必须**把这张
    文档自己的层带回来（test_switching_documents_returns_the_exact_same_frame 钉的就是
    这条），换一张文档才必须丢坐标层。这里造的就是「另一张文档」。
    """
    from PIL import Image
    q = tmp_path / "other-1024x1280.jpg"
    src = np.asarray(Image.open(FIXTURE).convert("RGB"), np.int16)
    Image.fromarray(np.clip(src + 24, 0, 255).astype(np.uint8), "RGB").save(q, quality=92)
    return str(q)


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
    assert ev["filter_cached"] is True, f"缓存没建立却说 filter_cached：{ev}"


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
    assert ev1["filter_ms"] > 0.0 and ev1["filter_cached"] is False, \
        f"重算帧却报 filter_cached=True：{ev1}"
    engine.send(cmd="set_strength", value=0.7)
    ev2 = engine.wait_for("params_set", timeout=30)
    assert ev2["filter_ms"] == 0.0 and ev2["filter_cached"] is True, \
        f"复用帧却报 filter_cached=False：{ev2}"


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
    assert done["filter_cached"] is False, done
    # 图层与滤波两条缓存分不开名：字典字面量后写会静默吃掉先写，于是其中一条永远
    # 送不出来而报表看着仍自洽（bench_done 的 light/deform 已经栽过一次）
    assert done["layer_recomputed"] is True, \
        f"消除笔真重算了却报 layer_recomputed=False：{done}"
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
def test_new_image_drops_previous_brush_strokes(engine, tmp_path):
    """换到**另一张图**必须丢画笔：旧坐标对新图没有任何意义（与旧掩膜同一条规矩）。

    重开同一张文档不在这条的射程里——那一族语义是"文档状态跟着文档走"，由 M5-a
    的切文档用例钉住。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="inpaint", action="add", rle=_brush_rle(h, w, h // 2, w // 2, 6), feather=2)
    engine.wait_for("inpaint_done", timeout=60)
    engine.send(cmd="load_image", path=_other_image(tmp_path), strength=0.0, max_px=207360)
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
def test_deform_done_reports_support_and_geometry(engine):
    """事件得能说出“这一层盖了多少画幅”与“这套点像不像一张脸”。

    两条臂（set / clear）必须同形状：UI 把这三个字段当必存读，少一个键就是
    一个 undefined 而编译期抓不到。clear 之后作用面归 0，不是留着上一个读数。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="precompute", backend="template")
    pc = engine.wait_for("precompute_ready", timeout=60)
    assert isinstance(pc["geometry_warning"], bool), pc
    peer = FrameShm(meta["name"])
    try:
        _nudge_frame(engine, 0.0)
        _read_frame(engine, peer, meta["h"], meta["w"])
        engine.send(cmd="deform", action="set", amounts={"slim_face": 0.9})
        done = engine.wait_for("deform_done", timeout=60)
        assert 0.0 < done["support_share"] <= 1.0, done
        assert done["landmark_notes"], "template 后端得在事件里自述它不是精度检测"
        kinds = done["build"]["kinds"]
        assert all("support_px" in v and "support_share" in v for v in kinds.values()), kinds
        engine.send(cmd="deform", action="clear")
        back = engine.wait_for("deform_done", timeout=60)
        assert {"support_share", "geometry_warning", "landmark_notes"} <= set(back), back
        assert back["support_share"] == 0.0, f"层已整条放下，作用面却还报 {back['support_share']}"
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
    # 分段自洽：kernel 是“整段减去 filter/light/deform”并夹到 0，某段被计两次时
    # 它只会显示 0.0 而不是负数——不报个数就永远看不出重复计时
    assert b["seg_over_frames"] == 0, \
        f"{b['seg_over_frames']} 帧的子段之和超过整段：有分段被计了两次"


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


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_light_done_carries_every_field_for_all_five_actions(engine):
    """light_done 的五种 action 必须送同一套字段：UI 按必存字段读，缺一个就是渲染崩溃。

    上一版 params 那条只回 {exposure, radius, ops, lit}，用户拖完"修容档数"松手，
    App 读 lastLight.field_peak.toFixed(2) 直接 TypeError。谎报发生在 JSON 边界上，
    TS 编译期抓不到（引擎交出来的是无类型 JSON），所以这条只能在协议层钉。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.3)
    h, w = meta["h"], meta["w"]
    rle = _brush_rle(h, w, h // 3, w // 3, 6)
    got = {}
    engine.send(cmd="light", action="add", rle=rle, sign=1)
    got["add"] = engine.wait_for("light_done", timeout=60)
    engine.send(cmd="light", action="params", exposure=0.9)
    got["params"] = engine.wait_for("light_done", timeout=60)
    engine.send(cmd="light", action="undo")
    got["undo"] = engine.wait_for("light_done", timeout=60)
    engine.send(cmd="light", action="redo")
    got["redo"] = engine.wait_for("light_done", timeout=60)
    engine.send(cmd="light", action="clear")
    got["clear"] = engine.wait_for("light_done", timeout=60)
    # 与 ui/src/native.ts 的 LightInfo 里声明为必存的字段一一对应
    required = {"action": str, "ops": int, "redo_pending": int, "painted_px": int,
                "field_peak": float, "lit": bool, "exposure": float, "radius": int,
                "light_build_ms": float, "light_ms": float, "filter_ms": float,
                "bands_ms": float, "render_ms": float, "total_ms": float,
                "bytes_light": int, "layer_recomputed": bool, "filter_cached": bool,
                "device": str, "strength": float}
    for act, ev in got.items():
        missing = sorted(k for k in required if k not in ev)
        assert not missing, f"{act} 那条缺字段 {missing}：UI 按必存读会读到 undefined"
        wrong = {k: type(ev[k]).__name__ for k, t in required.items()
                 if not isinstance(ev[k], t)
                 and not (t is float and isinstance(ev[k], (int, float)) and not isinstance(ev[k], bool))}
        assert not wrong, f"{act} 那条类型不对：{wrong}"
    # 专门把 params 与建层那条摆一起比：上一版就是这一条臂漂了
    assert set(got["params"]) - set(got["add"]) <= {"action"}, \
        f"params 那条多/少了键：{set(got['params']) ^ set(got['add'])}"
    assert got["params"]["lit"] is True and got["params"]["exposure"] == 0.9, got["params"]
    assert got["params"]["layer_recomputed"] is False, \
        "只改参数不重算场，报 layer_recomputed=True 就是假指标"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_landmark_change_rebuilds_the_resident_deform_field(engine):
    """关键点一换，已常驻的单位场必须真的重解：不然旧几何继续瘦这一张脸。

    上一版 cmd_precompute 什么也不做：template 建层后再 precompute，cmd_deform 看见
    built=True 就不再重解，而 deform_done 把 landmark_backend 报成新后端——上报与
    画面双向错配，而且"有变化、无异常、指标全绿"。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="precompute", backend="template")
    engine.wait_for("precompute_ready", timeout=60)
    peer = FrameShm(meta["name"])
    try:
        _nudge_frame(engine, 0.0)
        engine.send(cmd="deform", action="set", amounts={"slim_face": 0.8})
        first = engine.wait_for("deform_done", timeout=60)
        assert first["build"]["deform_builds"] == 1, first
        lit_px = _read_frame(engine, peer, meta["h"], meta["w"])
        # 再来一次 precompute：换了关键点就得真的重解，而滑块值原样保留
        engine.send(cmd="precompute", backend="template")
        engine.wait_for("precompute_ready", timeout=60)
        rb = engine.wait_for("deform_done", timeout=60)
        assert rb["action"] == "rebuild", rb
        assert rb["deform_builds"] == 2, f"关键点换了但单位场没重解：{rb}"
        assert rb["built"] is True and rb["lit"] is True, rb
        assert rb["amounts"]["slim_face"] == 0.8, f"重建不许把用户的滑块归零：{rb}"
        assert rb["landmark_backend"] == "template", rb
        assert rb["build"]["deform_build_ms"] > 0, rb
        # 重建那条必须补帧（不补就是“引擎已按新几何重建、屏幕停在旧像素”）；而同一批
        # 关键点重解出的单位场必须是同一个东西，所以两帧应当逐字节相等
        assert np.array_equal(_read_frame(engine, peer, meta["h"], meta["w"]), lit_px), \
            "同一批关键点重解后画面变了：TPS 解算不再确定性，换设备/重建重放那条全不可信"
        # 重建之后再拖滑块：不能再解（零推理那条承诺不因重建而失效）
        engine.send(cmd="deform", action="set", amounts={"slim_face": 0.4})
        after = engine.wait_for("deform_done", timeout=60)
        assert "build" not in after and after["deform_builds"] == 2, after
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_synthetic_landmarks_invalidate_a_built_deform_layer(engine):
    """后端换成不能按脸形语义取点的 synthetic：整层清除并明说，不能默默继续用旧几何。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="precompute", backend="template")
    engine.wait_for("precompute_ready", timeout=60)
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.9})
    first = engine.wait_for("deform_done", timeout=60)
    assert first["lit"] is True, first
    engine.send(cmd="precompute", backend="synthetic")
    engine.wait_for("precompute_ready", timeout=60)
    ev = engine.wait_for("deform_done", timeout=60)
    assert ev["action"] == "invalidate", ev
    assert ev["built"] is False and ev["lit"] is False and ev["bytes_deform"] == 0, ev
    assert ev["amounts"]["slim_face"] == 0.0, ev
    assert ev["dropped_amounts"]["slim_face"] == 0.9, \
        f"清层得说清刚才滑块是多少，否则用户看到的是滑块自己弹回零：{ev}"
    assert ev["landmark_backend"] == "synthetic", ev
    # 失效之后一条 set 必须重新走建层判定，并再次整条拒（不能拿旧的模板场继续服务）
    engine.send(cmd="deform", action="set", amounts={"slim_face": 0.5})
    _expect_error(engine, "synthetic")


# ============================================================ 调色（M3-a2）
# 这一节只量接线：方向、字节、事件形状、拒绝路径。表本身的数学已在 test_lut.py 钉死，
# 所以这里故意用“每通道乘一个常数”这种最素的表——方向判据要的是唯一答案。
def _write_cube(tmp_path, size: int = 8, k: float = 0.9, identity: bool = False) -> str:
    """烘一张「每通道乘 k」的 .cube 写进 tmp_path，返回路径（identity=True 就是恒等表）。"""
    t = np.linspace(0.0, 1.0, size)
    bb, gg, rr = np.meshgrid(t, t, t, indexing="ij")
    rows = np.stack([rr, gg, bb], axis=-1)                       # (B,G,R,3)：B 最外层
    out = rows if identity else np.clip(rows * k, 0.0, 1.0)
    lines = [f"LUT_3D_SIZE {size}", f'TITLE "k{size}-{k}"']
    lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in out.reshape(-1, 3)]
    path = tmp_path / f"grade-{size}-{k}{'-id' if identity else ''}.cube"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_lut_set_darkens_the_frame_in_the_direction_the_table_says(engine, tmp_path):
    """协议层的 LUT 直通：压暗表必须让画面变暗，而且上报得说清是哪一张表。

    不看字节看方向与幅度：接错通道、接反顺序、表根本没挂上——三种错都会让字节“变了”，
    但只有方向与幅度能把它们区分开（与 M2-a2 修容那条同一个理由）。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", path=_write_cube(tmp_path, 8, 0.9))
        done = engine.wait_for("lut_done", timeout=60)
        assert done["lut_set"] is True and done["lut_lit"] is True, done
        assert done["lut_size"] == 8 and done["lut_source"].endswith(".cube"), done
        assert done["lut_neutral"] is False and done["lut_amount"] == 1.0, done
        assert done["bytes_lut"] > 0 and done["lut_ms"] >= 0.0, done
        # 粗表得把精度不足说出来：这是库层的 notes，协议层不许把它吞掉
        assert any("8³" in n for n in done["lut_notes"]), done["lut_notes"]
        shot = _read_frame(engine, peer, h, w)
        d = (shot - base).astype(np.float64)
        assert float(d.mean()) < -1.0, f"压暗表却让画面均值为 {d.mean():+.2f} LSB：方向接反"
        assert float((np.abs(d) > 0).mean()) > 0.5, "改色只动了不到半张图：链路没通"
        assert float(np.abs(d).mean()) > 0.5, f"平均改动 {float(np.abs(d).mean()):.3f} LSB 太少"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_lut_identity_table_reports_loaded_but_leaves_every_byte(engine, tmp_path):
    """恒等表：“载入了一张表”与“画面动了”必须在上报里分开说。

    M3-a1 那个缺陷的形状是 DOMAIN 非 0–1 的表被当成恒等短路，于是“载入成功但一动不动”。
    反过来说，真正的恒等表**应当**一动不动——区别只在事件有没有把这件事说清楚。
    所以这里两条都卡：字节不动 + lut_neutral=True + lut_lit=False。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", path=_write_cube(tmp_path, 17, 1.0, identity=True))
        done = engine.wait_for("lut_done", timeout=60)
        assert done["lut_set"] is True, done
        assert done["lut_neutral"] is True and done["lut_lit"] is False, done
        assert done["lut_ms"] == 0.0, f"恒等表走了非短路那条路：{done}"
        # 体积不挂，但 CPU 原件常驻：账单只报一份就是藏账
        assert done["lut_grid_bytes"] > 0 and done["bytes_lut"] == done["lut_grid_bytes"], done
        assert np.array_equal(_read_frame(engine, peer, h, w), base), "恒等表改了画面"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_lut_amount_zero_is_byte_exact_over_ipc(engine, tmp_path):
    """强度归零必须逐字节回到未调色那一帧，而且采样一次也不跑。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", path=_write_cube(tmp_path, 8, 0.75), amount=0.6)
        done = engine.wait_for("lut_done", timeout=60)
        assert done["lut_amount"] == 0.6 and done["lut_lit"] is True, done
        graded = _read_frame(engine, peer, h, w)
        assert not np.array_equal(graded, base), "强度 0.6 却一点没动"
        engine.send(cmd="lut", action="amount", amount=0.0)
        zero = engine.wait_for("lut_done", timeout=60)
        assert zero["lut_lit"] is False and zero["lut_ms"] == 0.0, zero
        assert zero["lut_set"] is True and zero["lut_size"] == 8, \
            f"强度归零把表也丢了：{zero}"
        assert np.array_equal(_read_frame(engine, peer, h, w), base), "强度 0 却没逐字节还原"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_lut_arms_emit_the_same_event_shape(engine, tmp_path):
    """三条 action 臂的事件键集必须完全相等（含命令层加的那几个计时键）。

    库层用例卡的是 payload 的键集，这里卡的是**送出去的那一条**：两边都卡才封得住，
    因为漂往往发生在 cmd 层 `**info` 之后又手写几个字段的那一步。
    """
    _needs_torch()
    _load(engine, max_px=207360, strength=0.0)
    events = []
    # 逐条发、逐条收：wait_for 会把中间不匹配的事件吃掉，所以“三条全发再三条全等”
    # 拿到的是丢帧后的残流（本轮就这么错了一次）。lut_done 与它的 frame 在同一条命令里
    # 是固定次序（先状态后帧），按命令配对收才是确定性的。
    for kw in [dict(action="set", path=_write_cube(tmp_path, 8, 0.9)),
               dict(action="amount", amount=0.4),
               dict(action="clear")]:
        engine.send(cmd="lut", **kw)
        events.append(engine.wait_for("lut_done", timeout=60))
        engine.wait_for("frame", timeout=60)
    keys = [set(e) for e in events]
    assert keys[0] == keys[1] == keys[2], \
        f"事件形状漂了：{(keys[0] ^ keys[1]) | (keys[0] ^ keys[2])}"
    for k in ("lut_ms", "render_ms", "total_ms", "filter_ms", "bands_ms",
              "filter_cached", "deform_ms", "bytes_lut", "lut_source", "lut_amount",
              "lut_notes", "lut_clipped", "lut_domain_min", "device", "strength",
              "layer_recomputed", "action"):
        assert k in keys[0], k
    # 补的那一帧仍得命中磨皮缓存：这是“调色在链尾、不作废上游缓存”的协议级证据
    assert events[0]["filter_cached"] is True and events[0]["bands_ms"] == 0.0, events[0]


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_bad_lut_commands_leave_no_trace(engine, tmp_path):
    """被拒绝的调色命令整条不留痕：表没换、强度没改、画面还是原样。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.4)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        good = _write_cube(tmp_path, 8, 0.9)
        engine.send(cmd="lut", action="nope")
        _expect_error(engine, "未知 lut action")
        engine.send(cmd="lut", action="set")
        _expect_error(engine, "只能给一个来源")
        engine.send(cmd="lut", action="set", path=good, text="LUT_3D_SIZE 2\n0 0 0\n")
        _expect_error(engine, "只能给一个来源")
        engine.send(cmd="lut", action="set", path=str(tmp_path / "没有这个文件.cube"))
        _expect_error(engine, "LUT 被拒")
        engine.send(cmd="lut", action="set", text="不是 cube 的一坨文本\n1 2 3 4\n")
        _expect_error(engine, "LUT 被拒")
        engine.send(cmd="lut", action="set", path=good, amount=1.5)
        _expect_error(engine, "超出范围")
        engine.send(cmd="lut", action="set", path=good, amount=float("nan"))
        _expect_error(engine, "不是有限数")
        # 没挂表就调强度：库层与命令层各拦一次，两条都不许静默通过
        engine.send(cmd="lut", action="amount", amount=0.5)
        _expect_error(engine, "还没有 LUT")
        engine.send(cmd="lut", action="amount")
        _expect_error(engine, "什么也没给")
        # 拒绝之后状态必须是干净的：clear 报出 lut_set=False，画面与基线逐字节相同
        engine.send(cmd="lut", action="clear")
        done = engine.wait_for("lut_done", timeout=60)
        assert done["lut_set"] is False and done["lut_size"] == 0, done
        assert done["bytes_lut"] == 0 and done["lut_source"] == "", done
        assert np.array_equal(_read_frame(engine, peer, h, w), base), "被拒的调色命令动了画面"
        # 而一条合法命令必须还能正常生效（拒绝路径不能把会话弄成不可用）
        engine.send(cmd="lut", action="set", path=good)
        assert engine.wait_for("lut_done", timeout=60)["lut_lit"] is True
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_importing_a_new_image_drops_the_previous_grade(engine, tmp_path):
    """调色层随文档走：换图不能把上一张的色调静默带过来。"""
    _needs_torch()
    _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="lut", action="set", path=_write_cube(tmp_path, 8, 0.9))
    assert engine.wait_for("lut_done", timeout=60)["lut_lit"] is True
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="load_image", path=_other_image(tmp_path), strength=0.0)
    engine.wait_for("vram_ready", timeout=60)
    ready = engine.wait_for("image_ready", timeout=60)
    assert ready["bytes_lut"] == 0, f"换到另一张图却带着上一张的调色体积：{ready['bytes_lut']}"
    # 引擎侧那两个字段也得跟着清：留着就是下一条 amount 会以为表还在
    engine.send(cmd="lut", action="amount", amount=0.5)
    _expect_error(engine, "还没有 LUT")


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_drag_stream_with_lut_runs_every_frame_but_recomputes_nothing(engine, tmp_path):
    """挂着表拖 600 帧：滤波与修容一次都不重算，而调色每帧真在跑。

    最后那条是反向门禁：lut_frames 如果为 0，“常驻层里有一层调色”就只存在于上报里。
    它与 deform_builds 不增是两件事——那一条证“不解 TPS”，这一条证“层真的在服务”。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.5)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="lut", action="set", path=_write_cube(tmp_path, 33, 0.85))
    done = engine.wait_for("lut_done", timeout=60)
    assert done["lut_size"] == 33 and done["lut_lit"] is True, done
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="bench_start", mode="image_stream", frames=6, interval_ms=20,
                w=w, h=h)
    engine.wait_for("bench_started", timeout=30)
    b = engine.wait_for("bench_done", timeout=90)
    assert not b.get("failed"), f"跑靶失败：{b}"
    assert b["refilter_frames"] == 0, f"拖拽流里重算了 {b['refilter_frames']} 次滤波"
    assert b["relight_frames"] == 0, f"拖拽流里重算了 {b['relight_frames']} 次修容"
    assert b["deform_builds"] == 0, f"拖拽流里重解了 {b['deform_builds']} 次 TPS"
    assert b["lut_frames"] == b["frames"], \
        f"挂了表却只跑了 {b['lut_frames']}/{b['frames']} 帧调色：这一层没在服务"
    assert b["lut"] > 0.0, f"调色段均值 {b['lut']} ms 为 0，与 lut_frames 对不上"
    assert b["seg_over_frames"] == 0, f"分段重复计时 {b['seg_over_frames']} 帧"
    st = b["lut_state"]
    assert st["lit"] is True and st["size"] == 33 and st["bytes_lut"] > 0, st


# ============================================================ 肤色定向与预设（M3-b）
# 这一节的分工与 test_grade/test_presets 一致：库层管数学，这里只管**接线**——
# 方向、字节、事件形状、拒绝路径、跨层语义（预设一层命令动两层）。
GRADE_KEYS = ("grade_dh", "grade_ds", "grade_dv", "grade_amount", "grade_set", "grade_lit",
              "grade_limits", "bytes_grade", "device", "layer_recomputed")


def _sat(frame):
    """饱和度（max−min)/max：不需要完整 HSV，方向判据只要这一个量。"""
    a = np.asarray(frame, dtype=np.float64) / 255.0
    mx = a.max(axis=-1)
    mn = a.min(axis=-1)
    return np.where(mx > 0, (mx - mn) / np.where(mx > 0, mx, 1.0), 0.0)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_grade_set_moves_saturation_in_the_declared_direction(engine):
    """协议直通：ds=−0.6 必须让肤色像素降饱和，而且改色只发生在"有颜色的地方"。

    看方向而不是看字节：接错通道、参数没送进内核、内核根本没跑，三种错都会让字节
    "变了"，只有方向与分布能把它们分开（M2-a2 修容与 M3-a2 调色同一理由）。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="grade", action="set", dh=0.0, ds=-0.6, dv=0.0)
        done = engine.wait_for("grade_done", timeout=60)
        assert done["grade_set"] is True and done["grade_lit"] is True, done
        assert done["grade_ds"] == -0.6 and done["grade_amount"] == 1.0, done
        assert done["grade_ms"] > 0.0, f"点火了却没跑内核：{done}"
        assert done["grade_limits"] == [0.05, 0.60, 0.60], done
        assert done["bytes_grade"] == 0, "这层不持有张量，账单必须是 0（报而不藏）"
        assert done["filter_cached"] is True, f"设肤色参数却重算了滤波：{done}"
        shot = _read_frame(engine, peer, h, w)
        d = (shot - base).astype(np.float64)
        changed = np.abs(d).max(axis=-1) > 0
        assert float(changed.mean()) > 0.05, f"改动面只有 {float(changed.mean()):.2%}：链路没通"
        s0, s1 = _sat(base), _sat(shot)
        moved = (s1 - s0)[changed]
        assert float((moved < 0).mean()) > 0.9, \
            f"降饱和方向：只有 {float((moved < 0).mean()):.2%} 的改动像素饱和下降"
        assert np.array_equal(d[~changed], np.zeros(((~changed).sum(), 3))), \
            "窗外像素被改了：定向写成了全图调整"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_grade_zero_params_report_off_and_run_nothing(engine):
    """显式把三个增量设为 0 = 关灯：画面逐字节不动、内核一次不跑，而层"还在"。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="grade", action="set", dh=0.01, ds=-0.3, dv=0.2)
        assert engine.wait_for("grade_done", timeout=60)["grade_lit"] is True
        hot = _read_frame(engine, peer, h, w)
        assert not np.array_equal(hot, base), "点了火却没动画面：后面那条比对就是假的"
        engine.send(cmd="grade", action="set", dh=0.0, ds=0.0, dv=0.0)
        done = engine.wait_for("grade_done", timeout=60)
        assert done["grade_set"] is False and done["grade_lit"] is False, done
        assert done["grade_ms"] == 0.0, "全零参数却跑了内核：结构短路没接上"
        assert np.array_equal(_read_frame(engine, peer, h, w), base), \
            "把参数归零之后画面还带着上一组的色：帧不是按当前状态出的"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_bad_grade_commands_leave_no_trace(engine):
    """非法参数/错 action/多余键/未导图：一律整条拒，而且拒完状态是干净的。"""
    _needs_torch()
    _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="grade", action="nope")
    _expect_error(engine, "未知 grade action")
    engine.send(cmd="grade", action="set")
    _expect_error(engine, "什么也没给")
    engine.send(cmd="grade", action="set", dh=0.9)
    _expect_error(engine, "整条不生效")
    engine.send(cmd="grade", action="set", ds=float("nan"))
    _expect_error(engine, "整条不生效")
    engine.send(cmd="grade", action="set", dv=0.2, amount=1.5)
    _expect_error(engine, "整条不生效")
    engine.send(cmd="grade", action="set", ds=-0.3, degreed=0.2)      # 拼错的键必须被拒
    _expect_error(engine, "不认识的参数")
    engine.send(cmd="grade", action="amount")
    _expect_error(engine, "什么也没给")
    # 被拒之后层必须是干净的：clear 报出全零，而不是"留着刚才那半截"
    engine.send(cmd="grade", action="clear")
    done = engine.wait_for("grade_done", timeout=60)
    assert done["grade_lit"] is False and done["grade_ds"] == 0.0, done
    assert done["bytes_grade"] == 0, done


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_grade_done_arms_emit_the_same_event_shape(engine):
    """三条 action 臂过一遍 IPC：事件形状在 JSON 边界上不许漂（M2 审 ① 的原形状）。"""
    _needs_torch()
    _load(engine, max_px=207360, strength=0.0)
    events = []
    for kw in ({"action": "set", "ds": -0.3}, {"action": "amount", "amount": 0.5},
               {"action": "clear"}):
        engine.send(cmd="grade", **kw)
        events.append(engine.wait_for("grade_done", timeout=60))
        engine.wait_for("frame", timeout=60)
    extra = ("grade_ms", "lut_ms", "filter_ms", "bands_ms", "filter_cached",
             "deform_ms", "render_ms", "total_ms", "strength", "lut_preset", "action")
    for k in GRADE_KEYS:
        assert all(k in e for e in events), f"{k} 在某一臂里丢了"
    # 每帧分段与命令层计时得由协议层加：库层的 payload 里没有它们
    for k in extra:
        assert all(k in e for e in events), f"{k} 在某一臂里丢了"
    # 键集**闭合**：宿主那一侧的 TS 接口把每个字段都声明成必存，而谎报发生在 JSON
    # 边界上、编译期抓不到。M5-b 的真窗口轮就是这么撞上一次事故——grade_done 是铺平
    # 的一份（grade_dh / grade_amount / grade_lit），嵌套那份 grade_state 才是
    # dh / amount / lit；UI 把两套名字混进一个接口去读 .amount，渲染时一句
    # TypeError 把整棵 React 树拆掉，画面冻结在 0 帧（delivered=0）。
    # 所以这里同时钉两头：少一个键不行，把嵌套那套的短名字混进来也不行。
    want = {"event"} | set(GRADE_KEYS) | set(extra)
    for e in events:
        assert set(e) == want, f"grade_done 的键集漂了：多 {sorted(set(e) - want)}" \
                               f" 少 {sorted(want - set(e))}"
        for alias in ("dh", "ds", "dv", "amount", "lit"):
            assert alias not in e, f"grade_done 里出现了嵌套层的短名字 {alias}：宿主会读错一份"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_grade_and_lut_are_independent_layers(engine, tmp_path):
    """两层各自可关：清定向不能把表也清了，反之也一样。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", path=_write_cube(tmp_path, 8, 0.9))
        assert engine.wait_for("lut_done", timeout=60)["lut_lit"] is True
        engine.wait_for("frame", timeout=60)
        engine.send(cmd="grade", action="set", ds=-0.3)
        g = engine.wait_for("grade_done", timeout=60)
        assert g["grade_lit"] is True, g
        engine.wait_for("frame", timeout=60)
        engine.send(cmd="grade", action="clear")
        done = engine.wait_for("grade_done", timeout=60)
        assert done["grade_lit"] is False, done
        # 层的独立性由"另一层的现状仍在事件里"来证，而不是靠 UI 记状态
        assert done["lut_ms"] >= 0.0 and done["lut_preset"] is None, done
        engine.send(cmd="lut", action="amount", amount=1.0)
        l = engine.wait_for("lut_done", timeout=60)
        assert l["lut_set"] is True and l["lut_lit"] is True, l
        assert l["grade_state"]["lit"] is False, f"清掉的定向又活了：{l}"
        assert l["lut_preset"] is None, "走 path 载表却还带着预设身份"
        engine.send(cmd="lut", action="clear")
        assert engine.wait_for("lut_done", timeout=60)["lut_lit"] is False
        assert np.array_equal(_read_frame(engine, peer, h, w), base), "两层都关了画面却没还原"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_one_preset_command_sets_both_layers(engine):
    """一键预设 = 一张表 + 三个数：一条命令之后两层都得点着，而且数字来自资产。"""
    _needs_torch()
    from lumaretouch_engine.ops.presets import preset_grade as pg

    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    dh, ds, dv = pg("creamy")
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", preset="creamy")
        done = engine.wait_for("lut_done", timeout=60)
        assert done["lut_source"] == "preset:creamy", done
        assert done["lut_title"] == "韩系奶油" and done["lut_size"] == 33, done
        assert done["lut_preset"] == "creamy", done
        assert done["lut_lit"] is True and done["bytes_lut"] > 0, done
        g = done["grade_state"]
        assert (g["dh"], g["ds"], g["dv"]) == (dh, ds, dv), g
        assert g["lit"] is True and g["amount"] == 1.0, g
        assert done["grade_ms"] > 0.0, f"预设的定向层没跑：{done}"
        shot = _read_frame(engine, peer, h, w)
        d = np.abs((shot - base).astype(np.float64))
        assert float((d.max(axis=-1) > 0).mean()) > 0.5, \
            f"一键预设只改了 {float((d.max(axis=-1) > 0).mean()):.2%} 像素：不像上了预设"
        s0, s1 = _sat(base), _sat(shot)
        moved = (s1 - s0)[d.max(axis=-1) > 0]
        assert float((moved < 0).mean()) > 0.6, "奶油说降饱和，改动像素却多数在升"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_preset_amount_scales_both_layers_and_zero_is_byte_exact(engine):
    """预设强度是"整预设"的强度：0.4 要两层同时 0.4，归 0 要逐字节回到基线。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", preset="creamy", amount=0.4)
        done = engine.wait_for("lut_done", timeout=60)
        assert done["lut_amount"] == 0.4, done
        assert done["grade_state"]["amount"] == 0.4, \
            f"表的强度归 0.4 而肤色层还是 {done['grade_state']['amount']}：预设被拆开了"
        engine.wait_for("frame", timeout=60)
        engine.send(cmd="lut", action="amount", amount=0.0)
        zero = engine.wait_for("lut_done", timeout=60)
        assert zero["lut_lit"] is False and zero["grade_state"]["lit"] is False, zero
        assert zero["grade_state"]["amount"] == 0.0, zero
        assert zero["lut_ms"] == 0.0 and zero["grade_ms"] == 0.0, \
            f"强度归零却还在跑内核：{zero['lut_ms']}/{zero['grade_ms']}"
        assert np.array_equal(_read_frame(engine, peer, h, w), base), \
            "预设强度归 0 之后画面回不到基线：混色式或短路写错了"
        # 归 0 之后预设身份还在（只是强度 0），下一条 amount 仍应连带定向层
        engine.send(cmd="lut", action="amount", amount=0.8)
        back = engine.wait_for("lut_done", timeout=60)
        assert back["grade_state"]["amount"] == 0.8 and back["grade_state"]["lit"] is True, back
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_preset_clear_takes_both_layers_down(engine, tmp_path):
    """预设两层一起上，clear 就得两层一起下；而用户自己的肤色不许被清表带走。

    真图端到端试验量出来的：`lut set preset=creamy` 之后一记 `lut clear`，表下来了
    而预设写进肤色定向的那三个数还在画面上（与出厂帧差 63771 像素），而面板上
    已经没有任何东西指着它。`lut set` 那一臂代码里自己写着“预设要么两层都上，
    要么都不上”——不对称的那一半就在 clear 上。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", preset="creamy", amount=1.0)
        on = engine.wait_for("lut_done", timeout=60)
        assert on["preset_grade_cleared"] is False, on        # set 那一臂不动别人的东西
        assert on["grade_state"]["lit"] is True, on
        engine.wait_for("frame", timeout=60)
        engine.send(cmd="lut", action="clear")
        off = engine.wait_for("lut_done", timeout=60)
        assert off["preset_grade_cleared"] is True, off
        assert off["grade_state"]["lit"] is False, f"预设的肤色还亮着：{off['grade_state']}"
        assert off["grade_state"]["dh"] == 0.0 and off["grade_state"]["ds"] == 0.0, off
        assert np.array_equal(_read_frame(engine, peer, h, w), base), \
            "清掉预设之后画面必须逐字节回到出厂帧"

        # 反向：自己载表 + 手动改肤色时，清表不许伸进用户的肤色里
        cube = _write_cube(tmp_path, k=0.9)
        engine.send(cmd="lut", action="set", path=cube, amount=1.0)
        assert engine.wait_for("lut_done", timeout=60)["lut_preset"] is None
        engine.send(cmd="grade", action="set", dh=0.02, ds=-0.05, dv=0.03, amount=1.0)
        engine.wait_for("grade_done", timeout=60)
        engine.wait_for("frame", timeout=60)
        engine.send(cmd="lut", action="clear")
        mine = engine.wait_for("lut_done", timeout=60)
        assert mine["preset_grade_cleared"] is False, mine
        assert mine["grade_state"]["lit"] is True, \
            f"用户自己调的肤色被清表顺手拿掉了：{mine['grade_state']}"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_manual_grade_drops_the_preset_identity(engine):
    """用户手动动了肤色层，表的强度就不许再伸进肤色层——预设身份当场失效。"""
    _needs_torch()
    _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="lut", action="set", preset="creamy")
    done = engine.wait_for("lut_done", timeout=60)
    engine.wait_for("frame", timeout=60)
    assert done["lut_preset"] == "creamy" and done["grade_state"]["amount"] == 1.0, done
    engine.send(cmd="grade", action="set", ds=-0.5)
    g = engine.wait_for("grade_done", timeout=60)
    assert g["lut_preset"] is None, f"手动改了肤色却还留着预设身份：{g}"
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="lut", action="amount", amount=0.3)
    l = engine.wait_for("lut_done", timeout=60)
    assert l["lut_amount"] == 0.3, l
    assert l["grade_state"]["amount"] == 1.0, \
        f"表的强度把用户手调的肤色层一起拉走了：{l['grade_state']}"
    assert l["grade_state"]["ds"] == -0.5, l


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_unknown_preset_is_rejected_without_touching_anything(engine):
    """错预设名整条拒，而且两层都不动：不许"表上了、数字没上"。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base = _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", preset="weishimei")
        _expect_error(engine, "没有这个预设")
        engine.send(cmd="lut", action="amount", amount=0.5)
        _expect_error(engine, "还没有 LUT")
        # 被拒的命令不出帧，所以得先用一条会出帧的把"现在屏幕上是什么"取回来：
        # 层本来就空时 clear 也是一次正常提交（与 test_lut 那一节同一形状）
        engine.send(cmd="lut", action="clear")
        empty = engine.wait_for("lut_done", timeout=60)
        assert empty["lut_set"] is False and empty["bytes_lut"] == 0, empty
        assert np.array_equal(_read_frame(engine, peer, h, w), base), "被拒的预设改了画面"
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_importing_a_new_image_drops_the_skin_tuning(engine, tmp_path):
    """定向层随文档走：换到另一张图之后 image_ready 里那一份快照必须全是零。"""
    _needs_torch()
    _load(engine, max_px=207360, strength=0.0)
    engine.send(cmd="grade", action="set", dh=0.01, ds=-0.3, dv=0.2)
    assert engine.wait_for("grade_done", timeout=60)["grade_lit"] is True
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="load_image", path=_other_image(tmp_path), strength=0.0)
    engine.wait_for("vram_ready", timeout=60)
    ready = engine.wait_for("image_ready", timeout=60)
    g = ready["grade_state"]
    assert g["lit"] is False and (g["dh"], g["ds"], g["dv"]) == (0.0, 0.0, 0.0), \
        f"新会话继承了上一张图的肤色参数：{g}"
    assert g["amount"] == 1.0 and g["bytes_grade"] == 0, g
    assert ready["bytes_lut"] == 0, ready


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_drag_stream_with_grade_runs_every_frame_but_recomputes_nothing(engine):
    """挂着肤色层拖 600 帧：每帧真跑内核，而滤波/修容/TPS 一次都不重算。

    grade_frames == frames 是反向门禁：这层如果只存在于上报里，这个数就是 0。
    """
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.5)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="grade", action="set", dh=0.006, ds=-0.3, dv=0.2)
    done = engine.wait_for("grade_done", timeout=60)
    assert done["grade_lit"] is True, done
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="bench_start", mode="image_stream", frames=6, interval_ms=20, w=w, h=h)
    engine.wait_for("bench_started", timeout=30)
    b = engine.wait_for("bench_done", timeout=90)
    assert not b.get("failed"), f"跑靶失败：{b}"
    assert b["refilter_frames"] == 0, f"拖拽流里重算了 {b['refilter_frames']} 次滤波"
    assert b["relight_frames"] == 0, f"拖拽流里重算了 {b['relight_frames']} 次修容"
    assert b["deform_builds"] == 0, f"拖拽流里重解了 {b['deform_builds']} 次 TPS"
    assert b["grade_frames"] == b["frames"], \
        f"设了肤色参数却只跑了 {b['grade_frames']}/{b['frames']} 帧：这一层没在服务"
    assert b["grade"] > 0.0, f"定向段均值 {b['grade']} ms 为 0，与 grade_frames 对不上"
    assert b["seg_over_frames"] == 0, f"分段重复计时 {b['seg_over_frames']} 帧"
    st = b["grade_state"]
    assert st["lit"] is True and st["dh"] == 0.006 and st["bytes_grade"] == 0, st


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_grade_is_refused_while_bench_is_running(engine):
    """跑靶进行中改图层会污染那份数据：与 lut/deform/set_strength 同一条互斥。"""
    _needs_torch()
    meta = _load(engine, max_px=207360, strength=0.5)
    engine.send(cmd="bench_start", mode="image_stream", frames=400, interval_ms=20,
                w=meta["w"], h=meta["h"])
    engine.wait_for("bench_started", timeout=30)
    try:
        engine.send(cmd="grade", action="set", ds=-0.3)
        _expect_error(engine, "跑靶进行中，拒绝 grade")
        engine.send(cmd="lut", action="set", preset="creamy")
        _expect_error(engine, "跑靶进行中，拒绝 lut")
    finally:
        engine.send(cmd="bench_stop")
        engine.wait_for("bench_done", timeout=90)


def test_ready_event_lists_the_builtin_presets(engine):
    """预设清单由引擎在 ready 里报出来：UI 的按钮不是前端抄的一份名字。

    这条不需要 torch 也不需要真图——它是 CI 的 CPU job 里唯一能卡住“资产改了名而
    UI 还拿着旧名去撞拒绝”的位置。名字漂了不是报错而是按钮全灭，所以必须在这里钉。
    """
    engine.send(cmd="hello")
    ready = engine.wait_for("ready", timeout=30)
    assert ready["protocol"] == 1, ready
    got = {p["name"] for p in ready["presets"]}
    assert got == {"creamy", "coolwhite"}, f"预设清单与资产对不上：{ready['presets']}"
    assert all(p["title"] for p in ready["presets"]), "按钮要有可读标题，不能只有英文键名"


# ============================================================ M4 全尺寸导出（协议层）
# 这批用例管的是命令签名与事件形状——库层的分块保真在 test_export.py 里已经逐条钉过，
# 协议层不许重抄一份数学判据，那只会漂移出两个答案。
# EXPORT_KEYS 从引擎拿，不在这里刻一份：本仓对"双出处"付过多次钱（格式名单、
# grade 边界、版本号）——上一轮它就在这一行默默漂过：测试里那份少了 scale/sharpen/upscale_backend，
# 而引擎里已有，当时只是没断言到它们身上，漂移看不出来。
from lumaretouch_engine.server import Engine as _Engine

EXPORT_KEYS = _Engine.EXPORT_KEYS


def _next_error_or(engine, timeout: float = 20.0, ignore=("frame", "_raw")):
    """等一条**对得上这次命令**的答复：`error` 或任一 `export_*`，其余全部是 chatter。

    为什么不拿"下一个事件"当答复：导出一被拒就不发任何 export_* 事件，而此刻会话
    还在逐帧发 frame，还会补一条 session_state（load_image 的文档登记）——上一版就先
    报在 frame、再报在 session_state 上，看起来像"没报错"，而那句 error 就在后面两三
    条。拿白名单挑答复，才是"这条命令说了什么"。返回 export_* 表示**没被拒**，
    caller 那边的断言会把它当失败报出来，不会假装通过。
    """
    deadline = time.monotonic() + timeout
    seen: list = []
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError(f"{timeout}s 内没等到答复；路上事件={seen}")
        e = engine.next_event(timeout=min(left, 10.0))
        name = e.get("event", "")
        if name == "error" or name.startswith("export_"):
            return e
        if name not in ignore:
            seen.append(name)


def _collect_until(engine, event: str, timeout: float = 240.0):
    """自己读到某个事件为止，把路上的其它事件留着。

    不用 wait_for：它会把非目标事件丢掉，于是"这一批真的发过逐图进度"这句话
    在这条路上永远没法验。
    """
    deadline = time.monotonic() + timeout
    seen: list = []
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError(f"没等到 {event}；路上事件={[e.get('event') for e in seen]}")
        e = engine.next_event(timeout=min(left, 10.0))
        if e.get("event") == event:
            return e, seen
        if e.get("event") == "error":
            raise AssertionError(f"引擎报错: {e.get('error')}")
        seen.append(e)


def test_ready_advertises_the_export_surface(engine):
    """导出的格式名单与 tile 范围由 ready 报出，前端不抄一份。

    这条不需要 torch：CI 的 CPU job 也能卡住"引擎改了边界而 UI 还按旧的渲染"。
    """
    engine.send(cmd="hello")
    ready = engine.wait_for("ready", timeout=30)
    assert "jpg" in ready["export_formats"] and "png" in ready["export_formats"], ready
    lo, hi = ready["export_tile"]
    assert 64 <= lo < hi and lo <= ready["export_tile_default"] <= hi, ready


@pytest.mark.parametrize("bad,what", [
    ({"format": "bmp"}, "格式"),
    ({"tile": 64}, "tile"),
    ({"tile": 99999}, "tile"),
    ({"quality": 0}, "quality"),
    ({"quality": 101}, "quality"),
    ({"quality": "x"}, "整数"),
    ({"images": [""]}, "images"),
    ({"images": "not-a-list"}, "images"),
    ({"out_dir": ""}, "out_dir"),
    ({"action": "status"}, "action"),
])
def test_export_param_boundaries_are_refused_without_events(engine, bad, what):
    """非法参数整条拒：不发 export_progress、不发 export_done、不落半截文件。

    被拒的命令若还发进度事件，UI 的进度条会走完后发现什么都没有——那比直接报错坑。
    探针用 hello：它一定发事件，而且与导出无关，不会被"上一条其实偷偷跑了"蒙过去。
    """
    msg = {"cmd": "export", "out_dir": "/tmp", "format": "jpg", "images": [FIXTURE]}
    msg.update(bad)
    engine.send(**msg)
    e = engine.next_event(timeout=8)
    assert e.get("event") == "error", e
    assert what in e["error"] or "export" in e["error"], e
    engine.send(cmd="hello")
    ready = engine.wait_for("ready", timeout=15)
    assert ready["protocol"] == 1          # 上面那条被拒的 export 没有插进来任何事件


def test_export_rejects_unknown_keys_as_a_whole(engine):
    engine.send(cmd="export", out_dir="/tmp", images=[FIXTURE], formt="png")
    e = engine.next_event(timeout=8)
    assert e.get("event") == "error" and "formt" in e["error"], e


def test_export_without_document_and_without_images_is_refused(engine):
    engine.send(cmd="export", out_dir="/tmp")
    e = engine.next_event(timeout=8)
    assert e.get("event") == "error" and "images" in e["error"], e


def _need_export_env():
    pytest.importorskip("torch")
    pytest.importorskip("PIL")
    if not os.path.isfile(FIXTURE):
        pytest.skip(f"缺 fixture：{FIXTURE}")


def test_export_writes_full_size_not_the_proxy(engine, tmp_path):
    """导出的是源图那一个像素，不是预览的代理档。

    这条是 M4 的产品主张本身：预览会话被刻意压到很小（max_px），而落盘的 PNG 尺寸
    必须等于 fixture 的原始尺寸。只看"文件生成了"是分不出代理与满幅的。
    """
    _need_export_env()
    from PIL import Image
    engine.send(cmd="load_image", path=FIXTURE, strength=0.4, max_px=207360)
    ready = engine.wait_for("image_ready", timeout=60)
    assert ready["w"] * ready["h"] <= 207360, ready        # 预览确实是代理档
    engine.send(cmd="export", out_dir=str(tmp_path), format="png", tile=256, quality=90)
    done, others = _collect_until(engine, "export_done")
    assert done["failed"] == 0 and done["total"] == 1, done
    assert [e["event"] for e in others].count("export_progress") == 1, others
    img = done["images"][0]
    assert img["out"] == str(tmp_path / "portrait-1024x1280.png"), img
    with Image.open(img["out"]) as im:
        assert im.size == (ready["src_w"], ready["src_h"]), \
            f"导出尺寸 {im.size} != 源图 {(ready['src_w'], ready['src_h'])}：那是代理档"
    assert img["bytes"] > 10_000 and img["tiles"] > 1, img
    assert img["margin_px"] >= 80, "默认磨皮参数的作用面至少 80 px，margin 比这小就是漏了层"


def test_export_honours_the_current_layers(engine, tmp_path):
    """挂上一键预设后导出，满幅文件里必须真的变了（这层不能只活在事件里）。"""
    _need_export_env()
    import numpy as np
    from PIL import Image
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0, max_px=207360)
    engine.wait_for("image_ready", timeout=60)
    engine.send(cmd="export", out_dir=str(tmp_path / "base"), format="png", tile=512)
    _collect_until(engine, "export_done")
    base = str(tmp_path / "base" / "portrait-1024x1280.png")
    engine.send(cmd="lut", action="set", preset="creamy", amount=1.0)
    engine.wait_for("lut_done", timeout=30)
    engine.send(cmd="export", out_dir=str(tmp_path / "look"), format="png", tile=512)
    _collect_until(engine, "export_done")
    a = np.asarray(Image.open(base).convert("RGB"), np.int16)
    b = np.asarray(Image.open(str(tmp_path / "look" / "portrait-1024x1280.png")).convert("RGB"),
                   np.int16)
    d = np.abs(a - b).max(axis=-1)
    assert int(d.max()) >= 2, "挂了一键预设导出后画面没动：那一层只活在事件里"
    assert float((d > 0).mean()) > 0.5, f"预设只改了 {float((d > 0).mean()):.2%} 像素"

    def sat(x):
        mx, mn = x.max(axis=-1), x.min(axis=-1)
        return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0.0)
    # 肤色方向：奶油是降饱和，满幅图上肤色带的平均饱和必须真的降下来
    skin = (sat(a) > 0.10) & (sat(a) < 0.55) & (a.max(axis=-1) > 90) & (a.min(axis=-1) > 40)
    assert float(sat(b.astype(np.float64))[skin].mean()) < float(sat(a.astype(np.float64))[skin].mean())


def test_export_carries_the_deform_field_and_the_skin_channel(engine, tmp_path):
    """挂着形变与肤色通道导出：那两条分支必须真跑得通，而且报的是导出尺寸的数。

    这一条是真窗口抓出来的，不是补写的漂亮话：`_export_snapshot` 里形变与通道那两段
    用了 np，而 server 的模块层不导 numpy（与本文件其余按需取用同一条写法），而当时
    所有导出用例都不挂这两层——于是 `NameError: name 'np' is not defined` 一路活到
    装机件，在 gpuspike/runwin_m4.sh 的形变臂当场塌在 render 阶段。
    """
    _need_export_env()
    import os
    import numpy as np
    from PIL import Image
    engine.send(cmd="load_image", path=FIXTURE, strength=0.5, max_px=207360)
    engine.wait_for("image_ready", timeout=60)
    engine.send(cmd="precompute", backend="template")
    engine.wait_for("precompute_ready", timeout=60)
    engine.send(cmd="deform", action="set",
                amounts={"slim_face": 0.6, "big_eye": 0.3, "small_chin": 0.4})
    lit = engine.wait_for("deform_done", timeout=60)
    assert lit["lit"] is True, lit
    engine.send(cmd="export", out_dir=str(tmp_path / "deform"), format="png", tile=512)
    got, _others = _collect_until(engine, "export_done")
    assert got["failed"] == 0, f"挂上形变就导出失败：{got['images']}"
    img = got["images"][0]
    assert img["deform_peak_px"] > 0, "三滑块开着而场是空的：那一层根本没进导出"
    assert img["margin_px"] >= 80 + int(img["deform_peak_px"]), \
        f"margin 没按 ceil(peak)+1 加：{img['margin_px']} / peak {img['deform_peak_px']}"
    assert not img["skipped"], f"当前文档不该 skip 任何图层：{img['skipped']}"

    # 再把磨皮指到肤色通道：掩膜那一段用的是另一条 np 分支，同样必须活
    engine.send(cmd="set_strength", strength=0.5, channel="skin")
    engine.wait_for("frame", timeout=30)
    engine.send(cmd="export", out_dir=str(tmp_path / "chan"), format="png", tile=512)
    got2, _o2 = _collect_until(engine, "export_done")
    assert got2["failed"] == 0, f"分通道导出失败：{got2['images']}"
    assert got2["images"][0]["channel"] == "skin", \
        f"通道没带到导出（报的是 {got2['images'][0]['channel']}）：掩膜那一段是空的"
    name = os.path.splitext(os.path.basename(FIXTURE))[0] + ".png"
    with Image.open(str(tmp_path / "deform" / name)) as a, Image.open(str(tmp_path / "chan" / name)) as b:
        d = np.abs(np.asarray(a.convert("RGB"), np.int16) - np.asarray(b.convert("RGB"), np.int16)).max(-1)
    assert int(d.max()) >= 2, "分通道与全图导出逐字节相同：那张掩膜没参与"


def test_export_batch_isolates_failures_and_reports_skips(engine, tmp_path):
    """批量：坏路径只塌自己那一张；不属于本文档的图层明确报 skipped。"""
    _need_export_env()
    import shutil
    engine.send(cmd="load_image", path=FIXTURE, strength=0.5, max_px=207360)
    engine.wait_for("image_ready", timeout=60)
    other = str(tmp_path / "copy.jpg")
    shutil.copyfile(FIXTURE, other)
    missing = str(tmp_path / "没有这个文件.jpg")
    engine.send(cmd="export", out_dir=str(tmp_path / "batch"), format="jpg",
                images=[FIXTURE, other, missing], tile=512)
    done, others = _collect_until(engine, "export_done")
    assert done["total"] == 3 and done["failed"] == 1, done
    assert [e["event"] for e in others].count("export_progress") == 3, others
    bad = [i for i in done["images"] if "error" in i]
    assert bad and bad[0]["path"] == missing and "FileNotFoundError" in bad[0]["error"], done
    ok = [i for i in done["images"] if "error" not in i]
    assert len(ok) == 2
    doc = next(i for i in ok if i["path"] == FIXTURE)
    extra = next(i for i in ok if i["path"] == other)
    # 第二张不是"当前文档"：笔迹/形变/通道都不许搬过去，而且必须报出来
    assert "repair" in extra["skipped"] and "light" in extra["skipped"], extra["skipped"]
    assert "repair" not in doc["skipped"], doc["skipped"]


def test_export_refused_while_benching(engine, tmp_path):
    """跑靶与导出互斥（与 set_strength 那几条同一条理由：同抢一块卡，账单就不是那个数）。"""
    engine.send(cmd="bench_start", w=96, h=64, frames=400, interval_ms=8, mode="copy")
    engine.wait_for("bench_started", timeout=30)   # shm_ready 在它前面；等错事件就把噪声当成了答案
    try:
        engine.send(cmd="export", out_dir=str(tmp_path), images=[FIXTURE])
        _expect_error(engine, "跑靶进行中，拒绝导出")
        assert not os.listdir(tmp_path), "被拒的导出还在目录里落了东西"
    finally:
        engine.send(cmd="bench_stop")
        engine.wait_for("bench_done", timeout=90)


def test_export_command_keys_are_a_whitelist(engine):
    """命令层的白名单要把 `cmd` 自己算进去（M3-b 为这条付过 12 项用例的钱）。"""
    assert "cmd" in EXPORT_KEYS and "action" in EXPORT_KEYS
    # M7 给导出开了三个新键；它们必须同时在名单里——不在就是“收了但丢了”，
    # 而“导出了但尺寸不对”在事件里一个字不报
    assert {"scale", "sharpen", "upscale_backend"} <= EXPORT_KEYS


# ============================================================ M7：放大接入出片
# 这一节只管**命令接线与诚实**：scale 能不能从 stdin 一路走到落盘尺寸、无权重后端
# 是不是整条拒。放大本身的保真（分块逐字节等价、三臂对拍）在 test_export_scale.py
# 与 test_upscale.py 钉，不在这里重做一遍。
def test_export_scale_makes_the_file_actually_bigger(engine, tmp_path):
    """2× 导出：落盘尺寸必须是源图的两倍，而事件里同时留着源幅与倍率。只报“成了”
    不报“多大”的导出无法归因。"""
    _need_export_env()
    from PIL import Image
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0, max_px=207360)
    ready = engine.wait_for("image_ready", timeout=60)
    engine.send(cmd="export", out_dir=str(tmp_path), format="png", tile=512,
                scale=2, sharpen=0.5)
    done, _ = _collect_until(engine, "export_done")
    assert done["failed"] == 0 and done["total"] == 1, done
    assert done["scale"] == 2 and done["upscale_backend"] == "lanczos3", done
    assert float(done["sharpen"]) == 0.5, done
    img = done["images"][0]
    with Image.open(img["out"]) as im:
        assert im.size == (ready["src_w"] * 2, ready["src_h"] * 2), \
            f"落盘尺寸 {im.size} 不是源图 {(ready['src_w'], ready['src_h'])} 的 2×"
    assert (img["src_w"], img["src_h"]) == (ready["src_w"], ready["src_h"]), img
    assert img["w"] == im.size[0] and img["h"] == im.size[1], "账单尺寸要等于落盘尺寸"
    assert img["upscale_ms"] >= 0.0 and img["sharpen_ms"] >= 0.0, img
    # 4× 不是“参数能递到”就算了：倍率真乘到像素数上才算接对了
    engine.send(cmd="export", out_dir=str(tmp_path / "x4"), format="png", tile=512, scale=4)
    done4, _ = _collect_until(engine, "export_done")
    with Image.open(done4["images"][0]["out"]) as im:
        assert im.size == (ready["src_w"] * 4, ready["src_h"] * 4), im.size


def test_export_realesrgan_backend_is_refused_honestly_and_engine_lives(engine, tmp_path):
    """无权重要 Neural 后端：整条拒 + 理由点名权重 + 不落任何文件 + 引擎还能动。

    最坏的答案是“默默用 Lanczos 写了一张图，事件里写 upscale_backend=realesrgan”——
    那等于把确定性重采样当成神经网络超分卖。这一条钉的就是它不会发生。
    """
    _need_export_env()
    from PIL import Image
    engine.send(cmd="load_image", path=FIXTURE, strength=0.0, max_px=207360)
    engine.wait_for("image_ready", timeout=60)
    out_dir = tmp_path / "nn"
    engine.send(cmd="export", out_dir=str(out_dir), format="png", scale=2,
                upscale_backend="realesrgan")
    # 不用 wait_for：它碰到 error 会直接报断，而这一条要的就是那句 error。
    # 也不能拿到的第一个事件就当答复：会话在背地里还在发 frame，那一口吃的不是
    # export 的话（上一版就报在 {'event':'frame'} 上）。
    e = _next_error_or(engine, timeout=20)
    assert e.get("event") == "error", e
    txt = str(e["error"])
    assert "realesrgan" in txt.lower() or "权重" in txt, txt
    assert "lanczos3" in txt, f"拒绝理由要告诉用户可用的那一个档：{txt}"
    assert not list(out_dir.glob("*.png")), "被拒的导出不得留下半截文件"
    # 拒完还能正常出片：一条拒绝不能把会话或 worker 抖死
    engine.send(cmd="export", out_dir=str(out_dir), format="png", tile=512, scale=2)
    done, _ = _collect_until(engine, "export_done")
    assert done["failed"] == 0 and done["total"] == 1, done
    with Image.open(done["images"][0]["out"]) as im:
        assert im.size[0] > 0


def test_export_scale_bad_values_are_refused_without_events(engine):
    """倍率与锐化的越界值在**开跑前**就拒，不产生一个 export_progress 事件。"""
    _need_export_env()
    for bad in ({"scale": 5}, {"scale": 0}, {"scale": "two"}, {"sharpen": -1},
                {"sharpen": float("nan")}, {"upscale_backend": "bicubic"}):
        engine.send(cmd="export", out_dir="/tmp", format="jpg",
                    images=[FIXTURE], **bad)
        e = _next_error_or(engine, timeout=8)
        assert e.get("event") == "error", (bad, e)
        # 探针：hello 一定发事件，而且与导出无关——不会被"上一条其实偷偷跑了"蒙过去
        engine.send(cmd="hello")
        ready = engine.wait_for("ready", timeout=15)
        assert ready["protocol"] == 1


def test_ready_advertises_upscale_capabilities(engine):
    """能力上报（M7）：倍率与后端名单由引擎说，前端不刻一份。"""
    engine.send(cmd="hello")
    hello = engine.wait_for("ready", timeout=30)
    assert hello["upscale_scales"] == [1, 2, 3, 4], hello.get("upscale_scales")
    b = hello["upscale_backends"]
    assert "lanczos3" in b["baseline"] and "realesrgan" in b["weights_gated"]
    assert "realesrgan" not in b["baseline"], "无权重机器上不许把神经网络超分列为装机即用能力"


# ============================================================ M5-a：底片条（文档会话）
# 这一节只管**接线与生命周期**：扫描名单、缩略图的通道上限、切文档时图层跟不跟回来。
# 缩略图解码本身的口径（长边、降质、最坏情况）在 test_session.py 的库层用例里。
STRIP_MAX_PX = 207360            # 产品档代理（400×504）：M1-1/M1-2 钉死的那一档


def _strip_dir(tmp_path):
    """底片条靶：两张**同尺寸**真图 + 一个外来文件 + 一个子目录。

    两张必须同尺寸：代理档一致，切换时 shm 不会被重建。尺寸一变引擎会 `unlink` +
    重开同名缓冲，测试里那个 mmap peer 就指着已删的 inode —— 读到的是旧数据而不是
    错数据，那种失败最容易被当成"通过"。
    """
    from PIL import Image
    d = tmp_path / "strip"
    d.mkdir()
    a = d / "a.jpg"
    shutil.copyfile(FIXTURE, a)
    src = np.asarray(Image.open(FIXTURE).convert("RGB"), np.int16)
    b = d / "b.jpg"
    Image.fromarray(np.clip(src + 24, 0, 255).astype(np.uint8)).save(b, quality=92)
    (d / "note.txt").write_text("不是图")
    (d / "sub").mkdir()
    return str(d), [str(a), str(b)]


def _open_doc(engine, path, **kw):
    """开一张图（与 _load 同一套事件顺序），返回 (shm 元数据, image_ready)。"""
    engine.send(cmd="load_image", path=path,
                **{"max_px": STRIP_MAX_PX, "strength": 0.0, **kw})
    meta = engine.wait_for("shm_ready", timeout=90)
    engine.wait_for("vram_ready", timeout=90)
    return meta, engine.wait_for("image_ready", timeout=90)


def _collect(ep, until, timeout=120.0):
    """收到 until 为止，把期间的事件按类型归堆。

    缩略图是一串事件而不是一条：wait_for 会把它们全丢掉，而"几张到了、几张塌了"
    正是这一节要验的东西。
    """
    got: dict[str, list] = {}
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise AssertionError(f"{timeout}s 内没等到 {until}；已收到 {sorted(got)}")
        e = ep.next_event(timeout=min(left, 10.0))
        k = e.get("event") or "?"
        if k == "error":
            raise AssertionError(f"引擎报错：{e['error']}")
        got.setdefault(k, []).append(e)
        if k == until:
            return got


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_ready_advertises_filmstrip_bounds(engine):
    """行程与上限由引擎说，前端不许刻一份。"""
    engine.send(cmd="hello")
    ready = engine.wait_for("ready")
    assert "scan" in ready["session_actions"] and "select" in ready["session_actions"]
    lo, hi = ready["thumb_edge"]
    assert lo <= ready["thumb_edge_default"] <= hi
    assert 0 < ready["thumb_max_bytes"] <= 1 << 20
    assert ready["session_max_docs"] >= 1
    # 报出去的名单里每一个动作都得真能用（报一个不认的就是假承诺）
    assert "state" in ready["session_actions"]
    engine.send(cmd="session", action="state")
    engine.wait_for("session_state", timeout=30)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_session_scan_lists_rows_and_thumbs_stay_inside_the_channel(engine, tmp_path):
    d, files = _strip_dir(tmp_path)
    engine.send(cmd="hello")
    ready = engine.wait_for("ready")
    engine.send(cmd="session", action="scan", dir=d, edge=64, quality=60)
    ev = engine.wait_for("session_scan", timeout=30)
    assert ev["found"] == 2 and ev["rows"] == 2, ev
    assert ev["current_index"] == -1, "扫描不许动会话（一张也没开过）"
    why = {s["name"]: s["why"] for s in ev["skipped"]}
    assert why.get("note.txt") and "扩展名" in why["note.txt"]
    assert why.get("sub") and "目录" in why["sub"]
    assert ev["truncated"] is False

    got = _collect(engine, "thumbs_done")
    done = got["thumbs_done"][0]
    assert done["count"] == 2 and done["failed"] == 0 and done["dropped"] == 0, done
    thumbs = got["thumb_ready"]
    assert len(thumbs) == 2, thumbs
    for t in thumbs:
        assert max(t["w"], t["h"]) <= 64, f"缩略图超出格子：{t['w']}x{t['h']}"
        assert t["bytes"] <= ready["thumb_max_bytes"], f"一行 JSON 被顶爆：{t['bytes']} B"
        raw = base64.b64decode(t["jpeg_b64"])
        assert raw[:2] == b"\xff\xd8" and raw[-2:] == b"\xff\xd9"
        assert t["src_w"] == 1024 and t["src_h"] == 1280, "源尺寸报的是假的"
    # 事件里不许有满幅像素：一张 1024×1280 的 RGBA 是 5.2 MB，base64 后 7 MB 一行
    assert done["channel_kb"] < 400, f"缩略图把通道灌了 {done['channel_kb']} KB"
    # thumbs_done 之后引擎补发一份状态：拿 _collect 里最后那份会比到"解图之前"的快照
    st = engine.wait_for("session_state", timeout=30)
    assert st["count"] == 2 and all(x["thumb"] for x in st["docs"]), st
    assert [x["name"] for x in st["docs"]] == ["a.jpg", "b.jpg"]
    assert all(x["opened"] is False for x in st["docs"]), "没开过的格子不许说已开过"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_switching_documents_returns_the_exact_same_frame(engine, tmp_path):
    """这一节的主判据：切走再切回来，画面必须**逐字节**等于离开时那一帧。

    不看事件字段而看 shm 里的像素：layers 报 1 笔而画面没有那一笔、strength 报 0.62
    而实际按 0.5 出帧，两种错在事件里都自洽（本仓最贵那一族坑的形状）。
    """
    _needs_torch()
    d, (fa, fb) = _strip_dir(tmp_path)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    engine.send(cmd="session", action="scan", dir=d, thumbs=False)
    engine.wait_for("session_scan", timeout=30)

    shm, first = _open_doc(engine, fa)
    assert first["session_index"] == 0 and first["switched"] is False, first
    h, w = shm["h"], shm["w"]
    peer = FrameShm(shm["name"])
    try:
        _read_frame(engine, peer, h, w)

        # 四层一起挂上：逐点（lut/grade）与按坐标（笔迹）走的是两条不同的回挂路径
        engine.send(cmd="set_strength", value=0.62)
        engine.wait_for("params_set", timeout=30)
        _read_frame(engine, peer, h, w)
        engine.send(cmd="lut", action="set", preset="creamy", amount=0.8)
        engine.wait_for("lut_done", timeout=60)
        _read_frame(engine, peer, h, w)
        engine.send(cmd="grade", action="set", dh=0.01, ds=-0.3, dv=0.05)
        engine.wait_for("grade_done", timeout=60)
        _read_frame(engine, peer, h, w)
        engine.send(cmd="inpaint", action="add",
                    rle=_brush_rle(h, w, h // 3, w // 2, 6), feather=2)
        engine.wait_for("inpaint_done", timeout=180)
        edited = _read_frame(engine, peer, h, w)

        # 离开前把"这一格有哪几层"抄一份下来：回来时必须一模一样，一个字段都不许多。
        # 取 session_state 而不是 image_ready：后者那份快照停在开图那一刻，中间调的
        # 每一档都不在里面——拿它当基线，比的是"开图状态"而不是"离开时状态"。
        engine.send(cmd="session", action="state")
        sess_before = engine.wait_for("session_state", timeout=30)
        ds_before = sess_before["doc_state"]
        edits_before = sess_before["docs"][0]["edits"]
        assert edits_before["repair"] == 1 and edits_before["lut"] is True, edits_before
        assert edits_before["grade"] is True, edits_before
        # 手动改过定向之后预设就是 None（cmd_grade 的既定语义），这里把它钉住：
        # 断言"lut_preset 还是 creamy"会是拿一个从没存在过的语义当回归基线
        assert edits_before["lut_preset"] is None, edits_before

        # 切到 b：a 的四层必须全部消失，而不是"看起来干净了"
        engine.send(cmd="session", action="select", index=1)
        b = engine.wait_for("image_ready", timeout=90)
        assert b["session_index"] == 1 and b["switched"] is False, b
        assert abs(float(b["strength"]) - 0.5) < 1e-6, f"b 拿到了 a 的强度：{b['strength']}"
        assert b["layers"] == {"repair": 0, "light": 0, "deform": False, "lut": False,
                               "lut_preset": None, "grade": False, "channel": None}, b["layers"]
        assert b["bytes_lut"] == 0 and b["grade_state"]["lit"] is False, b
        frame_b = _read_frame(engine, peer, h, w)
        assert np.abs(frame_b - edited).mean() > 4.0, "a 与 b 是同一张画面，这个对拍没有鉴别力"

        # 切回 a：四层全部回来，而且画面与离开时逐字节相等
        engine.send(cmd="session", action="select", index=0)
        back = engine.wait_for("image_ready", timeout=90)
        assert back["switched"] is True and back["session_index"] == 0, back
        assert abs(float(back["strength"]) - 0.62) < 1e-6, back["strength"]
        assert back["layers"] == edits_before, (
            f"切回来少了一层：走时 {edits_before}，回来 {back['layers']}")
        # 数字也得跟着回来，不只是"有没有这一层"：宿主按 doc_state 重摆滑块，
        # 层在而数不对，UI 就会显示一个与画面无关的位置（双向错配的新一格）
        ds = back["doc_state"]
        assert abs(ds["strength"] - 0.62) < 1e-6, ds["strength"]
        assert ds["counts"]["repair"] == 1 and ds["counts"]["light"] == 0, ds["counts"]
        assert ds["lut"]["lit"] is True and abs(ds["lut"]["amount"] - 0.8) < 1e-6, ds["lut"]
        assert abs(ds["grade"]["ds"] + 0.3) < 1e-6 and ds["grade"]["lit"] is True, ds["grade"]
        assert ds == ds_before, f"切走时与回来时的文档状态不是一个数：\n 走 {ds_before}\n 回 {ds}"
        assert ds["params"]["radius"] >= 1 and ds["light"]["radius"] >= 0, ds
        assert set(ds["deform"]["amounts"]) == {"slim_face", "big_eye", "small_chin"}, ds["deform"]
        assert all(abs(v) < 1e-9 for v in ds["deform"]["amounts"].values()), \
            "这张图没动过形变滑块，回来却带着值：那是把上一张的场搬过来了"
        assert back["bytes_lut"] > 0 and back["grade_state"]["lit"] is True, back
        frame_back = _read_frame(engine, peer, h, w)
        assert np.array_equal(frame_back, edited), (
            f"切回来不是那一张：max {int(np.abs(frame_back - edited).max())} LSB / "
            f"{(np.abs(frame_back - edited).max(axis=-1) > 0).mean():.4%} 像素对不上")
        # 底片条那一格的徽章也得同步（当前格用 live 状态，不许报旧快照）
        st = engine.wait_for("session_state", timeout=30)
        assert st["index"] == 0 and st["docs"][0]["edits"]["repair"] == 1, st["docs"][0]
        assert st["docs"][1]["edits"] == {"repair": 0, "light": 0, "deform": False,
                                          "lut": False, "lut_preset": None, "grade": False,
                                          "channel": None}, st["docs"][1]["edits"]

        # 重复点当前那一格不开新会话（白付一次解码，还会把没存快照的 live 状态重装）
        engine.send(cmd="session", action="select", index=0)
        noop = engine.wait_for("session_state", timeout=30)
        assert noop.get("noop") is True, noop
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_a_different_proxy_budget_voids_coordinate_layers(engine, tmp_path):
    """代理档一变：按像素坐标成立的层作废并明说，逐点层原样留着。

    不作废就是拿一张小代理档上的笔迹去贴大一号的会话 —— 库层按名字把通道递出来，
    撞尺寸要等到 render 才发生，而那时报表上已经写着"有 skin 通道"。
    """
    _needs_torch()
    d, (fa, _fb) = _strip_dir(tmp_path)
    engine.send(cmd="hello")
    ready = engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    small, _e0 = _open_doc(engine, fa, max_px=64 * 64)
    engine.wait_for("frame", timeout=60)
    preset = ready["presets"][0]["name"]
    engine.send(cmd="lut", action="set", preset=preset, amount=1.0)
    engine.wait_for("lut_done", timeout=60)
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="inpaint", action="add",
                rle=[[small["h"] // 2, small["w"] // 2, 3, 255]], feather=0)
    engine.wait_for("inpaint_done", timeout=180)
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="session", action="state")
    assert engine.wait_for("session_state", timeout=30)["docs"][0]["edits"]["repair"] == 1

    # 第二次开同一张、但换一档代理：不能再走 _open_doc——它会把 image_ready 吃掉，
    # 下面那个"直到 image_ready 为止"的收集循环就会抱着后面的帧事件空等超时
    engine.send(cmd="load_image", path=fa, max_px=STRIP_MAX_PX)
    warn = None
    while True:
        e = engine.next_event(timeout=90)
        if e["event"] == "engine_warn" and "按像素坐标成立的层" in e["warn"]:
            warn = e
        if e["event"] == "image_ready":
            break
    assert warn is not None, "换了代理档却没说坐标层作废：静默丢工"
    assert "逐点层" in warn["warn"], warn
    assert e["layers"]["repair"] == 0, e["layers"]
    assert e["layers"]["lut"] is True and e["layers"]["lut_preset"] == preset, e["layers"]


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_document_switch_is_refused_while_benching(engine, tmp_path):
    """切文档与跑靶互斥：它走的就是 load_image 那条守卫，不另写一份。"""
    _needs_torch()
    d, (fa, _fb) = _strip_dir(tmp_path)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    _open_doc(engine, fa)
    engine.send(cmd="session", action="scan", dir=d, thumbs=False)
    engine.wait_for("session_scan", timeout=30)
    assert engine.wait_for("session_state", timeout=30)["index"] == 0
    engine.send(cmd="bench_start", w=96, h=64, frames=400, interval_ms=8, mode="copy")
    engine.wait_for("bench_started", timeout=30)
    try:
        engine.send(cmd="session", action="select", index=1)
        _expect_error(engine, "跑靶进行中，拒绝换图")
    finally:
        engine.send(cmd="bench_stop")
        engine.wait_for("bench_done", timeout=90)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_session_command_boundaries(engine, tmp_path):
    """参数越界与未知动作整条拒绝，而且不许留下半截底片条。"""
    d, files = _strip_dir(tmp_path)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="session", action="state", nope=1)
    _expect_error(engine, "不认识的参数")
    engine.send(cmd="session", action="翻一下底片条")
    _expect_error(engine, "未知 session action")
    engine.send(cmd="session", action="scan", dir=str(tmp_path / "没有这个目录"))
    _expect_error(engine, "不是目录或不存在")
    engine.send(cmd="session", action="scan", dir=files[0])
    _expect_error(engine, "不是目录或不存在")
    engine.send(cmd="session", action="scan", dir=d, limit=0)
    _expect_error(engine, "越界")
    engine.send(cmd="session", action="scan", dir=d, limit=S.MAX_DOCS + 1)
    _expect_error(engine, "越界")
    engine.send(cmd="session", action="select", index=99)
    _expect_error(engine, "不在底片条里")
    engine.send(cmd="session", action="select")
    _expect_error(engine, "需要 index")
    engine.send(cmd="session", action="add", paths=[])
    _expect_error(engine, "非空路径列表")
    engine.send(cmd="session", action="add", paths=[files[0], {"不是字符串": 1}])
    _expect_error(engine, "非空字符串列表")

    # 到这里前面全部被拒：底片条应当还是空的
    engine.send(cmd="session", action="state")
    st = engine.wait_for("session_state", timeout=30)
    assert st["count"] == 0, f"被拒的命令留下了半截底片条：{st['docs']}"

    engine.send(cmd="session", action="scan", dir=d, thumbs=False)
    engine.wait_for("session_scan", timeout=30)
    engine.send(cmd="session", action="add", paths=files)
    add = engine.wait_for("session_add", timeout=30)
    assert add["requested"] == 2 and add["added"] == 0 and add["duplicated"] == 2, add
    engine.send(cmd="session", action="add", paths=[str(tmp_path / "不存在.jpg")])
    _expect_error(engine, "不是现有文件")
    engine.send(cmd="session", action="state")
    st2 = engine.wait_for("session_state", timeout=30)
    assert st2["count"] == 2, f"被拒的 add 还是往底片条里塞了一格：{st2['docs']}"
    engine.send(cmd="session", action="thumbs", edge=8)
    _expect_error(engine, "缩略图参数非法")
    engine.send(cmd="session", action="stop_thumbs")
    engine.wait_for("session_state", timeout=30)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_rescan_keeps_rows_edits_and_skips_finished_thumbs(engine, tmp_path):
    """重扫不许丢工：格子的状态与已解好的缩略图都在，会话也不动。"""
    _needs_torch()
    d, (fa, _fb) = _strip_dir(tmp_path)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set")
    engine.send(cmd="session", action="scan", dir=d, edge=64)
    engine.wait_for("session_scan", timeout=30)
    _collect(engine, "thumbs_done")

    engine.send(cmd="session", action="select", index=0)
    engine.wait_for("image_ready", timeout=90)
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="set_strength", value=0.77)
    engine.wait_for("params_set", timeout=30)
    engine.wait_for("frame", timeout=30)

    engine.send(cmd="session", action="scan", dir=d)     # 用户又点了一次"刷新"
    again = engine.wait_for("session_scan", timeout=30)
    assert again["rows"] == 2 and again["current_index"] == 0, again
    st = engine.wait_for("session_state", timeout=30)
    assert st["index"] == 0 and st["current"] == os.path.abspath(fa), st
    done = _collect(engine, "thumbs_done")["thumbs_done"][0]
    assert done["count"] == 0, f"重扫把已解好的缩略图又解了一遍：{done}"
    assert done["dropped"] == 0 and done["failed"] == 0, done

    engine.send(cmd="session", action="select", index=1)
    engine.wait_for("image_ready", timeout=90)
    engine.wait_for("frame", timeout=60)
    engine.send(cmd="session", action="select", index=0)
    back = engine.wait_for("image_ready", timeout=90)
    assert abs(float(back["strength"]) - 0.77) < 1e-6, f"重扫一次，强度就没了：{back['strength']}"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_a_thumb_failure_only_kills_its_own_cell(engine, tmp_path):
    """一张解不开只塌自己那一格：整批不许停，其余格子照常出图。"""
    d, (fa, _fb) = _strip_dir(tmp_path)
    broken = os.path.join(d, "c.jpg")
    with open(broken, "wb") as f:
        f.write(b"%PDF-1.4 not-a-bitmap" * 64)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="session", action="scan", dir=d, edge=64)
    engine.wait_for("session_scan", timeout=30)
    got = _collect(engine, "thumbs_done")
    done = got["thumbs_done"][0]
    assert done["count"] == 2 and done["failed"] == 1, done
    bad = got["thumb_failed"][0]
    assert bad["path"] == os.path.abspath(broken) and "解不开" in bad["error"], bad
    st = engine.wait_for("session_state", timeout=30)
    row = next(x for x in st["docs"] if x["path"] == os.path.abspath(broken))
    assert row["thumb"] is None and "解不开" in row["thumb_error"], row
    assert all(x["thumb"] for x in st["docs"] if x["path"] != os.path.abspath(broken))


# ============================================================ M5-b：全局撤销/重做
# 这一节只管**画面与生命周期**：撤销回去的那一帧是不是逐字节同一张、一步的粒度对不对、
# 历史跟着不跟着文档走。占不占一步、快照装了什么这些纯口径判断在 test_history.py。

def _hist(engine, action="state", timeout=60):
    engine.send(cmd="history", action=action)
    return engine.wait_for("history_state", timeout=timeout)


def _drain_frames(engine, peer, h, w, quiet=0.5):
    """把已排队的 frame 事件收干净，返回 (最后一帧的像素, 那条 seq)。

    不能沿用 _read_frame：几条命令排了四帧在队列里，_read_frame 拿的是最早那条事件的
    slot 号，而双缓冲只有两块——那个号现在装着最新那一帧。撤回到"出厂那一帧"这种判据
    要是拿错了帧，比的是同一块内存里的同一张图，永远相等。
    """
    last = None
    while True:
        try:
            e = engine.next_event(timeout=quiet)
        except TimeoutError:
            break
        if e.get("event") == "frame":
            last = e
        elif e.get("event") == "error":
            raise AssertionError(f"引擎报错：{e.get('error')}")
    if last is None:
        # 队列安静了还不是一定没有帧：等 history_state / *_done 时，路上那条 frame 已被
        # wait_for 丢掉。引擎只留最后一帧在 shm 里，那个 slot 号说的就是当前画面。
        last = engine.last_frame
    assert last is not None, "一条帧事件都没有，画面证据是空的"
    engine.last_frame = None            # 取走就不留：下一次判据必须来自新的一帧
    px = np.frombuffer(peer.read_pixels(last["slot"]), np.uint8).reshape(h, w, 4)[:, :, :3]
    return px.astype(np.int16), int(last["seq"])


def test_history_contract_is_announced_at_ready(engine):
    """撤销的行程、步数上限与手势合并窗口都由引擎说，前端不许刻一份。"""
    engine.send(cmd="hello")
    r = engine.wait_for("ready")
    assert set(r["history_actions"]) == {"undo", "redo", "state", "clear"}
    assert 8 <= r["history_max"] <= 1024, r["history_max"]
    assert r["history_group_ms"] > 0
    for c in ("set_strength", "inpaint", "light", "deform", "lut", "grade"):
        assert c in r["history_edit_cmds"], f"{c} 不进历史：那一层的编辑撤不回来"
    # 这两条不是编辑：把它们算进去，换一张图就会凭空多一步
    assert "load_image" not in r["history_edit_cmds"]
    assert "precompute" not in r["history_edit_cmds"]


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_history_argument_boundaries(engine):
    """未知动作、多余参数、没有会话、空栈：四条都要整条拒绝或如实报 noop。"""
    _needs_torch()
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="history", action="nonsense")
    _expect_error(engine, "未知 history action")
    engine.send(cmd="history", action="state", extra=1)
    _expect_error(engine, "history 收到不认识的参数")
    engine.send(cmd="history", action="undo")
    _expect_error(engine, "尚未 load_image")
    # 空栈的 undo 不是错误：快捷键按多了是常态，报 noop 让按钮跟着灰下去
    _load(engine, max_px=STRIP_MAX_PX, strength=0.0)
    st = _hist(engine, "undo")
    assert st.get("noop") is True and st["undo_steps"] == 0 and st["can_redo"] is False


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_undo_returns_the_exact_frame_and_redo_replays_it(engine):
    """产品的主判据：撤销回去的那一帧必须与来时逐字节同一张，重做再原样回来。

    只看事件不作数：doc_state 报对了而画面没重放那一笔，是同时可能成立的。
    """
    _needs_torch()
    meta = _load(engine, max_px=STRIP_MAX_PX, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base, seq0 = _drain_frames(engine, peer, h, w)
        assert _hist(engine)["undo_steps"] == 0, "刚导完就该有历史？"
        engine.send(cmd="set_strength", value=0.9)
        engine.wait_for("params_set", timeout=30)
        strong, _ = _drain_frames(engine, peer, h, w)
        assert int(np.abs(strong - base).max()) > 0, "强度根本没上屏，后面那次相等不作数"
        st = _hist(engine, "undo")
        assert st["undo_steps"] == 0 and st["redo_steps"] == 1 and st["can_redo"]
        assert st["doc_state"]["strength"] == 0.0, st["doc_state"]
        assert st["history_ms"] >= 0.0
        back, seq1 = _drain_frames(engine, peer, h, w)
        assert np.array_equal(back, base), "撤销回去的帧与来时不是逐字节同一张"
        assert seq1 > seq0, "撤销没出帧"
        rd = _hist(engine, "redo")
        assert rd["doc_state"]["strength"] == 0.9 and rd["can_undo"]
        again, _ = _drain_frames(engine, peer, h, w)
        assert np.array_equal(again, strong), "重做回去的帧与撤销前不是逐字节同一张"
        _hist(engine, "undo")
        e = _hist(engine, "undo")           # 退无可退
        assert e.get("noop") is True and not e["can_undo"]
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_dragging_one_slider_is_one_undo_step(engine):
    """一步 = 一次手势：同一个滑块连发五条只占一步，换滑块或跨过合并窗口才算新的一步。"""
    _needs_torch()
    engine.send(cmd="hello")
    ready = engine.wait_for("ready")
    _load(engine, max_px=STRIP_MAX_PX, strength=0.0)
    for v in (0.1, 0.25, 0.4, 0.62, 0.8):
        engine.send(cmd="set_strength", value=v)
        engine.wait_for("params_set", timeout=30)
    assert _hist(engine)["undo_steps"] == 1, "一次拖拽被记成了多步：撤销要按五次"
    engine.send(cmd="set_strength", mid_gain=0.4)     # 另一个滑块（参数名不同）
    engine.wait_for("params_set", timeout=30)
    assert _hist(engine)["undo_steps"] == 2
    time.sleep(ready["history_group_ms"] / 1000.0 + 0.15)
    engine.send(cmd="set_strength", value=0.3)        # 跨过合并窗口，同组也要新起一步
    engine.wait_for("params_set", timeout=30)
    assert _hist(engine)["undo_steps"] == 3
    st = _hist(engine, "undo")
    assert st["doc_state"]["strength"] == pytest.approx(0.8)
    assert st["doc_state"]["params"]["mid_gain"] == pytest.approx(0.4)
    st = _hist(engine, "undo")
    assert st["doc_state"]["params"]["mid_gain"] == 0.0, "退掉修容带增益那一步没生效"
    st = _hist(engine, "undo")
    assert st["undo_steps"] == 0 and st["doc_state"]["strength"] == 0.0


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_rejected_edit_takes_no_history_step(engine):
    """整条被拒的命令不许占一步，也不许偷偷改掉任何一个字段。"""
    _needs_torch()
    _load(engine, max_px=STRIP_MAX_PX, strength=0.0)
    assert _hist(engine)["undo_steps"] == 0
    engine.send(cmd="set_strength", value=0.7, radius=999999)
    _expect_error(engine, "radius")
    st = _hist(engine)
    assert st["undo_steps"] == 0, "被拒绝的命令占了一步"
    assert st["doc_state"]["strength"] == 0.0, "拒绝的那条把 strength 偷偷改走了"
    engine.send(cmd="inpaint", action="nonsense")
    _expect_error(engine, "未知 inpaint action")
    assert _hist(engine)["undo_steps"] == 0


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_undo_walks_back_through_every_layer(engine, tmp_path):
    """五层各动一次 → 撤到底必须回到出厂状态与出厂那一帧；重做到顶再原样回来。

    这条是「跨层统一历史栈」的存在理由：各层自己有 undo 是不够的，用户按的是
    Ctrl+Z，不是「撤销上一次磨皮」。
    """
    _needs_torch()
    meta = _load(engine, max_px=STRIP_MAX_PX, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    try:
        base, _ = _drain_frames(engine, peer, h, w)
        engine.send(cmd="set_strength", value=0.6)
        engine.wait_for("params_set", timeout=30)
        engine.send(cmd="inpaint", action="add", rle=_brush_rle(h, w, h // 2, w // 2, 6),
                    feather=2)
        engine.wait_for("inpaint_done", timeout=120)
        engine.send(cmd="light", action="add", rle=_brush_rle(h, w, h // 3, w // 3, 6),
                    feather=2, sign=1, radius=6)
        engine.wait_for("light_done", timeout=120)
        engine.send(cmd="grade", action="set", dh=0.02, ds=0.10, dv=-0.05, amount=1.0)
        engine.wait_for("grade_done", timeout=60)
        engine.send(cmd="lut", action="set", path=_write_cube(tmp_path, 8, 0.9))
        engine.wait_for("lut_done", timeout=60)
        top, seq_top = _drain_frames(engine, peer, h, w)
        assert not np.array_equal(top, base), "五层全挂上画面却一模一样：这个对拍没有鉴别力"
        st = _hist(engine)
        assert st["undo_steps"] == 5, f"五层各一步，实际={st['undo_steps']}"
        ds = st["doc_state"]
        assert ds["counts"]["repair"] == 1 and ds["counts"]["light"] == 1
        assert ds["lut"]["lit"] is True and ds["grade"]["lit"] is True
        for _ in range(5):
            _hist(engine, "undo")
        done = _hist(engine)
        d0 = done["doc_state"]
        assert done["undo_steps"] == 0 and done["redo_steps"] == 5
        assert d0["strength"] == 0.0 and d0["counts"] == {"repair": 0, "light": 0,
                                                         "repair_redo": 0, "light_redo": 0}
        assert d0["lut"]["lit"] is False and d0["grade"]["lit"] is False
        back, _ = _drain_frames(engine, peer, h, w)
        assert np.array_equal(back, base), "撤到底的画面与出厂那一帧不是逐字节同一张"
        for _ in range(5):
            _hist(engine, "redo")
        again, seq_end = _drain_frames(engine, peer, h, w)
        assert np.array_equal(again, top), "重做到顶的画面与撤销前不是逐字节同一张"
        assert seq_end > seq_top
    finally:
        peer.close()


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_history_travels_with_the_document(engine, tmp_path):
    """每个文档一条历史：切走再回来，栈深与画面都还是它自己那份。"""
    _needs_torch()
    d, (fa, _fb) = _strip_dir(tmp_path)
    engine.send(cmd="hello")
    engine.wait_for("ready")
    engine.send(cmd="set_device", device="cpu")
    engine.wait_for("device_set", timeout=60)
    # 先 scan 再切：两张同尺寸，第二张不会再发 shm_ready（`_open_doc` 是"第一次开"
    # 那一族语义的助手，切文档要走 session select）
    engine.send(cmd="session", action="scan", dir=d, thumbs=False)
    engine.wait_for("session_scan", timeout=30)
    # 当前那一格的 index 直接从 image_ready 拿（它是引擎自己报的 session_index）。
    # 别去等 session_state：上一条 _hist 已经把 scan 发的那条从队列里吃掉了，
    # wait_for 就是这么不讲理——它会丢掉路上所有非目标事件
    _meta, ir_home = _open_doc(engine, fa)
    home = ir_home["session_index"]
    engine.send(cmd="set_strength", value=0.7)
    engine.wait_for("params_set", timeout=30)
    engine.send(cmd="set_strength", value=0.35)      # 同一次手势：仍然一步
    engine.wait_for("params_set", timeout=30)
    assert _hist(engine)["undo_steps"] == 1
    engine.send(cmd="session", action="select", index=1 - home)
    engine.wait_for("image_ready", timeout=60)
    assert _hist(engine)["undo_steps"] == 0, "切到新文档还挂着上一张的撤销栈"
    engine.send(cmd="set_strength", value=0.9)
    engine.wait_for("params_set", timeout=30)
    assert _hist(engine)["undo_steps"] == 1
    engine.send(cmd="session", action="select", index=home)
    ir = engine.wait_for("image_ready", timeout=60)
    assert ir["switched"] is True
    st = _hist(engine)
    assert st["undo_steps"] == 1, "回来之后历史不是那张的：撤销会退到别的故事上"
    assert st["doc_state"]["strength"] == pytest.approx(0.35)
    undone = _hist(engine, "undo")
    assert undone["doc_state"]["strength"] == 0.0
    # 另一张的历史没被这一下动过
    engine.send(cmd="session", action="select", index=1 - home)
    engine.wait_for("image_ready", timeout=60)
    assert _hist(engine)["undo_steps"] == 1
    assert _hist(engine)["doc_state"]["strength"] == pytest.approx(0.9)


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_budget_change_clears_history_and_says_so(engine):
    """代理档一变，快照里的像素坐标就不成立了：历史必须跟着清，而且要说出来。"""
    _needs_torch()
    meta = _load(engine, max_px=STRIP_MAX_PX, strength=0.0)
    h, w = meta["h"], meta["w"]
    engine.send(cmd="inpaint", action="add", rle=_brush_rle(h, w, h // 2, w // 2, 6),
                feather=2)
    engine.wait_for("inpaint_done", timeout=120)
    assert _hist(engine)["undo_steps"] == 1
    # 把同一张图按更大一档代理预算重开：坐标层作废，历史也就没有意义了
    engine.send(cmd="load_image", path=FIXTURE, max_px=576000, strength=0.0)
    got = _collect(engine, "image_ready", timeout=120)
    warns = [e for e in got.get("engine_warn", []) if "历史" in e["warn"]]
    assert warns, "清了历史没说：用户按撤销会以为那一笔还在，而画面已经不带它了"
    assert _hist(engine)["undo_steps"] == 0


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_history_refused_while_benching(engine):
    """撤销与跑靶互斥：跑靶线程在写 frame_gpu，这里也写同一块（同 set_strength 那条理由）。"""
    _needs_torch()
    meta = _load(engine, max_px=STRIP_MAX_PX, strength=0.0)
    engine.send(cmd="set_strength", value=0.6)
    engine.wait_for("params_set", timeout=30)
    engine.send(cmd="bench_start", w=meta["w"], h=meta["h"], frames=400,
                interval_ms=8, mode="copy")
    engine.wait_for("bench_started", timeout=30)
    try:
        engine.send(cmd="history", action="undo")
        _expect_error(engine, "跑靶进行中，拒绝 history undo")
    finally:
        engine.send(cmd="bench_stop")
        engine.wait_for("bench_done", timeout=90)
    # 跑靶停了就恢复正常
    assert _hist(engine, "undo")["undo_steps"] == 0


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_history_clear_is_not_a_step_and_refuses_empty_actions(engine):
    """clear 是运维口径（新照片/新会话），它自己不该被撤销回来。"""
    _needs_torch()
    _load(engine, max_px=STRIP_MAX_PX, strength=0.0)
    engine.send(cmd="set_strength", value=0.4)
    engine.wait_for("params_set", timeout=30)
    assert _hist(engine)["undo_steps"] == 1
    st = _hist(engine, "clear")
    assert st["undo_steps"] == 0 and st["redo_steps"] == 0 and st["can_undo"] is False
    again = _hist(engine, "undo")
    assert again.get("noop") is True
    assert again["doc_state"]["strength"] == pytest.approx(0.4), "clear 不该改画面状态"


# ------------------------------------------------------------------ M6 抠图/换底
@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_background_swap_changes_frame_and_is_undoable(engine):
    """M6-b 换底端到端：色键换底真改画面、可撤销逐字节回退、重做逐字节回来、clear 复原。

    证的是「常驻换底层接进了渲染热路径，并且被统一历史栈当成了一步」——算子层的保真
    在 test_matting 已钉，这里要的是通路级证据：帧真变了、撤销真能整层退回出厂帧。
    """
    _needs_torch()
    meta = _load(engine, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _read_frame(engine, peer, h, w)          # load 出厂帧（strength=0）

    engine.send(cmd="background", action="set", backend="color_key",
                bg=[255, 0, 0], tol=0.22, softness=0.06)
    done = engine.wait_for("bg_done", timeout=30)
    assert done["action"] == "set" and done["bg_active"] is True
    assert done["bytes_bg"] > 0, "换底层没占任何常驻——遮罩没建起来"
    assert done["device"].split(":")[0] == "cpu"
    swapped = _read_frame(engine, peer, h, w)
    changed = int((np.abs(swapped - base).sum(axis=2) > 0).sum())
    assert changed > 0, "换底画面一点没变（遮罩全 1 或热路径没接上）"
    red = (swapped[:, :, 0] > 200) & (swapped[:, :, 1] < 45) & (swapped[:, :, 2] < 45)
    assert int(red.sum()) > 0, "背景区没被换成红底"

    # 撤销：整层退回出厂帧，逐字节
    engine.send(cmd="history", action="undo")
    engine.wait_for("history_state", timeout=30)
    back = _read_frame(engine, peer, h, w)
    assert np.array_equal(back, base), "撤销换底没逐字节回到出厂帧"
    # 重做：逐字节回到换底那帧
    engine.send(cmd="history", action="redo")
    engine.wait_for("history_state", timeout=30)
    redone = _read_frame(engine, peer, h, w)
    assert np.array_equal(redone, swapped), "重做没逐字节回到换底帧"
    # clear 复原
    engine.send(cmd="background", action="clear")
    engine.wait_for("bg_done", timeout=30)
    off = _read_frame(engine, peer, h, w)
    assert np.array_equal(off, base), "clear 后没回到出厂帧"


@pytest.mark.skipif(not os.path.isfile(FIXTURE), reason="缺测试人像，先跑 packaging/make-test-portrait.py")
def test_background_birefnet_rejected_without_weights(engine):
    """birefnet 后端无权重必须诚实拒绝：报 error、不静默退成色键、引擎照常活着。

    这是 #11/决策 9 那条「能力不许说谎」在换底上的翻版：宁可拒绝也不拿色键冒充神经网络抠图。
    """
    _needs_torch()
    meta = _load(engine, strength=0.0)
    h, w = meta["h"], meta["w"]
    peer = FrameShm(meta["name"])
    base = _read_frame(engine, peer, h, w)

    engine.send(cmd="background", action="set", backend="birefnet", bg=[0, 255, 0])
    err = engine.wait_for("error", timeout=30)
    assert "birefnet" in err["error"].lower() or "权重" in err["error"], err["error"]
    # 引擎没死：随后一次色键换底应正常出帧
    engine.send(cmd="background", action="set", backend="color_key", bg=[0, 0, 255],
                tol=0.22, softness=0.06)
    engine.wait_for("bg_done", timeout=30)
    got = _read_frame(engine, peer, h, w)
    assert int((np.abs(got - base).sum(axis=2) > 0).sum()) > 0, "拒绝 birefnet 后引擎应仍能色键换底"
