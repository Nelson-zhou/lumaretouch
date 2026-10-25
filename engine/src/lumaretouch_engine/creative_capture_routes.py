# SPDX-License-Identifier: GPL-3.0-or-later
"""Serialized boundaries for independent current-photo creative modules.

Each family retains its own state, versioned recipes, source proofs and receipts.
This is a static registration boundary, not dynamic plugin loading.
"""

def guard_other(engine, name, request):
    from .lens_blur_host import guard_other as lens_guard
    from .expression_replacement_host import guard_other as expression_guard
    from .light_glow_host import guard_other as glow_guard
    lens_guard(engine, name, request)
    expression_guard(engine, name, request)
    glow_guard(engine, name, request)


def rejected(engine, name, request, error, boundary, emit):
    if not error:
        return
    started = bool(boundary and boundary['started'])
    if name == 'lens_blur':
        from .lens_blur_host import dispatch_rejected
        dispatch_rejected(request, error, started, emit, engine=engine)
    elif name == 'expression_replacement':
        from .expression_replacement_host import dispatch_rejected
        dispatch_rejected(engine, request, error, started, emit)
    elif name == 'light_glow':
        from .light_glow_host import dispatch_rejected
        dispatch_rejected(request, error, started, emit, engine=engine)
