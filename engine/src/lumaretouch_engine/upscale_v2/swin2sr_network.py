# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 Microsoft Research and The HuggingFace Inc. team.
# Modified 2026 for LumaRetouch: fixed-configuration functional inference only.
# Adapted from transformers commit 9417c924af539be5f941c8a709a96b60dfe29eb3.
# See swin2sr_NOTICE.txt and swin2sr_LICENSE.txt. No model weights included.
"""CPU-only HF Swin2SR graph, with no Transformers or training dependency.

The checkpoint's 724 original HF keys are used directly: no guessed renaming.
Input windows must already share global phase 8 and global reflect padding.
This source is UNRUN: graph parity, tiled quality and performance are not accepted.
"""
import math

from .swin2sr_loader import load_state


def build_model(torch, checkpoint_bytes: bytes):
    """Return only a fully admitted, frozen model; never random fallback weights."""
    state = load_state(torch, checkpoint_bytes)
    nn = torch.nn
    f = nn.functional

    class FixedSwin2SR(nn.Module):
        scale = 2

        def __init__(self):
            super().__init__()
            self._key_to_buffer = {}
            for index, (key, tensor) in enumerate(state.items()):
                name = f'weight_{index}'
                self.register_buffer(name, tensor, persistent=True)
                self._key_to_buffer[key] = name
            mean = torch.tensor((0.4488, 0.4371, 0.4040), dtype=torch.float32, device='cpu').view(1, 3, 1, 1)
            self.register_buffer('rgb_mean', mean, persistent=False)
            axis = torch.arange(-7, 8, dtype=torch.float32, device='cpu')
            coords = torch.stack(torch.meshgrid(axis, axis, indexing='ij')).permute(1, 2, 0).unsqueeze(0)
            coords = coords / 7 * 8
            coords = torch.sign(coords) * torch.log2(torch.abs(coords) + 1) / math.log2(8)
            self.register_buffer('relative_coords', coords, persistent=False)
            axis_i = torch.arange(8, device='cpu')
            grid = torch.stack(torch.meshgrid(axis_i, axis_i, indexing='ij')).flatten(1)
            relative = (grid[:, :, None] - grid[:, None, :]).permute(1, 2, 0).contiguous()
            relative[:, :, 0] += 7
            relative[:, :, 1] += 7
            relative[:, :, 0] *= 15
            self.register_buffer('position_index', relative.sum(-1), persistent=False)

        def weight(self, key):
            return getattr(self, self._key_to_buffer[key])

        def linear(self, x, key, bias=True):
            return f.linear(x, self.weight(key + '.weight'), self.weight(key + '.bias') if bias else None)

        def conv(self, x, key, padding=1):
            return f.conv2d(x, self.weight(key + '.weight'), self.weight(key + '.bias'), padding=padding)

        def norm(self, x, key):
            return f.layer_norm(x, (180,), self.weight(key + '.weight'), self.weight(key + '.bias'), 1e-5)

        @staticmethod
        def partition(x):
            b, h, w, c = x.shape
            return x.reshape(b, h//8, 8, w//8, 8, c).permute(0, 1, 3, 2, 4, 5).reshape(-1, 64, c)

        @staticmethod
        def reverse(x, h, w):
            return x.reshape(-1, h//8, w//8, 8, 8, 180).permute(0, 1, 3, 2, 4, 5).reshape(-1, h, w, 180)

        def attention(self, x, key, mask):
            a = key + '.attention.self'
            nw = x.shape[0]
            def heads(value):
                return value.reshape(nw, 64, 6, 30).permute(0, 2, 1, 3)
            q = heads(self.linear(x, a + '.query'))
            k = heads(self.linear(x, a + '.key', False))
            v = heads(self.linear(x, a + '.value'))
            scores = f.normalize(q, dim=-1) @ f.normalize(k, dim=-1).transpose(-2, -1)
            scores = scores * torch.clamp(self.weight(a + '.logit_scale'), max=math.log(100)).exp()
            cpb = a + '.continuous_position_bias_mlp'
            table = self.linear(f.relu(self.linear(self.relative_coords, cpb + '.0')), cpb + '.2', False).reshape(-1, 6)
            bias = table[self.position_index.reshape(-1)].reshape(64, 64, 6).permute(2, 0, 1).contiguous()
            scores = scores + (16 * torch.sigmoid(bias)).unsqueeze(0)
            if mask is not None:
                count = mask.shape[0]
                scores = scores.reshape(nw//count, count, 6, 64, 64)
                # Preserve the pinned HF implementation's two mask additions.
                scores = scores + mask[None, :, None] + mask[None, :, None]
                scores = scores.reshape(-1, 6, 64, 64)
            y = (f.softmax(scores, dim=-1) @ v).permute(0, 2, 1, 3).contiguous().reshape(nw, 64, 180)
            return self.linear(y, key + '.attention.output.dense')

        def shifted_mask(self, h, w):
            grid = torch.zeros((1, h, w, 1), dtype=torch.float32, device='cpu')
            slices = (slice(0, -8), slice(-8, -4), slice(-4, None))
            count = 0
            for hs in slices:
                for ws in slices:
                    grid[:, hs, ws, :] = count
                    count += 1
            windows = self.partition(grid).reshape(-1, 64)
            diff = windows.unsqueeze(1) - windows.unsqueeze(2)
            return diff.masked_fill(diff != 0, -100.0).masked_fill(diff == 0, 0.0)

        def forward(self, x):
            if (self.training or type(x) is not torch.Tensor or x.device.type != 'cpu'
                    or x.dtype != torch.float32 or x.ndim != 4 or x.shape[:2] != (1, 3)
                    or x.requires_grad or torch.is_grad_enabled()):
                raise ValueError('Swin2SR requires frozen CPU float32 N=1 RGB under inference/no_grad mode')
            h, w = x.shape[-2:]
            if min(h, w) < 16 or h % 8 or w % 8 or h*w > 1024*1024:
                raise ValueError('Swin2SR window must be bounded and phase-8 aligned, dimensions >=16')
            if not bool(torch.isfinite(x).all().item()) or bool(((x < 0) | (x > 1)).any().item()):
                raise ValueError('Swin2SR input must be finite encoded RGB in [0,1]')
            shallow = self.conv(x - self.rgb_mean, 'swin2sr.first_convolution')
            tokens = self.conv(shallow, 'swin2sr.embeddings.patch_embeddings.projection', 0)
            tokens = self.norm(tokens.flatten(2).transpose(1, 2), 'swin2sr.embeddings.patch_embeddings.layernorm')
            mask = self.shifted_mask(h, w)
            for stage in range(6):
                prefix = f'swin2sr.encoder.stages.{stage}'
                residual = tokens
                for layer in range(6):
                    key = prefix + f'.layers.{layer}'
                    shifted = tokens.reshape(1, h, w, 180)
                    if layer % 2:
                        shifted = torch.roll(shifted, (-4, -4), (1, 2))
                    windows = self.attention(self.partition(shifted), key, mask if layer % 2 else None)
                    output = self.reverse(windows, h, w)
                    if layer % 2:
                        output = torch.roll(output, (4, 4), (1, 2))
                    tokens = tokens + self.norm(output.reshape(1, h*w, 180), key + '.layernorm_before')
                    mlp = self.linear(f.gelu(self.linear(tokens, key + '.intermediate.dense'), approximate='none'), key + '.output.dense')
                    tokens = tokens + self.norm(mlp, key + '.layernorm_after')
                image = tokens.transpose(1, 2).reshape(1, 180, h, w)
                image = self.conv(image, prefix + '.conv')
                image = self.conv(image, prefix + '.patch_embed.projection', 0)
                tokens = image.flatten(2).transpose(1, 2) + residual
            image = self.norm(tokens, 'swin2sr.layernorm').transpose(1, 2).reshape(1, 180, h, w)
            image = self.conv(image, 'swin2sr.conv_after_body') + shallow
            image = f.leaky_relu(self.conv(image, 'upsample.conv_before_upsample'), negative_slope=0.01)
            image = f.pixel_shuffle(self.conv(image, 'upsample.upsample.convolution_0'), 2)
            return self.conv(image, 'upsample.final_convolution') + self.rgb_mean

    model = FixedSwin2SR()
    model.eval()
    model.requires_grad_(False)
    return model
