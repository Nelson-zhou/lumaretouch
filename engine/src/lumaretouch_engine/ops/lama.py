"""生成式修补后端（LaMa 类）：结构自搭 + 权重门禁，**不与内置扩散修补混报**。

为什么要单独一个文件而不是往 `ops/inpaint.py` 里加一个开关：这两条路的**证据强度完全不同**。
内置那条是确定性算子，有独立 CPU 参考实现、有孔内 MAE/PSNR 的还原精度、有逐字节不变式；
这一条是神经网络，没有权重就没有任何质量主张可写。把它们塞进同一个函数、同一个事件字段，
报表上就会出现一条“修补成功”把两种东西混成一个数——这正是本仓最贵那个坑的形状
（会话在 CPU 上跑却标着 cuda）。所以这里只允许两件事：**结构可跑（成本与显存可测）** 与
**权重齐了才可用（否则当场拒绝，绝不退成内置）**。

架构按公开论文思想自搭（大核局部滤波 + FFT 通道间复数混合的 U-Net，LaMa 一类），
不含任何上游代码：
* 输入 4 通道（RGB + 掩膜），输出 3 通道；
* 每个 block 把通道分成局部组（实域 3×3 大核）与全局组（频域复数逐点乘），
  全局组的空间表示用「实部 + 虚部」两组实通道承载，变换后仍还原成同样两组，
  因此块的输入/输出通道数一致，U-Net 的跳跃连接不会为对齐再花时间；
* 下采样 stride 卷积、上采样 ConvTranspose，中间若干级全分辨率 FFC；
* 复数运算一律 fp32（ROCm/CUDA 上半精度复数支持不完整，M0 已实测确认）。

权重不入库（决策 9）。文件放在 `LRT_MODEL_DIR`（默认 `~/.cache/lumaretouch/models`），
装载必须同时给出 `LRT_LAMA_SHA256`，否则拒绝加载；`torch.load(weights_only=True)`，
不接受 pickle 任意对象——权重文件是外部产物，加载它不等于执行它。
"""

from __future__ import annotations

import importlib.util
import os

from . import weights

MODEL_FILE = "lama_large.ft"
MODEL_SHA256_ENV = "LRT_LAMA_SHA256"
DEFAULT_MODEL_DIR = os.path.expanduser("~/.cache/lumaretouch/models")
# 生成分辨率下限：频域混合对窗口尺寸敏感，太小会把脸修糊；交互档不许用它（决策 15）
MIN_WINDOW = 256
SUGGESTED_WINDOW = 512


class MissingBackend(RuntimeError):
    """请求的生成式后端不可用。调用方必须把它当错误处理，不许退到别的路径继续跑。"""


def model_path(model_dir: str | None = None) -> str:
    d = model_dir or os.environ.get("LRT_MODEL_DIR") or DEFAULT_MODEL_DIR
    return os.path.join(d, MODEL_FILE)


def available(model_dir: str | None = None) -> bool:
    return os.path.isfile(model_path(model_dir))


def production_check(model_dir: str | None = None) -> tuple[bool, str]:
    """能不能上生产 + 不能的话是为什么。与 `load_net` 共用 ops/weights 那一份判定（M8）：
    能力上报与执行两套口径就是双出处，早晚漂。
    """
    return weights.production_gate(model_file=MODEL_FILE, sha_env=MODEL_SHA256_ENV,
                                   path=model_path(model_dir),
                                   absent_reason=missing_reason("lama", model_dir))


def ready_for_production(model_dir: str | None = None) -> bool:
    return production_check(model_dir)[0]


def missing_reason(backend: str = "lama", model_dir: str | None = None) -> str:
    """给协议层的一句话解释：为什么这条路现在不能走。"""
    return (f"生成式后端 {backend} 不可用：权重文件不在 {model_path(model_dir)}。"
            "权重不入库、引擎不吃下载（决策 9），需由安装器按 sha256 取官方发布件后再请求本后端；"
            "要把修补做出来请显式用 backend=\"builtin\"（确定性扩散修补），"
            "引擎不会替你默默换后端。")


def _torch():
    if importlib.util.find_spec("torch") is None:
        raise MissingBackend("torch 未安装，生成式修补后端不可用（CPU 数值对拍与协议门禁不受影响）")
    import torch
    return torch


