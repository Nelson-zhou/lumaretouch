"""One preview forwarding contract for independently owned portrait inputs.

Every engine-owned preview path supplies body ownership and hair source evidence
explicitly. An optional missing argument must not silently remove another edit.
This helper does not own state, construct evidence, publish or warp anything.
"""
_MISSING = object()


def preview(engine, state=None, *, body_bank=_MISSING, body_source=None):
    from .hair_colour_project import preview_kwargs
    state = engine._people_owner().snapshot() if state is None else state
    return {**preview_kwargs(engine, state),
            'eye_light_assets': engine._people_support,
            'blush_makeup_assets': engine._people_support,
            'lipstick_assets': engine._people_support,
            'eyeliner_assets': engine._people_support,
            'eyelash_assets': engine._people_support,
            'brow_makeup_assets': engine._people_support,
            'body_bank': engine._body_bank() if body_bank is _MISSING else body_bank,
            'body_source': engine._people_source() if body_source is None else body_source,
            'body_source_path': engine._doc_path}
