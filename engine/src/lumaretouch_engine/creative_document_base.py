"""Non-destructive bridge between immutable creative pixels and the photo editor.

The original path/bytes are never replaced. A returned base is a canonical asset
record, not a pathname, display proxy, or live ndarray. Only presentation may
matte/clip its alpha and HDR. The existing RGB photo/export pipeline currently
accepts opaque SDR bases and explicitly rejects unsupported alpha/HDR instead
of quietly flattening or clipping them. Numerical bridges are packaged Rust.
"""
from copy import deepcopy

from .creative_document_assets import validate_asset, make_asset, MAX_ORIGINAL_BYTES, MAX_PIXELS

DISPLAY_MATTE_LINEAR = (0.18, 0.18, 0.18)
DEFAULT_WORK_BYTES = 512_000_000
MAX_WORK_BYTES = 4_000_000_000


def check(record):
    if record is None:
        return None
    validate_asset(record)
    if record['kind'] != 'rgba':
        raise ValueError('A creative photo baseline must be a full RGBA asset')
    return record


def from_state(state):
    """State and frozen export snapshots intentionally use different key names."""
    if type(state) is not dict:
        raise ValueError('Creative baseline requires an owned document state')
    return check(state.get('_creative_base') if '_creative_base' in state else state.get('creative_base'))


def source_shape(state, original_hw):
    record = from_state(state)
    return (record['height'], record['width']) if record is not None else tuple(original_hw)


def _pixels(record):
    import numpy as np
    record = check(record)
    if record is None:
        raise ValueError('Missing creative baseline')
    # Immutable bytes-backed view. No integer quantization and no mutable cache.
    return np.frombuffer(record['content'], dtype='<f4').reshape(record['height'], record['width'], 4)


def export_source(record, *, cancelled=lambda: False, max_bytes=DEFAULT_WORK_BYTES):
    """Exact full-resolution f32 working RGB, with no implicit matte/tone map.

    RGB8/RGB16 encoding is performed only at the ordinary final export boundary.
    Native rejection preserves the canonical asset, including alpha/signed HDR.
    """
    import numpy as np
    from .creative_layer_native import encode_opaque_sdr_rgb
    record = check(record)
    if record is None:
        raise ValueError('Missing creative baseline')
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_WORK_BYTES:
        raise ValueError('Invalid creative export-source working budget')
    if record['width'] * record['height'] * 12 + 8_388_608 > max_bytes:
        raise ValueError('Full creative export-source conversion exceeds working memory budget')
    return encode_opaque_sdr_rgb(np.asarray(_pixels(record), dtype=np.float32), cancelled=cancelled)


