# SPDX-License-Identifier: GPL-3.0-or-later
"""Serialized boundaries for independent current-photo creative modules.

Each family retains its own state, versioned recipes, source proofs and receipts.
This is a static registration boundary, not dynamic plugin loading.
"""

def guard_other(engine, name, request):
    from .portrait_crop_routes import guard_other as crop_guard
    crop_guard(engine, name, request)
    from .lens_blur_host import guard_other as lens_guard
    from .expression_replacement_host import guard_other as expression_guard
    from .light_glow_host import guard_other as glow_guard
    from .creative_selection_host import guard_other as selection_guard
    from .hair_unification_controller import guard_other as hair_unification_guard
    hair_unification_guard(engine, name, request)
    selection_guard(engine, name, request)
    lens_guard(engine, name, request)
    expression_guard(engine, name, request)
    glow_guard(engine, name, request)


def rejected(engine, name, request, error, boundary, emit):
    if not error:
        return
    started = bool(boundary and boundary['started'])
    if name == 'portrait_crop':
        from .portrait_crop_routes import dispatch_rejected
        dispatch_rejected(engine, request, error, started, emit)
    elif name == 'lens_blur':
        from .lens_blur_host import dispatch_rejected
        dispatch_rejected(request, error, started, emit, engine=engine)
    elif name == 'expression_replacement':
        from .expression_replacement_host import dispatch_rejected
        dispatch_rejected(engine, request, error, started, emit)
    elif name == 'light_glow':
        from .light_glow_host import dispatch_rejected
        dispatch_rejected(request, error, started, emit, engine=engine)

    elif name == 'creative_selection':
        from .creative_selection_host import dispatch_rejected
        dispatch_rejected(engine, request, error, started, emit)
    elif name == 'hair_unification':
        from .hair_unification_controller import dispatch_rejected
        dispatch_rejected(engine, request, error, started, emit)
    elif name == 'background_material_library':
        from .background_material_host import dispatch_rejected
        dispatch_rejected(engine, request, error, started, emit)
