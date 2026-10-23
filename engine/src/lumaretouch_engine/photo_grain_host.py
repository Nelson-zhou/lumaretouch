"""Server adapter. Must be installed with integration hooks in INTEGRATION.md."""
from . import photo_grain_state as S, photo_grain_adapters as A
from .photo_grain_stage import PhotoGrainStage


class PhotoGrainHost:
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
            raise RuntimeError('Photo grain outcome uncertain; reload required')
        reason = self.engine._guard_editable('photo grain')
        if reason:
            raise ValueError(reason)

    def render_preview(self, recipe, cancelled):
        self.guard()
        if cancelled():
            raise InterruptedError('Photo grain preview cancelled')
        e = self.engine
        # Preview temporarily installs only stage, never the persistent recipe.
        # _write_current_frame returns a frame record; dispatcher must not emit it
        # outside the fenced preview envelope. Native chunk cancellation attached.
        previous = getattr(e, '_photo_grain_render_override', None)
        try:
            e._photo_grain_preview_active = True
            e._photo_grain_render_override = S.check(recipe)
            return self.render_source_frame('photo_grain_preview', cancelled)
        finally:
            e._photo_grain_preview_active = False
            e._photo_grain_render_override = previous

    def render_source_frame(self, reason, cancelled=lambda: False):
        # Host must bind full-resolution post-colour source rendering then its
        # canonical geometry/downsample/shared-frame publisher. No proxy fallback.
        renderer = getattr(self.engine, '_photo_grain_source_renderer', None)
        if not callable(renderer):
            raise RuntimeError('Photo grain source-resolution renderer is not integrated')
        return renderer(reason=reason, cancelled=cancelled)

    def render_committed(self):
        self.guard()
        return self.render_source_frame('photo_grain_cancel')

    def commit(self, recipe, document, revision):
        self.guard()
        if self.context() != (document, revision):
            raise ValueError('Photo grain commit is stale')
        e = self.engine
        e._cancel_snapshot('photo_grain')
        e._close_owned_previews()
        before = e._history_capture()
        history=e._history_controller()
        ledger=(list(history.undo),list(history.redo),history.group,history.group_ns)
        dirty=e._project_dirty
        previous = A.capture(e)
        changed = previous[S.KEY] != recipe
        try:
            A.restore(e, {S.KEY: recipe})
            # Verify frame before recording one non-coalesced gesture history.
            frame = self.render_source_frame('photo_grain', getattr(e, '_photo_grain_cancelled', lambda: False))
            if changed:
                e._history_record('photo_grain', before, coalesce=False)
            e._fence_current_document()
            return {'frame': frame, 'recipe': recipe, 'revision': self.context()[1],
                    'history': e._history_report(), 'no_change': not changed}
        except Exception:
            # A history write failure can have mutated history. Never pretend a
            # restored recipe alone establishes full rollback; require reload.
            try:
                e._photo_grain_publication=None
                e._photo_grain_cancelled=lambda:False
                e._history_apply(before)
                A.restore(e, previous)
                history.undo,history.redo,history.group,history.group_ns=ledger
                e._project_dirty=dirty
                self.render_source_frame('photo_grain_rollback')
            except Exception:
                self.requires_reload = True
                self.failure_document = str(e._load_id)
            raise
