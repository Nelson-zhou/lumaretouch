"""CPU Rust stage used identically by preview and export; no uint8 intermediary."""
import numpy as np
from . import primary_calibration_state as S
from .primary_calibration_native import apply, admit


class PrimaryCalibrationStage:
    def __init__(self, recipe):
        self.recipe = admit(recipe)
        self.active = S.active(self.recipe)
        self.cancelled = lambda: False

    def apply_np(self, pixels, *, encoding='extended-srgb-d65', cancelled=None):
        cancelled = cancelled or self.cancelled
        if not self.active:
            return pixels  # Legacy neutral bypass does not constrain other effects.
        # The current host's photographic pipeline is encoded extended sRGB.
        # ICC/non-sRGB source conversion is the decoder's responsibility.
        if not isinstance(pixels, np.ndarray) or pixels.ndim != 3 or pixels.shape[2] != 3 or pixels.dtype not in (np.dtype('uint8'), np.dtype('uint16'), np.dtype('float32')):
            raise ValueError('Primary calibration requires RGB8/RGB16/float32 HWC')
        if encoding not in ('linear-srgb-d65', 'extended-srgb-d65'):
            raise ValueError('Primary calibration encoding is unknown')
        if cancelled():
            raise InterruptedError('Primary calibration cancelled')
        if min(pixels.shape[:2]) < 1 or pixels.size > 300_000_000 or not np.isfinite(pixels).all():
            raise ValueError('Primary calibration RGB exceeds bounds or is non-finite')
        if pixels.dtype == np.float32 and np.max(np.abs(pixels)) > (65504 if encoding == 'linear-srgb-d65' else 128):
            raise ValueError('Primary calibration RGB exceeds working-domain headroom')
        if not self.active:
            return pixels
        if pixels.dtype == np.float32:
            return apply(pixels, self.recipe, encoding=encoding, cancelled=cancelled)
        # Integer API is a terminal SDR adapter, clipping only at quantization.
        if encoding != 'extended-srgb-d65':
            raise ValueError('Integer RGB must be explicitly encoded sRGB')
        maximum = np.iinfo(pixels.dtype).max
        result = apply(pixels.astype(np.float32) / maximum, self.recipe, encoding=encoding, cancelled=cancelled)
        return np.rint(np.clip(result, 0, 1) * maximum).astype(pixels.dtype)

    def apply_t(self, pixels, *, cancelled=None):
        if not self.active:
            return pixels  # No CPU/GPU transfer, synchronization or quantization.
        cancelled = cancelled or self.cancelled
        import torch
        if pixels.ndim != 4 or pixels.shape[1] != 3 or not pixels.is_floating_point():
            raise ValueError('Primary calibration requires NCHW floating RGB')
        if pixels.numel() == 0 or pixels.numel() > 300_000_000 or not bool(torch.isfinite(pixels).all()) or bool((pixels.abs() > 128).any()):
            raise ValueError('Primary calibration tensor exceeds supported RGB domain')
        if cancelled():
            raise InterruptedError('Primary calibration cancelled')
        if not self.active:
            return pixels
        # Explicit CPU bridge is correct but NOT a GPU/performance completion claim.
        images = []
        for image in pixels.detach().float().cpu():
            result = self.apply_np(image.permute(1, 2, 0).contiguous().numpy(), cancelled=cancelled)
            images.append(torch.from_numpy(result).permute(2, 0, 1))
        return torch.stack(images).to(device=pixels.device, dtype=torch.float32)
