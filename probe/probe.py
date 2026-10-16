"""GPU 可行性打靶：在 AMD gfx1102 (RX 7600 XT) 上验证 ROCm 加速是否真能用。

判定项（每一项都是后续架构决策的依据）：
1. torch.version.hip 是否存在、设备是否被识别
2. 显存分配上限（消费级 A 卡常有 BAR / 大张量分配坑）
3. GEMM 吞吐（决定能否用 PyTorch 跑推理）
4. 卷积吞吐（LaMa / BiRefNet 的真实负载形态，比 GEMM 更能反映可用性）
5. 半精度可用性（RDNA3 的 fp16 是主要加速来源）
"""

import os
import platform
import sys
import time

import torch


def header(title):
    print(f"\n===== {title} =====", flush=True)


def gpu_init():
    header("1. 设备识别")
    print("torch", torch.__version__)
    print("hip version:", torch.version.hip)
    print("HSA_OVERRIDE_GFX_VERSION:", os.environ.get("HSA_OVERRIDE_GFX_VERSION", "(未设置)"))
    ok = torch.cuda.is_available()
    print("cuda/hip available:", ok)
    if not ok:
        return False
    dev = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(dev)
    print(f"name={props.name} gcnArch={props.gcnArchName} "
          f"multiProcessorCount={props.multi_processor_count} "
          f"total_memory={props.total_memory / 1024**3:.1f} GiB")
    return True


