# SPDX-License-Identifier: GPL-3.0-or-later
"""Versioned, lower-copy portrait export source materialization. AUTHORED / UNRUN.

This bounds only the private RGB materialization phase. It does not admit the
semantic resampler, portrait solvers, repair replay, tensor preview or process
RSS. Those owners retain their existing independent checks and budgets.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


MATERIALIZATION_VERSION = 1
BLOCK_PIXELS = 65_536
MAX_OWNER_DEPTH = 64
BLOCK_WORKSPACE_OVERHEAD = 65_536


class UnsupportedSourceLayout(ValueError):
    """Structurally valid RGB with an owner this optional phase cannot inspect.

    Only this structural refusal may select the explicit legacy path, before
    materialization starts. Invalid pixels, budgets and cancellation never do.
    """


@dataclass(frozen=True, slots=True)
class SourceMaterializationPlan:
    version: int
    shape: tuple[int, int, int]
    source_storage_bytes: int
    output_bytes: int
    block_workspace_bytes: int
    peak_bytes: int
    bounds_kind: str = 'source-materialization-working-set-with-explicit-scratch'
    runtime_verified: bool = False


def _source(source, divisor):
    if (type(source) is not np.ndarray or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 1):
        raise ValueError('Portrait source materialization requires nonempty RGB pixels')
    if source.dtype == np.uint8:
        expected = 255
    elif source.dtype == np.uint16:
        expected = 65535
    elif source.dtype == np.float32:
        expected = 1
    else:
        raise ValueError('Portrait source materialization requires RGB8, RGB16 or working float32')
    if (not source.dtype.isnative or source.dtype.metadata is not None
            or source.dtype.fields is not None):
        raise ValueError('Portrait source materialization requires an ordinary numeric dtype')
    if type(divisor) is not int or divisor != expected:
        raise ValueError('Portrait source divisor does not match its original precision')


def _span(array):
    """Half-open address interval of every sample, without flattening/copying."""
    low = high = int(array.ctypes.data)
    for count, stride in zip(array.shape, array.strides):
        extent = (int(count) - 1) * int(stride)
        low += min(0, extent)
        high += max(0, extent)
    return low, high + int(array.dtype.itemsize)


def _owner_bytes(source):
    current = source
    seen = set()
    arrays = []
    while True:
        identity = id(current)
        if identity in seen:
            raise ValueError('Portrait source backing chain is cyclic')
        if len(seen) >= MAX_OWNER_DEPTH:
            raise UnsupportedSourceLayout('Portrait source backing chain exceeds inspection depth')
        seen.add(identity)
        if type(current) is np.ndarray:
            if (current.dtype.hasobject or current.dtype.fields is not None
                    or current.dtype.metadata is not None):
                raise UnsupportedSourceLayout('Portrait source has an unsupported backing dtype')
            arrays.append(current)
            if current.base is not None:
                current = current.base
                continue
            if not current.flags.owndata or not (current.flags.c_contiguous or current.flags.f_contiguous):
                raise UnsupportedSourceLayout('Portrait source has an unknown or strided owning allocation')
            owner_start = int(current.ctypes.data)
            owner_size = int(current.nbytes)
            break
        if type(current) is memoryview:
            if not current.contiguous:
                raise UnsupportedSourceLayout('Portrait source has a noncontiguous buffer wrapper')
            current = current.obj
            continue
        if type(current) in (bytes, bytearray):
            owner_size = len(current)
            # A metadata-only view locates the complete buffer. No pixel bytes
            # are allocated, converted or copied during owner inspection.
            owner_view = np.frombuffer(current, dtype=np.uint8)
            owner_start = int(owner_view.ctypes.data)
            break
        raise UnsupportedSourceLayout('Portrait source has an unsupported backing owner')
    owner_end = owner_start + owner_size
    for array in arrays:
        if not array.size:
            continue
        start, end = _span(array)
        if start < owner_start or end > owner_end:
            raise ValueError('Portrait source view exceeds its recognized backing allocation')
    return owner_size


def inspect_export_source(source, divisor):
    """Inspect actual retained backing and planned copies, without reading pixels.

    Views charge their complete terminal owner, not only visible ``nbytes``.
    Exact ndarray/bytes/bytearray owners are recognized; opaque buffer wrappers,
    memmaps, ndarray subclasses and unknown ownership remain the legacy owner's
    responsibility. The source keeps its backing alive throughout this phase.
    """
    _source(source, divisor)
    owner_bytes = _owner_bytes(source)
    pixels = int(source.shape[0]) * int(source.shape[1])
    output_bytes = pixels * 12
    # The unchanged cast/divide expression may overlap two float32 RGB blocks.
    # Finite/range checks use one boolean block beside one float32 RGB block,
    # which is smaller. The named overhead covers small array/iteration objects
    # and ufunc bookkeeping, not a measured allocator/RSS guarantee.
    scratch = min(pixels, BLOCK_PIXELS) * 24 + BLOCK_WORKSPACE_OVERHEAD
    return SourceMaterializationPlan(MATERIALIZATION_VERSION, tuple(source.shape),
        owner_bytes, output_bytes, scratch, owner_bytes + output_bytes + scratch)


def can_materialize_export_source(source, divisor):
    """Return False only for an unsupported owner, never malformed RGB metadata."""
    try:
        inspect_export_source(source, divisor)
    except UnsupportedSourceLayout:
        return False
    return True


def _cancel(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Portrait source materialization cancelled')


def _blocks(shape):
    height, width = shape[:2]
    rows = max(1, BLOCK_PIXELS // width)
    for top in range(0, height, rows):
        bottom = min(height, top + rows)
        # Split exceptionally wide rows as well: a row is not itself a bound.
        for left in range(0, width, BLOCK_PIXELS):
            yield top, bottom, left, min(width, left + BLOCK_PIXELS)


def materialize_export_source(source, divisor, *, max_bytes, cancelled=None):
    """Return one private readonly f32 RGB, or publish nothing on any refusal.

    The caller selects original/derived source identity and verifies repair and
    document ownership independently. No decoder, proxy, repair replacement,
    clipping, downsampling, inference, native solver or state mutation occurs.
    ``max_bytes`` includes the actual source backing, private output and scratch;
    other live roots remain the caller's responsibility. Cancellation is checked
    before allocation, before every block and before returning the result.
    """
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError('Portrait source materialization needs a nonnegative byte budget')
    if cancelled is not None and not callable(cancelled):
        raise ValueError('Portrait source cancellation must be callable or None')
    plan = inspect_export_source(source, divisor)
    if plan.peak_bytes > max_bytes:
        raise ValueError('Portrait source materialization exceeds memory budget before allocation')
    _cancel(cancelled)
    output = block = normalized = None
    try:
        output = np.empty(plan.shape, dtype=np.float32)
        for top, bottom, left, right in _blocks(plan.shape):
            _cancel(cancelled)
            block = source[top:bottom, left:right]
            # Retain the exact legacy cast then Python-integer divide expression.
            # A reciprocal multiply, float64 path or fused uint divide can change
            # rounding. Only allocation extent/layout changes in this version.
            normalized = block.astype(np.float32) / divisor
            if (not np.isfinite(normalized).all()
                    or np.any(normalized < 0) or np.any(normalized > 1)):
                raise ValueError('Portrait source materialization requires finite SDR working RGB')
            output[top:bottom, left:right] = normalized
            # Do not keep the previous block during the next expression.
            block = normalized = None
        _cancel(cancelled)
        output.setflags(write=False)
        return output
    finally:
        # Tracebacks can retain local variables after a failed export. Release
        # every new pixel allocation even if the caller retains the exception.
        output = block = normalized = None
