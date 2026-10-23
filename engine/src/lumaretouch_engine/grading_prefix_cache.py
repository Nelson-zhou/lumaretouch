"""Private, bounded proxy prefix reuse. Disabled pending runtime invalidation audit.

Original implementation inspired by PhotoCraft's session/base separation, not
its compositor or scheduling code. See docs/photocraft-preview-adaptation.md.
No cache object or pixels belong in a recipe, project, preset or wire message.
"""
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class PrefixKey:
    document: str
    revision: int
    source: tuple
    generation: int
    shape: tuple
    device: str
    dtype: str
    colour_space: str
    domain: str
    upstream: bytes


class GradingPrefixCache:
    def __init__(self, budget_bytes=64 * 1024 * 1024):
        self.enabled = False
        self.budget_bytes = max(0, int(budget_bytes))
        self.generation = 0
        self._entry = None
        self._lock = RLock()
        self.prefix_builds = 0
        self.cache_hits = 0
        self.suffix_runs = 0

    def invalidate(self):
        # Safe at ingress: no rendering or tensor-content mutation.
        with self._lock:
            self.generation += 1
            self._entry = None

    @property
    def cache_bytes(self):
        with self._lock:
            return 0 if self._entry is None else self._entry[2]

    def resolve(self, key, build, current):
        """Never expose retained storage, including to an in-place suffix.

        current() must recheck the entire post-sync context and cancellation.
        Failure to establish eligibility is a full-quality cache miss.
        """
        with self._lock:
            valid = self.enabled and key is not None and key.generation == self.generation
            entry = self._entry if valid else None
            if not valid or (entry is not None and entry[0] != key):
                self._entry = None
                entry = None
        if entry is not None and entry[0] == key and current():
            try:
                out = entry[1].clone()
            except (MemoryError, RuntimeError):
                self.invalidate()
            else:
                if current():
                    self.cache_hits += 1
                    return out
        # Release a stale retained snapshot before allocating any replacement.
        entry = None
        with self._lock:
            self._entry = None
        self.prefix_builds += 1
        out = build()  # exceptions/cancellation never install a partial prefix
        if not valid or not current():
            return out
        size = int(out.numel() * out.element_size())
        if (size > self.budget_bytes or tuple(out.shape) != key.shape
                or str(out.dtype) != 'torch.float32' or str(out.dtype) != key.dtype
                or str(out.device) != key.device):
            self.invalidate()
            return out
        # One owned immutable-by-convention snapshot; suffix retains original out.
        # Allocation failure is an optimization failure, not a quality fallback.
        try:
            saved = out.detach().clone()
        except (MemoryError, RuntimeError):
            self.invalidate()
            return out
        with self._lock:
            if self.enabled and key.generation == self.generation and current():
                self._entry = (key, saved, size)
        return out


def preview_context(engine, mode, original):
    """Called only AFTER normal runtime synchronization and frame guards.

    A future audited provider must return immutable bytes covering ALL live
    upstream state, including uncommitted overrides, masks and runtime content,
    plus actual colour-space/domain identifiers; None means uncertain. There is
    deliberately no production provider or user-facing enable switch yet.
    """
    pipe = engine._vram
    cache = pipe.grading_prefix_cache
    provider = getattr(engine, '_grading_prefix_audited_context', None)
    if (not cache.enabled or provider is None or original
            or mode != 'colour_grading_preview'
            or not getattr(engine, '_colour_grading_preview_active', False)):
        return None
    from . import colour_editor_runtime as editor, photo_grain_runtime as grain
    from . import sky_replacement_state as sky
    if editor.active(engine) or grain.active(engine):
        return None
    if pipe.sky_replacement.value != sky.empty():
        return None
    if any(value for name, value in vars(engine).items()
           if name.endswith('_preview_active') and name != '_colour_grading_preview_active'):
        return None
    if any(value is not None for name, value in vars(engine).items()
           if name.endswith('_publication') and name != '_colour_grading_publication'):
        return None
    src = pipe.src_f32
    if (src is None or pipe.src_u8 is None or str(src.dtype) != 'torch.float32'
            or tuple(src.shape) != (1, 3, pipe.h, pipe.w)):
        return None
    try:
        snapshot = provider()
    except Exception:
        return None  # Uncertain snapshot is never permission to reuse pixels.
    if (not isinstance(snapshot, tuple) or len(snapshot) != 3
            or not isinstance(snapshot[0], bytes) or not snapshot[0]
            or not all(isinstance(v, str) and v for v in snapshot[1:])):
        return None
    from .extended_tone_host import revision
    return PrefixKey(str(engine._load_id), revision(engine),
                     (id(pipe), id(src), src._version, str(engine._doc_path)),
                     cache.generation, tuple(src.shape), str(src.device),
                     str(src.dtype), snapshot[1], snapshot[2], snapshot[0])
