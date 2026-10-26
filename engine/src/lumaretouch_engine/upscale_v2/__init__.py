"""Optional native-size AI clarity: conditional CPU setup, runtime acceptance UNRUN.

Importing this package imports neither Torch nor BasicSR and performs no I/O.
The legacy ``ops.realesrgan`` experiment is intentionally not reused.
"""

from .adapter import BackendUnavailable, capability, restore_native_candidate
from .geometry import NativeCandidatePlan, iter_native_tiles, plan_native_candidate
from .source import CanonicalSource, SourceValidation, validate_source

__all__ = [
    "BackendUnavailable", "CanonicalSource", "NativeCandidatePlan",
    "SourceValidation", "capability", "iter_native_tiles",
    "plan_native_candidate", "restore_native_candidate", "validate_source",
]
