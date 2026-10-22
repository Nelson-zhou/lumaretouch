"""Isolated proposal review owner. Acceptance returns draft intent, never an edit.

The caller must still render/ack/commit through the existing sky preview proof.
In particular this owner cannot declare no-person, invent a horizon, apply an
effect, mutate history, or authorize export from its RGB8 locator.
"""
from copy import deepcopy
import secrets
from .job import SemanticJob
from . import resolver as R, state as S


class SemanticReview:
    def __init__(self, current_context, emit):
        self.current_context, self.emit = current_context, emit
        self.job = self.context = self.proposal = self.result = None
        self.shown = set()

    def cancel(self):
        if self.job is not None and self.job.state == 'running':
            self.job.cancel()
        self.job = self.context = self.proposal = self.result = None
        self.shown = set()

    close = cancel

    def start(self, path, source, device):
        self.cancel()
        self.context = deepcopy(self.current_context())
        self.proposal = secrets.token_hex(16)
        self.job = SemanticJob(path, source, device)
        return {'proposal_id': self.proposal, 'state': 'running', 'proposal_only': True}

    def matching(self, proposal):
        if proposal != self.proposal or self.context != self.current_context():
            raise ValueError('自动选区预览已过期；请基于当前照片重新生成')

    def tick(self):
        if self.job is None or self.result is not None:
            return
        if self.context != self.current_context():
            old = self.proposal
            self.cancel()
            self.emit({'event': 'sky_semantic_proposal', 'proposal_id': old, 'state': 'cancelled',
                       'error': '源照片或编辑版本已变化；未应用自动选区'})
            return
        state = self.job.poll()
        if state == 'running':
            return
        if state != 'ready':
            self.emit({'event': 'sky_semantic_proposal', 'proposal_id': self.proposal,
                       'state': state, 'error': self.job.error or '自动选区已取消'})
            self.job = None
            return
        try:
            result = self.job.result
            R.decode_fields(result)
            self.result = result
            self.emit({'event': 'sky_semantic_proposal', 'proposal_id': self.proposal, 'state': 'ready',
                       **{key: value for key, value in result.items() if not key.startswith('_')}})
        except Exception as error:
            self.emit({'event': 'sky_semantic_proposal', 'proposal_id': self.proposal,
                       'state': 'failed', 'error': str(error)[:2000]})
            self.job = None

    def acknowledge(self, proposal, region):
        self.matching(proposal)
        if self.result is None or region not in S.REGIONS:
            raise ValueError('自动选区候选尚未成功显示')
        self.shown.add(region)

    def accept(self, proposal, regions):
        self.matching(proposal)
        if not regions or self.result is None or not set(regions).issubset(self.shown):
            raise ValueError('请先查看自动选区候选，再选择接受的区域')
        for key in regions:
            if self.result['counts'].get(key, 0) <= 0:
                raise ValueError('未检测到该区域；请保留手工标记流程')
        descriptor = S.accept(self.result, self.result['source'], regions)
        R.remember(descriptor, self.result)
        return {'semantic': descriptor, 'draft_only': True, 'requires_sky_output_review': True,
                'person_declaration_unchanged': True, 'horizon_unchanged': True}
