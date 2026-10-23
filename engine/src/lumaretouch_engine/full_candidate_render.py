"""Exact target-owned full rendering, with no live swap or proxy fallback."""


def people_context(engine,row):
    """Read retained ownership without classifying/importing a graph owner."""
    from copy import deepcopy
    from . import virtual_copy_people as V,people_state as S
    if row.get('_people_new_import') and not V.is_private(row):
        raise ValueError('Open this target to establish its document ownership before crop review')
    active=engine.__dict__.get('_people_active_context')
    if engine.__dict__.get('_people_scope_row') is row and active is not None:
        graph_owner=engine.__dict__.get('_people_graph_owner')
        if graph_owner is None:raise ValueError('Current portrait ownership is unavailable')
        return V.check({'version':1,'people_graph':graph_owner.snapshot(),
            **{key:deepcopy(engine.__dict__.get(field,{})) for key,field in V.FIELDS.items()}})
    if V.is_private(row):
        if V.RUNTIME in row:return V.check(V._snapshot(row[V.RUNTIME]))
        return V.check(row.get(V.KEY))
    project=engine.__dict__.get('_people_project_context')
    if project is not None:
        if active is project:
            return V.check({'version':1,'people_graph':engine._people_graph_owner.snapshot(),
                **{key:deepcopy(engine.__dict__.get(field,{})) for key,field in V.FIELDS.items()}})
        return V.check(V._snapshot(project))
    if active is not None:raise ValueError('Target project portrait ownership is unavailable')
    graph_owner=engine.__dict__.get('_people_graph_owner')
    return V.check({'version':1,'people_graph':S.empty() if graph_owner is None else graph_owner.snapshot(),
        **{key:deepcopy(engine.__dict__.get(field,{})) for key,field in V.FIELDS.items()}})


def identity(engine,row,candidate_state,document_id,revision,*,people_graph=None):
    from . import creative_derived_source as SOURCE, virtual_copy_people as V
    from .optics_candidate_identity import fingerprint
    version=engine._document_versions().version(row)
    current=V.current_row(engine) is row
    if type(document_id) is not str or not document_id or document_id not in (version.document_id,getattr(engine,'_load_id',None) if current else None) or str(version.revision)!=str(revision):
        raise ValueError('Full candidate document identity or revision changed')
    context=people_context(engine,row)
    graph=context['people_graph'] if people_graph is None else people_graph
    # Preset capture can precede remembering the current document row. Compare
    # against the live immutable base, never an older parked row's baseline.
    source_row={**row,'state':{'_creative_base':getattr(engine,'_creative_base',None)}} if current else row
    proof=SOURCE.row_proof(source_row)
    SOURCE.verify_row({**row,'state':candidate_state},proof)
    return {'document_id':document_id,'revision':str(revision),'source_proof':proof,
        'candidate_sha256':fingerprint(candidate_state),
        'people_sha256':fingerprint({'graph':graph,'context':context})},graph,context


