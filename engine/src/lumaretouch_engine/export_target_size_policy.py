"""Versioned approximate JPEG target policy; no product-scale equivalence claim."""
from dataclasses import dataclass, asdict

UNITS = {"B": 1, "kB": 1000, "MB": 1000000, "KiB": 1024, "MiB": 1048576}
MAX_BYTES = 2**31 - 1


@dataclass(frozen=True)
class TargetSize:
    target_bytes: int
    tolerance_bytes: int
    min_quality: int = 60
    max_quality: int = 100
    max_attempts: int = 41
    time_budget_ms: int = 30000
    max_encoded_bytes: int = 134217728
    max_pixels: int = 50000000
    allow_best_effort: bool = False
    schema: int = 1

    def check(self):
        bounds = {"schema": (1, 1), "target_bytes": (1, MAX_BYTES),
                  "tolerance_bytes": (0, MAX_BYTES), "min_quality": (1, 100),
                  "max_quality": (1, 100), "max_attempts": (1, 100),
                  "time_budget_ms": (1, 300000), "max_encoded_bytes": (1024, MAX_BYTES),
                  "max_pixels": (1, 100000000)}
        for key, (low, high) in bounds.items():
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"target_size.{key}: expected integer {low}..{high}")
        if self.min_quality > self.max_quality:
            raise ValueError("target_size: minimum quality exceeds maximum")
        if self.tolerance_bytes > self.target_bytes:
            raise ValueError("target_size: tolerance must not exceed target")
        if type(self.allow_best_effort) is not bool:
            raise ValueError("target_size.allow_best_effort: expected boolean")
        return self

    def wire(self):
        return asdict(self)


def parse_target_size(value, *, format, bit_depth=8):
    if value is None:
        return None
    if format.lower() not in ("jpg", "jpeg") or bit_depth != 8:
        raise ValueError("近似目标大小仅支持 8-bit JPEG；不自动改变格式或位深")
    if not isinstance(value, dict):
        raise ValueError("target_size must be an object")
    try:
        return TargetSize(**value).check()
    except TypeError as error:
        raise ValueError(f"invalid target_size fields: {error}") from None
