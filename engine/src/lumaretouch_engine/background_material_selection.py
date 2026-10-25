# SPDX-License-Identifier: GPL-3.0-or-later
"""ID-background-only consumer seam. Catalogue selection is not a photo edit."""
from copy import deepcopy
from . import background_material_state as S
from .background_material_store import Store


def resolve_for_id_background(selection, *, cancelled=lambda: False, root=None):
    """Return real immutable IDBackgroundAsset; never return a path as authority.

    Caller owns current document/revision admission, history, bundle persistence,
    native frame and export. Catalogue removal cannot affect an already packed
    project asset, but it invalidates a not-yet-consumed selection.
    """
    from . import id_background_assets as A
    selection = S.selection(selection); S.cancelled(cancelled)
    store = Store(root)
    with store.read() as catalog:
        row = deepcopy(S.match_selection(catalog, selection))
        path = store.verify_object(row)
    S.cancelled(cancelled)
    asset = A.read(str(path), expected=row['binding'], cancelled=cancelled)
    if (asset.binding != row['binding'] or len(asset.content) != row['bytes']
            or (asset.alpha is not None) != row['has_alpha']):
        S.fail('背景素材完整解码结果与选择身份不一致', 'changed')
    # Catalogue/row changes during decode are not hidden by a cached selection.
    with store.read() as catalog:
        current = S.match_selection(catalog, selection)
        if current != row: S.fail('背景素材记录在准备期间变化', 'stale')
        store.verify_object(current)
    S.cancelled(cancelled)
    return asset
