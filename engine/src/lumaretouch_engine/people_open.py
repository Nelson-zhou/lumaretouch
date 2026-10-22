"""Restore retained analysis before first edited frame; keep correction UI reachable."""
from . import local_mask_state as SOURCE


def prepare(engine,decoded,request):
    if engine._precompute is not None:return
    state=engine._people_owner().snapshot();asset=SOURCE.source_digest(engine._doc_path)
    faces=[face for face in state['faces'].values() if face['asset_sha256']==asset]
    if not faces:return
    from .face import build
    backend=(engine._precompute_backend or 'mediapipe')
    if backend=='auto':backend='mediapipe' # Never upgrade a frozen owner through a silent fallback.
    try:
        producer=build(backend,request.get('model_dir'))
        try:engine._precompute=producer(decoded.rgb)
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
