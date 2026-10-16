"""预览管线：源图与输出帧常驻显存，滑块拖动期间不做逐帧 numpy 往返。

为什么要这一层：M0/M1-1 实测 1280×800 挂管线 34.9 ms/帧，而滤波内核只占 7.9 ms，
剩下的全是 numpy 前后处理与 H2D/D2H——`astype/255` 3.6、转置 2.7、H2D 1.8、
D2H 1.8、`clip*255→uint8` 4.5。也就是说我们花了 4 倍于算法的成本在搬运上。

约定：
- 源图以 uint8 (1,3,H,W) 一次性进显存，之后**不再回 CPU**；
- 每次渲染只改系数（对应滑块值），全程 GPU kernel；
- 输出用一张常驻 (H,W,4) uint8 显存帧，回读一次即共享内存的字节布局，
  不需要 permute/contiguous/tobytes 任何一步额外拷贝。
"""

from __future__ import annotations

import numpy as np

try:
    import torch          # 与 ops.guided 同一约定：torch 未装（M0 纯通路、CI 的 CPU job）
except Exception:        # 也要能 import 成功，不然整个测试收集阶段就报 ModuleNotFoundError
    torch = None

from .ops.guided import guided_t, retouch_t

# 与 ops.guided 的生产默认值保持一致；滑块只在这个基准附近改动系数
DEFAULT_RADIUS = 12
DEFAULT_EPS = 6e-4
DEFAULT_DETAIL_GAIN = 0.85


class PreviewPipeline:
    """一张图的 GPU 常驻预览会话。

    拆成 retouch()/pack() 两步而不是一个大函数，是为了让跑靶能把「滤波内核」
    和「float→uint8 收尾」分开计时——只有分开量，才能证明省下的 25 ms 全在
    搬运上，而不是顺手把算法也跳过了。
    """

    def __init__(self, device: str, w: int, h: int):
        if torch is None:
            raise RuntimeError("torch 未安装，显存常驻预览路径不可用（装 rocm/cuda/cpu 任一变体）")
        self.w, self.h = w, h
        want_cuda = device.startswith("cuda")
        if want_cuda and not torch.cuda.is_available():
            # 静默退到 CPU 会让「GPU 常驻」的结论变成假的，必须让调用方能看见
            self.fallback = f"要求 {device}，但 torch.cuda.is_available()=False，已退到 cpu"
            device = "cpu"
        else:
            self.fallback = None
        self.device = torch.device(device)
        # 源图 float 与 uint8 都留着：float 供滤波，uint8 供"恢复原图"这类需要原始像素的操作
        self.src_u8: torch.Tensor | None = None
        self.src_f32: torch.Tensor | None = None
        self.frame_gpu: torch.Tensor | None = None   # (H,W,4) uint8，回读即 shm 布局

    # ---- 装载：一次性 H2D ----------------------------------------------
    def load_rgb_u8(self, rgb: np.ndarray) -> None:
        """(H,W,3) uint8 → 显存常驻。整场会话只调一次（导入或换图时）。"""
        if rgb.shape[:2] != (self.h, self.w):
            raise ValueError(f"源图尺寸 {rgb.shape[:2]} != 会话 {self.h}x{self.w}")
        arr = np.ascontiguousarray(rgb.transpose(2, 0, 1))[None]
        # 不开 non_blocking：从 pageable 内存异步上传，调用方一释放这块 numpy 就是未定义行为；
        # 这里整场会话只走一次，同步拷贝不花什么钱。
        self.src_u8 = torch.from_numpy(arr).to(self.device)
        self.src_f32 = self.src_u8.to(torch.float32).div_(255.0)
        self.frame_gpu = torch.empty((self.h, self.w, 4), dtype=torch.uint8, device=self.device)
        self.frame_gpu[..., 3] = 255
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)

    # ---- 渲染：全 GPU，无 CPU 参与 --------------------------------------
    def retouch(self, strength: float, radius: int = DEFAULT_RADIUS,
                eps: float = DEFAULT_EPS, detail_gain: float = DEFAULT_DETAIL_GAIN):
        """只跑算法，返回显存里的 float (1,3,H,W)。滑块每动一次调一次。"""
        if self.src_f32 is None:
            raise RuntimeError("先 load_rgb_u8 再 render")
        return retouch_t(self.src_f32, strength=strength, radius=radius,
                         eps=eps, detail_gain=detail_gain)

    def pack(self, out) -> None:
        """float→uint8 并写进常驻帧缓冲，同样全程在显存里做。"""
        u8 = (out.clamp_(0.0, 1.0) * 255.0).to(torch.uint8)[0].permute(1, 2, 0)
        self.frame_gpu[..., :3] = u8

    def render(self, strength: float, **kw) -> None:
        """算一帧写进常驻帧缓冲。strength=0 时应当逐字节等于原图。"""
        self.pack(self.retouch(strength, **kw))

    def read_back(self) -> np.ndarray:
        """一次 D2H，返回可直接交给 shm.write_frame 的连续 (H,W,4) uint8。"""
        if self.frame_gpu is None:
            raise RuntimeError("尚未渲染")
        if self.device.type != "cpu":
            torch.cuda.synchronize(self.device)
        return self.frame_gpu.cpu().numpy()

    def stamp(self, seq: int) -> None:
        """把序号写进常驻帧缓冲里一个 16×16 小块——只给跑靶当「帧真的在换」的证据。

        位置与写法跟 frames.test_frame 逐字一致，两条臂因此可用同一套像素比对。
        生产通路不调它（HUD 由 WebGL 叠）。放在这里而不是让调用方改 numpy，是因为
        CPU 设备上 .cpu() 返回的就是常驻张量本身，在外面改等于改到了基图上。
        """
        if self.frame_gpu is None:
            raise RuntimeError("先 load_rgb_u8")
        s = seq & 0xFF
        blk = self.frame_gpu[16:32, 16:32]
        blk[..., 2] = s
        blk[..., 0] = 255 - s

    # ---- 掩膜类操作要用到的低频层，也常驻在 GPU 上 ----------------------
    def low_freq(self, radius: int = DEFAULT_RADIUS, eps: float = DEFAULT_EPS):
        assert self.src_f32 is not None
        return guided_t(self.src_f32, radius, eps)


def make_pipeline(device: str, w: int, h: int, rgb: np.ndarray | None = None) -> PreviewPipeline:
    p = PreviewPipeline(device, w, h)
    if rgb is not None:
        p.load_rgb_u8(rgb)
    return p
