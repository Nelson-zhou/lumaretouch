# SPDX-License-Identifier: GPL-3.0-or-later
"""Session-only prepared portrait replay data, never a graph/history owner.

Planning reads existing capabilities/target evidence but does not run rendering,
commit graphs, replay state, perform inference or change document/history data.
The caller still owns complete source/document/context review and transactions.
"""
from copy import deepcopy
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PresetReplayPlan:
    state: dict
    kwargs: dict
    managed: bool
    before: dict | None
    candidate: dict | None
    patches: tuple
    target_ref: dict | None
    owner_fence: int | None
    owner: object = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class PresetAliasReviewPlan(PresetReplayPlan):
    """Detached review data, never accepted by generic replay or rollback."""


def require_active_owner(engine):
    """A preview must not silently activate, migrate or create another owner."""
    from .virtual_copy_people import current_row
    row = current_row(engine)
    context = engine.__dict__.get('_people_active_context')
    owner = engine.__dict__.get('_people_graph_owner')
    if (row is None or type(context) is not dict or owner is None
            or engine.__dict__.get('_people_scope_row') is not row
            or context.get('owner') is not owner):
        raise ValueError('Portrait preset preview requires the existing active document owner; open and review this document first')
    return owner


def clone_state(value):
    """Copy recipe containers, retaining externally fenced large runtime buffers.

    Source/repair arrays and tensors are not duplicated just for plan bookkeeping.
    They are not additional authorization: the visual transaction must verify its
    actual immutable-source and complete-state fingerprints before publication.
    """
    if isinstance(value, dict): return {key: clone_state(item) for key, item in value.items()}
    if isinstance(value, list): return [clone_state(item) for item in value]
    if isinstance(value, tuple): return tuple(clone_state(item) for item in value)
    return value


def snapshot(state, kwargs, *, owner=None, owner_fence=None, before=None,
             candidate=None, patches=(), target_ref=None, review_only=False):
    """Detached graph/state values with an explicitly session-only owner fence."""
    if owner is not None and (owner.fence != owner_fence or owner.snapshot() != before):
        raise ValueError('Portrait owner changed while preparing the preset; review again')
    if type(review_only) is not bool:raise ValueError('Private preset planning mode must be explicit')
    kind = PresetAliasReviewPlan if review_only else PresetReplayPlan
    return kind(clone_state(state), dict(kwargs), owner is not None,
        deepcopy(before), deepcopy(candidate), tuple(deepcopy(patches)),
        deepcopy(target_ref), owner_fence, owner)


def graph_content(value):
    """Only monotonic top-level bookkeeping counters are normalized.

    Face analysis revisions, references, links, support keys and all intent stay
    exact; this is not a broad recursive removal of revision-like fields.
    """
    from .people_state import check
    out = check(value)
    out.pop('revision'); out.pop('association_revision')
    return out
