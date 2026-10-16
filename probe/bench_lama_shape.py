"""真实负载靶：LaMa 形状（含频域复数混合的 U-Net）在 gfx1102 上的耗时与显存实测。

不下权重、不抄任何仓库代码，架构按公开论文思想自搭。要回答的是工程问题：
  1. 512/1024/2048 修复窗口在 A 卡上多少毫秒 → 交互延迟是否可接受
  2. 峰值显存多少 → 全图/大图要不要分块与 fp16
  3. 同负载 CPU 参照 → GPU 加速到底带来几倍
"""

import time

import torch
import torch.nn as nn
import torch.nn.functional as F


class FFTMix(nn.Module):
    """LaMa 的 FFC 核心：fft -> 通道间复数全连接乘 -> ifft。"""

    def __init__(self, ch):
        super().__init__()
        self.register_buffer("wr", torch.randn(ch, ch) * 0.05)
        self.register_buffer("wi", torch.randn(ch, ch) * 0.05)

    def forward(self, x):
        # 复数 FFT 在 ROCm/CUDA 上都建议走 fp32；半精度复数支持不完整
        dtype = x.dtype
        xf = x.float()
        spec = torch.fft.fft2(xf)                                    # (B,C,H,W) complex
        w = torch.complex(self.wr.float(), self.wi.float())
        mixed = torch.einsum("bchw,cj->bjhw", spec, w)                # 通道间复数混合
        return torch.fft.ifft2(mixed).real.to(dtype)
        # 说明：真实 FFC 还会在实/虚部上接一个 1x1 conv；此处省略不影响
        # 本靶要测的成本主体（fft + 复数 einsum + ifft）。


class ResBlk(nn.Module):
    def __init__(self, ch):
        super().__init__()
        self.body = nn.Sequential(nn.Conv2d(ch, ch, 3, padding=1), nn.ReLU(),
                                  nn.Conv2d(ch, ch, 3, padding=1))
        self.fft = FFTMix(ch)

    def forward(self, x):
        return x + self.body(x) + self.fft(x)


class LamaShape(nn.Module):
    def __init__(self, ch=48, n_blocks=3):
        super().__init__()
        c = ch
        # 编码：3 次 /2 → 分辨率 1/8，通道 c, 2c, 4c
        self.enc = nn.ModuleList([
            nn.Conv2d(4 if i == 0 else c * (2 ** (i - 1)), c * (2 ** i), 4, 2, 1)
            for i in range(3)])
        self.mid = nn.Sequential(*[ResBlk(c * 4) for _ in range(n_blocks)])
        # 解码：3 次 x2 → 回到原分辨率
        self.dec = nn.ModuleList([
            nn.ConvTranspose2d(c * (2 ** (2 - j)), c * (2 ** (1 - j)) if j < 2 else c // 2,
                              4, 2, 1)
            for j in range(3)])
        self.out = nn.Conv2d(c // 2, 3, 3, padding=1)

    def forward(self, img, mask):
        x = torch.cat([img, mask], 1)
        for e in self.enc:
            x = F.relu(e(x))
        x = self.mid(x)
        for d in self.dec:
            x = F.relu(d(x))
        return self.out(x)


def bench(model, side, dtype, device, iters=3):
    img = torch.randn(1, 3, side, side, device=device, dtype=dtype)
    msk = (torch.rand(1, 1, side, side, device=device) > 0.9).to(dtype)
    with torch.no_grad():
        model(img, msk)
        if device == "cuda":
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        for _ in range(iters):
            out = model(img, msk)
        if device == "cuda":
            torch.cuda.synchronize()
        ms = (time.perf_counter() - t0) / iters * 1000
    peak = torch.cuda.max_memory_allocated() / 1024**2 if device == "cuda" else float("nan")
    return ms, peak, tuple(out.shape)


if __name__ == "__main__":
    props = torch.cuda.get_device_properties(0)
    print(f"设备: {props.name} / {props.gcnArchName} / {props.multi_processor_count} CU / "
          f"{props.total_memory/1024**3:.0f} GiB")
    print(f"torch {torch.__version__} hip {torch.version.hip}")

    tiles = 6 * 4  # 24 MP 图按 1024 窗口切 6x4
    for dtype, dname in ((torch.float32, "fp32"), (torch.float16, "fp16")):
        m = LamaShape(ch=48, n_blocks=3).to(device="cuda", dtype=dtype).eval()
        n = sum(p.numel() for p in m.parameters()) / 1e6
        print(f"\n===== GPU {dname} (自搭 LaMa 形状, {n:.0f}M 参数) =====")
        ms_1024 = None
        for side in (512, 1024, 2048):
            try:
                ms, peak, shape_ = bench(m, side, dtype, "cuda")
                print(f"  {side}x{side}: {ms:8.1f} ms   峰值 {peak:6.0f} MiB   输出{shape_}")
                if side == 1024:
                    ms_1024 = ms
            except RuntimeError as e:
                print(f"  {side}x{side}: FAIL -> {str(e).splitlines()[0][:120]}")
        if ms_1024:
            print(f"  → 24 MP 整图分块({tiles} 块 1024 窗口) 估计 {ms_1024 * tiles / 1000:.1f} s")

    print("\n===== CPU 参照 (fp32, 同负载) =====")
    torch.set_num_threads(12)
    mc = LamaShape(ch=48, n_blocks=3).eval()
    for side in (512, 1024):
        ms, _, _ = bench(mc, side, torch.float32, "cpu", iters=2)
        print(f"  {side}x{side}: {ms:8.1f} ms")
