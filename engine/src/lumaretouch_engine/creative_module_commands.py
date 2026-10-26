# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in creative command boundary; families retain their own state/history.

Extracted command wrappers preserve existing serialized dispatch. This is not a
dynamic plugin loader and does not share numerical implementations between tools.
"""

class CreativeModuleCommandsMixin:
    def cmd_upscale_restore(self, request):
        from .upscale_restore_host import handle
        from .server import emit
        return handle(self, request, emit)

    def cmd_light_glow(self, request):
        from .light_glow_host import handle
        from .server import emit
        return handle(self, request, emit)

    def cmd_lens_blur(self, request):
        from .lens_blur_host import handle
        from .server import emit
        return handle(self, request, emit)

    def cmd_expression_replacement(self, request):
        from .expression_replacement_host import handle
        from .server import emit
        return handle(self, request, emit)

    def cmd_creative_document(self, request):
        from .creative_document_host import handle
        from .server import emit
        return handle(self, request, emit)

    def cmd_creative_selection(self, request):
        from .creative_selection_host import handle
        from .server import emit
        return handle(self, request, emit)
