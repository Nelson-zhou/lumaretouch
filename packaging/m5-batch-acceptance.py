#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M5 发布验收：100 张一批的婚礼样片，批量导出零崩溃。

计划文档里 M5 那句验收写的是"100 张婚礼样片批量零崩溃"。M4 的 m4-export-bench 已经
证过**分块正确性**（分块 == 整幅逐字节、峰值只随 tile 走）与 2~5 MP 的单张量级；它没有
回答的是规模问题：一批一百张连跑下来，进程会不会慢慢漏、第 97 张会不会突然坏、跑完还
能不能接着服务。规模问题只能按规模量。

五节：

  ① 全出片：N 张里 failed 必须为 0，每张产物存在、PIL 解得开、**尺寸 == 源图尺寸**
     （导出必须是全尺寸：掉回代理档就是"批量很快、片子是小的"那种假绿）。
  ② 规模期稳定性：引擎 PID 全程不变；批前/批后 RSS 差有界；跑完这批之后引擎**还能
     服务**（再 hello 一次拿 ready、再导一张仍能出帧）——"零崩溃"不能只看这一批的
     返回值，一个正在漏显存的进程这一批也可能全过。
  ③ 分块账随规模的形状：tiles 随像素数增长，而单块耗时与 delta 峰值不随"这是第几张"
     增长（前面的张数不该把后面的拖慢——那是缓存/显存累积的直接读数）。
  ④ 逐张耗时：中位与最坏的上限；整批 total_ms 的上限。
  ⑤ 无损交付那一臂：一小批 PNG。①–④ 跑的是 JPEG，把编码器混在同一组预算里判无损
     就是拿有损的尺子量无损（真图实测：quality=95 旧映射跌到 PNG level 9，3 MP 要
     5.5 s/张，一百张就是九分钟纯编码）。这一臂单独预算，并验实际压缩档位报得出来。

素材是本仓那张程序化人像做的确定性变换（尺寸档循环 + 亮度/裁切按序号变），因此这一条
可在 CI 与任何机器上复现，且不涉及真人授权。

跑法（要带 GPU torch 的解释器）：
  N=100 LRT_DEVICE=cuda python3 packaging/m5-batch-acceptance.py
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
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine", "src"))

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
DEV = os.environ.get("LRT_DEVICE", "cuda")
N = int(os.environ.get("N", "100"))
TILE = int(os.environ.get("LRT_BATCH_TILE", "512"))

# ---- 判据（数字全部来自本机 RX 7600 XT + ROCm 的 N=100 实测轮，见计划文档 M5 验收段）
#   实测：failed 0/100；逐张 total_ms 最快 43.2 / 中位 127.2 / p95 179.9 / 最坏 191.3；
#   整批 15 640.7 ms（墙钟 15.6 s）；引擎 RSS 1164.9 → 1198.8 MiB（+34.0）；
#   单块耗时 前 1/4 中位 7.47 → 后 1/4 中位 7.21 ms（规模不累积）。
# 上限留的是 3~8 倍：CI 的 GPU runner 比本机慢，而这一条要挡的是"规模一上来就漏/就崩"，
# 不是挡 0.x ms 的抖动——RSS 那条尤其如此：+34 MiB 是缓存与碎片的正常量级，
# 256 MiB 挡的是"每张都在攒一份全幅张量不放手"那种形状（一百张就是几百 MiB）。
RSS_MAX_MIB = float(os.environ.get("LRT_BATCH_RSS", "256"))
PER_MED_MS = float(os.environ.get("LRT_BATCH_PER_MED", "400"))
PER_MAX_MS = float(os.environ.get("LRT_BATCH_PER_MAX", "800"))
BATCH_MAX_S = float(os.environ.get("LRT_BATCH_TOTAL", "60"))
# PNG（无损）那一臂：上面三个上限是从 JPEG 批量量出来的，把编码器混在同一组数里
# 就是拿有损的预算判无损。真图实测 PNG level 6 写一张 3 MP 要 ≈0.8 s，所以单独
# 设预算、单独取 N（默认 20，CI 不跑成分钟级）。
PNG_N = int(os.environ.get("LRT_BATCH_PNG_N", "20"))
PNG_PER_MED_MS = float(os.environ.get("LRT_BATCH_PNG_MED", "3000"))
PNG_PER_MAX_MS = float(os.environ.get("LRT_BATCH_PNG_MAX", "6000"))


