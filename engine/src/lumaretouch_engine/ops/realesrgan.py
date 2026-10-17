"""神经网络超分后端（Real-ESRGAN 类 RRDB 生成器）：结构自搭 + 权重门禁。

与 `ops/lama.py`、`ops/birefnet.py` 完全同构的立场，理由也一样：没有权重就没有任何
"AI 超分质感"的质量主张可写。这里只允许两件事——**结构可跑（成本与显存可测）** 与
**权重齐了才可用（否则当场拒绝，绝不退成 Lanczos 冒充超分）**。确定性放大
（`ops/upscale.py` 的 Lanczos + 锐化）是装机即用档；这一条是复杂纹理的正解，但必须
等权重按 sha256 放行。

架构按公开发表的 RRDB/ESRGAN 结构描述自搭（不含任何上游代码或权重）：
* `conv_first` 3→nf；`body` 为 num_block 个 RRDB（每个含 3 个残差密集块，密连
  5 层 3×3、LeakyReLU(0.2)、两次 0.2/2.3 残差缩放）；
* `conv_body` 后与 body 输入再残差相加（体内部全局残差），上采样用两级
  `conv → PixelShuffle(2)` 做到 ×4；`conv_hr + LeakyReLU → conv_last` 出 3 通道；
* 全 fp32：半精度在 ROCm 的卷积/PixelShuffle 组合上不完整，超分是最终质量敏感环节。

分块推理为什么必需而不是优化：×4 一张 4000×3000 的图，输出 16000×12000，特征图按
nf=64 存一层就是 ~33 GB——消费级 A 卡根本放不下。所以本模块自带带重叠的分块前向，
并把"重叠多大、接缝残余多少"作为可测项交出去（结构与 Lanczos 不同，卷积有边缘效应，
**不承诺逐字节等价**，只承诺随 overlap 收敛，这条边界写死在这里免得日后混报）。

权重不入库（决策 9）。文件放在 `LRT_MODEL_DIR`（默认 `~/.cache/lumaretouch/models`），
装载必须同时给出 `LRT_REALESRGAN_SHA256`，否则拒绝加载；`weights_only=True` +
`load_state_dict(strict=True)`——多一层少一层都要响，不许静默部分加载。
"""

from __future__ import annotations

import importlib.util
import os

from . import weights

MODEL_FILE = "realesrgan_generator.pt"
MODEL_SHA256_ENV = "LRT_REALESRGAN_SHA256"
DEFAULT_MODEL_DIR = os.path.expanduser("~/.cache/lumaretouch/models")
#: 超分推理的分块默认：512 源像素 → 2048 输出，是 12 GB 级 A 卡吃得住的档
INFER_TILE = 512
#: 块间重叠（源像素）。卷积有边缘效应，overlap 越大接缝残余越小；默认 16 的实测
#: 收敛性由 test_upscale 里那一条"随 overlap 单调不增"钉住
INFER_OVERLAP = 16


class MissingBackend(RuntimeError):
    """超分后端不可用。调用方必须把它当错误处理，不许退成 Lanczos 然后报"AI 超分完成"。"""


def model_path(model_dir: str | None = None) -> str:
    d = model_dir or os.environ.get("LRT_MODEL_DIR") or DEFAULT_MODEL_DIR
    return os.path.join(d, MODEL_FILE)


def available(model_dir: str | None = None) -> bool:
    return os.path.isfile(model_path(model_dir))


def production_check(model_dir: str | None = None) -> tuple[bool, str]:
    """能不能上生产 + 不能的话是为什么。**能力上报（scale_backends）与 `load_net` 共用
    这一份**（ops/weights）：“权重在位但被人换过”那一台机器上，只看文件存在会把
    一个注定被拒的后端报成装机可用。
    """
    return weights.production_gate(model_file=MODEL_FILE, sha_env=MODEL_SHA256_ENV,
                                   path=model_path(model_dir),
                                   absent_reason=missing_reason("realesrgan", model_dir))


def ready_for_production(model_dir: str | None = None) -> bool:
    return production_check(model_dir)[0]


