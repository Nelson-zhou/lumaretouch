"""Live smoothing render admission; missing scope never becomes whole image."""


def render_args(engine):
    from .creative_derived_smoothing_runtime import reset
    pipe=engine._vram
    if not engine._strength:
        reset(pipe)
        engine._creative_smoothing_suspended=None
        return 0.,None  # Retain requested scope in the document, not this neutral render.
    if engine._channel and engine._channel not in pipe.mask_names:
        reset(pipe)
        reason='回流图磨皮蒙版尚未恢复；保留强度和作用域，暂不应用，导出需完成当前来源分析。'
        if getattr(engine,'_creative_smoothing_suspended',None)!=reason:
            from .server import emit
            emit({'event':'engine_warn','warn':reason})
        engine._creative_smoothing_suspended=reason
        return 0.,None
    from .creative_derived_smoothing import preview
    preview(engine)  # Mismatched pixels/model/coverage refuse; never silently rebind.
    engine._creative_smoothing_suspended=None
    return engine._strength,engine._channel


def needs_analysis(engine):
    """Semantic effects can exist even when no face was detected or retained."""
    if getattr(engine,'_creative_base',None) is not None and getattr(engine,'_hand_shape',None) is not None:
        raise ValueError('Original-source hand geometry cannot be analyzed or rebound on creative-derived pixels')
    from .studio_background_state import check as studio_recipe
    studio=studio_recipe(getattr(engine,'_studio_background',None))
    return bool(getattr(engine,'_creative_base',None) is not None and (
        studio['region_mode']=='semantic_background' or
        getattr(engine,'_hand_tone',None) is not None or getattr(engine,'_limb_vein',None) is not None or getattr(engine,'_fabric_sweat',None) is not None or getattr(engine,'_fabric_amount',0) or
        (getattr(engine,'_strength',0) and getattr(engine,'_channel',None))))
