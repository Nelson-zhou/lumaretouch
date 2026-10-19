"""真实性能分位数（DoD §4：逐项跑通 P0/P1 之外还要"记录真实性能分位数"）。

为什么单独一个模块而不塞进功能用例：功能用例的判据是"对不对"，加不加时间断言都
不影响它过不过；把耗时写进功能用例只会诱导出为了绿而放宽的阈值。这里**只测量与
记录，不设失败阈值**（除两条：拖拽帧必须真的复用缓存、每张导出都必须有一条进度，
那是功能事实不是性能偏好），产物是一份 JSON，由 tools/run-acceptance.py 汇总成验收报告。

口径上有一条不能含糊：**量的必须是产品形状**。以前跑靶沿用测试夹具的 400×504 代理
（STRIP_MAX_PX，为了把协议用例跑得快），那不是用户看到的画面尺寸。这里默认不传
`max_px`，让引擎落到 `decode.PROXY_PIXELS`（960×600 预算，UI 出厂值同一个数）——
报告里同时把代理宽高与源图宽高写死在 `env` 段，读数离开那个形状就不成立。

跑法（必须在运行时 venv，没 torch 就没有产品形状）。这一条要**整段照抄**，少一个
变量就少一臂，而报告里不会报错——它只会在 notes 里写一句"本轮没量"：

    packaging/make-test-dng.py --from engine/tests/fixtures/portrait-1024x1280.jpg \
        --out /tmp/lrt-perf-dng.dng --edge 3000      # 合成 RAW 夹具（只需一次）
    LRT_PERF_OUT=/tmp/perf.json LRT_PERF_DNG=/tmp/lrt-perf-dng.dng \
        PYTHONPATH=engine/src <运行时python> -m pytest engine/tests/test_perf_report.py -q

`LRT_PERF_DNG` 那一个是 RAW/「秒开 DNG」那两档（首导 + 同档再导一次）的唯一开关。
2026-10-18 实测踩过：归档 1.2.0 那一份第一次就是用上面少了这个变量的命令跑的，产物
比旧的一档小了一半，逐键一对才发现 `import_dng` / `import_dng_second` 整块没了——
一个只在**报告变短**里露形的缺失，靠肉眼看汇总行是看不出来的。

不设 LRT_PERF_OUT 就整模块 skip：不然每次全量跑都白付几十秒，而没人收那份数。
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import time

import pytest

from test_protocol import (FIXTURE, EngineProcess, _need_export_env, _needs_torch,
                           _next_event)

OUT = os.environ.get("LRT_PERF_OUT")
SAMPLES = int(os.environ.get("LRT_PERF_SAMPLES", "120"))
# 0 = 不传 max_px，用引擎的产品档代理（见模块 docstring 那条口径）
MAX_PX = int(os.environ.get("LRT_PERF_MAX_PX", "0"))
PER_MS_KEYS = ("decode_ms", "shm_ms", "attach_ms", "first_frame_ms",
               "first_frame_filter_ms", "first_frame_bands_ms", "import_ms",
               "preview_ms", "open_ms", "orient_ms", "scale_ms", "total_ms")

pytestmark = pytest.mark.skipif(not OUT, reason="没设 LRT_PERF_OUT：这一轮不收性能数")


def pct(values: list[float], q: float) -> float:
    """线性插值分位数（不用 numpy 的 percentile 只是为了让这个模块在没有 torch 的
    机器上也能被 import——真正的数总是在有 torch 的那一遍里量）。"""
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    i = (len(s) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def bill(values: list[float]) -> dict:
    return {"n": len(values), "p50": round(pct(values, 0.50), 3),
            "p95": round(pct(values, 0.95), 3), "p99": round(pct(values, 0.99), 3),
            "max": round(max(values), 3) if values else None,
            "mean": round(statistics.fmean(values), 3) if values else None}


def bill_ms(entries: list[dict]) -> dict:
    """逐张成本 = 该条目里所有 `*_ms` 读数之和。

    不写死字段名是有意的：导出每张的账单会随分支变化（16-bit 那一路有 decode_ms 与
    readback，普通那一路有 tile/write/geometry）。点名取键的写法一旦上游加了字段就
    悄悄少算一笔，而"少算"在报表上长得和"更快了"一模一样。
    """
    return bill([round(sum(v for k, v in x.items()
                           if k.endswith("_ms") and isinstance(v, (int, float))), 3)
                 for x in entries])


@pytest.fixture(scope="module")
def engine_perf():
    """整模块共用一个引擎进程，但**不预先 hello**：

    第一条臂要从一次干净的手势开始（hello → set_device 含预热 → 首张导入），否则
    上一条臂把缓存、常驻会话、设备都弄热了之后，“首次”两个字就没意义了。
    """
    ep = EngineProcess(f"perf-{os.getpid()}")
    yield ep
    ep.close()


@pytest.fixture(scope="module")
def report():
    """整模块共用一份账：四条臂各测各的，最后一次性落盘。

    落盘放在 fixture 的 end 而不是每条用例里：中途一条红也不该把已经量到的数丢掉
    （"只在最慢的那台机器上响的失败"要能看见它慢在哪）。
    """
    data: dict = {"schema": "lrt.acceptance-perf.v1", "at": time.strftime("%FT%T"),
                  "samples": SAMPLES, "proxy_max_px": MAX_PX or "product(PROXY_PIXELS)",
                  "env": {}, "metrics": {}, "notes": []}
    yield data
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError as e:
        data["notes"].append(f"写 {OUT} 失败：{e}")


def _boot(ep: EngineProcess, report: dict) -> dict:
    """hello + set_device auto，并把环境形状记进报告（设备名必须来自引擎自报）。

    GPU 上下文与内核的预热是在 set_device 里付的（`engine_warm` 那一笔），
    所以下面读到的是“热好上下文之后的首图”。把预热那 265 ms 算进“每张图都要付”
    就是拿机器形状猜结论：两条各记各的，不混成一个总数。
    """
    ep.send(cmd="hello")
    ready = ep.wait_for("ready", timeout=90)
    ep.send(cmd="set_device", device="auto")
    dev = ep.wait_for("device_set", timeout=180)
    warm = None
    t_end = time.monotonic() + 30.0
    while time.monotonic() < t_end:
        try:
            e = ep.next_event(timeout=2.0)
        except TimeoutError:
            break                       # 静默两秒：没有预热（CPU 或已热过），不空等
        if e.get("event") == "engine_warm":
            warm = e.get("warm_ms")
            break
        if e.get("event") == "error":
            raise AssertionError(f"引擎拒绝：{e.get('error')}")
    if not report["env"]:
        rt = ready.get("runtime") or {}
        report["env"] = {"engine_version": ready.get("version"),
                         "protocol": ready.get("protocol"),
                         "device": dev.get("device"), "cuda": dev.get("cuda"),
                         "warm_ms": warm, "runtime": rt}
    return dev


def _load(ep: EngineProcess, **kw) -> dict:
    """按产品档加载一张图，返回 image_ready。

    这里**不等 shm_ready**：引擎只在真正新建/换档那块共享缓冲时发那一条（同尺寸
    早退不发，宿主 Rust 侧就这条约定写了注释），而“重选回同一张”恰好就是同尺寸。
    拿它当每条导入的必要事件，量到的不是性能而是“契约里有没有这一条”（本轮就这么
    误判过一次“引擎卡住”）。image_ready 排在帧通路都完成之后，它才是“可以编辑”那个时刻。
    """
    payload = {"cmd": "load_image", "path": FIXTURE, "strength": 0.0}
    if MAX_PX:
        payload["max_px"] = MAX_PX
    payload.update(kw)
    ep.send(**payload)
    return ep.wait_for("image_ready", timeout=240)


def _fixture_or_skip() -> None:
    _needs_torch()
    if not os.path.isfile(FIXTURE):
        pytest.skip("缺测试人像：先跑 packaging/make-test-portrait.py")


def _want(ep: EngineProcess, want: str, *, timeout: float = 120.0) -> dict:
    """等到某一条特定事件（默认那层 skip 只跳例行播报，不够用）。

    引擎每条命令都会顺带发帧与状态，靠“取下一条”去读目标事件会读到隔壁的账单；
    而 error 必须立刻响——它在事件流里排在前面，继续等只会等成一句 TimeoutError，
    把「被拒」写成了「没反应」。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        e = _next_event(ep, skip=("session_state", "engine_warn"),
                        timeout=min(10.0, max(0.1, deadline - time.monotonic())))
        if e["event"] == want:
            return e
        if e["event"] == "error":
            raise AssertionError(f"引擎拒绝：{e.get('error')}")
    raise TimeoutError(f"{timeout}s 内没等到 {want}")


