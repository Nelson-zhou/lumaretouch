"""One frozen pre-WB stage, shared geometry/risk/coverage and memory admission.

Only 1024 stratum centres cross to CPU. This is not a screenshot, a neutral
picker region, an analysis of already-WB pixels, or an upscaled proxy export.
"""
from .color_action_sampling import _input, _same, _lin_t

GRID = 32


def require_support(spec):
    xa, ya, xb, yb = spec.integer_crop
    # Projection intentionally resizes to the fixed proxy. A tiny crop must not
    # become 1024 apparently independent samples by that presentation resize.
    if min(spec.width, spec.height, xb-xa, yb-ya, *spec.rotated) < GRID:
        raise ValueError('自动白平衡至少需要 32×32 的有效裁剪输入；不会放大小裁剪制造独立取样')


def sample(pipeline, spec, strength, channel, params, *, available=None):
    require_support(spec)
    stage = _input(pipeline, spec, strength, channel, params, available)
    import torch
    # Deterministic integer centres, unique when each dimension >= GRID.
    xs = torch.tensor([(2*i+1)*spec.width//(2*GRID) for i in range(GRID)], device=stage.device)
    ys = torch.tensor([(2*i+1)*spec.height//(2*GRID) for i in range(GRID)], device=stage.device)

    def gather(tensor):
        # Small indexed result before CPU conversion; no whole-image .tolist().
        return tensor[0, :, ys[:, None], xs[None, :]].permute(1, 2, 0).reshape(GRID*GRID, -1).detach().to(device='cpu', dtype=torch.float64).tolist()

    rgb = gather(spec.apply(_lin_t(stage)))
    coverage = gather(spec.apply(torch.ones_like(stage[:, :1])))
    source_risk = ((stage >= 1.0) | (stage < 0.0)).any(dim=1, keepdim=True).to(dtype=stage.dtype)
    risk = gather(spec.apply(source_risk))
    _same(pipeline, spec)
    return tuple(tuple(pixel + cover + bad) for pixel, cover, bad in zip(rgb, coverage, risk))
