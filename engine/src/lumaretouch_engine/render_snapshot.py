"""Bounded, independently owned render inputs for asynchronous consumers.

This is an ownership boundary, not a render-memory estimator or recipe validator.
The caller MUST hold its edit/command-thread exclusion throughout this function.
Never copy live arrays from a worker while editing can mutate their aliases.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import math
import numpy as np


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class OwnedSnapshot:
    # Containers/known operation records are private to the consumer, not shared
    # with the live editor. Arrays are owned, C-contiguous and initially readonly.
    value: dict
    asset_bytes: int
    array_count: int
    container_nodes: int
    string_bytes: int


def _owned_with_array_copier(value: dict, *, max_asset_bytes: int,
                      max_nodes: int = 65536, max_string_bytes: int = 1048576,
                      array_copier) -> OwnedSnapshot:
    """Validate/count before ANY array copy, then privately clone known CPU data.

    Each reference is counted once per planned copy, even if two operations share
    the same array. No GPU tensors, custom deepcopy hooks, ndarray subclasses,
    memmaps, object arrays or unknown records are accepted. Source arrays are never
    made readonly. The result is not published on a failed copy.

    Dataclass records retain their existing types and semantics; this does not
    declare unsupported effects renderable. Downstream recipe validation and
    missing-layer checks remain mandatory. Budget covers array payloads only;
    Python/container overhead is separately bounded by node/string limits.
    """
    from .vram import RepairOp, LightOp
    from .face import FacePrecompute
    from .ops.lut import CubeLut
    from .custom_lut_asset import CustomCube
    records = (RepairOp, LightOp, FacePrecompute, CubeLut)
    limits = (max_asset_bytes, max_nodes, max_string_bytes)
    if any(type(n) is not int or n < 0 for n in limits) or max_nodes == 0:
        raise SnapshotError('Snapshot budgets must be explicit nonnegative integers')
    if type(value) is not dict:
        raise SnapshotError('Render snapshot root must be a plain dict')
    count = {'bytes': 0, 'arrays': 0, 'nodes': 0, 'strings': 0}
    ancestors = set()

    def inspect(v, depth=0):
        if depth > 128:
            raise SnapshotError('Snapshot nesting exceeds safe depth')
        count['nodes'] += 1
        if count['nodes'] > max_nodes:
            raise SnapshotError('Snapshot exceeds container/node budget')
        typ = type(v)
        if v is None or typ in (bool, int):
            return
        if typ is float:
            if not math.isfinite(v):
                raise SnapshotError('Snapshot contains nonfinite scalar')
            return
        if typ is str:
            remaining = max_string_bytes - count['strings']
            if len(v) > remaining:
                raise SnapshotError('Snapshot exceeds text budget')
            # Bound temporary encoding buffers even for large metadata strings.
            for offset in range(0, len(v), 4096):
                try:
                    count['strings'] += len(v[offset:offset+4096].encode('utf-8'))
                except UnicodeError as exc:
                    raise SnapshotError('Invalid UTF-8 snapshot text') from exc
                if count['strings'] > max_string_bytes:
                    raise SnapshotError('Snapshot exceeds text budget')
            return
        if typ is CustomCube:
            count["bytes"] += len(v.content)
            if count["bytes"] > max_asset_bytes: raise SnapshotError("Custom LUT exceeds snapshot asset budget")
            inspect(v.asset_id, depth + 1); inspect(v.title, depth + 1)
            return
        if typ is np.ndarray:
            if v.dtype.kind not in 'uif' or v.dtype.fields is not None or v.dtype.metadata is not None:
                raise SnapshotError('Snapshot only accepts numeric CPU arrays')
            count['bytes'] += int(v.nbytes)
            count['arrays'] += 1
            if count['bytes'] > max_asset_bytes:
                raise SnapshotError('Snapshot exceeds asset budget before copying')
            return
        if typ not in (dict, list, tuple) and typ not in records:
            raise SnapshotError(f'Unsupported snapshot type: {typ.__name__}')
        identity = id(v)
        if identity in ancestors:
            raise SnapshotError('Cyclic render snapshot is not supported')
        ancestors.add(identity)
        try:
            if typ is dict:
                for k, child in v.items():
                    if type(k) is not str:
                        raise SnapshotError('Snapshot dictionary keys must be strings')
                    inspect(k, depth + 1)
                    inspect(child, depth + 1)
            elif typ in (list, tuple):
                for child in v:
                    inspect(child, depth + 1)
            else:
                if set(vars(v)) != {field.name for field in fields(v)}:
                    raise SnapshotError('Unknown or missing snapshot record fields')
                for field in fields(v):
                    inspect(getattr(v, field.name), depth + 1)
        finally:
            ancestors.remove(identity)

    inspect(value)

    def clone(v):
        typ = type(v)
        if typ is CustomCube: return v  # Frozen object with immutable bytes, no mutable arrays.
        if typ is np.ndarray:
            # array(copy=True) rather than ascontiguousarray: even an already
            # contiguous source must not keep a writable alias into the editor.
            out = array_copier(v)
            out.setflags(write=False)
            return out
        if typ is dict:
            return {k: clone(child) for k, child in v.items()}
        if typ is list:
            return [clone(child) for child in v]
        if typ is tuple:
            return tuple(clone(child) for child in v)
        if typ in records:
            return typ(**{field.name: clone(getattr(v, field.name)) for field in fields(v)})
        return v

    owned = clone(value)
    return OwnedSnapshot(owned, count['bytes'], count['arrays'], count['nodes'], count['strings'])



def own_render_inputs(value: dict, *, max_asset_bytes: int,
                      max_nodes: int = 65536, max_string_bytes: int = 1048576) -> OwnedSnapshot:
    """Synchronous reference copy; caller excludes editing for the entire call."""
    return _owned_with_array_copier(value, max_asset_bytes=max_asset_bytes,
        max_nodes=max_nodes, max_string_bytes=max_string_bytes,
        array_copier=lambda a: np.array(a, copy=True, order='C', subok=False))


class SnapshotTransaction:
    """Single-executor, cancellable bounded-copy transaction.

    The owner must CANCEL this transaction before any source mutation, and must
    not run advance concurrently with commands. Constructor validates/counts and
    reserves private destinations but copies no array pixels. advance copies at
    most its byte allowance; only take_result can publish completed inputs.
    This is not a concurrent-reader lock or a complete process memory budget.
    """
    def __init__(self, value: dict, *, max_asset_bytes: int,
                 max_nodes: int = 65536, max_string_bytes: int = 1048576):
        self._copies = []
        self._index = 0
        self._offset = 0
        self._cancelled = False
        self._taken = False
        self.copied_bytes = 0
        def reserve(source):
            destination = np.empty(source.shape, dtype=source.dtype, order='C')
            if source.size:
                self._copies.append((source, destination))
            return destination
        self._staged = None
        try:
            self._staged = _owned_with_array_copier(value, max_asset_bytes=max_asset_bytes,
                max_nodes=max_nodes, max_string_bytes=max_string_bytes, array_copier=reserve)
            self.asset_bytes = self._staged.asset_bytes
        except BaseException:
            self.cancel()
            raise

    @property
    def complete(self):
        return not self._cancelled and not self._taken and self._index == len(self._copies)

    def cancel(self):
        self._cancelled = True
        self._copies.clear()
        self._staged = None

    def advance(self, max_copy_bytes: int) -> bool:
        if self._cancelled or self._taken:
            raise SnapshotError('Snapshot transaction is no longer active')
        if type(max_copy_bytes) is not int or max_copy_bytes <= 0:
            raise SnapshotError('Copy tick needs a positive byte allowance')
        remaining = max_copy_bytes
        try:
            while self._index < len(self._copies):
                source, destination = self._copies[self._index]
                itemsize = source.dtype.itemsize
                if remaining < itemsize:
                    if remaining == max_copy_bytes:
                        raise SnapshotError('Copy tick is smaller than an array element')
                    break
                n = min(source.size-self._offset, remaining//itemsize)
                # flat slicing materializes at most this tick, including for
                # negative/noncontiguous strides. Never reshape the source:
                # that could silently copy the entire array before this slice.
                chunk = source.flat[self._offset:self._offset+n]
                destination.setflags(write=True)
                try:
                    np.copyto(destination.reshape(-1)[self._offset:self._offset+n], chunk)
                finally:
                    destination.setflags(write=False)
                used = n*itemsize
                self.copied_bytes += used
                remaining -= used
                self._offset += n
                if self._offset == source.size:
                    self._index += 1
                    self._offset = 0
                if remaining == 0:
                    break
        except BaseException:
            self.cancel()
            raise
        return self.complete

    def take_result(self) -> OwnedSnapshot:
        if not self.complete:
            raise SnapshotError('Incomplete/cancelled snapshot cannot be published')
        result = self._staged
        self._staged = None
        self._copies.clear()
        self._taken = True
        return result
