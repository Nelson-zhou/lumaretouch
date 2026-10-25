# SPDX-License-Identifier: Apache-2.0
# Copyright 2018-2022 BasicSR Authors
# Modified 2026 for LumaRetouch: isolated inference-only compatibility adaptation.
# See LICENSE.BasicSR.txt and NOTICE in this directory. No model weights included.
"""Private, unexecuted compatibility graph, not an installed AI capability.

Adapted from BasicSR's RRDBNet at 651835a1b9d38dbbdaf45750f56906be2364f01a.
No BasicSR registry, training initialization, torchvision, downloader or CLI is
imported. The caller supplies a reviewed Torch runtime. This module does not
open/deserialise checkpoint files; all state must already have been safely
loaded from an admitted byte artifact before calling the private constructor.
"""

from collections import OrderedDict

from .architecture import architecture_for, expected_parameter_shapes


def _validate_checkpoint_state(torch, checkpoint, model_id: str):
    """Prefer params_ema; malformed EMA must not fall back to params.

This validates tensors after deserialization, so it is NOT a safe-load boundary
by itself. A future loader must hash bounded, local, immutable checkpoint bytes
first, use explicit weights_only=True, and have no pickle/allowlist fallback.
"""
    if type(checkpoint) not in (dict, OrderedDict):
        raise ValueError("checkpoint must have an official params envelope")
    key = "params_ema" if "params_ema" in checkpoint else "params"
    if key not in checkpoint or type(checkpoint[key]) not in (dict, OrderedDict):
        raise ValueError(f"checkpoint {key} is missing or malformed")
    state = checkpoint[key]
    if any(type(name) is not str for name in state):
        raise ValueError("checkpoint keys must be strings")
    expected = expected_parameter_shapes(model_id)
    if set(state) != set(expected):
        raise ValueError("checkpoint tensor keys do not match the pinned architecture")
    for name, shape in expected.items():
        value = state[name]
        if type(value) is not torch.Tensor:
            raise ValueError(f"{name}: plain tensors only, no tensor subclasses")
        if tuple(value.shape) != shape or value.dtype != torch.float32:
            raise ValueError(f"{name}: expected shape {shape} with float32 dtype")
        if value.device.type != "cpu" or value.layout != torch.strided:
            raise ValueError(f"{name}: expected a dense CPU tensor")
        if value.requires_grad or not value.is_contiguous() or value.storage_offset() != 0:
            raise ValueError(f"{name}: noncanonical checkpoint storage")
        if value.untyped_storage().nbytes() != value.numel() * 4:
            raise ValueError(f"{name}: tensor storage is larger than its declared payload")
        if not bool(torch.isfinite(value).all().item()):
            raise ValueError(f"{name}: nonfinite checkpoint tensor")
    return state, key


def _build_from_verified_checkpoint(torch, checkpoint, model_id: str):
    """Private graph construction after external byte/runtime/license admission.

No public path calls this in the current revision. Constructing a correct graph
does not authorize inference or make an unreviewed checkpoint trustworthy.
Returns no random/unloaded network and does not silently change device/dtype.
Training-only BasicSR default_init_weights is omitted because every parameter
is overwritten by strict checkpoint loading before the graph can be returned.
"""
    spec = architecture_for(model_id)
    state, envelope = _validate_checkpoint_state(torch, checkpoint, model_id)
    nn = torch.nn
    functional = nn.functional

    class ResidualDenseBlock(nn.Module):
        def __init__(self):
            super().__init__()
            for index in range(1, 6):
                inputs = spec.features + (index - 1) * spec.growth
                outputs = spec.features if index == 5 else spec.growth
                setattr(self, f"conv{index}", nn.Conv2d(
                    inputs, outputs, 3, 1, 1, device="cpu", dtype=torch.float32,
                ))
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        def forward(self, value):
            features = [value]
            for index in range(1, 5):
                joined = features[0] if index == 1 else torch.cat(features, dim=1)
                features.append(self.lrelu(getattr(self, f"conv{index}")(joined)))
            residual = self.conv5(torch.cat(features, dim=1))
            return residual * 0.2 + value

    class RRDB(nn.Module):
        def __init__(self):
            super().__init__()
            self.rdb1 = ResidualDenseBlock()
            self.rdb2 = ResidualDenseBlock()
            self.rdb3 = ResidualDenseBlock()

        def forward(self, value):
            residual = self.rdb3(self.rdb2(self.rdb1(value)))
            return residual * 0.2 + value

    class RRDBNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.scale = spec.scale
            def conv(inputs, outputs):
                return nn.Conv2d(inputs, outputs, 3, 1, 1, device="cpu", dtype=torch.float32)

            self.conv_first = conv(3 * spec.input_unshuffle ** 2, spec.features)
            self.body = nn.Sequential(*(RRDB() for _ in range(spec.blocks)))
            self.conv_body = conv(spec.features, spec.features)
            self.conv_up1 = conv(spec.features, spec.features)
            self.conv_up2 = conv(spec.features, spec.features)
            self.conv_hr = conv(spec.features, spec.features)
            self.conv_last = conv(spec.features, 3)
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        def forward(self, value):
            if value.ndim != 4 or value.shape[0] != 1 or value.shape[1] != 3:
                raise ValueError("model input must be RGB NCHW [1,3,H,W]")
            if value.dtype != torch.float32 or not value.is_contiguous():
                raise ValueError("model input must be contiguous float32")
            height, width = value.shape[2:]
            phase = spec.input_unshuffle
            if height < phase or width < phase or height % phase or width % phase:
                raise ValueError("input does not match the global pixel-unshuffle grid")
            if phase != 1:
                value = value.reshape(1, 3, height // phase, phase, width // phase, phase)
                value = value.permute(0, 1, 3, 5, 2, 4).reshape(
                    1, 3 * phase ** 2, height // phase, width // phase,
                )
            feature = self.conv_first(value)
            feature = feature + self.conv_body(self.body(feature))
            feature = self.lrelu(self.conv_up1(functional.interpolate(
                feature, scale_factor=2, mode="nearest",
            )))
            feature = self.lrelu(self.conv_up2(functional.interpolate(
                feature, scale_factor=2, mode="nearest",
            )))
            return self.conv_last(self.lrelu(self.conv_hr(feature)))

    network = RRDBNet()
    network.load_state_dict(state, strict=True)
    network.requires_grad_(False)
    network.eval()
    return network, envelope