def proxy_for_state(original_rgb, state, *, max_pixels=None,
                    matte=DISPLAY_MATTE_LINEAR, max_bytes=DEFAULT_WORK_BYTES):
    """Display-only proxy at the returned canvas aspect, never an export input.

    Resample premultiplied linear channels before the explicit display matte and
    SDR transfer. A single source float plane is staged at a time, not a second
    full RGBA canvas. The original comparison buffer is returned unchanged when
    no creative baseline exists; the host retains it separately in either case.
    """
    record = from_state(state)
    if record is None:
        return original_rgb
    import numpy as np
    from PIL import Image
    from .decode import proxy_size, PROXY_PIXELS, MAX_BUDGET
    from .creative_layer_native import display_rgba
    if max_pixels is None:
        max_pixels = min(PROXY_PIXELS, int(original_rgb.shape[0]) * int(original_rgb.shape[1]))
    if type(max_pixels) is not int or not 1 <= max_pixels <= MAX_BUDGET:
        raise ValueError('Invalid creative display pixel budget')
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_WORK_BYTES:
        raise ValueError('Invalid creative display working budget')
    width, height = record['width'], record['height']
    ow, oh = proxy_size(width, height, max_pixels)
    if ow > width or oh > height or ow * oh > max_pixels:
        # The ordinary proxy helper aligns both axes to eight. Very thin creative
        # canvases may not fit that alignment; do not enlarge or exceed the cap.
        ratio = min(1.0, (max_pixels / (width * height)) ** 0.5)
        ow, oh = max(1, int(width * ratio)), max(1, int(height * ratio))
        if ow * oh > max_pixels:
            if ow >= oh:
                ow = max(1, max_pixels // oh)
            else:
                oh = max(1, max_pixels // ow)
    pixels = _pixels(record)
    if (ow, oh) != (width, height):
        # One original F-mode plane, destination RGBA, one resized plane, RGB8,
        # and bounded transfer staging. Retained immutable asset storage is not
        # counted twice as a new temporary allocation.
        if width * height * 4 + ow * oh * 24 + 8_388_608 > max_bytes:
            raise ValueError('Creative display resampling exceeds working memory budget')
        reduced = np.empty((oh, ow, 4), dtype=np.float32)
        for channel in range(4):
            # BOX has nonnegative weights: no negative alpha or ringing outside
            # the premultiplied HDR contract at a sharp transparent boundary.
            plane = Image.fromarray(pixels[:, :, channel], mode='F')
            resized = plane.resize((ow, oh), resample=Image.Resampling.BOX)
            reduced[:, :, channel] = np.asarray(resized, dtype=np.float32)
            plane.close(); resized.close()
        pixels = reduced
    elif width * height * 3 + 8_388_608 > max_bytes:
        raise ValueError('Creative display conversion exceeds working memory budget')
    return display_rgba(np.asarray(pixels, dtype=np.float32), matte=matte)


def require_rebound_snapshot(snapshot):
    """Original-file analysis is not evidence about newly composited pixels.

    Until those source owners support content-addressed creative baselines,
    reject their requests before resampling masks or performing inference. Do
    not silently re-use old faces simply because canvas dimensions still match.
    """
    if from_state(snapshot) is None:
        return
    from . import local_grade_layers as LG, effect_recovery_state as ER
    from . import manual_liquify_state as ML
    from . import id_background_state as ID, optics_state as OP
    from . import reference_color_state as RC, semantic_colour_state as SC
    from . import lip_makeup_state as LIP, brow_shape_state as BROW, nose_shape_state as NOSE
    from . import eye_shape_state as EYE, mouth_shape_state as MOUTH
    from . import colour_editor_state as CE
    blocked = []
    people = snapshot.get('people')
    if people is not None:
        from .creative_derived_source import binding
        source = binding(snapshot)
        if people.get('creative_source') != source or people.get('asset_sha256') != source['sha256']:
            blocked.append('unbound original people observations')
    if snapshot.get('body_pose') is not None:
        from .creative_derived_body_export import verify_snapshot
        verify_snapshot(snapshot)
    from .creative_derived_masks import masks, verify_snapshot as verify_masks
    if masks(snapshot):verify_masks(snapshot)
    from .creative_derived_smoothing import verify_snapshot as verify_smoothing
    verify_smoothing(snapshot)
    if snapshot.get('grade_scope', 'all') not in ('all','objects'):
        blocked.append('original scoped masks')
    from .creative_derived_repairs import validate_stacks
    validate_stacks(snapshot)
    if snapshot.get('light_ops'):
        blocked.append('unbound light strokes')
    if any(float(v) != 0 for v in (snapshot.get('deform') or {}).get('amounts', {}).values()):
        blocked.append('original facial deformation')
    if any(float(v) != 0 for v in (snapshot.get('enhance') or {}).get('amounts', {}).values()):
        blocked.append('original portrait enhancement')
    if float(snapshot.get('fabric_amount', 0)):
        from .creative_derived_fabric import verify_snapshot as verify_fabric
        verify_fabric(snapshot)
    from .fringe_repair_state import verify_source as verify_fringe, neutral as neutral_fringe
    verify_fringe(neutral_fringe() if snapshot.get('fringe_repair') is None else snapshot['fringe_repair'],snapshot)
    from .creative_derived_common_background import verify_snapshot as verify_common
    verify_common(snapshot)
    if ER.check(snapshot.get('effect_recovery'))['targets']:
        from .creative_derived_global_recovery import verify_snapshot as verify_recovery
        verify_recovery(snapshot)
    if ML.check(snapshot.get('manual_liquify'))['strokes']:
        blocked.append('original source-bound local edits')
    from .creative_derived_studio import verify_snapshot as verify_studio
    verify_studio(snapshot)
    from .creative_derived_sky import verify_snapshot as verify_sky
    verify_sky(snapshot)
    from .creative_derived_id_background import verify_snapshot as verify_id
    verify_id(snapshot)
    for label, module, key in (
            ('reference colour', RC, 'reference_color'),
            ('semantic colour', SC, 'semantic_colour'), ('lip makeup', LIP, 'lip_makeup'),
            ('brow shape', BROW, 'brow_shape'), ('nose shape', NOSE, 'nose_shape'),
            ('eye shape', EYE, 'eye_shape'), ('mouth shape', MOUTH, 'mouth_shape')):
        if module.active(snapshot.get(key)):
            blocked.append(label)
    if OP.source_bound(OP.check(snapshot.get('optics'))):
        blocked.append('original lens/perspective analysis')
    editor = snapshot.get('colour_editor')
    if editor is not None and CE.check(editor)['scope'] == 'local':
        blocked.append('local colour editor')
    if blocked:
        raise ValueError('Creative baseline needs content-bound re-analysis before these edits: ' + ', '.join(blocked))


def require_rebound_spec(spec):
    """Same fail-closed gate for direct library callers bypassing snapshots."""
    snapshot = {key: getattr(spec, key, None) for key in (
        'creative_base', 'people', 'body_pose', 'body_pose_source_proof', 'channel', 'grade_scope',
        'strength', 'creative_smoothing_context',
        'fabric_amount', 'creative_fabric_context', 'local_masks', 'local_grade_groups', 'creative_mask_context', 'effect_recovery', 'creative_recovery_context', 'manual_liquify',
        'studio_background', 'creative_studio_context', 'id_background', 'id_background_bundle', 'creative_id_background_context', 'optics', 'sky_replacement', 'creative_sky_context',
        'reference_color', 'semantic_colour', 'lip_makeup', 'brow_shape',
        'nose_shape', 'eye_shape', 'mouth_shape', 'colour_editor', 'fringe_repair')}
    snapshot['params']={key:getattr(spec,key) for key in ('radius','eps','texture_radius','broad_gain','mid_gain','detail_gain')}
    snapshot.update(repair_ops=spec.repair, light_ops=spec.light,
        deform={'amounts': spec.deform_amounts}, enhance={'amounts': spec.enhance},
        _bg={'active': spec.bg_matte is not None or spec.bg_ref is not None})
    from .creative_derived_common_background import spec_state as common_state
    snapshot['_bg']=common_state(spec)['_bg']
    require_rebound_snapshot(snapshot)


def _neutral_snapshot(snapshot):
    """Conservative neutral gate for lossless alpha/HDR canonical passthrough."""
    from .master16_policy import Master16PolicyMixin
    from . import extended_tone_state as ET, photo_detail_state as PD, fringe_repair_state as FR
    from . import colour_grading_state as CG, selective_colour_state as SC
    from . import primary_calibration_state as PC, id_background_state as ID
    bare = dict(snapshot)
    bare['creative_base'] = None
    if Master16PolicyMixin._master16_snapshot_blockers(bare):
        return False
    if ET.active(bare.get('extended_tone')) or PD.active(bare.get('photo_detail')) or ID.active(bare.get('id_background')) or FR.active(bare.get('fringe_repair') or FR.neutral()):
        return False
    for module, key in ((CG, 'colour_grading'), (SC, 'selective_colour'), (PC, 'primary_calibration')):
        if module.active(bare.get(key) if bare.get(key) is not None else module.neutral()):
            return False
    return True


def _working_source(path, original, *, max_pixels, device):
    """Full native precision source for existing edits, never load_rgb/proxy."""
    import numpy as np
    from .decode import load_full, is_raw
    from .full_source_working import source_bits, require_opaque_8bit, working_rgb
    from PIL import Image
    # Ordinary capture shares inspection/export's native decoder. Creative
    # import keeps its independent alpha-capable immutable encoded-asset path.
    if is_raw(path):
        bits = 16
    else:
        with Image.open(path) as image:
            bits = 16 if source_bits(path, image) > 8 else 8
            if bits == 8:
                require_opaque_8bit(image)
    decoded = load_full(path, max_px=max_pixels, device=device, want_bits=bits)
    if (decoded.h, decoded.w) != (decoded.src_h, decoded.src_w) or decoded.draft_used or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size'):
        raise ValueError('Creative capture requires genuine full-resolution source pixels')
    if bits == 16 and decoded.rgb.dtype != np.uint16:
        raise ValueError('Creative capture refused a reduced-precision source')
    return working_rgb(decoded)


def capture_current_asset(engine, row, state, assets, *, cancelled=lambda: False,
                          max_bytes=DEFAULT_WORK_BYTES, neutral_import_version=0,
                          allow_legacy_import_budget_fallback=False,
                          edited_capture_version=0):
    """Freeze current full-resolution edits into a real canonical base record.

    Same recipe/source guards, crop, effects and float output as file export.
    Missing active layers reject the capture. The caller holds document ownership
    and commits only after its final revision check. This function changes no live
    document, source file, sliders, history, or comparison buffer.
    """
    import numpy as np
    from pathlib import Path
    from . import local_mask_state as LM, virtual_copy_people as VP
    from .creative_document_import import import_file
    from .creative_layer_native import linearize_rgba, linearize_extended_rgba
    from .export import export_float
    from .export_recipe import build_export_spec
    from .decode import is_raw
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_WORK_BYTES:
        raise ValueError('Invalid creative full-capture memory budget')
    if type(neutral_import_version) is not int or neutral_import_version not in (0, 1):
        raise ValueError('Unknown explicit neutral-source import strategy')
    if type(allow_legacy_import_budget_fallback) is not bool:
        raise ValueError('Legacy import budget fallback must be explicitly selected')
    if type(edited_capture_version) is not int or edited_capture_version not in (0, 1, 2):
        raise ValueError('Unknown explicit edited-source capture strategy')
    def poll(*_args):
        if cancelled():
            raise InterruptedError('Creative full-resolution capture cancelled')
    poll()
    path = row['path']; before = LM.file_stamp(path)
    version = engine._document_versions().version(row)
    if edited_capture_version in (1, 2):
        from .creative_edited_capture import preflight_snapshot
        if not preflight_snapshot(engine, row, state, max_bytes=max_bytes,
                                  geometry_version=1 if edited_capture_version == 2 else 0):
            edited_capture_version = 0
    frozen = deepcopy(state)
    if not frozen.get('_params') or not frozen.get('_light'):
        raise ValueError('Creative capture needs complete owned editing state, not current-document parameter fallbacks')
    snap = engine._state_to_export_snap(frozen, device='cpu', scale=1,
        upscale_backend='lanczos3', sharpen=0., source_path=path,
        people_context=VP.row_context(engine, row), people_graph=VP.row_snapshot(engine, row),people_document_id=version.document_id)
    from .people_export import verify_source, isolated_snapshot
    verify_source(snap,path)
    snap=isolated_snapshot(snap,for_document=True)
    neutral = _neutral_snapshot(snap)
    record = from_state(frozen)
    if edited_capture_version in (1, 2) and record is None and not neutral:
        from .creative_edited_capture import prepare as prepare_edited, finish as finish_edited
        pending = prepare_edited(engine, row, snap, retained_roots=(state, frozen, snap),
            source_stamp=before, document_id=version.document_id,
            max_bytes=max_bytes, persistent_roots=(state,), cancelled=cancelled,
            geometry_version=1 if edited_capture_version == 2 else 0)
        if pending is not None:
            # Frozen render roots end before output transfer/freezing. The host's
            # captured state still lives and is charged by Pending's census.
            del frozen, snap
            result = finish_edited(pending, cancelled=cancelled)
            poll()
            if LM.file_stamp(path) != before or engine._document_versions().version(row) != version:
                raise ValueError('Edited capture source/document changed before publication')
            assets.intern(result)
            return result
    source = None
    if record is None:
        if not is_raw(path):
            importer = import_file
            if neutral_import_version == 1 and neutral:
                # Explicit new capture strategy only. Legacy callers and every
                # non-neutral full-edit export keep their historical path.
                with open(path, 'rb') as header:
                    signature = header.read(8)
                if signature.startswith(b'\xff\xd8') or signature == b'\x89PNG\r\n\x1a\n':
                    from .creative_document_import_bounded import import_file as importer
            legacy_budget_retry = False
            if importer is import_file:
                identity = importer(path, assets, max_bytes=max_bytes, cancelled=cancelled)
            else:
                from .creative_document_import_bounded import ImportBudgetExceeded
                try:
                    identity = importer(path, assets, max_bytes=max_bytes, cancelled=cancelled)
                except ImportBudgetExceeded as error:
                    # Only post-metadata, pre-pixel allocation refusal qualifies.
                    # Invalid ICC/orientation/precision never reaches this retry.
                    if not allow_legacy_import_budget_fallback:
                        raise
                    error.__traceback__ = None
                    legacy_budget_retry = True
                if legacy_budget_retry:
                    # Leave the exception scope first: its frames must not retain
                    # a second original-file snapshot during legacy allocation.
                    poll()
                    identity = import_file(path, assets, max_bytes=max_bytes, cancelled=cancelled)
            record = assets.get(identity, 'rgba')
        else:
            size = Path(path).stat().st_size
            if size > MAX_ORIGINAL_BYTES or size * 2 > max_bytes:
                raise ValueError('Creative RAW source exceeds retained-byte budget')
            with open(path, 'rb') as handle:
                original = handle.read(min(MAX_ORIGINAL_BYTES, max_bytes // 2) + 1)
            if len(original) > min(MAX_ORIGINAL_BYTES, max_bytes // 2):
                raise ValueError('Creative RAW source grew during capture')
            from .ops import libraw
            dimensions = libraw.identify(path)
            limit = max(0, (max_bytes - 2 * len(original)) // 96)
            if dimensions is None or dimensions['w'] * dimensions['h'] > limit:
                raise ValueError('Creative RAW full-resolution capture exceeds memory budget')
            source = _working_source(path, original, max_pixels=limit, device='cpu')
            rgba = np.empty((*source.shape[:2], 4), dtype=np.float32)
            rgba[:, :, :3] = source.astype(np.float32) / 65535.0
            rgba[:, :, 3] = 1.0
            linear = linearize_rgba(rgba, cancelled=cancelled)
            record = make_asset('rgba', source.shape[1], source.shape[0], linear.astype('<f4', copy=False).tobytes(), original=original)
            del linear, rgba
            assets.intern(record)
    poll()
    if LM.file_stamp(path) != before:
        raise ValueError('Original source changed during creative capture')
    if neutral:
        # No transfer roundtrip, quantization, alpha loss, or HDR clipping.
        result = deepcopy(record)
    else:
        pixels = record['width'] * record['height']
        from .ops.geometry import out_size
        ow, oh = out_size(record['width'], record['height'], snap['crop_rect'], snap['crop_rotation'])
        if ow * oh > MAX_PIXELS:
            raise ValueError('Creative full edited canvas exceeds the canonical asset pixel budget')
        if max(pixels, ow * oh) * 96 + 2 * len(record['original']) > max_bytes:
            raise ValueError('Full current-edit creative capture exceeds its declared memory budget; no proxy fallback')
        if not np.all(_pixels(record)[:, :, 3] == 1):
            raise ValueError('Current RGB edits cannot preserve transparent source alpha; creative source remains unchanged')
        if from_state(frozen) is None and source is None:
            source = _working_source(path, record['original'], max_pixels=pixels, device='cpu')
        elif source is None:
            # Supplied ndarray is only a shape carrier; exporter resolves the
            # canonical base exactly once. No full-sized integer placeholder.
            source = np.empty((0, 0, 3), dtype=np.uint8)
        snap, for_document = engine._prepare_export_snapshot(path, snap, True)
        from . import local_grade_source as groups, effect_recovery_runtime as recovery
        from . import manual_liquify_runtime as manual, studio_background_runtime as studio
        from . import id_background_runtime as ident, optics_runtime as optics
        from . import sky_replacement_runtime as sky, body_pose_render as body
        shape = source_shape(snap, source.shape[:2])
        from . import fringe_repair_render as fringe
        for owner in (LM, groups, recovery, manual, studio, ident, optics, sky, body, fringe):
            owner.check_export_decode(snap, path, before, shape)
        from .reference_color_runtime import verify_export
        verify_export(snap, path, shape)
        spec, skipped = build_export_spec(snap, *shape, for_document=for_document)
        if skipped:
            raise ValueError('Creative capture cannot omit current edits: ' + ', '.join(map(str, skipped)))
        rgb, _facts = export_float(source, spec,
            geometry=(snap['crop_rect'], snap['crop_rotation']), progress=poll, provenance=False)
        rgba = np.empty((*rgb.shape[:2], 4), dtype=np.float32)
        rgba[:, :, :3] = rgb; rgba[:, :, 3] = 1.0
        del rgb
        linear = linearize_extended_rgba(rgba, cancelled=cancelled)
        del rgba
        result = make_asset('rgba', linear.shape[1], linear.shape[0],
            linear.astype('<f4', copy=False).tobytes(), original=record['original'], icc=record['icc'])
    poll()
    if LM.file_stamp(path) != before or engine._document_versions().version(row) != version:
        raise ValueError('Creative capture source/document changed before publication')
    assets.intern(result)
    return result
