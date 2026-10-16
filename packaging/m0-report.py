#!/usr/bin/env python3
"""M0 实测汇总：把 tier 阶梯与引擎分段摆成一张能判读的表。

用法：
  m0-report.py <results.jsonl> [engine.jsonl]   # 汇总表
  m0-report.py --one '<一条 M0_STATS json>'      # 单行简报（跑靶脚本逐组打印用）

判据（写死在计划里，不看完数据再改口）：
  1280 代理档  p95 ≤ 10 ms
  2048 精帧档  p95 ≤ 16 ms
看的是「引擎可读 → 真上屏」；present 回执没收齐时退回绘制回执并标注。
"""
from __future__ import annotations

import json
import statistics
import sys

MS = 1000.0


def ms(us: float) -> str:
    return f"{us / MS:.2f}"


def eng_ms(v) -> str:
    """引擎侧 bench_done 的分段本来就是 ms，不能再除一次 1000。"""
    return f"{float(v or 0):.2f}"


def load(path: str) -> list[dict]:
    try:
        with open(path) as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except FileNotFoundError:
        return []


def brief(d: dict) -> None:
    pt = d["pull_to_ack"]
    frames = pt["p50"] / MS / 16.7 or 1
    print(f"   fps={d['measured_fps']:.1f} 丢帧={d['drop_pct']:.1f}% "
          f"取→绘 p50={ms(pt['p50'])}ms({frames:.2f} 帧周期) p95={ms(pt['p95'])}ms "
          f"present={d.get('present_cover', 0)}/{d['n']}")


def engine_for(runs: list[dict], eng: list[dict]) -> dict:
    """同名 run 的引擎分段；bench_done 事件的 mode/device 也在这里。"""
    out: dict[str, dict] = {}
    for e in eng:
        if e.get("event") == "bench_done":
            out[e.get("_run", "?")] = e
    return out


# 引擎侧一帧拆成这样才读得懂：M1-2 的卖点就是「内核没动，省的全是搬运」，
# 只报一个「管线」总数就分不出这两种情况。
# M1-3c 之后「引擎:内核」这一列只包含混合那一步：滤波被拆到「引擎:滤波」，它是**一次性成本**
# （换图或换磨皮参数才付），拖拽期恒为 0。两列不相交，合计就是各列之和，不会算两遍。
ENG_COLS = ("引擎:测帧", "引擎:上传", "引擎:滤波", "引擎:内核", "引擎:GPU收尾", "引擎:CPU收尾",
            "引擎:回读", "引擎:写shm", "引擎:通知", "引擎:合计")


def eng_cells(e: dict) -> tuple[str, ...]:
    if not e:
        return ("—",) * len(ENG_COLS)
    if "kernel" in e:                      # M1-2 后的细粒度分段
        v = [e.get(k, 0) for k in ("synth", "pre", "filter", "kernel", "post_gpu",
                                   "cpu_post", "readback", "shm", "notify")]
        return tuple(eng_ms(x) for x in v) + (f"{sum(float(x or 0) for x in v):.2f}",)
    # 旧 jsonl 只给了一个 pipe 总数。把它填进「上传」或「内核」都会被读成
    # M1-2 的结论，所以那一列单独标成“管线(旧)”。
    pipe = float(e.get("pipe", 0) or 0)
    synth = float(e.get("synth", 0) or 0)
    shm, notify = float(e.get("shm", 0) or 0), float(e.get("notify", 0) or 0)
    cells = ["—"] * len(ENG_COLS)
    cells[0] = eng_ms(synth)
    cells[1] = f"管线(旧){pipe:.2f}"
    cells[7] = eng_ms(shm)
    cells[8] = eng_ms(notify)
    cells[9] = f"{synth + pipe + shm + notify:.2f}"
    return tuple(cells)