def alloc_ceiling():
    header("2. 显存分配阶梯")
    for gib in (1, 4, 8, 12, 16):
        try:
            t = torch.empty(int(gib * 1024**3 // 4), dtype=torch.float32, device="cuda")
            del t
            torch.cuda.empty_cache()
            print(f"  {gib:>2} GiB 分配: OK")
        except RuntimeError as e:
            print(f"  {gib:>2} GiB 分配: FAIL -> {str(e).splitlines()[0][:120]}")
            return gib
    return None


def bench(fn, iters=20, warmup=5):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / iters * 1000


def gemm():
    header("3. GEMM 吞吐 (4096^3)")
    for dt, label in ((torch.float32, "fp32"), (torch.float16, "fp16"), (torch.bfloat16, "bf16")):
        try:
            a = torch.randn(4096, 4096, device="cuda", dtype=dt)
            b = torch.randn(4096, 4096, device="cuda", dtype=dt)
            ms = bench(lambda: a @ b)
            tflops = 2 * 4096**3 / (ms / 1000) / 1e12
            print(f"  {label}: {ms:6.2f} ms  {tflops:6.1f} TFLOPS")
        except RuntimeError as e:
            print(f"  {label}: FAIL -> {str(e).splitlines()[0][:120]}")


def unet_conv():
    """LaMa / BiRefNet 的实际计算形态：中等通道数、多尺度卷积 + 实例归一化。"""
    header("4. 卷积负载 (U-Net 形态, 512x512 输入)")
    try:
        model = torch.nn.Sequential(
            torch.nn.Conv2d(3, 64, 3, padding=1), torch.nn.InstanceNorm2d(64), torch.nn.ReLU(),
            torch.nn.Conv2d(64, 128, 3, padding=1), torch.nn.InstanceNorm2d(128), torch.nn.ReLU(),
            torch.nn.Conv2d(128, 128, 3, padding=1), torch.nn.InstanceNorm2d(128), torch.nn.ReLU(),
            torch.nn.Conv2d(128, 64, 3, padding=1),
        ).cuda()
        x = torch.randn(1, 3, 512, 512, device="cuda")
        with torch.no_grad():
            ms = bench(lambda: model(x), iters=10, warmup=3)
        print(f"  fp32 前向: {ms:.1f} ms / 次")

        model = model.half()
        x = x.half()
        with torch.no_grad():
            ms = bench(lambda: model(x), iters=10, warmup=3)
        print(f"  fp16 前向: {ms:.1f} ms / 次")
        return True
    except RuntimeError as e:
        print(f"  FAIL -> {str(e).splitlines()[0][:200]}")
        return False


def einops_fft():
    """LaMa 的 FFN 依赖复数傅里叶变换，ROCm 上 fft 是已知薄弱点，单独验。"""
    header("5. FFT / 复数运算 (LaMa FFN 依赖)")
    try:
        x = torch.randn(2, 512, 512, device="cuda")
        ms = bench(lambda: torch.fft.rfft2(x), iters=20, warmup=5)
        print(f"  rfft2(2x512x512): {ms:.2f} ms  OK")
        c = torch.view_as_real(torch.fft.fftshift(torch.fft.fft2(x)))
        print(f"  复数张量回传 CPU 形状: {tuple(c.shape)}  OK")
        # 真实模型依赖 fft->逐点复数乘->ifft 的闭环，单独验往返精度
        spec = torch.fft.fft2(x)
        w = torch.randn(spec.shape, dtype=torch.cfloat, device="cuda")
        back = torch.fft.ifft2(spec * w).real
        ref = torch.fft.ifft2(torch.fft.fft2(x.cpu()) * w.cpu()).real
        err = (back.cpu() - ref).abs().max().item()
        print(f"  fft/复数乘/ifft 往返 GPU vs CPU 最大误差: {err:.3e}")
        return err < 1e-2
    except RuntimeError as e:
        print(f"  FAIL -> {str(e).splitlines()[0][:160]}")
        return False


def op_coverage():
    """精修管线真实会用到的算子，逐个验 ROCm 内核是否存在（缺失=运行时崩）。"""
    header("6. 算子覆盖 (真实精修管线依赖)")
    x = torch.randn(1, 32, 128, 128, device="cuda")
    checks = {
        "reflect pad + conv": lambda: torch.nn.functional.conv2d(
            torch.nn.functional.pad(x, (1, 1, 1, 1), mode="reflect"),
            torch.randn(32, 32, 3, 3, device="cuda"), padding=0),
        "conv_transpose2d":  lambda: torch.nn.ConvTranspose2d(32, 8, 4, stride=2).cuda()(x),
        "grid_sample(液化/塑形)": lambda: torch.nn.functional.grid_sample(
            x, torch.zeros(1, 64, 64, 2, device="cuda"), align_corners=False),
        "bilinear up/down(多尺度)": lambda: torch.nn.functional.interpolate(x, scale_factor=0.5, mode="bilinear"),
        "unfold(频域分离/Patch)":  lambda: x.unfold(2, 4, 2).unfold(3, 4, 2),
        "instance_norm":      lambda: torch.nn.InstanceNorm2d(32)(x),
        "layer_norm":         lambda: torch.nn.LayerNorm([32, 128, 128]).cuda()(x),
        "avg_pool + max_pool": lambda: (torch.nn.functional.avg_pool2d(x, 2),
                                        torch.nn.functional.max_pool2d(x, 2)),
        "cumsum(直方图/曲线)":   lambda: torch.cumsum(torch.randn(4096, device="cuda"), 0),
        "scatter/index_put":   lambda: torch.zeros(1000, device="cuda").index_put_(
            (torch.randint(0, 1000, (500,), device="cuda"),), torch.rand(500, device="cuda")),
        "fp16 storage 16bit图": lambda: torch.randn(1, 3, 2048, 2048, device="cuda",
                                                    dtype=torch.float16).float(),
    }
    bad = []
    for name, fn in checks.items():
        try:
            fn()
            torch.cuda.synchronize()
            print(f"  {name:<26} OK")
        except Exception as e:
            print(f"  {name:<26} FAIL -> {type(e).__name__}: {str(e).splitlines()[0][:100]}")
            bad.append(name)
    return not bad


def cpu_compare():
    """给一个同负载的 CPU 参照，量化 GPU 到底省了多少时间。"""
    header("7. CPU 参照 (12 线程)")
    torch.set_num_threads(os.cpu_count() or 12)
    m = torch.nn.Sequential(
        torch.nn.Conv2d(3, 64, 3, padding=1), torch.nn.ReLU(),
        torch.nn.Conv2d(64, 128, 3, padding=1), torch.nn.ReLU(),
        torch.nn.Conv2d(128, 128, 3, padding=1), torch.nn.ReLU(),
        torch.nn.Conv2d(128, 64, 3, padding=1))
    x = torch.randn(1, 3, 512, 512)
    with torch.no_grad():
        for _ in range(2):
            m(x)
        t0 = time.perf_counter()
        for _ in range(5):
            m(x)
        ms = (time.perf_counter() - t0) / 5 * 1000
    print(f"  同一 U-Net 负载 CPU: {ms:.1f} ms / 次")
    return ms


if __name__ == "__main__":
    print(f"平台: {platform.platform()} | torch {torch.__version__} | hip {torch.version.hip}")
    if not gpu_init():
        print("\n结论: 设备不可用，后续项跳过。")
        sys.exit(2)
    alloc_ceiling()
    gemm()
    conv_ok = unet_conv()
    fft_ok = einops_fft()
    ops_ok = op_coverage()
    cpu_ms = cpu_compare()
    header("综合")
    print(f"卷积可用={conv_ok} FFT往返正确={fft_ok} 算子全通过={ops_ok}")
    print("VERDICT=" + ("PASS" if (conv_ok and fft_ok and ops_ok) else "PARTIAL"))
