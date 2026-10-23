"""Restore retained analysis before first edited frame; keep correction UI reachable."""
from . import local_mask_state as SOURCE


def restore_source(engine):
    """Rebuild missing semantic input after an immutable-source history switch.

    Measured landmark ownership remains in the retained graph/store. Inference
    supplies source/model-matched semantic fields; ordinary binding restores the
    exact retained landmark revisions instead of inventing face associations.
    Missing backends leave that intent retained and visibly suspended.
    """
    from types import SimpleNamespace
    from .creative_derived_source import analysis_rgb, verify_precompute
    if engine._precompute is not None:
        verify_precompute(engine,engine._precompute)
        return
    source=engine._people_source()
    prepare(engine,SimpleNamespace(rgb=analysis_rgb(engine),src_w=source['width'],src_h=source['height']),{})


def prepare(engine,decoded,request):
    if engine._precompute is not None:return
    state=engine._people_owner().snapshot();asset=engine._people_source()['sha256']
    faces=[face for face in state['faces'].values() if face['asset_sha256']==asset]
    from .creative_smoothing_host import needs_analysis
    if not faces and not needs_analysis(engine):return
    from .hair_colour_replay import restore_open
    if getattr(engine,'_creative_base',None) is None and restore_open(engine,decoded):return
    from .face import build
    backend=(engine._precompute_backend or 'mediapipe')
    if backend=='auto':backend='mediapipe' # Never upgrade a frozen owner through a silent fallback.
    try:
        producer=build(backend,request.get('model_dir'))
        try:
            if getattr(engine,'_creative_base',None) is not None and getattr(producer,'name',None)!='mediapipe':
                raise ValueError('Composite reanalysis requires the actual MediaPipe backend')
            from .creative_derived_source import analysis_rgb, stamp_precompute
            rgb=analysis_rgb(engine) if getattr(engine,'_creative_base',None) is not None else decoded.rgb
            engine._precompute=producer(rgb)
            stamp_precompute(engine,engine._precompute,rgb)
        finally:
            close=getattr(producer,'close',None)
            if close is not None:close()
        engine._precompute_backend=backend
    except (ValueError,RuntimeError,OSError) as error:
        from .people_host import emit
        emit({'event':'engine_warn','warn':'Retained people analysis could not be restored; edits are preserved and export is blocked: '+str(error)})


def render(engine,pipe,render_edited):
    reason=getattr(pipe,'people_suspended',None)
    if not reason:return render_edited()
    # This is a visibly unapplied original loading view, NEVER an edited render.
    # It permits selecting/correcting unresolved regions instead of trapping the
    # user behind a failed load. All edit/export paths still require_ready().
    pipe.render_original()
    from .people_host import emit
    emit({'event':'engine_warn','warn':'Showing original only; retained people edits are suspended: '+reason})


def flags(engine):
    reason=getattr(engine._vram,'people_suspended',None)
    return {} if not reason else {'people_render_suspended':reason,'display_quality':'original_unapplied','suspended_effects':['people']}
