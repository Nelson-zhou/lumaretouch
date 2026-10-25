"""Fail-closed original edited-capture admission. AUTHORED / UNRUN.

No decoding, inference, native loading, preparation or rendering occurs here.
Eligibility selects an optimization, never permission to omit edits or a process
RSS certificate. Real export validation and source/document fences still apply.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import math
import sys

MAX_WORK_BYTES = 2_000_000_000
MAX_NODES = 65_536
MAX_DEPTH = 128
MAX_TEXT_BYTES = 1_048_576
DEFAULT_TILE = 1024
BLOCK_PIXELS = 65_536
METADATA_RESERVE = 16 * 1024 * 1024
NATIVE_RESERVE = 64 * 1024 * 1024
VALIDATION_RESERVE = 4 * 1024 * 1024
TILE_BYTES_PER_PIXEL = 512  # f64 colour planes and int64 curve gathers, not measured RSS


class AdmissionError(ValueError):
    pass


class CaptureBudgetExceeded(AdmissionError):
    pass


@dataclass(frozen=True, slots=True)
class StorageCensus:
    owners: tuple[tuple[int, int], ...]
    retained_bytes: int
    total_bytes: int
    array_copy_bytes: int
    container_bytes: int
    nodes: int
    array_count: int
    validation_scratch_bytes: int

    @property
    def owner_ids(self):
        return frozenset(identity for identity, _ in self.owners)


@dataclass(frozen=True, slots=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...]
    features: tuple[str, ...] = ()
    fingerprint: tuple = ()


@dataclass(frozen=True, slots=True)
class CaptureMemoryPlan:
    width: int
    height: int
    output_width: int
    output_height: int
    bits: int
    margin: int
    tile_pixels: int
    retained_bytes: int
    phases: tuple[tuple[str, int], ...]
    owners: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    max_bytes: int
    geometry_max_bytes: int = 0
    geometry_version: int = 0
    finishing_max_bytes: int = 0
    finishing_version: int = 0
    bounds_kind: str = 'application-working-set-with-conservative-native-reserves'
    runtime_verified: bool = False

    @property
    def peak_bytes(self):
        return max(size for _, size in self.phases)

    @property
    def peak_phase(self):
        return max(self.phases, key=lambda pair: pair[1])[0]


def _integer(value, name, *, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise AdmissionError('Invalid ' + name)
    return value


def _record_types():
    from .face import FacePrecompute
    from .ops.lut import CubeLut
    from .vram import RepairOp, LightOp
    from .export import ExportSpec
    from .custom_lut_asset import CustomCube
    return (FacePrecompute, CubeLut, RepairOp, LightOp, ExportSpec, CustomCube)


def inspect_storage(value, *, baseline=None):
    """Count actual backing owners without modifying flags, arrays or records.

    Keep baseline roots alive while comparing their terminal owner identities.
    Distinct ndarray views need distinct ordinary-deepcopy destinations; repeated
    references to one array need one. Equal immutable bytes are not necessarily
    the same allocation. Unknown records/properties/backing wrappers fail closed.
    """
    import numpy as np
    from .export import ExportSpec
    records = _record_types()
    if baseline is not None and type(baseline) is not StorageCensus:
        raise AdmissionError('Storage baseline must be a live-root census')
    excluded = baseline.owner_ids if baseline is not None else frozenset()
    owners, seen, ancestors = {}, set(), set()
    nodes = arrays = copies = containers = text_bytes = largest_array = 0

    def backing(array):
        current, chain, size = array, set(), 0
        while True:
            identity = id(current)
            if identity in chain or len(chain) >= 64:
                raise AdmissionError('Cyclic/excessive array backing chain')
            chain.add(identity)
            if type(current) is np.ndarray:
                if current.dtype.hasobject or current.dtype.fields is not None or current.dtype.metadata is not None:
                    raise AdmissionError('Object/structured array backing is not admitted')
                size = max(size, int(current.nbytes))
                if current.base is None:
                    if not current.flags.owndata:
                        raise AdmissionError('Unknown non-owning array storage')
                    return identity, size
                current = current.base
            elif type(current) is memoryview:
                size = max(size, current.nbytes)
                current = current.obj
            elif type(current) in (bytes, bytearray):
                return identity, max(size, len(current))
            else:
                raise AdmissionError('Unsupported array backing owner: ' + type(current).__name__)

    def visit(item, depth=0):
        nonlocal nodes, arrays, copies, containers, text_bytes, largest_array
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise AdmissionError('Capture snapshot exceeds traversal bounds')
        typ = type(item)
        if typ is float and not math.isfinite(item):
            raise AdmissionError('Nonfinite capture snapshot scalar')
        if item is None or typ in (bool, int, float, str):
            if typ is str:
                if len(item) > MAX_TEXT_BYTES - text_bytes:
                    raise AdmissionError('Capture snapshot exceeds text budget')
                text_bytes += len(item.encode('utf-8'))
                if text_bytes > MAX_TEXT_BYTES:
                    raise AdmissionError('Capture snapshot exceeds text budget')
            containers += sys.getsizeof(item)
            return
        identity = id(item)
        if identity in ancestors:
            raise AdmissionError('Cyclic capture snapshot')
        if identity in seen:
            return
        seen.add(identity)
        if typ is bytes:
            owners[identity] = max(owners.get(identity, 0), len(item))
            containers += sys.getsizeof(item) - len(item)
            return
        if typ is np.ndarray:
            if item.dtype.kind not in 'uif' or item.dtype.hasobject or item.dtype.fields is not None or item.dtype.metadata is not None:
                raise AdmissionError('Only ordinary numeric CPU arrays are admitted')
            owner, amount = backing(item)
            owners[owner] = max(owners.get(owner, 0), amount)
            copies += int(item.nbytes)
            arrays += 1
            largest_array = max(largest_array, int(item.size))
            containers += 256 + 16 * item.ndim
            return
        if typ not in (dict, list, tuple) and typ not in records:
            raise AdmissionError('Unsupported capture snapshot type: ' + typ.__name__)
        containers += sys.getsizeof(item) + 64
        ancestors.add(identity)
        try:
            if typ is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise AdmissionError('Capture snapshot keys must be strings')
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            elif typ in (list, tuple):
                for child in item:
                    visit(child, depth + 1)
            else:
                # Only exact project classes: never inspect an arbitrary object.
                data = object.__getattribute__(item, '__dict__')
                if typ is ExportSpec:
                    data = _spec_data(item)
                    if '_creative_capture_original_source' in data:
                        _check_source_context(data['_creative_capture_original_source'])
                elif set(data) != {entry.name for entry in fields(typ)}:
                    raise AdmissionError('Unknown/missing capture record fields')
                for child in data.values():
                    visit(child, depth + 1)
        finally:
            ancestors.remove(identity)

    visit(value)
    owned = tuple(sorted(owners.items()))
    total = sum(size for _, size in owned)
    retained = sum(size for identity, size in owned if identity not in excluded)
    # Sequential semantic finite/range checks can retain three boolean masks;
    # reserve four at the actual largest producer grid, not a fixed proxy size.
    validation = 4 * largest_array + 65_536
    return StorageCensus(owned, retained, total, copies, containers, nodes, arrays, validation)


def retained_bytes(*roots, baseline=None):
    census = inspect_storage(roots, baseline=baseline)
    return census.retained_bytes + census.container_bytes


def admit_snapshot_copy(value, *, max_bytes, host_lease_bytes=0, copies=1):
    """Admit new state/context/per-face copies before they allocate.

    value may be a tuple of raw roots. copies must bound separate deepcopy calls
    and per-face plane materializations, including alias sharing lost across
    them. Other already-live roots belong in host_lease_bytes. This cannot admit
    a host _capture_state() that already happened before this boundary.
    """
    _integer(max_bytes, 'capture budget', minimum=1, maximum=MAX_WORK_BYTES)
    _integer(host_lease_bytes, 'host lease')
    _integer(copies, 'planned snapshot copies', minimum=1, maximum=MAX_NODES)
    census = inspect_storage(value)
    required = (host_lease_bytes + census.total_bytes + copies * census.array_copy_bytes
                + (copies + 1) * census.container_bytes + METADATA_RESERVE
                + census.validation_scratch_bytes)
    if required > max_bytes:
        raise CaptureBudgetExceeded('Pre-snapshot ownership requires %d bytes; budget is %d' % (required, max_bytes))
    return census


# Explicit producer inventory. A new field needs an audit, even when neutral.
SNAPSHOT_FIELDS = frozenset('''people_document_id creative_base id_background id_background_bundle people strength params grade grade_scope grade_mask local_masks local_mask_owner local_grade_groups effect_recovery manual_liquify studio_background optics sky_replacement lip_makeup brow_shape brow_shape_owner nose_shape nose_shape_owner eye_shape eye_shape_owner reference_color mouth_shape mouth_shape_owner extended_tone photo_detail photo_grain fringe_repair colour_grading selective_colour colour_editor primary_calibration exposure exposure_ref_k wb_options hsl curves levels crop_rect crop_rotation lut lut_amount light light_ops repair_ops deform deform_defer fabric_amount enhance enhance_defer channel _bg precompute device scale upscale_backend sharpen body_pose body_pose_source_proof semantic_colour semantic_colour_mask_assets semantic_colour_source_path semantic_colour_binding export_skipped local_mask_source_path local_grade_source_stamp effect_recovery_path effect_recovery_stamp manual_liquify_path manual_liquify_stamp studio_background_path studio_background_stamp optics_path optics_stamp sky_replacement_path sky_replacement_stamp id_background_path id_background_stamp fringe_repair_source fringe_repair_path fringe_repair_stamp common_background_path common_background_stamp body_pose_source_path body_pose_source_stamp semantic_colour_source_stamp creative_mask_context creative_smoothing_context creative_fabric_context creative_recovery_context creative_sky_context creative_studio_context creative_id_background_context'''.split())
PARAM_FIELDS = frozenset(('radius', 'eps', 'texture_radius', 'broad_gain', 'mid_gain', 'detail_gain'))
CORE_FIELDS = frozenset('strength params grade lut lut_amount light light_ops repair_ops deform enhance channel precompute crop_rect crop_rotation'.split())


def _freeze(value):
    if type(value) is dict:
        return tuple((key, _freeze(child)) for key, child in sorted(value.items()))
    if type(value) in (list, tuple):
        return tuple(_freeze(child) for child in value)
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise AdmissionError('Unexpected value in recipe fingerprint')


def _cube_fingerprint(cube):
    if cube is None:
        return None, 0
    import numpy as np
    from .ops.lut import CubeLut, MIN_SIZE_3D, MAX_SIZE_3D
    if type(cube) is not CubeLut:
        raise AdmissionError('Only ordinary CubeLut is admitted; custom LUT needs its own parse ledger')
    data = object.__getattribute__(cube, '__dict__')
    if set(data) != {entry.name for entry in fields(CubeLut)}:
        raise AdmissionError('Unknown CubeLut fields')
    grid = data['grid']
    if (data['kind'] != '3d' or type(data['size']) is not int
            or not MIN_SIZE_3D <= data['size'] <= MAX_SIZE_3D
            or type(grid) is not np.ndarray or grid.dtype != np.dtype('float64')
            or not grid.dtype.isnative or grid.shape != (data['size'],) * 3 + (3,)
            or not grid.flags.c_contiguous or type(data['neutral']) is not bool):
        raise AdmissionError('Unsupported ordinary CubeLut layout')
    digest = hashlib.sha256()
    flat = grid.reshape(-1)
    for start in range(0, flat.size, BLOCK_PIXELS):
        block = flat[start:start + BLOCK_PIXELS]
        if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
            raise AdmissionError('Invalid ordinary CubeLut samples')
        digest.update(memoryview(block).cast('B'))
    lo, hi = data['domain_min'], data['domain_max']
    if type(lo) is not tuple or type(hi) is not tuple or len(lo) != 3 or len(hi) != 3:
        raise AdmissionError('Invalid ordinary CubeLut domain')
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (*lo, *hi)) or any(a >= b for a, b in zip(lo, hi)):
        raise AdmissionError('Invalid ordinary CubeLut domain')
    metadata = {key: child for key, child in data.items() if key != 'grid'}
    return (_freeze(metadata), digest.hexdigest()), int(grid.size) * 8


def _classify(snapshot, *, geometry_version=0, finishing_version=0):
    _integer(geometry_version, 'geometry version', maximum=1)
    _integer(finishing_version, 'finishing version', maximum=1)
    from . import white_balance_recipe as WB
    from .ops import curves as CURVES, levels as LEVELS, geometry as G
    from .ops.exposure import check_params as check_exposure
    from .ops.tone import check_tone
    from .ops.hsl import check_hsl
    from .ops.grade import check_params as check_grade
    from .ops.lut import check_amount
    from . import colour_grading_state as CG, selective_colour_state as SC, primary_calibration_state as PC
    from . import extended_tone_state as ET, photo_detail_state as PD, photo_grain_state as PG
    from . import fringe_repair_state as FR, colour_editor_state as CE
    from . import local_mask_state as LM, local_grade_layers as LG, effect_recovery_state as ER
    from . import manual_liquify_state as ML, id_background_state as ID
    from . import studio_background_state as ST, sky_replacement_state as SKY, optics_state as OP
    from . import semantic_colour_state as SEM, reference_color_state as REF
    if type(snapshot) is not dict or set(snapshot) - SNAPSHOT_FIELDS or not CORE_FIELDS <= set(snapshot):
        raise AdmissionError('Unknown or incomplete edited capture snapshot schema')
    inspect_storage(snapshot)
    # The semantic recipe validator can unpack old embedded mask payloads.
    # Refuse retained state structurally BEFORE calling it or the neutral policy.
    semantic_raw = snapshot.get('semantic_colour')
    if type(semantic_raw) is dict and (semantic_raw.get('groups') or semantic_raw.get('masks')
            or any(semantic_raw.get(key) is not None for key in ('target', 'reference', 'analysis', 'last_review'))):
        raise AdmissionError('Retained semantic colour sources/masks require the legacy path')
    reasons = []
    if snapshot.get('creative_base') is not None:
        reasons.append('existing creative baseline')
    if snapshot.get('people') is not None:
        from .creative_capture_people import neutral_census_candidate
        if not neutral_census_candidate(snapshot['people']):
            reasons.append('active or unaccounted people graph')
    if snapshot.get('strength') != 0 or snapshot.get('channel') is not None:
        reasons.append('smoothing or scoped channel')
    if snapshot.get('grade_scope', 'all') != 'all' or snapshot.get('grade_mask') is not None:
        reasons.append('local grade scope/mask')
    if snapshot.get('scale', 1) != 1 or snapshot.get('sharpen', 0) != 0 or snapshot.get('upscale_backend', 'lanczos3') != 'lanczos3':
        reasons.append('upscale/sharpen')
    if snapshot.get('device', 'cpu') != 'cpu':
        reasons.append('non-CPU capture')
    if type(snapshot['repair_ops']) is not list or type(snapshot['light_ops']) is not list:
        raise AdmissionError('Repair/light collections must be ordinary lists')
    if snapshot['repair_ops'] or snapshot['light_ops']:
        reasons.append('repair/light operators')
    if type(snapshot['light']) is not dict or set(snapshot['light']) != {'exposure', 'radius'}:
        raise AdmissionError('Unknown/incomplete legacy light parameters')
    _integer(snapshot['light']['radius'], 'legacy light radius')
    for key in ('deform', 'enhance'):
        value = snapshot[key]
        known = {'amounts', 'built', 'box'} if key == 'enhance' else {'amounts', 'built'}
        if type(value) is not dict or set(value) - known or type(value.get('amounts', {})) is not dict:
            raise AdmissionError('Unknown/incomplete portrait intent: ' + key)
    if snapshot.get('body_pose') is not None or snapshot.get('body_pose_source_proof') is not None:
        reasons.append('body source/geometry')
    if snapshot.get('export_skipped'):
        reasons.append('skipped effects')
    params = snapshot['params']
    if type(params) is not dict or set(params) != PARAM_FIELDS:
        raise AdmissionError('Unknown/incomplete tile parameters')
    for name in ('radius', 'texture_radius'):
        _integer(params[name], name)
    if 2 * params['texture_radius'] + 6 * params['radius'] > 2048:
        reasons.append('tile margin exceeds unchanged export limit')
    if params['eps'] <= 0:
        raise AdmissionError('Invalid smoothing epsilon')
    for key in ('grade', 'exposure', 'hsl'):
        if key in snapshot and type(snapshot[key]) not in (tuple, list):
            raise AdmissionError('Invalid colour vector: ' + key)
    grade = tuple(snapshot['grade'])
    if len(grade) != 4:
        raise AdmissionError('Complete legacy grade required')
    check_grade(*grade[:3], amount=grade[3])
    exposure = tuple(snapshot.get('exposure', (0.,) * 7))
    if len(exposure) not in (3, 7):
        raise AdmissionError('Invalid exposure vector')
    reference = snapshot.get('exposure_ref_k')
    check_exposure(*exposure[:3], ref_k=6500. if reference is None else reference)
    check_tone(*(exposure[3:] if len(exposure) == 7 else (0.,) * 4))
    options = WB.normalize_state({'_exposure': exposure, '_exposure_ref_k': reference,
        '_wb_options': snapshot.get('wb_options', WB.default_options())})['_wb_options']
    hsl = check_hsl(snapshot.get('hsl', (0.,) * 24))
    curves, levels = CURVES.check_curves(snapshot.get('curves')), LEVELS.check_levels(snapshot.get('levels'))
    check_amount(snapshot['lut_amount'])
    cube, _ = _cube_fingerprint(snapshot['lut'])
    geom = G.check(snapshot['crop_rect'], snapshot['crop_rotation'])
    arbitrary = G._snapped_quarter_turn(geom[-1]) is None
    if arbitrary and geometry_version == 0:
        reasons.append('arbitrary-angle geometry needs separately admitted renderer')
    lm = LM.check(snapshot.get('local_masks'))
    if lm['recipe']['objects'] or lm['source'] is not None or lm['semantic_owner'] is not None:
        reasons.append('retained local-mask objects/source')
    if LG.check(snapshot.get('local_grade_groups'))['layers']:
        reasons.append('retained local grade groups')
    if ER.check(snapshot.get('effect_recovery'))['targets']:
        reasons.append('retained recovery targets')
    if ML.check(snapshot.get('manual_liquify'))['strokes']:
        reasons.append('retained manual geometry')
    fringe = FR.check(FR.neutral() if snapshot.get('fringe_repair') is None else snapshot['fringe_repair'])
    editor = CE.check(CE.neutral() if snapshot.get('colour_editor') is None else snapshot['colour_editor'])
    grain = PG.check(PG.neutral() if snapshot.get('photo_grain') is None else snapshot['photo_grain'])
    if FR.active(fringe) or fringe['source'] is not None or fringe['coverage']['strokes']:
        reasons.append('fringe repair/source/coverage')
    if CE.active(editor) or editor['scope'] != 'all':
        reasons.append('continuous/local colour editor')
    if ET.active(snapshot.get('extended_tone')) or PD.active(snapshot.get('photo_detail')) or PG.active(grain):
        reasons.append('extended tone/photo detail/grain')
    ident = ID.check(snapshot.get('id_background'))
    if (ident['enabled'] or ident['source'] is not None or ident['background']['asset'] is not None
            or any(v is not None for v in ident['support'].values())):
        reasons.append('ID background/source/support')
    if ST.check(snapshot.get('studio_background'))['source'] is not None:
        reasons.append('retained studio source')
    sky = SKY.check(snapshot.get('sky_replacement'))
    if sky['source'] is not None or sky['asset'] is not None:
        reasons.append('retained sky source/asset')
    optical = OP.check(snapshot.get('optics'))
    if optical['source'] is not None or OP.source_bound(optical):
        reasons.append('retained optics source')
    semantic = SEM.check(snapshot.get('semantic_colour'))
    if semantic['groups'] or semantic['masks'] or any(semantic[key] is not None for key in ('target', 'reference', 'analysis', 'last_review')):
        reasons.append('retained semantic colour sources/masks')
    reference_recipe = REF.check(snapshot.get('reference_color'))
    if reference_recipe['source'] is not None or reference_recipe['reference'] is not None:
        reasons.append('retained reference colour sources')
    if snapshot.get('fabric_amount', 0) != 0:
        reasons.append('fabric processing')
    # Neutralize ONLY a local diagnostic dict, never the user's actual recipe.
    from .master16_policy import Master16PolicyMixin
    diagnostic = dict(snapshot)
    diagnostic.update(people=None, creative_base=None, grade=(0., 0., 0., 1.),
        exposure=(0.,) * 7, wb_options=WB.default_options(), hsl=(0.,) * 24,
        curves=CURVES.default_curves(), levels=LEVELS.default_levels(), lut=None,
        lut_amount=0., crop_rect=(0., 0., 1., 1.), crop_rotation=0.,
        photo_grain=grain, fringe_repair=fringe, colour_editor=editor)
    reasons.extend(Master16PolicyMixin._master16_snapshot_blockers(diagnostic))
    bg = snapshot.get('_bg')
    if bg is None:
        bg = {}
    if type(bg) is not dict or set(bg) - {'active', 'matte', 'bg', 'backend', 'tol', 'softness', 'key_recipe'}:
        raise AdmissionError('Unknown common-background metadata')
    if bg.get('active') or bg.get('key_recipe') is not None:
        reasons.append('retained common background')
    for key in SNAPSHOT_FIELDS:
        if (key.startswith('creative_') and key != 'creative_base') or key in (
            'id_background_bundle', 'semantic_colour_binding', 'semantic_colour_source_path',
            'fringe_repair_source', 'common_background_path', 'common_background_stamp'):
            if snapshot.get(key) is not None:
                reasons.append('unaccounted source-bound field: ' + key)
    if snapshot.get('semantic_colour_mask_assets'):
        reasons.append('semantic colour assets')
    native = {}
    for key, module in (('colour_grading', CG), ('selective_colour', SC), ('primary_calibration', PC)):
        native[key] = module.check(module.neutral() if snapshot.get(key) is None else snapshot[key])
    fingerprint = _freeze(dict(params=params, grade=grade, exposure=exposure,
        exposure_ref_k=reference, wb_options=options, hsl=hsl, curves=curves,
        levels=levels, lut=cube, lut_amount=float(snapshot['lut_amount']), **native))
    features = ['global-colour', 'bounded-arbitrary-angle' if arbitrary else 'integer-crop-quarter-turn']
    if cube is not None:
        features.append('ordinary-cube')
    if CG.active(native['colour_grading']) or SC.active(native['selective_colour']):
        features.append('native-full-colour')
        if arbitrary:
            # The legacy sampler returns f64. Native finishing requires f32;
            # casting or reordering an active effect would change the contract.
            reasons.append('arbitrary angle with active postgeometry native colour')
    if PC.active(native['primary_calibration']):
        features.append('primary-calibration')
    if snapshot.get('people') is not None:
        features.append('neutral-people-requires-source-proof')
    return Eligibility(not reasons, tuple(dict.fromkeys(reasons)), tuple(features), fingerprint)


def classify_snapshot(snapshot, *, geometry_version=0, finishing_version=0):
    """Before preparation, reject optimization without changing selected effects.

    Neutral people candidates still need definitive original source proof in the
    common renderer. Version 0 preserves quarter-turn-only selection. Explicit
    version 1 also permits bounded arbitrary geometry after unchanged export,
    only when every postgeometry effect is neutral. This result never authorizes
    skipping preparation itself or changing the generic export geometry path.
    Finishing version 1 separately opts into bounded native colour buffers; it
    does not expand the recipe cohort or admit native finishing after f64 geometry.
    """
    try:
        return _classify(snapshot, geometry_version=geometry_version, finishing_version=finishing_version)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        return Eligibility(False, ('snapshot admission: ' + str(error),))


def snapshot_eligible(snapshot, *, geometry_version=0, finishing_version=0):
    return classify_snapshot(snapshot, geometry_version=geometry_version,
                             finishing_version=finishing_version).eligible


# Frozen source-audited field inventory. Future fields fail closed.
SPEC_FIELDS = frozenset("""strength radius eps detail_gain mid_gain broad_gain texture_radius channel masks mask_names landmarks repair light light_exposure light_radius deform_amounts cube lut_amount grade grade_scope grade_mask local_masks local_mask_semantics local_mask_source_path creative_mask_context creative_smoothing_context creative_fabric_context creative_recovery_context local_grade_groups local_grade_fields local_grade_source_stamp effect_recovery effect_recovery_path effect_recovery_stamp effect_recovery_fields creative_sky_context sky_replacement sky_replacement_path sky_replacement_stamp sky_replacement_prepared optics optics_path optics_stamp id_background id_background_bundle creative_id_background_context id_background_path id_background_stamp id_background_prepared creative_studio_context studio_background studio_background_path studio_background_stamp studio_background_prepared manual_liquify manual_liquify_path manual_liquify_stamp manual_liquify_field bg_matte bg_ref common_background_key common_background_color common_background_path common_background_stamp enhance people people_document_id body_pose body_pose_source_path body_pose_source_stamp body_pose_source_proof brow_shape brow_shape_face nose_shape nose_shape_face eye_shape eye_shape_face mouth_shape mouth_shape_face lip_makeup lip_makeup_face facial_wrinkle_skin facial_wrinkle_backend facial_wrinkle_model_identity fabric_amount fabric_mask fabric_face_px exposure exposure_ref_k wb_options photo_grain photo_detail fringe_repair fringe_repair_path fringe_repair_stamp extended_tone colour_grading selective_colour colour_editor primary_calibration reference_color semantic_colour semantic_colour_binding semantic_colour_source_path semantic_colour_source_stamp float_output provenance_output provenance_result hsl curves levels scale upscale_backend sharpen_amount sharpen_radius sharpen_threshold creative_base""".split())
SPEC_PRIVATE_FIELDS = frozenset(('_common_background_retained', '_creative_capture_original_source',
    '_sky_replacement_immutable_input', '_sky_replacement_replay_key', '_common_recovery_recipe'))
SPEC_RECIPE_FIELDS = frozenset('''strength radius eps detail_gain mid_gain broad_gain texture_radius cube lut_amount grade grade_scope exposure exposure_ref_k wb_options hsl curves levels scale upscale_backend sharpen_amount sharpen_radius sharpen_threshold light_exposure light_radius colour_grading selective_colour primary_calibration people people_document_id float_output'''.split())
SPEC_NEUTRAL_RECIPES = frozenset('''local_masks local_grade_groups effect_recovery manual_liquify studio_background id_background optics sky_replacement lip_makeup brow_shape nose_shape eye_shape mouth_shape enhance photo_grain photo_detail fringe_repair extended_tone colour_editor reference_color semantic_colour'''.split())
SPEC_EMPTY_FIELDS = frozenset(('repair', 'light', 'deform_amounts', 'mask_names', 'local_mask_semantics'))


def _spec_data(spec):
    from .export import ExportSpec
    if type(spec) is not ExportSpec:
        raise AdmissionError('Edited capture requires an ordinary ExportSpec')
    if {entry.name for entry in fields(ExportSpec)} != SPEC_FIELDS:
        raise AdmissionError('ExportSpec schema changed since edited capture audit')
    data = object.__getattribute__(spec, '__dict__')
    if set(data) - (SPEC_FIELDS | SPEC_PRIVATE_FIELDS) or not SPEC_FIELDS <= set(data):
        raise AdmissionError('Unknown/missing postbuild ExportSpec fields')
    return data


def _check_source_context(context):
    if type(context) is not dict or set(context) != {'path', 'file_stamp', 'asset_sha256', 'document_id'}:
        raise AdmissionError('Invalid original-capture census context')
    if type(context['path']) is not str or not context['path'] or '\x00' in context['path']:
        raise AdmissionError('Invalid original-capture source path')
    stamp = context['file_stamp']
    if type(stamp) not in (list, tuple) or len(stamp) != 5 or any(type(v) is not int for v in stamp):
        raise AdmissionError('Invalid original-capture source stamp')
    digest = context['asset_sha256']
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise AdmissionError('Invalid original-capture source digest')
    if type(context['document_id']) is not str or not context['document_id']:
        raise AdmissionError('Invalid original-capture document identity')


def _snapshot_from_spec(data, snapshot):
    result = {key: data[key] for key in SPEC_NEUTRAL_RECIPES | SPEC_RECIPE_FIELDS
              if key in SNAPSHOT_FIELDS}
    result.update(params={key: data[key] for key in PARAM_FIELDS},
        lut=data['cube'], sharpen=data['sharpen_amount'], repair_ops=data['repair'],
        light_ops=data['light'], light={'exposure': data['light_exposure'], 'radius': data['light_radius']},
        deform={'amounts': data['deform_amounts'], 'built': False},
        enhance={'amounts': data['enhance'], 'built': False}, channel=data['channel'],
        precompute=None, grade_mask=data['grade_mask'], creative_base=data['creative_base'],
        body_pose=data['body_pose'], body_pose_source_proof=data['body_pose_source_proof'],
        _bg={}, crop_rect=(0., 0., 1., 1.), crop_rotation=0., device='cpu')
    if snapshot is not None:
        result['crop_rect'] = snapshot['crop_rect']
        result['crop_rotation'] = snapshot['crop_rotation']
    return result


def validate_spec(spec, snapshot=None, *, skipped=(), geometry_version=0, finishing_version=0):
    """Return eligible Eligibility or raise on postbuild recipe/resource drift.

    Does not call mutating ExportSpec.check or replace downstream validation.
    Private original-source context is structural evidence only; it never alone
    authorizes bypassing the definitive neutral-people gate.
    """
    _integer(geometry_version, 'geometry version', maximum=1)
    _integer(finishing_version, 'finishing version', maximum=1)
    if skipped:
        raise AdmissionError('Edited capture cannot omit export effects')
    data = _spec_data(spec)
    inspect_storage(data)
    for key in SPEC_FIELDS - SPEC_RECIPE_FIELDS - SPEC_NEUTRAL_RECIPES - SPEC_EMPTY_FIELDS:
        value = data[key]
        if key == 'fabric_amount':
            if value != 0:
                raise AdmissionError('Fabric processing is outside edited capture admission')
        elif key == 'provenance_output':
            if value is not False:
                raise AdmissionError('Provenance tap is outside edited capture admission')
        elif value is not None:
            raise AdmissionError('Unaccounted postbuild export field: ' + key)
    for key in SPEC_EMPTY_FIELDS:
        if data[key]:
            raise AdmissionError('Unaccounted postbuild export collection: ' + key)
    for key in ('_common_background_retained', '_sky_replacement_immutable_input',
                '_sky_replacement_replay_key', '_common_recovery_recipe'):
        if data.get(key) is not None:
            raise AdmissionError('Unaccounted postbuild private owner: ' + key)
    if '_creative_capture_original_source' in data:
        _check_source_context(data['_creative_capture_original_source'])
    result = classify_snapshot(_snapshot_from_spec(data, snapshot), geometry_version=geometry_version,
                               finishing_version=finishing_version)
    if not result.eligible:
        raise AdmissionError('Postbuild edited capture rejected: ' + '; '.join(result.reasons))
    if snapshot is not None:
        original = classify_snapshot(snapshot, geometry_version=geometry_version,
                                     finishing_version=finishing_version)
        if not original.eligible or result.fingerprint != original.fingerprint:
            raise AdmissionError('Postbuild export differs from admitted colour recipe')
        if (data['people'] is None) != (snapshot.get('people') is None):
            raise AdmissionError('Postbuild export changed people census presence')
    return result


def plan_capture(metadata, snapshot=None, *, spec=None, max_bytes,
                 retained_bytes=0, persistent_retained_bytes=0,
                 host_lease_bytes=0, tile=DEFAULT_TILE, geometry_version=0, finishing_version=0):
    """Named conservative phases before genuine decode and again after build.

    Use public inspect_encoded_source metadata. retained_bytes includes all
    frozen/state/context/spec roots but NOT encoded original/ICC. Persistent
    caller state is already included there, then charged separately in output
    tail phases after transient roots end. Other live session owners require the
    host lease. All source identity, opacity and decoder gates remain required.
    Geometry version 1 is explicit deferred bounded sampling, not a change to
    generic export. geometry_max_bytes covers geometry's source backing, output
    and scratch after subtracting every nongeometry live owner from max_bytes.
    Finishing version 1 replaces only active native colour's whole-frame buffer
    phase; finishing_max_bytes similarly excludes every nonfinishing live owner.
    """
    from .creative_document_assets import MAX_PIXELS, MAX_ORIGINAL_BYTES
    from .creative_document_import_bounded import ImportMemoryPlan
    from .ops import geometry as G
    _integer(geometry_version, 'geometry version', maximum=1)
    _integer(finishing_version, 'finishing version', maximum=1)
    _integer(max_bytes, 'capture budget', minimum=1, maximum=MAX_WORK_BYTES)
    _integer(retained_bytes, 'retained capture bytes')
    _integer(persistent_retained_bytes, 'persistent retained capture bytes')
    _integer(host_lease_bytes, 'host lease bytes')
    if type(tile) is not int or tile != DEFAULT_TILE:
        raise AdmissionError('Edited capture preserves the existing 1024 export tile')
    if type(metadata) is not dict or metadata.get('format') not in ('JPEG', 'PNG'):
        raise AdmissionError('Edited capture requires inspected original JPEG/PNG metadata')
    width = _integer(metadata.get('width'), 'source width', minimum=1)
    height = _integer(metadata.get('height'), 'source height', minimum=1)
    source_bits = metadata.get('bits')
    if type(source_bits) is not int or source_bits not in (1, 2, 4, 8, 16) or (metadata['format'] == 'JPEG' and source_bits != 8):
        raise AdmissionError('Unsupported original precision')
    bits = 16 if source_bits == 16 else 8  # genuine low-bit PNG expansion; metadata unchanged
    orientation = _integer(metadata.get('orientation'), 'source orientation', minimum=1, maximum=8)
    working_orientation = _integer(metadata.get('working_orientation'), 'working orientation', minimum=1, maximum=8)
    if working_orientation != orientation:
        raise AdmissionError('Working and canonical decoder orientation differ')
    original_bytes = _integer(metadata.get('original_bytes'), 'encoded original bytes', minimum=1, maximum=MAX_ORIGINAL_BYTES)
    icc = metadata.get('icc')
    if type(icc) is not bytes or len(icc) > 4 * 1024 * 1024:
        raise AdmissionError('Invalid inspected ICC provenance')
    import_plan = metadata.get('import_plan')
    if type(import_plan) is not ImportMemoryPlan:
        raise AdmissionError('Public metadata import plan is required')
    if (import_plan.width, import_plan.height, import_plan.bits, import_plan.format,
            import_plan.original_bytes, import_plan.icc_bytes) != (width, height, source_bits,
            metadata['format'], original_bytes, len(icc)):
        raise AdmissionError('Metadata and inspected source plan disagree')
    codec = _integer(import_plan.codec_workspace_reserve, 'codec workspace')
    n = width * height
    if n > MAX_PIXELS:
        raise AdmissionError('Source exceeds canonical pixel limit')
    if spec is None:
        eligibility = classify_snapshot(snapshot, geometry_version=geometry_version,
                                        finishing_version=finishing_version)
        if not eligibility.eligible:
            raise AdmissionError('Snapshot not eligible: ' + '; '.join(eligibility.reasons))
        params = snapshot['params']
        margin = 2 * params['texture_radius'] + 6 * params['radius']
        cube = snapshot['lut']
    else:
        eligibility = validate_spec(spec, snapshot, geometry_version=geometry_version,
                                    finishing_version=finishing_version)
        data = _spec_data(spec)
        from .export import ExportSpec
        margin = ExportSpec.margin_px(spec)
        cube = data['cube']
    geometry = ((0., 0., 1., 1.), 0.) if snapshot is None else (snapshot['crop_rect'], snapshot['crop_rotation'])
    x0, y0, x1, y1, rotation = G.check(*geometry)
    arbitrary = G._snapped_quarter_turn(rotation) is None
    if arbitrary and geometry_version == 0:
        raise AdmissionError('Unsnapped geometry requires its separate bounded admission')
    ow, oh = G.out_size(width, height, *geometry)
    m = ow * oh
    if m > MAX_PIXELS:
        raise AdmissionError('Output exceeds canonical pixel limit')
    xa, xb = G._cut(width, x0, x1)
    ya, yb = G._cut(height, y0, y1)
    c = (xb - xa) * (yb - ya)
    t = min(height, tile + 2 * margin) * min(width, tile + 2 * margin)
    _, table_upload = _cube_fingerprint(cube)
    # CPU f64 table is in retained owners. Extra 8 bytes/sample reserve covers
    # float32 conversion and a distinct torch/device copy, not a changed sampler.
    census = inspect_storage((snapshot,) if spec is None else (snapshot, spec))
    retained = max(retained_bytes, census.total_bytes + census.container_bytes)
    if persistent_retained_bytes > retained:
        raise AdmissionError('Persistent capture owners must be included in retained bytes')
    common = (('host-lease', host_lease_bytes), ('metadata-allocator', METADATA_RESERVE))
    provenance = (('encoded-original', original_bytes), ('retained-icc', len(icc)))
    render = common + provenance + (('capture-snapshot-owners', retained),)
    tail = common + provenance + (('persistent-caller-state', persistent_retained_bytes),)
    integer = ('integer-working-source', (3 if bits == 8 else 6) * n)
    native = ('native-allocator-reserve', NATIVE_RESERVE)
    last_tile = ('last-export-rgb-tile', 12 * t)
    block = min(BLOCK_PIXELS, m)
    geometry_max_bytes = 0  # no deferred sampler for default/snapped geometry
    finishing_max_bytes = 0  # neutral/default finishing never requests this hook
    owners = [
        ('snapshot-recipe-validation', render + (
             ('retained-array-validation', census.validation_scratch_bytes), native)),
        ('header-read', common + (('original-read-and-immutable', 2 * original_bytes),
             ('capture-snapshot-owners', retained), ('icc-parser-overlap', 5 * len(icc)), native)),
        # PNG16 independently admits 2O+64N+64MiB. Capture owns a THIRD O.
        ('decode-icc', common + (('three-encoded-source-owners', 3 * original_bytes),
             ('decode-working-overlap', 64 * n), ('codec-workspace', codec),
             ('icc-profile-overlap', 5 * len(icc)), ('capture-snapshot-owners', retained), native)),
        ('common-tile-render', render + (integer, ('stitched-float-rgb', 12 * n),
             ('halo-colour-workspace', TILE_BYTES_PER_PIXEL * t),
             ('lut-upload-copies', table_upload), native)),
    ]
    if arbitrary:
        from . import creative_capture_geometry as bounded_geometry
        if (bounded_geometry.GEOMETRY_VERSION != 'edited-capture-numpy-geometry-v1'
                or bounded_geometry.BLOCK_PIXELS != BLOCK_PIXELS):
            raise AdmissionError('Bounded geometry strategy changed since capture admission audit')
        # Same exported conservative component family as actual-array admission.
        # No dummy raster, full f64 source conversion or pixel scan is needed.
        scratch = tuple(('geometry-' + name, multiplier * block)
                        for name, multiplier in bounded_geometry.ARBITRARY_SCRATCH_PER_PIXEL)
        geometry_live = render + (integer, last_tile, native)
        geometry_max_bytes = max_bytes - sum(amount for _, amount in geometry_live)
        owners.append(('bounded-arbitrary-geometry', geometry_live + (
            ('stitched-rgb-backing', 12 * n), ('arbitrary-float64-output', 24 * m),
            *scratch,
            ('geometry-array-workspace', bounded_geometry.ARRAY_WORKSPACE_RESERVE),
            ('geometry-metadata', bounded_geometry.METADATA_RESERVE))))
    else:
        owners.append(('crop-quarter-turn', render + (integer, ('stitched-rgb-backing', 12 * n),
            ('integer-crop-copy', 12 * c), ('quarter-turn-output', 12 * m), last_tile, native)))
    if 'native-full-colour' in eligibility.features:
        if finishing_version == 1:
            from . import creative_capture_finishing as bounded_finishing
            if (bounded_finishing.FINISHING_VERSION != 'edited-capture-colour-finishing-v1'
                    or bounded_finishing.BLOCK_PIXELS != BLOCK_PIXELS):
                raise AdmissionError('Bounded finishing strategy changed since capture admission audit')
            finishing_live = render + (integer, last_tile, native)
            finishing_max_bytes = max_bytes - sum(amount for _, amount in finishing_live)
            scratch = tuple(('finishing-' + name, multiplier * block)
                            for name, multiplier in bounded_finishing.SCRATCH_PER_PIXEL)
            owners.append(('bounded-colour-finishing', finishing_live + (
                # Only one postgeometry RGB source owner survives assignment.
                # A contiguous small crop may still retain the full 12N backing.
                ('finishing-source-backing', max(12 * n, 12 * m)),
                ('private-finishing-rgb', 12 * m), *scratch,
                ('finishing-array-workspace', bounded_finishing.ARRAY_WORKSPACE_RESERVE),
                ('finishing-metadata', bounded_finishing.METADATA_RESERVE))))
        else:
            owners.append(('native-colour-finishing', render + (integer,
                ('retained-stitch-backing', 12 * n), ('native-input-output', 24 * m),
                ('validation-contiguous-return-reserve', 36 * m), last_tile, native)))
    # A small contiguous crop can still retain 12N original backing. Deferred
    # arbitrary geometry owns f64 output; never price that result as f32.
    owners.extend((
        ('rgb-to-canonical', tail + (('output-rgb-backing', max(12 * n, (24 if arbitrary else 12) * m)),
            ('private-rgba-sink', 16 * m), ('row-transfer-staging', 48 * block),
            ('array-workspace', VALIDATION_RESERVE))),
        ('immutable-freeze', tail + (('mutable-and-immutable-rgba', 32 * m),)),
        ('validate-intern', tail + (('immutable-rgba', 16 * m), ('validation-scratch', VALIDATION_RESERVE))),
    ))
    phases = tuple((name, sum(amount for _, amount in entries)) for name, entries in owners)
    plan = CaptureMemoryPlan(width, height, ow, oh, bits, margin, t, retained,
                             phases, tuple(owners), max_bytes,
                             geometry_max_bytes=geometry_max_bytes, geometry_version=geometry_version,
                             finishing_max_bytes=finishing_max_bytes, finishing_version=finishing_version)
    if plan.peak_bytes > max_bytes:
        raise CaptureBudgetExceeded('%s requires declared working set %d bytes; budget is %d' %
                                   (plan.peak_phase, plan.peak_bytes, max_bytes))
    return plan
