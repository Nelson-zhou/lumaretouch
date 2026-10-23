"""Bounded exhaustive descending JPEG-quality search, independent of size monotonicity.

A callback encodes exactly the same frozen pixels/metadata. No render callback is
accepted. Budget is cooperative between encoder calls, not a hard wall-clock cap.
"""
from dataclasses import dataclass
from time import monotonic
from .export_target_size_policy import TargetSize


class TargetSizeCancelled(RuntimeError):
    pass


class EncodedBudgetExceeded(ValueError):
    pass


@dataclass(frozen=True)
class SearchResult:
    data: bytes | None
    quality: int | None
    status: str
    attempts: tuple
    exhaustive: bool

    def receipt(self, policy):
        size = len(self.data) if self.data is not None else None
        return {"schema": 1, "status": self.status, "target_bytes": policy.target_bytes,
                "tolerance_bytes": policy.tolerance_bytes, "actual_bytes": size,
                "difference_bytes": None if size is None else size-policy.target_bytes,
                "within_tolerance": size is not None and abs(size-policy.target_bytes) <= policy.tolerance_bytes,
                "encoder_quality": self.quality, "exhaustive": self.exhaustive,
                "attempts": list(self.attempts), "policy": policy.wire(),
                "highest_quality_match_proven": self.status == "matched" and all(a["bytes"] is not None for a in self.attempts),
                "algorithm": "lrt.jpeg-target.descending.v1"}


def search(policy: TargetSize, encode, *, cancelled=lambda: False, progress=None,
           clock=monotonic):
    policy.check()
    started = clock()
    attempts = []
    best = None
    best_q = None
    status = "unreachable"
    exhausted = True
    for quality in range(policy.max_quality, policy.min_quality-1, -1):
        if cancelled():
            raise TargetSizeCancelled("目标大小导出已取消；未提交文件")
        if len(attempts) >= policy.max_attempts or (clock()-started)*1000 >= policy.time_budget_ms:
            status, exhausted = "budget_exhausted", False
            break
        try:
            data = encode(quality)
        except EncodedBudgetExceeded:
            attempts.append({"quality": quality, "bytes": None, "status": "encoded_budget_exceeded"})
            continue
        if not isinstance(data, bytes) or not data:
            raise ValueError("encoder must return nonempty bytes")
        if len(data) > policy.max_encoded_bytes:
            raise EncodedBudgetExceeded("encoder exceeded buffer contract")
        if cancelled():
            raise TargetSizeCancelled("目标大小导出已取消；未提交文件")
        size = len(data)
        attempts.append({"quality": quality, "bytes": size, "status": "encoded"})
        if best is None or abs(size-policy.target_bytes) < abs(len(best)-policy.target_bytes):
            best, best_q = data, quality
        if progress:
            progress({"stage": "target_size_search", "attempt": len(attempts),
                      "quality": quality, "bytes": size, "max_attempts": policy.max_attempts})
        # Descending traversal proves this is the highest quality in tolerance,
        # even if a lower quality would produce a larger file. No binary search.
        if abs(size-policy.target_bytes) <= policy.tolerance_bytes:
            return SearchResult(data, quality, "matched", tuple(attempts), quality == policy.min_quality and all(a["bytes"] is not None for a in attempts))
    if cancelled():
        raise TargetSizeCancelled("目标大小导出已取消；未提交文件")
    # Buffer-limited samples are unknown, NOT proof that the target is infeasible.
    if exhausted and any(a["bytes"] is None for a in attempts):
        status, exhausted = "encoded_budget_exhausted", False
    return SearchResult(best, best_q, status, tuple(attempts), exhausted)