def test_import_cost_breakdown(engine_perf, report):
    """首次导入的一次性成本分解：解码 / shm / 首次 attach（含 CUDA lazy init）/ 首帧。

    CORE-002「秒开」与 RAW 那条主张看的是这份数，不是拖拽的稳态数。
    """
    _fixture_or_skip()
    _boot(engine_perf, report)
    r = _load(engine_perf, strength=0.0)
    report["metrics"]["shape"] = {"proxy": [r["w"], r["h"]], "source": [r["src_w"], r["src_h"]],
                                  "format": r.get("format"), "draft": r.get("draft_used")}
    report["metrics"]["import_jpg"] = {k: r.get(k) for k in PER_MS_KEYS if k in r}
    report["metrics"]["import_jpg"]["sum_of_stages_ms"] = round(
        (r.get("total_ms") or 0) + (r.get("shm_ms") or 0) + (r.get("attach_ms") or 0)
        + (r.get("first_frame_ms") or 0), 2)
    report["env"]["device"] = r.get("device")     # image_ready 报的是真正落下的设备
    dng = os.environ.get("LRT_PERF_DNG")
    if dng and os.path.isfile(dng):
        r2 = _load(engine_perf, path=dng)
        report["metrics"]["import_dng"] = {k: r2.get(k) for k in PER_MS_KEYS if k in r2}
        report["metrics"]["import_dng"]["raw"] = r2.get("raw")
        report["metrics"]["import_dng"]["shape"] = {"proxy": [r2["w"], r2["h"]],
                                                    "source": [r2["src_w"], r2["src_h"]]}
        # 稳态成本：同档再导一次（上下文已热），“每张都要付的那一笔”看这个数
        r3 = _load(engine_perf, path=dng)
        report["metrics"]["import_dng_second"] = {k: r3.get(k) for k in PER_MS_KEYS if k in r3}
        report["notes"].append(
            f"RAW 那一臂是合成 DNG（夹具上采样后写 CFA，源幅 {r2['src_w']}×{r2['src_h']}）："
            "尺寸/位深/排阵的形状对，传感器噪声结构不对——这一组数能比“解码与"
            "下采样随像素的标度”，不能当作真机色彩质量结论。")
    else:
        report["notes"].append("没给 LRT_PERF_DNG：RAW 那一档的导入成本本轮没量（不猜）")


