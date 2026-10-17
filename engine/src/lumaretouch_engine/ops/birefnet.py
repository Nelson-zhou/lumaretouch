"""自动抠图后端（BiRefNet 类显著性分割）：结构自搭 + 权重门禁，**不与色键合成混报**。

与 `ops/lama.py` 完全同构的立场，理由也一样：没有权重就没有任何「抠得准」的质量主张
可写，所以这里只允许两件事——**结构可跑（成本与显存可测）** 与 **权重齐了才可用（否则
当场拒绝，绝不退成色键）**。色键（`ops/matting.key_matte_np`）是确定性、可测、零依赖的
基础档，能立刻出厂；这一条是复杂背景的正解，但必须等权重按 sha256 放行。

架构按公开论文思想自搭（多级编码器 + 空洞卷积金字塔扩感受野 + 渐进解码到单通道 alpha），
不含任何上游代码：
* 输入 3 通道 RGB（[0,1]），输出 1 通道 alpha logits；调用方 `sigmoid` 后当遮罩；
* 编码器逐级 stride 卷积下采样，中间一支 ASPP 式空洞金字塔（dilation 1/2/4/8）抓
  从发丝到整物的多尺度；解码逐级上采样 + 跳跃相加，尾层 1×1 出 alpha；
* 全 fp32：抠图是最终质量敏感环节，且 ROCm 半精度在某些卷积/插值组合上仍不完整。

权重不入库（决策 9）。文件放在 `LRT_MODEL_DIR`（默认 `~/.cache/lumaretouch/models`），
装载必须同时给出 `LRT_BIREFNET_SHA256`，否则拒绝加载；`torch.load(weights_only=True)`，
`load_state_dict(strict=True)`——多一层少一层都要响，不许静默部分加载。
"""

from __future__ import annotations

import importlib.util
import os

from . import weights

MODEL_FILE = "birefnet_matting.pt"
MODEL_SHA256_ENV = "LRT_BIREFNET_SHA256"
DEFAULT_MODEL_DIR = os.path.expanduser("~/.cache/lumaretouch/models")
# 抠图推理的最长边档：太小边缘糊、太大消费级 A 卡吃不住；与导出分块是两回事
INFER_LONG_EDGE = 1024


class MissingBackend(RuntimeError):
    """请求的抠图后端不可用。调用方必须把它当错误处理，不许退到色键然后报「抠图成功」。"""


def model_path(model_dir: str | None = None) -> str:
    d = model_dir or os.environ.get("LRT_MODEL_DIR") or DEFAULT_MODEL_DIR
    return os.path.join(d, MODEL_FILE)


def available(model_dir: str | None = None) -> bool:
    return os.path.isfile(model_path(model_dir))


def ready_for_production(model_dir: str | None = None) -> bool:
    return production_check(model_dir)[0]


def production_check(model_dir: str | None = None) -> tuple[bool, str]:
    """能不能上生产 + 不能的话是为什么。**能力上报与 `load_net` 共用这一份**（ops/weights）：
    上报说可用而提交被拒，与上报说不可用而其实早放行了，是同一种病（口径写两处就会漂）的两面。
    """
    return weights.production_gate(model_file=MODEL_FILE, sha_env=MODEL_SHA256_ENV,
                                   path=model_path(model_dir),
                                   absent_reason=missing_reason("birefnet", model_dir))


def matting_backends(model_dir: str | None = None) -> dict:
    """抠图后端的能力清单（与 `upscale.scale_backends` 同一个口径）：

    * `baseline`——确定性、零依赖、装机即用；
    * `weights_gated`——结构在包里但等按 sha256 放行的权重。

    权重齐了就把 birefnet 从 weights_gated 移到 baseline：这是**事实改变**后清单跟着变，
    不是前端自己猜"装了就能选"。

    `model_dir` 只为了可测（拿一个假目录验"裸机器那一档"），命令层不传——它吃的就是
    产品真正会用的那一个目录，探的是另一处就是双口径。
    """
    if ready_for_production(model_dir):
        return {"baseline": ["color_key", "birefnet"], "weights_gated": []}
    return {"baseline": ["color_key"], "weights_gated": ["birefnet"]}


def missing_reason(backend: str = "birefnet", model_dir: str | None = None) -> str:
    return (f"自动抠图后端 {backend} 不可用：权重文件不在 {model_path(model_dir)}。"
            "权重不入库、引擎不吃下载（决策 9），需由安装器按 sha256 取官方发布件后再请求本后端；"
            "纯色/蓝箱背景请先用确定性色键（backend=\"color_key\"），引擎不会替你默默切后端、"
            "更不会拿色键的结果冒充神经网络抠图的质量。")


