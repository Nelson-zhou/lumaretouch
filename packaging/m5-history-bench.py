#!/usr/bin/env python3
"""M5-b 离线跑靶：全局撤销/重做——保真、代价、内存账，三笔分开数。

主张有四句，每一句都得被量到：

  1) **撤销回去的那一帧必须逐字节等于来时那一帧，重做再原样回来。** 这是产品口径，
     不是"看起来差不多"。协议用例（test_undo_walks_back_through_every_layer）已经
     用裸引擎钉过这一条；这里钉的是**装机件那一档代理尺寸**上它仍然成立，并且
     量它的代价——用例不看时间，跑靶不看步数语义，两份各司其职。
  2) **一步 = 一次手势。** 拖一下强度滑块发出五十条命令，栈里只许多一格。这条
     同时在"记账成本"上打靶：合并路径与每步都新增的路径，逐条往返时延不许拉开。
  3) **64 步快照住在哪里必须看得见。** 快照是 CPU 侧的字典，代价应当只在 RSS；
     显存账单在灌满栈前后不许变（变了就是撤销在偷偷重挂常驻张量而不释放）。
  4) **撤销不许把预计算退掉。** 检测不是修图；快照里 HISTORY_SKIP 那两项一旦
     漏进去，撤销会同时退掉几 MB 原件与掩膜显存，画面与账单一起错。

臂之间交替跑（口径沿用 m1-drag / m2-face / m3-color / m4-export / m5-filmstrip）。

跑法（要一个带 ROCm/CUDA torch 的解释器；CI 的两个 GPU job 已接）：
  REPS=3 LRT_DEVICE=cuda python3 packaging/m5-history-bench.py
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

from lumaretouch_engine.shm import FrameShm, shm_name          # noqa: E402

FIXTURE = os.path.join(HERE, "..", "engine", "tests", "fixtures", "portrait-1024x1280.jpg")
DEV = os.environ.get("LRT_DEVICE", "cuda")
REPS = int(os.environ.get("REPS", "3"))
PROXY_PX = 207360                  # 产品档代理（400×504）：与 M4/M5-a 真窗口同一档
BIG_PX = 1024000                   # 1280×800 那一档：撤销的重放代价在这档才看得出差别
N_COST = int(os.environ.get("LRT_HIST_ROUNDS", "40"))
N_DRAG = int(os.environ.get("LRT_HIST_DRAG", "50"))
HIST_TIERS = (("产品档 400×504", PROXY_PX), ("高档 1280×800", BIG_PX))

# ---- 判据（数字全部来自本机 RX 7600 XT 的实测，见计划文档 M5-b 节；换口径必须同时改这里）
# 实测口径（本机 RX 7600 XT + ROCm，REPS=3 正式轮，五层全挂着的产品档会话）：
#   ① 保真：产品档 400×504 与高档 904×1128 都是撤到底 0 LSB / 重做回原 0 LSB，
#      改动字节和 3.1e6 ~ 6.1e7（先证明这一对判据有鉴别力，再看那两个 0）。
#      这一节的 history_ms 只报数不进闸，因为它随**累计图层数**增长：产品档三轮
#      13.66 → 23.90 → 29.34（每一轮都往消除笔/修容层上再叠一笔），高档三轮
#      49.91 → 75.24 → 91.26。撤销走的是"按快照整条重放图层"那一条路，代价本来就是
#      图层数的函数——把这条写进注释，是为了不让下一个人把它读成"栈越深越慢"。
#   ② 代价（进闸的那一条）：同一份会话、图层数不变，80 次来回 history_ms 中位 16.26 /
#      p95 19.12 / 最坏 22.31，出帧中位 7.02 ms；第 2 次与第 40 次 16.47 → 15.41，
#      栈深 40 倍差而单次代价不涨。上限取中位的 2 倍（30）与最坏的 2.7 倍（60）：
#      CI 的 GPU runner 更慢，留的是这个余量；30 ms 仍明显小于"重开一次文档"的可感
#      代价——撤销比开图还慢就是设计错。
UNDO_MED_MS = float(os.environ.get("LRT_HIST_UNDO_MED", "30"))
UNDO_MAX_MS = float(os.environ.get("LRT_HIST_UNDO_MAX", "60"))
#   ③ 内存：发 72 条编辑 → 栈封顶 64 步，引擎 RSS 1187.7 → 1188.5 MiB（+0.8 MiB），
#      五项常驻字节账单前后逐字段相同（+0 B）。上限 8 MiB 是实测的 10 倍：这一条要挡的是
#      "快照里混进了几 MB 的原件"（HISTORY_SKIP 漏一项就是那种形状），不是挡 0.x MiB 的噪声。
MEM_MAX_MIB = float(os.environ.get("LRT_HIST_MEM_MAX", "8"))
#   ④ 手势合并：50 条连发，合并臂 → 1 步、逐条中位 0.54 ms；每步新增臂 → 50 步、
#      0.71 ms。差 0.17 ms 就是"真往栈里 append 一份快照"的代价（list.append 摊还 O(1)）。
#      上限 4 ms 是实测的 7 倍（这一条走的是 IPC，CI 上抖动大）；两臂之差超 2 ms 就说明
#      记账里混进了别的东西——比如在快照时读了几 MB 张量。
DRAG_MED_MS = float(os.environ.get("LRT_HIST_DRAG_MED", "4"))
DRAG_SPAN_MS = float(os.environ.get("LRT_HIST_DRAG_SPAN", "2"))
# 反向门禁用的开关：只跑某一节。平时不设，四节全跑。
ONLY = os.environ.get("LRT_HIST_ONLY", "")


class Engine:
    """一个真引擎子进程：撤销走的必须是装机件那一条路（同 server、同 shm、同常驻层）。"""

    def __init__(self, session: str):
        self.session = session
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

    def wait(self, event: str, timeout: float = 90.0, pred=None) -> dict:
        """等一条事件，期间看到的其他事件一律寄存（不丢）。

        撤销那条链上 history_state 就发在 frame 前面：拿"读到目标就返回"的写法
        会把画面证据吃掉，或者反过来把历史答复吃掉。寄存起来，谁要谁取。
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
            if e.get("event") == "error":
                raise RuntimeError(f"引擎报错：{e.get('error')}")
            if e.get("event") == "engine_warn":
                self.warns = getattr(self, "warns", []) + [e.get("warn", "")]
            if e.get("event") == event and (pred is None or pred(e)):
                return e
            self.parked.append(e)

    def reply(self, action: str) -> dict:
        e = self.history(action)
        if action in ("undo", "redo") and "history_ms" not in e:
            raise RuntimeError(f"{action} 的答复没带 history_ms（大概是一条 noop）：{e}")
        return e

    def history(self, action: str) -> dict:
        """一条 history 命令 = 一条带同一个 action 的 history_state 答复。

        必须按 action 配对：引擎只在被问时发这一条，而 state 与 undo 的答复形状一样；
        寄存队列里若还躺着上一轮问的那条，"取第一条 history_state"就会把答复配错主
        （跑靶头一次就是这么撞的：undo 拿到了上一轮的 state，报不出 history_ms）。
        """
        self.send(cmd="history", action=action)
        return self.wait("history_state", timeout=120,
                         pred=lambda e: e.get("action") == action)

    def last_frame(self) -> tuple:
        """把已排队的 frame 收干净，返回 (最后一帧像素, seq)。

        不能只读"下一条 frame 事件"的 slot：几条命令排了四帧在队列里，而双缓冲只有
        两块——最早那条事件的 slot 号现在装着最新那一帧，判据会比的是同一块内存里的
        同一张图，永远相等（假绿）。
        """
        last = None
        while True:
            try:
                e = self.q.get(timeout=0.6)
            except queue.Empty:
                break
            if e.get("event") == "frame":
                last = e
            elif e.get("event") == "error":
                raise RuntimeError(f"引擎报错：{e.get('error')}")
            else:
                self.parked.append(e)
        if last is None:
            for e in reversed(self.parked):
                if e.get("event") == "frame":
                    self.parked.remove(e)
                    last = e
                    break
        if last is None:
            raise RuntimeError("一条帧事件都没有，画面证据是空的")
        peer = self._peer
        h, w = self._h, self._w
        px = np.frombuffer(peer.read_pixels(last["slot"]), np.uint8).reshape(h, w, 4)[:, :, :3]
        return px.astype(np.int16), int(last["seq"])

    def _attach(self, ir: dict) -> dict:
        """按 image_ready 的尺寸重接 shm。

        名字不拿 shm_ready 里的：代理档没变时引擎不重建 shm，那一条事件根本不会再来第二次
        （M5-a 就在这个坑上等过 10 s），而名字本来就是 shm_name(session) 一个确定值。
        但必须每次重接：换档时引擎会 unlink + 重建，旧的 mapping 指着已删的 inode。
        """
        self._h, self._w = ir["h"], ir["w"]
        if getattr(self, "_peer", None) is not None:
            self._peer.close()
        self._peer = FrameShm(shm_name(self.session))
        return ir

    def open(self, path: str, max_px: int, strength: float = 0.0) -> dict:
        self.send(cmd="load_image", path=path, max_px=max_px, strength=strength)
        return self._attach(self.wait("image_ready", timeout=120))

    def select(self, index: int) -> dict:
        """切到底片条另一格，把 image_ready 那份显存账单取回来。

        这一条只用来量常驻字节（切走再切回来 = 按当前状态重放一遍图层），
        像素判据一律走 open() 那一条直开的通路。
        """
        self.send(cmd="session", action="select", index=index)
        return self._attach(self.wait("image_ready", timeout=120))

    def rss_mib(self) -> float:
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
            os.unlink(f"/dev/shm/{shm_name(self.session)}")
        except FileNotFoundError:
            pass


