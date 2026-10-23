"""Extracted interactive tool routes; lifecycle/history remain engine-owned."""
def _emit(event):
    from .server import emit
    emit(event)

class StudioToolsMixin:
    def _manual_liquify_controller(self):
        from .manual_liquify_controller import controller
        return controller(self, _emit)

    def cmd_manual_liquify(self, p): self._manual_liquify_controller().apply(p)

    def cmd_manual_liquify_preview(self, p):
        from .manual_liquify_preview import controller
        controller(self, _emit).handle(p)

    def _effect_recovery_controller(self):
        from .effect_recovery_controller import controller
        return controller(self, _emit)

    def cmd_effect_recovery(self, p): self._effect_recovery_controller().apply(p)

    def cmd_local_grade_live(self, p):
        from .local_grade_live import controller
        controller(self, _emit).handle(p)

    def cmd_effect_recovery_preview(self, p):
        from .effect_recovery_preview import controller
        controller(self, _emit).handle(p)

    def _studio_background_controller(self):
        from .studio_background_controller import controller
        return controller(self, _emit)

    def cmd_studio_background(self, p): self._studio_background_controller().apply(p)

    def cmd_studio_background_preview(self, p):
        from .studio_background_preview import controller
        controller(self, _emit).handle(p)

    def _optics_controller(self):
        from .optics_controller import controller
        return controller(self, _emit)

    def cmd_optics(self, p): self._optics_controller().apply(p)

    def cmd_optics_preview(self, p):
        from .optics_preview import controller
        controller(self, _emit).handle(p)

    def _sky_replacement_controller(self):
        from .sky_replacement_controller import controller
        return controller(self, _emit)

    def cmd_sky_replacement(self, p): self._sky_replacement_controller().apply(p)

    def cmd_sky_replacement_preview(self, p):
        from .sky_replacement_preview import controller
        controller(self, _emit).handle(p)

    def cmd_common_background(self,p):
        from .common_background_controller import controller
        controller(self,_emit).handle(p)

    def cmd_common_background_preview(self,p):
        from .common_background_review import controller
        controller(self,_emit).handle(p)
