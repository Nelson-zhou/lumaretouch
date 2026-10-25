# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit fresh-original analysis, using the existing portrait/state owners.

This is a retained preparation transaction, NOT read-only review or a second
history/graph owner. The handoff invokes it only on the explicit prepare action.
No inference is performed merely by constructing or importing it.
"""
from .optics_candidate_identity import fingerprint
from .people_preset_plan import clone_state, graph_content, require_active_owner
from . import creative_derived_source as SOURCE, virtual_copy_people as V
from .workflow_preset_dispatch import dispatch

COMMAND = {'cmd': 'precompute', 'backend': 'mediapipe', 'channel': 'skin'}
DERIVED_FIELDS = {'_precompute', '_precompute_backend', '_channel', '_face_index',
    '_face_box', '_deform', '_enhance', '_brow_shape_owner', '_nose_shape_owner',
    '_eye_shape_owner', '_mouth_shape_owner'}


def _without(value, keys):
    return {key: item for key, item in value.items() if key not in keys}


def _runtime(engine):
    return {'analyses': clone_state(engine.__dict__.get('_people_analyses', {})),
        **{key: clone_state(engine.__dict__.get(field, {})) for key, field in V.FIELDS.items()}}


def require_fresh(engine, row):
    """One canonical definition of unedited; never relax to a few zero sliders."""
    recovery = engine.__dict__.get('_project_recovery_runtime')
    if recovery is not None and recovery.tainted:
        raise ValueError('Preparation cannot settle an existing uncertain project recovery boundary')
    if (row.get('copy_number', 0) != 0 or SOURCE.record(engine) is not None
            or engine._project_dirty or engine._undo or engine._redo):
        raise ValueError('Skin preparation requires a clean fresh original with no undo/redo history')
    state = engine._capture_state()
    fresh = engine._fresh_doc_state()
    if fingerprint(_without(state, {'_proxy'})) != fingerprint(_without(fresh, {'_proxy'})):
        raise ValueError('Skin preparation cannot replace an edited or already analysed target')
    # Canonical defaults may evolve; this preparation must remain pixel-neutral.
    if state['_strength'] != 0.0 or state['_channel'] is not None:
        raise ValueError('Fresh preparation requires zero smoothing strength and no selected channel')
    return clone_state(state)


class SkinPreparation:
    """Only the exclusive retained handoff may hold this ephemeral proof."""
    def __init__(self, engine, row, recheck):
        if not callable(recheck):
            raise ValueError('Preparation requires its retained source/document lease')
        recheck()
        self.engine, self.row, self.recheck = engine, row, recheck
        if V.current_row(engine) is not row or not engine._load_id:
            raise ValueError('Open the exact preparation target first')
        self.load_id = engine._load_id
        self.owner = require_active_owner(engine)
        self.context = engine.__dict__['_people_active_context']
        self.before = require_fresh(engine, row)
        self.source = SOURCE.row_proof({**row, 'state': self.before})
        self.asset = self.source['asset_sha256']
        self.graph = self.owner.snapshot()
        self.slice = self.owner.capture_document(self.asset)
        if (self.slice['faces'] or self.slice['overrides'] or self.slice['analysis_run'] is not None
                or any(item['status'] == 'unresolved' for item in self.slice['unresolved_legacy'])):
            raise ValueError('Fresh preparation cannot replace retained target people or unresolved intent')
        self.runtime = _runtime(engine)
        self.started = False
        self.expected = None
        self.restored = False
        self.ready = False
        self.recovery = engine.__dict__.get('_project_recovery_runtime')
        self.initial = self._proof()

    def _check(self):
        self.recheck()
        engine = self.engine
        recovery = engine.__dict__.get('_project_recovery_runtime')
        if recovery is not self.recovery or recovery is not None and recovery.tainted:
            raise ValueError('Project recovery marked this analysis uncertain; preparation cannot clear that owner taint')
        if (V.current_row(engine) is not self.row or engine._load_id != self.load_id
                or require_active_owner(engine) is not self.owner
                or engine.__dict__['_people_active_context'] is not self.context):
            raise ValueError('Preparation lost its exact loaded document or portrait owner')
        SOURCE.verify_row({**self.row, 'state': engine._capture_state()}, self.source)
        if engine._undo or engine._redo or engine._project_dirty:
            raise ValueError('Preparation cannot discard a normal edit or dirty project')

    def _proof(self):
        self._check()
        return (self.owner.fence, fingerprint(self.engine._capture_state()),
                fingerprint(_runtime(self.engine)), fingerprint(self.owner.snapshot()))

    def _target_only(self):
        """The normal document-slice owner validates rollback scope, not this DTO."""
        candidate = self.owner.stage_document_restore(self.slice,
            expected_asset_fence=self.owner.asset_fences.get(self.asset, 0),
            expected_association_fence=self.owner.association_fence)
        if graph_content(candidate) != graph_content(self.graph):
            raise ValueError('Preparation changed another source or shared portrait association')
        after = _runtime(self.engine)
        for key in after:
            left, right = self.runtime[key], after[key]
            if key in ('analyses', 'people_cursors', 'people_targets'):
                left, right = _without(left, {self.asset}), _without(right, {self.asset})
            elif key == 'people_landmarks':
                def other(rows):
                    return {name: value for name, value in rows.items()
                            if value.get('face_ref', {}).get('asset_sha256') != self.asset}
                left, right = other(left), other(right)
            if fingerprint(left) != fingerprint(right):
                raise ValueError('Preparation changed unrelated portrait evidence or support')

    def analyse(self):
        if self.started or self.restored:
            raise ValueError('An analysis attempt cannot be redispatched through the same preparation')
        if self._proof() != self.initial:
            raise ValueError('Fresh target changed before the explicit analysis action')
        self.started = True
        try:
            # Exact explicit backend: absent models/zero/multiple faces never
            # become template analysis or permission to copy another face mask.
            dispatch(self.engine, COMMAND, self._check)
            self._check()
            pc = self.engine._precompute
            if (pc is None or getattr(pc, 'backend', None) != 'mediapipe'
                    or type(getattr(pc, 'num_faces', None)) is not int or pc.num_faces != 1
                    or getattr(pc, 'masks', {}).get('skin') is None
                    or self.engine._channel != 'skin'):
                raise ValueError('Target preparation requires one real MediaPipe face and its own skin mask')
            # Establish the existing retained-person owner BEFORE rendering or
            # approving a preset. The canonical binder/mirror owns these changes.
            self.engine._people_sync(strict=True)
            self._check()
            self._target_only()
            after = self.engine._capture_state()
            if fingerprint(_without(after, DERIVED_FIELDS)) != fingerprint(_without(self.before, DERIVED_FIELDS)):
                raise ValueError('Analysis changed a non-preparation recipe field')
            if (after['_deform']['amounts'] != self.before['_deform']['amounts']
                    or after['_enhance']['amounts'] != self.before['_enhance']['amounts']):
                raise ValueError('Analysis unexpectedly changed visible portrait parameters')
            from .workflow_preset_retained_skin import require_target
            require_target(self.engine, self.row, self.engine._people_preset_capture())
            self.ready = True
        finally:
            # A failed/partial attempt still owns its exact observed state. If
            # the final proof cannot be acquired, caller must retain Unknown.
            self.expected = self._proof()

    def assert_current(self):
        if not self.ready or self.restored or self.expected is None or self._proof() != self.expected:
            raise ValueError('Prepared target changed; do not repeat analysis or overwrite its state')

    def restore(self):
        """Cancel a known preparation, never undo an applied preset or later edit."""
        if self.restored or not self.started or self.expected is None:
            raise ValueError('No exact unresolved preparation is available for cancellation')
        if self._proof() != self.expected:
            raise ValueError('Preparation changed after observation; cancellation must not overwrite it')
        self._target_only()
        # Existing document history owner restores only this source slice with
        # monotonic fences. There is no new graph, rewound fence or history entry.
        self.engine._people_history_apply(self.slice, source_state=self.before)
        self.engine._people_analyses = clone_state(self.runtime['analyses'])
        for key, field in V.FIELDS.items():
            setattr(self.engine, field, clone_state(self.runtime[key]))
        self.engine._people_analysis_key = None
        self.engine._fence_current_document()
        frame = self.engine._replay_state(clone_state(self.before),
            mode='workflow_preparation_cancel', replayed_for='workflow_preparation_cancel')
        self._check()
        if (fingerprint(self.engine._capture_state()) != fingerprint(self.before)
                or graph_content(self.owner.snapshot()) != graph_content(self.graph)
                or fingerprint(_runtime(self.engine)) != fingerprint(self.runtime)):
            raise ValueError('Preparation cancellation did not restore the original complete neutral state')
        self.engine._remember_current()
        self.expected = self._proof()
        self.restored = True
        from .server import emit
        emit(frame)
        self.engine.emit_session_state()
