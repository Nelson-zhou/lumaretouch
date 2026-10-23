"""Server adapter. Must be installed with integration hooks in INTEGRATION.md."""
from . import primary_calibration_state as S, primary_calibration_adapters as A
from .primary_calibration_stage import PrimaryCalibrationStage


class PrimaryCalibrationHost:
    def __init__(self, engine):
        self.engine = engine
        self.requires_reload = False
        self.failure_document = None

    def context(self):
        from .extended_tone_host import revision
        return (str(self.engine._load_id), revision(self.engine))

    def guard(self):
        if self.requires_reload and str(self.engine._load_id) != self.failure_document:
            self.requires_reload=False
            self.failure_document=None
        if self.requires_reload:
            raise RuntimeError('Primary calibration outcome uncertain; reload required')
        reason = self.engine._guard_editable('primary calibration')
        if reason:
            raise ValueError(reason)

    def render_preview(self, recipe, cancelled):
        self.guard()
        if cancelled():
            raise InterruptedError('Primary calibration preview cancelled')
        e = self.engine
        # Preview temporarily installs only stage, never the persistent recipe.
        # _write_current_frame returns a frame record; dispatcher must not emit it
        # outside the fenced preview envelope. Native chunk cancellation attached.
        previous = e._vram.primary_calibration
        stage = PrimaryCalibrationStage(recipe)
        stage.cancelled = lambda: cancelled() or getattr(e,'_primary_calibration_cancelled',lambda:False)()
        try:
            e._primary_calibration_preview_active=True
            e._vram.primary_calibration = stage
            frame = e._write_current_frame('primary_calibration_preview')
            if cancelled():
                raise InterruptedError('Primary calibration preview cancelled')
            return frame
        finally:
            e._primary_calibration_preview_active=False
            e._vram.primary_calibration = previous

    def render_committed(self):
        self.guard()
        return self.engine._write_current_frame('primary_calibration_cancel')

    def commit(self, recipe, document, revision):
        self.guard()
        if self.context() != (document, revision):
            raise ValueError('Primary calibration commit is stale')
        e = self.engine
        e._cancel_snapshot('primary_calibration')
        e._close_owned_previews(exclude="primary_calibration")
        before = e._history_capture()
        history=e._history_controller()
        ledger=(list(history.undo),list(history.redo),history.group,history.group_ns)
        dirty=e._project_dirty
        previous = A.capture(e)
        changed = previous[S.KEY] != recipe
        try:
            A.restore(e, {S.KEY: recipe})
            e._vram.primary_calibration.cancelled=getattr(e,'_primary_calibration_cancelled',lambda:False)
            # Verify frame before recording one non-coalesced gesture history.
            frame = e._write_current_frame('primary_calibration')
            if changed:
                e._history_record('primary_calibration', before, coalesce=False)
            e._fence_current_document()
            return {'frame': frame, 'recipe': recipe, 'revision': self.context()[1],
                    'history': e._history_report(), 'no_change': not changed}
        except Exception:
            # A history write failure can have mutated history. Never pretend a
            # restored recipe alone establishes full rollback; require reload.
            try:
                e._primary_calibration_publication=None
                e._primary_calibration_cancelled=lambda:False
                e._history_apply(before)
                A.restore(e, previous)
                history.undo,history.redo,history.group,history.group_ns=ledger
                e._project_dirty=dirty
                e._write_current_frame('primary_calibration_rollback')
            except Exception:
                self.requires_reload = True
                self.failure_document = str(e._load_id)
            raise
