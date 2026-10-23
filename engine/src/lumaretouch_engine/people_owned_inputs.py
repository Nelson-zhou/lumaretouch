"""One preview forwarding contract for independently owned portrait inputs.

Every engine-owned preview path supplies body ownership and hair source evidence
explicitly. An optional missing argument must not silently remove another edit.
This helper does not own state, construct evidence, publish or warp anything.
"""
_MISSING = object()


def preview(engine, state=None, *, body_bank=_MISSING, body_source=None):
    state = engine._people_owner().snapshot() if state is None else state
    from .creative_derived_source import record, binding, analysis_rgb, verify_precompute
    if record(engine) is not None:
        from .creative_derived_effects import require_graph
        owned = binding(engine); require_graph(state,owned)
        verify_precompute(engine,engine._precompute)
        from .creative_derived_makeup import validate_supports, input_banks
        validate_supports(state,engine._people_support,owned['sha256'])
        body = engine._body_bank() if body_bank is _MISSING else body_bank
        if body is not None and (body['bodies'] or body['analysis_runs'] or body['support_assets']):
            raise ValueError('Derived portrait preview cannot consume original-file body observations')
        if body_source is not None and body_source != owned:
            raise ValueError('Derived portrait preview source differs from its retained binding')
        # No resolver receives the original path. Reviewed makeup receives only the
        # canonical review bank; it verifies source, face and landmark ownership.
        # The runtime
        # checks the pipeline RGB against this owned inference/display proxy.
        return {'creative_source':owned,'creative_proxy':analysis_rgb(engine),
                **input_banks(engine._people_support)}
    from .hair_colour_project import preview_kwargs
    return {**preview_kwargs(engine, state),
            'eye_light_assets': engine._people_support,
            'blush_makeup_assets': engine._people_support,
            'lipstick_assets': engine._people_support,
            'eyeliner_assets': engine._people_support,
            'eyelash_assets': engine._people_support,
            'iris_makeup_assets': engine._people_support,
            'brow_makeup_assets': engine._people_support,
            'body_bank': engine._body_bank() if body_bank is _MISSING else body_bank,
            'body_source': engine._people_source() if body_source is None else body_source,
            'body_source_path': engine._doc_path}
