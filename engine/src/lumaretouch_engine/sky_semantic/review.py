"""Isolated proposal review owner. Acceptance returns draft intent, never an edit.

The caller must still render/ack/commit through the existing sky preview proof.
In particular this owner cannot declare no-person, invent a horizon, apply an
effect, mutate history, or authorize export from its RGB8 locator.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
import secrets
from .job import SemanticJob
from . import manifest as M, resolver as R, state as S


class SemanticReview:
    def __init__(self, current_context, emit, current_input=None):
        self.current_context, self.emit, self.current_input = current_context, emit, current_input
        self.job = self.context = self.proposal = self.result = None
        self.path = self.source = self.device = self.immutable_input = self.input_proof = self.result_proof = self.result_content = None
        self.shown = set()

    def cancel(self):
        if self.job is not None and self.job.state == 'running':
            self.job.cancel()
        self.job = self.context = self.proposal = self.result = None
        self.path = self.source = self.device = self.immutable_input = self.input_proof = self.result_proof = self.result_content = None
        self.shown = set()

    close = cancel

    @staticmethod
    def proof(path, source, immutable_input):
        source = S.source(source)
        if immutable_input is not None:
            from . import immutable_input as I
            if path is not None:
                raise ValueError('不可变来源自动选区不能同时携带原照片路径')
            packet = I.check(immutable_input, source)
            return None, source, I.metadata(packet)
        if path is None or not isinstance(os.fspath(path), str) or not os.fspath(path):
            raise ValueError('原照片自动选区缺少明确的源路径')
        return os.fspath(path), source, None

    def start(self, path, source, device, *, immutable_input=None):
        self.cancel()
        try:
            self.context = deepcopy(self.current_context())
            self.input_proof = self.proof(path, source, immutable_input)
            self.path, self.source = self.input_proof[:2]
            self.device = device
            if immutable_input is not None:
                from .immutable_input import check
                self.immutable_input = check(immutable_input, self.source)
            self.proposal = secrets.token_hex(16)
            self.job = (SemanticJob(self.path, self.source, device) if self.immutable_input is None else
                        SemanticJob(None, self.source, device, immutable_input=self.immutable_input))
            self.matching(self.proposal)
        except BaseException:
            self.cancel()
            raise
        return {'proposal_id': self.proposal, 'state': 'running', 'proposal_only': True}

    def result_identity(self, result):
        if result['source'] != self.source or result['device'] != self.device or result['model'] != M.identity():
            raise ValueError('自动选区结果不属于当前审核的源图、设备或固定模型')
        if self.immutable_input is not None:
            from .immutable_input import validate_result
            validate_result(self.immutable_input, result)
        elif result.get('_immutable_input') is not None:
            raise ValueError('不可变来源自动选区不能重绑定到原照片')
        # Regions are only a placeholder for validating the complete identity;
        # acceptance still requires the user's explicitly reviewed thresholds.
        return S.accept(result, self.source, {'sky': .5})

    @staticmethod
    def content(result):
        # Protect the actual shown overlays/counts and encoded label/support
        # payload too, not just their declared identities. Emission receives a
        # separate deep copy, and later review cannot silently relabel it.
        data = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(data) > M.MAX_RESULT_BYTES:
            raise ValueError('自动选区结果超过传输预算')
        return sha256(data).hexdigest()

    def matching(self, proposal):
        if proposal is None or proposal != self.proposal or self.context != self.current_context():
            raise ValueError('自动选区预览已过期；请基于当前照片重新生成')
        if (self.proof(self.path, self.source, self.immutable_input) != self.input_proof
                or (self.current_input is not None and self.proof(*self.current_input()) != self.input_proof)):
            raise ValueError('自动选区实际源图或规范推理输入已变化；请重新生成')
        if self.result is not None:
            if self.content(self.result) != self.result_content or self.result_identity(self.result) != self.result_proof:
                raise ValueError('自动选区候选的来源或显示内容已变化；请重新生成')

    def tick(self):
        if self.job is None or self.result is not None:
            return
        try:
            # Polling must not repeatedly materialize a full canonical source
            # on every engine tick. The complete source/input check occurs
            # immediately before publishing ready and at shown/accept instead.
            if self.context != self.current_context():
                raise ValueError('自动选区源图或编辑版本已变化')
        except Exception:
            old = self.proposal
            self.cancel()
            self.emit({'event': 'sky_semantic_proposal', 'proposal_id': old, 'state': 'cancelled',
                       'error': '源照片、规范推理输入或编辑版本已变化；未应用自动选区'})
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
            result = deepcopy(self.job.result)
            identity = self.result_identity(result)
            R.validate_candidates(result, R.decode_fields(result))
            content = self.content(result)
            self.matching(self.proposal)
            self.result = result
            self.result_proof = identity
            self.result_content = content
            self.emit({'event': 'sky_semantic_proposal', 'proposal_id': self.proposal, 'state': 'ready',
                       **deepcopy({key: value for key, value in result.items() if not key.startswith('_')})})
        except Exception as error:
            self.emit({'event': 'sky_semantic_proposal', 'proposal_id': self.proposal,
                       'state': 'failed', 'error': str(error)[:2000]})
            self.job = None
            self.result = self.result_proof = self.result_content = None
            self.shown = set()

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
        descriptor = S.accept(self.result, self.source, regions)
        R.remember(descriptor, self.result, immutable_input=self.immutable_input)
        self.matching(proposal)
        return {'semantic': descriptor, 'draft_only': True, 'requires_sky_output_review': True,
                'person_declaration_unchanged': True, 'horizon_unchanged': True}