def rss_mib(pid: int) -> float:
    with open(f"/proc/{pid}/status", encoding="utf-8") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    return -1.0


class Engine:
    """真引擎子进程：验收必须走装机那条路（同 server、同导出线程、同守卫）。"""

    def __init__(self, session: str):
        env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "..", "engine", "src"))
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "lumaretouch_engine.server", "--session", session],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env)
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line:
                try:
                    self.q.put(json.loads(line))
                except json.JSONDecodeError:
                    self.q.put({"event": "_raw", "text": line})

    def send(self, **cmd):
        self.proc.stdin.write(json.dumps(cmd) + "\n")
        self.proc.stdin.flush()

    def wait(self, event: str, timeout: float = 240.0) -> dict:
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            try:
                e = self.q.get(timeout=1.0)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"引擎进程提前退出（rc={self.proc.returncode}）")
                continue
            if e.get("event") == event:
                return e
            if e.get("event") == "error":
                raise RuntimeError(f"引擎报错：{e.get('error')}（等的是 {event}）")
        raise TimeoutError(f"等 {event} 超时 {timeout} s")


def build_batch(dst: str, n: int) -> list[str]:
    """确定性造 n 张"样片"：四档尺寸循环 + 按序号的亮度/裁切，全部从同一张人像派生。

    尺寸必须真的在动：一律同尺寸的批量只测吞吐，测不到 tiles/margin 随面积的分支，
    而那正是分块管线在规模下最先坏的地方。
    """
    base = Image.open(FIXTURE).convert("RGB")
    sizes = [(1024, 1280), (2048, 2560), (2400, 1600), (1600, 1600)]
    paths: list[str] = []
    for i in range(n):
        w, h = sizes[i % len(sizes)]
        img = base.resize((w, h), Image.LANCZOS)
        # 逐张可区分：亮度 + 一个按序号偏移的裁切框（不改尺寸，改内容）
        gain = 0.80 + 0.20 * ((i % 7) / 6.0)
        arr = np.clip(np.asarray(img, dtype=np.float32) * gain, 0, 255).astype(np.uint8)
        off = (i * 13) % 64
        arr[off:off + 40, :60] = (30 + (i % 50), 40, 50)
        p = os.path.join(dst, f"sample-{i:03d}.jpg")
        Image.fromarray(arr).save(p, format="JPEG", quality=93)
        paths.append(p)
    return paths


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print(f"× 缺少素材 {FIXTURE}（先跑 packaging/make-test-portrait.py）")
        return 2
    tmp = tempfile.mkdtemp(prefix="lrt-batch-")
    ind, outd = os.path.join(tmp, "in"), os.path.join(tmp, "out")
    os.makedirs(ind); os.makedirs(outd)
    fails: list[str] = []

    def chk(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  × ") + msg)
        if not cond:
            fails.append(msg)

    if N < 8:
        print("× N 至少 8：分位数与前/后 1/4 的对比在小样本上没有意义")
        return 2
    print(f"── 造 {N} 张样片（四档尺寸循环，确定性派生自 {os.path.basename(FIXTURE)}）")
    paths = build_batch(ind, N)
    mb = sum(os.path.getsize(p) for p in paths) / 2 ** 20
    print(f"  输入合计 {mb:.1f} MiB，输出目录 {outd}")

    eng = Engine(f"batch-{os.getpid()}")
    try:
        eng.send(cmd="hello")
        ready = eng.wait("ready")
        pid = ready["pid"]
        eng.send(cmd="set_device", device=DEV)
        ds = eng.wait("device_set")
        chk(bool(ds["cuda"]), f"设备真落在了 GPU 上（device_set 报 cuda={ds['cuda']}，"
                              f"落在 CPU 上这份验收就没有意义）")
        eng.send(cmd="load_image", path=paths[0], max_px=207360, strength=0.5)
        ir = eng.wait("image_ready")
        print(f"  引擎 pid={pid}，当前文档 {ir['w']}×{ir['h']}（代理档）")
        rss_before = rss_mib(pid)

        print(f"── ① 一批 {N} 张全尺寸导出")
        t0 = time.monotonic()
        eng.send(cmd="export", images=paths, out_dir=outd, format="jpg",
                 quality=92, tile=TILE)
        done = eng.wait("export_done", timeout=1800)
        wall = time.monotonic() - t0
        imgs = done["images"]
        chk(done["failed"] == 0, f"failed == 0（实际 {done['failed']}）")
        chk(len(imgs) == N, f"回报张数 == {N}（实际 {len(imgs)}）")

        bad_missing = bad_size = 0
        per_ms: list[float] = []
        tiles_by_px: dict[int, int] = {}
        order_drift: list[tuple[int, float]] = []
        for k, r in enumerate(imgs):
            if "error" in r:
                bad_missing += 1
                print(f"      第 {k} 张失败：{r.get('stage')} {r.get('error')}")
                continue
            src = Image.open(r["path"])
            got = Image.open(r["out"])
            if got.size != src.size or os.path.getsize(r["out"]) <= 0:
                bad_missing += 1
            if (got.width, got.height) != (r["w"], r["h"]):
                bad_size += 1
            per_ms.append(float(r["total_ms"]))
            tiles_by_px[int(r["px"])] = int(r["tiles"])
            order_drift.append((k, float(r["per_tile_ms"])))
        chk(bad_missing == 0, f"每张产物都在、可解码、且是全尺寸（坏 {bad_missing} 张）")
        chk(bad_size == 0, f"回报尺寸 == 产物尺寸（不符 {bad_size} 张）")

        print(f"── ② 规模期稳定性：进程与内存账")
        eng.send(cmd="hello")               # 再握手一次：进程还活着才报得出 ready
        again = eng.wait("ready", timeout=60.0)
        chk(again["pid"] == pid, f"批量前后是同一个进程（{pid} → {again['pid']}）")
        rss_after = rss_mib(pid)
        growth = rss_after - rss_before
        chk(growth <= RSS_MAX_MIB,
            f"引擎 RSS {rss_before:.1f} → {rss_after:.1f} MiB（+{growth:.1f}，上限 {RSS_MAX_MIB}）")
        # 跑完一百张还得能再服务一次：这一条比"这批返回值好看"更接近"零崩溃"
        eng.send(cmd="export", images=[paths[7]], out_dir=outd, format="jpg",
                 quality=92, tile=TILE)
        d2 = eng.wait("export_done", timeout=600)
        one = d2["images"][0]
        chk(d2["failed"] == 0 and os.path.getsize(one["out"]) > 0,
            f"批量之后仍能再导一张并出文件（{os.path.basename(one['out'])} "
            f"{os.path.getsize(one['out']) // 1024} KiB）——进程没被规模拖成半死")

        print(f"── ③ 分块账随规模的形状")
        chk(len(tiles_by_px) >= 3, f"覆盖到 {len(tiles_by_px)} 档像素数：{sorted(tiles_by_px)}")
        mono = all(sorted(tiles_by_px)[i] < sorted(tiles_by_px)[i + 1]
                   and tiles_by_px[sorted(tiles_by_px)[i]] <= tiles_by_px[sorted(tiles_by_px)[i + 1]]
                   for i in range(len(tiles_by_px) - 1))
        chk(mono, "tiles 随像素数单调不减（分块数由面积算，不是拍脑袋的定值）")
        first_q = [v for k, v in order_drift if k < N // 4]
        last_q = [v for k, v in order_drift if k >= N - N // 4]
        f_med, l_med = statistics.median(first_q), statistics.median(last_q)
        chk(l_med <= f_med * 1.6 + 5,
            f"单块耗时不随张数累积：前 1/4 中位 {f_med:.2f} ms → 后 1/4 中位 {l_med:.2f} ms")

        print(f"── ④ 逐张与整批耗时")
        med, worst = statistics.median(per_ms), max(per_ms)
        chk(med <= PER_MED_MS, f"逐张 total_ms 中位 {med:.1f} ≤ {PER_MED_MS}")
        chk(worst <= PER_MAX_MS, f"逐张 total_ms 最坏 {worst:.1f} ≤ {PER_MAX_MS}")
        chk(done["total_ms"] / 1000.0 <= BATCH_MAX_S,
            f"整批 total_ms {done['total_ms']:.1f} ms（墙钟 {wall:.1f} s）≤ {BATCH_MAX_S} s")
        # method 必须是 inclusive：默认的 exclusive 会在样本少时外插，报出比"最坏"还高的
        # p95（N=8 那轮就是 189.1 > 185.5）——一行里两个数自相矛盾，读的人第一个疑问就是
        # "这份账是不是没对齐"。
        p95 = statistics.quantiles(per_ms, n=20, method="inclusive")[18]
        print(f"  明细：最快 {min(per_ms):.1f} / 中位 {med:.1f} / p95 {p95:.1f} "
              f"/ 最坏 {worst:.1f} ms")
        chk(p95 <= worst, f"p95 {p95:.1f} ≤ 最坏 {worst:.1f}（分位数自己不许和最大值打架）")

        print(f"── ⑤ 无损交付那一臂：{PNG_N} 张 PNG")
        # 婚礼样片真要交无损片时，卡的不是分块而是编码器。quality=95 旧映射会跌进
        # PNG level 9（实测 3 MP 要 5.5 s/张），一百张就是九分钟纯编码——这一臂
        # 把"批量零崩溃"从"JPEG 很块"补成"无损也交得出"。
        png_paths = paths[:PNG_N]
        t0 = time.monotonic()
        eng.send(cmd="export", images=png_paths, out_dir=outd, format="png",
                 quality=95, tile=TILE)
        dpng = eng.wait("export_done", timeout=1800)
        pw = [float(r["write_ms"]) for r in dpng["images"] if "error" not in r]
        chk(dpng["failed"] == 0 and len(pw) == PNG_N,
            f"PNG 批量 failed={dpng['failed']}，出片 {len(pw)}/{PNG_N}")
        lv = {r.get("compress_level") for r in dpng["images"] if "error" not in r}
        chk(lv == {6}, f"quality=95 的 PNG 实际落在档位 {lv}（上限 6；7–9 档实测"
                       "只换 3–4% 体积却多花 1.4–6.8× 时间）")
        one = dpng["images"][0]
        src0 = Image.open(one["path"])
        got0 = Image.open(one["out"])
        chk(got0.size == src0.size and os.path.getsize(one["out"]) > 0,
            f"PNG 产物可解码且尺寸等于源图（{got0.size}）；"
            "无损语义本身由 test_export 的逐字节往返用例钉，不在这里重言一遍")
        pmed, pmax = statistics.median(pw), max(pw)
        chk(pmed <= PNG_PER_MED_MS, f"PNG 逐张 write_ms 中位 {pmed:.1f} ≤ {PNG_PER_MED_MS}")
        chk(pmax <= PNG_PER_MAX_MS, f"PNG 逐张 write_ms 最坏 {pmax:.1f} ≤ {PNG_PER_MAX_MS}")
        print(f"  PNG 明细：{PNG_N} 张共 {time.monotonic() - t0:.1f} s，"
              f"最快 {min(pw):.1f} / 中位 {pmed:.1f} / 最坏 {pmax:.1f} ms")
    finally:
        try:
            eng.send(cmd="shutdown")
        except Exception:
            pass
        eng.proc.wait(timeout=30)
        if os.environ.get("LRT_BATCH_KEEP") != "1":
            shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"── N={N} tile={TILE} 设备={DEV}：{len(fails)} 条不过" if fails
          else f"── N={N} tile={TILE} 设备={DEV}：全部通过")
    print("VERDICT=PASS" if not fails else "VERDICT=FAIL")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
