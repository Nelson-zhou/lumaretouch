"""Bounded immutable preflight records; no editor, row or image ownership."""
from collections import OrderedDict
from dataclasses import dataclass
import json
import uuid
from .body_scalar_transfer_review import select as body_family

MAX_PENDING=8
MAX_TERMINAL=32
MAX_BYTES=2*1024*1024
MAX_RESULT_BYTES=8*1024*1024
MAX_TERMINAL_BYTES=16*1024*1024
MAX_TARGETS=10000
TTL_NS=30*60*1_000_000_000


def collarbone_required(plan):
    """Frozen owner intent, never a caller-supplied review flag."""
    people = plan.params().get('_people_transfer')
    if type(people) is not dict: return False
    if people.get('mode') == 'persistent_association':
        return people.get('collarbone_visual_required') is True
    return 'lnx.collarbone.v1' in plan.modules


def collarbone_cohort(plan):
    return collarbone_required(plan) and plan.params()['_people_transfer'].get('mode') == 'persistent_association'


def face_style_records(plan):
    """Validate actual frozen intent and each eligible target, never an ACK flag."""
    from . import face_style_batch_review as review
    if not review.required(plan):return None
    options=plan.params()['_people_transfer']['options']
    value=review.recipe(options['face_style'])
    review.check_selection(value,options.get('selection'))
    if options.get('target_policy')!='explicit_face_map' or list(plan.modules)!=list(review.selection(value)):
        raise ValueError('Face-style review requires its exact explicit-face-map operation scope')
    if not 1<=len(plan.targets)<=review.MAX_TARGETS:
        raise ValueError('Face-style review requires one to sixteen complete target records')
    records=[];seen=set();digest=review.recipe_digest(value)
    for target in plan.targets:
        if target.blocked:continue
        if target.people_json is None:raise ValueError('Eligible face-style target lacks its frozen visual evidence')
        payload=json.loads(target.people_json)
        if (review.recipe(payload.get('face_style'))!=value
                or canonical(payload.get('parameters'))!=canonical(review.parameters(value))):
            raise ValueError('Face-style target differs from its frozen named recipe and typed leaves')
        record=review.checked(payload.get('face_style_visual'))
        proof=(json.loads(target.source_proof_json) if target.source_proof_json is not None
               else json.loads(target.before_json).get('source_proof'))
        if (record['document_id']!=target.document_id or record['revision']!=str(target.revision)
                or record['recipe_sha256']!=digest or record['source_proof']!=proof or target.document_id in seen):
            raise ValueError('Face-style visual does not belong to its frozen target and named recipe')
        seen.add(target.document_id);records.append(record)
    return records


