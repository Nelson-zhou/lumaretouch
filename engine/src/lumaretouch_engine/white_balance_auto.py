"""Thin current-input identity/preparation adapter for the canonical WB owner."""
from copy import deepcopy
from hashlib import sha256
import json
from .color_action_sampling import Projection
from . import white_balance_auto_native as native
from .white_balance_recipe import check_options, compile_gains

INPUT_KEYS = ('input_id', 'recipe_document_id', 'recipe_revision')


def context(engine):
    """No file reads, rendering or pixel sampling; opaque runtime identity."""
    e = engine
    if e._vram is None or not 0 <= e._doc_index < len(e._docs):
        raise ValueError('No current auto WB input')
    row = e._docs[e._doc_index]
    versions = e._document_versions()
    version = versions.version(row)
    pipeline = e._vram
    spec = Projection.from_pipeline(pipeline)
    source = pipeline.src_f32
    if source is None:
        raise ValueError('Auto WB source is unavailable')
    payload = {'version': 1, 'domain': 'pre-wb-linear-working-srgb',
               'workspace': versions.workspace, 'document_id': str(e._load_id),
               'recipe_document_id': version.document_id, 'recipe_revision': str(version.revision),
               'source_asset_id': row.get('source_asset_id'), 'source_instance': id(source),
               'pipeline_instance': id(pipeline), 'source_shape': list(source.shape),
               'source_dtype': str(source.dtype), 'source_device': str(source.device),
               'projection': spec.descriptor(), 'strength': e._strength, 'channel': e._channel,
               'params': e._params, 'repair_version': pipeline.repair_version}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return {'input_id': sha256(raw).hexdigest(), 'recipe_document_id': version.document_id,
            'recipe_revision': str(version.revision)}, spec


def report(engine):
    try:
        return context(engine)[0]
    except (ValueError, TypeError, AttributeError, RuntimeError):
        return None


class AutomaticWhiteBalance:
    def __init__(self, engine):
        self.engine = engine
        self.transaction = {'phase': 'no_write'}
        self.baseline = None

    def prepare(self, request):
        e = self.engine
        self.baseline = None
        from .final_canvas_flip_state import require_processing_capture
        require_processing_capture(e)
        if not native.available():
            raise ValueError('自动白平衡 Rust 核心未安装或版本不匹配；不会退回吸管或人工算法')
        inspection = e._inspection_controller()
        if any(value is not None for value in (inspection.tx, inspection.result, inspection.job)):
            raise ValueError('请结束全分辨率检查后再使用自动白平衡')
        before, spec = context(e)
        if any(request.get(key) != before[key] for key in INPUT_KEYS):
            raise ValueError('自动白平衡输入或配方版本已变化；未提交，请刷新当前照片')
        pipeline = e._vram
        strength, channel = e._retouch_render_args()
        from .white_balance_auto_sampling import sample
        rows = sample(pipeline, spec, strength, channel, deepcopy(e._params))
        exposure = e.doc_state()['exposure']
        options = check_options(exposure['options'])
        # Keep algorithm/reference/manual controls; exclude EV and prior correction.
        manual = compile_gains({**options, 'picked_gains': [1.0, 1.0, 1.0]},
            6500.0 if exposure['reference_k'] is None else exposure['reference_k'],
            exposure['temperature_shift'], exposure['tint_shift'])
        result = native.calculate(rows, manual)
        if context(e) != (before, spec) or e._vram is not pipeline:
            raise ValueError('自动白平衡输入在取样中变化；未提交')
        history = e._history_controller()
        row = e._docs[e._doc_index]
        self.baseline = {'pipeline': pipeline, 'document': str(e._load_id),
                         'signature': e._hist_sig(e._history_capture()),
                         'undo': tuple(history.undo), 'redo': tuple(history.redo),
                         'expected_group': e._history_group('white_balance', request),
                         'group': history.group, 'group_ns': history.group_ns,
                         'dirty': e._project_dirty, 'row': row,
                         'edit_time': ('_library_edit_time_ns' in row, row.get('_library_edit_time_ns'))}
        return {**before, **result}

    def apply(self, patch):
        self.transaction = {'phase': 'unknown'}
        return self.engine.cmd_exposure(patch, preserve_reference=True, auto_transaction=self.transaction)

    def settle(self, phase):
        # Only this private adapter can settle the existing recovery boundary.
        from .white_balance_auto_recovery import mark
        try:
            mark(self.engine, phase)
        finally:
            # A receipt must not retain an old full-image pipeline/history after
            # a document switch. Only bounded scalar diagnostics survive.
            self.baseline = None

    def verify(self, phase):
        """Post-history proof, not inferred from a frame or queue acceptance."""
        if phase not in ('applied', 'no_change', 'rolled_back'):
            return
        e, base = self.engine, self.baseline
        if base is None or e._vram is not base['pipeline'] or str(e._load_id) != base['document']:
            raise ValueError('Auto WB terminal document/pipeline proof failed')
        history = e._history_controller()
        if phase == 'applied':
            if (len(history.undo) != min(len(base['undo'])+1, history.limit) or not history.undo
                    or history.redo or history.group != base['expected_group']
                    or e._hist_sig(history.undo[-1]) != base['signature']):
                raise ValueError('Auto WB did not record the exact canonical undo step')
            return
        same = lambda current, old: len(current) == len(old) and all(a is b for a, b in zip(current, old))
        row = base['row']
        if (e._hist_sig(e._history_capture()) != base['signature']
                or not same(history.undo, base['undo']) or not same(history.redo, base['redo'])
                or history.group != base['group'] or history.group_ns != base['group_ns']
                or e._project_dirty != base['dirty']
                or ('_library_edit_time_ns' in row, row.get('_library_edit_time_ns')) != base['edit_time']):
            raise ValueError('Auto WB no-change/rollback recipe and history proof failed')
