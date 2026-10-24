"""Prepare every face using frozen source inputs; no selected-face engine state.

Shared by actual preview and original-source export. Source integration is not
runtime acceptance evidence. Missing evidence or any requested face refusal
prevents publication of a silently partial render.
"""
from dataclasses import dataclass
import hashlib
import numpy as np
from . import people_state as S, people_algorithms as A, people_render_plan as P
from . import people_effects as E
from .people_geometry import combine


class PeoplePreparationRefused(ValueError):
    def __init__(self, refusals):
        self.refusals = refusals
        super().__init__('People render preparation refused: ' + '; '.join(x['face_instance_id'] + ': ' + x['reason'] for x in refusals))


@dataclass(frozen=True)
class PreparedPeople:
    plan: dict
    geometry: object
    effects: tuple
    facts: dict
    recovery: dict
    face_fields: tuple=()
    body_fields: tuple=()
    body_operation_order: dict|None=None

    def apply_source_stage(self, stage, pixels):
        return E.apply(stage, pixels, self.effects, recovery=self.recovery)

    def align_source_field(self, field):
        return self.geometry.warp(field)

    def authentic_scene_support(self, field):
        """Reference-colour producer must use this SAME all-face real map."""
        value = np.asarray(field)
        if value.ndim != 2 or np.any((value < 0) | (value > 1)):
            raise ValueError('Authentic scene support must be source-frame coverage')
        return self.align_source_field(value)


def verify_analysis(face, analysis, shape):
    from .skin_colour_support import FIELDS, check_analysis_fields
    from .body_skin_semantics import FIELDS as BODY_FIELDS, check_analysis_fields as check_body_fields
    required = {'face_ref', 'evidence', 'landmarks', 'excluded', 'skin'}
    if type(analysis) is not dict or not required.issubset(analysis) or set(analysis) - required - FIELDS - BODY_FIELDS:
        raise ValueError('Frozen per-face analysis fields are incomplete')
    if analysis['face_ref'] != S.face_ref(face) or analysis['evidence'] != face['evidence']:
        raise ValueError('Frozen analysis owner/evidence does not match durable instance')
    evidence = S.check_evidence(analysis['evidence'])
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('Real face analysis required, not manually invented or synthetic landmarks')
    lm = np.asarray(analysis['landmarks'], dtype='<f4')
    if lm.shape != (478,3) or not np.isfinite(lm).all(): raise ValueError('Invalid frozen face landmarks')
    if hashlib.sha256(np.ascontiguousarray(lm).tobytes()).hexdigest() != evidence['landmark_digest']:
        raise ValueError('Frozen landmark bytes differ from retained analysis')
    for key in ('excluded', 'skin'):
        mask = analysis[key]
        if mask is not None and (mask.shape != tuple(shape) or not np.isfinite(mask).all() or np.any((mask < 0) | (mask > 1))):
            raise ValueError('Frozen face semantic support differs from source frame')
        if mask is not None and evidence['semantic_model_sha256'] is None:
            raise ValueError('Semantic support lacks actual loaded-model evidence')
    check_analysis_fields(analysis, shape)
    check_body_fields(analysis, shape)
    return lm


