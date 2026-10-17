#!/usr/bin/env python3
"""M5-a 离线跑靶：底片条——缩略图批量不挤坏帧通路、切换把上一张的画面原样拿回来。

主张有三句，每一句都得被量到：

  1) **缩略图是后台活，不能把预览拖下来。** 这是这一节唯一的"新性能风险"：解码走
     CPU，而引擎的 stdin 循环、跑靶线程、渲染都住在同一个进程同一个 GIL 下面。
     判据写成两臂交错对拍（quiet / busy），不是"跑一次看看还行"——邻居噪声与真实
     退化在单一采样里长得一模一样（M1-1 就因为单一采样下错过一次结论）。
  2) **切走再切回来，画面必须逐字节等于离开时那一帧。** 光看事件不作数：
     `switched=true`、`layers.repair=1` 与"画面其实没重放那一笔"完全可以同时成立。
     这里直接读 /dev/shm 里的像素比。
  3) **通道不能被缩略图灌爆。** 单张 ≤ THUMB_MAX_BYTES，整批的 base64 总量按张摊
     开算给用户看——宿主那边每一张都要进一个 HashMap。

臂之间交替跑（口径沿用 m1-drag / m2-face / m3-color / m4-export）。

跑法（要一个带 ROCm/CUDA torch 的解释器；CI 的两个 GPU job 已接）：
  REPS=5 LRT_DEVICE=cuda python3 packaging/m5-filmstrip-bench.py
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

from lumaretouch_engine.decode import load_rgb                 # noqa: E402
from lumaretouch_engine.session import (EDGE, THUMB_MAX_BYTES,  # noqa: E402
                                        make_thumb, scan_dir)
from lumaretouch_engine.shm import FrameShm, shm_name          # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
DEV = os.environ.get("LRT_DEVICE", "cuda")
REPS = int(os.environ.get("REPS", "5"))
N_STRIP = int(os.environ.get("LRT_STRIP_N", "60"))
BENCH_FRAMES = int(os.environ.get("LRT_STRIP_FRAMES", "300"))
PROXY_PX = 207360                  # 产品档代理（400×504）：与 M4 真窗口同一档

# ---- 判据（数字全部来自本机 RX 7600 XT 的实测，见计划文档 M5 节；换口径必须同时改这里）
# 实测口径（RX 7600 XT + ROCm，60 张一批、长边 160、产品档 400×504）：
#   busy 窗口 fps 59.87~60.00 / quiet 59.87~59.88（差 ±0.1）——缩略图批量在同一个
#   进程同一个 GIL 下解码，节流（THUMB_BATCH=4 / THUMB_SLEEP_MS=2）够用，所以下限
#   直接取预览的标称节奏 59，而不是"掉一点也算过"。
#   吞吐按批的大小分两档：40 张 44~46 张/秒；60 张（尺寸 0.6×~3.7× 混档）28.5~29.3
#   张/秒。下限 18 留的是对最慢那一档的 1.6× 余量，覆盖弱 CPU——真掉到 18 以下，
#   60 张的底片条要等 3 秒以上，那就不是"后台慢慢补"而是能被用户看见了。
#   切文档 import_ms 中位 16.2 / 最坏 21.5（含解码+渲染+写 shm）：上限 220 是同一条
#   余量逻辑，且它必须显著小于 load_image 首开的导入时间，否则"切图"就退化成了重开。
FPS_MIN = float(os.environ.get("LRT_STRIP_FPS_MIN", "59"))       # 两臂都要过
FPS_SPAN = float(os.environ.get("LRT_STRIP_FPS_SPAN", "1.2"))    # busy 相对 quiet 最多掉这么多
DROP_MAX = float(os.environ.get("LRT_STRIP_DROP_MAX", "1.5"))    # 丢帧百分比，两臂同判
THUMB_RATE_MIN = float(os.environ.get("LRT_STRIP_RATE_MIN", "18"))   # 张/秒（后台批量吞吐下限）
SWITCH_MS_MAX = float(os.environ.get("LRT_STRIP_SWITCH_MS", "220"))  # 一次切文档的 import_ms 上限


class Engine:
    """一个真引擎子进程：跑靶线程与缩略图线程都在它里面，这才是要测的那个争用面。"""

    def __init__(self, session: str):
        env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "..", "engine", "src"))
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "lumaretouch_engine.server", "--session", session],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env)
        self.q: queue.Queue = queue.Queue()
        self.parked: list = []
        self.err: list[str] = []
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()

    def _pump_out(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line:
                try:
                    self.q.put(json.loads(line))
                except json.JSONDecodeError:
                    self.q.put({"event": "_raw", "text": line})

    def _pump_err(self):
        for line in self.proc.stderr:
            if line.strip():
                self.err.append(line.rstrip())

    def send(self, **cmd):
        self.proc.stdin.write(json.dumps(cmd) + "\n")
        self.proc.stdin.flush()

    def wait(self, event: str, timeout: float = 60.0, pred=None) -> dict:
        """等一条事件；**期间看到的其他事件一律寄存**，不丢。

        不寄存就会出这种事：缩略图比跑靶先跑完，thumbs_done 正好落在 wait("bench_started")
        的通道里被丢掉，然后调用方拿着 180 s 的超时等一条永远不会再发第二次的事件。
        """
        for i, e in enumerate(self.parked):
            if e.get("event") == event and (pred is None or pred(e)):
                return self.parked.pop(i)
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise RuntimeError(f"没等到 {event}；stderr 尾部={self.err[-4:]}；"
                                   f"寄存了 {sorted({e.get('event') for e in self.parked})}")
            try:
                e = self.q.get(timeout=min(left, 10.0))
            except queue.Empty:
                continue
            if e.get("event") not in (event,) and e.get("event") != "bench_progress":
                self.parked.append(e)
                if event == "bench_progress" or pred is not None:
                    continue
            if e.get("event") == "error":
                raise RuntimeError(f"引擎报错：{e.get('error')}")
            if e.get("event") == event and (pred is None or pred(e)):
                return e

    def rss_mib(self) -> float:
        """引擎进程的 RSS（MiB）：缩略图那笔 base64 是活在宿主里的，这里只量引擎自己。"""
        with open(f"/proc/{self.proc.pid}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
        return -1.0

    def close(self):
        try:
            self.send(cmd="shutdown")
            self.proc.wait(timeout=8)
        except Exception:
            self.proc.kill()
            self.proc.wait(timeout=5)
        try:
            os.unlink(f"/dev/shm/{shm_name(self.proc.args[-1])}")
        except FileNotFoundError:
            pass


def build_strip(tmp: str, n: int) -> list[str]:
    """n 张真图（把 fixture 缩放到不同尺寸再存 JPEG）。

    尺寸必须各不相同：同一档尺寸的批量会把解码成本量成一个常数，而真实的底片条
    里每张图的 DCT 缩放档位都不一样。
    """
    from PIL import Image
    base = Image.open(FIXTURE).convert("RGB")
    paths = []
    for i in range(n):
        k = 0.6 + 0.12 * i                      # 0.6×…3.7×：600k px 到 5 MP 一带
        w, h = int(base.width * k), int(base.height * k)
        p = os.path.join(tmp, f"p{i:03d}.jpg")
        base.resize((w, h), Image.LANCZOS).save(p, quality=90)
        paths.append(p)
    return paths


def window_stats(marks: list, t_a: float, t_b: float, period_ns: int) -> tuple:
    """marks 里取 [t_a, t_b] 这段的 (fps, 跟不上节奏的%)。

    marks 用的是**引擎自己**的 (t_emit_ns, seq)：每一帧写进 shm 时打的那个
    CLOCK_MONOTONIC 纳秒。拿宿主收事件的墙钟来算会把 IPC 抖动一起量进去，而这里
    要问的恰好是"引擎自己这一拍有没有跟上"。

    为什么不能只看整场跑靶的平均：缩略图批量只压在开头那几秒，一场 5 s 的跑靶会把
    这段摊平——总平均"还是 59"而开头那段其实一直在掉帧。两臂都取同一个窗口：busy 臂
    的窗口正是缩略图在跑的那段，quiet 臂同位置的窗口是它的对照（同一路径、同一阶段，
    只差后台那批解码）。
    """
    inside = [m for m in marks if t_a <= m[0] <= t_b]
    if len(inside) < 2:
        return -1.0, -1.0
    t0, s0 = inside[0]
    t1, s1 = inside[-1]
    dt = t1 - t0
    if dt <= 0:
        return -1.0, -1.0
    fps = (s1 - s0) / (dt / 1e9)
    expect = dt / period_ns
    return fps, max(0.0, (1.0 - (s1 - s0) / expect)) * 100.0


def run_bench(engine: Engine, *, frames: int, interval: float,
              win_s: float) -> dict:
    """跑一段 image_stream，边跑边采 bench_progress 的时间戳（窗口 fps 的唯一来源）。"""
    engine.send(cmd="bench_start", w=400, h=504, frames=frames,
                interval_ms=interval, mode="image_stream")
    engine.wait("bench_started", timeout=60)
    marks: list = []
    others: list = []
    done: dict | None = None
    while done is None:
        try:
            e = engine.q.get(timeout=180)
        except queue.Empty:
            raise RuntimeError("跑靶 180 s 没发过 bench_done")
        if e.get("event") == "frame":
            marks.append((int(e["t_emit_ns"]), int(e["seq"])))
        elif e.get("event") == "bench_done":
            done = e
        elif e.get("event") == "error":
            raise RuntimeError(f"引擎报错：{e.get('error')}")
        elif e.get("event") != "bench_progress":
            # 缩略图那几条与跑靶同时在进行：顺手收起来，别让调用方再等一条已被吃掉的事件
            others.append(e)
    if done.get("failed"):
        raise RuntimeError(f"跑靶没跑成：{done}")
    period_ns = int(interval * 1e6)
    t_start, t_end = marks[0][0], marks[-1][0]
    fps, drop = window_stats(marks, t_start, t_end, period_ns)
    wfps, wdrop = window_stats(marks, t_start, t_start + int(win_s * 1e9), period_ns)
    return {"fps": round(fps, 2), "drop": round(drop, 2),
            "win_fps": round(wfps, 2), "win_drop": round(wdrop, 2),
            "frames": int(done.get("frames", 0)),
            "seg": {k: done[k] for k in ("filter", "kernel", "shm", "notify", "readback")
                    if k in done},
            "samples": len(marks), "device": done.get("pipe_device"), "others": others}


def one_arm(engine: Engine, strip_dir: str, *, busy: bool, win_s: float) -> dict:
    """一臂：可选地先把缩略图批量开起来，然后跑一段 image_stream，取总 fps 与窗口 fps。

    忙碌臂扫的是**这一轮自己的目录**（dirs 的由来）：缩略图按 path 记账，同一批文件
    重扫第二次会全部命中已有缩略图——count=0、total_ms=0，于是"每秒四万张"这种数
    就是从那个除零里长出来的。被测的后台活必须是没干过的活。
    """
    thumbs = None
    if busy:
        engine.send(cmd="session", action="scan", dir=strip_dir, edge=EDGE, thumbs=True)
        sc = engine.wait("session_scan", timeout=30)
        if not sc["found"]:
            raise RuntimeError(f"{strip_dir} 里一张都没扫到：忙碌臂测了个空")
    else:
        # 静止臂在开跑前先把后台掐了：这不是顺手一发，而是保证窗口里绝不会有
        # 上一轮残留的解码线程还在吃 CPU——那样的"quiet"臂就失去对照身份了
        engine.send(cmd="session", action="stop_thumbs")
    r = run_bench(engine, frames=BENCH_FRAMES, interval=16.7, win_s=win_s)
    if busy:
        dd = next((e for e in r["others"] if e.get("event") == "thumbs_done"), None)
        if dd is None:
            dd = engine.wait("thumbs_done", timeout=180)
        if dd.get("stopped"):
            raise RuntimeError("缩略图批量被中途停掉了，这一轮的吞吐与窗口都不作数")
        thumbs = {"count": dd["count"], "failed": dd["failed"], "dropped": dd["dropped"],
                  "total_ms": dd["total_ms"], "channel_kb": dd["channel_kb"],
                  "found": sc["found"]}
        # 判 count 而不是判 "count>0"：解了一半也报得出一个好看的张/秒
        if thumbs["count"] != thumbs["found"]:
            raise RuntimeError(f"这一轮解了 {thumbs['count']} 张，但扫到 {thumbs['found']} 张："
                               f"dropped={thumbs['dropped']}，分母对不上就不该拿来算吞吐")
        if thumbs["failed"]:
            raise RuntimeError(f"{thumbs['failed']} 张缩略图解失败")
    r["thumbs"] = thumbs
    return r


def part_fps(failures: list[str]) -> None:
    print("\n=== 1) 缩略图批量不挤坏帧通路（quiet / busy 两臂交错） ===")
    root = tempfile.mkdtemp(prefix="m5-strip-")
    # 每轮一个干净目录：见 one_arm 的说明。图在计时之外先建好，免得把 LANCZOS 的
    # 耗时算进任何一侧的窗口里
    dirs = []
    for i in range(REPS):
        d = os.path.join(root, f"r{i}")
        os.makedirs(d)
        dirs.append(d)
        build_strip(d, N_STRIP)
    eng = Engine(f"m5fps-{os.getpid()}")
    try:
        eng.send(cmd="hello")
        eng.wait("ready")
        eng.send(cmd="set_device", device=DEV)
        ds = eng.wait("device_set", timeout=60)
        if DEV.startswith("cuda") and not ds.get("cuda"):
            print("  跳过：要求 cuda 而这台机器没有 GPU，安静臂与忙碌臂都无从谈起")
            return
        eng.send(cmd="load_image", path=os.path.join(dirs[0], "p000.jpg"),
                 max_px=PROXY_PX, strength=0.5)
        eng.wait("image_ready", timeout=90)
        # 窗口取"整批缩略图从头解到尾的那段"，两臂用同一个长度
        win = max(1.0, min(6.0, N_STRIP * 0.045))
        quiet: list = []
        busy: list = []
        qwin: list = []
        bwin: list = []
        rates: list = []
        rss_before = eng.rss_mib()
        q = b = None
        for i in range(REPS):
            # 交替顺序：奇数轮先 busy，避免"永远是 quiet 先跑（机器更冷）"这种单边偏袒
            if i % 2:
                b = one_arm(eng, dirs[i], busy=True, win_s=win)
                q = one_arm(eng, dirs[i], busy=False, win_s=win)
            else:
                q = one_arm(eng, dirs[i], busy=False, win_s=win)
                b = one_arm(eng, dirs[i], busy=True, win_s=win)
            quiet.append(q["fps"]); busy.append(b["fps"])
            qwin.append(q["win_fps"]); bwin.append(b["win_fps"])
            rate = b["thumbs"]["count"] * 1000.0 / b["thumbs"]["total_ms"]
            rates.append(rate)
            print(f"  第 {i + 1} 轮  quiet 总 {q['fps']:5.2f} / 前 {win:.1f}s {q['win_fps']:5.2f} fps"
                  f"（丢 {q['drop']:4.1f}%）   busy 总 {b['fps']:5.2f} / 同窗口 {b['win_fps']:5.2f} fps"
                  f"（丢 {b['drop']:4.1f}%）  缩略图 {b['thumbs']['count']}/{N_STRIP} 张 / "
                  f"{b['thumbs']['total_ms']:6.0f} ms = {rate:4.1f} 张/秒 / "
                  f"{b['thumbs']['channel_kb']:5.1f} KB")
            if b["win_drop"] > DROP_MAX or b["drop"] > DROP_MAX:
                failures.append(f"busy 臂丢帧 {b['drop']:.1f}% 超上限 {DROP_MAX}%：后台解码在吃帧预算")
            if q["fps"] < FPS_MIN or b["fps"] < FPS_MIN:
                failures.append(f"fps 掉到 quiet {q['fps']:.2f} / busy {b['fps']:.2f}"
                                f"（下限 {FPS_MIN}）")
            if b["win_fps"] < q["win_fps"] - FPS_SPAN:
                failures.append(f"缩略图窗口内 busy 比 quiet 掉 {q['win_fps'] - b['win_fps']:.2f} fps，"
                                f"超 {FPS_SPAN}：节流不够（THUMB_BATCH/THUMB_SLEEP_MS）")
        print(f"  汇总（{REPS} 轮）  总 fps quiet {statistics.median(quiet):.2f} / "
              f"busy {statistics.median(busy):.2f}   "
              f"窗口 fps quiet {statistics.median(qwin):.2f} / busy {statistics.median(bwin):.2f}"
              f"   差 {statistics.median(qwin) - statistics.median(bwin):+.2f}")
        print(f"  后台吞吐 中位 {statistics.median(rates):.1f} / 最慢 {min(rates):.1f} 张/秒"
              f"（{N_STRIP} 张，长边 {EDGE}）  "
              f"引擎 RSS {rss_before:.0f} → {eng.rss_mib():.0f} MiB")
        if statistics.median(bwin) < FPS_MIN:
            failures.append(f"窗口内中位 fps 只有 {statistics.median(bwin):.2f}（下限 {FPS_MIN}）："
                            "总平均把开头那几秒的掉帧摊平了")
        if min(rates) < THUMB_RATE_MIN:
            failures.append(f"缩略图吞吐最慢一轮只有 {min(rates):.1f} 张/秒（下限 {THUMB_RATE_MIN}）："
                            "底片条要等太久，节流过头也是错")
    finally:
        eng.close()
        shutil.rmtree(root, ignore_errors=True)


def part_switch(failures: list[str]) -> None:
    print("\n=== 2) 切走再切回来：画面逐字节 + 切换成本 ===")
    tmp = tempfile.mkdtemp(prefix="m5-swap-")
    paths = build_strip(tmp, 6)
    eng = Engine(f"m5swap-{os.getpid()}")
    try:
        eng.send(cmd="hello")
        eng.wait("ready")
        eng.send(cmd="set_device", device=DEV)
        ds = eng.wait("device_set", timeout=60)
        if DEV.startswith("cuda") and not ds.get("cuda"):
            print("  跳过：没有 GPU")
            return
        # 先把底片条建起来再开图：select 走的是 index，格子里只有 load_image 那一张
        # 时"切到第 2 张"会被引擎当场拒绝——这条不是测试脚手架的省事写法，它正是
        # 宿主那边点第二格时用户按下去的那一下
        eng.send(cmd="session", action="scan", dir=tmp, thumbs=False)
        sc = eng.wait("session_scan", timeout=30)
        if sc["found"] != len(paths):
            raise RuntimeError(f"扫到 {sc['found']} 张，期望 {len(paths)} 张")
        eng.send(cmd="load_image", path=paths[0], max_px=PROXY_PX, strength=0.0)
        shm = eng.wait("shm_ready", timeout=60)
        eng.wait("image_ready", timeout=90)
        h, w = shm["h"], shm["w"]
        peer = FrameShm(shm["name"])
        # 在 a 上留一层看得见的内容：只 strength=0 的话两张图都可能等于原图，对拍没鉴别力
        eng.send(cmd="set_strength", value=0.62)
        eng.wait("params_set", timeout=30)
        eng.send(cmd="inpaint", action="add",
                 rle=[[h // 2, w // 2, 8, 255]], feather=2)
        eng.wait("inpaint_done", timeout=120)

        def frame() -> tuple:
            ev = eng.wait("frame", timeout=30)
            return np.frombuffer(peer.read_pixels(ev["slot"]), np.uint8).reshape(h, w, 4)[:, :, :3].copy()

        base = frame()
        # 这一句是给"逐字节相等"当地基的：strength 归 0 且没那一笔时的那一帧必须与
        # 现在这一帧不同，否则比的是两张原图，绕回当然"相等"——那种 PASS 不作数
        eng.send(cmd="set_strength", value=0.0)
        eng.wait("params_set", timeout=30)
        plain = frame()
        eng.send(cmd="set_strength", value=0.62)
        eng.wait("params_set", timeout=30)
        eng.wait("frame", timeout=30)
        if np.array_equal(plain, base):
            failures.append("对拍没有鉴别力：加了消除笔与 0.62 强度之后画面逐字节没变，"
                            "绕回相等自然全绿，这样的 PASS 不作数")
        else:
            d0 = np.abs(plain.astype(np.int16) - base.astype(np.int16)).max(axis=-1)
            print(f"  鉴别力：那一笔 + 0.62 强度改了 {(d0 > 0).mean():.2%} 像素"
                  f"（max {int(d0.max())} LSB）")
        costs: list = []
        backs: list = []
        for k in range(3):
            for idx in (1, 2, 3, 0):
                eng.send(cmd="session", action="select", index=idx)
                ir = eng.wait("image_ready", timeout=90)
                costs.append(ir["import_ms"])
                if idx != 0:
                    assert ir["layers"]["repair"] == 0, f"第 {idx} 张拿到了 a 的笔迹：{ir['layers']}"
                    eng.wait("frame", timeout=30)
                else:
                    back = ir          # 切回 a 的那条就是这一条，出了循环就没有第二次
            got = frame()
            same = bool(np.array_equal(got, base))
            backs.append(same)
            if not same:
                d = np.abs(got.astype(np.int16) - base.astype(np.int16)).max(axis=-1)
                failures.append(f"第 {k + 1} 次绕回 a 的画面对不上：max {int(d.max())} LSB / "
                                f"{(d > 0).mean():.4%} 像素")
            if not back["switched"]:
                failures.append(f"切回已开过的文档却没说 switched：{back['switched']}")
        med = statistics.median(costs)
        worst = max(costs)
        print(f"  {len(costs)} 次切换：import_ms 中位 {med:.1f} / 最坏 {worst:.1f} ms"
              f"（上限 {SWITCH_MS_MAX}）")
        print(f"  {len(backs)} 次绕回 a 逐字节相等：{sum(backs)}/{len(backs)}（{w}×{h}，"
              f"含一笔消除笔 + strength 0.62）")
        if sum(backs) != len(backs):
            failures.append(f"{len(backs) - sum(backs)} 次绕回 a 的画面没原样拿回来")
        if med > SWITCH_MS_MAX:
            failures.append(f"切文档中位 {med:.0f} ms 超上限 {SWITCH_MS_MAX}")
        peer.close()
    finally:
        eng.close()
        shutil.rmtree(tmp, ignore_errors=True)


def part_mixed(failures: list[str]) -> None:
    """4) 换幅面切文档到底劣化不劣化帧通路：A 直开 / B 绕一趟不同幅面，同进程交错。

    起因是真窗口里那条 mixed 臂（切到横幅那张 → shm 整块重建 → 切回竖幅）六次采样红了
    两次（57.44 / 58.39 fps），而同臂其余四次与同幅面那条臂从没红过。窗口一次运行要
    付启动、解码、预计算的钱，5 s 的采样里一次 200 ms 的外部停顿就是 4% 丢帧——这分不出
    "重建 shm 有代价"和"桌面上刚好有别的东西在跑"。所以把这一对搬到跑靶里：同一个引擎
    进程、同一张卡、两臂交替，唯一差别就是中间那一趟换幅面。
    """
    print("\n=== 4) 换幅面切文档不劣化帧通路（A 直开 / B 绕一趟不同幅面，交错） ===")
    from PIL import Image
    tmp = tempfile.mkdtemp(prefix="m5-mixed-")
    base = Image.open(FIXTURE).convert("RGB")
    pA = os.path.join(tmp, "portrait.jpg")                    # 4:5 → 代理 400×504
    base.resize((1024, 1280), Image.LANCZOS).save(pA, quality=90)
    pB = os.path.join(tmp, "landscape.jpg")                   # 3:2 → 代理 552×368
    base.resize((1600, 1067), Image.LANCZOS).save(pB, quality=90)
    eng = Engine(f"m5mixed-{os.getpid()}")
    try:
        eng.send(cmd="hello")
        eng.wait("ready")
        eng.send(cmd="set_device", device=DEV)
        ds = eng.wait("device_set", timeout=60)
        if DEV.startswith("cuda") and not ds.get("cuda"):
            print("  跳过：没有 GPU")
            return
        afps: list = []
        bfps: list = []
        adrop: list = []
        bdrop: list = []
        sizes: set = set()
        for i in range(REPS):
            if i % 2:
                b = _mixed_once(eng, tmp, pA, pB, busy=True)
                a = _mixed_once(eng, tmp, pA, pB, busy=False)
            else:
                a = _mixed_once(eng, tmp, pA, pB, busy=False)
                b = _mixed_once(eng, tmp, pA, pB, busy=True)
            afps.append(a["fps"]); bfps.append(b["fps"])
            adrop.append(a["drop"]); bdrop.append(b["drop"])
            sizes.update(b["dims"])
            print(f"  第 {i + 1} 轮  A 直开 {a['fps']:5.2f} fps（丢 {a['drop']:4.1f}%）   "
                  f"B 绕一趟换幅面 {b['fps']:5.2f} fps（丢 {b['drop']:4.1f}%）  "
                  f"绕回后代理档 {b['dims'][-1]} / 切换 {b['switch_ms']:.1f} ms")
        ma, mb = statistics.median(afps), statistics.median(bfps)
        print(f"  汇总（{REPS} 轮）  A 中位 {ma:.2f} / B 中位 {mb:.2f}  差 {ma - mb:+.2f}  "
              f"丢帧中位 A {statistics.median(adrop):.2f}% / B {statistics.median(bdrop):.2f}%")
        if len(sizes) < 2:
            failures.append(f"B 臂没真换过幅面（只见到 {sizes}）：这一节测的不是那件事")
        if mb < FPS_MIN:
            failures.append(f"B 臂中位只有 {mb:.2f} fps（下限 {FPS_MIN}）：切完文档帧通路没回到标称节奏")
        if ma - mb > FPS_SPAN:
            failures.append(f"B 比 A 掉 {ma - mb:.2f} fps（上限 {FPS_SPAN}）：重建 shm / 重挂预计算在吃帧预算")
        if statistics.median(bdrop) > DROP_MAX:
            failures.append(f"B 臂丢帧中位 {statistics.median(bdrop):.2f}%（上限 {DROP_MAX}%）")
    finally:
        eng.close()
        shutil.rmtree(tmp, ignore_errors=True)


def _mixed_once(engine: Engine, tmp: str, pA: str, pB: str, *, busy: bool) -> dict:
    """一臂：都把竖幅那张装好，B 臂中间多绕一趟"切到横幅 → 切回竖幅"，然后跑同一段 image_stream。"""
    engine.send(cmd="load_image", path=pA, max_px=PROXY_PX, strength=0.5)
    engine.wait("image_ready", timeout=90)
    dims: list = []
    sw_ms = 0.0
    if busy:
        engine.send(cmd="session", action="scan", dir=tmp, thumbs=False)
        sc = engine.wait("session_scan", timeout=30)
        if sc["found"] != 2:
            raise RuntimeError(f"这一节要正好两张不同幅面的图，扫到 {sc['found']} 张")
        idx_home = sc["current_index"]
        idx_other = 1 - idx_home
        engine.send(cmd="session", action="select", index=idx_other)
        ir = engine.wait("image_ready", timeout=90)
        dims.append(f"{ir['w']}x{ir['h']}")
        engine.send(cmd="session", action="select", index=idx_home)
        back = engine.wait("image_ready", timeout=90)
        dims.append(f"{back['w']}x{back['h']}")
        sw_ms = ir["import_ms"] + back["import_ms"]
        if back["w"] == ir["w"]:
            raise RuntimeError("切过去与切回来同幅面：这一节没测到重建 shm 那条路")
    else:
        dims.append("（没切）")
    r = run_bench(engine, frames=BENCH_FRAMES, interval=16.7, win_s=3.0)
    r["dims"] = dims
    r["switch_ms"] = sw_ms
    return r


def part_channel(failures: list[str]) -> None:
    print("\n=== 3) 通道账单：单张与整批都不许撑爆一行 JSON ===")
    tmp = tempfile.mkdtemp(prefix="m5-chan-")
    paths = build_strip(tmp, 8)
    try:
        got = scan_dir(tmp)
        infos = [make_thumb(p) for p in got["files"]]
        over = [i for i in infos if i["bytes"] > THUMB_MAX_BYTES]
        too_big = [i for i in infos if max(i["w"], i["h"]) > EDGE]
        kb = sum(len(i["jpeg_b64"]) for i in infos) / 1024.0
        print(f"  8 张（长边 ≤{EDGE}）：单张最大 {max(i['bytes'] for i in infos)} B，"
              f"整批 base64 {kb:.1f} KB，解码合计 {sum(i['decode_ms'] for i in infos):.0f} ms")
        print(f"  降质 {sum(1 for i in infos if i['reencoded'])} 张 / 缩尺寸 "
              f"{sum(1 for i in infos if i['resized'])} 张")
        if over:
            failures.append(f"{len(over)} 张缩略图超通道上限 {THUMB_MAX_BYTES} B")
        if too_big:
            failures.append(f"{len(too_big)} 张缩略图长边超过 {EDGE}")
        # 满幅像素绝不能进这条通道：一张 400×504 的 RGBA 就是 806 KB
        if kb / 8 > 128:
            failures.append(f"平均每张 {kb / 8:.0f} KB：这不是缩略图的量级，检查是不是把代理帧发出去了")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print(f"缺 fixture：{FIXTURE}")
        return 2
    if not torch.cuda.is_available() and DEV.startswith("cuda"):
        print("没有 GPU 可跑 image_stream：这一节不进闸，跳过而不是装 PASS")
        return 0
    failures: list[str] = []
    part_fps(failures)
    part_switch(failures)
    part_mixed(failures)
    part_channel(failures)
    print()
    if failures:
        for f in failures:
            print(f"× {f}")
        print(f"VERDICT=FAIL（{len(failures)} 条）")
        return 1
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
