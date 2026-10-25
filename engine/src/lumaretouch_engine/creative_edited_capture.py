"""Explicit original-colour capture without an unused canonical original.

Reimplemented from the verified published baseline after workspace loss. All
runtime/numerical/RSS acceptance is UNRUN. Common export still owns the pixels;
this module narrows admission and separates render owners from output freezing.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path

from .creative_document_assets import MAX_ORIGINAL_BYTES, make_asset

VERSION = 1
MAX_WORK_BYTES = 2_000_000_000
FINAL_RESERVE = 8 * 1024 * 1024


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Full edited-source capture cancelled')


def _plain_graph_candidate(graph, context, asset):
    """Cheap exclusions before new copy admission, never source proof.

    Owner.snapshot already checks the graph schema. Do not inspect numeric
    analysis planes here: their validation scratch has not yet been admitted.
    Unsupported retained intent stays on the complete historical route.
    """
    from .people_algorithms import defaults
    if (graph['persons'] or graph['groups'] or graph['links']
            or graph['unresolved_legacy'] or set(graph['analysis_runs']) - {asset}
            or any(context[key] for key in (
                'people_support_assets', 'hair_colour_assets', 'hair_colour_evidence'))):
        return False
    for face in graph['faces'].values():
        evidence = face['evidence']
        if (face['asset_sha256'] != asset or face['local_assets'] or face['manual']
                or evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe'):
            return False
    neutral = defaults()
    for override in graph['overrides']:
        if override['scope'] == 'all_people' and override['target_id'] != asset:
            return False
        operation, path = override['operation_id'], override['parameter_path']
        if operation not in neutral or path not in neutral[operation]:
            return False
        expected, value = neutral[operation][path], override['value']
        domain = (type(value) in (int, float) if type(expected) in (int, float)
                  else type(value) is type(expected))
        if not domain or value != expected:
            return False
    return True


def preflight_snapshot(engine, row, state, *, max_bytes, geometry_version=0):
    """Select this family, then admit prospective copies before deepcopy.

    The diagnostic mapping is never passed to a renderer. Unsupported sources,
    custom LUTs and neutral originals retain complete historical dispatch.
    Definitive snapshot/spec/source proof is still required after selection.
    """
    from . import virtual_copy_people as VP
    from .creative_edited_capture_admission import (
        admit_snapshot_copy, classify_snapshot, SNAPSHOT_FIELDS,
    )
    from .creative_document_base import _neutral_snapshot
    from .people_export import fastpath_blocker
    from .local_mask_state import source_digest
    from .body_pose_project import bank as body_bank
    from .body_pose_render import retained as retained_body
    if state.get('_creative_base') is not None or retained_body(body_bank(state)):
        return False
    with open(row['path'], 'rb') as stream:
        signature = stream.read(8)
    if not (signature.startswith(b'\xff\xd8') or signature == b'\x89PNG\r\n\x1a\n'):
        return False
    diagnostic = {key: state['_' + key] for key in SNAPSHOT_FIELDS if '_' + key in state}
    diagnostic.update(people=None, people_document_id=None, creative_base=None,
        local_grade_groups=state.get('_local_grade_layers'), _bg=state.get('_bg') or {},
        device='cpu', scale=1, upscale_backend='lanczos3', sharpen=0.)
    defaults = dict(strength=0., params={}, grade=(0., 0., 0., 1.), lut=None,
        lut_amount=0., light={}, light_ops=[], repair_ops=[], deform={}, enhance={},
        channel=None, precompute=None, crop_rect=(0., 0., 1., 1.), crop_rotation=0.)
    for key, value in defaults.items():
        diagnostic.setdefault(key, value)
    if not classify_snapshot(diagnostic, geometry_version=geometry_version).eligible or _neutral_snapshot(diagnostic):
        return False
    VP._remember_active(engine)
    context = VP._context(engine, row)
    graph = context['owner'].snapshot()
    asset = source_digest(row['path'])
    if (not _plain_graph_candidate(graph, context, asset)
            or fastpath_blocker({'state': graph, 'asset_sha256': asset})):
        return False
    # The actual snapshot producer uses current precompute or measured hair
    # replay, not the raw analysis cache. Hair replay is outside this family.
    if graph['faces'] and state.get('_precompute') is None:
        return False
    # Shared source semantic planes can be copied once per target face. Charge
    # planned materializations, not just the unique source owner references.
    faces = sum(face['asset_sha256'] == asset for face in graph['faces'].values())
    roots = (state, graph, context['analyses'], tuple(context[key] for key in VP.FIELDS))
    admit_snapshot_copy(roots, max_bytes=max_bytes, copies=4 + 2 * faces)
    return True


@dataclass
class PendingEditedRGB:
    """Only output RGB/provenance cross render scope; host state stays charged."""
    rgb: object
    original: bytes
    icc: bytes
    max_bytes: int
    persistent_retained_bytes: int = 0


def prepare(engine, row, snapshot, *, retained_roots, source_stamp,
            document_id, max_bytes, persistent_roots=(), cancelled=lambda: False,
            geometry_version=0):
    """Return full RGB, or None before decoding an unsupported family.

    None means the unchanged complete legacy path, never a partial overlay.
    Once decoding starts, errors abort instead of changing rendering strategy.
    """
    from .creative_edited_capture_admission import (
        classify_snapshot, retained_bytes, plan_capture, validate_spec,
    )
    from . import local_mask_state as LM
    from .creative_document_import_bounded import (
        inspect_encoded_source, METADATA_RESERVE, SAFETY_RESERVE,
    )
    from .creative_document_base import _working_source
    from .export_recipe import build_export_spec
    from .export import export_float
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_WORK_BYTES:
        raise ValueError('Edited capture requires the unchanged bounded working budget')
    if not classify_snapshot(snapshot, geometry_version=geometry_version).eligible:
        return None
    # The engine's raw analysis/support banks remain alive even after its
    # exported copies are released. They are real distinct owners, not freed
    # merely because the frozen snapshot is dropped by capture_current_asset.
    from . import virtual_copy_people as VP
    context = VP._context(engine, row)
    persistent_roots = (persistent_roots, context['analyses'],
                        tuple(context[key] for key in VP.FIELDS))
    held = retained_bytes((retained_roots, persistent_roots))
    persistent = retained_bytes(persistent_roots)
    path = row['path']
    _poll(cancelled)
    with open(path, 'rb') as stream:
        signature = stream.read(8)
    if not (signature.startswith(b'\xff\xd8') or signature == b'\x89PNG\r\n\x1a\n'):
        return None
    size = Path(path).stat().st_size
    if not 0 < size <= min(MAX_ORIGINAL_BYTES, max_bytes // 3):
        raise ValueError('Edited original exceeds the encoded-source reservation')
    if held + 2 * size + METADATA_RESERVE + SAFETY_RESERVE > max_bytes:
        raise ValueError('Edited source header plus retained snapshots exceed working budget')
    with open(path, 'rb') as stream:
        original = stream.read(size + 1)
    if len(original) != size or LM.file_stamp(path) != source_stamp:
        raise ValueError('Original changed while freezing edited-source provenance')
    metadata = inspect_encoded_source(original, max_bytes=max_bytes, cancelled=cancelled)
    if metadata['orientation'] != metadata['working_orientation']:
        return None  # Do not reinterpret either legacy PNG16 canvas.
    plan_capture(metadata, snapshot, max_bytes=max_bytes, retained_bytes=held,
                 persistent_retained_bytes=persistent, geometry_version=geometry_version)
    width, height = metadata['width'], metadata['height']
    source = _working_source(path, original, max_pixels=width * height, device='cpu')
    if source.shape[:2] != (height, width) or LM.file_stamp(path) != source_stamp:
        raise ValueError('Genuine edited-source decode differs from frozen source extent')
    expected_dtype = 'uint16' if metadata['bits'] == 16 else 'uint8'
    if str(source.dtype) != expected_dtype:
        raise ValueError('Genuine edited-source decode changed original sample precision')
    if hashlib.sha256(original).hexdigest() != LM.source_digest(path):
        raise ValueError('Decoded original no longer matches immutable provenance')
    _poll(cancelled)
    snapshot, for_document = engine._prepare_export_snapshot(path, snapshot, True)
    _verify_inputs(snapshot, path, source_stamp, source.shape[:2])
    spec, skipped = build_export_spec(snapshot, *source.shape[:2], for_document=for_document)
    validate_spec(spec, snapshot, skipped=skipped, geometry_version=geometry_version)
    if skipped:
        raise ValueError('Edited capture cannot omit current edits: ' + ', '.join(map(str, skipped)))
    spec._creative_capture_original_source = {
        'path': path, 'file_stamp': list(source_stamp),
        'asset_sha256': hashlib.sha256(original).hexdigest(), 'document_id': document_id,
    }
    plan = plan_capture(metadata, snapshot, spec=spec, max_bytes=max_bytes,
        retained_bytes=retained_bytes((retained_roots, persistent_roots, snapshot, spec)),
        persistent_retained_bytes=persistent, geometry_version=geometry_version)
    def progress(*_args):
        _poll(cancelled)
    geometry = (snapshot['crop_rect'], snapshot['crop_rotation'])
    from .ops.geometry import _snapped_quarter_turn
    deferred = geometry_version == 1 and _snapped_quarter_turn(geometry[1]) is None
    # Only version2 capture's proven-neutral finishing cohort can defer this
    # stage. Generic export and every old saved recipe keep their original path.
    # This also avoids feeding legacy f64 geometry into neutral PhotoDetail's
    # f32-only validator; no cast/rounding is introduced to hide that mismatch.
    rgb, _facts = export_float(source, spec,
        geometry=None if deferred else geometry,
        progress=progress, provenance=False)
    if deferred:
        import numpy as np
        from .creative_capture_geometry import crop_rotate_np_bounded
        if (type(rgb) is not np.ndarray or rgb.shape != (height, width, 3)
                or rgb.dtype != np.dtype('float32') or not rgb.dtype.isnative):
            raise ValueError('Deferred geometry requires the exact full-source float32 export canvas')
        rgb = crop_rotate_np_bounded(rgb, *geometry,
            max_bytes=plan.geometry_max_bytes, cancelled=cancelled)
    if LM.file_stamp(path) != source_stamp:
        raise ValueError('Original changed during complete edited-source rendering')
    _poll(cancelled)
    # Source/spec/decoder scopes end here. Parent must also release its frozen
    # snapshots; its independently retained host state remains explicitly charged.
    return PendingEditedRGB(rgb, original, metadata['icc'], max_bytes, persistent)


def _verify_inputs(snapshot, path, stamp, shape):
    """Same full-render ownership checks as the legacy capture boundary."""
    from . import local_mask_state as masks, local_grade_source as groups
    from . import effect_recovery_runtime as recovery, manual_liquify_runtime as manual
    from . import studio_background_runtime as studio, id_background_runtime as ident
    from . import optics_runtime as optics, sky_replacement_runtime as sky
    from . import body_pose_render as body, fringe_repair_render as fringe
    for owner in (masks, groups, recovery, manual, studio, ident, optics, sky, body, fringe):
        owner.check_export_decode(snapshot, path, stamp, shape)
    from .reference_color_runtime import verify_export
    verify_export(snapshot, path, shape)


def finish(pending, *, cancelled=lambda: False):
    """Consume this private RGB owner, then freeze one immutable asset.

    Other parent snapshot aliases must already have ended. No original file,
    document or history is mutated here, including on cancellation/failure.
    """
    from .creative_edited_capture_sink import inspect_rgb_sink, capture_rgb_sink
    if type(pending) is not PendingEditedRGB or pending.rgb is None:
        raise ValueError('Edited RGB capture has already been consumed or is invalid')
    rgb = pending.rgb
    pending.rgb = None
    other = (len(pending.original) + len(pending.icc) + FINAL_RESERVE
             + pending.persistent_retained_bytes)
    available = pending.max_bytes - other
    output = content = None
    try:
        plan = inspect_rgb_sink(rgb, max_bytes=available, cancelled=cancelled)
        if plan.freeze_bytes_after_source_release > available:
            raise ValueError('Edited canonical immutable freeze exceeds working budget')
        output = capture_rgb_sink(rgb, max_bytes=available, cancelled=cancelled)
        rgb = None
        _poll(cancelled)
        content = bytes(output.sink)
        width, height = output.width, output.height
        output = None
        _poll(cancelled)
        return make_asset('rgba', width, height, content,
                          original=pending.original, icc=pending.icc)
    finally:
        rgb = output = content = None