def prepare(state, asset_sha256, source, analyses, *, byte_budget, document_id=None, max_faces=32, recovery_assets=None, repaired=None,
            creative_source=None, creative_repair_evidence=None, hair_assets=None, hair_evidence=None, hair_source_path=None, force_hair_prompted=False, eye_light_assets=None, blush_makeup_assets=None, lipstick_assets=None,eyeliner_assets=None,eyelash_assets=None,brow_makeup_assets=None,iris_makeup_assets=None,skin_colour_body_assets=None,skin_finish_body_assets=None,body_bank=None):
    state = S.check(state)
    from .people_cross_owner import validate_owner
    validate_owner(state,asset_sha256,document_id)
    source_only = creative_source is not None
    if source_only:
        from .creative_derived_effects import require_graph
        require_graph(state,creative_source,document_id=document_id)
        if asset_sha256 != creative_source['sha256']:
            raise ValueError('Derived portrait graph source mismatch')
        if hair_source_path is not None:
            raise ValueError('Derived portrait runtime cannot acquire original-file inputs')
        if repaired is not None:
            from .creative_derived_repair_runtime import verify_evidence
            verify_evidence(creative_repair_evidence,creative_source,source,repaired)
        from .creative_derived_hair import validate as validate_hair
        validate_hair(state,hair_assets or {},hair_evidence,creative_source)
        from .creative_derived_makeup import validate_supports
        # Each port carries the same canonical bank, but validate against its
        # actual supplied bank below rather than trusting that caller convention.
        banks = {'eye_light_visibility':eye_light_assets,'lipstick_visibility':lipstick_assets,
            'blush_makeup_visibility':blush_makeup_assets,'eyeliner_visibility':eyeliner_assets,
            'eyelash_visibility':eyelash_assets,'brow_makeup_visibility':brow_makeup_assets,
            'iris_makeup_visibility':iris_makeup_assets}
        for kind,bank in banks.items():
            validate_supports(state,bank or {},asset_sha256,only_kind=kind)
    if type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3 or source.shape[2] != 3 or not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('People preparation needs frozen working-sRGB float32 RGB')
    effect_source = source if repaired is None else repaired
    if type(effect_source) is not np.ndarray or effect_source.dtype != np.float32 or effect_source.shape != source.shape or not np.isfinite(effect_source).all() or np.any((effect_source<0)|(effect_source>1)):
        raise ValueError('Repaired effect source must share the original frozen source frame')
    pending = [x for x in state['unresolved_legacy'] if x['asset_sha256']==asset_sha256 and x['status']=='unresolved']
    if pending:
        raise PeoplePreparationRefused([{'face_instance_id':'legacy','reason':'Review retained ambiguous legacy intent: '+x['legacy_key']} for x in pending])
    if not any(face['asset_sha256']==asset_sha256 for face in state['faces'].values()):
        from .brow_enhance_project import validate_leaf as validate_brow_leaf
        for row in state['overrides']:
            if (row['scope']=='all_people' and row['target_id']==asset_sha256
                    and row['operation_id']==A.BROW_ENHANCE.OP):
                validate_brow_leaf(row['parameter_path'], row['value'])
            if (row['scope']=='all_people' and row['target_id']==asset_sha256
                    and row['operation_id']==A.LIP_TEXTURE.OP):
                from .lip_texture_project import validate_leaf as validate_lip_leaf
                validate_lip_leaf(row['parameter_path'], row['value'])
    if not any(face['asset_sha256']==asset_sha256 for face in state['faces'].values()) and any(
            row['scope']=='all_people' and row['target_id']==asset_sha256
            and row['value']!=A.defaults().get(row['operation_id'],{}).get(row['parameter_path'])
            and not (row['operation_id']==A.EYE_SYMMETRY.OP and row['parameter_path']=='/reference'
                     and type(row['value']) is str and row['value'] in A.EYE_SYMMETRY.REFERENCES)
            and not (row['operation_id']==A.BROW_ENHANCE.OP and row['parameter_path']=='/linked'
                     and type(row['value']) is bool)
            for row in state['overrides']):
        raise ValueError('Requested photograph-wide portrait parameters have no retained face; add or analyse a face before rendering')
    h,w = source.shape[:2]
    if source_only:
        from .creative_derived_recovery import validate_fields
        validate_fields(state,creative_source,recovery_assets or {},(h,w))
    # Conservative admission includes full-source algorithms and joint map. This
    # is a refusal bound, not a measured peak; never downsample requested export.
    if type(byte_budget) is not int or byte_budget < h*w*256 + 128*1024*1024:
        raise ValueError('Multi-person source analysis exceeds memory admission budget')
    evidence = {key:{'face_ref':value['face_ref'],'evidence':value['evidence']} for key,value in analyses.items()}
    plan = P.build(state, asset_sha256, A.defaults(), max_faces=max_faces, per_face_cost=1,
                   total_budget=max_faces, available_evidence=evidence, operation_check=lambda _face,_resolved:[])
    failures = []; fields = []; effects = []; facts = {}; owned_recovery = {}
    for entry in plan['entries']:
        key = entry['face_ref']['face_instance_id']
        try:
            if entry['status'] != 'ready': raise ValueError(', '.join(entry['reasons']))
            values = A.recipes(entry['resolved'])
            A.validate_compatibility(values)
            if not entry['requires_analysis']: continue
            face = state['faces'][key]; analysis = analyses[key]
            for asset in face['local_assets'].values():
                stage = asset['kind']
                if stage in ('skin_colour_body_visibility','skin_finish_body_visibility'):
                    # Separate operation-owned support, never generic recovery.
                    # Resolve each only when its own recipe is active below;
                    # dormant review cannot prevent disabling either recipe.
                    continue
                if stage=='iris_makeup_visibility':
                    from .iris_makeup_support import resolve as resolve_iris_support
                    resolve_iris_support(state,iris_makeup_assets or {},entry['face_ref'])
                    continue
                if stage=='eyeliner_visibility':
                    from .eyeliner_support import resolve as resolve_eyeliner_support
                    resolve_eyeliner_support(state,eyeliner_assets or {},entry['face_ref'])
                    continue
                if stage=='eyelash_visibility':
                    from .eyelash_support import resolve as resolve_eyelash_support
                    resolve_eyelash_support(state,eyelash_assets or {},entry['face_ref'])
                    continue
                if stage=='brow_makeup_visibility':
                    from .brow_makeup_support import resolve as resolve_brow_makeup_support
                    resolve_brow_makeup_support(state,brow_makeup_assets or {},entry['face_ref'])
                    continue
                if stage=='lipstick_visibility':
                    from .lipstick_support import resolve as resolve_lipstick_support
                    resolve_lipstick_support(state,lipstick_assets or {},entry['face_ref'])
                    continue
                if stage=='blush_makeup_visibility':
                    from .blush_makeup_support import resolve as resolve_blush_support
                    resolve_blush_support(state,blush_makeup_assets or {},entry['face_ref'])
                    continue
                if stage=='eye_light_visibility':
                    from .eye_light_support import resolve as resolve_eye_support
                    resolve_eye_support(state,eye_light_assets or {},entry['face_ref'])
                    continue
                if stage=='hair_colour':continue # Dedicated source-owned consumer, not recovery.
                if stage not in E.STAGES:
                    raise ValueError('Source-owned local support requires an explicit consumer: ' + stage)
                recovery = (recovery_assets or {}).get((key,stage))
                if recovery is None or recovery.get('recipe_sha256') != asset['content_sha256']:
                    raise ValueError('Retained recovery asset is missing; refusing to ignore it')
                E.verify_recovery(entry['face_ref'], stage, recovery, (h,w))
                owned = {**recovery, 'weight':recovery['weight'].copy()}
                owned['weight'].setflags(write=False); owned_recovery[(key,stage)] = owned
            lm = verify_analysis(face, analysis, (h,w))
            A.SLIM_FACE.check_coexistence(values[A.SLIM_FACE.OP], values[A.DEFORM]['slim_face'],
                                        values[A.FACE_CONTOUR.OP])
            field = A.build_geometry(key, lm, values, source, analysis['excluded'], backend=face['evidence']['backend'])
            from .slim_face_people import append as append_slim
            field, slim_facts = append_slim(field, state, entry['face_ref'], analysis, source,
                                          values[A.SLIM_FACE.OP], values[A.DEFORM]['slim_face'],
                                          values[A.FACE_CONTOUR.OP])
            from .face_contour_people import append as append_contour
            field, contour_facts = append_contour(field, state, entry['face_ref'], analysis, source, values[A.FACE_CONTOUR.OP])
            from .face_size_people import append as append_size
            field, size_facts = append_size(field, state, entry['face_ref'], analysis, source, values[A.FACE_SIZE.OP])
            from .lower_face_people import append as append_lower
            field, lower_facts = append_lower(field, state, entry['face_ref'], analysis, source, values[A.LOWER_FACE.OP])
            from .mid_face_people import append as append_mid
            field, mid_facts = append_mid(field, state, entry['face_ref'], analysis, source, values[A.MID_FACE.OP])
            from .chin_shape_people import append as append_chin
            field, chin_facts = append_chin(field, state, entry['face_ref'], analysis, source, values[A.CHIN_SHAPE.OP])
            from .chin_length_people import append as append_chin_length
            field, chin_length_facts = append_chin_length(field, state, entry['face_ref'], analysis, source,
                values[A.CHIN_LENGTH.OP], legacy_amount=values[A.DEFORM]['small_chin'])
            from .philtrum_people import append as append_philtrum
            field, philtrum_facts = append_philtrum(field, state, entry['face_ref'], analysis, source, values[A.PHILTRUM.OP])
            from .eye_symmetry_people import append as append_eye_symmetry
            field, eye_symmetry_facts = append_eye_symmetry(field, state, entry['face_ref'], analysis, source, values[A.EYE_SYMMETRY.OP])
            blush_review=lipstick_review=None
            from .lipstick_support import raster as lipstick_raster
            lipstick_review=lipstick_raster(state,lipstick_assets or {},entry['face_ref'],(h,w)) if A.LIPSTICK.active(values[A.LIPSTICK.OP]) else None
            from .blush_makeup_support import raster as blush_raster
            blush_review=blush_raster(state,blush_makeup_assets or {},entry['face_ref'],(h,w)) if A.BLUSH.active(values[A.BLUSH.OP]) else None
            local = E.prepare(entry['face_ref'], lm, values, effect_source, excluded=analysis['excluded'], skin=analysis['skin'],
                              backend=face['evidence']['backend'], semantic_sha=face['evidence']['semantic_model_sha256'],blush_review=blush_review,lipstick_review=lipstick_review,source_only=source_only)
            if (A.SKIN_COLOUR.active(values[A.SKIN_COLOUR.OP])
                    or A.SKIN_FINISH.active(values[A.SKIN_FINISH.OP])
                    or A.SKIN_GLOSS.active(values[A.SKIN_GLOSS.OP])
                    or A.SKIN_TEXTURE.active(values[A.SKIN_TEXTURE.OP])):
                from .skin_colour_people import prepare as prepare_skin_colour
                others = []; protected_boxes = []
                for other_key, other_face in state['faces'].items():
                    if other_key == key or other_face['asset_sha256'] != asset_sha256:
                        continue
                    other = analyses.get(other_key)
                    try:
                        verify_analysis(other_face, other, (h,w))
                    except ValueError:
                        protected_boxes.append(other_face['box'])
                    else:
                        others.append(other)
                # Reserve already-owned records and the retained analysis bank
                # before another face can allocate private support/native work.
                seen_arrays = set(); analysis_bytes = 0
                for row in analyses.values():
                    for array in row.values():
                        if isinstance(array,np.ndarray) and id(array) not in seen_arrays:
                            seen_arrays.add(id(array)); analysis_bytes += array.nbytes
                prior_bytes = sum(f.resident_bytes() for f in fields) + field.resident_bytes()
                prior_bytes += sum(a.nbytes for record in (*effects,*local)
                                   for a in (record.delta,record.weights) if a is not None)
                local.extend(prepare_skin_colour(entry['face_ref'], analysis, others, effect_source,
                    values[A.SKIN_COLOUR.OP], byte_budget=byte_budget-analysis_bytes-prior_bytes,
                    protected_boxes=protected_boxes,people_state=state,
                    body_assets=skin_colour_body_assets,body_bank=body_bank,
                    finish_recipe=values[A.SKIN_FINISH.OP],finish_body_assets=skin_finish_body_assets,
                    gloss_recipe=values[A.SKIN_GLOSS.OP],texture_recipe=values[A.SKIN_TEXTURE.OP]))
            from .eye_light_people import prepare as prepare_eye_light
            from .eye_light_state import OPERATION as EYE_LIGHT
            local.extend(prepare_eye_light(state,eye_light_assets or {},entry['face_ref'],analysis,effect_source,values[EYE_LIGHT],source_revision=state['revision']))
            if A.EYELINER.active(values[A.EYELINER.OP]):
                from .eyeliner_people import prepare as prepare_eyeliner
                local.extend(prepare_eyeliner(state,eyeliner_assets or {},entry['face_ref'],analysis,effect_source,values[A.EYELINER.OP],source_revision=state['revision']))
            if A.EYELASH.active(values[A.EYELASH.OP]):
                from .eyelash_people import prepare as prepare_eyelash
                local.extend(prepare_eyelash(state,eyelash_assets or {},entry['face_ref'],analysis,effect_source,values[A.EYELASH.OP],source_revision=state['revision']))
            if A.LIP_TEXTURE.active(values[A.LIP_TEXTURE.OP]):
                from .lip_texture_layer import prepare as prepare_lip_texture
                lip_neighbors = tuple(tuple(other['box']) for other_key, other in state['faces'].items()
                    if other_key != key and other['asset_sha256'] == asset_sha256)
                local.extend(prepare_lip_texture(entry['face_ref'], analysis, effect_source,
                    values[A.LIP_TEXTURE.OP], byte_budget=byte_budget,
                    protected_boxes=lip_neighbors))
            if A.BROW_ENHANCE.active(values[A.BROW_ENHANCE.OP]):
                from .brow_enhance_layer import prepare as prepare_brow_enhance
                brow_neighbors = tuple(tuple(other['box']) for other_key, other in state['faces'].items()
                    if other_key != key and other['asset_sha256'] == asset_sha256)
                local.extend(prepare_brow_enhance(entry['face_ref'], analysis, effect_source,
                    values[A.BROW_ENHANCE.OP], byte_budget=byte_budget,
                    protected_boxes=brow_neighbors))
            if A.BROW_MAKEUP.active(values[A.BROW_MAKEUP.OP]):
                from .brow_makeup_people import prepare as prepare_brow_makeup
                local.extend(prepare_brow_makeup(state,brow_makeup_assets or {},entry['face_ref'],analysis,effect_source,values[A.BROW_MAKEUP.OP],source_revision=state['revision']))
            if A.IRIS.active(values[A.IRIS.OP]):
                from .iris_makeup_people import prepare as prepare_iris
                local.extend(prepare_iris(state,iris_makeup_assets or {},entry['face_ref'],analysis,effect_source,values[A.IRIS.OP]))
            # Preserve mouth's source-cavity teeth veto independently per face.
            # Contour appends a fifth field; the legacy mouth slot remains 3.
            mouth = field.fields[3]
            if mouth is not None and mouth.state is not None:
                for record in local:
                    if record.stage == 'enhance':
                        y,x,rh,rw = record.window
                        record.weights.setflags(write=True)
                        record.weights[2] *= mouth.teeth_support[y:y+rh,x:x+rw]
                        record.weights.setflags(write=False)
            resident = sum(f.resident_bytes() for f in fields)+field.resident_bytes()
            resident += sum(a.nbytes for record in (*effects,*local) for a in (record.delta,record.weights) if a is not None)
            if resident+h*w*256+128*1024*1024 > byte_budget: raise ValueError('Accumulated portrait fields exceed memory budget')
            fields.append(field); effects.extend(local)
            facts[key] = {record.stage:record.facts for record in local}
            if slim_facts is not None: facts[key]['slim_face_v2'] = slim_facts
            if size_facts is not None: facts[key]['face_size'] = size_facts
            if lower_facts is not None: facts[key]['lower_face'] = lower_facts
            if mid_facts is not None: facts[key]['mid_face'] = mid_facts
            if chin_facts is not None: facts[key]['chin_shape'] = chin_facts
            if chin_length_facts is not None: facts[key]['chin_length'] = chin_length_facts
            if philtrum_facts is not None: facts[key]['philtrum'] = philtrum_facts
            if eye_symmetry_facts is not None: facts[key]['eye_symmetry'] = eye_symmetry_facts
            if contour_facts is not None: facts[key]['face_contour'] = contour_facts
            liner_facts=[record.facts for record in local if record.stage=='eyeliner']
            if liner_facts:facts[key]['eyeliner']={'eyes':liner_facts,'stage':'source-working-srgb'}
            lash_facts=[record.facts for record in local if record.stage=='eyelash']
            if lash_facts:facts[key]['eyelash']={'parts':lash_facts,'stage':'source-working-srgb'}
            brow_facts=[record.facts for record in local if record.stage=='brow_makeup']
            if brow_facts:facts[key]['brow_makeup']={'brows':brow_facts,'stage':'source-working-srgb'}
            eye_facts=[record.facts for record in local if record.stage=='eye_light']
            if eye_facts:facts[key]['eye_light']={'eyes':eye_facts,'stage':'source-working-srgb','physical_light_recovery':False}
            facts[key].update({name:part.facts for name,part in zip(('brow_shape','nose_shape','eye_shape','mouth_shape'),field.fields) if part is not None})
        except (ValueError, RuntimeError, OSError, MemoryError) as error:
            failures.append({'face_instance_id':key,'reason':str(error)})
    if failures: raise PeoplePreparationRefused(failures)
    geometry = combine(fields, (h,w), byte_budget=byte_budget)
    prepared=PreparedPeople(plan, geometry, tuple(effects), facts, owned_recovery,tuple(fields))
    if source_only:
        from .creative_derived_hair import needed
        if not needed(state,asset_sha256):return prepared
    from .hair_colour_runtime import prepare_bank
    hair, hair_facts=prepare_bank(state,asset_sha256,effect_source,plan,evidence=hair_evidence,assets=hair_assets,
        byte_budget=byte_budget-retained_bytes(prepared)-source.nbytes-(0 if repaired is None else repaired.nbytes),
        source_path=hair_source_path,force_prompted=force_hair_prompted)
    for key,fact in hair_facts.items():facts.setdefault(key,{})['hair_colour']=fact
    return PreparedPeople(plan,geometry,tuple(effects)+hair,facts,owned_recovery,tuple(fields))


def retained_bytes(prepared,*,include_geometry=True):
    total=sum(field.resident_bytes() for field in (*prepared.face_fields,*prepared.body_fields))
    total+=sum(array.nbytes for record in prepared.effects for array in (record.delta,record.weights) if array is not None)
    total+=sum(record['weight'].nbytes for record in prepared.recovery.values())
    if include_geometry:total+=prepared.geometry.delta.nbytes+prepared.geometry.owner.nbytes
    return total