def missing_reason(backend: str = "realesrgan", model_dir: str | None = None) -> str:
    return (f"超分后端 {backend} 不可用：权重文件不在 {model_path(model_dir)}。"
            "权重不入库、引擎不吃下载（决策 9），需由安装器按 sha256 取官方发布件后再请求本后端；"
            "请先用确定性放大（backend=\"lanczos3\"），引擎不会替你默默切后端、"
            "更不会拿 Lanczos 的结果冒充神经网络超分的质量。")


def _torch():
    if importlib.util.find_spec("torch") is None:
        raise MissingBackend("torch 未安装，超分神经网络后端不可用（Lanczos 放大不受影响）")
    import torch
    return torch


def build_net(torch, scale: int = 4, num_block: int = 23, nf: int = 64, growth: int = 32):
    """自搭 RRDBNet（未加载权重）。构造期就把倍率合法性钉死，不留到首次前向才炸。"""
    import torch.nn as nn

    if scale not in (1, 2, 4):
        raise ValueError(f"本结构支持 scale=1/2/4，收到 {scale}")
    n_up = {1: 0, 2: 1, 4: 2}[scale]

    class ResidualDenseBlock(nn.Module):
        """密连 5 层：每层吃前面所有层的拼接，出口再乘 0.2 加回输入。"""
        def __init__(self):
            super().__init__()
            ch = nf
            self.c1 = nn.Conv2d(ch, growth, 3, 1, 1)
            self.c2 = nn.Conv2d(ch + growth, growth, 3, 1, 1)
            self.c3 = nn.Conv2d(ch + 2 * growth, growth, 3, 1, 1)
            self.c4 = nn.Conv2d(ch + 3 * growth, growth, 3, 1, 1)
            self.c5 = nn.Conv2d(ch + 4 * growth, ch, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        def forward(self, x):
            o1 = self.lrelu(self.c1(x))
            o2 = self.lrelu(self.c2(torch.cat([x, o1], 1)))
            o3 = self.lrelu(self.c3(torch.cat([x, o1, o2], 1)))
            o4 = self.lrelu(self.c4(torch.cat([x, o1, o2, o3], 1)))
            o5 = self.c5(torch.cat([x, o1, o2, o3, o4], 1))
            return o5 * 0.2 + x

    class RRDB(nn.Module):
        def __init__(self):
            super().__init__()
            self.r1 = ResidualDenseBlock()
            self.r2 = ResidualDenseBlock()
            self.r3 = ResidualDenseBlock()
            self.bd = nn.Conv2d(nf, nf, 3, 1, 1)

        def forward(self, x):
            y = self.r3(self.r2(self.r1(x)))
            return self.bd(y) * 2.3 + x

    class RRDBNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv_first = nn.Conv2d(3, nf, 3, 1, 1)
            self.body = nn.Sequential(*[RRDB() for _ in range(num_block)])
            self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
            ups = []
            for _ in range(n_up):
                ups += [nn.Conv2d(nf, nf * 4, 3, 1, 1), nn.PixelShuffle(2)]
            self.upsample = nn.Sequential(*ups)
            self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)
            self.scale = scale

        def forward(self, x):
            f = self.conv_first(x)
            b = self.conv_body(self.body(f)) + f
            h = self.upsample(b)
            return self.conv_last(self.lrelu(self.conv_hr(h)))

    return RRDBNet()


def load_net(model_dir: str | None = None, device: str = "cuda", scale: int = 4,
             num_block: int = 23, nf: int = 64):
    """建网 + 权重装载 + sha256 校验。任何一步不满足都抛 MissingBackend。"""
    torch = _torch()
    ok, why = production_check(model_dir)
    if not ok:
        raise MissingBackend(why)
    path = model_path(model_dir)
    net = build_net(torch, scale=scale, num_block=num_block, nf=nf)
    state = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "net" in state:
        state = state["net"]
    net.load_state_dict(state, strict=True)
    net.eval().to(device)
    return net


