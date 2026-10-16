"""引擎主进程：stdin 收 JSON lines 命令，stdout 发 JSON lines 事件。

像素不进这条通道——它走 /dev/shm 双缓冲，这里只发「第 seq 帧已就绪、
在 slot N、t_emit_ns=...」这种几十字节的通知。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time

from .frames import test_frame
from .shm import FrameShm, monotonic_ns, shm_name

PROTOCOL_VERSION = 1


def emit(obj: dict) -> None:
    """stdout 会被主循环与跑靶线程同时写，必须串行化。"""
    with _EMIT_LOCK:
        sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        sys.stdout.flush()


_EMIT_LOCK = threading.Lock()


class Engine:
    def __init__(self, session: str):
        self.session = session
        self.shm: FrameShm | None = None
        self.bench: threading.Thread | None = None
        self.stop_flag = threading.Event()
        self.device = "cpu"
        self._quit = False
        self._pipe_out = None

    # ------------------------------------------------------------ 通路自检
    def cmd_hello(self, _p: dict):
        emit({"event": "ready", "protocol": PROTOCOL_VERSION, "pid": os.getpid()})

    # ------------------------------------------------------------ 帧缓冲
    def _ensure_shm(self, w: int, h: int) -> FrameShm:
        if self.shm and (self.shm.w, self.shm.h) == (w, h):
            return self.shm
        if self.shm:
            self.shm.close()
            self.shm.unlink()
        self.shm = FrameShm(shm_name(self.session), w, h, slots=2, create=True)
        emit({"event": "shm_ready", "name": self.shm.name, "path": self.shm.path,
              "w": w, "h": h, "slot_size": self.shm.slot_size,
              "pixel_size": self.shm.pixel_size, "total": self.shm.total})
        return self.shm

    # ------------------------------------------------------------ 跑靶
    def cmd_bench_start(self, p: dict):
        w, h = int(p["w"]), int(p["h"])
        frames = int(p.get("frames", 600))
        interval_ms = float(p.get("interval_ms", 16.7))
        mode = p.get("mode", "copy")          # copy | pipeline
        shm = self._ensure_shm(w, h)
        self.stop_flag.clear()
        self.bench = threading.Thread(target=self._bench_loop,
                                      args=(shm, frames, interval_ms, mode), daemon=True)
        self.bench.start()
        emit({"event": "bench_started", "frames": frames, "interval_ms": interval_ms,
              "mode": mode, "w": w, "h": h})

    def _bench_loop(self, shm: FrameShm, frames: int, interval_ms: float, mode: str):
        # 分段计时：测帧 / GPU 管线 / 写 shm / 发通知。M0 必须知道 60fps 的天花板
        # 卡在哪一段——上一版只给一个总数，把合成图形的 17 ms 当成了通路极限。
        period = interval_ms / 1000.0
        next_t = monotonic_ns() / 1e9
        acc = dict(synth=0.0, pipe=0.0, prep=0.0, shm=0.0, notify=0.0)
        t_last_report = time.perf_counter()

        def snapshot(done: int) -> dict:
            return {k: round(v / max(done, 1), 3) for k, v in acc.items()}

        for i in range(frames):
            if self.stop_flag.is_set():
                break
            t0 = monotonic_ns()
            pixels = test_frame(shm.w, shm.h, i)
            acc["synth"] += (monotonic_ns() - t0) / 1e6
            if mode == "pipeline":
                t1 = monotonic_ns()
                pixels = self._pipeline_rgba(pixels)
                acc["pipe"] += (monotonic_ns() - t1) / 1e6
            t3 = monotonic_ns()
            seq, t_emit, slot = shm.write_frame(pixels)
            acc["shm"] += (monotonic_ns() - t3) / 1e6
            emit({"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
                  "w": shm.w, "h": shm.h, "mode": mode})
            acc["notify"] += (monotonic_ns() - t_emit) / 1e6
            next_t += period
            delay = next_t - monotonic_ns() / 1e9
            if delay > 0:
                time.sleep(delay)
            if time.perf_counter() - t_last_report > 2.0:
                emit({"event": "bench_progress", "done": i + 1, "total": frames,
                      **snapshot(i + 1)})
                t_last_report = time.perf_counter()
        emit({"event": "bench_done", "frames": frames, "mode": mode,
              "device": self.device, **snapshot(frames)})

    # ------------------------------------------------------------ GPU 管线
    def _pipeline_rgba(self, rgba):
        """跑靶管线：输入缓存好的 RGBA 测帧，输出另存一张 RGBA。

        故意不复用输入缓冲：那是 test_frame 的缓存本体，改写它会让下一帧的
        “基图”逐帧漂走，「帧真的在换」这个证据就不可靠了。
        """
        import numpy as np

        from .ops.guided import make_tensor, retouch_t, to_numpy_chw
        out = self._pipe_out
        if out is None or out.shape != rgba.shape:
            out = np.empty_like(rgba)
            out[:, :, 3] = 255
            self._pipe_out = out
        arr = rgba[:, :, :3].astype(np.float32) / 255.0
        t = make_tensor(arr, self.device)
        o = retouch_t(t, strength=0.6, radius=12, eps=6e-4)
        out[:, :, :3] = (np.clip(to_numpy_chw(o), 0, 1) * 255).astype(np.uint8)
        return out

    def cmd_set_device(self, p: dict):
        self.device = p.get("device", "cpu")
        emit({"event": "device_set", "device": self.device})

    def cmd_shutdown(self, _p: dict):
        self.stop_flag.set()
        self._quit = True
        emit({"event": "bye"})

    # ------------------------------------------------------------ 主循环
    def run(self):
        table = {"hello": self.cmd_hello, "bench_start": self.cmd_bench_start,
                 "bench_stop": lambda p: (self.stop_flag.set(), emit({"event": "bench_stopped"})),
                 "set_device": self.cmd_set_device, "shutdown": self.cmd_shutdown}
        # 不用 `for line in sys.stdin`：那会等 EOF，收到 shutdown 也退不掉
        while not self._quit:
            line = sys.stdin.readline()
            if not line:            # 父进程已关闭管道
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                fn = table.get(msg.get("cmd", ""))
                if fn is None:
                    emit({"event": "error", "error": f"未知命令: {msg.get('cmd')}"})
                    continue
                fn(msg)
            except Exception as e:  # 协议层不许因单条消息崩溃
                emit({"event": "error", "error": f"{type(e).__name__}: {e}"})
        self.stop_flag.set()
        if self.shm:
            self.shm.close()
            self.shm.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="default")
    args = ap.parse_args()
    Engine(args.session).run()


if __name__ == "__main__":
    main()
