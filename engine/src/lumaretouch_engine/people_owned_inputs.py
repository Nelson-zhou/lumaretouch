"""One preview forwarding contract for independently owned portrait inputs.

Every engine-owned preview path supplies body ownership and hair source evidence
explicitly. An optional missing argument must not silently remove another edit.
This helper does not own state, construct evidence, publish or warp anything.
"""
_MISSING = object()


def preview(engine, state=None, *, body_bank=_MISSING, body_source=None, support_bank=_MISSING):
    state = engine._people_owner().snapshot() if state is None else state
    support_bank=engine._people_support if support_bank is _MISSING else support_bank
    document_id=engine._people_binding()['document_id']
    from .people_cross_owner import validate_owner
    validate_owner(state,engine._people_source()['sha256'],document_id)
    from .creative_derived_source import record, binding, analysis_rgb, verify_precompute
    if record(engine) is not None:
        from .creative_derived_effects import require_graph
        owned = binding(engine); require_graph(state,owned,document_id=document_id)
        verify_precompute(engine,engine._precompute)
        from .creative_derived_makeup import validate_supports, input_banks
        validate_supports(state,support_bank,owned['sha256'])
        from .creative_derived_recovery import validate_supports as validate_recovery
        validate_recovery(state,support_bank,owned)
        from .creative_derived_hair import preview_inputs
        hair_inputs=preview_inputs(engine,state,owned)
        body = engine._body_bank() if body_bank is _MISSING else body_bank
        from .creative_derived_body import validate as validate_body
        if body is not None:validate_body(body,owned)
        body_pixels=None
        from .body_pose_render import needs_arm_replay
        if body is not None and needs_arm_replay(body):
            from .creative_derived_arm_input import capture
            body_pixels=capture(engine)
        if body_source is not None and body_source != owned:
            raise ValueError('Derived portrait preview source differs from its retained binding')
        # No resolver receives the original path. Reviewed makeup receives only the
        # canonical review bank; it verifies source, face and landmark ownership.
        # The runtime
        # checks the pipeline RGB against this owned inference/display proxy.
        return {'document_id':document_id,'creative_source':owned,'creative_proxy':analysis_rgb(engine),
                **input_banks(support_bank),**hair_inputs,
                'body_bank':body,'body_source':owned,'body_source_pixels':body_pixels}
    from .hair_colour_project import preview_kwargs
    return {'document_id':document_id,**preview_kwargs(engine, state),
            'eye_light_assets': support_bank,
            'blush_makeup_assets': support_bank,
            'lipstick_assets': support_bank,
            'eyeliner_assets': support_bank,
            'eyelash_assets': support_bank,
            'iris_makeup_assets': support_bank,
            'brow_makeup_assets': support_bank,
            'body_bank': engine._body_bank() if body_bank is _MISSING else body_bank,
            'body_source': engine._people_source() if body_source is None else body_source,
            'body_source_path': engine._doc_path}