def portrait_cohort_records(plan):
    """Bind full-portrait consent to the actual atomic source-first cohort.

    Selected modules can be empty for unlink or narrower for a later scalar
    patch. Only the frozen complete intent determines this review requirement.
    """
    from . import portrait_cohort_review as review
    value=plan.params().get('_people_transfer')
    if type(value) is not dict:return None
    if value.get('mode')!='persistent_association':
        if 'portrait_cohort_required' in value:
            raise ValueError('Portrait cohort marker requires a persistent association')
        return None
    intent=value.get('review')
    if type(intent) is not dict or type(value.get('portrait_cohort_required')) is not bool:
        raise ValueError('Persistent association requires its actual frozen portrait review marker')
    required=review.content_required(intent.get('intent'))
    if value['portrait_cohort_required'] is not required:
        raise ValueError('Portrait cohort marker differs from actual complete shared intent')
    if not required:
        if type(value.get('options')) is dict and 'face_style' in value['options']:
            raise ValueError('Named persistent recipe cannot omit complete portrait cohort intent')
        return None
    from .people_cross_owner_workflow import options
    from .people_transfer_inventory import check_proof
    from .people_cross_owner import check_descriptor
    from .people_state import digest as check_digest
    selected=options(value.get('options'),list(plan.modules))
    if (set(intent)!={'version','operation','association_id','generation','members','intent'}
            or intent['operation']!=selected['operation']
            or intent['association_id']!=selected['association_id']):
        raise ValueError('Portrait cohort review differs from its frozen association operation')
    capsule=check_descriptor({key:item for key,item in intent.items() if key!='operation'}
                             | {'local_document_id':plan.source_id})
    if 'face_style' in selected:
        from .face_style_batch_review import parameters
        leaves={(leaf['op'],leaf['path']):leaf['value'] for leaf in capsule['intent']}
        if any(canonical(leaves.get((leaf['operation_id'],leaf['parameter_path'])))!=canonical(leaf['value'])
               for leaf in parameters(selected['face_style'])):
            raise ValueError('Named cohort intent differs from its exact locally generated typed recipe')
    proofs=[selected['source']]+[item['target'] for item in selected['targets']]
    refs=[selected['source_ref']]+[item['target_refs'][0] for item in selected['targets']]
    if (plan.policy!='recheck' or plan.rejected() or not 2<=len(plan.targets)<=16
            or len(plan.targets)!=len(proofs) or plan.targets[0].document_id!=plan.source_id
            or plan.targets[0].revision!=plan.source_revision or plan.targets[0].path!=plan.source_path
            or any(target.blocked is not None for target in plan.targets)):
        raise ValueError('Portrait cohort requires source first and every two to sixteen atomic members')
    members={member['document_id']:member for member in capsule['members']}
    expected_digest=review.digest(selected,intent);records=[];seen=set()
    for target,expected,ref in zip(plan.targets,proofs,refs):
        proof=check_proof(json.loads(target.before_json))
        member=members.get(target.document_id)
        if (type(target.revision) is not int or proof!=expected or proof['document']['document_id']!=target.document_id
                or proof['document']['revision']!=target.revision or proof['document']['epoch']!=plan.workspace
                or target.document_id in seen or member!={'document_id':target.document_id,
                    'scope_id':proof['people_scope'],'original_sha256':proof['source_proof']['original_sha256'],'ref':ref}
                or ref['asset_sha256']!=proof['source_proof']['asset_sha256']
                or target.people_json is None):
            raise ValueError('Portrait cohort member differs from its exact frozen endpoint proof')
        payload=json.loads(target.people_json)
        if type(payload) is not dict:raise ValueError('Portrait cohort requires its frozen member payload')
        snapshots=payload.get('portrait_snapshots')
        if type(snapshots) is not dict or set(snapshots)!={'before','after'}:
            raise ValueError('Portrait cohort requires both private full-render snapshot proofs')
        for snapshot in snapshots.values():
            if type(snapshot) is not dict or set(snapshot)!={'render_sha256','context_sha256','graph_sha256'}:
                raise ValueError('Portrait cohort snapshot proof requires exact render, context and graph digests')
            for digest in snapshot.values():check_digest(digest)
        record=review.checked(payload.get('portrait_visual'))
        if (payload.get('ref')!=ref or record['document_id']!=target.document_id
                or record['revision']!=str(target.revision) or record['source_proof']!=proof['source_proof']
                or record['cohort_sha256']!=expected_digest
                or (target.source_proof_json is not None and json.loads(target.source_proof_json)!=proof['source_proof'])):
            raise ValueError('Portrait visual differs from its source, document, revision or complete cohort intent')
        seen.add(target.document_id);records.append(record)
    if seen!=set(members):raise ValueError('Portrait cohort cannot omit or invent an association member')
    return records


def canonical(value,limit=MAX_BYTES):
    text=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    if len(text.encode('utf-8'))>limit:raise ValueError('batch preflight exceeds metadata budget')
    return text

@dataclass(frozen=True)
class FrozenTarget:
    document_id:str
    revision:int
    index:int
    path:str
    blocked:str|None
    before_json:str
    prepared_json:str|None=None
    transfer_json:str|None=None
    optics_json:str|None=None
    reference_json:str|None=None
    people_json:str|None=None
    source_proof_json:str|None=None
    crop_json:str|None=None
    spill_json:str|None=None
    shadow_json:str|None=None
    torso_json:str|None=None
    waist_json:str|None=None
    head_json:str|None=None

@dataclass(frozen=True)
class FrozenPlan:
    token:str
    workspace:str
    source_id:str
    source_revision:int
    source_path:str
    modules:tuple[str,...]
    params_json:str
    policy:str
    targets:tuple[FrozenTarget,...]
    rejected_json:str
    created_ns:int
    expires_ns:int
    source_proof_json:str|None=None

    def params(self):return json.loads(self.params_json)
    def rejected(self):return json.loads(self.rejected_json)