def forward_tiled(net, x, tile: int = INFER_TILE, overlap: int = INFER_OVERLAP):
    """带重叠的分块前向：`x` 为 (1,3,H,W) [0,1]。返回 (out, info)。

    每块多取 `overlap` 像素的边，算完按线性交叉淡化裁回自己的地盘——所以每个输出
    像素都由两块各自算过一遍再混合，接缝随 overlap 增大而收敛（不是逐字节承诺）。
    没有这套，×4 满幅的特征图直接把显存推到卡的上限之外：这条路径的存在是"能不能
    上市"的问题，不是"快不快"的问题。
    """
    import torch
    if x.ndim != 4 or x.shape[0] != 1:
        raise ValueError(f"forward_tiled 需要 (1,3,H,W)，得到 {tuple(x.shape)}")
    if tile <= 0 or overlap < 1 or overlap >= tile:
        raise ValueError(f"tile={tile} / overlap={overlap} 不合法（需 1≤overlap<tile）")
    s = int(getattr(net, "scale", 4))
    _, _, h, w = x.shape
    out = torch.zeros((1, 3, h * s, w * s), dtype=x.dtype, device=x.device)
    weight = torch.zeros((1, 1, h * s, w * s), dtype=x.dtype, device=x.device)
    tiles = 0
    peak_px = 0

    def ramp(n: int, lead: int, trail: int):
        """行/列权重掩码：两端各有 lead/trail 个输出行做 0→1 / 1→0 的线性淡化。

        lead/trail 是**输出单**的淡化宽度（= 借来的 halo 源像素 × scale）。
        只在真有 halo 的那一端淡（图缘那端 lead/trail=0）：那里只有一块覆盖，
        除权后就是它自己的值，淡不淡都不影响结果。
        """
        m = torch.ones(n, dtype=x.dtype, device=x.device)
        if lead > 0:
            o = min(lead, n)
            m[:o] = torch.linspace(0.0, 1.0, o + 1, dtype=x.dtype, device=x.device)[1:]
        if trail > 0:
            o = min(trail, n)
            m[-o:] = torch.linspace(1.0, 0.0, o + 1, dtype=x.dtype, device=x.device)[:-1]
        return m

    ys = list(range(0, h, tile))
    xs = list(range(0, w, tile))
    for by in ys:
        y0 = max(0, by - overlap) if by > 0 else 0
        y1 = min(h, by + tile + overlap)
        for bx in xs:
            x0 = max(0, bx - overlap) if bx > 0 else 0
            x1 = min(w, bx + tile + overlap)
            with torch.no_grad():
                seg = net(x[:, :, y0:y1, x0:x1])
            peak_px = max(peak_px, seg.numel() // 3)
            # 整段（含 halo）都写回去：重叠区因此真被两块各算一遍再交叉混合
            mh = ramp(seg.shape[2], (by - y0) * s, (y1 - (by + min(tile, h - by))) * s)
            mv = ramp(seg.shape[3], (bx - x0) * s, (x1 - (bx + min(tile, w - bx))) * s)
            m = mh.view(1, 1, -1, 1) * mv.view(1, 1, 1, -1)
            oy0, ox0 = y0 * s, x0 * s
            out[:, :, oy0:oy0 + seg.shape[2], ox0:ox0 + seg.shape[3]] += seg * m
            weight[:, :, oy0:oy0 + seg.shape[2], ox0:ox0 + seg.shape[3]] += m
            tiles += 1
    out = out / weight.clamp_min(1e-6)
    return out.clamp(0.0, 1.0), {"tiles": tiles, "tile": int(tile),
                                 "overlap": int(overlap), "peak_px": int(peak_px),
                                 "scale": s}


class RealESRGAN:
    """超分后端：整幅或带重叠分块前向，返回放大后的 [0,1] 张量。不与 Lanczos 共用出口，
    否则报表里"确定性放大"与"神经网络超分"的成本与质量就成了同一个数。"""

    name = "realesrgan"

    def __init__(self, model_dir: str | None = None, device: str = "cuda", scale: int = 4):
        torch = _torch()
        self.torch = torch
        self.device = device
        self.scale = scale
        self.net = load_net(model_dir, device, scale=scale)

    def __call__(self, img, tile: int | None = None, overlap: int = INFER_OVERLAP):
        """img: (1,3,H,W) [0,1]。`tile=None` 走整幅（只该用于小图/取证），否则走分块。"""
        torch = self.torch
        x = img if img.is_cuda else img.to(self.device)
        if tile is None:
            with torch.no_grad():
                return self.net(x).clamp(0.0, 1.0), {"tiles": 1, "tile": 0,
                                                     "overlap": 0, "scale": self.scale,
                                                     "peak_px": int(x.shape[2] * x.shape[3]
                                                                    * self.scale * self.scale)}
        return forward_tiled(self.net, x, tile=tile, overlap=overlap)
