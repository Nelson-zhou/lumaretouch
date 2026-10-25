# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-precision immutable decode and existing ordered repair math. UNRUN."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Captured:
    content: bytes
    input_sha256: str
    source_bits: int


def poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Neck source capture cancelled before publication')


def capture(loader, operations, source, *, byte_budget, cancelled):
    """No proxy, output bit-depth or cached corrected image enters this path."""
    import numpy as np
    from .portrait_fit_source import _freeze
    pixels = source['width'] * source['height']
    # Conservative source + full replay/solver reservation, not measured peak.
    # Each operation is materialized separately; masks do not accumulate.
    reserve = (256*pixels + 64*1024**2) if operations else 0
    if type(byte_budget) is not int or byte_budget <= reserve:
        raise MemoryError('Neck canonical repair replay exceeds remaining source budget')
    poll(cancelled)
    base = loader(byte_budget=byte_budget-reserve, cancelled=lambda: bool(cancelled and cancelled()))
    if base.source != source:
        raise ValueError('Neck decoder returned another immutable source')
    if not operations:
        return Captured(base._content, base.input_sha256, base.source_bits)
    from .optional_dependencies import optional_module
    torch = optional_module('torch')
    if torch is None:
        raise ValueError('Canonical neck repair replay requires the existing Torch repair backend')
    from .repair_source_materialization import materialize
    from .repair_replay import replay_repair_t
    # Writable private copy: Torch must never receive immutable bytes as writable.
    cur = torch.from_numpy(np.array(base.pixels, copy=True)).permute(2, 0, 1).unsqueeze(0)
    bits = base.source_bits
    del base
    for op in operations:
        poll(cancelled)
        full = materialize([op], (source['height'], source['width']))
        cur, _, _ = replay_repair_t(cur, full)
        del full
    poll(cancelled)
    rgb = cur.squeeze(0).permute(1, 2, 0).detach().cpu().numpy()
    content, digest = _freeze(rgb, source, lambda: bool(cancelled and cancelled()))
    return Captured(content, digest, bits)