def brush_rle(h: int, w: int, cy: int, cx: int, r: int) -> list:
    out = []
    for y in range(max(0, cy - r), min(h, cy + r + 1)):
        dy = y - cy
        dx = int((r * r - dy * dy) ** 0.5)
        x0, x1 = max(0, cx - dx), min(w, cx + dx + 1)
        if x1 > x0:
            out.append([y, x0, x1 - x0, 255])
    return out


def write_cube(tmp: str, size: int = 8, k: float = 0.9) -> str:
    t = np.linspace(0.0, 1.0, size)
    bb, gg, rr = np.meshgrid(t, t, t, indexing="ij")
    rows = np.stack([rr, gg, bb], axis=-1)
    out = np.clip(rows * k, 0.0, 1.0)
    lines = [f"LUT_3D_SIZE {size}", f'TITLE "bench-{size}-{k}"']
    lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in out.reshape(-1, 3)]
    p = os.path.join(tmp, f"bench-{size}-{k}.cube")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p


def apply_five_layers(eng: Engine, cube: str, k: int = 0) -> None:
    """五层各动一次：磨皮强度、消除笔、修容笔、肤色定向、调色表。

    每层用的都是**不同的一条命令名**，因此在历史里天然是五个不同的组——这五层
    全撤得回来，才叫"一条跨层的历史"，各层自己 undo 是不够的。

    数值必须逐轮不同（k 是轮次）：一条不改任何东西的命令不占一步，这是引擎的
    正确行为（同值重复提交本来就没什么可撤销的），而"五层各一步"这条判据要的
    是"五次真改动"。第一轮跑第二、三次时报出栈深 4，就是这个差别被当成缺陷——
    grade 那四个数与上一轮逐字相同，签名一致，确实不该占步。
    """
    h, w = eng._h, eng._w
    eng.send(cmd="set_strength", value=0.55 + 0.05 * (k % 7))
    eng.wait("params_set", timeout=60)
    eng.send(cmd="inpaint", action="add",
             rle=brush_rle(h, w, h // 2 + 3 * (k % 5), w // 2 + 2 * (k % 7), 8), feather=2)
    eng.wait("inpaint_done", timeout=120)
    eng.send(cmd="light", action="add",
             rle=brush_rle(h, w, h // 3 + 2 * (k % 5), w // 3 + 3 * (k % 7), 8),
             feather=2, sign=1 if k % 2 == 0 else -1, radius=6)
    eng.wait("light_done", timeout=120)
    eng.send(cmd="grade", action="set", dh=0.010 + 0.004 * (k % 5),
             ds=0.08 + 0.01 * (k % 4), dv=-0.05 + 0.005 * (k % 6), amount=1.0)
    eng.wait("grade_done", timeout=120)
    eng.send(cmd="lut", action="set", path=cube)
    eng.wait("lut_done", timeout=120)


def part_fidelity(failures: list[str]) -> None:
    print("\n=== 1) 保真：两档代理尺寸上，撤到底逐字节等于出厂帧、重做到顶等于撤销前 ===")
    if DEV.startswith("cuda") and not torch.cuda.is_available():
        print("  跳过：要求 cuda 而这台机器没有 GPU")
        return
    tmp = tempfile.mkdtemp(prefix="m5-hist-")
    try:
        # 一档一个引擎进程。不是怕慢：同一张路径换代理档重开时，M5-a 的口径是
        # "丢掉坐标层 + 清历史，逐点层（表/肤色定向）原样保留"——于是上一档那张表
        # 还在，lut 去重下"再挂同一张表"不占一步，栈深 4 而不是 5（头一轮就是这么撞的）。
        # 那件事已由 test_session 钉住，这一节要钉的是"五层各一步"本身，所以从干净进程起。
        for t_idx, (label, px) in enumerate(HIST_TIERS):
            eng = Engine(f"m5hist-fid-t{t_idx}-{os.getpid()}")
            try:
                eng.send(cmd="hello")
                eng.wait("ready")
                eng.send(cmd="set_device", device=DEV)
                eng.wait("device_set", timeout=120)
                for i in range(REPS):
                    # 每次烘一张新表：同一张表在 lut 去重下不占一步，栈深会少一格
                    seq_idx = t_idx * REPS + i
                    cube = write_cube(tmp, 8, 0.80 + 0.03 * seq_idx)
                    ir = eng.open(FIXTURE, px, strength=0.0)
                    base, seq0 = eng.last_frame()
                    # 起算点：清掉上一轮留下的历史，并把这一刻的文档状态与那一帧一起
                    # 钉成基线。第 2 轮的"出厂帧"不是零图层——第 1 轮 redo 到顶后那些层
                    # 还挂着，这是引擎的正确语义（撤销退到的是"这一步之前"，不是"全零"）
                    snap0 = eng.history("clear")
                    st = eng.history("state")
                    if st["undo_steps"] != 0:
                        failures.append(f"{label} 第 {i + 1} 次：刚 clear 完栈里就有 {st['undo_steps']} 步")
                    apply_five_layers(eng, cube, seq_idx)
                    top, seq_top = eng.last_frame()
                    changed = int(np.abs(top - base).sum())
                    if changed == 0:
                        failures.append(f"{label} 第 {i + 1} 次：五层全挂上画面一模一样，对拍没鉴别力")
                        continue
                    st = eng.history("state")
                    steps = st["undo_steps"]
                    if steps != 5:
                        failures.append(f"{label} 第 {i + 1} 次：五层各一步，实际栈深 {steps}")
                    ms = []
                    for _ in range(steps):
                        ms.append(eng.reply("undo")["history_ms"])
                    back, seq_back = eng.last_frame()
                    diff_back = int(np.abs(back - base).max())
                    ds = eng.history("state")["doc_state"]
                    back_to = [ds["strength"], ds["counts"]["repair"], ds["counts"]["light"],
                               ds["lut"]["lit"], ds["grade"]["lit"], ds["grade"]["dh"],
                               ds["light"]["exposure"], ds["params"]["mid_gain"]]
                    start = [snap0["doc_state"]["strength"], snap0["doc_state"]["counts"]["repair"],
                             snap0["doc_state"]["counts"]["light"], snap0["doc_state"]["lut"]["lit"],
                             snap0["doc_state"]["grade"]["lit"], snap0["doc_state"]["grade"]["dh"],
                             snap0["doc_state"]["light"]["exposure"],
                             snap0["doc_state"]["params"]["mid_gain"]]
                    if back_to != start:
                        failures.append(f"{label} 第 {i + 1} 次：撤到底的文档状态不是起算点那一份 "
                                        f"{back_to} ≠ {start}")
                    for _ in range(steps):
                        ms.append(eng.reply("redo")["history_ms"])
                    again, _ = eng.last_frame()
                    diff_again = int(np.abs(again - top).max())
                    if seq_back <= seq0:
                        failures.append(f"{label} 第 {i + 1} 次：撤销没出帧（seq {seq0}→{seq_back}）")
                    if diff_back or diff_again:
                        failures.append(f"{label} 第 {i + 1} 次：撤到底最大偏差 {diff_back} LSB / "
                                        f"重做到顶 {diff_again} LSB（判据 0）")
                    print(f"  {label} 第 {i + 1} 次：{ir['w']}x{ir['h']} 改动字节和 {changed}（>0 才有鉴别力），"
                          f"撤到底 {diff_back} LSB，重做回原 {diff_again} LSB，"
                          f"{2 * steps} 次 history_ms 中位 {statistics.median(ms):.2f} 最坏 {max(ms):.2f}")
            finally:
                eng.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def part_cost(failures: list[str]) -> None:
    print(f"\n=== 2) 代价：产品档上 {N_COST} 次撤销/重做来回的 history_ms ===")
    if DEV.startswith("cuda") and not torch.cuda.is_available():
        print("  跳过：要求 cuda 而这台机器没有 GPU")
        return
    tmp = tempfile.mkdtemp(prefix="m5-hist-cost-")
    cube = write_cube(tmp)
    try:
        eng = Engine(f"m5hist-cost-{os.getpid()}")
        try:
            eng.send(cmd="hello")
            eng.wait("ready")
            eng.send(cmd="set_device", device=DEV)
            eng.wait("device_set", timeout=120)
            ir = eng.open(FIXTURE, PROXY_PX, strength=0.0)
            apply_five_layers(eng, cube)
            base, _ = eng.last_frame()
            undo_ms: list = []
            redo_ms: list = []
            render_ms: list = []
            for i in range(N_COST):
                u = eng.reply("undo")
                undo_ms.append(u["history_ms"])
                render_ms.append(u["render_ms"])
                r = eng.reply("redo")
                redo_ms.append(r["history_ms"])
                if i % 10 == 9:
                    print(f"  第 {i + 1} 次  undo {u['history_ms']:6.2f} ms / "
                          f"redo {r['history_ms']:6.2f} ms（出帧 {u['render_ms']:.2f} ms，"
                          f"栈 {u['undo_steps']}/{r['redo_steps']}）")
                if u.get("noop") or r.get("noop"):
                    failures.append(f"第 {i + 1} 次来回里出现了 noop：五层会话不该退无可退")
            back, _ = eng.last_frame()
            drift = int(np.abs(back - base).max())
            allms = undo_ms + redo_ms
            med, p95, mx = statistics.median(allms), sorted(allms)[int(len(allms) * 0.95) - 1], max(allms)
            print(f"  汇总（{len(allms)} 次）  中位 {med:.2f} / p95 {p95:.2f} / 最坏 {mx:.2f} ms，"
                  f"出帧中位 {statistics.median(render_ms):.2f} ms")
            print(f"  第 2 次撤销与第 2N 次的差："
                  f"{undo_ms[1]:.2f} → {undo_ms[-1]:.2f}（栈深变了不许让单次代价涨）")
            if drift:
                failures.append(f"{N_COST} 次来回之后画面与出厂帧差 {drift} LSB：撤销链在漂")
            if med > UNDO_MED_MS:
                failures.append(f"撤销中位 {med:.2f} ms 超上限 {UNDO_MED_MS}：按 Ctrl+Z 的手感不合格")
            if mx > UNDO_MAX_MS:
                failures.append(f"撤销最坏 {mx:.2f} ms 超上限 {UNDO_MAX_MS}")
            if len(undo_ms) > 4 and statistics.median(undo_ms[-10:]) > statistics.median(undo_ms[:10]) + DRAG_SPAN_MS:
                failures.append("后半程比前半程慢：栈越深越贵，说明重放里混进了随栈深增长的东西")
        finally:
            eng.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def part_memory(failures: list[str]) -> None:
    print(f"\n=== 3) 内存账：灌满 {64} 步快照的 RSS，与显存账单在前后不许动 ===")
    if DEV.startswith("cuda") and not torch.cuda.is_available():
        print("  跳过：要求 cuda 而这台机器没有 GPU")
        return
    tmp = tempfile.mkdtemp(prefix="m5-hist-mem-")
    strip = os.path.join(tmp, "strip")
    os.makedirs(strip)
    from PIL import Image
    base = Image.open(FIXTURE).convert("RGB")
    base.resize((900, 600), Image.LANCZOS).save(os.path.join(strip, "a.jpg"), quality=92)
    base.resize((640, 480), Image.LANCZOS).save(os.path.join(strip, "b.jpg"), quality=92)
    cube = write_cube(tmp)
    try:
        eng = Engine(f"m5hist-mem-{os.getpid()}")
        try:
            eng.send(cmd="hello")
            ready = eng.wait("ready")
            eng.send(cmd="set_device", device=DEV)
            eng.wait("device_set", timeout=120)
            eng.send(cmd="session", action="scan", dir=strip, thumbs=False)
            eng.wait("session_scan", timeout=30)
            ir = eng.open(FIXTURE, PROXY_PX, strength=0.0)
            apply_five_layers(eng, cube)
            sess = eng.wait("session_state", timeout=30)
            other = next(d["index"] for d in sess["docs"] if d["path"] != ir["doc"])
            # 基线：切走再切回来一次。这一趟按当前状态重放全部图层，报出来的就是
            # "这一格的显存账单"；历史灌满之后再走同一条路取第二次。两趟同一路径，
            # 差出来的那一点才是历史栈的代价（预期恒为 0 字节）
            eng.select(other)
            b0 = eng.select(ir["session_index"])
            rss0 = eng.rss_mib()
            # 灌满：交替 value / mid_gain 两个参数名——换组就不进合并窗口，每条真的
            # 新增一步（靠 sleep 跨窗口会把这一节拖成一分钟，而且测的不是同件事）
            n = ready["history_max"] + 8
            for i in range(n):
                if i % 2:
                    eng.send(cmd="set_strength", mid_gain=0.01 * (i % 9 + 1))
                else:
                    eng.send(cmd="set_strength", value=0.02 * (i % 40 + 1))
                eng.wait("params_set", timeout=60)
            st = eng.history("state")
            steps = st["undo_steps"]
            rss1 = eng.rss_mib()
            eng.select(other)
            b1 = eng.select(ir["session_index"])
            keys = ("bytes_filter", "bytes_bands", "bytes_light", "bytes_deform", "bytes_lut")
            dmem = rss1 - rss0
            print(f"  发了 {n} 条编辑 → 栈深 {steps}（上限 {ready['history_max']}），"
                  f"引擎 RSS {rss0:.1f} → {rss1:.1f} MiB（+{dmem:.1f}）")
            print("  显存账单（重放同一条文档状态两次）：" +
                  "，".join(f"{k} {b1[k] - b0[k]:+d} B" for k in keys))
            if steps != ready["history_max"]:
                failures.append(f"发了 {n} 条而栈深 {steps}：封顶没生效或合并把不同手势吃了")
            if dmem > MEM_MAX_MIB:
                failures.append(f"{steps} 步快照吃了 {dmem:.1f} MiB，超上限 {MEM_MAX_MIB}："
                                "快照里混进了大件（检查 HISTORY_SKIP）")
            for k in keys:
                if b1[k] != b0[k]:
                    failures.append(f"{k} 在灌满历史前后差 {b1[k] - b0[k]} B：撤销在动常驻显存")
            ds = st["doc_state"]
            if not ds["params"]:
                failures.append("doc_state.params 是空的：快照没带分带参数，撤销会抹掉半径/eps")
        finally:
            eng.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def part_drag(failures: list[str]) -> None:
    print(f"\n=== 4) 手势合并的经济性：{N_DRAG} 条连发的逐条往返，合并臂 vs 每步新增臂 ===")
    if DEV.startswith("cuda") and not torch.cuda.is_available():
        print("  跳过：要求 cuda 而这台机器没有 GPU")
        return
    eng = Engine(f"m5hist-drag-{os.getpid()}")
    try:
        eng.send(cmd="hello")
        ready = eng.wait("ready")
        eng.send(cmd="set_device", device=DEV)
        eng.wait("device_set", timeout=120)
        eng.open(FIXTURE, PROXY_PX, strength=0.0)
        med = {}
        for arm in ("merged", "distinct"):
            eng.history("clear")
            stamps: list = []
            for i in range(N_DRAG):
                t0 = time.monotonic()
                if arm == "merged":
                    eng.send(cmd="set_strength", value=0.1 + 0.8 * (i % 20) / 20.0)
                else:
                    # 换参数名 = 换一组：每一条都真的往栈里 append 一格
                    if i % 2 == 0:
                        eng.send(cmd="set_strength", value=0.1 + 0.8 * (i % 20) / 20.0)
                    else:
                        eng.send(cmd="set_strength", mid_gain=0.05 * (i % 15 + 1))
                eng.wait("params_set", timeout=60)
                stamps.append((time.monotonic() - t0) * 1000.0)
            st = eng.history("state")
            m = statistics.median(stamps)
            med[arm] = m
            want = 1 if arm == "merged" else min(N_DRAG, ready["history_max"])
            print(f"  {arm:8s} 臂：{N_DRAG} 条 → 栈深 {st['undo_steps']}（期望 {want}），"
                  f"逐条中位 {m:.2f} ms / p95 {sorted(stamps)[int(N_DRAG * 0.95) - 1]:.2f} ms")
            if st["undo_steps"] != want:
                failures.append(f"{arm} 臂 {N_DRAG} 条连发得到 {st['undo_steps']} 步，期望 {want}")
            if m > DRAG_MED_MS:
                failures.append(f"{arm} 臂逐条中位 {m:.2f} ms 超上限 {DRAG_MED_MS}：拖拽被记账拖慢了")
        if med["distinct"] - med["merged"] > DRAG_SPAN_MS:
            failures.append(f"每步新增臂比合并臂慢 {med['distinct'] - med['merged']:.2f} ms，"
                            f"超 {DRAG_SPAN_MS}：快照复制在吃预算")
    finally:
        eng.close()


def main() -> int:
    if not os.path.isfile(FIXTURE):
        print(f"缺 fixture：{FIXTURE}")
        return 2
    if not torch.cuda.is_available() and DEV.startswith("cuda"):
        print("没有 GPU 可跑常驻管线：这一节不进闸，跳过而不是装 PASS")
        return 0
    failures: list[str] = []
    parts = {"1": part_fidelity, "2": part_cost, "3": part_memory, "4": part_drag}
    if ONLY:
        # 这个开关只为反向门禁省时间（把一条判据调到实测之下，看它是不是真的报红）。
        # 平时不设；CI 不设——四节全跑才是这一节的完整口径。
        parts = {ONLY: parts[ONLY]}
        print(f"（只跑第 {ONLY} 节：反向门禁用法，正式轮必须四节全跑）")
    for fn in parts.values():
        fn(failures)
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
