"""Parameter-only general transfers involving immutable creative photo sources.

This is not a command-name exemption or a new source of pixel/support data.
Callers own exact row proofs, document identities, revisions and transactions.
Only the actual frozen/stored module map can establish admission; request scope
claims, inactive defaults and a shared original pathname cannot do so.
"""
from . import creative_derived_source as SOURCE


def _context(state, source_proof, related_states):
    values = [SOURCE.record(value) for value in (state, *related_states)]
    proof = SOURCE.check_row_proof(source_proof) if source_proof is not None else None
    return any(value is not None for value in values) or bool(proof and proof['creative_source'] is not None), values


def involved(state, source_proof=None, *, related_states=()):
    """Validate every supplied baseline, including dormant history snapshots."""
    return _context(state, source_proof, related_states)[0]


def _photo_sources(values):
    """Reuse the actual photo-return limitation, without rendering or clipping.

    Parked rows have no render to reject incompatible alpha/HDR before success.
    The immutable source proof alone is metadata, not a current pixel input.
    """
    seen = set()
    for value in values:
        if value is not None and value['id'] not in seen:
            from .creative_document_host import require_photo_return
            require_photo_return(value)
            seen.add(value['id'])


def require_modules(state, modules, source_proof=None, *, related_states=()):
    """Return validated parameters for derived involvement; preserve originals.

    The proof is frozen source evidence, not a requirement that the source still
    exists or is unchanged. The caller separately verifies each target's proof.
    """
    derived, values = _context(state, source_proof, related_states)
    if not derived:
        return modules
    from . import scope as SC
    clean = SC.check_derived_modules(modules)
    _photo_sources(values)
    return clean


def _same(left, right):
    """Compare recipe containers without truth-testing arbitrary image arrays.

    Untouched runtime objects must retain identity. Parameter transfer must not
    manufacture or copy inference arrays, even if their pixels happen to match.
    """
    if left is right:
        return True
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_same(left[key], right[key]) for key in left)
    if type(left) in (list, tuple):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if type(left) in (str, bytes, int, float, bool, type(None)):
        return left == right
    return False


def require_candidate(before, after, modules, source_proof=None):
    """Prove the candidate is only the approved parameter replacement.

    Regeneration through the one scope owner protects shared exposure tuple
    subfields as well as source assets, analysis, local support and provenance.
    Non-scope fields remain target-owned, never borrowed from the source.
    """
    derived, values = _context(before, source_proof, (after,))
    if not derived:
        return after
    from . import scope as SC
    clean = SC.check_derived_modules(modules)
    _photo_sources(values)
    expected = SC.apply_modules(before, clean)
    if not _same(expected, after):
        raise SC.ScopeError('合成来源的参数迁移不能改写目标像素、来源、分析或所选模块以外的状态')
    return after


def require_restoration(current, previous, restored, ops, source_proof=None):
    """Admit same-target history only, not portable source-bound coverage.

    Transfer commits still use require_candidate's parameter-reset semantics.
    Here the history owner separately verifies the frozen target source proof;
    reconstructing the scoped prior target is the only accepted difference.
    """
    derived, values = _context(current, source_proof, (previous, restored))
    if not derived:
        return restored
    from . import scope as SC
    if set(ops) - SC.DERIVED_PARAMETER_OPS:
        raise SC.ScopeError('合成来源历史不能读取或恢复未经支持的模块')
    SC.check_derived_modules(SC.params_of(previous, ops))
    _photo_sources(values)
    expected = SC.restore_modules(current, previous, ops)
    if not _same(expected, restored):
        raise SC.ScopeError('合成来源历史只能恢复已审核目标的所选模块，不能改写来源或其他状态')
    return restored