def test_filmstrip_thumbnail_percentiles(engine_perf, report):
    """底片条缩略图的逐张成本（DoD §3「RAW/图片秒开缩略图」的唯一数源）。"""
    _fixture_or_skip()
    n = int(os.environ.get("LRT_PERF_THUMBS", "24"))
    d = os.environ.get("LRT_PERF_TMP", "/tmp/lrt-perf-export")
    strip = os.path.join(d, f"strip-{n}")
    os.makedirs(strip, exist_ok=True)
    for i in range(n):
        dst = os.path.join(strip, f"frame-{i:03d}.jpg")
        if not os.path.isfile(dst):
            shutil.copyfile(FIXTURE, dst)
    engine_perf.send(cmd="session", action="scan", dir=strip, edge=160, quality=72)
    deadline = time.monotonic() + 240
    per, done = [], None
    while time.monotonic() < deadline and done is None:
        e = _next_event(engine_perf, skip=("session_state", "engine_warn"), timeout=30)
        if e["event"] == "thumb_ready":
            per.append(float(e.get("total_ms") or 0.0))
        elif e["event"] == "thumbs_done":
            done = e
        elif e["event"] == "error":
            pytest.fail(f"缩略图扫描被拒：{e['error']}")
    assert done is not None, "等不到 thumbs_done：底片条会在真窗口里一直转圈"
    report["metrics"]["thumbnail_ms"] = bill(per)
    report["metrics"]["thumbnail_batch"] = {"count": done.get("count"),
                                           "failed": done.get("failed"),
                                           "dropped": done.get("dropped"),
                                           "edge": done.get("edge"),
                                           "wall_ms": done.get("total_ms"),
                                           "channel_kb": done.get("channel_kb")}
    # 逐张账加起来必须对得上批次墙钟：对不上说明有一段时间谁都不认账（线程池排队、
    # 或事件里漏了一个阶段），那种"秒开"是报表造出来的
    assert (done.get("count") or 0) == len(per), \
        f"批次报 {done.get('count')} 张，事件里只捡到 {len(per)} 张的账"


