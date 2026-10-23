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
    if type(analysis) is not dict or set(analysis) != {'face_ref', 'evidence', 'landmarks', 'excluded', 'skin'}:
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
    return lm


def prepare(state, asset_sha256, source, analyses, *, byte_budget, max_faces=32, recovery_assets=None, repaired=None):
    state = S.check(state)
    if type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3 or source.shape[2] != 3 or not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('People preparation needs frozen working-sRGB float32 RGB')
    effect_source = source if repaired is None else repaired
    if type(effect_source) is not np.ndarray or effect_source.dtype != np.float32 or effect_source.shape != source.shape or not np.isfinite(effect_source).all() or np.any((effect_source<0)|(effect_source>1)):
        raise ValueError('Repaired effect source must share the original frozen source frame')
    pending = [x for x in state['unresolved_legacy'] if x['asset_sha256']==asset_sha256 and x['status']=='unresolved']
    if pending:
        raise PeoplePreparationRefused([{'face_instance_id':'legacy','reason':'Review retained ambiguous legacy intent: '+x['legacy_key']} for x in pending])
    if not any(face['asset_sha256']==asset_sha256 for face in state['faces'].values()) and any(row['scope']=='all_people' and row['target_id']==asset_sha256 and row['value']!=A.defaults().get(row['operation_id'],{}).get(row['parameter_path']) for row in state['overrides']):
        raise ValueError('Requested photograph-wide portrait parameters have no retained face; add or analyse a face before rendering')
    h,w = source.shape[:2]
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
            if not entry['requires_analysis']: continue
            face = state['faces'][key]; analysis = analyses[key]
            for asset in face['local_assets'].values():
                stage = asset['kind']
                if stage not in E.STAGES:
                    raise ValueError('Source-owned local support requires an explicit consumer: ' + stage)
                recovery = (recovery_assets or {}).get((key,stage))
                if recovery is None or recovery.get('recipe_sha256') != asset['content_sha256']:
                    raise ValueError('Retained recovery asset is missing; refusing to ignore it')
                E.verify_recovery(entry['face_ref'], stage, recovery, (h,w))
                owned = {**recovery, 'weight':recovery['weight'].copy()}
                owned['weight'].setflags(write=False); owned_recovery[(key,stage)] = owned
            lm = verify_analysis(face, analysis, (h,w))
            field = A.build_geometry(key, lm, values, source, analysis['excluded'], backend=face['evidence']['backend'])
            local = E.prepare(entry['face_ref'], lm, values, effect_source, excluded=analysis['excluded'], skin=analysis['skin'],
                              backend=face['evidence']['backend'], semantic_sha=face['evidence']['semantic_model_sha256'])
            # Preserve mouth's source-cavity teeth veto independently per face.
            mouth = field.fields[-1]
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
            facts[key].update({name:part.facts for name,part in zip(('brow_shape','nose_shape','eye_shape','mouth_shape'),field.fields) if part is not None})
        except (ValueError, RuntimeError, OSError) as error:
            failures.append({'face_instance_id':key,'reason':str(error)})
    if failures: raise PeoplePreparationRefused(failures)
    geometry = combine(fields, (h,w), byte_budget=byte_budget)
    return PreparedPeople(plan, geometry, tuple(effects), facts, owned_recovery,tuple(fields))