def table(runs: list[dict], eng: list[dict]) -> None:
    eby = engine_for(runs, eng)
    cols = ("run", "tier", "尺寸", "模式", "设备", "fps", "丢帧%",
            "取帧ms", "取→绘 p50/p95/p99", "可→上 p50/p95/p99") + ENG_COLS
    rows = []
    for d in runs:
        tier = d.get("tier", 2)
        key = "emit_to_present" if d.get("present_cover", 0) > 0 else "emit_to_ack"
        lab = "" if key == "emit_to_present" else " †"
        pt, pa = d["pull_to_ack"], d[key]
        e = eby.get(d.get("_run", ""), {})
        rows.append((
            d.get("_run", "?"),
            f"{tier}",
            f"{d['w']}x{d['h']}",
            d["mode"],
            d.get("device", "?"),
            f"{d['measured_fps']:.1f}",
            f"{d['drop_pct']:.1f}",
            ms(d["pull_dur"]["p95"]),
            f"{ms(pt['p50'])} / {ms(pt['p95'])} / {ms(pt['p99'])}",
            f"{ms(pa['p50'])} / {ms(pa['p95'])} / {ms(pa['p99'])}{lab}",
        ) + eng_cells(e))
    w = [max(len(str(c)), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]
    print("  " + " | ".join(str(c).ljust(w[i]) for i, c in enumerate(cols)))
    print("  " + "-+-".join("-" * x for x in w))
    for r in rows:
        print("  " + " | ".join(str(v).ljust(w[i]) for i, v in enumerate(r)))
    if any(not d.get("present_cover", 0) for d in runs):
        print("  † 该组 present 回执为空，用的是绘制回执（少算一次合成等待）")


def marginal(runs: list[dict]) -> None:
    """tier 阶梯的差值才是真答案：绝对值里掺着测量框架自己的地板。"""
    by = {(d["w"], d.get("tier", 2), d["mode"]): d for d in runs}
    t0, t1, t2 = by.get((1280, 0, "copy")), by.get((1280, 1, "copy")), by.get((1280, 2, "copy"))
    if not (t0 and t1 and t2):
        print("\n  [归因] tier 阶梯缺组，无法分解：见上表 tier 列")
        return
    f = lambda d, k: d[k]["p50"] / MS
    print("\n  [归因 · 1280x800 copy，p50]")
    print(f"    tier0 rAF+IPC 地板            : {f(t0,'pull_to_ack'):6.2f} ms   （不传像素不绘制）")
    print(f"    tier1 +4MB/帧 跨进程传输       : {f(t1,'pull_to_ack'):6.2f} ms   （净增 {f(t1,'pull_to_ack')-f(t0,'pull_to_ack'):+.2f}）")
    print(f"    tier2 +texSubImage2D+draw     : {f(t2,'pull_to_ack'):6.2f} ms   （净增 {f(t2,'pull_to_ack')-f(t1,'pull_to_ack'):+.2f}）")
    print(f"    帧率  {t0['measured_fps']:.1f} → {t1['measured_fps']:.1f} → {t2['measured_fps']:.1f} fps"
          f"   丢帧率 {t0['drop_pct']:.1f}% → {t1['drop_pct']:.1f}% → {t2['drop_pct']:.1f}%")


def gates(runs: list[dict]) -> None:
    """M0 判据（重定义版，理由见本文件底部 NOTES）：
      交互流主指标是可持续帧率与丢帧，不是“引擎→上屏”的绝对延迟——后者最少
      包含一个垂直同步周期（60Hz 下 16.7 ms），再快也不可能进 10 ms。
    """
    print("\n  [判据 · 帧率/丢帧]")
    for d in runs:
        if d.get("tier", 2) != 2:
            continue
        if d["w"] <= 1280:
            ok = d["measured_fps"] >= 55.0 and d["drop_pct"] <= 5.0
            print(f"    {d['w']}x{d['h']} {d['mode']:8s} 代理档  fps={d['measured_fps']:5.1f}"
                  f"(≥55) 丢帧={d['drop_pct']:4.1f}%(≤5) → {'成立' if ok else '不成立'}")
        else:
            ok = d["measured_fps"] >= 20.0
            print(f"    {d['w']}x{d['h']} {d['mode']:8s} 精帧档  fps={d['measured_fps']:5.1f}"
                  f" 单帧 p50={ms(d['pull_dur']['p50'])}ms → "
                  f"{'可走按需出帧' if ok else '必须换路径'}")


NOTES = """
  为何重定义判据（不是改口要把没达标说成达标）：
    原阈「引擎可读 → 上屏 p95 ≤ 10 ms」在 60Hz 屏幕上物理不可达：帧必须在 vsync
    边界上才画得出去，光等下一个同步点就是 16.7 ms，与实现无关。
    所以 M0 真正要量的是两件可验的事：
      1) 连续预览能不能 sustained 60fps（帧率+丢帧）
      2) 像素搬运/上传绘制到底贵多少（tier 阶梯的差值）
    延迟则按「几个帧周期」报，不按绝对 ms 报，否则数字全是调度不是成本。
"""


def eng_arm(eng_by_run: dict, arm: str) -> dict | None:
    """把同一臂各次的 bench_done 归成中位。engine_for 的键是 "E2-xxx#3"，这里按臂名聚合。"""
    rows = [e for key, e in eng_by_run.items() if key.split("#")[0] == arm]
    if not rows:
        return None
    seg = ("synth", "pre", "filter", "kernel", "post_gpu", "cpu_post", "readback", "shm", "notify")
    med = lambda xs: statistics.median(xs) if xs else 0.0
    per = {k: med([float(r.get(k, 0) or 0) for r in rows]) for k in seg}
    # 旧数据只有一个 pipe：当作「管线+搬运」合计读，不假装能拆开口
    if not any("kernel" in r for r in rows):
        per = dict(synth=med([float(r.get("synth", 0) or 0) for r in rows]),
                   pipe=med([float(r.get("pipe", 0) or 0) for r in rows]))
    # 重算次数取"最差那一次"而不是中位：中位会被 600 帧摊平成 0.00，缓存被绕过也看不出来
    refl = [int(r.get("refilter_frames", 0) or 0) for r in rows if "refilter_frames" in r]
    return {"kernel": per.get("kernel", 0.0), "filter": per.get("filter", 0.0),
            "refilter": max(refl) if refl else None, "total": sum(per.values())}


def aggregate(runs: list[dict], eng: dict | None = None) -> None:
    """按臂聚合（run 名形如 A1-raw#3）。看中位与最差，不挑最好看的那一次。"""
    reps = [d for d in runs if "#" in (d.get("_run") or "")]
    if len(reps) < 2:
        return
    eng = eng or {}
    arms: dict[str, list[dict]] = {}
    for d in reps:
        arms.setdefault(d["_run"].split("#")[0], []).append(d)
    print("\n  [按臂聚合 · 中位 / 最差]")
    # 预计算列只在 G 轮这类真跑过 precompute 的数据里出现：无条件加列会让 E/F 轮
    # 整片“—”，而报表里满屏占位符正是没人再认真看列的原因
    has_pc = any(d.get("pcBackend") for ds in arms.values() for d in ds)
    # 老引擎数据没 refilter_frames，加一列全"—"不如不加（同 has_pc 的理由）
    has_drag = any("refilter_frames" in e for e in (eng or {}).values())
    cols = ("臂", "n", "MB/帧", "上传策略", "分块", "fps 中位", "fps 最差",
            "丢帧% 中位", "丢帧% 最差", "取→绘 p50", "p95", "撞帧run",
            "引擎合计", "内核")
    if has_drag:
        cols += ("滤波中位/重算帧",)
    if has_pc:
        cols += ("预计算（后端·点·通道·MB·总ms）",)
    cols += ("≥中位59且最差≤5%",)
    rows = []
    for name, ds in arms.items():
        fps = [d["measured_fps"] for d in ds]
        drop = [d["drop_pct"] for d in ds]
        p50 = [d["pull_to_ack"]["p50"] for d in ds]
        p95 = [d["pull_to_ack"]["p95"] for d in ds]
        ok = statistics.median(fps) >= 59 and max(drop) <= 5
        d0 = ds[0]
        frac = min(float(d0.get("dirtyFrac", 1) or 1), 1.0)
        mb = d0["w"] * d0["h"] * 4 * frac / 1e6
        ck = int(d0.get("chunks", 1) or 1)
        # 「撞帧」判定：p95 超过 1.5 个帧周期就算尾部撞了整整一帧（双峰分布）
        stalls = sum(1 for x in p95 if x > 25_000)
        # 引擎侧分段：同一臂的 bench_done 取中位（老数据没拆细分段时只给得出合计）
        e = eng_arm(eng, name)
        cells = [name, str(len(ds)), f"{mb:.2f}", str(d0.get("upload", "raw")), str(ck),
                 f"{statistics.median(fps):.1f}", f"{min(fps):.1f}",
                 f"{statistics.median(drop):.1f}", f"{max(drop):.1f}",
                 ms(statistics.median(p50)), ms(statistics.median(p95)),
                 f"{stalls}/{len(ds)}",
                 f"{e['total']:.2f}" if e else "—", f"{e['kernel']:.2f}" if e else "—"]
        if has_drag:
            cells.append("—" if not e else
                         f"{e['filter']:.2f}/{e['refilter']}"
                         if e['refilter'] is not None else f"{e['filter']:.2f}/—")
        if has_pc:
            pcs = [d["pcTotalMs"] for d in ds if d.get("pcTotalMs") is not None]
            cells.append("—" if not pcs else (
                f"{d0.get('pcBackend')}·{d0.get('numLandmarks')}·"
                f"{d0.get('activeChannel') or '全图'}·"
                f"{(d0.get('maskBytes') or 0) / 1e6:.1f}·{statistics.median(pcs):.1f}"))
        cells.append("✓" if ok else "✗")
        rows.append(tuple(cells))
    w = [max(len(str(c)), *(len(r[i]) for r in rows)) for i, c in enumerate(cols)]
    print("  " + " | ".join(str(c).ljust(w[i]) for i, c in enumerate(cols)))
    print("  " + "-+-".join("-" * x for x in w))
    for r in rows:
        print("  " + " | ".join(str(v).ljust(w[i]) for i, v in enumerate(r)))


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--one":
        brief(json.loads(sys.argv[2]))
        return 0
    runs = load(sys.argv[1]) if len(sys.argv) > 1 else []
    eng = load(sys.argv[2]) if len(sys.argv) > 2 else []
    if not runs:
        print("无结果")
        return 1
    eby = engine_for(runs, eng)
    table(runs, eng)
    aggregate(runs, eby)
    marginal(runs)
    gates(runs)
    print(NOTES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
