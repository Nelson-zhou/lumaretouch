# SPDX-License-Identifier: GPL-3.0-or-later
"""Authenticated fit-source ports; no raw pixels or fit matrices in history."""
from copy import deepcopy
from . import skin_reference_match_project as PROJECT

KEY = 'skin_reference_match_source_info'


def needed(state, asset):
    from .skin_reference_body_project import active_refs as body_refs
    return bool(PROJECT.active_refs(state, asset) or body_refs(state, asset))


def preview(engine, state, assets):
    source = deepcopy(engine._people_source())
    result = {'skin_reference_match_assets': assets}
    if not needed(state, source['sha256']): return result
    def full_source(*, byte_budget, cancelled):
        from .portrait_fit_source import capture
        return capture(engine, expected_source=source, byte_budget=byte_budget, cancelled=cancelled)
    result['skin_reference_match_source'] = full_source
    return result


def freeze(snapshot, source, *, source_path=None):
    """Bind frozen export to its effective source, never to output bit depth."""
    if not needed(snapshot['state'], snapshot['asset_sha256']): return snapshot
    if source is None or source['sha256'] != snapshot['asset_sha256']:
        raise ValueError('Skin-reference export needs its exact effective-source binding')
    if snapshot.get('creative_source') is not None:
        if snapshot['creative_source'] != source:
            raise ValueError('Skin-reference derived export belongs to another source')
        snapshot[KEY] = {'kind': 'creative', 'source': deepcopy(source)}
    else:
        from .local_mask_state import file_stamp, source_digest
        stamp = file_stamp(source_path)
        if source_digest(source_path) != source['sha256'] or file_stamp(source_path) != stamp:
            raise ValueError('Skin-reference original changed during source capture')
        snapshot[KEY] = {'kind': 'original', 'source': deepcopy(source),
                         'path': source_path, 'stamp': list(stamp)}
    return snapshot


def _verified_creative(source, binding, *, byte_budget, cancelled):
    """Internal export seam after canonical base/source validation, not a decoder.

    The only caller is people_engine_runtime.prepare_export after its effective
    source, shape, dtype, opacity/SDR and owner checks. No external pixels admitted.
    """
    import numpy as np
    from .portrait_fit_source import FullSource, _freeze
    if (type(source) is not np.ndarray or source.dtype != np.float32
            or source.shape != (binding['height'], binding['width'], 3)
            or type(byte_budget) is not int or byte_budget < source.nbytes*2+64*1024**2):
        raise ValueError('Canonical skin-reference float capture exceeds shape/memory contract')
    content, digest = _freeze(source, binding, cancelled)
    return FullSource(binding['sha256'], binding['width'], binding['height'], digest,
                      32, 'creative', source.nbytes*2+64*1024**2, content)


def export_kwargs(snapshot, source):
    result = {'skin_reference_match_assets': snapshot.get('support_assets', {})}
    if not needed(snapshot['state'], snapshot['asset_sha256']): return result
    info = deepcopy(snapshot.get(KEY)); creative = snapshot.get('creative_source')
    if type(info) is not dict or type(info.get('source')) is not dict or info['source'].get('sha256') != snapshot['asset_sha256']:
        raise ValueError('Skin-reference frozen source fit proof is missing')
    if creative is not None:
        if set(info) != {'kind', 'source'} or info['kind'] != 'creative' or info['source'] != creative:
            raise ValueError('Skin-reference derived fitting cannot use original-file inputs')
        def full_source(*, byte_budget, cancelled):
            return _verified_creative(source, info['source'], byte_budget=byte_budget, cancelled=cancelled)
    else:
        if set(info) != {'kind', 'source', 'path', 'stamp'} or info['kind'] != 'original':
            raise ValueError('Skin-reference original fit needs its exact path/stamp')
        def full_source(*, byte_budget, cancelled):
            from .portrait_fit_source import capture_original
            return capture_original(info['path'], expected_source=info['source'], expected_stamp=info['stamp'],
                                    byte_budget=byte_budget, cancelled=cancelled)
    result['skin_reference_match_source'] = full_source
    return result
