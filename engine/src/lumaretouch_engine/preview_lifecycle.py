"""Owned preview lifecycles, with no idle-loop shutdown or orphan workers."""


class PreviewLifecycleMixin:
    def cmd_sky_semantic(self, command):
        from .server import emit
        from .sky_semantic.controller import controller
        controller(self, emit).handle(command)

    def _tick_owned_previews(self):
        for key in ('_manual_liquify_preview_owner', '_sky_replacement_preview_owner',
                    '_studio_background_preview_owner', '_prompted_mask_owner', '_sky_semantic_owner', '_semantic_colour_owner'):
            owner = self.__dict__.get(key)
            if owner is not None:
                owner.tick()

    def _close_owned_previews(self):
        for key in ('_manual_liquify_preview_owner', '_sky_replacement_preview_owner',
                    '_optics_preview_owner', '_studio_background_preview_owner', '_sky_semantic_owner'):
            owner = self.__dict__.get(key)
            if owner is not None:
                owner.close()
        for key in ('_prompted_mask_owner', '_effect_recovery_preview_owner'):
            owner = self.__dict__.get(key)
            if owner is not None:
                owner.cancel()
