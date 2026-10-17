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
from .vram import DEFAULT_BROAD_GAIN, DEFAULT_DETAIL_GAIN, DEFAULT_EPS, DEFAULT_MID_GAIN, \
    DEFAULT_RADIUS, DEFAULT_TEXTURE_RADIUS, DEFAULT_REPAIR, LightOp, RepairOp, warm_device
from .ops.light import DB_EXPOSURE_LIMIT, DEFAULT_DB_EXPOSURE, DEFAULT_DB_RADIUS
from .ops.deform import KINDS, DeformGeometryError, check_amounts
from .ops.lut import LutError, check_amount, load_cube_file, parse_cube
from .ops.grade import DH_LIMIT, DS_LIMIT, DV_LIMIT, GradeError, check_params
from .ops.presets import PRESETS, PresetError, get_preset, preset_grade, preset_lut
# M4 导出：FORMATS/尺寸边界与落盘器全部从 export 走，命令层不掌一份格式名单（双出处）。
from .export import (DEFAULT_TILE, FORMATS, MAX_TILE, MIN_TILE, ExportSpec,
                     export_image, resample_field, write_file)

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
        self._params = dict(radius=DEFAULT_RADIUS, eps=DEFAULT_EPS,
                            texture_radius=DEFAULT_TEXTURE_RADIUS,
                            broad_gain=DEFAULT_BROAD_GAIN, mid_gain=DEFAULT_MID_GAIN,
                            detail_gain=DEFAULT_DETAIL_GAIN)
        # 消除笔（M1-4）的操作列表在引擎侧也有份：常驻会话会因换设备而重建，
        # 只存在 pipe 里的话迁完就“脸还在但修补全没了”。存的是输入（画笔 uint8），不是结果。
        # redo 栈也得有一份：不然切一次设备就把“重做”历史静默抹掉，与“撤销/重做都靠重放”矛盾。
        self._repair_ops: list = []
        self._redo_ops: list = []
        self._op_seq = 0
        # 修容层（M2-a2）在引擎侧也有一份：它跟消除笔一样是“只存输入”的图层，
        # 换设备重建会话时要能就地重放。参数（强度/带限半径）也存在引擎侧，
        # 因为新会话的默认值不等于当前会话的值。
        self._light_ops: list = []
        self._light_redo: list = []
        self._light = dict(exposure=DEFAULT_DB_EXPOSURE, radius=DEFAULT_DB_RADIUS)
        # 形变层（M2-b）：存的是三个滑块的值，单位场不存（它能从关键点重算，
        # 而关键点已经在 _precompute 里）。换设备重建时重新 build 一次，55 ms。
        self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
        # 调色层（M3-a2）：引擎侧存的是那张表本身（CPU 原件）与混合系数。
        # 表不存会话里只存在这里是不够的：常驻体积张量活在一块设备上，换设备必须重挂。
        self._lut = None
        self._lut_amount = 1.0
        # 定向层（M3-b）：引擎侧只存四个数（它不持有张量）。与调色层同一条规矩：
        # 随图清、随设备迁移重提交。
        self._grade = (0.0, 0.0, 0.0, 1.0)
        # 当前生效的内置预设名（走 path/text 或手动改定向时为 None）。它不是装饰：
        # 它决定“调色强度”要不要连带施加到定向层，也是 UI 显示“预设/手动”的唯一出处。
        self._lut_preset = None
        # 分段计时的自洽计数：子段之和超过整帧内核段的帧数（只可能是重复计时）。
        # kernel 靠减法得出并夹到 0，不记这一笔就永远看不出某段被计了两次。
        self._seg_over_frames = 0
        self._wlock = threading.Lock()   # 跑靶线程与 stdin 线程都在写同一块双缓冲
        self._strength = _clamp_strength(0.5)
        # 当前文档的源路径：导出默认导的就是这一张，而导入时只留下了像素没留下名字。
        self._doc_path: str | None = None
        self._export: threading.Thread | None = None
        self._export_args: tuple | None = None

    # ------------------------------------------------------------ 通路自检
    def cmd_hello(self, _p: dict):
        emit({"event": "ready", "protocol": PROTOCOL_VERSION, "pid": os.getpid(),
              # 内置预设清单（M3-b）：按钮上写什么字、按哪个名提交，全部由引擎说。
              # 前端抄一份名字就是双出处：资产改名后 UI 会静默拿着错名去撞拒绝。
              "presets": [{"name": k, "title": v.title} for k, v in sorted(PRESETS.items())],
              # 三个增量的硬边界也在这里报一次：滑块的行程在引擎说了为准之后才能开始渲染，
              # 不等一条 grade_done 才拿到范围（那时滑块已经错看了一轮）。
              "grade_limits": [DH_LIMIT, DS_LIMIT, DV_LIMIT],
              # M4：导出能力也由引擎说。前端抄一份格式名单或 tile 范围，就是下一轮改边界时
              # 漏改的那一处。
              "export_formats": sorted(set(FORMATS)),
              "export_tile": [MIN_TILE, MAX_TILE],
              "export_tile_default": DEFAULT_TILE})

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
        if self._export is not None and self._export.is_alive():
            # 同一条理由与换图一样：跑靶与导出同抢一块卡，两边的帧成本账单都不是那个数
            self._reject_bench("导出进行中，拒绝开跑靶：等 export_done", p.get("mode", "copy"))
            return
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
        seg = dict(synth=0.0, pre=0.0, filter=0.0, light=0.0, deform=0.0, lut=0.0,
                   grade=0.0, kernel=0.0, post_gpu=0.0, cpu_post=0.0, readback=0.0)
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
            # M2-a2：修容层也是热路径上可分离的一笔。它应当与 filter 同构：
            # 只在图层/参数变了的那一帧非 0，拖 strength 时恒为 0。不拆出来
            # 就会把 db 的开销记到 kernel 头上，而“拖滑块零重算”这条判据看不出来。
            seg["light"] = float(getattr(pipe, "last_light_ms", 0.0) or 0.0)
            # M2-b：形变与修容不同，它每帧真在跑（grid_sample），所以它不是“重算次数”
            # 而是“每帧成本”。零推理那条靠 deform_builds 不增来证，不靠这一段为 0。
            seg["deform"] = float(getattr(pipe, "last_deform_ms", 0.0) or 0.0)
            # M3-a2：调色与形变同构，也是每帧真在跑的一笔（grid_sample 3d）；它不是
            # “重算次数”而是“每帧成本”。不拆出来就会把它记到 kernel 头上，而
            # “挂上 LUT 后拖磨皮滑块仍零重算”那条判据就看不出是谁在花钱。
            seg["lut"] = float(getattr(pipe, "last_lut_ms", 0.0) or 0.0)
            # M3-b：肤色定向与调色同构（每帧真在跑的逐点内核，只是它不拿表而拿公式）。
            # 不拆出来，拖那三个滑块时花的 1.3 ms/帧就会全部记到 kernel 头上，而
            # “定向不作废磨皮缓存”与“定向每帧真跑了”两条判据都看不出是谁在花钱。
            seg["grade"] = float(getattr(pipe, "last_grade_ms", 0.0) or 0.0)
            # kernel 是“整段减去五个子段”，减法夹到 0 就看不出重复计时：子段之和超过整段
            # 只可能是某段被计了两次或计时嵌套了。当场记一笔，由 bench_done 说话——
            # 一个永远非负、越界也不报的数不是一个判据。
            seg_sum = seg["filter"] + seg["light"] + seg["deform"] + seg["lut"] + seg["grade"]
            if seg_sum - whole > 0.5:
                self._seg_over_frames += 1
            seg["kernel"] = max(whole - seg_sum, 0.0)
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
        acc = dict(synth=0.0, pre=0.0, filter=0.0, light=0.0, deform=0.0, lut=0.0,
                   grade=0.0, kernel=0.0, post_gpu=0.0, cpu_post=0.0, readback=0.0,
                   shm=0.0, notify=0.0)
        # 重算次数：拖拽期零推理的直接证据。只要这个数不是 1（或 0），缓存就没真的生效，
        # 而按均值报 filter 会把它藏起来（600 帧里重算一次只有 0.0075 ms/帧）。
        refilters = 0
        # 修容层同一个口径：600 帧拖滑块期间 relight_frames 应当是 0，
        # 不为 0 就是 db 缓存没命中（键算错了），而均值会把它洗掉。
        relights = 0
        # M3-a2：调色是逐帧固定成本，没有“命中缓存”这一说。它只用来防“挂了一层却没跑”：
        # 表挂上且强度非 0 时它必须等于跑靶帧数，否则那一层只存在于上报里。
        lut_frames = 0
        # M3-b：定向也是逐帧固定成本（点火时）。与 lut 同一个用途：防“设了参数却没跑”。
        grade_frames = 0

        def snapshot(done: int) -> dict:
            return {k: round(v / max(done, 1), 3) for k, v in acc.items()}

        pipe = (self._vram if mode == "image_stream"
                else self._open_vram(shm.w, shm.h) if mode == "pipeline_resident" else None)
        # M2-b：拖 600 帧滑块期间一次 TPS 也不许解。deform_builds 只在 build_deform
        # 里递增，而 build_deform 只由 cmd_deform 触发——跑靶不碰它。取开头与结尾
        # 两个快照而不是只取结尾：只取结尾的话，“中途重解了三次但开头就是 3”看不出来。
        builds_at_start = int(getattr(pipe, "deform_builds", 0)) if pipe is not None else 0
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
            if seg.get("light", 0.0) > 0:
                relights += 1
            if seg.get("lut", 0.0) > 0:
                lut_frames += 1
            if seg.get("grade", 0.0) > 0:
                grade_frames += 1
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
              "relight_frames": relights,
              "relight_ms_total": round(acc["light"], 2),
              "deform_ms_total": round(acc["deform"], 2),
              "deform_builds": (int(getattr(pipe, "deform_builds", 0)) - builds_at_start
                                if pipe is not None else 0),
              # M3-a2：调色是逐帧固定成本（不像 filter/light 有缓存命中），所以它没有
              # “重算次数”可证，只有“每帧真跑了多少帧”：挂上表且强度非 0 时它应当等于
              # frames，而 lut 均值为 0 就是“挂了一层却没跑”的当场证据。
              "lut_ms_total": round(acc["lut"], 2),
              "lut_frames": lut_frames,
              "grade_ms_total": round(acc["grade"], 2),
              "grade_frames": grade_frames,
              # 图层状态与每帧分段不能同名（上一版 `"light": dict(self._light)` 就是被
              # snapshot 里的同名字段吃掉的）。取局部 pipe 而不是 self._vram：后者会被
              # 别的命令顶掉，报的就不是刚才那 600 帧的服务者。
              "lut_state": dict(source=(pipe.lut.source if pipe is not None and pipe.lut else None),
                                size=(pipe.lut.size if pipe is not None and pipe.lut else 0),
                                amount=float(pipe.lut_amount) if pipe is not None else None,
                                lit=bool(pipe.has_lut()) if pipe is not None else False,
                                bytes_lut=pipe.lut_resident_bytes() if pipe is not None else 0),
              # M3-b：定向层状态与 lut_state 同构（不同名、不吃 snapshot 的同名键）。
              # dh/ds/dv/amount 取自局部 pipe：报的就是刚才那 600 帧真正在用的那组数。
              "grade_state": dict(dh=(pipe.grade_params[0] if pipe is not None else 0.0),
                                  ds=(pipe.grade_params[1] if pipe is not None else 0.0),
                                  dv=(pipe.grade_params[2] if pipe is not None else 0.0),
                                  amount=float(pipe.grade_amount) if pipe is not None else 1.0,
                                  lit=bool(pipe.has_grade()) if pipe is not None else False,
                                  bytes_grade=(pipe.grade_resident_bytes()
                                               if pipe is not None else 0)),
              # 分段不自洽的帧数：某段被重复计时时会在这里非 0，而不是表上看不出来
              "seg_over_frames": int(self._seg_over_frames),
              "params": dict(self._params),
              # 图层状态与每帧分段不能同名。上一版 `"light": dict(self._light)` 写在
              # `**snapshot()` 前面，而 snapshot 里就有同名的每帧 ms——字典字面量后写的
              # 覆盖先写的，于是上报里的 light 永远是那个毫秒数，曝光/半径根本送不出来，
              # 而且报表看起来完全自洽。M2-b 的 deform 撞上了同一条，一起改。
              "light_state": dict(self._light),
              "deform_state": dict(self._deform),
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
            # 会话新建在另一个设备上：旧张量全在那边，这里按存下的画笔重放一遍。
            # 不重放就是“会话迁了、图层没迁”，与 M1-3a 那个“会话在 CPU 上跑却标 cuda”同形。
            if self._repair_ops:
                pipe.set_repair_ops(self._repair_ops, self._redo_ops)
            # 参数先于图层：新会话的 exposure 默认值不等于用户当前拖到的值，
            # 先挂图层再改参数会白跑一次 db（而且上报里的 exposure 与实际算的不是一个数）
            pipe.light_exposure = float(self._light["exposure"])
            pipe.light_radius = int(self._light["radius"])
            if self._light_ops:
                pipe.set_light_ops(self._light_ops, self._light_redo)
            # 形变层：单位场不存只重解（一次 55 ms，换设备本来就是重操作）。
            # 关键点不在（没 precompute）时不能默默建不起来：那会“迁了会话、
            # 滑块还在 0.6 但画面不动”，而事件里看不出异常。上一版这段只有 if、
            # 没有 else，注释里写的担心恰好就是代码缺的那一半。
            if self._deform["built"]:
                if self._precompute is None:
                    emit({"event": "engine_warn",
                          "warn": "会话已迁到新设备，但没有关键点可重建形变层，已整层清除"})
                    self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
                    self._emit_deform_state("invalidate", reason="没有关键点可重建单位场")
                else:
                    # 不补帧：调用方（换设备那一条）紧后就自己渲染并写 shm，
                    # 而会话刚迁移时 _write_current_frame 抱异常会把整个迁移打断
                    self._rebuild_deform_for_landmarks(self._precompute, write_frame=False)
            # 调色层：表与像素位置无关，重挂只是把同一份原件再上一次显存（33³ 实测 428 KB）。
            # 不重挂就是“会话迁了、调色没迁”：新会话里 lut is None，屏幕回到未调色，
            # 而宿主侧 status.lut 还停在上一条 payload——上报与实际双向错配。
            if self._lut is not None:
                try:
                    pipe.set_lut(self._lut, self._lut_amount)
                    self._lut_amount = float(pipe.lut_amount)
                except (LutError, RuntimeError, ValueError) as e:
                    emit({"event": "engine_warn",
                          "warn": f"新会话重挂调色层失败，已整层清除（{type(e).__name__}）：{e}"})
                    self._lut = None
                    self._lut_amount = 1.0
            # 定向层（M3-b）：它不持有张量，所以“重挂”就是把同一组数重新提交一次。
            # 不提交就是“会话迁了、肤色滑块还在宿主侧的 0.6 但画面不动”——lut 上面
            # 那段注释写的担心，在这一层一模一样。
            if self._grade != (0.0, 0.0, 0.0, 1.0):
                try:
                    pipe.set_grade(self._grade[0], self._grade[1], self._grade[2],
                                   amount=self._grade[3])
                    self._grade = tuple(pipe.grade_params) + (float(pipe.grade_amount),)
                except (GradeError, RuntimeError, ValueError) as e:
                    emit({"event": "engine_warn",
                          "warn": f"新会话重提交肤色定向失败，已整层清除（{type(e).__name__}）：{e}"})
                    self._grade = (0.0, 0.0, 0.0, 1.0)
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
        # 导出线程正拿着上一张图的笔迹与关键点在跑满幅：此时换图会把“当前文档”
        # 这张纸从它脚下抽掉，而它报出去的 skipped 里写的是旧文档。
        if self._export is not None and self._export.is_alive():
            emit({"event": "error", "error": "导出进行中，拒绝换图：等 export_done"})
            return
        t0 = monotonic_ns()
        try:
            d = load_rgb(p["path"], int(p.get("max_px") or PROXY_PIXELS))
        except Exception as e:
            emit({"event": "error", "error": f"导入失败({type(e).__name__}): {e}"})
            return
        self._doc_path = str(p["path"])      # 导出默认目标；只有导成功才记账
        shm = self._ensure_shm(d.w, d.h)
        # 旧图的预计算产物对新图没有任何意义（尺寸/内容都变了），先清空；
        # 不清的话下一个请求会拿到上一张脸的掩膜，那比没有掩膜更坑。
        self._precompute = None
        self._precompute_backend = None
        self._channel = None
        # 上一张图的画笔坐标对新图没有任何意义（与旧掩膜同一条规矩），先清空
        self._repair_ops = []
        self._redo_ops = []
        self._op_seq = 0
        self._light_ops = []
        self._light_redo = []
        # 形变层也得跟着图走：上一张脸的单位场对这一张脸没有任何意义
        self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
        # 调色层也随文档走。一张 .cube 是“这一张照片的调色”，不是引擎全局偏好：
        # 留着旧表就是“导入第二张照片一上来就带着第一张的色调”，那是静默错配。
        # （与磨皮参数不同：radius/增益是“我习惯怎么磨”的全局默认，而表是作品的一部分。）
        self._lut = None
        self._lut_amount = 1.0
        # 定向层也随文档走：上一张照片调好的肤色窗口，对这一张不是“预设”而是误调。
        self._grade = (0.0, 0.0, 0.0, 1.0)
        self._lut_preset = None
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
              # M2-a：首帧那一笔里“分带”与“重组”各占多少。两者混在一个数里就看不出
              # 分层缓存有没有价值（分带贵、重组便宜）。
              "first_frame_bands_ms": round(float(pipe.last_bands_ms), 2),
              # 零推理换来的显存代价必须能看见，不能只报快了多少
              "bytes_filter": pipe.filter_resident_bytes(),
              "bytes_bands": pipe.bands_resident_bytes(),
              # 修容层在导入后必然为空（换图已清），这个数报 0 本身就是“没图上一张的笔迹”的证据
              "bytes_light": pipe.light_resident_bytes(),
              "bytes_deform": pipe.deform_resident_bytes(),
              # 刚导完图时它必须是 0：预热会话那张临时表不能让真会话继承（不然这里会
              # 多报 428 KB，而用户一张预设也没点）
              "bytes_lut": pipe.lut_resident_bytes(),
              # M3-b：定向层在导入后也必须是零。宿主靠这一份快照摆滑块，不留它就只能
              # 把上一张图的肤色参数继续显示成“已调”（与 bytes_lut=0 同一条理由）。
              "grade_state": dict(dh=float(pipe.grade_params[0]), ds=float(pipe.grade_params[1]),
                                  dv=float(pipe.grade_params[2]), amount=float(pipe.grade_amount),
                                  lit=bool(pipe.has_grade()),
                                  bytes_grade=int(pipe.grade_resident_bytes())),
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
        # 形变层是例外：它的单位场就是从这批关键点解出来的，关键点一走它就是
        # 无源之水（M2-b 审查项 2，口径见 _rebuild_deform_for_landmarks）。
        self._rebuild_deform_for_landmarks(pc)

    def _rebuild_deform_for_landmarks(self, pc, *, write_frame: bool = True) -> None:
        """关键点更新后重建已常驻的形变层：滑块值保留，单位场跟着新几何走。

        上一版这里什么都不做，于是“precompute(template) → deform set slim=0.9 →
        装上 mediapipe 再 precompute(mediapipe)”之后 cmd_deform 看见 built=True 就
        不再重解：形变还在用肤色盒模板的几何瘦这一张脸，而 deform_done 把
        landmark_backend 报成 mediapipe——上报与画面双向错配，而且是“看不出错”那一类。
        库层 vram.clear_face 的注释早就写明“关键点一走单位场就是无源之水”，但命令层
        没接线，所以它一直是没人走的死代码。

        先清再建：新后端解不出层时，旧几何绝不能继续服务。滑块值不重置：换后端是
        “同一张脸量得更准”，不是“用户改了主意”，把用户的作品按引擎内部事件归零是
        另一种静默降级。解不出时发 action=invalidate，UI 那条必须把滑块跟着归零。
        """
        if not self._deform["built"]:
            return
        amounts = dict(self._deform["amounts"])
        self._vram.clear_deform()
        self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
        if pc.backend == "synthetic":
            emit({"event": "engine_warn",
                  "warn": "关键点后端换成 synthetic（网格占位几何），形变层已整层清除"})
            self._emit_deform_state("invalidate", reason="synthetic 占位几何不能按脸形语义取点",
                                    dropped_amounts=amounts)
            return
        try:
            built = self._vram.build_deform(pc.landmarks)
            state = self._vram.set_deform_amounts(amounts)
        except (DeformGeometryError, ValueError, RuntimeError) as e:
            self._vram.clear_deform()
            emit({"event": "engine_warn",
                  "warn": f"用新关键点重建形变层失败，已整层清除：{type(e).__name__}: {e}"})
            self._emit_deform_state("invalidate", reason=f"重建失败：{e}",
                                    dropped_amounts=amounts)
            return
        self._deform = dict(amounts=dict(state["amounts"]), built=True)
        # 层真的变了（有非零滑块）就必须补一帧：不补就是“引擎已按新几何形变，
        # 屏幕还是旧像素”，而 precompute_ready 里看不出画面错开
        render_ms = 0.0
        fr = None
        if write_frame and bool(state["lit"]) and self.shm is not None \
                and (self.shm.w, self.shm.h) == (self._vram.w, self._vram.h):
            try:
                fr = self._write_current_frame("deform")
                render_ms = fr.pop("render_ms")
            except Exception as e:
                # 补帧失败不能把整条 precompute 拖死（预计算本身已成立），但必须说清
                # “引擎已按新几何重建形变层、屏幕还是旧帧”这件事
                emit({"event": "engine_warn", "warn": f"形变层重建后补帧失败：{e}"})
        # 事件次序与 cmd_deform 一致：先报状态、后报帧。反过来会让“等 deform_done”的
        # 调用方把中间那条 frame 事件吞掉，下一帧就再也等不到（本轮真踩过）
        self._emit_deform_state("rebuild", build=built, render_ms=render_ms)
        if fr is not None:
            emit(fr)

    def _emit_deform_state(self, action: str, *, build: dict | None = None,
                           render_ms: float = 0.0, total_ms: float = 0.0,
                           reason: str | None = None,
                           dropped_amounts: dict | None = None) -> None:
        """deform_done 只在这里组装一次（cmd_deform 与关键点重建/清除三条臂共用）。

        与 _precompute_ready_event 同一条理由：两处各写一份，漂的方向永远是“后接的那
        条臂少一个字段”，而 TS 把字段声明成必存——谎报发生在 JSON 边界上，编译期抓不到。
        """
        pipe = self._vram
        ev = {"event": "deform_done", "action": action,
              "amounts": dict(pipe.deform_amounts),
              "built": bool(pipe.deform_units),
              "lit": bool(pipe.has_deform()),
              "deform_builds": int(pipe.deform_builds),
              "deform_ms": round(float(pipe.last_deform_ms), 2),
              "bytes_deform": int(pipe.deform_resident_bytes()),
              "render_ms": round(float(render_ms), 2),
              "total_ms": round(float(total_ms), 2),
              # 关键点出自哪个后端必须原样上报：template 是“按肤色盒摆的模板”，
              # 贴合度不验收。UI 拿不到这个数就会把模板拟合当成真检测给用户看。
              "landmark_backend": (self._precompute.backend if self._precompute else None),
              "device": str(pipe.device), "strength": self._strength}
        if build is not None:
            ev["build"] = build
        if reason:
            ev["reason"] = reason
        if dropped_amounts:
            # 失效那一条要让用户看到“刚才拖的是多少”：只报 lit=false 的话，滑块弹回
            # 零像出了 bug，而实际是后端换了
            ev["dropped_amounts"] = dict(dropped_amounts)
        emit(ev)

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
        # 与 max_px 同一类风险。texture_radius 还要多一层：它决定线性高通的窗口，同样进分配。
        # 下界不是随手取的：eps=0 会让 `a = var/(var+eps)` 在平坦皮区算 0/0 = NaN（产品档实测
        # 402795 个子像素为 NaN）。这份 NaN 会被写进常驻缓存，而 `(1-0)*img + 0*NaN` 仍是 NaN
        # （IEEE 里 0×NaN = NaN），于是 strength=0 与解码原图差到 255 LSB —— 验收口径③
        # 整段会话被打穿。radius=0 不产 NaN，但滑块彻底空操作（实测 s=0.5 与原图 0 处不同），
        # 产品上没有任何意义，一并卡掉。texture_radius=0 同理：blur 就是原图、tex 全零，
        # “肌理保留”滑块当场变成空控件，所以协议层要 ≥1（库层仍允许 0，给对拍用）。
        params = dict(self._params)
        for k, lo, hi in (("radius", 1, 256), ("eps", 1e-6, 1.0), ("texture_radius", 1, 32),
                          ("detail_gain", 0.0, 2.0), ("mid_gain", 0.0, 2.0),
                          ("broad_gain", 0.0, 2.0)):
            if p.get(k) is None:
                continue
            try:
                v = int(p[k]) if k in ("radius", "texture_radius") else float(p[k])
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"参数 {k} 非法：{p[k]!r}"})
                return
            if v != v:          # NaN 比大小永远是 False，不先拦就会被当成“越界”报个误导的区间错
                emit({"event": "error", "error": f"参数 {k} 不是有限数：{p[k]!r}"})
                return
            if not lo <= v <= hi:
                emit({"event": "error", "error": f"参数 {k}={v} 超出范围 [{lo}, {hi}]"})
                return
            params[k] = v
        self._strength, self._channel, self._params = strength, channel, params
        # 出帧走与 cmd_inpaint 同一个入口：以前这里是一份手写的“render → 锁内写 shm → emit frame”，
        # 而写多份的下场已经受过（上一轮就是其中一份漏了尺寸守卫）。
        fr = self._write_current_frame("drag")
        render_ms = fr.pop("render_ms")
        # filter_ms > 0 就是这一帧重算了滤波（参数刚变）；0.0 才是拖拽期的常态。
        emit({"event": "params_set", "strength": self._strength, "channel": self._channel,
              "render_ms": render_ms,
              "filter_ms": round(float(self._vram.last_filter_ms), 2),
              # M2-a 分层：bands_ms > 0 才是这一帧真重跑了 guided 分带。拖“匀肤/细节/肌理”
              # 三个滑块时 filter_ms 不为 0 而 bands_ms = 0，说明只重跑了逐点乘加——
              # 分带/重组两层缓存是否生效，这是唯一的直接证据。
              "bands_ms": round(float(self._vram.last_bands_ms), 2),
              # 这一帧到底复用了缓存没有：`retouched is not None` 是个恒真的说法（render 成功
              # 之后它必然非空），缓存被无声绕过时也照样报 True。只有 last_filter_ms 才由执行路径约束。
              # 名字叫 filter_cached 不叫 cached：库层字典里那条 cached 说的是“本层真重算了”，
              # 两件事共用一个键名时，字典字面量后写的会静默吃掉先写的。
              "filter_cached": float(self._vram.last_filter_ms) == 0.0,
              # M2-a2：拖磨皮滑块时这一笔应当恒为 0（两份 db 结果都命中常驻）。
              # 不为 0 就是修容层把磨皮那条零推理热路径拖回了重算——两个数得分开报才能看见。
              "light_ms": round(float(self._vram.last_light_ms), 2), **self._params})
        emit(fr)

    # ------------------------------------------------------------ 消除笔（M1-4）
    def _write_current_frame(self, mode: str) -> dict:
        """把当前会话渲染一帧并写 shm，返回 frame 事件字段（带 render_ms，调用方 pop）。

        set_strength / inpaint 都走这一个出口；load_image 也渲染+写 shm，但它面对的是刚刚
        新建的 shm 与一次性分段计时（shm_ms/attach_ms/first_frame_ms），所以单独一段——
        不并进来不等于可以不要守卫，尺寸不配就在这里拦一次：上一轮“三份里有一份漏守卫”
        的下场已经受过。
        """
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            raise RuntimeError(f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                               f"!= 会话 {self._vram.w}x{self._vram.h}：不许把会话尺寸的帧写进别人的槽")
        t0 = monotonic_ns()
        self._vram.render(self._strength, channel=self._channel, **self._params)
        render_ms = (monotonic_ns() - t0) / 1e6
        with self._wlock:
            seq, t_emit, slot = self.shm.write_frame(self._vram.read_back())
        return {"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
                "w": self.shm.w, "h": self.shm.h, "mode": mode, "render_ms": round(render_ms, 2)}

    def cmd_inpaint(self, p: dict):
        """消除笔：一次事件（松手）算一次修补；拖滑块期间不重算也不重上传。

        与 M1-3c 同一原则：一次性成本与逐帧成本分开报。这里的一次性成本 =
        RLE 解码 + 羽化 + 裁块修补 + 滤波重放；之后的拖动只读现成的 repair_base。
        """
        action = p.get("action", "add")
        if action not in ("add", "undo", "redo", "clear"):
            emit({"event": "error", "error": f"未知 inpaint action: {action}"
                  f"（可用：add/undo/redo/clear）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                  f"!= 会话 {self._vram.w}x{self._vram.h}，请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            # 与 set_strength 同一条守卫：跑靶线程在写 frame_gpu，这里也写同一块
            emit({"event": "error", "error": "跑靶进行中，拒绝 inpaint：先 bench_stop"})
            return
        t_start = monotonic_ns()
        info_add = {}
        if action == "add":
            # 先全部校验、再一次性提交（与 cmd_set_strength 同一条铁律）：
            # 被拒绝的命令必须整条不留痕，不能“图层加了一半、参数改了”那种中间态。
            import numpy as np

            from .ops.inpaint import feather_np, mask_from_rle

            rle = p.get("rle")
            if not isinstance(rle, list):
                emit({"event": "error", "error": "inpaint add 缺 rle：应为 [[y,x,len,value255], …]"
                      "（从代理帧坐标采集，尺寸就是 shm_ready 的 w/h）"})
                return
            if len(rle) == 0:
                emit({"event": "error", "error": "rle 为空：这一笔一个像素也没盖到，不该发这条命令"})
                return
            h, w = self._vram.h, self._vram.w
            try:
                hard = mask_from_rle(rle, h, w)
            except (ValueError, TypeError) as e:
                emit({"event": "error", "error": f"rle 非法，整条拒绝：{e}"})
                return
            feather = int(p.get("feather", 2))
            if not 0 <= feather <= 8:
                emit({"event": "error", "error": f"feather={feather} 超出范围 [0, 8]"})
                return
            params = dict(DEFAULT_REPAIR)
            for k, lo, hi, cast in (("smooth_iters", 0, 4, int), ("refine_iters", 0, 32, int),
                                    ("kappa", 1e-3, 1.0, float), ("pad", 0, 256, int),
                                    ("grow", 1.0, 8.0, float)):
                if p.get(k) is None:
                    continue
                try:
                    v = cast(p[k])
                except (TypeError, ValueError):
                    emit({"event": "error", "error": f"参数 {k} 非法：{p[k]!r}"})
                    return
                if not lo <= v <= hi:
                    emit({"event": "error", "error": f"参数 {k}={v} 超出范围 [{lo}, {hi}]"})
                    return
                params[k] = v
            backend = p.get("backend", "builtin")
            if backend != "builtin":
                # 不许静默降级（与 face.MediaPipeFace 同一条规矩）：请求真模型而权重不在，
                # 就报错说清缺什么，绝不“退成内置扩散然后报一个修补成功”。
                # （lama 在 ops 包里：上一版写成 `from . import lama`，这条守卫自己先报
                # ImportError，文案全丢——守卫也要能被测到才算守卫。）
                from .ops import lama

                emit({"event": "error", "error": lama.missing_reason(backend)})
                return
            t_dec = monotonic_ns()
            soft = feather_np(hard, feather) if feather else (hard.astype(np.float32))
            weight = np.round(np.clip(soft, 0.0, 1.0) * 255.0).astype(np.uint8)
            if int((weight > 0).sum()) == 0:
                emit({"event": "error", "error": "羽化后覆盖度归零：画笔太小或 feather 与坐标不匹配"
                      "（会话为代理帧尺寸，得用代理帧坐标而不是原图坐标）"})
                return
            decode_ms = (monotonic_ns() - t_dec) / 1e6
            # 号只在提交成功后占：add_repair 内部现在“全算完才写回”，真失败时图层
            # 一笔也不会多出来，把自增放在前面会白白跳号
            op = RepairOp(op_id=self._op_seq + 1, weight=weight, params=params)
            info = self._vram.add_repair(op)
            self._op_seq = op.op_id
            info_add = {"op_id": op.op_id, "decode_ms": round(decode_ms, 2),
                        "backend": backend, "feather": feather, "params": dict(params),
                        "rle_runs": len(rle)}
        elif action == "undo":
            info = self._vram.undo_repair()
            if info is None:
                emit({"event": "error", "error": "没有可撤销的消除笔操作"})
                return
        elif action == "redo":
            info = self._vram.redo_repair()
            if info is None:
                emit({"event": "error", "error": "没有可重做的消除笔操作"})
                return
        else:
            info = self._vram.clear_repair()
        # 引擎侧那份列表必须跟着会话走：不同步的话下一次换设备会重放出旧图层
        self._repair_ops = list(self._vram.repair_ops)
        self._redo_ops = list(self._vram.redo_ops)
        fr = self._write_current_frame("repair")
        render_ms = fr.pop("render_ms")
        emit({"event": "inpaint_done", "action": action, **info, **info_add,
              "filter_ms": round(float(self._vram.last_filter_ms), 2),
              "bands_ms": round(float(self._vram.last_bands_ms), 2),
              "filter_cached": float(self._vram.last_filter_ms) == 0.0,
              "repair_ms": info["repair_ms"], "render_ms": render_ms,
              "total_ms": round((monotonic_ns() - t_start) / 1e6, 2),
              "device": str(self._vram.device), "strength": self._strength})
        emit(fr)

    def _light_params_or_reject(self, p: dict):
        """从命令里取修容层参数，全部校验通过才返回；失败时自己发 error 并返 None。

        为什么单独拆出来：add 与 params 两条臂都得能带 exposure/radius。上一版只在
        params 里处理，add 带了就直接**静默忽略**——手工跑一条 add 带 radius=6 时
        上报里仍是默认的 24，而 exposure 默认值恰好也是 0.6，整个事件看不出任何异常。
        静默吞掉一个参数比报错难查十倍。
        """
        got = {}
        for k, lo, hi in (("exposure", -DB_EXPOSURE_LIMIT, DB_EXPOSURE_LIMIT),
                          ("radius", 0, 256)):
            if p.get(k) is None:
                continue
            try:
                v = float(p[k]) if k == "exposure" else int(p[k])
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"参数 {k} 非法：{p[k]!r}"})
                return None
            if not v == v or abs(v) == float("inf"):
                emit({"event": "error", "error": f"参数 {k} 不是有限数：{p[k]!r}"})
                return None
            if not lo <= v <= hi:
                emit({"event": "error", "error": f"参数 {k}={v} 超出范围 [{lo}, {hi}]"})
                return None
            got[k] = v
        return got

    def cmd_light(self, p: dict):
        """修容笔（M2-a2）：一次事件（松手/改完参数）算一次场；拖磨皮滑块期间不重算。

        与消除笔同一套事件调度、同一条铁律：先全量校验、后一次性提交，被拒绝的命令
        整条不留痕（不能“图层加了一笔、参数改了、场还是旧的”那种中间态）。
        """
        action = p.get("action", "add")
        if action not in ("add", "undo", "redo", "clear", "params"):
            emit({"event": "error", "error": f"未知 light action: {action}"
                  f"（可用：add/undo/redo/clear/params）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x{getattr(self.shm, 'h', '?')} "
                  f"!= 会话 {self._vram.w}x{self._vram.h}，请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 light：先 bench_stop"})
            return
        t_start = monotonic_ns()
        info_add: dict = {}
        if action == "params":
            # 参数也得“先校验后写”：一半一半会留下一张用旧曝光算出来、但上报写着新曝光的帧
            got = self._light_params_or_reject(p)
            if got is None:
                return
            if not got:
                emit({"event": "error", "error": "light params 什么也没给：至少要有 exposure 或 radius"})
                return
            self._light = dict(self._light, **got)
            info = self._vram.set_light_params(self._light["exposure"], self._light["radius"])
            info_add = {"params": dict(self._light)}
        elif action == "add":
            import numpy as np

            from .ops.inpaint import feather_np, mask_from_rle

            rle = p.get("rle")
            if not isinstance(rle, list) or not rle:
                emit({"event": "error", "error": "light add 缺 rle 或 rle 为空："
                      "应为 [[y,x,len,value255], …]，从代理帧坐标采集"})
                return
            h, w = self._vram.h, self._vram.w
            try:
                hard = mask_from_rle(rle, h, w)
            except (ValueError, TypeError) as e:
                emit({"event": "error", "error": f"rle 非法，整条拒绝：{e}"})
                return
            try:
                sign = int(p.get("sign", 1))
            except (TypeError, ValueError):
                emit({"event": "error", "error": f"sign 非法：{p.get('sign')!r}（需 +1 减淡 / -1 加深）"})
                return
            if sign not in (-1, 1):
                emit({"event": "error", "error": f"sign={sign} 非法：只能是 +1（减淡）或 -1（加深）"})
                return
            feather = int(p.get("feather", 2))
            if not 0 <= feather <= 8:
                emit({"event": "error", "error": f"feather={feather} 超出范围 [0, 8]"})
                return
            t_dec = monotonic_ns()
            soft = feather_np(hard, feather) if feather else hard.astype(np.float32)
            weight = np.round(np.clip(soft, 0.0, 1.0) * 255.0).astype(np.uint8)
            if int((weight > 0).sum()) == 0:
                emit({"event": "error", "error": "羽化后覆盖度归零：画笔太小或坐标不匹配"
                      "（会话为代理帧尺寸，得用代理帧坐标而不是原图坐标）"})
                return
            decode_ms = (monotonic_ns() - t_dec) / 1e6
            # 带不带参数都得过同一道校验：静默忽略比拒绝坏得多
            got = self._light_params_or_reject(p)
            if got is None:
                return
            op = LightOp(op_id=self._op_seq + 1, weight=weight, sign=sign)
            prev_light = dict(self._light)
            if got:
                # 参数先于建层：两者在同一条事件里，提交后帧与上报必须同时是新参数的
                self._light = dict(self._light, **got)
                self._vram.set_light_params(self._light["exposure"], self._light["radius"])
            try:
                info = self._vram.add_light(op)
            except Exception as e:
                # 回滚必须成对。上一版只 except ValueError 且不回滚参数：任何
                # RuntimeError（先 load_rgb_u8）、非有限场、显存 OOM 都会留下“参数已是新的、
                # 图层一笔没加、事件一条没发”的半应用状态——上报里曝光变了而画面按旧曝光
                # 渲染，Rust 侧 status.light 还停在上一条 payload。cmd_set_strength 已为同一个
                # 形状付过钱：“先全量校验、后一次性提交”不是注释，得真的回得去。
                self._light = prev_light
                try:
                    self._vram.set_light_params(prev_light["exposure"], prev_light["radius"])
                except Exception:      # 回滚本身再抛就得当场说清，不能留个“看起来已回滚”的状态
                    emit({"event": "engine_warn",
                          "warn": f"修容回滚失败，参数层已不可信，请重新导图：{type(e).__name__}"})
                emit({"event": "error",
                      "error": f"修容被拒，参数一并回滚（{type(e).__name__}）：{e}"})
                return
            self._op_seq = op.op_id
            info_add = {"op_id": op.op_id, "sign": sign, "decode_ms": round(decode_ms, 2),
                        "rle_runs": len(rle), "feather": feather, "params": dict(self._light)}
        elif action == "undo":
            info = self._vram.undo_light()
            if info is None:
                emit({"event": "error", "error": "没有可撤销的修容笔"})
                return
        elif action == "redo":
            info = self._vram.redo_light()
            if info is None:
                emit({"event": "error", "error": "没有可重做的修容笔"})
                return
        else:
            info = self._vram.clear_light()
        # 引擎侧那份列表必须跟着会话走：不同步的话下一次换设备会重放出旧图层
        self._light_ops = list(self._vram.light_ops)
        self._light_redo = list(self._vram.light_redo)
        fr = self._write_current_frame("light")
        render_ms = fr.pop("render_ms")
        # 显存账单在渲染之后才算：建层那一刻两份 db 结果还是空的，在那里报会少算
        # 两个产品档各 6.5 MiB——“零重算”换来的显存代价藏不得
        info["bytes_light"] = self._vram.light_resident_bytes()
        emit({"event": "light_done", "action": action, **info, **info_add,
              "light_ms": round(float(self._vram.last_light_ms), 2),
              "filter_ms": round(float(self._vram.last_filter_ms), 2),
              "bands_ms": round(float(self._vram.last_bands_ms), 2),
              "filter_cached": float(self._vram.last_filter_ms) == 0.0,
              "render_ms": render_ms,
              "total_ms": round((monotonic_ns() - t_start) / 1e6, 2),
              "device": str(self._vram.device), "strength": self._strength})
        emit(fr)

    def cmd_deform(self, p: dict):
        """五官微调（M2-b）：瘦脸 / 大眼 / 小下巴三个滑块。

        与修容笔的区别：它不是逐笔图层而是一个“参数层”——滑块值就是全部状态；
        撤销/重做属于产品闭环（M5）统一做，不在这里先做三份中的一份。

        铁律与 light 同构：先全量校验、后一次性提交。建层需要 478 点关键点，
        而 **synthetic 后端给的是网格占位几何**：拿它按脸形语义取点会搬到完全无关的
        位置上，而且画面“真的动了”——看不出错。所以整条拒绝并说清原因。
        """
        action = p.get("action", "set")
        if action not in ("set", "clear"):
            emit({"event": "error", "error": f"未知 deform action: {action}（可用：set/clear）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x"
                  f"{getattr(self.shm, 'h', '?')} != 会话 {self._vram.w}x{self._vram.h}，"
                  "请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 deform：先 bench_stop"})
            return
        t_start = monotonic_ns()
        build_info: dict = {}
        prev_amounts = dict(self._deform["amounts"])
        if action == "clear":
            self._vram.clear_deform()
            self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
        else:
            try:
                # 参数先于建层：越界值不该先付一次 55 ms 解算再被拒
                got = check_amounts(p.get("amounts"))
            except ValueError as e:
                emit({"event": "error", "error": f"deform 被拒，整条拒绝：{e}"})
                return
            if not self._deform["built"]:
                pc = self._precompute
                if pc is None:
                    emit({"event": "error", "error":
                          "形变需要先 precompute：没有 478 点关键点就不知道把哪里搬到哪里"})
                    return
                if pc.backend == "synthetic":
                    emit({"event": "error", "error":
                          "形变拒绝 synthetic 后端的关键点：它们是网格占位几何、不是脸形，"
                          "按点号取“左脸轮廓”会搬到无关位置。请装 mediapipe 插件后端"})
                    return
                try:
                    built = self._vram.build_deform(pc.landmarks)
                except (DeformGeometryError, ValueError, RuntimeError) as e:
                    emit({"event": "error", "error": f"形变建层失败，整条拒绝：{e}"})
                    return
                self._deform["built"] = True
                build_info = {"build": built}
            try:
                info = self._vram.set_deform_amounts(got)
            except ValueError as e:
                emit({"event": "error", "error": f"deform 被拒，整条拒绝：{e}"})
                return
            self._deform["amounts"] = dict(info["amounts"])
        try:
            fr = self._write_current_frame("deform")
        except Exception as e:
            # 滑块值已写进常驻层而渲染抛了（apply_deform 的非有限值护栏、会话尺寸不配）：
            # 必须把滑块值退回上一条已证能出帧的状态，否则“层里留着新值而屏幕停在旧帧”，
            # 而下一条 set 会拿这个坏场再跑一次。回滚后补一帧把画面与层对齐。
            self._deform["amounts"] = prev_amounts
            try:
                self._vram.set_deform_amounts(prev_amounts)
                back = self._write_current_frame("deform")
                back.pop("render_ms", None)
                emit(back)
            except Exception:      # 回滚也出帧失败：能说清的只有“重新导图”
                emit({"event": "engine_warn",
                      "warn": "形变回滚后仍无法出帧，本会话不可信，请重新导入图片"})
            emit({"event": "error", "error": f"形变渲染失败，滑块已退回上一值（"
                  f"{type(e).__name__}）：{e}"})
            return
        render_ms = fr.pop("render_ms")
        self._emit_deform_state(action, build=build_info.get("build"),
                                render_ms=render_ms,
                                total_ms=round((monotonic_ns() - t_start) / 1e6, 2))
        emit(fr)

    # ------------------------------------------------------------ 调色（M3-a2）与预设（M3-b）
    def _resolve_lut_source(self, p: dict):
        """从命令里解析出那张表：path / text / preset 三个来源必给且只给一个。

        返回 `(cube, preset_or_None)`：走 preset 那一臂时还要把预设的肤色定向一并提交
        （一个预设 = 一张表 + 三个数），返回的第二个元素就是那个预设对象。
        失败自己发 error 返 None。

        为什么不“都给就用 text”：两个来源并存时先选一个就是替用户做决定，而两个表
        往往正好不一样——拿到哪个都是“对的那张的错版本”。当场拒比猜安全。
        """
        given = [k for k in ("path", "text", "preset") if p.get(k)]
        if len(given) != 1:
            emit({"event": "error",
                  "error": f"lut set 需要且只能给一个来源（path / text / preset），收到 "
                           f"{len(given)} 个{('：' + ', '.join(given)) if given else ''}"})
            return None
        key = given[0]
        try:
            if key == "path":
                return load_cube_file(str(p["path"])), None
            if key == "text":
                return parse_cube(str(p["text"]), source="text"), None
            preset = get_preset(p["preset"])
            return preset_lut(preset.name), preset
        except (LutError, PresetError, OSError, UnicodeDecodeError, ValueError) as e:
            # 整条拒：不留“解了一半”的表。上一轮“预计算失败留半截显存”同一形状。
            # 事件里的词沿用 “LUT 被拒”（test_protocol 一直在卡这个字面，也是报表里最好认的一个）。
            emit({"event": "error", "error": f"LUT 被拒，整条不生效（{type(e).__name__}）：{e}"})
            return None

    def _restore_lut(self, prev) -> None:
        """回到上一条已证能出帧的调色状态（补帧失败与回滚两条臂共用）。"""
        cube, amount = prev
        try:
            if cube is None:
                self._vram.clear_lut()
            else:
                self._vram.set_lut(cube, amount)
        except Exception as e:      # 回滚再失败就只能说清“重新导图”，不留一个看起来已回滚的状态
            emit({"event": "engine_warn",
                  "warn": f"调色层回滚失败（{type(e).__name__}）：{e}，本会话不可信，请重新导入图片"})

    def _restore_grade(self, prev) -> None:
        """回滚肤色定向层。与 _restore_lut 同一条：回滚再失败就明说“重新导图”。"""
        try:
            if prev == (0.0, 0.0, 0.0, 1.0):
                self._vram.clear_grade()
            else:
                self._vram.set_grade(prev[0], prev[1], prev[2], amount=prev[3])
        except Exception as e:
            emit({"event": "engine_warn",
                  "warn": f"肤色定向回滚失败（{type(e).__name__}）：{e}，本会话不可信，"
                          "请重新导入图片"})

    def _emit_lut_state(self, action: str, info: dict, *, render_ms: float = 0.0,
                        total_ms: float = 0.0) -> None:
        """lut_done 的唯一组装点（set/clear/amount 三条臂共用一份形状）。

        图层字段全部来自 vram._lut_payload，这里只加计时与每帧那几笔。与
        _precompute_ready_event / _emit_deform_state 同一条理由：两处各写一份必然漂，
        而 TS 把字段声明成必存——谎报发生在 JSON 边界上，编译期抓不到。
        """
        pipe = self._vram
        emit({"event": "lut_done", "action": action, **info,
              # 这一帧真跑了多少调色（挂上表且强度非 0 时 > 0；为 0 就是那层没跑）
              "lut_ms": round(float(pipe.last_lut_ms), 2),
              # M3-b：预设一条命令同时动两层，所以 lut_done 必须能说出定向那层的现状：
              # 否则 UI 只能自己记一份数，而引擎里那一层可能因为回滚已经变了。
              # 它与 grade_done 里的 grade_ms 同一出处（都取自局部 pipe），不是第2个口径。
              "grade_ms": round(float(pipe.last_grade_ms), 2),
              "grade_state": dict(dh=float(pipe.grade_params[0]), ds=float(pipe.grade_params[1]),
                                  dv=float(pipe.grade_params[2]), amount=float(pipe.grade_amount),
                                  lit=bool(pipe.has_grade()),
                                  bytes_grade=int(pipe.grade_resident_bytes())),
              # 当前生效的预设名（没走预设就是 None）：UI 靠它区分“预设强度”与
              # “自己载的表”，而不是自己记住上一次按了哪个按钮
              "lut_preset": self._lut_preset,
              # 这两条是“设 LUT 不作废磨皮缓存”的直接证据：补的那一帧仍应命中
              "filter_ms": round(float(pipe.last_filter_ms), 2),
              "bands_ms": round(float(pipe.last_bands_ms), 2),
              "filter_cached": float(pipe.last_filter_ms) == 0.0,
              "deform_ms": round(float(pipe.last_deform_ms), 2),
              "render_ms": round(float(render_ms), 2),
              "total_ms": round(float(total_ms), 2),
              "strength": self._strength})

    def cmd_lut(self, p: dict):
        """3D LUT 调色（M3-a2）：载入/清除一张表，或只改混合系数。

        与 light/deform 同一套铁律：跑靶互斥、先全量校验后一次性提交、被拒整条不留痕、
        事件只有一个组装点。与它们的区别在于本层不依赖关键点也不依赖笔迹：
        换设备要重挂（体积活在那块卡上），但不随磨皮/修容参数作废任何缓存。
        """
        action = p.get("action", "set")
        if action not in ("set", "clear", "amount"):
            emit({"event": "error", "error": f"未知 lut action: {action}（可用：set/clear/amount）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x"
                  f"{getattr(self.shm, 'h', '?')} != 会话 {self._vram.w}x{self._vram.h}，"
                  "请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 lut：先 bench_stop"})
            return
        t_start = monotonic_ns()
        prev = (self._lut, self._lut_amount)
        prev_grade = self._grade
        prev_preset = self._lut_preset
        if action == "set":
            # 强度先校：不能先付一次解析 + 上显存再发现参数非法（与 cmd_deform“参数先于建层”同形）
            amount = None
            if p.get("amount") is not None:
                try:
                    amount = check_amount(p["amount"])
                except LutError as e:
                    emit({"event": "error", "error": f"lut 被拒，整条不生效：{e}"})
                    return
            got = self._resolve_lut_source(p)
            if got is None:
                return
            cube, preset = got
            gvals = None
            if preset is not None:
                # 预设同时动两层，那两层的参数都得先过完才能开始提交：先挂表再拒
                # 参数就是“半应用”（M1-3c/M2-a2 审查里同一个形状）。
                # 强度一个数管两层：预设的“50%”应当是整预设 50%，不是表 50% + 定向 100%。
                try:
                    gvals = check_params(*preset_grade(preset.name),
                                         amount=(1.0 if amount is None else float(amount)))
                except GradeError as e:
                    emit({"event": "error", "error": f"预设 {preset.name} 被拒，两层均未改动：{e}"})
                    return
            try:
                info = self._vram.set_lut(cube, amount)
            except (LutError, RuntimeError, ValueError) as e:
                # 库层只在全部可失败步骤之后才赋值，所以这里会话状态原样未动；
                # 引擎侧那两个字段也必须不动，否则下一条 set 会以为已经挂上了这张表
                emit({"event": "error", "error": f"调色层被拒，会话原样未动（"
                      f"{type(e).__name__}）：{e}"})
                return
            self._lut, self._lut_amount = self._vram.lut, float(self._vram.lut_amount)
            # 预设身份记在引擎侧：它决定“调色强度”要不要连带施加到定向层（见 amount 臂）。
            # 走 path/text 就是用户自己拿表说话，预设身份当场清掉。
            self._lut_preset = preset.name if preset is not None else None
            if gvals is not None:
                # 参数已在上一步校过，这里的提交不会再拒：预设要么两层都上，要么都不上。
                # 不拿它的返回值当 info：那会把 lut_done 的形状换成 grade 的那份（就是
                # M2 审 ⑤ “字典后写吃先写”同一个形状，本轮协议用例一个 KeyError 抽出来的）。
                # 定向层的现状由 _emit_lut_state 直接从 pipe 组装，只有一个出处。
                self._vram.set_grade(gvals[0], gvals[1], gvals[2], amount=gvals[3])
                self._grade = gvals
        elif action == "amount":
            if p.get("amount") is None:
                emit({"event": "error", "error": "lut amount 什么也没给：需要一个 0–1 的数值"})
                return
            try:
                amount = check_amount(p["amount"])
            except LutError as e:
                emit({"event": "error", "error": f"lut 被拒，整条不生效：{e}"})
                return
            try:
                info = self._vram.set_lut_amount(amount)
            except (LutError, RuntimeError, ValueError) as e:
                emit({"event": "error", "error": f"调色强度被拒，会话原样未动：{e}"})
                return
            self._lut_amount = float(self._vram.lut_amount)
            if self._lut_preset is not None:
                # 这一句不是“强度顺便也给定向层用”那么顺手：它是预设语义的必要一半。
                # `lut set preset=creamy amount=0.5` 把两层同时拉到 50%，之后只拖
                # “预设强度”滑块走的就是这一臂——不同步定向层就会“表淡了、肤色还满调”。
                # 只对走过预设的会话生效（_lut_preset 非空）：用户自己载表 + 手动调肤色时，
                # 表的强度不该伸到另一层里去。
                try:
                    self._vram.set_grade_amount(amount)
                    self._grade = (self._vram.grade_params[0], self._vram.grade_params[1],
                                   self._vram.grade_params[2], float(self._vram.grade_amount))
                except GradeError as e:
                    emit({"event": "error", "error": f"预设强度连带定向层被拒，已整条回滚：{e}"})
                    self._lut, self._lut_amount = prev
                    self._restore_lut(prev)
                    return
        else:
            info = self._vram.clear_lut()
            self._lut, self._lut_amount = None, 1.0
            self._lut_preset = None
        try:
            fr = self._write_current_frame("lut")
        except Exception as e:
            # 表/强度已写进常驻层而渲染抛了：必须退回上一条已证能出帧的状态。
            # cmd_deform 为同一个形状付过钱：“拒绝了但画面变了”比报错难查得多。
            self._lut, self._lut_amount = prev
            self._grade = prev_grade
            self._lut_preset = prev_preset
            self._restore_lut(prev)
            self._restore_grade(prev_grade)
            try:
                back = self._write_current_frame("lut")
                back.pop("render_ms", None)
                emit(back)
            except Exception:      # 回滚后仍出不了一帧：能说清的只有“重新导图”
                emit({"event": "engine_warn", "warn": "调色回滚后仍无法出帧，本会话不可信，"
                      "请重新导入图片"})
            emit({"event": "error", "error": f"调色渲染失败，已退回上一状态（"
                  f"{type(e).__name__}）：{e}"})
            return
        render_ms = fr.pop("render_ms")
        self._emit_lut_state(action, info, render_ms=render_ms,
                             total_ms=round((monotonic_ns() - t_start) / 1e6, 2))
        emit(fr)

    def _emit_grade_state(self, action: str, info: dict, *, render_ms: float = 0.0,
                          total_ms: float = 0.0) -> None:
        """grade_done 的唯一组装点（set/clear/amount 三条臂共用一份形状）。

        与 _emit_lut_state 同构：图层字段全部来自 vram._grade_payload，这里只加计时
        与每帧那几笔。字段集在两层之间对齐不是强迫症：哪一臂的 payload 少一个键，
        TS 侧就是个运行时 TypeError，而编译期抓不到。
        """
        pipe = self._vram
        emit({"event": "grade_done", "action": action, **info,
              # 这一帧真跑了多少定向（点火时 > 0；为 0 就是那层没跑，或走的是结构短路）
              "grade_ms": round(float(pipe.last_grade_ms), 2),
              # 调色层现状：手动改肤色会清掉预设身份，而“表还在不在”只能由事件说
              "lut_ms": round(float(pipe.last_lut_ms), 2),
              "lut_preset": self._lut_preset,
              "filter_ms": round(float(pipe.last_filter_ms), 2),
              "bands_ms": round(float(pipe.last_bands_ms), 2),
              "filter_cached": float(pipe.last_filter_ms) == 0.0,
              "deform_ms": round(float(pipe.last_deform_ms), 2),
              "render_ms": round(float(render_ms), 2),
              "total_ms": round(float(total_ms), 2),
              "strength": self._strength})

    def cmd_grade(self, p: dict):
        """肤色 HSL 定向（M3-b）：三个滑块 + 一个混入比例。

        与 cmd_lut 的区别只有一件：这一层不拿表，拿的是公式（窗口内逐帧内核）。
        其余铁律逐字沿用：跑靶互斥、先全量校验后一次性提交、被拒整条不留痕、
        出帧失败回滚 + 补帧、事件只有一个组装点。它与磨皮/修容/形变一样不参与
        任何缓存键：改它不会让滤波重算，反向也一样。
        """
        action = p.get("action", "set")
        if action not in ("set", "clear", "amount"):
            emit({"event": "error",
                  "error": f"未知 grade action: {action}（可用：set/clear/amount）"})
            return
        if not self._image_loaded or self._vram is None:
            emit({"event": "error", "error": "尚未 load_image"})
            return
        if self.shm is None or (self.shm.w, self.shm.h) != (self._vram.w, self._vram.h):
            emit({"event": "error", "error": f"shm {getattr(self.shm, 'w', '?')}x"
                  f"{getattr(self.shm, 'h', '?')} != 会话 {self._vram.w}x{self._vram.h}，"
                  "请先 load_image"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝 grade：先 bench_stop"})
            return
        # 参数键集合当场卡住：拼错了名字的键会被默默当作“没给”而沿用旧值，
        # 那是“按了滑块但画面不动、而事件看起来完全正常”的下一个版本。
        # cmd 本身也算一个键（命令与参数同层），所以它必须在白名单里——第一版就是
        # 忘了它，协议用例一跑就全军“grade 收到不认识的参数：cmd”。
        extra = sorted(set(p) - {"cmd", "action", "dh", "ds", "dv", "amount"})
        if extra:
            emit({"event": "error", "error": f"grade 收到不认识的参数：{', '.join(extra)}"
                  "（可用：dh / ds / dv / amount）"})
            return
        t_start = monotonic_ns()
        prev = self._grade
        prev_preset = self._lut_preset
        if action == "set":
            cur = dict(dh=self._grade[0], ds=self._grade[1], dv=self._grade[2])
            given = {k: p[k] for k in ("dh", "ds", "dv") if p.get(k) is not None}
            if not given and p.get("amount") is None:
                emit({"event": "error", "error": "grade set 什么也没给：三个增量里至少给一个，"
                      "或者走 clear 把整层关掉"})
                return
            cur.update(given)
            try:
                # 部分提交语义与 cmd_deform 一致：拖一个滑块不该把另外两个抹零，
                # 但合出来的那组数必须整组校过才能写进常驻层
                vals = check_params(cur["dh"], cur["ds"], cur["dv"],
                                    amount=float(p.get("amount", self._grade[3])))
            except GradeError as e:
                emit({"event": "error", "error": f"grade 被拒，整条不生效：{e}"})
                return
            info = self._vram.set_grade(vals[0], vals[1], vals[2], amount=vals[3])
            self._grade = vals
            # 手动改了肤色，预设身份就当场失效：不然下一条 `lut amount` 会以为
            # “这层的肤色还是预设那份”，把用户刚调的数与表的强度绑在一起盖掉
            self._lut_preset = None
        elif action == "amount":
            if p.get("amount") is None:
                emit({"event": "error", "error": "grade amount 什么也没给：需要一个 0–1 的数值"})
                return
            try:
                info = self._vram.set_grade_amount(p["amount"])
            except GradeError as e:
                emit({"event": "error", "error": f"肤色定向强度被拒，会话原样未动：{e}"})
                return
            self._grade = (self._vram.grade_params[0], self._vram.grade_params[1],
                           self._vram.grade_params[2], float(self._vram.grade_amount))
        else:
            info = self._vram.clear_grade()
            self._grade = (0.0, 0.0, 0.0, 1.0)
            self._lut_preset = None
        try:
            fr = self._write_current_frame("grade")
        except Exception as e:
            self._grade = prev
            self._lut_preset = prev_preset
            self._restore_grade(prev)
            try:
                back = self._write_current_frame("grade")
                back.pop("render_ms", None)
                emit(back)
            except Exception:      # 回滚后仍出不了一帧：能说清的只有“重新导图”
                emit({"event": "engine_warn", "warn": "肤色定向回滚后仍无法出帧，本会话不可信，"
                      "请重新导入图片"})
            emit({"event": "error", "error": f"肤色定向渲染失败，已退回上一状态（"
                  f"{type(e).__name__}）：{e}"})
            return
        render_ms = fr.pop("render_ms")
        self._emit_grade_state(action, info, render_ms=render_ms,
                               total_ms=round((monotonic_ns() - t_start) / 1e6, 2))
        emit(fr)

    def _pipe_copyin(self, rgba, strength: float, radius: int = DEFAULT_RADIUS,
                     eps: float = DEFAULT_EPS, detail_gain: float = DEFAULT_DETAIL_GAIN,
                     mid_gain: float = DEFAULT_MID_GAIN,
                     broad_gain: float = DEFAULT_BROAD_GAIN,
                     texture_radius: int = DEFAULT_TEXTURE_RADIUS):
        """逐帧搬运路径（对照组）：CPU numpy → H2D → 内核 → D2H → CPU numpy。

        返回 (RGBA, 各段 ms)。故意不复用输入缓冲：那是 test_frame 的缓存本体，
        改写它会让下一帧的「基图」逐帧漂走，「帧真的在换」这个证据就不可靠了。

        磨皮参数照单接收：两条臂跑同一组参数，否则 copyin 与 resident 的差值里混着算法差异。
        """
        import numpy as np

        from .ops.guided import make_tensor, retouch_t, to_numpy_chw
        from .quant import quantize_np

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
        # 这条对照臂就会静默漂离开生产参数，两个臂比的就不是同一件事了（M2-a 新加的
        # 三个参数必须一并带过来，否则对照臂还在跑二分频，差值里混着算法改动）
        o = retouch_t(tensor, strength=strength, radius=radius, eps=eps,
                      detail_gain=detail_gain, mid_gain=mid_gain,
                      broad_gain=broad_gain, texture_radius=texture_radius)
        self._sync()
        seg["kernel"] = (monotonic_ns() - t) / 1e6
        t = monotonic_ns()
        # 量化走唯一口径（四舍五入）：这条对照臂与常驻臂必须用同一种收尾，
        # 否则两臂的差值里混着半 LSB 的系统偏移，字节对拍就没法看了
        out[:, :, :3] = quantize_np(to_numpy_chw(o))
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
        if self._export is not None and self._export.is_alive():
            # 导出线程里存的是拍的 device；但换设备会重建当前会话并清掉那些图层产物，
            # 正在跑的那一批下一张拿到的就是半旧半新的状态
            emit({"event": "error", "error": "导出进行中，拒绝 set_device：等 export_done"})
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
        # 预热：把 GPU 上下文与首帧内核加载付在起进程时，而不是用户第一次点“导入”时
        # （F 轮：冷首图 ~299 ms vs 稳态 ~35 ms，那 265 ms 与图尺寸无关）。已有会话就不必
        # 再预热：那条链已被真图跑过，再建一个小会话只会白占显存。
        if self._cuda and not self._image_loaded:
            try:
                ms = warm_device(self._effective_device())
            except Exception as e:      # 预热失败不许拖垮设备切换，但必须报出来
                emit({"event": "engine_warn", "warn": f"GPU 预热失败（首图会慢）：{e}"})
                ms = 0.0
            if ms > 0.0:
                emit({"event": "engine_warm", "warm_ms": round(ms, 2), "device": self.device})
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
                try:
                    info = self._vram.load_face(self._precompute)
                except Exception as e:
                    # 会话已在新设备上而掩膜没重挂：不回收状态字段，下一条带 channel
                    # 的 set_strength 会被 mask_names 拒掉，而报表仍写着“有 skin 通道”——
                    # UI 说“没掩膜”的同时引擎里那张掩膜并不存在，两边各自自洽。
                    # 语义与库层 clear_face 一致：关键点一走，靠它的东西全部放下。
                    emit({"event": "error",
                          "error": f"新会话重挂预计算产物失败，掩膜/通道/形变层已全部清除（"
                                   f"{type(e).__name__}）：{e}"})
                    self._vram.clear_face()
                    self._precompute = None
                    self._precompute_backend = None
                    self._channel = None
                    self._deform = dict(amounts={k: 0.0 for k in KINDS}, built=False)
                    info = None
                if info is not None:
                    emit(self._precompute_ready_event(
                        self._precompute, info,
                        # 重挂没重新算：建图与推理都是 0，不是“没测到”。这里给 0.0 而不是
                        # 缺字段，是为了让两条臂的事件形状完全一致——UI 那边一旦按必存字段
                        # 读，少一个键就会在报表上变成 undefined 而无人报错
                        build_ms=0.0, infer_ms=0.0,
                        attach_ms=round((monotonic_ns() - t_p) / 1e6, 2),
                        total_ms=round((monotonic_ns() - t_p) / 1e6, 2),
                        replayed_for="device_switch"))
                # 形变层已在 _attach_pipeline 里跟着新会话重解过（那里不补帧，因为
                # 下面紧后就自己渲染并写 shm）——这里不能再解一次，那会把换设备的
                # 一次性成本翻倍，而 deform_builds 会凭空多一格
            if self.shm is not None and (self.shm.w, self.shm.h) == (self._vram.w, self._vram.h):
                # 通道必须跟着会话一起迁移：不传 channel 的话，报表里 active_channel 还是 skin，
                # 而给用户补发的是一帧全图渲染——字段与实际执行不一致正是本仓最贵那个坑的形状
                self._vram.render(self._strength, channel=self._channel, **self._params)
                with self._wlock:
                    seq, t_emit, slot = self.shm.write_frame(self._vram.read_back())
                emit({"event": "frame", "seq": seq, "slot": slot, "t_emit_ns": t_emit,
                      "w": self.shm.w, "h": self.shm.h, "mode": "device_switch"})

    # ------------------------------------------------------------ M4 全尺寸导出
    EXPORT_KEYS = {"cmd", "action", "images", "out_dir", "format", "quality", "tile"}

    def _export_snapshot(self, snap: dict, eh: int, ew: int, *, for_document: bool):
        """从命令线程拍好的快照里组一份 ExportSpec。返回 (spec, skipped)。

        为什么不直接读 self._*：导出跑在 worker 线程里，而 stdin 线程随时可能在改参数。
        读 live 状态的话，一批三张图会各自拿到"当时"的设置——中间拖一下滑块，前两张与
        后两张就不是同一套设置，而 export_done 里只写了一份。全部取自分好的 snap。

        `for_document=False`（导的不是当前这张图）时，消除笔、修容笔迹与形变一律不带：
        那些坐标属于**这一张脸**。把它们搬到别的照片上不是"批量应用设置"而是误调——
        与 M2-b 拒绝 synthetic 占位关键点是同一条理由。能跨图复用的只有参数级的东西：
        磨皮参数、调色表、肤色定向。skip 必须逐图报出去，不能默默少几层。
        """
        p = snap["params"]
        skipped: list = []
        spec = ExportSpec(strength=float(snap["strength"]), radius=int(p["radius"]),
                          eps=float(p["eps"]), texture_radius=int(p["texture_radius"]),
                          broad_gain=float(p["broad_gain"]), mid_gain=float(p["mid_gain"]),
                          detail_gain=float(p["detail_gain"]),
                          grade=tuple(snap["grade"]), cube=snap["lut"],
                          lut_amount=float(snap["lut_amount"]),
                          deform_amounts={})
        if not for_document:
            skipped += ["repair", "light", "deform", "channel（笔迹与掩膜属于当前文档）"]
            return spec, skipped
        spec.repair = [RepairOp(op_id=op.op_id,
                                weight=resample_field(op.weight, (eh, ew), uint8=True),
                                params=dict(op.params)) for op in snap["repair_ops"]]
        spec.light = [LightOp(op_id=op.op_id,
                              weight=resample_field(op.weight, (eh, ew), uint8=True),
                              sign=op.sign) for op in snap["light_ops"]]
        spec.light_exposure = float(snap["light"]["exposure"])
        spec.light_radius = int(snap["light"]["radius"])
        deform = snap["deform"]
        amounts = {k: float(v) for k, v in (deform.get("amounts") or {}).items()
                   if float(v) != 0.0}
        pc = snap["precompute"]
        if amounts and deform.get("built"):
            if pc is None:
                # 关键点不在就没有场：宁可少一层形变也不能拿上一张脸的场来凑
                skipped.append("deform（没有可用的关键点）")
            else:
                spec.deform_amounts = amounts
                spec.landmarks = np.asarray(pc.landmarks, dtype=np.float32)
        if snap["channel"]:
            if pc is None:
                skipped.append(f"channel:{snap['channel']}（没有掩膜）")
            else:
                arr, names = pc.stack()
                spec.channel = snap["channel"]
                spec.mask_names = list(names)
                spec.masks = resample_field(np.asarray(arr, dtype=np.float32), (eh, ew))
        return spec, skipped

    def cmd_export(self, p: dict):
        """全尺寸分块导出（批量）。在 worker 线程里跑：满幅一块图就能是几秒。"""
        unknown = set(p) - self.EXPORT_KEYS
        if unknown:
            emit({"event": "error", "error": f"export 收到不认识的参数：{sorted(unknown)}"})
            return
        # action 在白名单里就必须被校验：不校验的话 {"action":"status"} 会当成"开始导出"
        # 直接跑起来——前端想要的是状态，拿到的是一次满幅批量出片。
        action = p.get("action", "start")
        if action != "start":
            emit({"event": "error",
                  "error": f"export 只认识 action=start（收到 {action!r}）；" \
                           "进度看 export_progress / export_done 事件"})
            return
        if self.bench is not None and self.bench.is_alive():
            emit({"event": "error", "error": "跑靶进行中，拒绝导出：先 bench_stop"})
            return
        if self._export is not None and self._export.is_alive():
            emit({"event": "error",
                  "error": "导出已在进行中：一批只许一个（两个导出会同抢一块卡，"
                           "峰值账单就不是那个数了）"})
            return
        doc = self._doc_path
        images = p.get("images") or ([doc] if doc else [])
        if not isinstance(images, list) or not images:
            emit({"event": "error", "error": "export 需要 images（路径列表），且当前没有已加载的文档"})
            return
        if any((not isinstance(x, str) or not x) for x in images):
            emit({"event": "error", "error": "export 的 images 必须是非空字符串列表"})
            return
        out_dir = p.get("out_dir")
        if not isinstance(out_dir, str) or not out_dir:
            emit({"event": "error", "error": "export 需要 out_dir（导出目录）"})
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            emit({"event": "error", "error": f"out_dir 不可用：{e}"})
            return
        fmt = str(p.get("format", "jpg")).lower().lstrip(".")
        if fmt not in FORMATS:
            emit({"event": "error", "error": f"不支持的导出格式：{fmt}（可用 {sorted(set(FORMATS))}）"})
            return
        try:
            quality = int(p.get("quality", 95))
            tile = int(p.get("tile", DEFAULT_TILE))
        except (TypeError, ValueError):
            emit({"event": "error", "error": "quality/tile 必须是整数"})
            return
        if not (MIN_TILE <= tile <= MAX_TILE):
            emit({"event": "error", "error": f"tile={tile} 越界（允许 {MIN_TILE}~{MAX_TILE}）"})
            return
        if not (1 <= quality <= 100):
            emit({"event": "error", "error": f"quality={quality} 越界（需要 1~100）"})
            return
        # 参数在命令线程里全部拍定：worker 里不再读 self._*，否则中途改一下滑块，
        # 这一批里前几张与后几张用的就不是同一套设置（而事件里只写了一份）
        snap = dict(strength=self._strength, params=dict(self._params), grade=tuple(self._grade),
                    lut=self._lut, lut_amount=self._lut_amount, light=dict(self._light),
                    light_ops=list(self._light_ops), repair_ops=list(self._repair_ops),
                    deform=dict(self._deform), channel=self._channel,
                    precompute=self._precompute, device=self.device)
        self._export_args = (list(images), out_dir, fmt, quality, tile, doc, snap)
        self._export = threading.Thread(target=self._export_loop, daemon=True)
        self._export.start()

    def _export_loop(self):
        from .decode import load_full
        images, out_dir, fmt, quality, tile, doc, snap = self._export_args
        n = len(images)
        t0 = monotonic_ns()
        results: list = []
        failed = 0
        for idx, path in enumerate(images):
            stage = "decode"
            try:
                d = load_full(path)
                stage = "render"
                spec, skipped = self._export_snapshot(snap, d.h, d.w,
                                                      for_document=(path == doc))
                stage = "write"
                out_path = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + "." + fmt)
                frame, st = export_image(d.rgb, spec, device=snap["device"], tile=tile)
                info = write_file(frame, out_path, quality=quality)
                results.append({"path": path, "out": info["path"], "format": info["format"],
                                "bytes": info["bytes"], "write_ms": info["write_ms"],
                                "skipped": skipped, **st})
            except Exception as e:      # 逐图失败不能带倒整批
                failed += 1
                results.append({"path": path, "stage": stage, "error": f"{type(e).__name__}: {e}"})
            emit({"event": "export_progress", "index": idx, "total": n, "path": path,
                  "ok": "error" not in results[-1]})
        emit({"event": "export_done", "total": n, "failed": failed,
              "out_dir": out_dir, "format": fmt, "quality": quality, "tile": tile,
              "total_ms": round((monotonic_ns() - t0) / 1e6, 1), "images": results})

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
                 "precompute": self.cmd_precompute, "inpaint": self.cmd_inpaint,
                 "light": self.cmd_light, "deform": self.cmd_deform,
                 "lut": self.cmd_lut, "grade": self.cmd_grade, "export": self.cmd_export}
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