def render(engine,row,candidate_state,document_id,revision,*,people_graph=None,cancelled=lambda:False):
    from copy import deepcopy
    from . import local_mask_state as M
    from . import creative_derived_source as SOURCE, virtual_copy_people as V
    from .creative_document_base import from_state, require_rebound_snapshot
    from .decode import load_full,is_raw,_source_bits
    from .cpu_memory_budget import available_estimate
    from .export_recipe import build_export_spec
    from .export import export_float
    from . import local_grade_source as groups,effect_recovery_runtime as recovery
    from . import manual_liquify_runtime as manual,studio_background_runtime as studio,sky_replacement_runtime as sky
    from PIL import Image
    def checkpoint(*_):
        if cancelled():raise ValueError('Full candidate preparation cancelled')
    checkpoint()
    proof,graph,context=identity(engine,row,candidate_state,document_id,revision,people_graph=people_graph)
    path=row['path'];stamp=M.file_stamp(path);state=deepcopy(candidate_state)
    base=from_state(state)
    available=available_estimate();limit=min(32_000_000,max(0,(available-768*1024*1024)//300))
    if limit<4096:raise ValueError('Insufficient memory for complete people target preparation')
    if base is not None:
        from .creative_document_host import require_photo_return
        require_photo_return(base)
        h,w=base['height'],base['width']
        if h*w>limit:raise ValueError('Creative target exceeds the portrait preparation budget; no proxy fallback')
        SOURCE.verify_precompute(state,state.get('_precompute'))
        # The public exporter resolves spec.creative_base exactly once through
        # the packaged float32 bridge. This empty shape carrier is never read
        # as image pixels and avoids decoding or quantizing the original file.
        import numpy as np
        pixels=np.empty((0,0,3),dtype=np.uint8)
    else:
        if is_raw(path):
            from .ops import libraw
            dimensions=libraw.identify(path)
            if dimensions is None or dimensions['w']*dimensions['h']>limit:raise ValueError('Original RAW target exceeds the available portrait budget')
            bits=16
        else:
            with Image.open(path) as image:
                if image.width*image.height>limit:raise ValueError('Original target exceeds the portrait preparation budget')
                bits=16 if _source_bits(image)>8 else 8
        decoded=load_full(path,max_px=limit,device='cpu',want_bits=bits)
        if (decoded.h,decoded.w)!=(decoded.src_h,decoded.src_w) or decoded.draft_used or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size'):
            raise ValueError('People target preparation cannot use reduced source pixels')
        if bits==16 and str(decoded.rgb.dtype)!='uint16':raise ValueError('Full target preparation requires genuine RGB16 input')
        pixels=decoded.rgb;h,w=decoded.h,decoded.w
    checkpoint()
    snap=engine._state_to_export_snap(state,device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0.,source_path=path,people_graph=graph,people_context=context,people_document_id=engine._document_versions().version(row).document_id)
    from .people_export import isolated_snapshot,verify_source
    verify_source(snap,path);snap=isolated_snapshot(snap,for_document=True)
    if base is not None:
        people=snap.get('people')
        if (people is not None and (people['state']!=graph or people['asset_sha256']!=proof['source_proof']['asset_sha256'])) or (people_graph is not None and people is None):
            raise ValueError('Creative target preparation omitted its exact candidate portrait graph')
        frozen_base=from_state(snap)
        if frozen_base is None or frozen_base['id']!=base['id']:
            raise ValueError('Creative target snapshot replaced its immutable source')
        require_rebound_snapshot(snap)
    from . import body_pose_render as body_render, id_background_runtime as id_background, fringe_repair_render as fringe
    for owner in (groups,recovery,manual,studio,sky,body_render,id_background,fringe):owner.check_export_decode(snap,path,stamp,(h,w))
    if snap.get('grade_scope')=='objects':
        M.verify_snapshot(snap,path,(h,w));snap['local_mask_source_path']=path
    spec,skipped=build_export_spec(snap,h,w,for_document=True)
    if skipped:raise ValueError('People target preparation cannot omit existing edits: '+str(skipped))
    from .ops.geometry import out_size
    import numpy as np
    geometry=(snap['crop_rect'],snap['crop_rotation']);expected=out_size(w,h,*geometry)
    if expected[0]*expected[1]>limit:raise ValueError('Expanded crop exceeds complete preparation budget')
    rgb,_=export_float(pixels,spec,geometry=geometry,progress=checkpoint)
    checkpoint()
    if rgb.ndim!=3 or rgb.shape[2]!=3 or (rgb.shape[1],rgb.shape[0])!=expected or not np.issubdtype(rgb.dtype,np.floating) or not np.isfinite(rgb).all():
        raise ValueError('Complete candidate is not finite float RGB at its exact geometry')
    latest,_,_=identity(engine,row,candidate_state,document_id,revision,people_graph=people_graph)
    if M.file_stamp(path)!=stamp or latest!=proof:raise ValueError('Target changed during complete preparation')
    return rgb,{**proof,'source_size':[w,h],'output_size':list(expected)}
