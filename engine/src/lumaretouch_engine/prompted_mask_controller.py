"""Read-only prompt previews, redeemed only by the existing local-mask edit path."""
from copy import deepcopy
import re
from .source_patch_controller import PROOF_KEYS
from .prompted_mask_source import check_prompts, check_binding
from .prompted_mask_job import PromptedJob
from . import local_mask_state as S


class PromptedController:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.job = self.proof = self.preview_id = self.source = None
        self.source_stamp = None
        self.source_input = None
        self.runtime_stamp = None
        self.presented_candidate = None

    def cancel(self):
        if self.job is not None: self.job.cancel()
        self.job = self.proof = self.preview_id = self.source = None
        self.source_stamp = None
        self.source_input = None
        self.runtime_stamp = None
        self.presented_candidate = None

    def _capture(self, proof):
        capture = self.engine._source_patch_controller().capture._matching(proof, recipe=True)
        if not capture['eligible'] or capture['descriptor']['domain'] != 'source-input':
            raise ValueError('Show a current effective-source capture before requesting AI selection')
        return capture

    def tick(self):
        if self.job is None: return
        try:
            self._capture(self.proof)
            path = self.engine._docs[self.engine._doc_index]['path']
            if S.file_stamp(path) != self.source_stamp:
                raise ValueError('Prompted selection source changed')
            from .creative_derived_source import verify
            verify(self.source,self.engine)
            self.job.poll()
            if self.runtime_stamp is not None:
                from .prompted_mask_resolver import dependency_stamp
                if dependency_stamp()!=self.runtime_stamp:raise ValueError('Prompted runtime changed since preview start')
            if self.job.state=='ready':
                from .creative_derived_prompted import verify_result
                verify_result(self.job.result,self.source,self.source_input)
        except Exception as error:
            self.job.cancel()
            self.job.state, self.job.error = 'failed', str(error)[:2000]

    def handle(self, p):
        ident = p.get('preview_id')
        event = {'event': 'prompted_masks', 'protocol': 1, 'preview_id': ident,
                 'document_id': p.get('document_id'), 'success': False}
        try:
            if type(ident) is not str or not re.fullmatch('[0-9a-f]{32}', ident):
                raise ValueError('Invalid prompted preview identity')
            action = p.get('action')
            common = {'cmd', 'action', 'preview_id', *PROOF_KEYS}
            extras = {'open': set(), 'predict': {'prompts', 'device'}, 'poll': set(),
                      'presented': {'candidate'}, 'cancel': set()}
            if action not in extras or set(p) != common|extras[action]:
                raise ValueError('Invalid prompted preview command')
            proof = {k: p[k] for k in PROOF_KEYS}
            if action == 'cancel':
                if ident == self.preview_id and proof == self.proof: self.cancel()
                event.update(success=True, state='cancelled')
            elif action in ('open', 'predict'):
                self._capture(proof)
                if ident == self.preview_id:
                    raise ValueError('Use a fresh preview ID for each prompt change; never replay a start')
                from .creative_derived_source import binding
                from .creative_derived_prompted import capture
                source = binding(self.engine)
                source_input=capture(self.engine)
                prompts = check_prompts(p['prompts']) if action == 'predict' else None
                device = p.get('device', 'cpu')
                if device not in ('cpu', 'cuda'):
                    raise ValueError('Choose CPU or GPU explicitly')
                self.cancel()
                path = self.engine._docs[self.engine._doc_index]['path']
                self._capture(proof)
                from .creative_derived_source import verify
                verify(source,self.engine)
                runtime_stamp=None
                if prompts is not None:
                    from .prompted_mask_resolver import dependency_stamp
                    runtime_stamp=dependency_stamp()
                self.job = (PromptedJob(path,source,prompts,device) if source_input is None else
                    PromptedJob(None,source,prompts,device,source_input=source_input))
                self.source_input=source_input
                self.runtime_stamp=runtime_stamp
                self.proof, self.source, self.preview_id = proof, source, ident
                self.source_stamp = S.file_stamp(path)
                event.update(success=True, state='running')
            else:
                if ident != self.preview_id or proof != self.proof or self.job is None:
                    raise ValueError('Prompted preview expired')
                self.tick()
                if action == 'presented':
                    candidate = p['candidate']
                    if (self.job.state != 'ready' or not self.job.result.get('candidates')
                            or type(candidate) is not int or not 0 <= candidate < 3):
                        raise ValueError('Display a completed candidate before accepting it')
                    self.presented_candidate = candidate
                visible = {k: v for k, v in self.job.result.items() if not k.startswith('_')} if self.job.state == 'ready' else None
                event.update(success=self.job.state != 'failed', state=self.job.state,
                             error=self.job.error, result=visible, presented_candidate=self.presented_candidate)
        except Exception as error:
            event.update(state='failed', error=str(error)[:2000])
        self.emit(event)

    def accepted_object(self, mutation, proof):
        keys = {'action', 'preview_id', 'candidate', 'id', 'name', 'operation', 'opacity', 'feather'}
        if type(mutation) is not dict or set(mutation) != keys or mutation['action'] != 'accept_prompted':
            raise ValueError('Invalid prompted candidate acceptance')
        if (mutation['preview_id'] != self.preview_id or proof != self.proof
                or self.job is None or self.job.state != 'ready'):
            raise ValueError('Prompted preview expired; request and review a new preview')
        self.tick()
        if self.job.state!='ready':raise ValueError(self.job.error or 'Prompted source expired before acceptance')
        self._capture(proof)
        from .creative_derived_source import binding as effective_binding
        if effective_binding(self.engine) != self.source:
            raise ValueError('Prompted source changed before acceptance')
        candidate = mutation['candidate']
        if type(candidate) is not int or candidate != self.presented_candidate:
            raise ValueError('The accepted candidate has not been displayed')
        result = self.job.result
        from .creative_derived_prompted import verify_result
        verify_result(result,self.source,self.source_input)
        binding = check_binding({'prompts': result['prompts'], 'candidate': candidate,
                                 'model': result['model'], 'input_sha256': result['input_sha256'],
                                 'device': 'cuda' if result['device'] in ('CUDA', 'ROCm') else 'cpu'})
        from .prompted_mask_resolver import seed
        path = self.engine._docs[self.engine._doc_index]['path']
        seed(binding,self.source,path if self.source_input is None else None,result['_mask_fields'][candidate],
             'cuda' if result['device'] in ('CUDA','ROCm') else 'cpu',source_input=self.source_input)
        return {'id': mutation['id'], 'name': mutation['name'], 'operation': mutation['operation'],
                'opacity': mutation['opacity'], 'feather': mutation['feather'], 'enabled': True,
                'kind': 'prompted', 'selection': deepcopy(binding)}


def controller(engine, emit):
    owner = engine.__dict__.get('_prompted_mask_owner')
    if owner is None: owner = engine._prompted_mask_owner = PromptedController(engine, emit)
    return owner