class PreflightStore:
    def __init__(self,clock):
        self.clock=clock;self.pending=OrderedDict();self.terminal=OrderedDict()

    def create(self,workspace,source_id,source_revision,source_path,modules,params,policy,targets,rejected,*,source_proof=None):
        if not targets or len(targets)>MAX_TARGETS:raise ValueError('invalid batch preflight target count')
        from .creative_derived_source import check_row_proof
        from .spill_removal_scope import OP as SPILL_OP
        spill=SPILL_OP in modules
        if spill:
            from .spill_transfer_review import MAX_TARGETS as SPILL_MAX_TARGETS
            if len(targets)>SPILL_MAX_TARGETS:raise ValueError('Spill visual review supports at most eight targets; no target was omitted')
        from .original_shadow_scope import OP as SHADOW_OP
        shadow=SHADOW_OP in modules
        if shadow:
            from .original_shadow_transfer_review import MAX_TARGETS as SHADOW_MAX_TARGETS
            if len(targets)>SHADOW_MAX_TARGETS:raise ValueError('Original-shadow visual review supports at most eight targets; no target was omitted')
        family=body_family(modules)
        if family is not None and len(targets)>family.review.MAX_TARGETS:
            raise ValueError(f'{family.name} visual review supports at most eight targets; no target was omitted')
        if family is not None and source_proof is None:
            raise ValueError('Body-scalar preflight requires its frozen source proof')
        if source_proof is not None:
            source_proof=check_row_proof(source_proof)
        for target in targets:
            if target.source_proof_json is not None:
                if type(target.source_proof_json) is not str or len(target.source_proof_json)>4096:
                    raise ValueError('Invalid bounded batch target source proof')
                check_row_proof(json.loads(target.source_proof_json))
            if target.crop_json is not None:
                from .crop_transfer_review import check_record
                if type(target.crop_json) is not str or len(target.crop_json)>16384:
                    raise ValueError('Invalid compact crop review proof')
                check_record(json.loads(target.crop_json))
            if target.spill_json is not None:
                from .spill_transfer_review import checked
                if not spill or type(target.spill_json) is not str or len(target.spill_json)>16384:
                    raise ValueError('Invalid compact spill review proof')
                record=checked(json.loads(target.spill_json))
                modules_for_target=params if target.prepared_json is None else json.loads(target.prepared_json)
                if (record['document_id']!=target.document_id or record['revision']!=str(target.revision)
                        or target.source_proof_json is None or record['source_proof']!=json.loads(target.source_proof_json)
                        or record['parameters']!=modules_for_target.get(SPILL_OP)):
                    raise ValueError('Spill review does not belong to its frozen target')
            elif spill and not target.blocked:
                raise ValueError('Every eligible spill target requires full before/after review evidence')
            if target.shadow_json is not None:
                from .original_shadow_transfer_review import checked
                if not shadow or type(target.shadow_json) is not str or len(target.shadow_json)>16384:
                    raise ValueError('Invalid compact shadow review proof')
                record=checked(json.loads(target.shadow_json))
                modules_for_target=params if target.prepared_json is None else json.loads(target.prepared_json)
                if (record['document_id']!=target.document_id or record['revision']!=str(target.revision)
                        or target.source_proof_json is None or record['source_proof']!=json.loads(target.source_proof_json)
                        or record['parameters']!=modules_for_target.get(SHADOW_OP)):
                    raise ValueError('Original-shadow review does not belong to its frozen target')
            elif shadow and not target.blocked:
                raise ValueError('Every eligible shadow target requires full before/after review evidence')
            for frozen_key in ('torso_json','waist_json','head_json'):
                value=getattr(target,frozen_key)
                if value is None:continue
                if family is None or frozen_key!=family.frozen_key or type(value) is not str or len(value)>16384:
                    raise ValueError('Invalid or foreign compact body-scalar review proof')
                record=family.review.checked(json.loads(value))
                modules_for_target=params if target.prepared_json is None else json.loads(target.prepared_json)
                if (record['document_id']!=target.document_id or record['revision']!=str(target.revision)
                        or target.source_proof_json is None or record['source_proof']!=json.loads(target.source_proof_json)
                        or record['parameters']!=modules_for_target.get(family.operation_id)):
                    raise ValueError('Body-scalar review does not belong to its frozen target')
            if family is not None and not target.blocked and getattr(target,family.frozen_key) is None:
                raise ValueError('Every eligible body-scalar target requires full before/after review evidence')
        now=self.clock();self._prune(now)
        # Validate the total metadata budget, not only each target independently.
        canonical({'source':[source_id,source_revision,source_path],'modules':modules,'params':params,
            'source_proof':source_proof,
            'targets':[[t.document_id,t.revision,t.index,t.path,t.blocked,t.before_json,t.prepared_json,t.transfer_json,t.optics_json,t.reference_json,t.people_json,t.source_proof_json,t.crop_json,t.spill_json,t.shadow_json,t.torso_json,t.waist_json,t.head_json] for t in targets],'rejected':rejected})
        plan=FrozenPlan(uuid.uuid4().hex,workspace,source_id,source_revision,source_path,tuple(modules),canonical(params),policy,
            tuple(targets),canonical(rejected),now,now+TTL_NS,None if source_proof is None else canonical(source_proof))
        face_style_records(plan)
        from .eye_bag_batch_review import records as eye_bag_records
        eye_bag_records(plan)
        from .face_decoration_batch_review import records as decoration_records
        decoration_records(plan)
        portrait_cohort_records(plan)
        from .eye_bag_cohort_review import records as eye_cohort_records
        eye_cohort_records(plan)
        self.pending[plan.token]=plan
        while len(self.pending)>MAX_PENDING:self.pending.popitem(last=False)
        return plan

    def _prune(self,now):
        for token,plan in list(self.pending.items()):
            if now>=plan.expires_ns:del self.pending[token]

    def get(self,token,workspace):
        self._prune(self.clock())
        if not isinstance(token,str) or len(token)!=32:raise ValueError('invalid batch preflight token')
        plan=self.pending.get(token)
        if plan is None:raise ValueError('batch preflight missing, expired or already consumed; preflight again')
        if plan.workspace!=workspace:raise ValueError('batch preflight belongs to another workspace')
        return plan

    def completed(self,token,workspace):
        if not isinstance(token,str) or len(token)!=32:raise ValueError('invalid batch preflight token')
        record=self.terminal.get(token)
        if record is None:return None
        generation,payload=record
        if generation!=workspace:raise ValueError('batch result belongs to another workspace')
        return json.loads(payload)

    def claim(self,plan,*,spill_review_ack=None,shadow_review_ack=None,torso_review_ack=None,waist_review_ack=None,head_review_ack=None,collarbone_review_ack=None,face_style_review_ack=None,portrait_cohort_ack=None,eye_bag_review_ack=None,eye_bag_cohort_ack=None,face_decoration_review_ack=None,face_decoration_cohort_ack=None,request_id=None):
        # Consume before the first write: even failure to encode the final receipt
        # must never leave a successfully applied token available for reexecution.
        if request_id is not None and (type(request_id) is not str or not 1<=len(request_id)<=128):
            raise ValueError('Invalid batch claim request identity')
        family=body_family(plan.modules)
        scalar_acks={'torso_review_ack':torso_review_ack,'waist_review_ack':waist_review_ack,'head_review_ack':head_review_ack}
        if any(value is not None and (family is None or key!=family.ack_key) for key,value in scalar_acks.items()):
            raise ValueError('Body-scalar claim cannot retain another family acknowledgment')
        if family is not None:
            records=[json.loads(getattr(target,family.frozen_key)) for target in plan.targets if not target.blocked]
            family.review.acknowledgments(scalar_acks[family.ack_key],records)
        if collarbone_required(plan):
            from .collarbone_transfer_review import acknowledgments
            records=[json.loads(target.people_json)['collarbone_visual'] for target in plan.targets if not target.blocked]
            acknowledgments(collarbone_review_ack,records)
        elif collarbone_review_ack is not None:
            raise ValueError('Collarbone claim requires its frozen people-transfer scope')
        portrait_records=portrait_cohort_records(plan)
        if portrait_records is not None:
            from .portrait_cohort_review import acknowledgments
            if any(value is not None for value in (spill_review_ack,shadow_review_ack,torso_review_ack,waist_review_ack,head_review_ack,face_style_review_ack,eye_bag_review_ack)):
                raise ValueError('Portrait cohort claim cannot retain another family acknowledgment')
            acknowledgments(portrait_cohort_ack,portrait_records)
        elif portrait_cohort_ack is not None:
            raise ValueError('Portrait cohort claim requires its actual complete persistent intent')
        face_records=face_style_records(plan)
        if face_records is not None:
            from .face_style_batch_review import acknowledgments
            if any(value is not None for value in (spill_review_ack,shadow_review_ack,torso_review_ack,waist_review_ack,head_review_ack,collarbone_review_ack,portrait_cohort_ack,eye_bag_review_ack)):
                raise ValueError('Face-style claim cannot retain another family acknowledgment')
            acknowledgments(face_style_review_ack,face_records)
        elif face_style_review_ack is not None:
            raise ValueError('Face-style claim requires its actual frozen named people-transfer scope')
        from .eye_bag_batch_review import records as eye_bag_records, acknowledgments as eye_acknowledgments
        eye_records=eye_bag_records(plan)
        if eye_records is not None:
            if any(value is not None for value in (spill_review_ack,shadow_review_ack,torso_review_ack,waist_review_ack,head_review_ack,face_style_review_ack,portrait_cohort_ack)):
                raise ValueError('Eye-bag claim cannot retain unrelated acknowledgment families')
            eye_acknowledgments(eye_bag_review_ack,eye_records)
        elif eye_bag_review_ack is not None:
            raise ValueError('Eye-bag claim requires actual frozen ordinary explicit intent')
        from .eye_bag_cohort_review import records as eye_cohort_records, acknowledgments as cohort_acknowledgments
        cohort_records=eye_cohort_records(plan)
        if cohort_records is not None:
            if any(value is not None for value in (spill_review_ack,shadow_review_ack,torso_review_ack,waist_review_ack,head_review_ack,face_style_review_ack,eye_bag_review_ack)):
                raise ValueError('Eye-bag cohort claim cannot retain unrelated acknowledgment families')
            cohort_acknowledgments(eye_bag_cohort_ack,cohort_records)
        elif eye_bag_cohort_ack is not None:
            raise ValueError('Eye-bag cohort claim requires actual frozen complete association review')
        from .face_decoration_cohort_review import records as decoration_cohort_records,acknowledgments as decoration_cohort_acks
        decoration_members=decoration_cohort_records(plan)
        if decoration_members is not None:decoration_cohort_acks(face_decoration_cohort_ack,decoration_members)
        elif face_decoration_cohort_ack is not None:raise ValueError('Decoration cohort claim requires actual complete review')
        from .face_decoration_batch_review import records as decoration_records,acknowledgments as decoration_acknowledgments
        decorations=decoration_records(plan)
        if decorations is not None:decoration_acknowledgments(face_decoration_review_ack,decorations)
        elif face_decoration_review_ack is not None:raise ValueError('Decoration claim requires actual image evidence')
        self.finish(plan,{'success':False,'outcome_unknown':True,'preflight_token':plan.token,'request_id':request_id,
            **({'module_scope':list(plan.modules)} if face_decoration_cohort_ack is not None or face_decoration_review_ack is not None or eye_bag_cohort_ack is not None or eye_bag_review_ack is not None or face_style_review_ack is not None or portrait_cohort_ack is not None or collarbone_review_ack is not None or any(value is not None for value in scalar_acks.values()) else {}),
            **({'face_decoration_cohort_ack':face_decoration_cohort_ack,'face_decoration_cohort':True} if face_decoration_cohort_ack is not None else {}),
            **({'eye_bag_cohort_ack':eye_bag_cohort_ack,'eye_bag_cohort':True} if eye_bag_cohort_ack is not None else {}),
            **({'portrait_cohort_ack':portrait_cohort_ack,'portrait_cohort':True} if portrait_cohort_ack is not None else {}),
            **({'face_decoration_review_ack':face_decoration_review_ack} if face_decoration_review_ack is not None else {}),
            **({'eye_bag_review_ack':eye_bag_review_ack} if eye_bag_review_ack is not None else {}),
            **({'face_style_review_ack':face_style_review_ack} if face_style_review_ack is not None else {}),
            **({'collarbone_review_ack':collarbone_review_ack} if collarbone_review_ack is not None else {}),
            **({'collarbone_cohort':True} if collarbone_cohort(plan) else {}),
            'error':'batch started; terminal outcome has not been recorded',
            **({'spill_review_ack':spill_review_ack} if spill_review_ack is not None else {}),
            **({'shadow_review_ack':shadow_review_ack} if shadow_review_ack is not None else {}),
            **({'torso_review_ack':torso_review_ack} if torso_review_ack is not None else {}),
            **({'waist_review_ack':waist_review_ack} if waist_review_ack is not None else {}),
            **({'head_review_ack':head_review_ack} if head_review_ack is not None else {})})

    def finish(self,plan,result):
        # Keep the original bounded commit identity in the private terminal
        # store. Replay transport correlation is still owned by emit_result.
        result=dict(result)
        previous=self.terminal.get(plan.token)
        retained=(json.loads(previous[1]) if previous is not None and previous[0]==plan.workspace else {})
        if 'request_id' not in result:
            if retained:result['request_id']=retained.get('request_id')
        request_id=result.get('request_id')
        if request_id is not None and (type(request_id) is not str or not 1<=len(request_id)<=128):
            raise ValueError('Invalid retained batch request identity')
        portrait_records=portrait_cohort_records(plan);portrait_ack=None
        if portrait_records is not None:
            from .portrait_cohort_review import acknowledgments
            if any(key in result for key in ('spill_review_ack','shadow_review_ack','torso_review_ack','waist_review_ack','head_review_ack','face_style_review_ack','eye_bag_review_ack')):
                raise ValueError('Portrait cohort result cannot contain another family acknowledgment')
            portrait_ack=acknowledgments(result.get('portrait_cohort_ack',retained.get('portrait_cohort_ack')),portrait_records)
            if ('portrait_cohort_ack' in retained and canonical(portrait_ack)!=canonical(retained['portrait_cohort_ack'])):
                raise ValueError('Portrait cohort result cannot change the claimed acknowledgment')
            if ('module_scope' in result and result['module_scope']!=list(plan.modules)
                    or 'portrait_cohort' in result and result['portrait_cohort'] is not True):
                raise ValueError('Portrait cohort result cannot change its frozen scope or review kind')
            result.update(portrait_cohort_ack=portrait_ack,portrait_cohort=True,module_scope=list(plan.modules))
            if collarbone_required(plan):
                from .collarbone_transfer_review import acknowledgments as collarbone_acknowledgments
                records=[json.loads(target.people_json)['collarbone_visual'] for target in plan.targets]
                collarbone_ack=collarbone_acknowledgments(result.get('collarbone_review_ack',retained.get('collarbone_review_ack')),records)
                if ('collarbone_review_ack' in retained and canonical(collarbone_ack)!=canonical(retained['collarbone_review_ack'])):
                    raise ValueError('Portrait cohort result cannot change its claimed collarbone acknowledgment')
                if 'collarbone_cohort' in result and result['collarbone_cohort'] is not True:
                    raise ValueError('Portrait cohort result cannot change its collarbone review kind')
                result.update(collarbone_review_ack=collarbone_ack,collarbone_cohort=True)
            elif 'collarbone_review_ack' in result or 'collarbone_cohort' in result:
                raise ValueError('Portrait cohort result cannot invent collarbone review')
        elif 'portrait_cohort_ack' in result or 'portrait_cohort' in result:
            raise ValueError('Portrait cohort receipt cannot accompany another frozen scope')
        face_records=face_style_records(plan);face_ack=None
        if face_records is not None:
            from .face_style_batch_review import acknowledgments
            if any(key in result for key in ('spill_review_ack','shadow_review_ack','torso_review_ack','waist_review_ack','head_review_ack','collarbone_review_ack','portrait_cohort_ack','eye_bag_review_ack')):
                raise ValueError('Face-style result cannot contain another family acknowledgment')
            face_ack=acknowledgments(result.get('face_style_review_ack',retained.get('face_style_review_ack')),face_records)
            if ('face_style_review_ack' in retained and canonical(face_ack)!=canonical(retained['face_style_review_ack'])):
                raise ValueError('Face-style result cannot change the claimed visual acknowledgment')
            if 'module_scope' in result and result['module_scope']!=list(plan.modules):
                raise ValueError('Face-style result cannot change its frozen operation scope')
            result.update(face_style_review_ack=face_ack,module_scope=list(plan.modules))
        elif 'face_style_review_ack' in result:
            raise ValueError('Face-style receipt cannot accompany another frozen scope')
        from .eye_bag_batch_review import records as eye_bag_records, acknowledgments as eye_acknowledgments
        eye_records=eye_bag_records(plan);eye_ack=None
        if eye_records is not None:
            if any(key in result for key in ('spill_review_ack','shadow_review_ack','torso_review_ack','waist_review_ack','head_review_ack','face_style_review_ack','portrait_cohort_ack')):
                raise ValueError('Eye-bag result cannot contain unrelated acknowledgment families')
            eye_ack=eye_acknowledgments(result.get('eye_bag_review_ack',retained.get('eye_bag_review_ack')),eye_records)
            if 'eye_bag_review_ack' in retained and canonical(eye_ack)!=canonical(retained['eye_bag_review_ack']):
                raise ValueError('Eye-bag result cannot change the exact claimed visual acknowledgment')
            if 'module_scope' in result and result['module_scope']!=list(plan.modules):
                raise ValueError('Eye-bag result cannot change the frozen mixed scope')
            result.update(eye_bag_review_ack=eye_ack,module_scope=list(plan.modules))
            if collarbone_required(plan):
                from .collarbone_transfer_review import acknowledgments as collarbone_acknowledgments
                records=[json.loads(target.people_json)['collarbone_visual'] for target in plan.targets if not target.blocked]
                collarbone_ack=collarbone_acknowledgments(result.get('collarbone_review_ack',retained.get('collarbone_review_ack')),records)
                if 'collarbone_review_ack' in retained and canonical(collarbone_ack)!=canonical(retained['collarbone_review_ack']):
                    raise ValueError('Mixed eye-bag result cannot change its collarbone acknowledgment')
                result['collarbone_review_ack']=collarbone_ack
            elif 'collarbone_review_ack' in result:
                raise ValueError('Eye-bag result cannot invent another review family')
        elif 'eye_bag_review_ack' in result:
            raise ValueError('Eye-bag receipt cannot accompany another frozen scope')
        from .eye_bag_cohort_review import records as eye_cohort_records, acknowledgments as cohort_acknowledgments
        cohort_records=eye_cohort_records(plan);cohort_ack=None
        if cohort_records is not None:
            if any(key in result for key in ('spill_review_ack','shadow_review_ack','torso_review_ack','waist_review_ack','head_review_ack','face_style_review_ack','eye_bag_review_ack')):
                raise ValueError('Eye-bag cohort result cannot contain unrelated acknowledgment families')
            cohort_ack=cohort_acknowledgments(result.get('eye_bag_cohort_ack',retained.get('eye_bag_cohort_ack')),cohort_records)
            if 'eye_bag_cohort_ack' in retained and canonical(cohort_ack)!=canonical(retained['eye_bag_cohort_ack']):
                raise ValueError('Eye-bag cohort result cannot change claimed images, order or replacement choices')
            if ('module_scope' in result and result['module_scope']!=list(plan.modules)
                    or 'eye_bag_cohort' in result and result['eye_bag_cohort'] is not True):
                raise ValueError('Eye-bag cohort result cannot change frozen scope or review kind')
            result.update(eye_bag_cohort_ack=cohort_ack,eye_bag_cohort=True,module_scope=list(plan.modules))
            if collarbone_required(plan):
                from .collarbone_transfer_review import acknowledgments as clavicle_acknowledgments
                clavicle_ack=clavicle_acknowledgments(result.get('collarbone_review_ack',retained.get('collarbone_review_ack')),
                    [json.loads(target.people_json)['collarbone_visual'] for target in plan.targets])
                if 'collarbone_review_ack' in retained and canonical(clavicle_ack)!=canonical(retained['collarbone_review_ack']):
                    raise ValueError('Eye-bag cohort cannot change its independently mandatory collarbone acknowledgment')
                if 'collarbone_cohort' in result and result['collarbone_cohort'] is not True:
                    raise ValueError('Eye-bag cohort cannot change collarbone proof kind')
                result.update(collarbone_review_ack=clavicle_ack,collarbone_cohort=True)
            elif 'collarbone_review_ack' in result or 'collarbone_cohort' in result:
                raise ValueError('Eye-bag cohort result cannot invent collarbone review')
        elif 'eye_bag_cohort_ack' in result or 'eye_bag_cohort' in result:
            raise ValueError('Eye-bag cohort receipt cannot accompany another frozen scope')
        from .face_decoration_cohort_review import reconcile as reconcile_decoration_cohort
        decoration_cohort_ack=reconcile_decoration_cohort(plan,result,retained)
        from .face_decoration_batch_review import reconcile as decoration_reconcile
        decoration_ack=decoration_reconcile(plan,result,retained)
        try:payload=canonical(result,MAX_RESULT_BYTES)
        except (ValueError,TypeError):
            # A compact spill acknowledgment is also the terminal retry fence.
            # Recover it from the frozen plan, not an oversized result payload.
            from .spill_removal_scope import OP as SPILL_OP
            ack={}
            if SPILL_OP in plan.modules:
                records=[json.loads(t.spill_json) for t in plan.targets if not t.blocked and t.spill_json is not None]
                ack={'spill_review_ack':[{'document_id':r['document_id'],'revision':r['revision'],
                    'before_sha256':r['before']['sha256'],'after_sha256':r['after']['sha256']} for r in records]}
            from .original_shadow_scope import OP as SHADOW_OP
            if SHADOW_OP in plan.modules:
                records=[json.loads(t.shadow_json) for t in plan.targets if not t.blocked and t.shadow_json is not None]
                ack={'shadow_review_ack':[{'document_id':r['document_id'],'revision':r['revision'],
                    'before_sha256':r['before']['sha256'],'after_sha256':r['after']['sha256']} for r in records]}
            family=body_family(plan.modules)
            if family is not None:
                records=[json.loads(getattr(t,family.frozen_key)) for t in plan.targets
                         if not t.blocked and getattr(t,family.frozen_key) is not None]
                ack[family.ack_key]=[{'document_id':r['document_id'],'revision':r['revision'],
                    'before_sha256':r['before']['sha256'],'after_sha256':r['after']['sha256']} for r in records]
                ack['module_scope']=list(plan.modules)
            if collarbone_required(plan):
                records=[json.loads(t.people_json)['collarbone_visual'] for t in plan.targets if not t.blocked and t.people_json is not None]
                ack['collarbone_review_ack']=[{'document_id':r['document_id'],'revision':r['revision'],
                    'before_sha256':r['before']['sha256'],'after_sha256':r['after']['sha256'],
                    'coverage_sha256':r['coverage_sha256']} for r in records]
                ack['module_scope']=list(plan.modules)
                if collarbone_cohort(plan):ack['collarbone_cohort']=True
            if decoration_cohort_ack is not None:ack.update(face_decoration_cohort_ack=decoration_cohort_ack,face_decoration_cohort=True,module_scope=list(plan.modules))
            if decoration_ack is not None:ack.update(face_decoration_review_ack=decoration_ack,module_scope=list(plan.modules),face_decoration_visual_required=True)
            if eye_ack is not None:
                ack.update(eye_bag_review_ack=eye_ack,module_scope=list(plan.modules))
            if face_ack is not None:
                ack['face_style_review_ack']=face_ack
                ack['module_scope']=list(plan.modules)
            if cohort_ack is not None:
                ack.update(eye_bag_cohort_ack=cohort_ack,eye_bag_cohort=True,module_scope=list(plan.modules))
            if portrait_ack is not None:
                ack.update(portrait_cohort_ack=portrait_ack,portrait_cohort=True,module_scope=list(plan.modules))
            payload=canonical({'success':False,'outcome_unknown':True,'preflight_token':plan.token,'request_id':request_id,
                'error':'batch result could not be retained; inspect document state before a new batch',**ack})
        self.terminal[plan.token]=(plan.workspace,payload)
        self.pending.pop(plan.token,None)
        from .collarbone_visual_store import prune
        prune(self)
        from .face_style_batch_store import prune as prune_face_style
        prune_face_style(self)
        from .eye_bag_batch_store import prune as prune_eye_bag
        prune_eye_bag(self)
        from .face_decoration_batch_store import prune as prune_decoration
        prune_decoration(self)
        from .portrait_cohort_store import prune as prune_portrait_cohort
        prune_portrait_cohort(self)
        from .eye_bag_cohort_store import prune as prune_eye_cohort
        prune_eye_cohort(self)
        from .face_decoration_cohort_store import prune as prune_decoration_cohort
        prune_decoration_cohort(self)
        while (len(self.terminal)>MAX_TERMINAL or
               sum(len(value[1].encode('utf-8')) for value in self.terminal.values())>MAX_TERMINAL_BYTES):
            self.terminal.popitem(last=False)
        return json.loads(payload)