def test_drag_frame_stream_percentiles(engine_perf, report):
    """拖拽期的逐帧渲染成本（产品档代理、强度来回拖）。RENDER-001/002/003 的同一批数。"""
    _fixture_or_skip()
    _load(engine_perf, strength=0.3)
    ms: list = []
    cached_true = 0
    for i in range(SAMPLES):
        v = 0.2 + 0.6 * ((i % 20) / 19.0)
        engine_perf.send(cmd="set_strength", value=v)
        e = _next_event(engine_perf, skip=("session_state", "vram_ready", "engine_warn",
                                           "image_ready", "frame"), timeout=60)
        assert e["event"] == "params_set", e
        ms.append(float(e["render_ms"]))
        cached_true += 1 if e["filter_cached"] else 0
    report["metrics"]["drag_render_ms"] = bill(ms)
    # 拖拽期零重滤波是 M1-3c/M2-a 的产品主张（功能事实，不是性能偏好）：
    # 缓存被无声绕过时 render_ms 照样是个"看着正常"的数，只有 filter_cached 能揭穿
    report["metrics"]["drag_filter_cached_ratio"] = round(cached_true / len(ms), 4)
    assert cached_true == len(ms), (
        f"拖拽 {len(ms)} 帧里有 {len(ms) - cached_true} 帧重跑了滤波："
        "拖滑块应当在已常驻的结果上只改系数")


def test_face_reshaping_percentiles(engine_perf, report):
    """面部重塑（GPU 网格场）：PORTRAIT-001/002 那条"毫秒级"的数从哪来。

    分两笔记：`deform_apply_ms` 是每帧真的跑了一次 grid_sample 的成本，
    `deform_build_ms` 是首次建层（关键点变了才重建）。把两笔混成一个数，就会把
    "拖动时其实不重建"这句话证伪不了。
    """
    _fixture_or_skip()
    _load(engine_perf, strength=0.3)
    engine_perf.send(cmd="precompute", backend="mediapipe")
    try:
        pc = engine_perf.wait_for("precompute_ready", timeout=180)
    except (AssertionError, TimeoutError):
        pytest.skip("这台机器没有可用的 mediapipe 后端：面部重塑的分位数在这个形状下量不出来")
    report["metrics"]["landmark_backend"] = pc.get("backend")
    report["metrics"]["num_landmarks"] = pc.get("num_landmarks")
    report["metrics"]["precompute_ms"] = {k: pc.get(k) for k in
                                          ("build_ms", "infer_ms", "total_ms") if k in pc}
    # 第一笔含建层，单独记；后面全是"改系数重采样"
    engine_perf.send(cmd="deform", action="set", amounts={"slim_face": 0.5})
    try:
        e = _want(engine_perf, "deform_done", timeout=120)
    except (AssertionError, TimeoutError) as err:
        pytest.skip(f"deform 在这台机器上跑不通（{err}）：没有关键点就没有重塑，不猜数")
    report["metrics"]["deform_build_ms"] = e.get("total_ms")
    builds_after = int(e.get("deform_builds") or 0)
    ms: list = []
    for i in range(min(SAMPLES, 60)):
        a = 0.1 + 0.5 * ((i % 10) / 9.0)
        engine_perf.send(cmd="deform", action="set",
                         amounts={"slim_face": a, "big_eye": a, "small_chin": -a})
        e = _want(engine_perf, "deform_done", timeout=120)
        ms.append(float(e.get("deform_ms") or 0.0))
    report["metrics"]["deform_apply_ms"] = bill(ms)
    # 来回拖不许反复建层：每次 deform 都重建 = 每帧付一次特征分解，"毫秒级"当场不成立
    report["metrics"]["deform_builds_during_drag"] = int(e.get("deform_builds") or 0) - builds_after


