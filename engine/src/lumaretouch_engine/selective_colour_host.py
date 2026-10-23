"""Server adapter. Must be installed with integration hooks in INTEGRATION.md."""
from . import selective_colour_state as S, selective_colour_adapters as A
from .selective_colour_stage import SelectiveColourStage


class SelectiveColourHost:
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
            raise RuntimeError('Selective colour outcome uncertain; reload required')
        reason = self.engine._guard_editable('selective colour')
        if reason:
            raise ValueError(reason)

    def render_preview(self, recipe, cancelled):
        self.guard()
        if cancelled():
            raise InterruptedError('Selective colour preview cancelled')
        e = self.engine
        # Preview temporarily installs only stage, never the persistent recipe.
        # _write_current_frame returns a frame record; dispatcher must not emit it
        # outside the fenced preview envelope. Native chunk cancellation attached.
        previous = e._vram.selective_colour
        stage = SelectiveColourStage(recipe)
        stage.cancelled = lambda: cancelled() or getattr(e,'_selective_colour_cancelled',lambda:False)()
        try:
            e._selective_colour_preview_active=True
            e._vram.selective_colour = stage
            frame = e._write_current_frame('selective_colour_preview')
            if cancelled():
                raise InterruptedError('Selective colour preview cancelled')
            return frame
        finally:
            e._selective_colour_preview_active=False
            e._vram.selective_colour = previous

    def render_committed(self):
        self.guard()
        return self.engine._write_current_frame('selective_colour_cancel')

    def commit(self, recipe, document, revision):
        self.guard()
        if self.context() != (document, revision):
            raise ValueError('Selective colour commit is stale')
        e = self.engine
        e._cancel_snapshot('selective_colour')
        e._close_owned_previews()
        before = e._history_capture()
        history=e._history_controller()
        ledger=(list(history.undo),list(history.redo),history.group,history.group_ns)
        dirty=e._project_dirty
        previous = A.capture(e)
        changed = previous[S.KEY] != recipe
        try:
            A.restore(e, {S.KEY: recipe})
            e._vram.selective_colour.cancelled=getattr(e,'_selective_colour_cancelled',lambda:False)
            # Verify frame before recording one non-coalesced gesture history.
            frame = e._write_current_frame('selective_colour')
            if changed:
                e._history_record('selective_colour', before, coalesce=False)
            e._fence_current_document()
            return {'frame': frame, 'recipe': recipe, 'revision': self.context()[1],
                    'history': e._history_report(), 'no_change': not changed}
        except Exception:
            # A history write failure can have mutated history. Never pretend a
            # restored recipe alone establishes full rollback; require reload.
            try:
                e._selective_colour_publication=None
                e._selective_colour_cancelled=lambda:False
                e._history_apply(before)
                A.restore(e, previous)
                history.undo,history.redo,history.group,history.group_ns=ledger
                e._project_dirty=dirty
                e._write_current_frame('selective_colour_rollback')
            except Exception:
                self.requires_reload = True
                self.failure_document = str(e._load_id)
            raise