def build_net(torch, base: int = 96, n_ffc: int = 4):
    """自搭的 FFC U-Net（未加载权重）。形状在构造期就自校验，不留到第一次前向才炸。"""
    import torch.nn as nn

    class FFCLayer(nn.Module):
        """局部 3×3 大核 + 全局频域复数逐点乘。输入输出通道数同为 ch（ch 要能被 4 整除）。

        通道布局：`[局部 ch/2 ‖ 全局实部 ch/4 ‖ 全局虚部 ch/4]`。为什么用“两个实数组”而不是
        complex Parameter：state_dict 里的 complex 参数在跨 torch 版本与 weights_only 装载上
        更挑，strict 校验时坑多。频域乘法对两个实部各自做同一套复数乘（线性），
        而不是拼成一个 Hermitian 谱再逆变换：后者需要先拆 Hermitian 对称部分，等价的写法反而慢。
        """

        def __init__(self, ch):
            super().__init__()
            assert ch % 4 == 0, f"FFC 通道数要能被 4 整除（局部/全局实部/全局虚部），得到 {ch}"
            self.ch = ch
            self.cl = ch // 2
            self.gl = ch // 4
            self.loc_to_loc = nn.Conv2d(self.cl, self.cl, 3, padding=1, bias=False)
            self.glob_to_loc = nn.Conv2d(2 * self.gl, self.cl, 3, padding=1, bias=False)
            # 频域复数权重：(gl, gl) 矩阵的实部/虚部两份参数。初始化置零：未加载权重时
            # 全局支路输出 0，网络仍可前向（成本与形状可测），不会随机数决定形状行为
            self.wr = nn.Parameter(torch.zeros(self.gl, self.gl))
            self.wi = nn.Parameter(torch.zeros(self.gl, self.gl))
            self.norm = nn.InstanceNorm2d(ch, affine=True)
            self.act = nn.LeakyReLU(0.2, inplace=True)

        def _mix(self, spec, wr, wi):
            """沿输入通道 c 求和的复数乘：(a+ib)(w_r+iw_i)，w 形状 (g, c)。"""
            ar = torch.einsum("bckw,gc->bgkw", spec.real, wr) - torch.einsum("bckw,gc->bgkw", spec.imag, wi)
            ai = torch.einsum("bckw,gc->bgkw", spec.real, wi) + torch.einsum("bckw,gc->bgkw", spec.imag, wr)
            return torch.complex(ar, ai)

        def forward(self, x):
            loc = x[:, :self.cl]
            gre = x[:, self.cl:self.cl + self.gl]
            gim = x[:, self.cl + self.gl:]
            wr = self.wr.float()
            wi = self.wi.float()
            a = self._mix(torch.fft.rfft2(gre.float(), norm="forward"), wr, wi)
            b = self._mix(torch.fft.rfft2(gim.float(), norm="forward"), wr, wi)
            glo_r = torch.fft.irfft2(a, s=x.shape[-2:], norm="forward")
            glo_i = torch.fft.irfft2(b, s=x.shape[-2:], norm="forward")
            local_out = self.loc_to_loc(loc) + self.glob_to_loc(torch.cat([gre, gim], 1))
            out = torch.cat([local_out, glo_r, glo_i], 1)
            if out.shape[1] != self.ch:
                raise RuntimeError(f"FFC 内部形状不守恒：输出 {out.shape[1]} 通道 != {self.ch}")
            return self.act(self.norm(out.to(x.dtype)))

    class ResBlock(nn.Module):
        def __init__(self, c):
            super().__init__()
            self.body = nn.Sequential(nn.Conv2d(c, c, 3, padding=1, bias=False),
                                      nn.LeakyReLU(0.2, inplace=True),
                                      nn.Conv2d(c, c, 3, padding=1, bias=False))

        def forward(self, x):
            return x + self.body(x)

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            c = base
            self.head = nn.Conv2d(4, c, 3, padding=1)
            self.b0 = nn.Sequential(FFCLayer(c), FFCLayer(c))
            self.d1 = nn.Conv2d(c, c, 3, stride=2, padding=1)
            self.b1 = nn.Sequential(FFCLayer(c), FFCLayer(c))
            self.d2 = nn.Conv2d(c, c * 2, 3, stride=2, padding=1)
            self.mid = nn.Sequential(*[FFCLayer(c * 2) for _ in range(max(n_ffc, 1))])
            self.u1 = nn.ConvTranspose2d(c * 2, c, 3, stride=2, padding=1, output_padding=1)
            self.b2 = nn.Sequential(FFCLayer(c), FFCLayer(c))
            self.u0 = nn.ConvTranspose2d(c, c, 3, stride=2, padding=1, output_padding=1)
            self.tail = nn.Sequential(ResBlock(c), nn.Conv2d(c, 3, 3, padding=1), nn.Sigmoid())

        def forward(self, x):
            if min(x.shape[-2:]) < MIN_WINDOW:
                raise ValueError(f"修补窗口边长不得小于 {MIN_WINDOW}，得到 {tuple(x.shape[-2:])}")
            if x.shape[1] != 4:
                raise ValueError(f"生成式修补入参必须是 RGB + 掩膜 4 通道，得到 {x.shape[1]}")
            h = self.head(x)
            s0 = self.b0(h)
            s1 = self.b1(self.d1(s0))
            s2 = self.mid(self.d2(s1))
            u1 = self.b2(self.u1(s2) + s1)
            u0 = self.u0(u1) + s0
            return self.tail(u0)

    return Net()


def load_net(model_dir: str | None = None, device: str = "cuda", base: int = 96, n_ffc: int = 4):
    """建网 + 权重装载 + sha256 校验。任何一步不满足都抛 MissingBackend。"""
    torch = _torch()
    ok, why = production_check(model_dir)
    if not ok:
        raise MissingBackend(why)
    path = model_path(model_dir)
    net = build_net(torch, base=base, n_ffc=n_ffc)
    state = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "net" in state:
        state = state["net"]
    net.load_state_dict(state, strict=True)     # strict：多一层少一层都要响，不许静默部分加载
    net.eval().to(device)
    return net


class LamaInpainter:
    """出片档修补后端：整窗推理，返回 (1,3,H,W) 的**填充结果**（不做混合）。

    调用方负责混合与生命周期；本类不碰常驻缓存，因此不会把生成式的成本混进
    `filter` 分段——事件驱动的那一次必须单独可归因，否则报表又会把两种成本算成一个。
    """

    name = "lama"

    def __init__(self, model_dir: str | None = None, device: str = "cuda"):
        torch = _torch()
        self.torch = torch
        self.device = device
        self.net = load_net(model_dir, device)

    def __call__(self, img, weight):
        m = (weight > 0).to(img.dtype).expand_as(img[:, :1]) if weight.shape[1] != 1 else (weight > 0).to(img.dtype)
        out = self.net(torch.cat([img, m], dim=1))
        return torch.clamp(out, 0.0, 1.0)