def test_eye_teeth_enhance_percentiles(engine_perf, report):
    """眼牙局部增强（LNX-PORTRAIT-009）：这一层的"毫秒级"要单独有一笔账。

    与面部重塑那臂同一个分法：`enhance_build_ms` 是首次从关键点重画掩膜的一次性代价，
    `enhance_apply_ms` 是拖动期间每帧的逐点乘加。为什么不拿真窗口那一格的 enhance_ms
    当这份证据：`apply_enhance` 里那句 `torch.cuda.synchronize()` 等到的是**这块卡上
    排到此处为止的全部工作**（同进程里帧通路还在跑靶），装机壳那一臂量到 50 ms 就是这个
    形状——它不是这一层的成本，把它当成本就是假指标。这里量的是"只有这一层在动"的那一份。
    """
    _fixture_or_skip()
    _load(engine_perf, strength=0.3)
    engine_perf.send(cmd="precompute", backend="mediapipe")
    try:
        pc = engine_perf.wait_for("precompute_ready", timeout=180)
    except (AssertionError, TimeoutError):
        pytest.skip("这台机器没有可用的 mediapipe 后端：眼牙这一层的掩膜从关键点重画，"
                    "没有关键点就量不出这个形状")
    # 第一笔含建层（几何场 + 内容门），单独记；后面全是"改系数逐点乘加"
    engine_perf.send(cmd="enhance", action="set", sclera=0.6, iris=0.5, teeth=0.7)
    try:
        e = _want(engine_perf, "enhance_done", timeout=120)
    except (AssertionError, TimeoutError) as err:
        pytest.skip(f"enhance 在这台机器上跑不通（{err}）：没有可信关键点就没有这一层，不猜数")
    report["metrics"]["enhance_build_ms"] = e.get("enhance_build_ms")
    report["metrics"]["enhance_gated_px"] = e.get("enhance_gated_px")
    report["metrics"]["enhance_window"] = e.get("enhance_window")
    report["metrics"]["bytes_enhance"] = e.get("bytes_enhance")
    ms: list = []
    rebuilt = 0
    for i in range(min(SAMPLES, 60)):
        a = 0.1 + 0.6 * ((i % 10) / 9.0)
        engine_perf.send(cmd="enhance", action="set",
                         sclera=a, iris=a * 0.8, teeth=a * 0.6)
        e = _want(engine_perf, "enhance_done", timeout=120)
        ms.append(float(e.get("enhance_ms") or 0.0))
        rebuilt += 1 if e.get("layer_recomputed") else 0
    report["metrics"]["enhance_apply_ms"] = bill(ms)
    # 拖动期间不许反复重画掩膜：每事件重画就是每事件付一次几何栅格化 + 内容门 + 一次
    # D2H（实测 12 ms/次），"毫秒级"当场不成立。这一格与形变那臂的
    # deform_builds_during_drag 同一个身份：功能事实（系数与几何各算一次钱），不是偏好。
    report["metrics"]["enhance_rebuilds_during_drag"] = rebuilt
    assert rebuilt == 0, f"拖动 {len(ms)} 次里重画了 {rebuilt} 次掩膜：这一层没在复用场"


def test_export_batch_percentiles(engine_perf, report):
    """批量出片的逐张成本（EXPORT-002/003 的"队列稳定"要看的是每张都有数）。"""
    _fixture_or_skip()
    _need_export_env()
    tmp = os.path.join(os.environ.get("LRT_PERF_TMP", "/tmp/lrt-perf-export"), "batch")
    os.makedirs(tmp, exist_ok=True)
    paths = []
    for i in range(6):
        d = os.path.join(tmp, f"perf-{i}.jpg")
        shutil.copyfile(FIXTURE, d)
        paths.append(d)
    _load(engine_perf, strength=0.3)
    out = os.path.join(tmp, "out")
    engine_perf.send(cmd="export", out_dir=out, format="jpg", quality=92,
                     tile=512, images=paths)
    done, got = None, []
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        try:
            e = engine_perf.next_event(timeout=10.0)
        except TimeoutError:
            continue
        if e.get("event") == "export_progress":
            got.append(e)
        if e.get("event") == "export_done":
            done = e
            break
        if e.get("event") == "error":
            pytest.fail(f"批量导出被拒：{e['error']}")
    assert done and done["total"] == 6, done
    ok_entries = [x for x in done["images"] if "error" not in x]
    report["metrics"]["export_per_image_ms"] = bill_ms(ok_entries)
    report["metrics"]["export_progress_events"] = len(got)
    report["metrics"]["export_total_ms"] = done.get("total_ms")
    report["metrics"]["export_tile"] = done.get("tile")
    report["metrics"]["export_failed"] = done.get("failed")
    # 每张都要有一条进度：16-bit 那条分支以前 continue 得太早，进度条"动都不动"
    assert len(got) == 6, f"六张图只发了 {len(got)} 条 export_progress"
    assert done.get("failed") == 0, f"批量里有失败条目：{done['images']}"
