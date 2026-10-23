"""Bounded immutable preflight records; no editor, row or image ownership."""
from collections import OrderedDict
from dataclasses import dataclass
import json
import uuid

MAX_PENDING=8
MAX_TERMINAL=32
MAX_BYTES=2*1024*1024
MAX_RESULT_BYTES=8*1024*1024
MAX_TERMINAL_BYTES=16*1024*1024
MAX_TARGETS=10000
TTL_NS=30*60*1_000_000_000


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
        now=self.clock();self._prune(now)
        # Validate the total metadata budget, not only each target independently.
        canonical({'source':[source_id,source_revision,source_path],'modules':modules,'params':params,
            'source_proof':source_proof,
            'targets':[[t.document_id,t.revision,t.index,t.path,t.blocked,t.before_json,t.prepared_json,t.transfer_json,t.optics_json,t.reference_json,t.people_json,t.source_proof_json,t.crop_json] for t in targets],'rejected':rejected})
        plan=FrozenPlan(uuid.uuid4().hex,workspace,source_id,source_revision,source_path,tuple(modules),canonical(params),policy,
            tuple(targets),canonical(rejected),now,now+TTL_NS,None if source_proof is None else canonical(source_proof))
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

    def claim(self,plan):
        # Consume before the first write: even failure to encode the final receipt
        # must never leave a successfully applied token available for reexecution.
        self.finish(plan,{'success':False,'outcome_unknown':True,'preflight_token':plan.token,
            'error':'batch started; terminal outcome has not been recorded'})

    def finish(self,plan,result):
        try:payload=canonical(result,MAX_RESULT_BYTES)
        except (ValueError,TypeError):
            payload=canonical({'success':False,'outcome_unknown':True,'preflight_token':plan.token,
                'error':'batch result could not be retained; inspect document state before a new batch'})
        self.terminal[plan.token]=(plan.workspace,payload)
        self.pending.pop(plan.token,None)
        while (len(self.terminal)>MAX_TERMINAL or
               sum(len(value[1].encode('utf-8')) for value in self.terminal.values())>MAX_TERMINAL_BYTES):
            self.terminal.popitem(last=False)
        return json.loads(payload)