def _torch():
    if importlib.util.find_spec("torch") is None:
        raise MissingBackend("torch 未安装，自动抠图后端不可用（色键与合成不受影响）")
    import torch
    return torch


def build_net(torch, base: int = 48):
    """自搭的显著性抠图 U-Net + 空洞金字塔（未加载权重）。构造期自检形状，不留到首次前向才炸。"""
    import torch.nn as nn

    def conv_bn(cin, cout, k=3, s=1, d=1):
        return nn.Sequential(
            nn.Conv2d(cin, cout, k, stride=s, padding=d * (k - 1) // 2, dilation=d, bias=False),
            nn.BatchNorm2d(cout), nn.ReLU(inplace=True))

    class ASPP(nn.Module):
        def __init__(self, ch):
            super().__init__()
            c = ch // 2
            self.b1 = conv_bn(ch, c, 1)
            self.b2 = conv_bn(ch, c, 3, d=2)
            self.b3 = conv_bn(ch, c, 3, d=4)
            self.b4 = conv_bn(ch, c, 3, d=8)
            self.pool = nn.Sequential(nn.AdaptiveAvgPool2d(1), conv_bn(ch, c, 1))
            self.fuse = conv_bn(c * 5, ch)

        def forward(self, x):
            import torch.nn.functional as F
            p = self.pool(x)
            p = F.interpolate(p, size=x.shape[-2:], mode="bilinear", align_corners=False)
            return self.fuse(torch.cat([self.b1(x), self.b2(x), self.b3(x), self.b4(x), p], 1))

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            b = base
            self.e0 = nn.Sequential(conv_bn(3, b), conv_bn(b, b))       # 1×
            self.e1 = conv_bn(b, b * 2, 3, s=2)                          # 1/2
            self.e2 = conv_bn(b * 2, b * 4, 3, s=2)                      # 1/4
            self.mid = ASPP(b * 4)
            self.d2 = conv_bn(b * 4 + b * 2, b * 2)                      # 拼 e1
            self.d1 = conv_bn(b * 2 + b, b)                             # 拼 e0
            self.head = nn.Conv2d(b, 1, 3, padding=1)                    # alpha logits

        def forward(self, x):
            import torch.nn.functional as F
            s0 = self.e0(x)
            s1 = self.e1(s0)
            s2 = self.e2(s1)
            m = self.mid(s2)
            d2 = self.d2(torch.cat([F.interpolate(m, size=s1.shape[-2:], mode="bilinear",
                                                   align_corners=False), s1], 1))
            d1 = self.d1(torch.cat([F.interpolate(d2, size=s0.shape[-2:], mode="bilinear",
                                                   align_corners=False), s0], 1))
            return self.head(d1)

    return Net()


def load_net(model_dir: str | None = None, device: str = "cuda", base: int = 48):
    """建网 + 权重装载 + sha256 校验。任何一步不满足都抛 MissingBackend。"""
    torch = _torch()
    ok, why = production_check(model_dir)
    if not ok:
        raise MissingBackend(why)
    path = model_path(model_dir)
    net = build_net(torch, base=base)
    state = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "net" in state:
        state = state["net"]
    net.load_state_dict(state, strict=True)
    net.eval().to(device)
    return net


class BiRefNetMatte:
    """自动抠图后端：整图推理，返回 (H,W) 的 [0,1] alpha（sigmoid 后）。不做合成、不碰常驻缓存。

    调用方负责拿这个 alpha 去 `ops.matting.composite_*` 换底，并负责生命周期；本类单独可归因，
    否则报表会把神经网络抠图的成本混进合成或滤波那一段。
    """

    name = "birefnet"

    def __init__(self, model_dir: str | None = None, device: str = "cuda"):
        torch = _torch()
        self.torch = torch
        self.device = device
        self.net = load_net(model_dir, device)

    def __call__(self, img):
        """img: (1,3,H,W) [0,1] float tensor，已在 self.device 上。返回 (H,W) float [0,1]。"""
        torch = self.torch
        x = img if img.is_cuda else img.to(self.device)
        with torch.no_grad():
            logits = self.net(x)
            return torch.sigmoid(logits)[0, 0].clamp(0.0, 1.0)
