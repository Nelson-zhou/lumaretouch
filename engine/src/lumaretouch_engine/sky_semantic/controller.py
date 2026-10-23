"""Source-session-bound proposal protocol. It never mutates retained edits."""
from copy import deepcopy
import json
import re
from .review import SemanticReview


class SemanticController:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.binding = None
        self.owner = SemanticReview(self.context, self.proposal_event, self.current_input)

    def context(self):
        from ..sky_replacement_preview import context
        return context(self.engine)

    def current_input(self):
        """Use the effective source owner, never relabel the physical original.

        The locator remains display-only. A returned creative source supplies
        its independently captured canonical inference packet instead of the
        original pathname or the current RGB8 display/analysis proxy.
        """
        from ..sky_replacement_preview import controller
        from ..creative_derived_source import record
        session = controller(self.engine, self.emit).matching(self.binding)
        source = deepcopy(session['binding'])
        if record(self.engine) is None:
            return session['path'], source, None
        from ..creative_derived_sky import semantic_input
        from .immutable_input import check
        return None, source, check(semantic_input(self.engine), source)

    def proposal_event(self, value):
        if self.binding is not None:
            self.emit({**value, **self.binding, 'protocol': 1})

    def handle(self, command):
        binding = {key: command.get(key) for key in ('document_id', 'session_id', 'run_id')}
        result = {'event': 'sky_semantic_result', 'protocol': 1, **binding,
                  'request_id': command.get('request_id'), 'success': False, 'draft_only': True}
        try:
            action = command.get('action')
            extra = {'start': {'device'}, 'cancel': set(), 'shown': {'proposal_id', 'region'},
                     'accept': {'proposal_id', 'regions'}}
            if (action not in extra or set(command) != {'cmd', 'action', 'request_id', *binding} | extra[action]
                    or command['cmd'] != 'sky_semantic' or type(command['request_id']) is not str
                    or not re.fullmatch('[A-Za-z0-9_-]{1,128}', command['request_id'])
                    or len(json.dumps(command, allow_nan=False).encode()) > 8192):
                raise ValueError('自动选区命令无效')
            if type(binding['run_id']) is not str or not re.fullmatch('[0-9a-f]{32}', binding['run_id']):
                raise ValueError('自动选区运行身份无效')
            if action == 'start' and command['request_id'] != binding['run_id']:
                raise ValueError('自动选区启动身份不一致')
            if action != 'start' and binding != self.binding:
                raise ValueError('自动选区源会话已变化')
            if action == 'cancel':
                self.close()
                result.update(success=True, state='cancelled')
            else:
                from ..sky_replacement_preview import controller
                session = controller(self.engine, self.emit).matching(command)
                if not session['shown']:
                    raise ValueError('请先显示并确认天空源图定位画面')
                if action == 'start':
                    reason = self.engine._guard_editable('sky semantic proposal')
                    if reason:
                        raise ValueError(reason)
                    # Even a failed new capture must not expose the previous
                    # proposal or shown acknowledgements under this new run.
                    self.owner.cancel()
                    self.binding = binding
                    path, source, packet = self.current_input()
                    result.update(self.owner.start(path, source, command['device'], immutable_input=packet), success=True)
                elif action == 'shown':
                    self.owner.acknowledge(command['proposal_id'], command['region'])
                    result.update(success=True, state='shown')
                else:
                    result.update(self.owner.accept(command['proposal_id'], command['regions']), success=True)
        except Exception as error:
            result['error'] = str(error)[:2000]
        self.emit(result)

    def tick(self):
        preview = getattr(self.engine, '_sky_replacement_preview_owner', None)
        if self.binding is not None:
            try:
                if preview is None:
                    raise ValueError('天空源会话已关闭')
                preview.matching(self.binding)
            except Exception:
                self.proposal_event({'event': 'sky_semantic_proposal', 'proposal_id': self.owner.proposal,
                                     'state': 'cancelled', 'error': '天空源会话已变化；未应用自动选区'})
                self.close()
                return
        self.owner.tick()

    def close(self):
        self.owner.close()
        self.binding = None


def controller(engine, emit):
    owner = getattr(engine, '_sky_semantic_owner', None)
    if owner is None:
        owner = engine._sky_semantic_owner = SemanticController(engine, emit)
    return owner
