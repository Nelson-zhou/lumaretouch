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
# 磨皮参数的默认值只在这里取一次：vram 在模块层就容忍 torch 缺失（CPU job 也能 import），
# 在这里复用它们而不是写第二份字面量，否则默认值与生产值会漂移。
from .vram import DEFAULT_DETAIL_GAIN, DEFAULT_EPS, DEFAULT_RADIUS

PROTOCOL_VERSION = 1

# 跑靶模式：
#   copy               纯拷贝，M0 通路基线
#   pipeline / pipeline_copyin  逐帧 numpy 往返（M1-2 对照组）
#   pipeline_resident  源图与输出帧常驻显存（M1-2 目标组）
#   image_stream       真图常驻流（M1-3a）：需先 load_image，每帧只拖滑块系数
MODES = ("copy", "pipeline", "pipeline_copyin", "pipeline_resident", "image_stream")
# torch 首次建 ROCm 上下文 + 显存池要几百毫秒，混进均值里会把稳态算胖，先空跑几帧
WARMUP_FRAMES = 8


def _clamp_strength(v) -> float:
    """强度只接受 [0,1]。load_image 与 set_strength 必须同一规：一边夹一边不夹的话，
    越界值会被包框里的 clamp_ 削平成一张看不出错但语义错的帧，而 image_ready.strength
    照原值上报。"""
    return min(max(float(v), 0.0), 1.0)


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
        self._cuda = False        # 真的是 GPU 才需要 synchronize，CPU 上调一次是白调
        self._torch = None        # set_device 时握一次模块引用，免得每帧走一遍 import
        self._quit = False
        self._pipe_out = None
        self._vram = None
        # 常驻会话对应的那张源图（CPU 侧 numpy），留着是为了换设备时能就地重建。
        # F 轮第一轮就是栽在这里：load_image 先于 set_device，会话建在 cpu 上，
        # 之后切 cuda 也只改了 self.device，旧张量静静躺在 CPU 上跑了 91 ms/帧，
        # 而 bench_done 照样报 cuda:true——数据看起来完全正常，结论全是假的。
        self._src_rgb = None
        # 真图会话是否建立。不能拿 self._vram is not None 当“已导图”：跑靶的合成会话
        # 会把它顶掉，之后 set_strength 就不报错而是拿彩条图冒充用户照片。
        self._image_loaded = False
        # 预计算产物的 CPU 原件留着：换设备重建会话时要就地重挂，不能“迁移完就没脸了”。
        # 掩膜与关键点只在当前会话的当前尺寸上成立，这是本节的主要不变式。
        self._precompute = None
        self._precompute_backend = None
        self._channel = None
        # 磨皮参数（M1-3c）：与 strength 不同，它们变了滤波结果才会变。缓存键靠这个字典，
        # 所以它必须存在引擎侧而不是只在调用方：否则报表上看不出「这一帧重算了没」。
        self._params = dict(radius=DEFAULT_RADIUS, eps=DEFAULT_EPS, detail_gain=DEFAULT_DETAIL_GAIN)
        self._wlock = threading.Lock()   # 跑靶线程与 stdin 线程都在写同一块双缓冲
        self._strength = _clamp_strength(0.5)

    # ------------------------------------------------------------ 通路自检
    def cmd_hello(self, _p: dict):
        emit({"event": "ready", "protocol": PROTOCOL_VERSION, "pid": os.getpid()})

    # ------------------------------------------------------------ 帧缓冲
    def _ensure_shm(self, w: int, h: int) -> FrameShm:
        if self.shm and (self.shm.w, self.shm.h) == (w, h):
            return self.shm
        with self._wlock:
            if self.shm:
                self.shm.close()
                self.shm.unlink()
            self.shm = FrameShm(shm_name(self.session), w, h, slots=2, create=True)
        emit({"event": "shm_ready", "name": self.shm.name, "path": self.shm.path,
              "w": w, "h": h, "slot_size": self.shm.slot_size,
              "pixel_size": self.shm.pixel_size, "total": self.shm.total})
        return self.shm

    # ------------------------------------------------------------ 跑靶
    def _reject_bench(self, msg: str, mode: str):
        """拒绝开跑：除了 error 还必须发 bench_done{failed}。

        只发 error 的话，宿主那边认为 bench 已经开起来了，前端会空轮询到超时（上一轮
        就是这么静默卡了 200 s），拿到的表现是“没数据”而不是“没跑成”。
        """
        emit({"event": "error", "error": msg})
        emit({"event": "bench_done", "frames": 0, "mode": mode, "failed": True,
              "device": self.device, "cuda": self._cuda, "reason": msg})

    def cmd_bench_start(self, p: dict):
        if "w" not in p or "h" not in p:
            # 少参数时原来是裸 int(p["w"]) 抛 KeyError，事件里只有一句 "KeyError: 'w'"，
            # 看不出是协议用错还是引擎坏了；说清缺什么、从哪拿（shm_ready 里的 w/h）
            self._reject_bench("bench_start 缺 w/h：应从 shm_ready 拿会话尺寸", p.get("mode", "copy"))
            return
        w, h = int(p["w"]), int(p["h"])
        frames = int(p.get("frames", 600))
        interval_ms = float(p.get("interval_ms", 16.7))
        mode = p.get("mode", "copy")          # 见 MODES
        if mode not in MODES:
            # 不认得的模式不能默默当成 copy 跑：上一轮矩阵里写错模式名就会拿到
            # 一份“管线其实没跑”的数据，看上去还完全正常
            self._reject_bench(f"未知 bench 模式: {mode}（可用：{', '.join(MODES)}）", mode)
            return
        if mode == "image_stream":
            if not self._image_loaded:
                self._reject_bench("image_stream 需要先 load_image", mode)
                return
            if (int(p["w"]), int(p["h"])) != (self._vram.w, self._vram.h):
                # 尺寸不一致会在写 shm 时才爆，且报的是“字节数不对”，看不出根因；先拦住
                self._reject_bench(f"image_stream 尺寸 {p['w']}x{p['h']} "
                                   f"!= 已加载图的代理档 {self._vram.w}x{self._vram.h}", mode)
                return
        shm = self._ensure_shm(w, h)
        self.stop_flag.clear()
        self.bench = threading.Thread(target=self._bench_loop,
                                      args=(shm, frames, interval_ms, mode), daemon=True)
        self.bench.start()
        emit({"event": "bench_started", "frames": frames, "interval_ms": interval_ms,
              "mode": mode, "w": w, "h": h})

    def _sync(self) -> None:
        """GPU 内核是异步排队执行的：不在段边界 synchronize，内核时间会被记到
        后一段（D2H）的头上，分段就白分了。两条臂用同一套同步点，总量仍可比。"""
        if self._cuda:
            self._torch.cuda.synchronize()

    def _make_frame(self, shm: FrameShm, i: int, mode: str, pipe):
        """引擎侧一帧的全部工作，按模式分派。返回 (RGBA 帧, 各段 ms)。

        抽成一个方法是为了让 packaging/m1-vram-bench.py 能直接复用同一份代码——
        离线跑靶如果自己拼一份近似逻辑，量的数就不能代表产品通路。
        """
        seg = dict(synth=0.0, pre=0.0, filter=0.0, kernel=0.0, post_gpu=0.0, cpu_post=0.0, readback=0.0)
        # image_stream 模拟拖滑块：系数在 0.25→0.75 上扫一个 100 帧周期，
        # 像素逐帧真的在变；常驻管线的系数跑靶如果只动 0.001，字节上几乎看不出区别
        if mode == "image_stream":
            strength = 0.25 + 0.5 * (i % 100) / 99.0
        else:
            strength = 0.6 + 0.001 * (i % 50)
        if pipe is not None:
            # 常驻路径：源图不重算、不上传，每帧只换一个系数
            channel = self._channel if mode == "image_stream" else None
            t = monotonic_ns()
            # 参数必须跟着走：不传的话调用方用 set_strength 改了半径，跑靶仍按默认值出帧，
            # 量的就不是产品通路（而且会多一次缓存重算混进数据里）
            out = pipe.retouch(strength, channel=channel, **self._params)
            self._sync()
            # M1-3c：kernel 段现在只是混合；重算滤波的那一笔单独列到 filter 段。
            # 两者不重叠（filter 由 prepare 自己量，kernel = 整段减去 filter），拼起来
            # 才是以前的“内核”，这样拖拽热路径的真实成本能被看见，也不会把合计算两遍。
            # 注意 pipeline_copyin 那条臂没有 filter 段：它调的是 retouch_t，滤波与混合
            # 在同一个表达式里拆不开（filter=0 不等于“它不滤波”）。跨臂对拍要比的是
            # copyin.kernel ≈ resident.filter + resident.kernel。
            whole = (monotonic_ns() - t) / 1e6
            seg["filter"] = float(getattr(pipe, "last_filter_ms", 0.0) or 0.0)
            seg["kernel"] = max(whole - seg["filter"], 0.0)
            t = monotonic_ns()
            pipe.pack(out)
            # 跑靶指纹（只给合成靶纸用）：常驻路径的源图不动，逐帧变化的像素只能靠盖序号块。
            # 真图流不能盖——那会在用户照片上刷一块彩色补丁；它的 strength 在扫，像素本来就在变。
            if mode == "pipeline_resident":
                pipe.stamp(i)
            self._sync()
            seg["post_gpu"] = (monotonic_ns() - t) / 1e6
            t = monotonic_ns()
            pixels = pipe.read_back()
            seg["readback"] = (monotonic_ns() - t) / 1e6
            return pixels, seg
        t = monotonic_ns()
        pixels = test_frame(shm.w, shm.h, i)
        seg["synth"] = (monotonic_ns() - t) / 1e6
        if mode in ("pipeline", "pipeline_copyin"):
            pixels, s = self._pipe_copyin(pixels, strength, **self._params)
            seg.update(s)
        return pixels, seg

    def _bench_loop(self, shm: FrameShm, frames: int, interval_ms: float, mode: str):
        """跑靶线程的入口：任何异常都必须变成一条事件。

        主循环的 try 包不到这个线程里。上一轮就是这个问题：`_open_vram` 里 torch
        报错或显存不够，线程静默死掉，调用方只能等超时，拿到一份「没跑但看上去正常」
        的数据。现在早退发 error + bench_done{failed}，脚本当场能看出来。
        """
        try:
            self._bench_run(shm, frames, interval_ms, mode)
        except Exception as e:
            emit({"event": "error", "error": f"bench 线程异常退出({mode}): {type(e).__name__}: {e}"})
            emit({"event": "bench_done", "frames": 0, "mode": mode, "failed": True,
                  "device": self.device, "cuda": self._cuda, "warmup": WARMUP_FRAMES})

    def _bench_run(self, shm: FrameShm, frames: int, interval_ms: float, mode: str):
        # 分段计时：测帧 / 上传 / 内核 / GPU 收尾 / 回读 / 写 shm / 发通知。
        # M0 必须知道 60fps 的天花板卡在哪一段——上一版只给一个总数，把合成图形的 17 ms
        # 当成了通路极限；M1-2 要证的是「内核没变快，快的全是搬运」，那就更得拆开。
        period = interval_ms / 1000.0
        acc = dict(synth=0.0, pre=0.0, filter=0.0, kernel=0.0, post_gpu=0.0, cpu_post=0.0,
                   readback=0.0, shm=0.0, notify=0.0)
        # 重算次数：拖拽期零推理的直接证据。只要这个数不是 1（或 0），缓存就没真的生效，
        # 而按均值报 filter 会把它藏起来（600 帧里重算一次只有 0.0075 ms/帧）。
        refilters = 0

        def snapshot(done: int) -> dict:
            return {k: round(v / max(done, 1), 3) for k, v in acc.items()}

        pipe = (self._vram if mode == "image_stream"
                else self._open_vram(shm.w, shm.h) if mode == "pipeline_resident" else None)
        # 预热：跑完全相同的每帧工作（同一 _make_frame），但不写 shm、不发事件、不进统计
        for k in range(WARMUP_FRAMES):
            self._make_frame(shm, k, mode, pipe)
        self._sync()
        emit({"event": "bench_warmup", "frames": WARMUP_FRAMES, "mode": mode,
              "device": self.device, "cuda": self._cuda})

        next_t = monotonic_ns() / 1e9
        t_last_report = time.perf_counter()
        for i in range(frames):
            if self.stop_flag.is_set():
                break
            pixels, seg = self._make_frame(shm, i, mode, pipe)
            if seg.get("filter", 0.0) > 0:
                refilters += 1
            for k, v in seg.items():
                acc[k] += v
            t4 = monotonic_ns()
            with self._wlock:
                seq, t_emit, slot = shm.write_frame(pixels)
            acc["shm"] += (monotonic_ns() - t4) / 1e6
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
              "device": self.device, "cuda": self._cuda, "warmup": WARMUP_FRAMES,
              # pipe_device 才是真正跑了这 600 帧的设备。只报 self.device/cuda 的话，
              # 会话落在 CPU 上也能报出一份标着 cuda 的好数据。取局部 pipe 而不是
              # self._vram：后者会被别的命令顶掉，报的就不是刚才那一轮的服务者。
              "pipe_device": str(pipe.device) if pipe is not None else None,
              # 零推理跑靶的验收面：重算次数应当是 0（预热那 8 帧已经付掉一次性成本）
              "refilter_frames": refilters,
              "refilter_ms_total": round(acc["filter"], 2),
              "params": dict(self._params),
              **snapshot(frames)})

    # ------------------------------------------------------------ GPU 管线
    def _attach_pipeline(self, rgb, adopt: bool = True):
        """把一张 (H,W,3) uint8 接成 GPU 常驻会话。源图一次性进显存，之后不再回 CPU。

        adopt=False 给跑靶的合成会话用：它不能顶掉真图会话（self._vram/_src_rgb），
        否则一次 pipeline_resident 跑靶之后，“已导图”这个判定、set_strength 与
        bench_done.pipe_device 都会对着那张彩条图说话。"""
        from .vram import make_pipeline

        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        pipe = make_pipeline(self.device, w, h, rgb)
        if pipe.fallback:
            emit({"event": "engine_warn", "warn": pipe.fallback})
        if adopt:
            self._vram = pipe
            self._src_rgb = rgb
        emit({"event": "vram_ready", "device": str(pipe.device), "w": w, "h": h,
              "adopted": bool(adopt),
              "bytes_src": int(pipe.src_u8.numel() * pipe.src_u8.element_size()),
              "bytes_frame": int(pipe.frame_gpu.numel() * pipe.frame_gpu.element_size())})
        return pipe

    def _open_vram(self, w: int, h: int):
        """跑靶用的合成源图会话（不拥有全局会话，见 _attach_pipeline.adopt）。"""
        return self._attach_pipeline(test_frame(w, h, 0)[:, :, :3].copy(), adopt=False)

    # ------------------------------------------------------------ 真图导入
    def cmd_load_image(self, p: dict):
        """导入一张真图：解码 → 代理帧 → 常驻显存 → 出第一帧。整场会话只走一次。

        解码耗时不藏在帧里：它是一次性成本，与拖滑块时的逐帧成本完全不同量级，
        混在一起量就分不出“导入慢”还是“交互慢”。
        """
        from .decode import PROXY_PIXELS, load_rgb

        # 跑靶线程还在写那块双缓冲：此时换图会 close/unlink 它正在写的 shm，
        # 线程会在已失效的 mmap 上抱错，产出一份“跑了半截但 frames=600”的数。
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝换图：先 bench_stop"})
            return
        t0 = monotonic_ns()
        try:
            d = load_rgb(p["path"], int(p.get("max_px") or PROXY_PIXELS))
        except Exception as e:
            emit({"event": "error", "error": f"导入失败({type(e).__name__}): {e}"})
            return
        shm = self._ensure_shm(d.w, d.h)
        # 旧图的预计算产物对新图没有任何意义（尺寸/内容都变了），先清空；
        # 不清的话下一个请求会拿到上一张脸的掩膜，那比没有掩膜更坑。
        self._precompute = None
        self._precompute_backend = None
        self._channel = None
        t_a = monotonic_ns()
        pipe = self._attach_pipeline(d.rgb)
        self._image_loaded = True
        t_b = monotonic_ns()
        self._strength = _clamp_strength(p.get("strength", 0.5))
        pipe.render(self._strength, **self._params)
        with self._wlock:
            seq, t_emit, slot = shm.write_frame(pipe.read_back())
        t_c = monotonic_ns()
        emit({"event": "image_ready", **d.meta(), "device": str(pipe.device),
              "strength": self._strength,
              # 逐段归因，不留“由减法得出的一坨”：验收口径①要的是「解码」与「初始化常驻张量」
              # 两个分开数。首次 attach 里含着 CUDA 上下文/内核模块的进程级 lazy init，
              # 不拆开来就会把它当成「每张图都要 150 ms」写进产品结论。
              "shm_ms": round((t_a - t0) / 1e6 - d.t_total_ms, 2),
              "attach_ms": round((t_b - t_a) / 1e6, 2),
              "first_frame_ms": round((t_c - t_b) / 1e6, 2),
              # M1-3c：首帧里含一次与强度无关的滤波（产品档实测 ~4.5 ms）。不拆进单独字段，
              # first_frame_ms 就会被读成“每帧都得 4.5 ms”，而拖拽期实际只付混合那 0.1 ms。
              # 一次性成本与逐帧成本混在一起量就分不出谁是谁。
              "first_frame_filter_ms": round(float(pipe.last_filter_ms), 2),
              # 零推理换来的显存代价必须能看见，不能只报快了多少
              "bytes_filter": pipe.filter_resident_bytes(),
              # 只报滤波这一份：掩膜在本事件之后才挂上（precompute 跑在 image_ready 后面），这里附 bytes_face 恒为 0，
              # 反而会被读成"掩膜没常驻"。掩膜/关键点的字节数由 precompute_ready 报，那才是它们为真的那一刻。
              "import_ms": round((t_c - t0) / 1e6, 2)})
        emit({"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
              "w": shm.w, "h": shm.h, "mode": "image"})
        # 导入期预计算：产品上“导图就算一次”，但它是可选步——失败不许把导入本身拖成失败。
        # 它自己的 error 事件会单独发，报表里 backend/resident 一眼可验。
        if p.get("precompute"):
            self.cmd_precompute({"backend": p.get("backend", "auto"),
                                 "model_dir": p.get("model_dir"),
                                 "channel": p.get("channel")})

    # ------------------------------------------------------------ 导入期预计算
    def _precompute_ready_event(self, pc, info, *, build_ms: float, infer_ms: float,
                                attach_ms: float, total_ms: float, replayed_for: str | None = None):
        """precompute_ready 只在这里组装一次。

        两处各写一份的必然结果是漂移，而且漂的方向永远是“设备切换那条臂少一个字段”：
        重挂那条路径先前就没有 build_ms/infer_ms/total_ms，UI 把它们声明为必存字段
        就会读到 undefined。现在两条臂的事件形状相同，差别只写在 replayed_for 里。
        """
        ev = {"event": "precompute_ready", **pc.meta(self._vram.h, self._vram.w),
              "resident_device": info["resident_device"],
              "mask_bytes": info["mask_bytes"], "landmark_bytes": info["landmark_bytes"],
              "active_channel": self._channel,
              "build_ms": build_ms, "infer_ms": infer_ms,
              "attach_ms": attach_ms, "total_ms": total_ms}
        if replayed_for:
            ev["replayed_for"] = replayed_for
        return ev

    def cmd_precompute(self, p: dict):
        """导入期一次性预计算：478 点关键点 + 语义掩膜，算完直接常驻显存。

        三个耗时分开报，因为它们是三种成本：后端建图/首次推理是每进程一笔，
        逐图推理是每张图一笔，H2D 挂载是代理帧字节数的一笔。混成一个总数就分不出
        下一步该优化谁。

        不许静默降级：点名要 mediapipe 而后端/模型不在，直接报错；只有 `auto` 允许回落，
        且回落必须发 engine_warn —— 上轮「CPU 会话标 cuda」就是少了这一层。
        """
        from . import face as face_mod

        if not self._image_loaded or self._vram is None or self._src_rgb is None:
            emit({"event": "error", "error": "precompute 需要先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝预计算：先 bench_stop"})
            return
        backend = p.get("backend", "auto")
        t0 = monotonic_ns()
        try:
            fn = face_mod.build(backend, p.get("model_dir"))
        except face_mod.MissingBackend as e:
            emit({"event": "error", "error": f"预计算后端不可用({backend}): {e}"})
            return
        except ValueError as e:
            emit({"event": "error", "error": f"预计算参数非法: {e}"})
            return
        t1 = monotonic_ns()
        if backend == "auto" and fn.name != backend and getattr(fn, "notes", None):
            emit({"event": "engine_warn", "warn": f"auto 回落 {fn.name}: {fn.notes[-1]}"})
        try:
            pc = fn(self._src_rgb)
        except Exception as e:
            emit({"event": "error", "error": f"预计算失败({type(e).__name__}): {e}"})
            return
        t2 = monotonic_ns()
        # 通道校验必须上移到“上显存”之前。放在 load_face 之后报错会留下半截状态：
        # 掩膜已常驻、_precompute 已赋值、但 precompute_ready 从没发过——宿主只收到一个 error，
        # 下次换设备却突然收到一个它从未见过初始值的 replayed_for；而 UI 报“没掩膜”的同一
        # 时刻，引擎里那张掩膜是可用且真的在参与渲染的。
        channel = p.get("channel")
        available = sorted(pc.masks)
        if channel and channel not in available:
            emit({"event": "error", "error": f"没有掩膜通道 {channel}"
                  f"（可用：{', '.join(available) or '无'}）"})
            return
        try:
            info = self._vram.load_face(pc)
        except Exception as e:
            emit({"event": "error", "error": f"掩膜上显存失败({type(e).__name__}): {e}"})
            return
        t3 = monotonic_ns()
        self._precompute = pc
        self._precompute_backend = pc.backend
        if channel:
            self._channel = channel
        emit(self._precompute_ready_event(pc, info,
              build_ms=round((t1 - t0) / 1e6, 2),
              infer_ms=round((t2 - t1) / 1e6, 2),
              attach_ms=round((t3 - t2) / 1e6, 2),
              total_ms=round((t3 - t0) / 1e6, 2)))
        # 预计算完不重发帧：默认渲染路径不看掩膜，重发只能多一个变量进测量。
        # 要看掩膜作不作数，用 set_strength + channel。

    def cmd_set_strength(self, p: dict):
        """滑块动一下：只重算系数，不重解码也不重上传。返回一帧。

        channel 可以指到某个常驻掩膜通道（只换张量引用，不重传任何东西），这就是
        M1-3c「拖滑块零推理」的入口。
        """
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            # 会话与缓冲不同尺寸时 write_frame 只会报“字节数不对”，看不出是换档没走完
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                  f"!= 会话 {self._vram.w}x{self._vram.h}，请先 load_image"})
            return
        # 跑靶互斥：_wlock 只护“写 shm”那一步，护不到 frame_gpu。跑靶线程是
        # pack(frame_gpu) → read_back() → 锁内写 shm，这里的 render 也写同一个 frame_gpu；
        # 插在中间就会让跑靶把拖滑块的像素当成自己那一帧（seq/slot 仍配得上，但证据对不上人）。
        # 实测代价还不止错乱：672×848 跑靶中一次 render_ms 到过 534.79 ms。
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 set_strength：先 bench_stop"})
            return
        # 先全部校验、再一次性提交：这条命令里任何一个字段非法就整条不生效。
        # 原来的顺序是先把 self._strength / self._channel 提交，再校验磨皮参数；参数越界时
        # 虽然 emit error 返回了，strength 却已经被这条"没有执行"的命令改走——下一条不带
        # value 的 set_strength 会拿这个泄漏值出帧，用户看到的是"我拒绝了，画面却变了"。
        strength = _clamp_strength(p.get("value", self._strength))
        channel = self._channel
        if "channel" in p:
            if p["channel"] and p["channel"] not in self._vram.mask_names:
                emit({"event": "error", "error": f"没有掩膜通道 {p['channel']}"
                      f"（可用：{', '.join(self._vram.mask_names) or '无，先 precompute'}）"})
                return
            channel = p["channel"] or None
        # 磨皮参数：只有真变了才会重算滤波。半径直接决定 reflect pad 后的分配量
        # （积分图是 O(1)/像素但与窗口面积挂钩），没硬边界的话一个越界值就能把显存打爆，
        # 与 max_px 同一类风险。
        # 下界不是随手取的：eps=0 会让 `a = var/(var+eps)` 在平坦皮区算 0/0 = NaN（产品档实测
        # 402795 个子像素为 NaN）。这份 NaN 会被写进常驻缓存，而 `(1-0)*img + 0*NaN` 仍是 NaN
        # （IEEE 里 0×NaN = NaN），于是 strength=0 与解码原图差到 255 LSB —— 验收口径③
        # 整段会话被打穿。radius=0 不产 NaN，但滑块彻底空操作（实测 s=0.5 与原图 0 处不同），
        # 产品上没有任何意义，一并卡掉。
        params = dict(self._params)
        for k, lo, hi in (("radius", 1, 256), ("eps", 1e-6, 1.0), ("detail_gain", 0.0, 2.0)):
            if p.get(k) is None:
                continue
            try:
                v = int(p[k]) if k == "radius" else float(p[k])
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"参数 {k} 非法：{p[k]!r}"})
                return
            if not lo <= v <= hi:
                emit({"event": "error", "error": f"参数 {k}={v} 超出范围 [{lo}, {hi}]"})
                return
            params[k] = v
        self._strength, self._channel, self._params = strength, channel, params
        t0 = monotonic_ns()
        self._vram.render(self._strength, channel=self._channel, **params)
        render_ms = (monotonic_ns() - t0) / 1e6
        with self._wlock:
            seq, t_emit, slot = self.shm.write_frame(self._vram.read_back())
        # filter_ms > 0 就是这一帧重算了滤波（参数刚变）；0.0 才是拖拽期的常态。
        emit({"event": "params_set", "strength": self._strength, "channel": self._channel,
              "render_ms": round(render_ms, 2),
              "filter_ms": round(float(self._vram.last_filter_ms), 2),
              # 这一帧到底复用了缓存没有：`retouched is not None` 是个恒真的说法（render 成功
              # 之后它必然非空），缓存被无声绕过时也照样报 True。只有 last_filter_ms 才由执行路径约束。
              "cached": float(self._vram.last_filter_ms) == 0.0, **self._params})
        emit({"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
              "w": self.shm.w, "h": self.shm.h, "mode": "drag"})

    def _pipe_copyin(self, rgba, strength: float, radius: int = DEFAULT_RADIUS,
                     eps: float = DEFAULT_EPS, detail_gain: float = DEFAULT_DETAIL_GAIN):
        """逐帧搬运路径（对照组）：CPU numpy → H2D → 内核 → D2H → CPU numpy。

        返回 (RGBA, 各段 ms)。故意不复用输入缓冲：那是 test_frame 的缓存本体，
        改写它会让下一帧的「基图」逐帧漂走，「帧真的在换」这个证据就不可靠了。

        磨皮参数照单接收：两条臂跑同一组参数，否则 copyin 与 resident 的差值里混着算法差异。
        """
        import numpy as np

        from .ops.guided import make_tensor, retouch_t, to_numpy_chw

        seg = dict(pre=0.0, kernel=0.0, cpu_post=0.0)
        out = self._pipe_out
        if out is None or out.shape != rgba.shape:
            out = np.empty_like(rgba)
            out[:, :, 3] = 255
            self._pipe_out = out
        t = monotonic_ns()
        arr = rgba[:, :, :3].astype(np.float32) / 255.0
        tensor = make_tensor(arr, self.device)
        seg["pre"] = (monotonic_ns() - t) / 1e6
        t = monotonic_ns()
        # 这里原先写的是 radius=12, eps=6e-4 两个字面量、而且不传 detail_gain：默认值一改
        # 这条对照臂就会静默漂离开生产参数，两个臂比的就不是同一件事了
        o = retouch_t(tensor, strength=strength, radius=radius, eps=eps,
                      detail_gain=detail_gain)
        self._sync()
        seg["kernel"] = (monotonic_ns() - t) / 1e6
        t = monotonic_ns()
        out[:, :, :3] = (np.clip(to_numpy_chw(o), 0, 1) * 255).astype(np.uint8)
        seg["cpu_post"] = (monotonic_ns() - t) / 1e6
        return out, seg

    def cmd_set_device(self, p: dict):
        # 跑靶进行中整条拒绝。原来只拦"重建常驻会话"，可 self.device/self._cuda 在拦截之前
        # 就已经改写并发出了 device_set：会话还留在旧设备上服务，而 _sync() 按 self._cuda
        # 决定要不要 synchronize —— cuda 翻成 cpu 后跑靶线程的 kernel 段只剩"入队时间"，
        # 滤波与混合看起来突然变快，数据不崩但分段计时与设备标签双双失真。
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 set_device：先 bench_stop"})
            return
        self.device = p.get("device", "cpu")
        # 只有 torch 真认了这个后端才算 GPU，否则 _sync 会去调一个不存在的 API
        self._cuda = False
        if self.device.startswith("cuda"):
            try:
                import torch
                self._torch = torch
                self._cuda = torch.cuda.is_available()
            except Exception as e:
                emit({"event": "engine_warn", "warn": f"torch 不可用: {e}"})
        emit({"event": "device_set", "device": self.device, "cuda": self._cuda})
        # 已经建好的真图会话必须跟着迁移：不然“切设备”只改了个字符串，旧张量继续在
        # 原设备上服务，而所有上报都按新设备解读。重建代价实测 1.6~1.9 ms。
        if self._image_loaded and self._vram is not None \
                and str(self._vram.device) != self._effective_device():
            if self.bench is not None and self.bench.is_alive():
                # 跑靶中途重建会写花正在用的会话与缓冲，当场拒并说清原因
                emit({"event": "error", "error": "跑靶进行中，不迁移常驻会话：先 bench_stop"})
                return
            emit({"event": "engine_info", "info": f"常驻会话从 {self._vram.device} 重建到 {self._effective_device()}"})
            self._attach_pipeline(self._src_rgb)
            # 预计算产物是“这个会话这个设备上的张量”：迁完不重挂，掩膜就停在旧设备上，
            # 下一次带 channel 的渲染会直接读错/读到已释放的显存
            if self._precompute is not None:
                t_p = monotonic_ns()
                info = self._vram.load_face(self._precompute)
                emit(self._precompute_ready_event(
                    self._precompute, info,
                    # 重挂没重新算：建图与推理都是 0，不是“没测到”。这里给 0.0 而不是
                    # 缺字段，是为了让两条臂的事件形状完全一致——UI 那边一旦按必存字段读，
                    # 少一个键就会在报表上变成 undefined 而无人报错
                    build_ms=0.0, infer_ms=0.0,
                    attach_ms=round((monotonic_ns() - t_p) / 1e6, 2),
                    total_ms=round((monotonic_ns() - t_p) / 1e6, 2),
                    replayed_for="device_switch"))
            if self.shm is not None and (self.shm.w, self.shm.h) == (self._vram.w, self._vram.h):
                # 通道必须跟着会话一起迁移：不传 channel 的话，报表里 active_channel 还是 skin，
                # 而给用户补发的是一帧全图渲染——字段与实际执行不一致正是本仓最贵那个坑的形状
                self._vram.render(self._strength, channel=self._channel, **self._params)
                with self._wlock:
                    seq, t_emit, slot = self.shm.write_frame(self._vram.read_back())
                emit({"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
                      "w": self.shm.w, "h": self.shm.h, "mode": "device_switch"})

    def _effective_device(self) -> str:
        """会话真正会落在哪个设备上（要求 cuda 但没 GPU 时是 cpu，不是 cuda）。"""
        if self.device.startswith("cuda") and not self._cuda:
            return "cpu"
        return self.device

    def cmd_shutdown(self, _p: dict):
        self.stop_flag.set()
        self._quit = True
        emit({"event": "bye"})

    # ------------------------------------------------------------ 主循环
    def run(self):
        table = {"hello": self.cmd_hello, "bench_start": self.cmd_bench_start,
                 "bench_stop": lambda p: (self.stop_flag.set(), emit({"event": "bench_stopped"})),
                 "set_device": self.cmd_set_device, "shutdown": self.cmd_shutdown,
                 "load_image": self.cmd_load_image, "set_strength": self.cmd_set_strength,
                 "precompute": self.cmd_precompute}
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
